from __future__ import annotations

from typing import Any

import pytest

from app.modules.tenant_migration import (
    POSTGRES_OWNER_MIGRATION_SCHEMA_VERSION,
    PostgresOwnerMigrationSchema,
    PostgresOwnerMigrationSchemaError,
)
from app.modules.tenant_migration.postgres_schema import (
    POSTGRES_OWNER_MIGRATION_SCHEMA_STATEMENTS,
)


class _Cursor:
    def __init__(self, row: dict[str, Any] | None = None) -> None:
        self._row = row

    def fetchone(self) -> dict[str, Any] | None:
        return self._row


class _Connection:
    def __init__(self, execute) -> None:
        self._execute = execute

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def execute(self, query: str, params=None) -> _Cursor:
        return self._execute(query, params)


def test_schema_requires_preview_fingerprint_and_explicit_confirmation() -> None:
    state = {"installed": False, "writes": 0, "connections": 0}

    def execute(query: str, params) -> _Cursor:
        normalized = " ".join(query.split())
        if normalized.startswith("SELECT to_regclass"):
            marker = "schema_versions" if state["installed"] else None
            return _Cursor({"metadata_table": marker})
        if "information_schema.tables" in normalized:
            return _Cursor({"table_count": 0})
        if normalized.startswith("SELECT schema_version"):
            return _Cursor(
                {"schema_version": POSTGRES_OWNER_MIGRATION_SCHEMA_VERSION}
            )
        if "WHERE FALSE" in normalized:
            return _Cursor()
        if normalized.startswith("SELECT pg_advisory_xact_lock"):
            return _Cursor()
        state["writes"] += 1
        if normalized.startswith("INSERT INTO") and "schema_versions" in normalized:
            state["installed"] = True
        return _Cursor()

    def connect() -> _Connection:
        state["connections"] += 1
        return _Connection(execute)

    schema = PostgresOwnerMigrationSchema(
        connect=connect  # type: ignore[arg-type]
    )
    assert state["connections"] == 0
    plan = schema.preview()
    assert plan.state == "empty"
    assert plan.changed is False
    assert len(plan.fingerprint) == 64
    assert state["writes"] == 0

    with pytest.raises(
        PostgresOwnerMigrationSchemaError,
        match="POSTGRES_OWNER_MIGRATION_SCHEMA_CONFIRMATION_REQUIRED",
    ):
        schema.apply(expected_fingerprint=plan.fingerprint)
    with pytest.raises(
        PostgresOwnerMigrationSchemaError,
        match="POSTGRES_OWNER_MIGRATION_SCHEMA_PLAN_CHANGED",
    ):
        schema.apply(expected_fingerprint="0" * 64, confirmed=True)
    assert state["writes"] == 0

    applied = schema.apply(expected_fingerprint=plan.fingerprint, confirmed=True)
    assert applied.changed is True
    assert state["writes"] == plan.statement_count

    current = schema.apply(expected_fingerprint=plan.fingerprint, confirmed=True)
    assert current.state == "current"
    assert current.changed is False
    assert state["writes"] == plan.statement_count


def test_schema_refuses_an_unknown_existing_target() -> None:
    writes = 0

    def execute(query: str, params) -> _Cursor:
        nonlocal writes
        normalized = " ".join(query.split())
        if normalized.startswith("SELECT to_regclass"):
            return _Cursor({"metadata_table": None})
        if "information_schema.tables" in normalized:
            return _Cursor({"table_count": 1})
        if normalized.startswith("SELECT pg_advisory_xact_lock"):
            return _Cursor()
        writes += 1
        return _Cursor()

    schema = PostgresOwnerMigrationSchema(
        connect=lambda: _Connection(execute)  # type: ignore[arg-type]
    )
    plan = schema.preview()
    assert plan.state == "unexpected"
    with pytest.raises(
        PostgresOwnerMigrationSchemaError,
        match="POSTGRES_OWNER_MIGRATION_SCHEMA_UNEXPECTED",
    ):
        schema.apply(expected_fingerprint=plan.fingerprint, confirmed=True)
    assert writes == 0


def test_schema_is_target_bound_without_persisting_source_owner_identity() -> None:
    sql = "\n".join(POSTGRES_OWNER_MIGRATION_SCHEMA_STATEMENTS)

    assert "target_tenant_id" in sql
    assert "target_owner_id" in sql
    assert "target_binding_fingerprint" in sql
    assert "dependency_digests JSONB" in sql
    assert "payload_json JSONB" in sql
    assert "source_checksum" in sql
    assert "staged_storage_key" in sql
    assert "published_storage_key" in sql
    assert "source_owner_id" not in sql


def test_schema_errors_are_stable_and_do_not_echo_connection_details() -> None:
    with pytest.raises(
        PostgresOwnerMigrationSchemaError,
        match="POSTGRES_OWNER_MIGRATION_DSN_REQUIRED",
    ):
        PostgresOwnerMigrationSchema.from_dsn("  ")

    secret = "postgresql://owner:secret@example.invalid/app"

    def fail_connect() -> _Connection:
        raise RuntimeError(secret)

    schema = PostgresOwnerMigrationSchema(
        connect=fail_connect  # type: ignore[arg-type]
    )
    with pytest.raises(PostgresOwnerMigrationSchemaError) as caught:
        schema.preview()
    assert str(caught.value) == "POSTGRES_OWNER_MIGRATION_TARGET_UNAVAILABLE"
    assert secret not in str(caught.value)
