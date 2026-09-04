from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

from pydantic import ValidationError

from app.modules.lesson_plans.drafting import (
    LessonDrafting,
    LessonDraftingConflict,
    LessonDraftingError,
    ensure_lesson_high_school_scope,
)

if TYPE_CHECKING:
    from app.modules.lesson_exports import RenderedLessonPlan, SavedLessonPlanDocumentRenderer
from app.modules.lesson_plans.editing import (
    LessonBlockEditingConflict,
    ensure_lesson_source_facts_unchanged,
)
from app.modules.lesson_plans.schemas import (
    LessonDraftCommand,
    LessonEditableDraft,
    LessonSavedVersion,
    LessonVersionHistoryItem,
    LessonVersionHistoryList,
    LessonVersionLifecycleCommand,
    LessonVersionSaveCommand,
)


class LessonVersioningError(ValueError):
    pass


class LessonVersioningConflict(LessonVersioningError):
    pass


class LessonSavedExportingError(ValueError):
    pass


class LessonVersioning:
    """Owns immutable lesson versions, owner history and recoverable lifecycle state."""

    def __init__(self, *, database_path: Path, drafting: LessonDrafting) -> None:
        self.database_path = database_path
        self.drafting = drafting
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def save(self, command: LessonVersionSaveCommand, *, owner_id: str) -> LessonSavedVersion:
        if command.lesson_plan_id:
            # Reject foreign IDs before source validation/building. The transaction
            # below rechecks ownership and lifecycle before committing a version.
            self.get(command.lesson_plan_id, owner_id=owner_id)
        submitted = command.draft
        self._validate_current_sources(submitted, owner_id=owner_id)
        try:
            validated = LessonEditableDraft.model_validate(submitted.model_dump(mode="python"))
            ensure_lesson_high_school_scope(validated)
        except (ValidationError, LessonDraftingError) as exc:
            raise LessonVersioningError("教案未通过结构、课时或高中范围检查，不能保存。") from exc

        now = datetime.now(timezone.utc).isoformat()
        fingerprint = self._fingerprint(validated)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if command.lesson_plan_id:
                row = connection.execute(
                    "SELECT owner_id, current_version, lifecycle_state, created_at FROM m10_lesson_plans WHERE lesson_plan_id = ?",
                    (command.lesson_plan_id,),
                ).fetchone()
                if row is None or row["owner_id"] != owner_id:
                    raise KeyError(command.lesson_plan_id)
                if row["lifecycle_state"] != "active":
                    raise LessonVersioningConflict("回收站中的教案不能建立新版本，请先恢复。")
                lesson_plan_id = command.lesson_plan_id
                version = int(row["current_version"]) + 1
                created_at = row["created_at"]
            else:
                lesson_plan_id = str(uuid4())
                version = 1
                created_at = now

            saved = LessonSavedVersion(
                lesson_plan_id=lesson_plan_id,
                version=version,
                title=validated.title,
                draft_fingerprint=fingerprint,
                draft=validated,
                created_at=created_at,
                saved_at=now,
            )
            raw = saved.model_dump_json()
            if version == 1:
                connection.execute(
                    """INSERT INTO m10_lesson_plans
                    (lesson_plan_id, owner_id, title, current_version, lifecycle_state, trashed_at, created_at, updated_at)
                    VALUES (?, ?, ?, ?, 'active', NULL, ?, ?)""",
                    (lesson_plan_id, owner_id, validated.title, version, created_at, now),
                )
            else:
                connection.execute(
                    """UPDATE m10_lesson_plans
                    SET title = ?, current_version = ?, updated_at = ?
                    WHERE lesson_plan_id = ? AND owner_id = ?""",
                    (validated.title, version, now, lesson_plan_id, owner_id),
                )
            connection.execute(
                """INSERT INTO m10_lesson_versions
                (lesson_plan_id, version, owner_id, draft_fingerprint, raw_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (lesson_plan_id, version, owner_id, fingerprint, raw, now),
            )
        return saved

    def list(
        self,
        *,
        owner_id: str,
        lifecycle_state: str = "active",
        limit: int = 30,
    ) -> LessonVersionHistoryList:
        if lifecycle_state not in {"active", "trashed"}:
            raise LessonVersioningError("不支持的教案生命周期状态。")
        with self._connect() as connection:
            total = connection.execute(
                "SELECT COUNT(*) FROM m10_lesson_plans WHERE owner_id = ? AND lifecycle_state = ?",
                (owner_id, lifecycle_state),
            ).fetchone()[0]
            rows = connection.execute(
                """SELECT p.lesson_plan_id, p.title, p.current_version, p.updated_at,
                          p.lifecycle_state, p.trashed_at, v.raw_json
                   FROM m10_lesson_plans p
                   JOIN m10_lesson_versions v
                     ON v.lesson_plan_id = p.lesson_plan_id AND v.version = p.current_version
                   WHERE p.owner_id = ? AND p.lifecycle_state = ?
                   ORDER BY p.updated_at DESC LIMIT ?""",
                (owner_id, lifecycle_state, limit),
            ).fetchall()
        return LessonVersionHistoryList(
            items=[self._history_item(row) for row in rows],
            total=int(total),
        )

    def get(
        self,
        lesson_plan_id: str,
        *,
        owner_id: str,
        version: int | None = None,
    ) -> LessonSavedVersion:
        with self._connect() as connection:
            plan = connection.execute(
                "SELECT owner_id, current_version, lifecycle_state FROM m10_lesson_plans WHERE lesson_plan_id = ?",
                (lesson_plan_id,),
            ).fetchone()
            if plan is None or plan["owner_id"] != owner_id:
                raise KeyError(lesson_plan_id)
            target_version = version or int(plan["current_version"])
            row = connection.execute(
                """SELECT raw_json FROM m10_lesson_versions
                   WHERE lesson_plan_id = ? AND version = ? AND owner_id = ?""",
                (lesson_plan_id, target_version, owner_id),
            ).fetchone()
        if row is None:
            raise KeyError((lesson_plan_id, target_version))
        saved = LessonSavedVersion.model_validate_json(row["raw_json"])
        return saved.model_copy(update={"lifecycle_state": plan["lifecycle_state"]})

    def change_lifecycle(
        self,
        lesson_plan_id: str,
        command: LessonVersionLifecycleCommand,
        *,
        owner_id: str,
    ) -> LessonVersionHistoryItem:
        target = "trashed" if command.action == "trash" else "active"
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT owner_id FROM m10_lesson_plans WHERE lesson_plan_id = ?",
                (lesson_plan_id,),
            ).fetchone()
            if row is None or row["owner_id"] != owner_id:
                raise KeyError(lesson_plan_id)
            connection.execute(
                """UPDATE m10_lesson_plans
                   SET lifecycle_state = ?, trashed_at = ?, updated_at = ?
                   WHERE lesson_plan_id = ? AND owner_id = ?""",
                (target, now if target == "trashed" else None, now, lesson_plan_id, owner_id),
            )
            updated = connection.execute(
                """SELECT p.lesson_plan_id, p.title, p.current_version, p.updated_at,
                          p.lifecycle_state, p.trashed_at, v.raw_json
                   FROM m10_lesson_plans p JOIN m10_lesson_versions v
                     ON v.lesson_plan_id = p.lesson_plan_id AND v.version = p.current_version
                   WHERE p.lesson_plan_id = ? AND p.owner_id = ?""",
                (lesson_plan_id, owner_id),
            ).fetchone()
        return self._history_item(updated)

    def permanently_delete(
        self,
        lesson_plan_id: str,
        *,
        owner_id: str,
        expected_updated_at: str,
    ) -> None:
        """Delete one trashed lesson and its versions, preserving source snapshots."""

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT lifecycle_state, updated_at FROM m10_lesson_plans
                   WHERE lesson_plan_id = ? AND owner_id = ?""",
                (lesson_plan_id, owner_id),
            ).fetchone()
            if row is None:
                raise KeyError(lesson_plan_id)
            if row["lifecycle_state"] != "trashed":
                raise LessonVersioningConflict("教案必须先移入回收站")
            if row["updated_at"] != expected_updated_at:
                raise LessonVersioningConflict("教案已发生变化，请刷新后重试")
            connection.execute(
                "DELETE FROM m10_lesson_versions WHERE lesson_plan_id = ? AND owner_id = ?",
                (lesson_plan_id, owner_id),
            )
            cursor = connection.execute(
                "DELETE FROM m10_lesson_plans WHERE lesson_plan_id = ? AND owner_id = ?",
                (lesson_plan_id, owner_id),
            )
            if cursor.rowcount != 1:  # pragma: no cover - transaction safety
                raise LessonVersioningConflict("教案活动存储不完整，已取消永久删除")

    def _validate_current_sources(self, submitted: LessonEditableDraft, *, owner_id: str) -> None:
        try:
            current = self.drafting.build(
                LessonDraftCommand(source_draft=submitted.source_draft),
                owner_id=owner_id,
            )
            ensure_lesson_source_facts_unchanged(submitted, current)
        except LessonBlockEditingConflict as exc:
            raise LessonVersioningConflict(str(exc)) from exc
        except LessonDraftingConflict as exc:
            raise LessonVersioningConflict(str(exc)) from exc
        except LessonDraftingError as exc:
            raise LessonVersioningError(str(exc)) from exc

    @staticmethod
    def _fingerprint(draft: LessonEditableDraft) -> str:
        raw = json.dumps(
            draft.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _history_item(row: sqlite3.Row) -> LessonVersionHistoryItem:
        saved = LessonSavedVersion.model_validate_json(row["raw_json"])
        return LessonVersionHistoryItem(
            lesson_plan_id=row["lesson_plan_id"],
            title=row["title"],
            version=int(row["current_version"]),
            duration_minutes=saved.draft.source_draft.blueprint.duration_minutes,
            lesson_type=saved.draft.source_draft.blueprint.lesson_type,
            updated_at=row["updated_at"],
            lifecycle_state=row["lifecycle_state"],
            trashed_at=row["trashed_at"],
        )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS m10_lesson_plans (
                    lesson_plan_id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    current_version INTEGER NOT NULL,
                    lifecycle_state TEXT NOT NULL DEFAULT 'active',
                    trashed_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS m10_lesson_versions (
                    lesson_plan_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    owner_id TEXT NOT NULL,
                    draft_fingerprint TEXT NOT NULL,
                    raw_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (lesson_plan_id, version)
                )"""
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS ix_m10_lesson_owner_state ON m10_lesson_plans(owner_id, lifecycle_state, updated_at)"
            )


class LessonSavedExporting:
    """Export one exact owner-scoped immutable lesson version."""

    def __init__(
        self,
        *,
        versioning: LessonVersioning,
        renderer: "SavedLessonPlanDocumentRenderer",
    ) -> None:
        self.versioning = versioning
        self.renderer = renderer

    def export(
        self,
        *,
        lesson_plan_id: str,
        version: int,
        owner_id: str,
        export_format: Literal["docx", "pdf"],
    ) -> "RenderedLessonPlan":
        try:
            saved = self.versioning.get(
                lesson_plan_id,
                owner_id=owner_id,
                version=version,
            )
        except KeyError as exc:
            raise LessonSavedExportingError(
                "教案版本不存在或不属于当前教师。"
            ) from exc
        if saved.version != version or saved.lesson_plan_id != lesson_plan_id:
            raise LessonSavedExportingError("教案版本快照不一致，已停止导出。")
        if saved.draft_fingerprint != LessonVersioning._fingerprint(saved.draft):
            raise LessonSavedExportingError("教案版本内容校验失败，已停止导出。")
        return self.renderer.render_saved(saved, export_format)
