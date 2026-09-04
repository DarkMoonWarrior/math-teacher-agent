from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal


DeletionObjectKind = Literal[
    "library_item",
    "question_capture",
    "personal_question",
    "exam_paper",
    "lesson_plan",
]


@dataclass(frozen=True)
class DeletionTombstone:
    object_kind: DeletionObjectKind
    object_id: str
    owner_id: str
    deleted_at: str


class OwnerDeletionLedger:
    """Small durable boundary for owner-confirmed deletion tombstones.

    This database is intentionally outside the backed-up owner stores. Recovery
    consumers use it to prevent an older snapshot from reviving deleted objects.
    """

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path.resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS owner_deletion_tombstones (
                       object_kind TEXT NOT NULL,
                       object_id TEXT NOT NULL,
                       owner_id TEXT NOT NULL,
                       deleted_at TEXT NOT NULL,
                       PRIMARY KEY (object_kind, object_id, owner_id)
                   )"""
            )

    def record(
        self,
        *,
        object_kind: DeletionObjectKind,
        object_id: str,
        owner_id: str,
    ) -> DeletionTombstone:
        if not object_id or not owner_id:
            raise ValueError("DELETION_TOMBSTONE_INVALID")
        deleted_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO owner_deletion_tombstones
                       (object_kind, object_id, owner_id, deleted_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(object_kind, object_id, owner_id)
                   DO UPDATE SET deleted_at = excluded.deleted_at""",
                (object_kind, object_id, owner_id, deleted_at),
            )
        return DeletionTombstone(object_kind, object_id, owner_id, deleted_at)

    def list(self) -> tuple[DeletionTombstone, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT object_kind, object_id, owner_id, deleted_at
                   FROM owner_deletion_tombstones
                   ORDER BY deleted_at, object_kind, object_id"""
            ).fetchall()
        return tuple(DeletionTombstone(**dict(row)) for row in rows)

    def remove(self, tombstone: DeletionTombstone) -> None:
        """Roll back only the exact intent record created by the current operation."""

        with self._connect() as connection:
            connection.execute(
                """DELETE FROM owner_deletion_tombstones
                   WHERE object_kind = ? AND object_id = ? AND owner_id = ? AND deleted_at = ?""",
                (
                    tombstone.object_kind,
                    tombstone.object_id,
                    tombstone.owner_id,
                    tombstone.deleted_at,
                ),
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection
