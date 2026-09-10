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
from app.modules.tenant_migration.inventory import (
    OwnerDataInventoryError,
    OwnerDirectoryStoreSpec,
    OwnerSqliteStoreSpec,
    owner_data_store_specs,
)
from app.modules.tenant_migration.schemas import (
    OwnerFileReconciliationReport,
    OwnerFileStoreReconciliation,
)


class OwnerFileReconciliationError(ValueError):
    """The file reconciliation contract is unsafe or incomplete."""


FileLayout = Literal["private_library", "question_capture", "pdf_imports", "exam_papers"]


@dataclass(frozen=True)
class OwnerFileStoreSpec:
    store_id: str
    database: OwnerSqliteStoreSpec
    files: OwnerDirectoryStoreSpec
    layout: FileLayout


def owner_file_store_specs(settings: Settings) -> tuple[OwnerFileStoreSpec, ...]:
    catalog = {spec.store_id: spec for spec in owner_data_store_specs(settings)}
    mappings = (
        ("private_library_files", "private_library", "private_library"),
        ("question_capture_files", "question_capture", "question_capture"),
        ("pdf_import_files", "pdf_imports", "pdf_imports"),
        ("exam_paper_assets", "exam_papers", "exam_papers"),
    )
    result: list[OwnerFileStoreSpec] = []
    for file_id, database_id, layout in mappings:
        files = catalog.get(file_id)
        database = catalog.get(database_id)
        if not isinstance(files, OwnerDirectoryStoreSpec) or not isinstance(
            database, OwnerSqliteStoreSpec
        ):
            raise OwnerFileReconciliationError("OWNER_FILE_CATALOG_INVALID")
        result.append(OwnerFileStoreSpec(file_id, database, files, layout))
    return tuple(result)


