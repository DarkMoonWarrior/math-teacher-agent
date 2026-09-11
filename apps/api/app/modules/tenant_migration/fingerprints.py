from __future__ import annotations

import hashlib
import json
import math

from app.modules.tenant_migration.schemas import OwnerMigrationPlanReport


class OwnerMigrationFingerprintError(ValueError):
    """A migration fingerprint input cannot be represented canonically."""


def canonical_digest(value: object) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def migration_plan_fingerprint(plan: OwnerMigrationPlanReport) -> str:
    """Recompute the digest-covered portion of an immutable migration plan."""
    return canonical_digest(
        {
            "schema_version": plan.schema_version,
            "source_inventory_fingerprint": plan.source_inventory_fingerprint,
            "source_file_reconciliation_fingerprint": (
                plan.source_file_reconciliation_fingerprint
            ),
            "target_binding_fingerprint": plan.target_binding_fingerprint,
            "tables": [table.model_dump(mode="json") for table in plan.tables],
            "files": [item.model_dump(mode="json") for item in plan.files],
        }
    )


def target_binding_fingerprint(
    target_owner_id: str,
    target_tenant_id: str,
) -> str:
    return canonical_digest(
        ("m14-target-binding-v1", target_owner_id, target_tenant_id)
    )


def target_advisory_lock_key(binding_fingerprint: str) -> int:
    """Map a validated SHA-256 binding to PostgreSQL's signed bigint lock key."""
    unsigned = int(binding_fingerprint[:16], 16)
    return unsigned if unsigned < (1 << 63) else unsigned - (1 << 64)


def owner_object_digest(
    binding: tuple[str, str, str],
    store_id: str,
    table_name: str,
    key: tuple[object, ...],
) -> str:
    return canonical_digest(
        (
            "m14-owner-object-v1",
            *binding,
            store_id,
            table_name,
            key,
        )
    )


def owner_file_digest(
    binding: tuple[str, str, str],
    store_id: str,
    reference: str,
) -> str:
    return canonical_digest(
        ("m14-owner-file-v1", *binding, store_id, reference)
    )


def canonical_sqlite_value(value: object) -> object:
    if isinstance(value, bytes):
        return {
            "blob_sha256": hashlib.sha256(value).hexdigest(),
            "byte_length": len(value),
        }
    if value is None or isinstance(value, (str, int)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    raise OwnerMigrationFingerprintError("MIGRATION_RECORD_VALUE_INVALID")


def source_record_fingerprint(
    binding: tuple[str, str, str],
    store_id: str,
    table_name: str,
    columns: tuple[str, ...],
    row: tuple[object, ...],
) -> str:
    record = tuple(canonical_sqlite_value(value) for value in row)
    return canonical_digest(
        (
            "m14-source-record-v1",
            *binding,
            store_id,
            table_name,
            columns,
            record,
        )
    )
