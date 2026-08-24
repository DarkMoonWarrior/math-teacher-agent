from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.modules.personal_question_library.schemas import (
    PersonalCategoryCreate,
    PersonalCategoryList,
    PersonalCategoryUpdate,
    PersonalCategoryView,
    PersonalCollectionCreate,
    PersonalCollectionList,
    PersonalCollectionUpdate,
    PersonalCollectionView,
)


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
                SELECT collections.*, COUNT(categories.category_id) AS category_count
                FROM personal_question_collections AS collections
                LEFT JOIN personal_question_categories AS categories
                    ON categories.collection_id = collections.collection_id
                    AND categories.owner_id = collections.owner_id
                WHERE collections.owner_id = ?
                GROUP BY collections.collection_id
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
                SELECT collections.*, COUNT(categories.category_id) AS category_count
                FROM personal_question_collections AS collections
                LEFT JOIN personal_question_categories AS categories
                    ON categories.collection_id = collections.collection_id
                    AND categories.owner_id = collections.owner_id
                WHERE collections.collection_id = ? AND collections.owner_id = ?
                GROUP BY collections.collection_id
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
                SELECT * FROM personal_question_categories
                WHERE collection_id = ? AND owner_id = ?
                ORDER BY sort_order ASC, updated_at DESC, category_id ASC
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
                SELECT * FROM personal_question_categories
                WHERE category_id = ? AND owner_id = ?
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

                CREATE INDEX IF NOT EXISTS idx_personal_collections_owner
                    ON personal_question_collections(owner_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_personal_categories_owner_collection
                    ON personal_question_categories(owner_id, collection_id, sort_order);
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
            question_count=0,
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
            question_count=0,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
