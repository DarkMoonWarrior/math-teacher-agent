from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.modules.personal_question_library.schemas import (
    PersonalAuthoringDraftList,
    PersonalAuthoringDraftView,
    PersonalAuthoringHistoryDeletionReceipt,
    PersonalAuthoringRevisionList,
    PersonalAuthoringRevisionView,
    PersonalCategoryCreate,
    PersonalCategoryList,
    PersonalCategoryUpdate,
    PersonalCategoryView,
    PersonalCollectionCreate,
    PersonalCollectionList,
    PersonalCollectionUpdate,
    PersonalCollectionView,
    PersonalQuestionCopy,
    PersonalQuestionDeletionReceipt,
    PersonalQuestionExportArtifact,
    PersonalQuestionList,
    PersonalQuestionPermanentDelete,
    PersonalQuestionRevisionCreate,
    PersonalQuestionSave,
    PersonalQuestionUpdate,
    PersonalQuestionVersionCommand,
    PersonalQuestionView,
    SavedPersonalQuestionDraft,
)
from app.modules.question_authoring import GeneratedQuestionDraft


class PersonalQuestionLibraryError(ValueError):
    pass


class PersonalQuestionLibraryConflict(PersonalQuestionLibraryError):
    pass


class PersonalQuestionLibrary:
    """Owner-only collections and categories for assisted-authored questions.

    SQLite and owner isolation stay behind this interface. This module is
    deliberately separate from QuestionBank and has no publish/share path.
    """

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path.resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def create_collection(
        self,
        command: PersonalCollectionCreate,
        *,
        owner_id: str,
    ) -> PersonalCollectionView:
        name, name_key = self._normalized_name(command.name, kind="个人题库")
        now = self._now()
        collection_id = f"pql_{uuid4().hex[:16]}"
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO personal_question_collections (
                        collection_id, owner_id, name, name_key, description,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        collection_id,
                        owner_id,
                        name,
                        name_key,
                        command.description.strip(),
                        now,
                        now,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise PersonalQuestionLibraryConflict("同名个人题库已经存在") from exc
        return self.get_collection(collection_id, owner_id=owner_id)

    def list_collections(self, *, owner_id: str) -> PersonalCollectionList:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT collections.*,
                    (
                        SELECT COUNT(*) FROM personal_question_categories AS categories
                        WHERE categories.collection_id = collections.collection_id
                          AND categories.owner_id = collections.owner_id
                    ) AS category_count,
                    (
                        SELECT COUNT(*) FROM personal_questions AS questions
                        WHERE questions.collection_id = collections.collection_id
                          AND questions.owner_id = collections.owner_id
                          AND questions.lifecycle_state = 'active'
                    ) AS question_count
                FROM personal_question_collections AS collections
                WHERE collections.owner_id = ?
                ORDER BY collections.updated_at DESC, collections.collection_id ASC
                """,
                (owner_id,),
            ).fetchall()
        return PersonalCollectionList(
            items=[self._collection_view(row) for row in rows],
            total=len(rows),
        )

    def get_collection(
        self,
        collection_id: str,
        *,
        owner_id: str,
    ) -> PersonalCollectionView:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT collections.*,
                    (
                        SELECT COUNT(*) FROM personal_question_categories AS categories
                        WHERE categories.collection_id = collections.collection_id
                          AND categories.owner_id = collections.owner_id
                    ) AS category_count,
                    (
                        SELECT COUNT(*) FROM personal_questions AS questions
                        WHERE questions.collection_id = collections.collection_id
                          AND questions.owner_id = collections.owner_id
                          AND questions.lifecycle_state = 'active'
                    ) AS question_count
                FROM personal_question_collections AS collections
                WHERE collections.collection_id = ? AND collections.owner_id = ?
                """,
                (collection_id, owner_id),
            ).fetchone()
        if row is None:
            raise KeyError(collection_id)
        return self._collection_view(row)

    def update_collection(
        self,
        collection_id: str,
        command: PersonalCollectionUpdate,
        *,
        owner_id: str,
    ) -> PersonalCollectionView:
        current = self.get_collection(collection_id, owner_id=owner_id)
        name, name_key = self._normalized_name(
            command.name if command.name is not None else current.name,
            kind="个人题库",
        )
        description = (
            command.description.strip()
            if command.description is not None
            else current.description
        )
        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    """
                    UPDATE personal_question_collections
                    SET name = ?, name_key = ?, description = ?, updated_at = ?
                    WHERE collection_id = ? AND owner_id = ?
                    """,
                    (
                        name,
                        name_key,
                        description,
                        self._now(),
                        collection_id,
                        owner_id,
                    ),
                )
                if cursor.rowcount == 0:
                    raise KeyError(collection_id)
        except sqlite3.IntegrityError as exc:
            raise PersonalQuestionLibraryConflict("同名个人题库已经存在") from exc
        return self.get_collection(collection_id, owner_id=owner_id)

    def create_category(
        self,
        collection_id: str,
        command: PersonalCategoryCreate,
        *,
        owner_id: str,
    ) -> PersonalCategoryView:
        self.get_collection(collection_id, owner_id=owner_id)
        name, name_key = self._normalized_name(command.name, kind="个人分类")
        category_id = f"pqc_{uuid4().hex[:16]}"
        now = self._now()
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO personal_question_categories (
                        category_id, collection_id, owner_id, name, name_key,
                        description, sort_order, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        category_id,
                        collection_id,
                        owner_id,
                        name,
                        name_key,
                        command.description.strip(),
                        command.sort_order,
                        now,
                        now,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise PersonalQuestionLibraryConflict("当前题库中已存在同名分类") from exc
        return self.get_category(category_id, owner_id=owner_id)

    def list_categories(
        self,
        collection_id: str,
        *,
        owner_id: str,
    ) -> PersonalCategoryList:
        self.get_collection(collection_id, owner_id=owner_id)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT categories.*,
                    (
                        SELECT COUNT(*) FROM personal_questions AS questions
                        WHERE questions.category_id = categories.category_id
                          AND questions.owner_id = categories.owner_id
                          AND questions.lifecycle_state = 'active'
                    ) AS question_count
                FROM personal_question_categories AS categories
                WHERE categories.collection_id = ? AND categories.owner_id = ?
                ORDER BY categories.sort_order ASC, categories.updated_at DESC,
                         categories.category_id ASC
                """,
                (collection_id, owner_id),
            ).fetchall()
        return PersonalCategoryList(
            collection_id=collection_id,
            items=[self._category_view(row) for row in rows],
            total=len(rows),
        )

    def get_category(
        self,
        category_id: str,
        *,
        owner_id: str,
    ) -> PersonalCategoryView:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT categories.*,
                    (
                        SELECT COUNT(*) FROM personal_questions AS questions
                        WHERE questions.category_id = categories.category_id
                          AND questions.owner_id = categories.owner_id
                          AND questions.lifecycle_state = 'active'
                    ) AS question_count
                FROM personal_question_categories AS categories
                WHERE categories.category_id = ? AND categories.owner_id = ?
                """,
                (category_id, owner_id),
            ).fetchone()
        if row is None:
            raise KeyError(category_id)
        return self._category_view(row)

    def update_category(
        self,
        category_id: str,
        command: PersonalCategoryUpdate,
        *,
        owner_id: str,
    ) -> PersonalCategoryView:
        current = self.get_category(category_id, owner_id=owner_id)
        name, name_key = self._normalized_name(
            command.name if command.name is not None else current.name,
            kind="个人分类",
        )
        description = (
            command.description.strip()
            if command.description is not None
            else current.description
        )
        sort_order = command.sort_order if command.sort_order is not None else current.sort_order
        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    """
                    UPDATE personal_question_categories
                    SET name = ?, name_key = ?, description = ?, sort_order = ?, updated_at = ?
                    WHERE category_id = ? AND owner_id = ?
                    """,
                    (
                        name,
                        name_key,
                        description,
                        sort_order,
                        self._now(),
                        category_id,
                        owner_id,
                    ),
                )
                if cursor.rowcount == 0:
                    raise KeyError(category_id)
        except sqlite3.IntegrityError as exc:
            raise PersonalQuestionLibraryConflict("当前题库中已存在同名分类") from exc
        return self.get_category(category_id, owner_id=owner_id)

    def stage_generated_draft(
        self,
        draft: GeneratedQuestionDraft,
        *,
        owner_id: str,
    ) -> PersonalAuthoringDraftView:
        """Record a generated draft in the owner's unsaved authoring workspace."""

        now = self._now()
        payload = draft.model_dump_json()
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO personal_authoring_drafts (
                        draft_id, owner_id, current_revision, saved_question_id,
                        created_at, updated_at
                    ) VALUES (?, ?, 1, NULL, ?, ?)
                    """,
                    (draft.draft_id, owner_id, now, now),
                )
                connection.execute(
                    """
                    INSERT INTO personal_authoring_revisions (
                        draft_id, owner_id, revision_number, revision_source,
                        edit_summary, draft_json, created_at
                    ) VALUES (?, ?, 1, 'ai_generated', ?, ?, ?)
                    """,
                    (
                        draft.draft_id,
                        owner_id,
                        "AI 生成的初始草稿",
                        payload,
                        now,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise PersonalQuestionLibraryConflict("命题草稿已经存在") from exc
        return self.get_authoring_draft(draft.draft_id, owner_id=owner_id)

    def get_authoring_draft(
        self,
        draft_id: str,
        *,
        owner_id: str,
    ) -> PersonalAuthoringDraftView:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT drafts.*, revisions.revision_source,
                       revisions.edit_summary, revisions.draft_json,
                       revisions.created_at AS revision_created_at
                FROM personal_authoring_drafts AS drafts
                JOIN personal_authoring_revisions AS revisions
                  ON revisions.draft_id = drafts.draft_id
                 AND revisions.owner_id = drafts.owner_id
                 AND revisions.revision_number = drafts.current_revision
                WHERE drafts.draft_id = ? AND drafts.owner_id = ?
                """,
                (draft_id, owner_id),
            ).fetchone()
        if row is None:
            raise KeyError(draft_id)
        return self._authoring_draft_view(row)

    def list_authoring_drafts(
        self, *, owner_id: str, limit: int = 50, offset: int = 0
    ) -> PersonalAuthoringDraftList:
        with self._connect() as connection:
            total = connection.execute(
                "SELECT COUNT(*) FROM personal_authoring_drafts WHERE owner_id = ? AND history_visible = 1",
                (owner_id,),
            ).fetchone()[0]
            rows = connection.execute(
                """
                SELECT drafts.*, revisions.revision_source,
                       revisions.edit_summary, revisions.draft_json,
                       revisions.created_at AS revision_created_at
                FROM personal_authoring_drafts AS drafts
                JOIN personal_authoring_revisions AS revisions
                  ON revisions.draft_id = drafts.draft_id
                 AND revisions.owner_id = drafts.owner_id
                 AND revisions.revision_number = drafts.current_revision
                WHERE drafts.owner_id = ? AND drafts.history_visible = 1
                ORDER BY drafts.updated_at DESC, drafts.draft_id DESC
                LIMIT ? OFFSET ?
                """,
                (owner_id, limit, offset),
            ).fetchall()
        return PersonalAuthoringDraftList(
            items=[self._authoring_draft_view(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    def delete_authoring_history(
        self, draft_id: str, *, owner_id: str
    ) -> PersonalAuthoringHistoryDeletionReceipt:
        """Remove a history entry; an already-saved private question stays intact."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT saved_question_id FROM personal_authoring_drafts WHERE draft_id = ? AND owner_id = ? AND history_visible = 1",
                (draft_id, owner_id),
            ).fetchone()
            if row is None:
                raise KeyError(draft_id)
            preserved = row["saved_question_id"] is not None
            if preserved:
                connection.execute(
                    "UPDATE personal_authoring_drafts SET history_visible = 0, updated_at = ? WHERE draft_id = ? AND owner_id = ?",
                    (self._now(), draft_id, owner_id),
                )
            else:
                connection.execute(
                    "DELETE FROM personal_authoring_revisions WHERE draft_id = ? AND owner_id = ?",
                    (draft_id, owner_id),
                )
                connection.execute(
                    "DELETE FROM personal_authoring_drafts WHERE draft_id = ? AND owner_id = ?",
                    (draft_id, owner_id),
                )
        return PersonalAuthoringHistoryDeletionReceipt(
            draft_id=draft_id, saved_question_preserved=preserved
        )

    def list_authoring_revisions(
        self,
        draft_id: str,
        *,
        owner_id: str,
    ) -> PersonalAuthoringRevisionList:
        current = self.get_authoring_draft(draft_id, owner_id=owner_id)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM personal_authoring_revisions
                WHERE draft_id = ? AND owner_id = ?
                ORDER BY revision_number DESC
                """,
                (draft_id, owner_id),
            ).fetchall()
        items = [self._revision_view(row) for row in rows]
        return PersonalAuthoringRevisionList(
            draft_id=draft_id,
            current_revision=current.current_revision,
            items=items,
            total=len(items),
        )

    def append_teacher_revision(
        self,
        revised: GeneratedQuestionDraft,
        *,
        owner_id: str,
        expected_revision: int,
        edit_summary: str,
    ) -> PersonalAuthoringDraftView:
        return self._append_authoring_revision(
            revised,
            owner_id=owner_id,
            expected_revision=expected_revision,
            edit_summary=edit_summary,
            revision_source="teacher_edit",
        )

    def append_ai_revision(
        self,
        revised: GeneratedQuestionDraft,
        *,
        owner_id: str,
        expected_revision: int,
        edit_summary: str,
    ) -> PersonalAuthoringDraftView:
        return self._append_authoring_revision(
            revised,
            owner_id=owner_id,
            expected_revision=expected_revision,
            edit_summary=edit_summary,
            revision_source="ai_generated",
        )

    def _append_authoring_revision(
        self,
        revised: GeneratedQuestionDraft,
        *,
        owner_id: str,
        expected_revision: int,
        edit_summary: str,
        revision_source: str,
    ) -> PersonalAuthoringDraftView:
        next_revision = expected_revision + 1
        now = self._now()
        summary = re.sub(r"\s+", " ", edit_summary).strip()
        if not summary:
            raise PersonalQuestionLibraryError("revision 修改说明不能为空")
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE personal_authoring_drafts
                SET current_revision = ?, updated_at = ?
                WHERE draft_id = ? AND owner_id = ?
                  AND current_revision = ? AND saved_question_id IS NULL
                """,
                (
                    next_revision,
                    now,
                    revised.draft_id,
                    owner_id,
                    expected_revision,
                ),
            )
            if cursor.rowcount == 0:
                existing = connection.execute(
                    """
                    SELECT current_revision, saved_question_id
                    FROM personal_authoring_drafts
                    WHERE draft_id = ? AND owner_id = ?
                    """,
                    (revised.draft_id, owner_id),
                ).fetchone()
                if existing is None:
                    raise KeyError(revised.draft_id)
                if existing["saved_question_id"] is not None:
                    raise PersonalQuestionLibraryConflict(
                        "该草稿已经保存；已保存题目的继续编辑将在个人管理切片开放"
                    )
                raise PersonalQuestionLibraryConflict(
                    f"草稿版本已更新，当前版本为 {existing['current_revision']}"
                )
            connection.execute(
                """
                INSERT INTO personal_authoring_revisions (
                    draft_id, owner_id, revision_number, revision_source,
                    edit_summary, draft_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    revised.draft_id,
                    owner_id,
                    next_revision,
                    revision_source,
                    summary,
                    revised.model_dump_json(),
                    now,
                ),
            )
        return self.get_authoring_draft(revised.draft_id, owner_id=owner_id)

    def save_authoring_draft(
        self,
        draft_id: str,
        command: PersonalQuestionSave,
        *,
        owner_id: str,
    ) -> PersonalQuestionView:
        name, _ = self._normalized_name(command.name, kind="私题")
        question_id = f"pqq_{uuid4().hex[:16]}"
        now = self._now()
        with self._connect() as connection:
            category = connection.execute(
                """
                SELECT category_id FROM personal_question_categories
                WHERE category_id = ? AND collection_id = ? AND owner_id = ?
                """,
                (command.category_id, command.collection_id, owner_id),
            ).fetchone()
            if category is None:
                raise KeyError(command.category_id)
            draft_row = connection.execute(
                """
                SELECT drafts.current_revision, drafts.saved_question_id,
                       revisions.draft_json
                FROM personal_authoring_drafts AS drafts
                JOIN personal_authoring_revisions AS revisions
                  ON revisions.draft_id = drafts.draft_id
                 AND revisions.owner_id = drafts.owner_id
                 AND revisions.revision_number = drafts.current_revision
                WHERE drafts.draft_id = ? AND drafts.owner_id = ?
                """,
                (draft_id, owner_id),
            ).fetchone()
            if draft_row is None:
                raise KeyError(draft_id)
            if draft_row["saved_question_id"] is not None:
                raise PersonalQuestionLibraryConflict("该命题草稿已经保存")
            if draft_row["current_revision"] != command.expected_revision:
                raise PersonalQuestionLibraryConflict(
                    f"草稿版本已更新，当前版本为 {draft_row['current_revision']}"
                )
            cursor = connection.execute(
                """
                UPDATE personal_authoring_drafts
                SET saved_question_id = ?, updated_at = ?
                WHERE draft_id = ? AND owner_id = ?
                  AND current_revision = ? AND saved_question_id IS NULL
                """,
                (
                    question_id,
                    now,
                    draft_id,
                    owner_id,
                    command.expected_revision,
                ),
            )
            if cursor.rowcount != 1:  # pragma: no cover - concurrent writer safety
                raise PersonalQuestionLibraryConflict("草稿版本已更新或已经保存")
            connection.execute(
                """
                INSERT INTO personal_questions (
                    question_id, owner_id, collection_id, category_id, name,
                    source_draft_id, selected_revision, question_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    question_id,
                    owner_id,
                    command.collection_id,
                    command.category_id,
                    name,
                    draft_id,
                    command.expected_revision,
                    draft_row["draft_json"],
                    now,
                    now,
                ),
            )
        return self.get_question(question_id, owner_id=owner_id)

    def get_question(
        self,
        question_id: str,
        *,
        owner_id: str,
    ) -> PersonalQuestionView:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM personal_questions
                WHERE question_id = ? AND owner_id = ?
                """,
                (question_id, owner_id),
            ).fetchone()
        if row is None:
            raise KeyError(question_id)
        return self._question_view(row)

    def list_questions(
        self,
        *,
        owner_id: str,
        query: str = "",
        collection_id: str | None = None,
        category_id: str | None = None,
        lifecycle_state: str = "active",
        limit: int = 50,
        offset: int = 0,
    ) -> PersonalQuestionList:
        if lifecycle_state not in {"active", "trashed"}:
            raise PersonalQuestionLibraryError("不支持的私题 lifecycle")
        if not 1 <= limit <= 200 or offset < 0:
            raise PersonalQuestionLibraryError("私题分页参数无效")
        if collection_id:
            self.get_collection(collection_id, owner_id=owner_id)
        if category_id:
            category = self.get_category(category_id, owner_id=owner_id)
            if collection_id and category.collection_id != collection_id:
                raise PersonalQuestionLibraryError("个人分类不属于所选题库")

        clauses = ["owner_id = ?", "lifecycle_state = ?"]
        params: list[object] = [owner_id, lifecycle_state]
        normalized_query = re.sub(r"\s+", " ", query).strip()
        if collection_id:
            clauses.append("collection_id = ?")
            params.append(collection_id)
        if category_id:
            clauses.append("category_id = ?")
            params.append(category_id)
        if normalized_query:
            escaped = (
                normalized_query.replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            pattern = f"%{escaped}%"
            clauses.append(
                "(name LIKE ? ESCAPE '\\' OR tags_json LIKE ? ESCAPE '\\' "
                "OR question_json LIKE ? ESCAPE '\\')"
            )
            params.extend([pattern, pattern, pattern])
        where = " AND ".join(clauses)
        with self._connect() as connection:
            total = connection.execute(
                f"SELECT COUNT(*) FROM personal_questions WHERE {where}",
                params,
            ).fetchone()[0]
            rows = connection.execute(
                f"""
                SELECT * FROM personal_questions
                WHERE {where}
                ORDER BY sort_order ASC, updated_at DESC, question_id ASC
                LIMIT ? OFFSET ?
                """,
                [*params, limit, offset],
            ).fetchall()
        return PersonalQuestionList(
            query=normalized_query,
            lifecycle_state=lifecycle_state,
            items=[self._question_view(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    def append_saved_question_revision(
        self,
        question_id: str,
        revised: GeneratedQuestionDraft,
        command: PersonalQuestionRevisionCreate,
        *,
        owner_id: str,
    ) -> PersonalQuestionView:
        summary = re.sub(r"\s+", " ", command.edit_summary).strip()
        if not summary:
            raise PersonalQuestionLibraryError("revision 修改说明不能为空")
        next_revision = command.expected_revision + 1
        now = self._now()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT source_draft_id, selected_revision, lifecycle_state, updated_at
                FROM personal_questions
                WHERE question_id = ? AND owner_id = ?
                """,
                (question_id, owner_id),
            ).fetchone()
            if row is None:
                raise KeyError(question_id)
            if row["lifecycle_state"] != "active":
                raise PersonalQuestionLibraryConflict("请先从回收站恢复私题再修改")
            if (
                row["selected_revision"] != command.expected_revision
                or row["updated_at"] != command.expected_updated_at
            ):
                raise PersonalQuestionLibraryConflict("私题版本已变化，请刷新后重试")
            if revised.draft_id != row["source_draft_id"]:
                raise PersonalQuestionLibraryError("修订草稿与个人题目来源不一致")

            draft_cursor = connection.execute(
                """
                UPDATE personal_authoring_drafts
                SET current_revision = ?, updated_at = ?
                WHERE draft_id = ? AND owner_id = ?
                  AND current_revision = ? AND saved_question_id = ?
                """,
                (
                    next_revision,
                    now,
                    revised.draft_id,
                    owner_id,
                    command.expected_revision,
                    question_id,
                ),
            )
            if draft_cursor.rowcount != 1:
                raise PersonalQuestionLibraryConflict("命题 revision 已变化，请刷新后重试")
            connection.execute(
                """
                INSERT INTO personal_authoring_revisions (
                    draft_id, owner_id, revision_number, revision_source,
                    edit_summary, draft_json, created_at
                ) VALUES (?, ?, ?, 'teacher_edit', ?, ?, ?)
                """,
                (
                    revised.draft_id,
                    owner_id,
                    next_revision,
                    summary,
                    revised.model_dump_json(),
                    now,
                ),
            )
            question_cursor = connection.execute(
                """
                UPDATE personal_questions
                SET selected_revision = ?, question_json = ?, updated_at = ?
                WHERE question_id = ? AND owner_id = ?
                  AND selected_revision = ? AND updated_at = ?
                  AND lifecycle_state = 'active'
                """,
                (
                    next_revision,
                    revised.model_dump_json(),
                    now,
                    question_id,
                    owner_id,
                    command.expected_revision,
                    command.expected_updated_at,
                ),
            )
            if question_cursor.rowcount != 1:  # pragma: no cover - transaction safety
                raise PersonalQuestionLibraryConflict("私题版本已变化，请刷新后重试")
        return self.get_question(question_id, owner_id=owner_id)

    def update_question(
        self,
        question_id: str,
        command: PersonalQuestionUpdate,
        *,
        owner_id: str,
    ) -> PersonalQuestionView:
        current = self.get_question(question_id, owner_id=owner_id)
        if current.lifecycle_state != "active":
            raise PersonalQuestionLibraryConflict("请先从回收站恢复私题再修改")
        if current.updated_at != command.expected_updated_at:
            raise PersonalQuestionLibraryConflict("私题版本已变化，请刷新后重试")
        collection_id = command.collection_id or current.collection_id
        category_id = command.category_id or current.category_id
        name = current.name
        if command.name is not None:
            name, _ = self._normalized_name(command.name, kind="私题")
        tags = current.tags if command.tags is None else self._normalized_tags(command.tags)
        sort_order = current.sort_order if command.sort_order is None else command.sort_order
        now = self._now()
        with self._connect() as connection:
            self._require_owned_category(
                connection,
                collection_id=collection_id,
                category_id=category_id,
                owner_id=owner_id,
            )
            cursor = connection.execute(
                """
                UPDATE personal_questions
                SET collection_id = ?, category_id = ?, name = ?, tags_json = ?,
                    sort_order = ?, updated_at = ?
                WHERE question_id = ? AND owner_id = ? AND lifecycle_state = 'active'
                  AND updated_at = ?
                """,
                (
                    collection_id,
                    category_id,
                    name,
                    json.dumps(tags, ensure_ascii=False, separators=(",", ":")),
                    sort_order,
                    now,
                    question_id,
                    owner_id,
                    command.expected_updated_at,
                ),
            )
            if cursor.rowcount != 1:
                raise PersonalQuestionLibraryConflict("私题状态已变化，请刷新后重试")
        return self.get_question(question_id, owner_id=owner_id)

    def copy_question(
        self,
        question_id: str,
        command: PersonalQuestionCopy,
        *,
        owner_id: str,
    ) -> PersonalQuestionView:
        source = self.get_question(question_id, owner_id=owner_id)
        if source.lifecycle_state != "active":
            raise PersonalQuestionLibraryConflict("回收站中的私题不能复制")
        name = command.name or f"{source.name}（副本）"
        name, _ = self._normalized_name(name, kind="私题")
        copied_question_id = f"pqq_{uuid4().hex[:16]}"
        copied_draft_id = f"qad_{uuid4().hex[:16]}"
        now = self._now()
        draft_payload = source.question.model_dump(mode="json")
        draft_payload.update(
            {
                "draft_id": copied_draft_id,
                "saved": False,
                "created_at": now,
            }
        )
        copied_draft = GeneratedQuestionDraft.model_validate(draft_payload)
        tags_json = json.dumps(
            source.tags,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        with self._connect() as connection:
            self._require_owned_category(
                connection,
                collection_id=command.collection_id,
                category_id=command.category_id,
                owner_id=owner_id,
            )
            connection.execute(
                """
                INSERT INTO personal_authoring_drafts (
                    draft_id, owner_id, current_revision, saved_question_id,
                    created_at, updated_at
                ) VALUES (?, ?, 1, ?, ?, ?)
                """,
                (
                    copied_draft_id,
                    owner_id,
                    copied_question_id,
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO personal_authoring_revisions (
                    draft_id, owner_id, revision_number, revision_source,
                    edit_summary, draft_json, created_at
                ) VALUES (?, ?, 1, 'teacher_edit', ?, ?, ?)
                """,
                (
                    copied_draft_id,
                    owner_id,
                    f"复制自个人题目 {question_id}",
                    copied_draft.model_dump_json(),
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO personal_questions (
                    question_id, owner_id, collection_id, category_id, name,
                    source_draft_id, selected_revision, question_json,
                    tags_json, sort_order, lifecycle_state, trashed_at,
                    copied_from_question_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, 'active', NULL, ?, ?, ?)
                """,
                (
                    copied_question_id,
                    owner_id,
                    command.collection_id,
                    command.category_id,
                    name,
                    copied_draft_id,
                    copied_draft.model_dump_json(),
                    tags_json,
                    source.sort_order,
                    question_id,
                    now,
                    now,
                ),
            )
        return self.get_question(copied_question_id, owner_id=owner_id)

    def export_question(
        self,
        question_id: str,
        *,
        owner_id: str,
        export_format: str,
    ) -> PersonalQuestionExportArtifact:
        question = self.get_question(question_id, owner_id=owner_id)
        safe_name = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "-", question.name).strip("-")
        safe_name = (safe_name or "personal-question")[:60]
        if export_format == "json":
            return PersonalQuestionExportArtifact(
                filename=f"{safe_name}.json",
                media_type="application/json",
                content=json.dumps(
                    question.model_dump(mode="json"),
                    ensure_ascii=False,
                    indent=2,
                ),
            )
        if export_format == "markdown":
            option_lines = [
                f"- {option.key}. {option.text}" for option in question.question.options
            ]
            step_lines = [
                f"{index}. {step}"
                for index, step in enumerate(question.question.solution_steps, start=1)
            ]
            content = "\n".join(
                [
                    f"# {question.name}",
                    "",
                    "> 仅自己可见 · AI 辅助命制 · 必须由教师复核",
                    "",
                    f"- 教材知识点：{question.question.curriculum.name if question.question.curriculum else '待教师确认'}",
                    f"- 细分知识点：{'、'.join(question.question.knowledge_points) if question.question.knowledge_points else '待教师补充'}",
                    f"- 考查方法：{'、'.join(question.question.assessed_methods) if question.question.assessed_methods else '待教师补充'}",
                    f"- 常见易错点：{'、'.join(question.question.common_mistakes) if question.question.common_mistakes else '待教师补充'}",
                    f"- 标签：{'、'.join(question.tags) if question.tags else '无'}",
                    f"- 可信状态：{question.question.verification.status}",
                    "",
                    "## 题目",
                    "",
                    question.question.stem_plain,
                    "",
                    *option_lines,
                    "",
                    "## 答案",
                    "",
                    question.question.answer_value,
                    "",
                    "## 解析",
                    "",
                    f"方法：{question.question.solution_method}",
                    "",
                    *step_lines,
                    "",
                    f"最终答案：{question.question.final_answer}",
                    "",
                ]
            )
            return PersonalQuestionExportArtifact(
                filename=f"{safe_name}.md",
                media_type="text/markdown",
                content=content,
            )
        raise PersonalQuestionLibraryError("仅支持 json 或 markdown 私题导出")

    def trash_question(
        self,
        question_id: str,
        command: PersonalQuestionVersionCommand,
        *,
        owner_id: str,
    ) -> PersonalQuestionView:
        return self._change_question_lifecycle(
            question_id,
            owner_id=owner_id,
            expected_updated_at=command.expected_updated_at,
            from_state="active",
            to_state="trashed",
        )

    def restore_question(
        self,
        question_id: str,
        command: PersonalQuestionVersionCommand,
        *,
        owner_id: str,
    ) -> PersonalQuestionView:
        return self._change_question_lifecycle(
            question_id,
            owner_id=owner_id,
            expected_updated_at=command.expected_updated_at,
            from_state="trashed",
            to_state="active",
        )

    def permanently_delete_question(
        self,
        question_id: str,
        command: PersonalQuestionPermanentDelete,
        *,
        owner_id: str,
    ) -> PersonalQuestionDeletionReceipt:
        now = self._now()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT source_draft_id, lifecycle_state, updated_at
                FROM personal_questions
                WHERE question_id = ? AND owner_id = ?
                """,
                (question_id, owner_id),
            ).fetchone()
            if row is None:
                raise KeyError(question_id)
            if row["lifecycle_state"] != "trashed":
                raise PersonalQuestionLibraryConflict("永久删除前必须先把私题移入回收站")
            if row["updated_at"] != command.expected_updated_at:
                raise PersonalQuestionLibraryConflict("私题版本已变化，请刷新后重新确认")
            source_draft_id = row["source_draft_id"]
            question_cursor = connection.execute(
                "DELETE FROM personal_questions WHERE question_id = ? AND owner_id = ?",
                (question_id, owner_id),
            )
            revision_cursor = connection.execute(
                """
                DELETE FROM personal_authoring_revisions
                WHERE draft_id = ? AND owner_id = ?
                """,
                (source_draft_id, owner_id),
            )
            draft_cursor = connection.execute(
                """
                DELETE FROM personal_authoring_drafts
                WHERE draft_id = ? AND owner_id = ?
                """,
                (source_draft_id, owner_id),
            )
            if (
                question_cursor.rowcount != 1
                or revision_cursor.rowcount < 1
                or draft_cursor.rowcount != 1
            ):  # pragma: no cover - storage integrity safety
                raise PersonalQuestionLibraryConflict(
                    "私题活动存储不完整，已取消永久删除"
                )
        return PersonalQuestionDeletionReceipt(
            question_id=question_id,
            source_draft_id=source_draft_id,
            deleted_at=now,
        )

    def _change_question_lifecycle(
        self,
        question_id: str,
        *,
        owner_id: str,
        expected_updated_at: str,
        from_state: str,
        to_state: str,
    ) -> PersonalQuestionView:
        now = self._now()
        trashed_at = now if to_state == "trashed" else None
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE personal_questions
                SET lifecycle_state = ?, trashed_at = ?, updated_at = ?
                WHERE question_id = ? AND owner_id = ?
                  AND lifecycle_state = ? AND updated_at = ?
                """,
                (
                    to_state,
                    trashed_at,
                    now,
                    question_id,
                    owner_id,
                    from_state,
                    expected_updated_at,
                ),
            )
            if cursor.rowcount == 0:
                existing = connection.execute(
                    """
                    SELECT lifecycle_state, updated_at FROM personal_questions
                    WHERE question_id = ? AND owner_id = ?
                    """,
                    (question_id, owner_id),
                ).fetchone()
                if existing is None:
                    raise KeyError(question_id)
                raise PersonalQuestionLibraryConflict("私题状态或版本已变化，请刷新后重试")
        return self.get_question(question_id, owner_id=owner_id)

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS personal_question_collections (
                    collection_id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    name_key TEXT NOT NULL,
                    description TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(owner_id, name_key),
                    UNIQUE(collection_id, owner_id)
                );

                CREATE TABLE IF NOT EXISTS personal_question_categories (
                    category_id TEXT PRIMARY KEY,
                    collection_id TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    name_key TEXT NOT NULL,
                    description TEXT NOT NULL,
                    sort_order INTEGER NOT NULL DEFAULT 0 CHECK (sort_order >= 0),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(owner_id, collection_id, name_key),
                    FOREIGN KEY(collection_id, owner_id)
                        REFERENCES personal_question_collections(collection_id, owner_id)
                        ON DELETE RESTRICT
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_personal_categories_identity
                    ON personal_question_categories(category_id, collection_id, owner_id);

                CREATE TABLE IF NOT EXISTS personal_authoring_drafts (
                    draft_id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    current_revision INTEGER NOT NULL CHECK (current_revision >= 1),
                    saved_question_id TEXT,
                    history_visible INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(draft_id, owner_id)
                );

                CREATE TABLE IF NOT EXISTS personal_authoring_revisions (
                    draft_id TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    revision_number INTEGER NOT NULL CHECK (revision_number >= 1),
                    revision_source TEXT NOT NULL
                        CHECK (revision_source IN ('ai_generated', 'teacher_edit')),
                    edit_summary TEXT NOT NULL,
                    draft_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(draft_id, owner_id, revision_number),
                    FOREIGN KEY(draft_id, owner_id)
                        REFERENCES personal_authoring_drafts(draft_id, owner_id)
                        ON DELETE RESTRICT
                );

                CREATE TABLE IF NOT EXISTS personal_questions (
                    question_id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    collection_id TEXT NOT NULL,
                    category_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    source_draft_id TEXT NOT NULL,
                    selected_revision INTEGER NOT NULL CHECK (selected_revision >= 1),
                    question_json TEXT NOT NULL,
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    sort_order INTEGER NOT NULL DEFAULT 0 CHECK (sort_order >= 0),
                    lifecycle_state TEXT NOT NULL DEFAULT 'active'
                        CHECK (lifecycle_state IN ('active', 'trashed')),
                    trashed_at TEXT,
                    copied_from_question_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(question_id, owner_id),
                    UNIQUE(owner_id, source_draft_id),
                    FOREIGN KEY(collection_id, owner_id)
                        REFERENCES personal_question_collections(collection_id, owner_id)
                        ON DELETE RESTRICT,
                    FOREIGN KEY(category_id, collection_id, owner_id)
                        REFERENCES personal_question_categories(
                            category_id, collection_id, owner_id
                        ) ON DELETE RESTRICT,
                    FOREIGN KEY(source_draft_id, owner_id)
                        REFERENCES personal_authoring_drafts(draft_id, owner_id)
                        ON DELETE RESTRICT
                );

                CREATE INDEX IF NOT EXISTS idx_personal_collections_owner
                    ON personal_question_collections(owner_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_personal_categories_owner_collection
                    ON personal_question_categories(owner_id, collection_id, sort_order);
                CREATE INDEX IF NOT EXISTS idx_personal_authoring_drafts_owner
                    ON personal_authoring_drafts(owner_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_personal_authoring_revisions_owner
                    ON personal_authoring_revisions(owner_id, draft_id, revision_number DESC);
                CREATE INDEX IF NOT EXISTS idx_personal_questions_owner_category
                    ON personal_questions(owner_id, collection_id, category_id, updated_at DESC);
                """
            )
            self._ensure_column(
                connection,
                "personal_authoring_drafts",
                "history_visible",
                "INTEGER NOT NULL DEFAULT 1",
            )
            self._ensure_column(
                connection,
                "personal_questions",
                "tags_json",
                "TEXT NOT NULL DEFAULT '[]'",
            )
            self._ensure_column(
                connection,
                "personal_questions",
                "sort_order",
                "INTEGER NOT NULL DEFAULT 0",
            )
            self._ensure_column(
                connection,
                "personal_questions",
                "lifecycle_state",
                "TEXT NOT NULL DEFAULT 'active'",
            )
            self._ensure_column(
                connection,
                "personal_questions",
                "trashed_at",
                "TEXT",
            )
            self._ensure_column(
                connection,
                "personal_questions",
                "copied_from_question_id",
                "TEXT",
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_personal_questions_owner_lifecycle
                ON personal_questions(owner_id, lifecycle_state, sort_order, updated_at DESC)
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _ensure_column(
        connection: sqlite3.Connection,
        table: str,
        column: str,
        definition: str,
    ) -> None:
        columns = {
            row[1] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in columns:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    @staticmethod
    def _require_owned_category(
        connection: sqlite3.Connection,
        *,
        collection_id: str,
        category_id: str,
        owner_id: str,
    ) -> None:
        row = connection.execute(
            """
            SELECT category_id FROM personal_question_categories
            WHERE category_id = ? AND collection_id = ? AND owner_id = ?
            """,
            (category_id, collection_id, owner_id),
        ).fetchone()
        if row is None:
            raise KeyError(category_id)

    @staticmethod
    def _normalized_name(value: str, *, kind: str) -> tuple[str, str]:
        name = re.sub(r"\s+", " ", value).strip()
        if not name:
            raise PersonalQuestionLibraryError(f"{kind}名称不能为空")
        return name, name.casefold()

    @staticmethod
    def _normalized_tags(values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            tag = re.sub(r"\s+", " ", value).strip()
            if not tag:
                raise PersonalQuestionLibraryError("私题标签不能为空")
            key = tag.casefold()
            if key not in seen:
                normalized.append(tag)
                seen.add(key)
        return normalized

    @staticmethod
    def _collection_view(row: sqlite3.Row) -> PersonalCollectionView:
        return PersonalCollectionView(
            collection_id=row["collection_id"],
            name=row["name"],
            description=row["description"],
            category_count=row["category_count"],
            question_count=row["question_count"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _category_view(row: sqlite3.Row) -> PersonalCategoryView:
        return PersonalCategoryView(
            category_id=row["category_id"],
            collection_id=row["collection_id"],
            name=row["name"],
            description=row["description"],
            sort_order=row["sort_order"],
            question_count=row["question_count"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _revision_view(row: sqlite3.Row) -> PersonalAuthoringRevisionView:
        return PersonalAuthoringRevisionView(
            draft_id=row["draft_id"],
            revision_number=row["revision_number"],
            revision_source=row["revision_source"],
            edit_summary=row["edit_summary"],
            draft=GeneratedQuestionDraft.model_validate_json(row["draft_json"]),
            created_at=row["created_at"],
        )

    @classmethod
    def _authoring_draft_view(cls, row: sqlite3.Row) -> PersonalAuthoringDraftView:
        current = PersonalAuthoringRevisionView(
            draft_id=row["draft_id"],
            revision_number=row["current_revision"],
            revision_source=row["revision_source"],
            edit_summary=row["edit_summary"],
            draft=GeneratedQuestionDraft.model_validate_json(row["draft_json"]),
            created_at=row["revision_created_at"],
        )
        return PersonalAuthoringDraftView(
            draft_id=row["draft_id"],
            current_revision=row["current_revision"],
            saved=row["saved_question_id"] is not None,
            saved_question_id=row["saved_question_id"],
            current=current,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _question_view(row: sqlite3.Row) -> PersonalQuestionView:
        question_payload = json.loads(row["question_json"])
        question_payload["saved"] = True
        warnings = [
            warning
            for warning in question_payload.get("warnings", [])
            if "尚未保存" not in warning and "仍在个人命题工作区" not in warning
        ]
        saved_warning = "本题已由教师明确保存到个人私题库；始终仅自己可见。"
        if saved_warning not in warnings:
            warnings.insert(0, saved_warning)
        question_payload["warnings"] = warnings
        return PersonalQuestionView(
            question_id=row["question_id"],
            collection_id=row["collection_id"],
            category_id=row["category_id"],
            name=row["name"],
            source_draft_id=row["source_draft_id"],
            selected_revision=row["selected_revision"],
            tags=json.loads(row["tags_json"]),
            sort_order=row["sort_order"],
            lifecycle_state=row["lifecycle_state"],
            trashed_at=row["trashed_at"],
            copied_from_question_id=row["copied_from_question_id"],
            question=SavedPersonalQuestionDraft.model_validate(question_payload),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
