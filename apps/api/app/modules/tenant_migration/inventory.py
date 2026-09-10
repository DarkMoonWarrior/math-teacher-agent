from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from app.core.config import Settings
from app.modules.tenant_migration.schemas import (
    OwnerDataInventoryReport,
    OwnerDataStoreInventory,
    OwnerDataTableInventory,
)


class OwnerDataInventoryError(ValueError):
    """The inventory contract is unsafe or incomplete."""


OwnershipMode = Literal["direct", "inherited", "legacy_unowned"]


@dataclass(frozen=True)
class OwnerTableSpec:
    table_name: str
    ownership: OwnershipMode
    required_columns: tuple[str, ...]


@dataclass(frozen=True)
class OwnerSqliteStoreSpec:
    store_id: str
    path: Path
    tables: tuple[OwnerTableSpec, ...]


@dataclass(frozen=True)
class OwnerDirectoryStoreSpec:
    store_id: str
    path: Path
    owner_source_store: str


OwnerStoreSpec = OwnerSqliteStoreSpec | OwnerDirectoryStoreSpec


def _direct(table_name: str, *required_columns: str) -> OwnerTableSpec:
    return OwnerTableSpec(
        table_name,
        "direct",
        tuple(dict.fromkeys((*required_columns, "owner_id"))),
    )


def _inherited(table_name: str, *required_columns: str) -> OwnerTableSpec:
    return OwnerTableSpec(table_name, "inherited", required_columns)


def _legacy(table_name: str, *required_columns: str) -> OwnerTableSpec:
    return OwnerTableSpec(table_name, "legacy_unowned", required_columns)


def owner_data_store_specs(settings: Settings) -> tuple[OwnerStoreSpec, ...]:
    """Return the explicit M14 private-data migration catalog.

    Public question-bank content, derived indexes, exports, sessions, security
    facts and M13 validation facts are deliberately outside this catalog. Every
    table in an included SQLite file is named so unclassified data blocks later
    migration rather than being silently dropped.
    """

    return (
        OwnerSqliteStoreSpec(
            "private_library",
            settings.private_library_db,
            (
                _direct("library_items", "library_item_id"),
                _inherited("library_text_revisions", "library_item_id"),
                _inherited("library_ocr_runs", "library_item_id"),
                _inherited("library_question_candidates", "library_item_id"),
                _inherited("library_lifecycle_events", "library_item_id"),
            ),
        ),
        OwnerDirectoryStoreSpec(
            "private_library_files", settings.private_library_dir, "private_library"
        ),
        OwnerSqliteStoreSpec(
            "question_capture",
            settings.question_capture_db,
            (
                _direct("question_capture_assets", "asset_id"),
                _inherited("question_capture_revisions", "asset_id"),
                _inherited("question_capture_recognitions", "asset_id"),
                _direct("question_capture_solve_uses", "request_id", "asset_id"),
            ),
        ),
        OwnerDirectoryStoreSpec(
            "question_capture_files", settings.question_capture_dir, "question_capture"
        ),
        OwnerSqliteStoreSpec(
            "personal_question_library",
            settings.personal_question_library_db,
            (
                _direct("personal_question_collections", "collection_id"),
                _direct(
                    "personal_question_categories", "category_id", "collection_id"
                ),
                _direct("personal_authoring_drafts", "draft_id"),
                _direct(
                    "personal_authoring_revisions", "draft_id", "revision_number"
                ),
                _direct("personal_questions", "question_id"),
            ),
        ),
        OwnerSqliteStoreSpec(
            "pdf_imports",
            settings.pdf_import_db,
            (
                _direct("import_batches", "batch_id"),
                _inherited("import_files", "file_id", "batch_id"),
                _inherited("import_file_lifecycle_events", "file_id"),
                _inherited("import_batch_lifecycle_events", "batch_id"),
                _inherited("import_pages", "page_id", "file_id"),
                _inherited(
                    "import_source_pairs",
                    "pair_id",
                    "question_file_id",
                    "solution_file_id",
                ),
                _inherited(
                    "import_boundary_candidates", "candidate_id", "file_id"
                ),
                _inherited(
                    "import_source_item_matches", "item_match_id", "pair_id"
                ),
                _inherited(
                    "import_structured_question_drafts", "draft_id", "file_id"
                ),
                _inherited(
                    "import_structured_media_crops", "crop_id", "draft_id"
                ),
            ),
        ),
        OwnerDirectoryStoreSpec(
            "pdf_import_files", settings.pdf_import_dir, "pdf_imports"
        ),
        OwnerSqliteStoreSpec(
            "lesson_plans",
            settings.lesson_plan_db,
            (
                _legacy("lesson_plans", "lesson_plan_id"),
                _direct("m10_lesson_plans", "lesson_plan_id"),
                _direct("m10_lesson_versions", "lesson_plan_id", "version"),
            ),
        ),
        OwnerSqliteStoreSpec(
            "exam_papers",
            settings.exam_paper_db,
            (
                _direct("exam_papers", "exam_paper_id"),
                _direct("exam_paper_revisions", "exam_paper_id", "version"),
            ),
        ),
        OwnerDirectoryStoreSpec(
            "exam_paper_assets", settings.exam_paper_asset_dir, "exam_papers"
        ),
        OwnerSqliteStoreSpec(
            "teacher_memory",
            settings.teacher_memory_db,
            (
                _direct("m11_teacher_memory_profiles"),
                _direct("m11_teacher_preferences", "preference_key"),
                _direct("m11_teacher_memory_observations", "evidence_id"),
                _direct("m11_teacher_memory_proposals", "proposal_id"),
                _direct("m11_teacher_memory_feedback", "feedback_id"),
            ),
        ),
    )


