from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, NoReturn, Protocol

from app.modules.tenant_migration.file_reconciliation import OwnerFileReconciliation
from app.modules.tenant_migration.fingerprints import (
    canonical_digest,
    migration_plan_fingerprint,
    target_binding_fingerprint,
)
from app.modules.tenant_migration.schemas import OwnerMigrationPlanReport
from app.modules.tenant_migration.source_files import (
    OwnerMigrationSourceFile,
    OwnerMigrationSourceFileError,
    OwnerMigrationSourceFileStore,
)


class OwnerMigrationFileMaterializationError(ValueError):
    """A planned file stream cannot be materialized without ambiguity."""


class OwnerMigrationFileSource(Protocol):
    def inspect(
        self,
        *,
        source_owner_id: str,
        binding: tuple[str, str, str],
    ) -> tuple[OwnerMigrationSourceFileStore, ...]: ...


@dataclass(frozen=True, repr=False)
class MaterializedMigrationFile:
    sequence: int
    store_id: str
    object_digest: str
    source_checksum: str
    byte_length: int
    _path: Path = field(repr=False)

    def copy_to(self, staging_sink: BinaryIO) -> int:
        """Stream into a rollback-capable staging sink and verify again at EOF."""
        digest = hashlib.sha256()
        length = 0
        try:
            OwnerFileReconciliation._reject_links(self._path)
            with self._path.open("rb") as source:
                while chunk := source.read(1024 * 1024):
                    written = staging_sink.write(chunk)
                    if written is not None and written != len(chunk):
                        raise OSError("short staging write")
                    digest.update(chunk)
                    length += len(chunk)
        except OwnerMigrationFileMaterializationError:
            raise
        except (OSError, ValueError) as error:
            raise OwnerMigrationFileMaterializationError(
                "MIGRATION_FILE_STREAM_FAILED"
            ) from error
        if length != self.byte_length or not secrets.compare_digest(
            digest.hexdigest(), self.source_checksum
        ):
            raise OwnerMigrationFileMaterializationError(
                "MIGRATION_FILE_MATERIALIZATION_SOURCE_CHANGED"
            )
        return length


@dataclass(frozen=True, repr=False)
class OwnerMigrationFileBatch:
    plan_fingerprint: str
    target_binding_fingerprint: str
    file_count: int
    files: tuple[MaterializedMigrationFile, ...] = field(repr=False)


class OwnerMigrationFileMaterializer:
    """Bind a migration plan to owner-scoped, repeatedly verified file streams."""

    def __init__(self, source: OwnerMigrationFileSource) -> None:
        self._source = source

    def materialize(
        self,
        *,
        plan: OwnerMigrationPlanReport,
        source_owner_id: str,
        target_owner_id: str,
        target_tenant_id: str,
    ) -> OwnerMigrationFileBatch:
        self._validate_binding(
            source_owner_id, target_owner_id, target_tenant_id
        )
        expected_target = target_binding_fingerprint(
            target_owner_id, target_tenant_id
        )
        if not secrets.compare_digest(
            plan.target_binding_fingerprint, expected_target
        ):
            raise OwnerMigrationFileMaterializationError(
                "MIGRATION_FILE_MATERIALIZATION_TARGET_CHANGED"
            )
        self._validate_plan(plan)

        binding = (source_owner_id, target_owner_id, target_tenant_id)
        try:
            current_stores = self._source.inspect(
                source_owner_id=source_owner_id,
                binding=binding,
            )
        except OwnerMigrationSourceFileError as error:
            raise OwnerMigrationFileMaterializationError(
                "MIGRATION_FILE_MATERIALIZATION_SOURCE_CHANGED"
            ) from error

        current_by_store = {item.store_id: item for item in current_stores}
        planned_by_store = {item.store_id: item for item in plan.files}
        if (
            len(current_by_store) != len(current_stores)
            or len(planned_by_store) != len(plan.files)
            or set(current_by_store) != set(planned_by_store)
        ):
            self._source_changed()

        result: list[MaterializedMigrationFile] = []
        sequence = 1
        for planned_store in plan.files:
            current_store = current_by_store[planned_store.store_id]
            current_objects = {
                item.object_digest: item for item in current_store.objects
            }
            planned_objects = {
                item.object_digest: item for item in planned_store.objects
            }
            if (
                len(current_objects) != len(current_store.objects)
                or len(planned_objects) != len(planned_store.objects)
                or set(current_objects) != set(planned_objects)
                or planned_store.object_count != len(current_objects)
                or planned_store.object_set_fingerprint
                != canonical_digest(
                    [item.model_dump(mode="json") for item in planned_store.objects]
                )
            ):
                self._source_changed()
            for digest in sorted(current_objects):
                current = current_objects[digest]
                planned = planned_objects[digest]
                self._require_same_content(
                    current,
                    planned.source_checksum,
                    planned.byte_length,
                )
                result.append(
                    MaterializedMigrationFile(
                        sequence=sequence,
                        store_id=planned_store.store_id,
                        object_digest=digest,
                        source_checksum=current.source_checksum,
                        byte_length=current.byte_length,
                        _path=current.path,
                    )
                )
                sequence += 1
        if len(result) != plan.file_count:
            self._source_changed()
        return OwnerMigrationFileBatch(
            plan_fingerprint=plan.plan_fingerprint,
            target_binding_fingerprint=expected_target,
            file_count=len(result),
            files=tuple(result),
        )

    @staticmethod
    def _require_same_content(
        current: OwnerMigrationSourceFile,
        checksum: str,
        byte_length: int,
    ) -> None:
        if current.byte_length != byte_length or not secrets.compare_digest(
            current.source_checksum, checksum
        ):
            OwnerMigrationFileMaterializer._source_changed()

    @staticmethod
    def _validate_plan(plan: OwnerMigrationPlanReport) -> None:
        if (
            not secrets.compare_digest(
                plan.plan_fingerprint, migration_plan_fingerprint(plan)
            )
            or plan.object_count != sum(item.object_count for item in plan.tables)
            or plan.file_count != sum(item.object_count for item in plan.files)
        ):
            raise OwnerMigrationFileMaterializationError(
                "MIGRATION_FILE_MATERIALIZATION_PLAN_INVALID"
            )

    @staticmethod
    def _validate_binding(
        source_owner_id: str,
        target_owner_id: str,
        target_tenant_id: str,
    ) -> None:
        values = (source_owner_id, target_owner_id, target_tenant_id)
        if (
            any(not value or len(value) > 120 for value in values)
            or source_owner_id == target_owner_id
        ):
            raise OwnerMigrationFileMaterializationError(
                "MIGRATION_FILE_MATERIALIZATION_BINDING_INVALID"
            )

    @staticmethod
    def _source_changed() -> NoReturn:
        raise OwnerMigrationFileMaterializationError(
            "MIGRATION_FILE_MATERIALIZATION_SOURCE_CHANGED"
        )
