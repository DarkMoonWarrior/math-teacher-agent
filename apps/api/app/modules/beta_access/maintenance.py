"""Operator-only maintenance; intentionally not exposed to HTTP or Agent tools."""
from __future__ import annotations

import re
import sqlite3
import stat
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


class SessionMaintenanceError(ValueError):
    """Stable error code, never a database path, token or SQL error message."""


@dataclass(frozen=True)
class SessionMaintenanceReport:
    cutoff: str
    total: int
    active: int
    expired: int
    revoked: int
    unclassified: int
    deleted: int = 0


class BetaSessionMaintenance:
    """Preview or explicitly prune invalid sessions in the configured session store.

    Missing stores are never created. Cleanup rechecks eligibility in one write
    transaction, retains unclassifiable records and never touches content stores.
    Reports contain only counts and the evaluation time, not user identifiers.
    """

    def __init__(self, *, database_path: Path, clock: Callable[[], datetime] | None = None):
        self._path = database_path
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def preview(self) -> SessionMaintenanceReport:
        return self._run(cleanup=False)

    def prune(self, *, confirmed: bool = False) -> SessionMaintenanceReport:
        if confirmed is not True:
            raise SessionMaintenanceError("SESSION_CLEANUP_CONFIRMATION_REQUIRED")
        return self._run(cleanup=True)

    def _validated_path(self) -> Path:
        path = self._path.absolute()
        try:
            for index, item in enumerate((path, *path.parents)):
                info = item.lstat()
                if stat.S_ISLNK(info.st_mode) or (
                    getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
                ):
                    raise SessionMaintenanceError("SESSION_STORE_LINK_UNSAFE")
                if index == 0 and not stat.S_ISREG(info.st_mode):
                    raise SessionMaintenanceError("SESSION_STORE_NOT_A_FILE")
                if index > 0 and not stat.S_ISDIR(info.st_mode):
                    raise SessionMaintenanceError("SESSION_STORE_NOT_A_FILE")
            return path.resolve(strict=True)
        except OSError:
            raise SessionMaintenanceError("SESSION_STORE_UNAVAILABLE") from None

    @staticmethod
    def _validate_schema(connection: sqlite3.Connection) -> None:
        tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT GLOB 'sqlite_*'"
        ).fetchall()
        columns = connection.execute("PRAGMA table_info(m12_beta_sessions)").fetchall()
        expected = {"token_hash", "teacher_id", "display_label", "created_at", "expires_at", "revoked_at"}
        if (
            tables != [("m12_beta_sessions",)]
            or not expected.issubset({column[1] for column in columns})
            or not any(column[1] == "token_hash" and column[5] == 1 for column in columns)
            or connection.execute("SELECT 1 FROM sqlite_master WHERE type='trigger'").fetchone()
            or connection.execute("PRAGMA foreign_key_list(m12_beta_sessions)").fetchone()
        ):
            raise SessionMaintenanceError("SESSION_STORE_SCHEMA_UNEXPECTED")

    def _run(self, *, cleanup: bool) -> SessionMaintenanceReport:
        cutoff = self._clock()
        if cutoff.tzinfo is None or cutoff.utcoffset() is None:
            raise SessionMaintenanceError("SESSION_CLOCK_TIMEZONE_REQUIRED")
        cutoff = cutoff.astimezone(timezone.utc)
        path = self._validated_path()
        mode = "rw" if cleanup else "ro"
        try:
            with closing(sqlite3.connect(f"{path.as_uri()}?mode={mode}", uri=True)) as connection:
                # Hold one consistent snapshot; cleanup prevents concurrent session
                # updates between enumerating exact targets and deleting those keys.
                connection.execute("BEGIN IMMEDIATE" if cleanup else "BEGIN")
                try:
                    self._validate_schema(connection)
                    counts = dict(active=0, expired=0, revoked=0, unclassified=0)
                    targets: list[tuple[str]] = []
                    rows = connection.execute(
                        "SELECT token_hash, expires_at, revoked_at FROM m12_beta_sessions"
                    ).fetchall()
                    for key, expiry, revoked in rows:
                        category = "unclassified"
                        if isinstance(key, str) and re.fullmatch(r"[0-9a-f]{64}", key):
                            if revoked is not None:
                                category = "revoked"
                            else:
                                try:
                                    expires_at = datetime.fromisoformat(expiry)
                                    if expires_at.utcoffset() is not None:
                                        category = "expired" if expires_at <= cutoff else "active"
                                except (TypeError, ValueError, OverflowError):
                                    pass
                        counts[category] += 1
                        if category in ("expired", "revoked"):
                            targets.append((key,))
                    deleted = 0
                    if cleanup and targets:
                        deleted = connection.executemany(
                            "DELETE FROM m12_beta_sessions WHERE token_hash = ?", targets,
                        ).rowcount
                        if deleted != len(targets):
                            raise SessionMaintenanceError("SESSION_CLEANUP_COUNT_MISMATCH")
                    connection.commit()
                except Exception:
                    connection.rollback()
                    raise
        except sqlite3.Error:
            raise SessionMaintenanceError("SESSION_STORE_UNAVAILABLE") from None
        return SessionMaintenanceReport(cutoff=cutoff.isoformat(), total=len(rows), deleted=deleted, **counts)
