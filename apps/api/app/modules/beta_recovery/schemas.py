from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


BackupSourceKind = Literal["sqlite", "directory"]
BackupSourceStatus = Literal["ready", "missing"]


class BackupInventoryItem(BaseModel):
    store_id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    kind: BackupSourceKind
    status: BackupSourceStatus
    file_count: int = Field(ge=0)


class BackupFileRecord(BaseModel):
    relative_path: str = Field(min_length=1, max_length=500)
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class BackupStoreRecord(BaseModel):
    store_id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    kind: BackupSourceKind
    status: Literal["captured", "missing"]
    files: list[BackupFileRecord]


class BackupManifest(BaseModel):
    schema_version: Literal[1] = 1
    backup_id: str = Field(pattern=r"^backup_[0-9a-f]{32}$")
    created_at: datetime
    stores: list[BackupStoreRecord]


class BackupVerification(BaseModel):
    backup_id: str
    status: Literal["verified"] = "verified"
    store_count: int = Field(ge=0)
    file_count: int = Field(ge=0)
    total_bytes: int = Field(ge=0)


class RestoreDrillReport(BaseModel):
    backup_id: str
    status: Literal["restored_and_verified"] = "restored_and_verified"
    store_count: int = Field(ge=0)
    file_count: int = Field(ge=0)
    sqlite_integrity_checks: int = Field(ge=0)
    suppressed_deletions: int = Field(default=0, ge=0)
    total_bytes: int = Field(ge=0)


class BackupRetentionPreview(BaseModel):
    retention_days: Literal[30] = 30
    evaluated_at: datetime
    cutoff_at: datetime
    retained_backups: int = Field(ge=0)
    expired_backups: int = Field(ge=0)
    unclassifiable_entries: int = Field(ge=0)


class BackupRetentionResult(BackupRetentionPreview):
    deleted_backups: int = Field(ge=0)