class OwnerFileReconciliation:
    """Reconcile owner file references without reading contents or writing stores."""

    _STORE_ID = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
    _PAPER_ID = re.compile(r"^[A-Za-z0-9_-]{1,160}$")
    _ASSET_ID = re.compile(r"^[A-Za-z0-9_-]{1,180}$")

    def __init__(self, specs: tuple[OwnerFileStoreSpec, ...]) -> None:
        if not specs:
            raise OwnerFileReconciliationError("OWNER_FILE_CATALOG_EMPTY")
        store_ids = [spec.store_id for spec in specs]
        layouts = [spec.layout for spec in specs]
        paths = [
            os.path.normcase(str(path.absolute()))
            for spec in specs
            for path in (spec.database.path, spec.files.path)
        ]
        if (
            len(store_ids) != len(set(store_ids))
            or len(layouts) != len(set(layouts))
            or len(paths) != len(set(paths))
            or any(not self._STORE_ID.fullmatch(value) for value in store_ids)
            or any(spec.files.owner_source_store != spec.database.store_id for spec in specs)
        ):
            raise OwnerFileReconciliationError("OWNER_FILE_CATALOG_INVALID")
        self._specs = specs

    def reconcile(self, *, source_owner_id: str) -> OwnerFileReconciliationReport:
        if not source_owner_id or len(source_owner_id) > 120:
            raise OwnerFileReconciliationError("SOURCE_OWNER_INVALID")
        stores = tuple(self._inspect(spec, source_owner_id) for spec in self._specs)
        canonical = {
            "schema_version": 1,
            "owner_digest": hashlib.sha256(source_owner_id.encode("utf-8")).hexdigest(),
            "stores": [store.model_dump(mode="json") for store in stores],
        }
        fingerprint = hashlib.sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return OwnerFileReconciliationReport(
            store_count=len(stores),
            ready_store_count=sum(store.status == "ready" for store in stores),
            blocked_store_count=sum(store.status == "blocked" for store in stores),
            missing_store_count=sum(store.status == "missing" for store in stores),
            referenced_files=sum(store.referenced_files for store in stores),
            present_files=sum(store.present_files for store in stores),
            migration_ready=all(store.migration_ready for store in stores),
            report_fingerprint=fingerprint,
            stores=stores,
        )

    def _inspect(
        self, spec: OwnerFileStoreSpec, source_owner_id: str
    ) -> OwnerFileStoreReconciliation:
        try:
            self._reject_links(spec.database.path)
            self._reject_links(spec.files.path)
            if not spec.database.path.exists() and not spec.files.path.exists():
                return self._result(spec.store_id, status="missing")
            if spec.database.path.exists() and not spec.database.path.is_file():
                raise OwnerFileReconciliationError("OWNER_FILE_DATABASE_INVALID")
            if spec.files.path.exists() and not spec.files.path.is_dir():
                raise OwnerFileReconciliationError("OWNER_FILE_ROOT_INVALID")
            if spec.layout == "exam_papers":
                return self._inspect_exam_store(spec, source_owner_id)
            return self._inspect_flat_store(spec, source_owner_id)
        except (OSError, sqlite3.Error, ValueError, OwnerDataInventoryError):
            return self._result(
                spec.store_id,
                status="blocked",
                issues=("OWNER_FILE_RECONCILIATION_FAILED",),
            )

    def _inspect_flat_store(
        self, spec: OwnerFileStoreSpec, source_owner_id: str
    ) -> OwnerFileStoreReconciliation:
        issues: list[str] = []
        actual = self._flat_files(spec.files.path, issues)
        references: list[tuple[str, str]] = []
        unresolved = 0
        if spec.database.path.exists():
            with self._connect(spec.database.path) as connection:
                issues.extend(self._validate_schema(connection, spec.database))
                if not issues:
                    references, unresolved = self._flat_references(
                        connection, spec.layout
                    )
        elif actual:
            issues.append("FILE_REFERENCE_DATABASE_MISSING")

        owners_by_name: dict[str, set[str]] = {}
        for owner_id, stored_name in references:
            if not self._safe_name(stored_name):
                issues.append("FILE_REFERENCE_PATH_UNSAFE")
                continue
            owners_by_name.setdefault(stored_name, set()).add(owner_id)
        owned = {
            name for name, owners in owners_by_name.items() if source_owner_id in owners
        }
        missing = owned - actual
        orphaned = actual - set(owners_by_name)
        collisions = {
            name
            for name in owned
            if owners_by_name[name] - {source_owner_id}
        }
        if missing:
            issues.append("OWNER_REFERENCED_FILE_MISSING")
        if orphaned:
            issues.append("UNREFERENCED_FILE_PRESENT")
        if collisions:
            issues.append("CROSS_OWNER_FILE_REFERENCE")
        if unresolved:
            issues.append("FILE_REFERENCE_OWNER_UNRESOLVED")
        return self._result(
            spec.store_id,
            status="blocked" if issues else "ready",
            referenced_files=len(owned),
            present_files=len(owned & actual),
            missing_files=len(missing),
            orphaned_files=len(orphaned),
            cross_owner_collisions=len(collisions),
            unresolved_owner_references=unresolved,
            issues=tuple(dict.fromkeys(issues)),
            evidence={
                "actual": sorted(actual),
                "references": sorted(
                    (hashlib.sha256(owner.encode("utf-8")).hexdigest(), name)
                    for name, owners in owners_by_name.items()
                    for owner in owners
                ),
            },
        )

    def _inspect_exam_store(
        self, spec: OwnerFileStoreSpec, source_owner_id: str
    ) -> OwnerFileStoreReconciliation:
        issues: list[str] = []
        actual = self._exam_files(spec.files.path, issues)
        rows: list[tuple[str, str, str]] = []
        if spec.database.path.exists():
            with self._connect(spec.database.path) as connection:
                issues.extend(self._validate_schema(connection, spec.database))
                if not issues:
                    rows = self._exam_rows(connection)
        elif actual:
            issues.append("FILE_REFERENCE_DATABASE_MISSING")

        owners_by_paper: dict[str, set[str]] = {}
        assets_by_paper: dict[str, set[str]] = {}
        unresolved = 0
        for owner_id, paper_id, raw_json in rows:
            if not self._PAPER_ID.fullmatch(paper_id):
                issues.append("FILE_REFERENCE_PATH_UNSAFE")
                continue
            owners_by_paper.setdefault(paper_id, set()).add(owner_id)
            try:
                assets = self._asset_ids(raw_json)
            except (json.JSONDecodeError, TypeError, ValueError):
                unresolved += 1
                continue
            assets_by_paper.setdefault(paper_id, set()).update(assets)

        expected = {
            (paper_id, asset_id)
            for paper_id, assets in assets_by_paper.items()
            for asset_id in assets
        }
        owned = {
            reference
            for reference in expected
            if source_owner_id in owners_by_paper.get(reference[0], set())
        }
        missing = owned - actual
        orphaned = actual - expected
        collisions = {
            reference
            for reference in owned
            if owners_by_paper.get(reference[0], set()) - {source_owner_id}
        }
        if any(len(owners) > 1 for owners in owners_by_paper.values()):
            issues.append("CROSS_OWNER_FILE_REFERENCE")
        if missing:
            issues.append("OWNER_REFERENCED_FILE_MISSING")
        if orphaned:
            issues.append("UNREFERENCED_FILE_PRESENT")
        if unresolved:
            issues.append("FILE_REFERENCE_OWNER_UNRESOLVED")
        return self._result(
            spec.store_id,
            status="blocked" if issues else "ready",
            referenced_files=len(owned),
            present_files=len(owned & actual),
            missing_files=len(missing),
            orphaned_files=len(orphaned),
            cross_owner_collisions=len(collisions),
            unresolved_owner_references=unresolved,
            issues=tuple(dict.fromkeys(issues)),
            evidence={
                "actual": sorted(actual),
                "expected": sorted(expected),
                "paper_owners": sorted(
                    (
                        paper_id,
                        hashlib.sha256(owner.encode("utf-8")).hexdigest(),
                    )
                    for paper_id, owners in owners_by_paper.items()
                    for owner in owners
                ),
            },
        )

    def _validate_schema(
        self, connection: sqlite3.Connection, spec: OwnerSqliteStoreSpec
    ) -> list[str]:
        objects = connection.execute(
            "SELECT type, name FROM sqlite_master "
            "WHERE type IN ('table', 'view', 'trigger') AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        expected = {table.table_name for table in spec.tables}
        actual = {name for kind, name in objects if kind == "table"}
        issues: list[str] = []
        if not actual.issubset(expected) or any(kind != "table" for kind, _ in objects):
            issues.append("FILE_REFERENCE_SCHEMA_UNCLASSIFIED")
        return issues

    def _flat_references(
        self, connection: sqlite3.Connection, layout: FileLayout
    ) -> tuple[list[tuple[str, str]], int]:
        if layout == "private_library":
            return self._query_direct(connection, "library_items"), 0
        if layout == "question_capture":
            query = (
                "SELECT a.owner_id, r.stored_name FROM question_capture_revisions r "
                "JOIN question_capture_assets a ON a.asset_id = r.asset_id"
            )
            return self._query_join(connection, "question_capture_revisions", query)
        if layout == "pdf_imports":
            files_query = (
                "SELECT b.owner_id, f.stored_name FROM import_files f "
                "JOIN import_batches b ON b.batch_id = f.batch_id"
            )
            crops_query = (
                "SELECT b.owner_id, c.stored_name FROM import_structured_media_crops c "
                "JOIN import_files f ON f.file_id = c.file_id "
                "JOIN import_batches b ON b.batch_id = f.batch_id"
            )
            files, missing_files = self._query_join(connection, "import_files", files_query)
            crops, missing_crops = self._query_join(
                connection, "import_structured_media_crops", crops_query
            )
            return files + crops, missing_files + missing_crops
        raise OwnerFileReconciliationError("OWNER_FILE_LAYOUT_INVALID")

    def _query_direct(
        self, connection: sqlite3.Connection, table: str
    ) -> list[tuple[str, str]]:
        if not self._table_has_columns(connection, table, {"owner_id", "stored_name"}):
            if not self._table_exists(connection, table):
                return []
            raise OwnerFileReconciliationError("FILE_REFERENCE_SCHEMA_INVALID")
        return [
            (str(row[0]), str(row[1]))
            for row in connection.execute(
                f'SELECT owner_id, stored_name FROM "{table}"'
            )
        ]

    def _query_join(
        self, connection: sqlite3.Connection, child_table: str, query: str
    ) -> tuple[list[tuple[str, str]], int]:
        if not self._table_exists(connection, child_table):
            return [], 0
        try:
            total = int(connection.execute(f'SELECT COUNT(*) FROM "{child_table}"').fetchone()[0])
            rows = [(str(row[0]), str(row[1])) for row in connection.execute(query)]
        except sqlite3.OperationalError as error:
            raise OwnerFileReconciliationError("FILE_REFERENCE_SCHEMA_INVALID") from error
        return rows, total - len(rows)

    def _exam_rows(self, connection: sqlite3.Connection) -> list[tuple[str, str, str]]:
        rows: list[tuple[str, str, str]] = []
        for table in ("exam_papers", "exam_paper_revisions"):
            if not self._table_exists(connection, table):
                continue
            if not self._table_has_columns(
                connection, table, {"owner_id", "exam_paper_id", "raw_json"}
            ):
                raise OwnerFileReconciliationError("FILE_REFERENCE_SCHEMA_INVALID")
            rows.extend(
                (str(row[0]), str(row[1]), str(row[2]))
                for row in connection.execute(
                    f'SELECT owner_id, exam_paper_id, raw_json FROM "{table}"'
                )
            )
        return rows

    @classmethod
    def _asset_ids(cls, raw_json: str) -> set[str]:
        payload = json.loads(raw_json)
        items = payload.get("items")
        if not isinstance(items, list):
            raise ValueError("items")
        result: set[str] = set()
        for item in items:
            images = (item.get("question") or {}).get("images") if isinstance(item, dict) else None
            if images is None:
                continue
            if not isinstance(images, list):
                raise ValueError("images")
            for image in images:
                asset_id = image.get("asset_id") if isinstance(image, dict) else None
                if not isinstance(asset_id, str) or not cls._ASSET_ID.fullmatch(asset_id):
                    raise ValueError("asset_id")
                result.add(asset_id)
        return result

    @classmethod
    def _flat_files(cls, root: Path, issues: list[str]) -> set[str]:
        if not root.exists():
            return set()
        result: set[str] = set()
        for entry in root.iterdir():
            cls._reject_link_only(entry)
            if not entry.is_file() or not cls._safe_name(entry.name):
                issues.append("FILE_ROOT_LAYOUT_INVALID")
                continue
            result.add(entry.name)
        return result

    @classmethod
    def _exam_files(cls, root: Path, issues: list[str]) -> set[tuple[str, str]]:
        if not root.exists():
            return set()
        result: set[tuple[str, str]] = set()
        for directory in root.iterdir():
            cls._reject_link_only(directory)
            if not directory.is_dir() or not cls._PAPER_ID.fullmatch(directory.name):
                issues.append("FILE_ROOT_LAYOUT_INVALID")
                continue
            stems: set[str] = set()
            for entry in directory.iterdir():
                cls._reject_link_only(entry)
                if not entry.is_file() or not cls._safe_name(entry.name):
                    issues.append("FILE_ROOT_LAYOUT_INVALID")
                    continue
                if entry.stem in stems:
                    issues.append("FILE_ROOT_LAYOUT_INVALID")
                stems.add(entry.stem)
                result.add((directory.name, entry.stem))
        return result

    @staticmethod
    def _safe_name(value: str) -> bool:
        return bool(
            value
            and value not in {".", ".."}
            and Path(value).name == value
            and "/" not in value
            and "\\" not in value
        )

    @staticmethod
    def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
        return connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
        ).fetchone() is not None

    @classmethod
    def _table_has_columns(
        cls, connection: sqlite3.Connection, table: str, required: set[str]
    ) -> bool:
        if not cls._table_exists(connection, table):
            return False
        columns = {
            str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")')
        }
        return required.issubset(columns)

    @staticmethod
    def _connect(path: Path) -> sqlite3.Connection:
        encoded = quote(path.resolve().as_posix(), safe="/:")
        connection = sqlite3.connect(f"file:{encoded}?mode=ro", uri=True)
        connection.execute("PRAGMA query_only = ON")
        return connection

    @classmethod
    def _reject_links(cls, path: Path) -> None:
        absolute = path.absolute()
        for current in (absolute, *absolute.parents):
            cls._reject_link_only(current)

    @staticmethod
    def _reject_link_only(path: Path) -> None:
        is_junction = getattr(path, "is_junction", None)
        if path.is_symlink() or bool(is_junction and is_junction()):
            raise OwnerFileReconciliationError("OWNER_FILE_LINK_NOT_ALLOWED")
        try:
            attributes = getattr(path.lstat(), "st_file_attributes", 0)
        except FileNotFoundError:
            return
        reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        if attributes & reparse:
            raise OwnerFileReconciliationError("OWNER_FILE_LINK_NOT_ALLOWED")

    @staticmethod
    def _result(
        store_id: str,
        *,
        status: Literal["ready", "missing", "blocked"],
        referenced_files: int = 0,
        present_files: int = 0,
        missing_files: int = 0,
        orphaned_files: int = 0,
        cross_owner_collisions: int = 0,
        unresolved_owner_references: int = 0,
        issues: tuple[str, ...] = (),
        evidence: object | None = None,
    ) -> OwnerFileStoreReconciliation:
        evidence_fingerprint = hashlib.sha256(
            json.dumps(
                evidence,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode("utf-8")
        ).hexdigest()
        return OwnerFileStoreReconciliation(
            store_id=store_id,
            status=status,
            migration_ready=status != "blocked",
            referenced_files=referenced_files,
            present_files=present_files,
            missing_files=missing_files,
            orphaned_files=orphaned_files,
            cross_owner_collisions=cross_owner_collisions,
            unresolved_owner_references=unresolved_owner_references,
            evidence_fingerprint=evidence_fingerprint,
            issues=issues,
        )
