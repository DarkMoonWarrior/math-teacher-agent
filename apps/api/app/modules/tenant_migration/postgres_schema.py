from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Protocol


POSTGRES_OWNER_MIGRATION_SCHEMA = "math_teacher_content_migration"
POSTGRES_OWNER_MIGRATION_SCHEMA_VERSION = "m14.owner_migration.v1"
_SCHEMA_TABLE = f"{POSTGRES_OWNER_MIGRATION_SCHEMA}.schema_versions"
_RUNS = f"{POSTGRES_OWNER_MIGRATION_SCHEMA}.owner_migration_runs"
_OBJECTS = f"{POSTGRES_OWNER_MIGRATION_SCHEMA}.owner_migration_objects"
_FILES = f"{POSTGRES_OWNER_MIGRATION_SCHEMA}.owner_migration_files"


class _Cursor(Protocol):
    def fetchone(self) -> Mapping[str, Any] | None: ...


class _Connection(Protocol):
    def __enter__(self) -> "_Connection": ...

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None: ...

    def execute(
        self,
        query: str,
        params: Sequence[Any] | None = None,
    ) -> _Cursor: ...


Connect = Callable[[], _Connection]


def _psycopg_connect(dsn: str) -> _Connection:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as error:
        raise PostgresOwnerMigrationSchemaError(
            "POSTGRES_OWNER_MIGRATION_DRIVER_UNAVAILABLE"
        ) from error
    try:
        return psycopg.connect(dsn, row_factory=dict_row)
    except Exception as error:
        raise PostgresOwnerMigrationSchemaError(
            "POSTGRES_OWNER_MIGRATION_CONNECTION_UNAVAILABLE"
        ) from error


POSTGRES_OWNER_MIGRATION_SCHEMA_STATEMENTS = (
    f"CREATE SCHEMA IF NOT EXISTS {POSTGRES_OWNER_MIGRATION_SCHEMA}",
    f"""CREATE TABLE IF NOT EXISTS {_SCHEMA_TABLE} (
        component TEXT PRIMARY KEY,
        schema_version TEXT NOT NULL,
        installed_at TIMESTAMPTZ NOT NULL
    )""",
    f"""CREATE TABLE IF NOT EXISTS {_RUNS} (
        plan_fingerprint TEXT PRIMARY KEY,
        target_binding_fingerprint TEXT NOT NULL,
        target_tenant_id TEXT NOT NULL,
        target_owner_id TEXT NOT NULL,
        status TEXT NOT NULL CHECK (
            status IN ('in_progress', 'complete', 'rolled_back')
        ),
        object_count INTEGER NOT NULL CHECK (object_count >= 0),
        file_count INTEGER NOT NULL CHECK (file_count >= 0),
        created_at TIMESTAMPTZ NOT NULL,
        completed_at TIMESTAMPTZ,
        UNIQUE (target_tenant_id, target_owner_id, plan_fingerprint)
    )""",
    f"""CREATE TABLE IF NOT EXISTS {_OBJECTS} (
        plan_fingerprint TEXT NOT NULL REFERENCES {_RUNS}(plan_fingerprint),
        target_tenant_id TEXT NOT NULL,
        target_owner_id TEXT NOT NULL,
        sequence INTEGER NOT NULL CHECK (sequence >= 1),
        store_id TEXT NOT NULL,
        table_name TEXT NOT NULL,
        object_digest TEXT NOT NULL,
        source_record_fingerprint TEXT NOT NULL,
        dependency_digests JSONB NOT NULL,
        payload_json JSONB NOT NULL,
        PRIMARY KEY (plan_fingerprint, object_digest)
    )""",
    f"""CREATE TABLE IF NOT EXISTS {_FILES} (
        plan_fingerprint TEXT NOT NULL REFERENCES {_RUNS}(plan_fingerprint),
        target_tenant_id TEXT NOT NULL,
        target_owner_id TEXT NOT NULL,
        sequence INTEGER NOT NULL CHECK (sequence >= 1),
        store_id TEXT NOT NULL,
        object_digest TEXT NOT NULL,
        source_checksum TEXT NOT NULL,
        byte_length BIGINT NOT NULL CHECK (byte_length >= 0),
        staged_storage_key TEXT NOT NULL,
        published_storage_key TEXT,
        PRIMARY KEY (plan_fingerprint, object_digest)
    )""",
    f"""CREATE INDEX IF NOT EXISTS owner_migration_runs_target_idx
        ON {_RUNS} (target_tenant_id, target_owner_id, created_at)""",
    f"""CREATE INDEX IF NOT EXISTS owner_migration_objects_target_idx
        ON {_OBJECTS} (target_tenant_id, target_owner_id, store_id, table_name)""",
    f"""CREATE INDEX IF NOT EXISTS owner_migration_files_target_idx
        ON {_FILES} (target_tenant_id, target_owner_id, store_id)""",
    f"""INSERT INTO {_SCHEMA_TABLE}
        (component, schema_version, installed_at)
        VALUES ('owner_migration', %s, %s)
        ON CONFLICT (component) DO NOTHING""",
)


class PostgresOwnerMigrationSchemaError(ValueError):
    """Stable operator error that never includes the target DSN."""


@dataclass(frozen=True)
class PostgresOwnerMigrationSchemaPlan:
    state: str
    schema_version: str
    statement_count: int
    fingerprint: str
    changed: bool = False


