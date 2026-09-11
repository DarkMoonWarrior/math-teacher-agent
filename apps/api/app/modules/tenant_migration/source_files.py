from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

from app.modules.tenant_migration.file_reconciliation import (
    OwnerFileReconciliation,
    OwnerFileStoreSpec,
)
from app.modules.tenant_migration.fingerprints import owner_file_digest


class OwnerMigrationSourceFileError(ValueError):
    """An owner-scoped source file cannot be resolved without ambiguity."""


@dataclass(frozen=True, repr=False)
class OwnerMigrationSourceFile:
    store_id: str
    object_digest: str
    source_checksum: str
    byte_length: int
    reference: str = field(repr=False)
    path: Path = field(repr=False)


@dataclass(frozen=True, repr=False)
class OwnerMigrationSourceFileStore:
    store_id: str
    objects: tuple[OwnerMigrationSourceFile, ...] = field(repr=False)


class OwnerMigrationSourceFiles:
    """Resolve and fingerprint only files referenced by one source owner."""

    _PAPER_ID = re.compile(r"^[A-Za-z0-9_-]{1,160}$")
    _ASSET_ID = re.compile(r"^[A-Za-z0-9_-]{1,180}$")

    def __init__(self, specs: tuple[OwnerFileStoreSpec, ...]) -> None:
        try:
            OwnerFileReconciliation(specs)
        except ValueError as error:
            raise OwnerMigrationSourceFileError(
                "MIGRATION_SOURCE_FILE_CATALOG_INVALID"
            ) from error
        self._specs = specs

    def inspect(
        self,
        *,
        source_owner_id: str,
        binding: tuple[str, str, str],
    ) -> tuple[OwnerMigrationSourceFileStore, ...]:
        if (
            not source_owner_id
            or len(source_owner_id) > 120
            or len(binding) != 3
            or binding[0] != source_owner_id
            or any(not value or len(value) > 120 for value in binding)
        ):
            raise OwnerMigrationSourceFileError(
                "MIGRATION_SOURCE_FILE_BINDING_INVALID"
            )
        try:
            return tuple(
                self._inspect_store(spec, source_owner_id, binding)
                for spec in self._specs
            )
        except OwnerMigrationSourceFileError:
            raise
        except (OSError, sqlite3.Error, ValueError) as error:
            raise OwnerMigrationSourceFileError(
                "MIGRATION_SOURCE_FILE_UNAVAILABLE"
            ) from error

    def _inspect_store(
        self,
        spec: OwnerFileStoreSpec,
        source_owner_id: str,
        binding: tuple[str, str, str],
    ) -> OwnerMigrationSourceFileStore:
        references = self._references(spec, source_owner_id)
        objects = tuple(
            sorted(
                (self._inspect_file(spec, binding, reference) for reference in references),
                key=lambda item: item.object_digest,
            )
        )
        return OwnerMigrationSourceFileStore(store_id=spec.store_id, objects=objects)

    def _inspect_file(
        self,
        spec: OwnerFileStoreSpec,
        binding: tuple[str, str, str],
        reference: str,
    ) -> OwnerMigrationSourceFile:
        path = self._path(spec, reference)
        OwnerFileReconciliation._reject_links(path)
        digest = hashlib.sha256()
        length = 0
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
                length += len(chunk)
        return OwnerMigrationSourceFile(
            store_id=spec.store_id,
            object_digest=owner_file_digest(binding, spec.store_id, reference),
            source_checksum=digest.hexdigest(),
            byte_length=length,
            reference=reference,
            path=path,
        )

    def _references(self, spec: OwnerFileStoreSpec, source_owner_id: str) -> set[str]:
        OwnerFileReconciliation._reject_links(spec.database.path)
        if not spec.database.path.exists():
            return set()
        with self._connect(spec.database.path) as connection:
            if spec.layout == "private_library":
                rows = connection.execute(
                    "SELECT stored_name, owner_id FROM library_items"
                ).fetchall()
                return self._owned_rows(rows, source_owner_id, "library")
            if spec.layout == "question_capture":
                rows = connection.execute(
                    "SELECT r.stored_name, a.owner_id "
                    "FROM question_capture_revisions r "
                    "LEFT JOIN question_capture_assets a ON a.asset_id = r.asset_id"
                ).fetchall()
                return self._owned_rows(rows, source_owner_id, "capture")
            if spec.layout == "pdf_imports":
                files = connection.execute(
                    "SELECT f.stored_name, b.owner_id FROM import_files f "
                    "LEFT JOIN import_batches b ON b.batch_id = f.batch_id"
                ).fetchall()
                crops = connection.execute(
                    "SELECT c.stored_name, b.owner_id "
                    "FROM import_structured_media_crops c "
                    "LEFT JOIN import_files f ON f.file_id = c.file_id "
                    "LEFT JOIN import_batches b ON b.batch_id = f.batch_id"
                ).fetchall()
                return self._owned_rows((*files, *crops), source_owner_id, "pdf")
            if spec.layout == "exam_papers":
                return self._exam_references(connection, source_owner_id)
        raise OwnerMigrationSourceFileError("MIGRATION_SOURCE_FILE_LAYOUT_INVALID")

    @staticmethod
    def _owned_rows(
        rows: list[tuple[object, object]] | tuple[tuple[object, object], ...],
        source_owner_id: str,
        namespace: str,
    ) -> set[str]:
        result: set[str] = set()
        for name, owner in rows:
            if not isinstance(name, str) or not OwnerFileReconciliation._safe_name(name):
                raise OwnerMigrationSourceFileError(
                    "MIGRATION_SOURCE_FILE_REFERENCE_INVALID"
                )
            if not isinstance(owner, str) or not owner:
                raise OwnerMigrationSourceFileError(
                    "MIGRATION_SOURCE_FILE_OWNER_UNRESOLVED"
                )
            if owner == source_owner_id:
                result.add(f"{namespace}:{name}")
        return result

    def _exam_references(
        self, connection: sqlite3.Connection, source_owner_id: str
    ) -> set[str]:
        owners: dict[tuple[str, str], set[str]] = {}
        for table in ("exam_papers", "exam_paper_revisions"):
            if not self._table_exists(connection, table):
                continue
            rows = connection.execute(
                f'SELECT owner_id, exam_paper_id, raw_json FROM "{table}"'
            ).fetchall()
            for owner, paper_id, raw_json in rows:
                if not isinstance(owner, str) or not owner:
                    raise OwnerMigrationSourceFileError(
                        "MIGRATION_SOURCE_FILE_OWNER_UNRESOLVED"
                    )
                if not isinstance(paper_id, str) or not self._PAPER_ID.fullmatch(
                    paper_id
                ):
                    raise OwnerMigrationSourceFileError(
                        "MIGRATION_SOURCE_FILE_REFERENCE_INVALID"
                    )
                try:
                    payload = json.loads(str(raw_json))
                    items = payload["items"]
                    if not isinstance(items, list):
                        raise TypeError
                    for item in items:
                        images = item.get("question", {}).get("images", [])
                        if not isinstance(images, list):
                            raise TypeError
                        for image in images:
                            asset_id = image["asset_id"]
                            if not isinstance(
                                asset_id, str
                            ) or not self._ASSET_ID.fullmatch(asset_id):
                                raise TypeError
                            owners.setdefault((paper_id, asset_id), set()).add(owner)
                except (KeyError, TypeError, json.JSONDecodeError) as error:
                    raise OwnerMigrationSourceFileError(
                        "MIGRATION_SOURCE_FILE_REFERENCE_INVALID"
                    ) from error
        if any(len(values) != 1 for values in owners.values()):
            raise OwnerMigrationSourceFileError(
                "MIGRATION_SOURCE_FILE_OWNER_UNRESOLVED"
            )
        return {
            f"paper:{paper_id}:{asset_id}"
            for (paper_id, asset_id), values in owners.items()
            if source_owner_id in values
        }

    def _path(self, spec: OwnerFileStoreSpec, reference: str) -> Path:
        prefixes = {
            "private_library": "library:",
            "question_capture": "capture:",
            "pdf_imports": "pdf:",
        }
        prefix = prefixes.get(spec.layout)
        if prefix is not None:
            if not reference.startswith(prefix):
                raise OwnerMigrationSourceFileError(
                    "MIGRATION_SOURCE_FILE_REFERENCE_INVALID"
                )
            name = reference[len(prefix) :]
            if not OwnerFileReconciliation._safe_name(name):
                raise OwnerMigrationSourceFileError(
                    "MIGRATION_SOURCE_FILE_REFERENCE_INVALID"
                )
            return spec.files.path / name

        parts = reference.split(":")
        if (
            len(parts) != 3
            or parts[0] != "paper"
            or not self._PAPER_ID.fullmatch(parts[1])
            or not self._ASSET_ID.fullmatch(parts[2])
        ):
            raise OwnerMigrationSourceFileError(
                "MIGRATION_SOURCE_FILE_REFERENCE_INVALID"
            )
        directory = spec.files.path / parts[1]
        OwnerFileReconciliation._reject_links(directory)
        matches = [
            entry
            for entry in directory.iterdir()
            if entry.is_file() and entry.stem == parts[2]
        ]
        if len(matches) != 1:
            raise OwnerMigrationSourceFileError("MIGRATION_SOURCE_FILE_UNAVAILABLE")
        return matches[0]

    @staticmethod
    def _connect(path: Path) -> sqlite3.Connection:
        encoded = quote(path.resolve().as_posix(), safe="/:")
        connection = sqlite3.connect(f"file:{encoded}?mode=ro", uri=True)
        connection.execute("PRAGMA query_only = ON")
        return connection

    @staticmethod
    def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
        return connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone() is not None
