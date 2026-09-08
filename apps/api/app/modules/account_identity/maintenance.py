"""Operator-only account session maintenance; never exposed to HTTP or Agent tools."""
from __future__ import annotations

import re
import sqlite3
import stat
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


class AccountSessionMaintenanceError(ValueError):
    """Stable error code without a database path, account or session token."""


@dataclass(frozen=True)
class AccountSessionMaintenanceReport:
    cutoff: str
    total: int
    active: int
    expired: int
    revoked: int
    unclassified: int
    deleted: int = 0


class AccountSessionMaintenance:
    """Preview or explicitly prune expired and revoked production sessions.

    The store must already exist and match the M14 SQLite adapter schema. A
    malformed row is retained for manual investigation. Reports contain only
    counts and the cutoff time, never account identifiers or token hashes.
    """

    def __init__(
        self, *, database_path: Path, clock: Callable[[], datetime] | None = None
    ) -> None:
        self._path = database_path
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def preview(self) -> AccountSessionMaintenanceReport:
        return self._run(cleanup=False)

    def prune(self, *, confirmed: bool = False) -> AccountSessionMaintenanceReport:
        if confirmed is not True:
            raise AccountSessionMaintenanceError(
                "ACCOUNT_SESSION_CLEANUP_CONFIRMATION_REQUIRED"
            )
        return self._run(cleanup=True)

    def _validated_path(self) -> Path:
        path = self._path.absolute()
        try:
            for index, item in enumerate((path, *path.parents)):
                info = item.lstat()
                if stat.S_ISLNK(info.st_mode) or (
                    getattr(info, "st_file_attributes", 0)
                    & stat.FILE_ATTRIBUTE_REPARSE_POINT
                ):
                    raise AccountSessionMaintenanceError(
                        "ACCOUNT_SESSION_STORE_LINK_UNSAFE"
                    )
                if index == 0 and not stat.S_ISREG(info.st_mode):
                    raise AccountSessionMaintenanceError(
                        "ACCOUNT_SESSION_STORE_NOT_A_FILE"
                    )
                if index > 0 and not stat.S_ISDIR(info.st_mode):
                    raise AccountSessionMaintenanceError(
                        "ACCOUNT_SESSION_STORE_NOT_A_FILE"
                    )
            return path.resolve(strict=True)
        except OSError:
            raise AccountSessionMaintenanceError(
                "ACCOUNT_SESSION_STORE_UNAVAILABLE"
            ) from None

    @staticmethod
    def _validate_schema(connection: sqlite3.Connection) -> None:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT GLOB 'sqlite_*'"
            ).fetchall()
        }
        expected_tables = {
            "m14_accounts",
            "m14_tenants",
            "m14_memberships",
            "m14_account_sessions",
        }
        session_columns = connection.execute(
            "PRAGMA table_info(m14_account_sessions)"
        ).fetchall()
        expected_columns = {
            "token_hash",
            "account_id",
            "tenant_id",
            "created_at",
            "expires_at",
            "revoked_at",
        }
        foreign_keys = connection.execute(
            "PRAGMA foreign_key_list(m14_account_sessions)"
        ).fetchall()
        foreign_key_tables = {row[2] for row in foreign_keys}
        if (
            tables != expected_tables
            or {column[1] for column in session_columns} != expected_columns
            or not any(
                column[1] == "token_hash" and column[5] == 1
                for column in session_columns
            )
            or foreign_key_tables != {"m14_accounts", "m14_tenants"}
            or connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='trigger'"
            ).fetchone()
        ):
            raise AccountSessionMaintenanceError(
                "ACCOUNT_SESSION_STORE_SCHEMA_UNEXPECTED"
            )

    def _run(self, *, cleanup: bool) -> AccountSessionMaintenanceReport:
        cutoff = self._clock()
        if cutoff.tzinfo is None or cutoff.utcoffset() is None:
            raise AccountSessionMaintenanceError(
                "ACCOUNT_SESSION_CLOCK_TIMEZONE_REQUIRED"
            )
        cutoff = cutoff.astimezone(timezone.utc)
        path = self._validated_path()
        mode = "rw" if cleanup else "ro"
        try:
            with closing(
                sqlite3.connect(f"{path.as_uri()}?mode={mode}", uri=True)
            ) as connection:
                connection.execute("BEGIN IMMEDIATE" if cleanup else "BEGIN")
                try:
                    self._validate_schema(connection)
                    counts = dict(
                        active=0, expired=0, revoked=0, unclassified=0
                    )
                    targets: list[tuple[str]] = []
                    rows = connection.execute(
                        "SELECT token_hash, expires_at, revoked_at "
                        "FROM m14_account_sessions"
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
                                        category = (
                                            "expired" if expires_at <= cutoff else "active"
                                        )
                                except (TypeError, ValueError, OverflowError):
                                    pass
                        counts[category] += 1
                        if category in ("expired", "revoked"):
                            targets.append((key,))
                    deleted = 0
                    if cleanup and targets:
                        deleted = connection.executemany(
                            "DELETE FROM m14_account_sessions WHERE token_hash = ?",
                            targets,
                        ).rowcount
                        if deleted != len(targets):
                            raise AccountSessionMaintenanceError(
                                "ACCOUNT_SESSION_CLEANUP_COUNT_MISMATCH"
                            )
                    connection.commit()
                except Exception:
                    connection.rollback()
                    raise
        except sqlite3.Error:
            raise AccountSessionMaintenanceError(
                "ACCOUNT_SESSION_STORE_UNAVAILABLE"
            ) from None
        return AccountSessionMaintenanceReport(
            cutoff=cutoff.isoformat(), total=len(rows), deleted=deleted, **counts
        )
