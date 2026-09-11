from __future__ import annotations

import hashlib
import json
import math


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


def target_binding_fingerprint(
    target_owner_id: str,
    target_tenant_id: str,
) -> str:
    return canonical_digest(
        ("m14-target-binding-v1", target_owner_id, target_tenant_id)
    )


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
