"""Operator-only M13 retention maintenance; never exposed to HTTP or Agent tools."""
from __future__ import annotations

import re
import sqlite3
import stat
from collections.abc import Callable
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.modules.beta_validation.schemas import (
    METRIC_DEFINITION_VERSION,
    RETENTION_DAYS,
    BetaValidationRetentionReport,
)


_EVENT_ID = re.compile(r"^bve_[0-9a-f]{32}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")


class BetaValidationMaintenanceError(ValueError):
    """Stable error code, never a path, identifier, SQL string or event value."""


class BetaValidationRetention:
    """Preview or explicitly remove only well-formed events older than 90 days.

    The configured store must already exist and match the exact M13 schema.
    Participation acknowledgments and malformed rows are always retained.
    """

    def __init__(
        self,
        *,
        database_path: Path,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._path = database_path
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def preview(self) -> BetaValidationRetentionReport:
        return self._run(cleanup=False)

    def prune(self, *, confirmed: bool = False) -> BetaValidationRetentionReport:
        if confirmed is not True:
            raise BetaValidationMaintenanceError(
                "BETA_VALIDATION_RETENTION_CONFIRMATION_REQUIRED"
            )
        return self._run(cleanup=True)

    def _validated_path(self) -> Path:
        path = self._path.absolute()
        try:
            for index, item in enumerate((path, *path.parents)):
                info = item.lstat()
                is_reparse = bool(
                    getattr(info, "st_file_attributes", 0)
                    & stat.FILE_ATTRIBUTE_REPARSE_POINT
                )
                if stat.S_ISLNK(info.st_mode) or is_reparse:
                    raise BetaValidationMaintenanceError(
                        "BETA_VALIDATION_STORE_LINK_UNSAFE"
                    )
                expected = stat.S_ISREG if index == 0 else stat.S_ISDIR
                if not expected(info.st_mode):
                    raise BetaValidationMaintenanceError(
                        "BETA_VALIDATION_STORE_NOT_A_FILE"
                    )
            return path.resolve(strict=True)
        except OSError:
            raise BetaValidationMaintenanceError(
                "BETA_VALIDATION_STORE_UNAVAILABLE"
            ) from None

    @staticmethod
    def _validate_schema(connection: sqlite3.Connection) -> None:
        tables = {
            row[0]
            for row in connection.execute(
                """SELECT name FROM sqlite_master
                   WHERE type='table' AND name NOT GLOB 'sqlite_*'"""
            )
        }
        event_columns = connection.execute(
            "PRAGMA table_info(m13_beta_validation_events)"
        ).fetchall()
        participant_columns = connection.execute(
            "PRAGMA table_info(m13_beta_validation_participants)"
        ).fetchall()
        expected_events = {
            "event_id",
            "definition_version",
            "participant_key",
            "task_key",
            "workflow",
            "event_type",
            "trust_tier",
            "duration_ms",
            "model_cost_usd",
            "occurred_at",
        }
        expected_participants = {
            "participant_key",
            "notice_version",
            "acknowledged_at",
        }
        invalid = (
            tables
            != {
                "m13_beta_validation_events",
                "m13_beta_validation_participants",
            }
            or expected_events != {column[1] for column in event_columns}
            or expected_participants != {column[1] for column in participant_columns}
            or not any(
                column[1] == "event_id" and column[5] == 1
                for column in event_columns
            )
            or not any(
                column[1] == "participant_key" and column[5] == 1
                for column in participant_columns
            )
            or connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='trigger'"
            ).fetchone()
            or connection.execute(
                "PRAGMA foreign_key_list(m13_beta_validation_events)"
            ).fetchone()
            or connection.execute(
                "PRAGMA foreign_key_list(m13_beta_validation_participants)"
            ).fetchone()
        )
        if invalid:
            raise BetaValidationMaintenanceError(
                "BETA_VALIDATION_STORE_SCHEMA_UNEXPECTED"
            )

    def _run(self, *, cleanup: bool) -> BetaValidationRetentionReport:
        evaluated_at = self._clock()
        if evaluated_at.tzinfo is None or evaluated_at.utcoffset() is None:
            raise BetaValidationMaintenanceError(
                "BETA_VALIDATION_CLOCK_TIMEZONE_REQUIRED"
            )
        evaluated_at = evaluated_at.astimezone(timezone.utc)
        cutoff = evaluated_at - timedelta(days=RETENTION_DAYS)
        path = self._validated_path()
        mode = "rw" if cleanup else "ro"
        try:
            with closing(
                sqlite3.connect(f"{path.as_uri()}?mode={mode}", uri=True)
            ) as connection:
                connection.execute("BEGIN IMMEDIATE" if cleanup else "BEGIN")
                try:
                    self._validate_schema(connection)
                    rows = connection.execute(
                        """SELECT event_id, definition_version, participant_key,
                                  task_key, occurred_at
                           FROM m13_beta_validation_events"""
                    ).fetchall()
                    retained = 0
                    unclassified = 0
                    targets: list[tuple[str]] = []
                    for event_id, version, participant, task, occurred in rows:
                        if not (
                            isinstance(event_id, str)
                            and _EVENT_ID.fullmatch(event_id)
                            and version == METRIC_DEFINITION_VERSION
                            and isinstance(participant, str)
                            and _DIGEST.fullmatch(participant)
                            and isinstance(task, str)
                            and _DIGEST.fullmatch(task)
                        ):
                            unclassified += 1
                            continue
                        try:
                            occurred_at = datetime.fromisoformat(occurred)
                            if occurred_at.utcoffset() is None:
                                raise ValueError
                            occurred_at = occurred_at.astimezone(timezone.utc)
                        except (TypeError, ValueError, OverflowError):
                            unclassified += 1
                            continue
                        if occurred_at < cutoff:
                            targets.append((event_id,))
                        else:
                            retained += 1
                    deleted = 0
                    if cleanup and targets:
                        deleted = connection.executemany(
                            """DELETE FROM m13_beta_validation_events
                               WHERE event_id = ?""",
                            targets,
                        ).rowcount
                        if deleted != len(targets):
                            raise BetaValidationMaintenanceError(
                                "BETA_VALIDATION_RETENTION_COUNT_MISMATCH"
                            )
                    connection.commit()
                except Exception:
                    connection.rollback()
                    raise
        except BetaValidationMaintenanceError:
            raise
        except sqlite3.Error:
            raise BetaValidationMaintenanceError(
                "BETA_VALIDATION_STORE_UNAVAILABLE"
            ) from None
        return BetaValidationRetentionReport(
            evaluated_at=evaluated_at,
            cutoff_at=cutoff,
            total_events=len(rows),
            retained_events=retained,
            expired_events=len(targets),
            unclassified_events=unclassified,
            deleted_events=deleted,
        )
