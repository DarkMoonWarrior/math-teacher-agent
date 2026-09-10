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