class PostgresOwnerMigrationSchema:
    """Deploy the fixed landing schema only through preview and confirmation."""

    _ADVISORY_LOCK = 1414002

    def __init__(self, *, connect: Connect) -> None:
        self._connect = connect

    @classmethod
    def from_dsn(cls, dsn: str) -> "PostgresOwnerMigrationSchema":
        if not dsn.strip():
            raise PostgresOwnerMigrationSchemaError(
                "POSTGRES_OWNER_MIGRATION_DSN_REQUIRED"
            )
        return cls(connect=lambda: _psycopg_connect(dsn))

    @staticmethod
    def _fingerprint() -> str:
        payload = "\n".join(POSTGRES_OWNER_MIGRATION_SCHEMA_STATEMENTS).encode(
            "utf-8"
        )
        return hashlib.sha256(payload).hexdigest()

    def preview(self) -> PostgresOwnerMigrationSchemaPlan:
        try:
            with self._connect() as connection:
                state = _schema_state(connection)
        except PostgresOwnerMigrationSchemaError:
            raise
        except Exception as error:
            raise PostgresOwnerMigrationSchemaError(
                "POSTGRES_OWNER_MIGRATION_TARGET_UNAVAILABLE"
            ) from error
        return self._plan(state)

    def apply(
        self,
        *,
        expected_fingerprint: str,
        confirmed: bool = False,
    ) -> PostgresOwnerMigrationSchemaPlan:
        if confirmed is not True:
            raise PostgresOwnerMigrationSchemaError(
                "POSTGRES_OWNER_MIGRATION_SCHEMA_CONFIRMATION_REQUIRED"
            )
        if expected_fingerprint != self._fingerprint():
            raise PostgresOwnerMigrationSchemaError(
                "POSTGRES_OWNER_MIGRATION_SCHEMA_PLAN_CHANGED"
            )
        try:
            with self._connect() as connection:
                connection.execute(
                    "SELECT pg_advisory_xact_lock(%s)",
                    (self._ADVISORY_LOCK,),
                )
                state = _schema_state(connection)
                plan = self._plan(state)
                if state == "unexpected":
                    raise PostgresOwnerMigrationSchemaError(
                        "POSTGRES_OWNER_MIGRATION_SCHEMA_UNEXPECTED"
                    )
                if state == "current":
                    return plan
                now = datetime.now(timezone.utc)
                for statement in POSTGRES_OWNER_MIGRATION_SCHEMA_STATEMENTS[:-1]:
                    connection.execute(statement)
                connection.execute(
                    POSTGRES_OWNER_MIGRATION_SCHEMA_STATEMENTS[-1],
                    (POSTGRES_OWNER_MIGRATION_SCHEMA_VERSION, now),
                )
        except PostgresOwnerMigrationSchemaError:
            raise
        except Exception as error:
            raise PostgresOwnerMigrationSchemaError(
                "POSTGRES_OWNER_MIGRATION_SCHEMA_APPLY_FAILED"
            ) from error
        return replace(plan, changed=True)

    @classmethod
    def _plan(cls, state: str) -> PostgresOwnerMigrationSchemaPlan:
        return PostgresOwnerMigrationSchemaPlan(
            state=state,
            schema_version=POSTGRES_OWNER_MIGRATION_SCHEMA_VERSION,
            statement_count=len(POSTGRES_OWNER_MIGRATION_SCHEMA_STATEMENTS),
            fingerprint=cls._fingerprint(),
        )


def _schema_state(connection: _Connection) -> str:
    marker = connection.execute(
        "SELECT to_regclass(%s) AS metadata_table",
        (f"{POSTGRES_OWNER_MIGRATION_SCHEMA}.schema_versions",),
    ).fetchone()
    if marker is None or marker.get("metadata_table") is None:
        count = connection.execute(
            "SELECT COUNT(*) AS table_count FROM information_schema.tables "
            "WHERE table_schema = %s",
            (POSTGRES_OWNER_MIGRATION_SCHEMA,),
        ).fetchone()
        return (
            "empty"
            if count is not None and count.get("table_count") == 0
            else "unexpected"
        )
    version = connection.execute(
        f"SELECT schema_version FROM {_SCHEMA_TABLE} WHERE component = %s",
        ("owner_migration",),
    ).fetchone()
    if (
        version is None
        or version.get("schema_version")
        != POSTGRES_OWNER_MIGRATION_SCHEMA_VERSION
    ):
        return "unexpected"
    try:
        _validate_schema_shape(connection)
    except Exception:
        return "unexpected"
    return "current"


def _validate_schema_shape(connection: _Connection) -> None:
    connection.execute(
        f"""SELECT plan_fingerprint, target_binding_fingerprint,
        target_tenant_id, target_owner_id, status, object_count, file_count,
        created_at, completed_at FROM {_RUNS} WHERE FALSE"""
    )
    connection.execute(
        f"""SELECT plan_fingerprint, target_tenant_id, target_owner_id,
        sequence, store_id, table_name, object_digest,
        source_record_fingerprint, dependency_digests, payload_json
        FROM {_OBJECTS} WHERE FALSE"""
    )
    connection.execute(
        f"""SELECT plan_fingerprint, target_tenant_id, target_owner_id,
        sequence, store_id, object_digest, source_checksum, byte_length,
        staged_storage_key, published_storage_key FROM {_FILES} WHERE FALSE"""
    )
