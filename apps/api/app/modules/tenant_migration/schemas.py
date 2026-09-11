from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class OwnerDataTableInventory(BaseModel):
    table_name: str = Field(pattern=r"^[a-z][a-z0-9_]{1,79}$")
    ownership: Literal["direct", "inherited", "legacy_unowned"]
    total_rows: int = Field(ge=0)
    matching_owner_rows: int | None = Field(default=None, ge=0)


class OwnerDataStoreInventory(BaseModel):
    store_id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    kind: Literal["sqlite", "directory"]
    status: Literal["ready", "missing", "blocked"]
    migration_ready: bool
    tables: tuple[OwnerDataTableInventory, ...] = ()
    file_count: int = Field(default=0, ge=0)
    issues: tuple[str, ...] = ()


class OwnerDataInventoryReport(BaseModel):
    schema_version: Literal[1] = 1
    scope: Literal["requested_owner"] = "requested_owner"
    store_count: int = Field(ge=0)
    ready_store_count: int = Field(ge=0)
    blocked_store_count: int = Field(ge=0)
    missing_store_count: int = Field(ge=0)
    matching_owner_rows: int = Field(ge=0)
    migration_ready: bool
    report_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    stores: tuple[OwnerDataStoreInventory, ...]


class OwnerFileStoreReconciliation(BaseModel):
    store_id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    status: Literal["ready", "missing", "blocked"]
    migration_ready: bool
    referenced_files: int = Field(ge=0)
    present_files: int = Field(ge=0)
    missing_files: int = Field(ge=0)
    orphaned_files: int = Field(ge=0)
    cross_owner_collisions: int = Field(ge=0)
    unresolved_owner_references: int = Field(ge=0)
    evidence_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    issues: tuple[str, ...] = ()


class OwnerFileReconciliationReport(BaseModel):
    schema_version: Literal[1] = 1
    scope: Literal["requested_owner"] = "requested_owner"
    store_count: int = Field(ge=0)
    ready_store_count: int = Field(ge=0)
    blocked_store_count: int = Field(ge=0)
    missing_store_count: int = Field(ge=0)
    referenced_files: int = Field(ge=0)
    present_files: int = Field(ge=0)
    migration_ready: bool
    report_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    stores: tuple[OwnerFileStoreReconciliation, ...]


class OwnerMigrationObjectPlan(BaseModel):
    object_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_record_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    dependency_digests: tuple[str, ...] = ()


class OwnerMigrationTablePlan(BaseModel):
    store_id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    table_name: str = Field(pattern=r"^[a-z][a-z0-9_]{1,79}$")
    ownership: Literal["direct", "inherited"]
    sequence: int = Field(ge=1)
    object_count: int = Field(ge=0)
    object_set_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    objects: tuple[OwnerMigrationObjectPlan, ...]


class OwnerMigrationFilePlan(BaseModel):
    store_id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    sequence: int = Field(ge=1)
    object_count: int = Field(ge=0)
    object_set_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    object_digests: tuple[str, ...]


class OwnerMigrationPlanReport(BaseModel):
    schema_version: Literal[1] = 1
    scope: Literal["requested_owner"] = "requested_owner"
    execution_allowed: Literal[False] = False
    migration_ready: Literal[True] = True
    source_inventory_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_file_reconciliation_fingerprint: str = Field(
        pattern=r"^[0-9a-f]{64}$"
    )
    target_binding_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    object_count: int = Field(ge=0)
    file_count: int = Field(ge=0)
    plan_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    tables: tuple[OwnerMigrationTablePlan, ...]
    files: tuple[OwnerMigrationFilePlan, ...]


class OwnerMigrationTargetState(BaseModel):
    state: Literal["empty", "in_progress", "complete", "unexpected"]
    target_binding_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    plan_fingerprint: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )


class OwnerMigrationTargetReconciliation(BaseModel):
    plan_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    object_count: int = Field(ge=0)
    file_count: int = Field(ge=0)
    object_set_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    file_set_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class OwnerMigrationExecutionReceipt(BaseModel):
    schema_version: Literal[1] = 1
    outcome: Literal["applied", "already_applied"]
    plan_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    target_binding_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    object_count: int = Field(ge=0)
    file_count: int = Field(ge=0)
    reconciled: Literal[True] = True