class OwnerDataInventory:
    """Inspect legacy owner data without creating, mutating or exposing it."""

    _IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{1,79}$")

    def __init__(self, specs: tuple[OwnerStoreSpec, ...]) -> None:
        if not specs:
            raise OwnerDataInventoryError("OWNER_DATA_CATALOG_EMPTY")
        store_ids = [spec.store_id for spec in specs]
        if len(store_ids) != len(set(store_ids)) or any(
            not re.fullmatch(r"[a-z][a-z0-9_]{1,63}", store_id)
            for store_id in store_ids
        ):
            raise OwnerDataInventoryError("OWNER_DATA_CATALOG_INVALID")
        sqlite_store_ids = {
            spec.store_id for spec in specs if isinstance(spec, OwnerSqliteStoreSpec)
        }
        normalized_paths = [
            os.path.normcase(str(spec.path.absolute())) for spec in specs
        ]
        if len(normalized_paths) != len(set(normalized_paths)):
            raise OwnerDataInventoryError("OWNER_DATA_CATALOG_INVALID")
        for spec in specs:
            if isinstance(spec, OwnerDirectoryStoreSpec):
                if spec.owner_source_store not in sqlite_store_ids:
                    raise OwnerDataInventoryError("OWNER_DATA_CATALOG_INVALID")
                continue
            table_names = [table.table_name for table in spec.tables]
            if len(table_names) != len(set(table_names)) or any(
                not self._IDENTIFIER.fullmatch(name) for name in table_names
            ):
                raise OwnerDataInventoryError("OWNER_DATA_CATALOG_INVALID")
        self._specs = specs

    def inspect(self, *, source_owner_id: str) -> OwnerDataInventoryReport:
        if not source_owner_id or len(source_owner_id) > 120:
            raise OwnerDataInventoryError("SOURCE_OWNER_INVALID")
        stores = tuple(
            self._inspect_store(spec, source_owner_id) for spec in self._specs
        )
        canonical = {
            "schema_version": 1,
            "source_owner_digest": hashlib.sha256(
                source_owner_id.encode("utf-8")
            ).hexdigest(),
            "stores": [store.model_dump(mode="json") for store in stores],
        }
        fingerprint = hashlib.sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()
        matching_rows = sum(
            table.matching_owner_rows or 0
            for store in stores
            for table in store.tables
        )
        return OwnerDataInventoryReport(
            store_count=len(stores),
            ready_store_count=sum(store.status == "ready" for store in stores),
            blocked_store_count=sum(store.status == "blocked" for store in stores),
            missing_store_count=sum(store.status == "missing" for store in stores),
            matching_owner_rows=matching_rows,
            migration_ready=all(store.migration_ready for store in stores),
            report_fingerprint=fingerprint,
            stores=stores,
        )

    def _inspect_store(
        self, spec: OwnerStoreSpec, source_owner_id: str
    ) -> OwnerDataStoreInventory:
        try:
            self._reject_links(spec.path)
            if not spec.path.exists():
                return OwnerDataStoreInventory(
                    store_id=spec.store_id,
                    kind=(
                        "directory"
                        if isinstance(spec, OwnerDirectoryStoreSpec)
                        else "sqlite"
                    ),
                    status="missing",
                    migration_ready=True,
                )
            if isinstance(spec, OwnerDirectoryStoreSpec):
                return self._inspect_directory(spec)
            return self._inspect_sqlite(spec, source_owner_id)
        except (OSError, sqlite3.Error, OwnerDataInventoryError):
            return OwnerDataStoreInventory(
                store_id=spec.store_id,
                kind=(
                    "directory"
                    if isinstance(spec, OwnerDirectoryStoreSpec)
                    else "sqlite"
                ),
                status="blocked",
                migration_ready=False,
                issues=("OWNER_STORE_INSPECTION_FAILED",),
            )

    def _inspect_sqlite(
        self, spec: OwnerSqliteStoreSpec, source_owner_id: str
    ) -> OwnerDataStoreInventory:
        if not spec.path.is_file():
            raise OwnerDataInventoryError("OWNER_STORE_NOT_FILE")
        resolved_path = quote(spec.path.resolve().as_posix(), safe="/:")
        uri = f"file:{resolved_path}?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            connection.execute("PRAGMA query_only = ON")
            objects = connection.execute(
                "SELECT type, name FROM sqlite_master "
                "WHERE type IN ('table', 'view', 'trigger') "
                "AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
            actual_tables = {name for kind, name in objects if kind == "table"}
            expected_tables = {table.table_name for table in spec.tables}
            issues: list[str] = []
            # Stores initialize lazily, so an absent known table means there is
            # nothing to migrate. An unknown table is unsafe because it has no
            # declared ownership path.
            if not actual_tables.issubset(expected_tables):
                issues.append("OWNER_STORE_TABLE_SET_MISMATCH")
            if any(kind != "table" for kind, _ in objects):
                issues.append("OWNER_STORE_UNEXPECTED_SQL_OBJECT")

            table_results: list[OwnerDataTableInventory] = []
            for table in spec.tables:
                if table.table_name not in actual_tables:
                    continue
                identifier = self._quote(table.table_name)
                columns = {
                    str(row[1])
                    for row in connection.execute(f"PRAGMA table_info({identifier})")
                }
                if not set(table.required_columns).issubset(columns):
                    issues.append("OWNER_STORE_COLUMN_SET_MISMATCH")
                    continue
                total = int(
                    connection.execute(f"SELECT COUNT(*) FROM {identifier}").fetchone()[0]
                )
                matching: int | None = None
                if table.ownership == "direct":
                    matching = int(
                        connection.execute(
                            f"SELECT COUNT(*) FROM {identifier} WHERE owner_id = ?",
                            (source_owner_id,),
                        ).fetchone()[0]
                    )
                table_results.append(
                    OwnerDataTableInventory(
                        table_name=table.table_name,
                        ownership=table.ownership,
                        total_rows=total,
                        matching_owner_rows=matching,
                    )
                )
                if table.ownership == "legacy_unowned" and total:
                    issues.append("LEGACY_UNOWNED_ROWS_PRESENT")

        unique_issues = tuple(dict.fromkeys(issues))
        return OwnerDataStoreInventory(
            store_id=spec.store_id,
            kind="sqlite",
            status="blocked" if unique_issues else "ready",
            migration_ready=not unique_issues,
            tables=tuple(table_results),
            issues=unique_issues,
        )

    def _inspect_directory(
        self, spec: OwnerDirectoryStoreSpec
    ) -> OwnerDataStoreInventory:
        if not spec.path.is_dir():
            raise OwnerDataInventoryError("OWNER_STORE_NOT_DIRECTORY")
        file_count = 0
        for root, directories, files in os.walk(
            spec.path, followlinks=False, onerror=self._raise_walk_error
        ):
            root_path = Path(root)
            for name in (*directories, *files):
                self._reject_link_only(root_path / name)
            file_count += len(files)
        issues = (
            ("INDIRECT_FILE_OWNERSHIP_REQUIRES_RECONCILIATION",)
            if file_count
            else ()
        )
        return OwnerDataStoreInventory(
            store_id=spec.store_id,
            kind="directory",
            status="blocked" if issues else "ready",
            migration_ready=not issues,
            file_count=file_count,
            issues=issues,
        )

    @staticmethod
    def _raise_walk_error(error: OSError) -> None:
        raise error

    @classmethod
    def _quote(cls, value: str) -> str:
        if not cls._IDENTIFIER.fullmatch(value):
            raise OwnerDataInventoryError("OWNER_DATA_CATALOG_INVALID")
        return f'"{value}"'

    @classmethod
    def _reject_links(cls, path: Path) -> None:
        absolute = path.absolute()
        for current in (absolute, *absolute.parents):
            cls._reject_link_only(current)

    @staticmethod
    def _reject_link_only(path: Path) -> None:
        is_junction = getattr(path, "is_junction", None)
        if path.is_symlink() or bool(is_junction and is_junction()):
            raise OwnerDataInventoryError("OWNER_STORE_LINK_NOT_ALLOWED")
        try:
            info = path.lstat()
        except FileNotFoundError:
            return
        if stat.S_ISLNK(info.st_mode) or bool(
            getattr(info, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        ):
            raise OwnerDataInventoryError("OWNER_STORE_LINK_NOT_ALLOWED")
