from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.modules.personal_question_library.schemas import (
    PersonalAuthoringDraftView,
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
    PersonalQuestionSave,
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
        question_payload = json.loads(row["question_json"])
        question_payload["saved"] = True
        return PersonalQuestionView(
            question_id=row["question_id"],
            collection_id=row["collection_id"],
            category_id=row["category_id"],
            name=row["name"],
            source_draft_id=row["source_draft_id"],
            selected_revision=row["selected_revision"],
            question=SavedPersonalQuestionDraft.model_validate(question_payload),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

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

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _normalized_name(value: str, *, kind: str) -> tuple[str, str]:
        name = re.sub(r"\s+", " ", value).strip()
        if not name:
            raise PersonalQuestionLibraryError(f"{kind}名称不能为空")
        return name, name.casefold()

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
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
