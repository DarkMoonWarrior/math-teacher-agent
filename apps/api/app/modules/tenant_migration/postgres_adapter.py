from __future__ import annotations

import json
import re
import secrets
from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager, contextmanager
from datetime import datetime, timezone
from typing import Any, Protocol

from app.modules.tenant_migration.execution import (
    OwnerMigrationExecutionError,
    migration_set_fingerprint,
)
from app.modules.tenant_migration.file_materialization import (
    MaterializedMigrationFile,
    OwnerMigrationFileBatch,
)
from app.modules.tenant_migration.fingerprints import target_binding_fingerprint
from app.modules.tenant_migration.materialization import OwnerMigrationObjectBatch
from app.modules.tenant_migration.postgres_schema import (
    POSTGRES_OWNER_MIGRATION_SCHEMA,
)
from app.modules.tenant_migration.schemas import (
    OwnerMigrationPlanReport,
    OwnerMigrationTargetReconciliation,
    OwnerMigrationTargetState,
)


_RUNS = f"{POSTGRES_OWNER_MIGRATION_SCHEMA}.owner_migration_runs"
_OBJECTS = f"{POSTGRES_OWNER_MIGRATION_SCHEMA}.owner_migration_objects"
_FILES = f"{POSTGRES_OWNER_MIGRATION_SCHEMA}.owner_migration_files"


class PostgresOwnerMigrationAdapterError(ValueError):
    """Stable target adapter failure without private migration content."""


class _Cursor(Protocol):
    @property
    def rowcount(self) -> int: ...

    def fetchone(self) -> Mapping[str, Any] | None: ...

    def fetchall(self) -> Sequence[Mapping[str, Any]]: ...


class _Connection(Protocol):
    def __enter__(self) -> "_Connection": ...

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None: ...

    def execute(
        self,
        query: str,
        params: Sequence[Any] | None = None,
    ) -> _Cursor: ...


class _ObjectMaterializer(Protocol):
    def materialize(self, **kwargs: object) -> OwnerMigrationObjectBatch: ...


class _FileMaterializer(Protocol):
    def materialize(self, **kwargs: object) -> OwnerMigrationFileBatch: ...


class OwnerMigrationFileStagingTransaction(Protocol):
    def stage(self, item: MaterializedMigrationFile) -> str: ...

    def publish(self) -> Mapping[str, str]: ...


class OwnerMigrationFileStaging(Protocol):
    def transaction(
        self, *, plan_fingerprint: str
    ) -> AbstractContextManager[OwnerMigrationFileStagingTransaction]: ...


Connect = Callable[[], _Connection]


def _psycopg_connect(dsn: str) -> _Connection:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as error:
        raise PostgresOwnerMigrationAdapterError(
            "POSTGRES_OWNER_MIGRATION_DRIVER_UNAVAILABLE"
        ) from error
    try:
        return psycopg.connect(dsn, row_factory=dict_row)
    except Exception as error:
        raise PostgresOwnerMigrationAdapterError(
            "POSTGRES_OWNER_MIGRATION_CONNECTION_UNAVAILABLE"
        ) from error


class PostgresOwnerMigrationAdapter:
    """Apply target-bound payloads through one PostgreSQL/file transaction seam."""

    _FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")

    def __init__(
        self,
        *,
        connect: Connect,
        object_materializer: _ObjectMaterializer,
        file_materializer: _FileMaterializer,
        file_staging: OwnerMigrationFileStaging,
        source_owner_id: str,
        target_owner_id: str,
        target_tenant_id: str,
    ) -> None:
        values = (source_owner_id, target_owner_id, target_tenant_id)
        if (
            any(not value or len(value) > 120 for value in values)
            or source_owner_id == target_owner_id
        ):
            raise PostgresOwnerMigrationAdapterError(
                "POSTGRES_OWNER_MIGRATION_BINDING_INVALID"
            )
        self._connect = connect
        self._objects = object_materializer
        self._files = file_materializer
        self._file_staging = file_staging
        self._source_owner_id = source_owner_id
        self._target_owner_id = target_owner_id
        self._target_tenant_id = target_tenant_id
        self._target_binding = target_binding_fingerprint(
            target_owner_id, target_tenant_id
        )

    @classmethod
    def from_dsn(cls, *, dsn: str, **kwargs: object) -> "PostgresOwnerMigrationAdapter":
        if not dsn.strip():
            raise PostgresOwnerMigrationAdapterError(
                "POSTGRES_OWNER_MIGRATION_DSN_REQUIRED"
            )
        return cls(connect=lambda: _psycopg_connect(dsn), **kwargs)  # type: ignore[arg-type]

    @contextmanager
    def transaction(
        self,
        *,
        target_binding_fingerprint: str,
        plan_fingerprint: str,
    ):
        if (
            not self._FINGERPRINT.fullmatch(target_binding_fingerprint)
            or not self._FINGERPRINT.fullmatch(plan_fingerprint)
            or not secrets.compare_digest(
                target_binding_fingerprint, self._target_binding
            )
        ):
            raise PostgresOwnerMigrationAdapterError(
                "POSTGRES_OWNER_MIGRATION_TARGET_CHANGED"
            )
        try:
            with self._file_staging.transaction(
                plan_fingerprint=plan_fingerprint
            ) as file_transaction:
                with self._connect() as connection:
                    connection.execute(
                        "SELECT pg_advisory_xact_lock(%s)",
                        (_target_lock_key(target_binding_fingerprint),),
                    )
                    yield _PostgresOwnerMigrationTransaction(
                        connection=connection,
                        file_transaction=file_transaction,
                        plan_fingerprint=plan_fingerprint,
                        target_binding_fingerprint=target_binding_fingerprint,
                        source_owner_id=self._source_owner_id,
                        target_owner_id=self._target_owner_id,
                        target_tenant_id=self._target_tenant_id,
                        object_materializer=self._objects,
                        file_materializer=self._files,
                    )
        except (OwnerMigrationExecutionError, PostgresOwnerMigrationAdapterError):
            raise
        except Exception as error:
            raise PostgresOwnerMigrationAdapterError(
                "POSTGRES_OWNER_MIGRATION_TRANSACTION_FAILED"
            ) from error


class _PostgresOwnerMigrationTransaction:
    def __init__(
        self,
        *,
        connection: _Connection,
        file_transaction: OwnerMigrationFileStagingTransaction,
        plan_fingerprint: str,
        target_binding_fingerprint: str,
        source_owner_id: str,
        target_owner_id: str,
        target_tenant_id: str,
        object_materializer: _ObjectMaterializer,
        file_materializer: _FileMaterializer,
    ) -> None:
        self._connection = connection
        self._file_transaction = file_transaction
        self._plan_fingerprint = plan_fingerprint
        self._target_binding_fingerprint = target_binding_fingerprint
        self._source_owner_id = source_owner_id
        self._target_owner_id = target_owner_id
        self._target_tenant_id = target_tenant_id
        self._objects = object_materializer
        self._files = file_materializer
        self._staged: dict[str, str] = {}

    def inspect(self) -> OwnerMigrationTargetState:
        exact = self._connection.execute(
            f"SELECT target_binding_fingerprint, status FROM {_RUNS} "
            "WHERE plan_fingerprint = %s",
            (self._plan_fingerprint,),
        ).fetchone()
        if exact is not None:
            return OwnerMigrationTargetState(
                state=self._state(exact.get("status")),
                target_binding_fingerprint=str(
                    exact.get("target_binding_fingerprint", "")
                ),
                plan_fingerprint=self._plan_fingerprint,
            )
        related = self._connection.execute(
            f"SELECT plan_fingerprint FROM {_RUNS} "
            "WHERE target_binding_fingerprint = %s "
            "AND status IN ('in_progress', 'complete') LIMIT 2",
            (self._target_binding_fingerprint,),
        ).fetchall()
        if related:
            return OwnerMigrationTargetState(
                state="unexpected",
                target_binding_fingerprint=self._target_binding_fingerprint,
                plan_fingerprint=None,
            )
        return OwnerMigrationTargetState(
            state="empty",
            target_binding_fingerprint=self._target_binding_fingerprint,
        )

    def apply(self, plan: OwnerMigrationPlanReport) -> None:
        objects = self._objects.materialize(
            plan=plan,
            source_owner_id=self._source_owner_id,
            target_owner_id=self._target_owner_id,
            target_tenant_id=self._target_tenant_id,
        )
        files = self._files.materialize(
            plan=plan,
            source_owner_id=self._source_owner_id,
            target_owner_id=self._target_owner_id,
            target_tenant_id=self._target_tenant_id,
        )
        if (
            objects.plan_fingerprint != plan.plan_fingerprint
            or objects.target_binding_fingerprint != plan.target_binding_fingerprint
            or objects.object_count != plan.object_count
            or files.plan_fingerprint != plan.plan_fingerprint
            or files.target_binding_fingerprint != plan.target_binding_fingerprint
            or files.file_count != plan.file_count
        ):
            raise PostgresOwnerMigrationAdapterError(
                "POSTGRES_OWNER_MIGRATION_MATERIALIZATION_MISMATCH"
            )
        for item in files.files:
            key = self._file_transaction.stage(item)
            if not key or len(key) > 500 or item.object_digest in self._staged:
                raise PostgresOwnerMigrationAdapterError(
                    "POSTGRES_OWNER_MIGRATION_FILE_STAGE_FAILED"
                )
            self._staged[item.object_digest] = key

        now = datetime.now(timezone.utc)
        self._connection.execute(
            f"INSERT INTO {_RUNS} (plan_fingerprint, "
            "target_binding_fingerprint, target_tenant_id, target_owner_id, "
            "status, object_count, file_count, created_at, completed_at) "
            "VALUES (%s, %s, %s, %s, 'in_progress', %s, %s, %s, NULL)",
            (
                plan.plan_fingerprint,
                plan.target_binding_fingerprint,
                self._target_tenant_id,
                self._target_owner_id,
                plan.object_count,
                plan.file_count,
                now,
            ),
        )
        for item in objects.objects:
            self._connection.execute(
                f"INSERT INTO {_OBJECTS} (plan_fingerprint, target_tenant_id, "
                "target_owner_id, sequence, store_id, table_name, object_digest, "
                "source_record_fingerprint, dependency_digests, payload_json) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)",
                (
                    plan.plan_fingerprint,
                    self._target_tenant_id,
                    self._target_owner_id,
                    item.sequence,
                    item.store_id,
                    item.table_name,
                    item.object_digest,
                    item.source_record_fingerprint,
                    json.dumps(item.dependency_digests),
                    item.payload_json,
                ),
            )
        for item in files.files:
            self._connection.execute(
                f"INSERT INTO {_FILES} (plan_fingerprint, target_tenant_id, "
                "target_owner_id, sequence, store_id, object_digest, "
                "source_checksum, byte_length, staged_storage_key, "
                "published_storage_key) VALUES (%s, %s, %s, %s, %s, %s, %s, "
                "%s, %s, NULL)",
                (
                    plan.plan_fingerprint,
                    self._target_tenant_id,
                    self._target_owner_id,
                    item.sequence,
                    item.store_id,
                    item.object_digest,
                    item.source_checksum,
                    item.byte_length,
                    self._staged[item.object_digest],
                ),
            )

    def reconcile(self) -> OwnerMigrationTargetReconciliation:
        object_rows = self._connection.execute(
            f"SELECT object_digest FROM {_OBJECTS} WHERE plan_fingerprint = %s",
            (self._plan_fingerprint,),
        ).fetchall()
        file_rows = self._connection.execute(
            f"SELECT object_digest FROM {_FILES} WHERE plan_fingerprint = %s",
            (self._plan_fingerprint,),
        ).fetchall()
        objects = tuple(str(row["object_digest"]) for row in object_rows)
        files = tuple(str(row["object_digest"]) for row in file_rows)
        return OwnerMigrationTargetReconciliation(
            plan_fingerprint=self._plan_fingerprint,
            object_count=len(objects),
            file_count=len(files),
            object_set_fingerprint=migration_set_fingerprint(
                "m14-target-objects-v1", objects
            ),
            file_set_fingerprint=migration_set_fingerprint(
                "m14-target-files-v1", files
            ),
        )

    def mark_complete(self) -> None:
        published = dict(self._file_transaction.publish())
        if set(published) != set(self._staged) or any(
            not key or len(key) > 500 for key in published.values()
        ):
            raise PostgresOwnerMigrationAdapterError(
                "POSTGRES_OWNER_MIGRATION_FILE_PUBLISH_FAILED"
            )
        for digest, key in published.items():
            cursor = self._connection.execute(
                f"UPDATE {_FILES} SET published_storage_key = %s "
                "WHERE plan_fingerprint = %s AND object_digest = %s "
                "AND published_storage_key IS NULL",
                (key, self._plan_fingerprint, digest),
            )
            if cursor.rowcount != 1:
                raise PostgresOwnerMigrationAdapterError(
                    "POSTGRES_OWNER_MIGRATION_FILE_PUBLISH_FAILED"
                )
        cursor = self._connection.execute(
            f"UPDATE {_RUNS} SET status = 'complete', completed_at = %s "
            "WHERE plan_fingerprint = %s AND target_binding_fingerprint = %s "
            "AND status = 'in_progress'",
            (
                datetime.now(timezone.utc),
                self._plan_fingerprint,
                self._target_binding_fingerprint,
            ),
        )
        if cursor.rowcount != 1:
            raise PostgresOwnerMigrationAdapterError(
                "POSTGRES_OWNER_MIGRATION_COMPLETE_FAILED"
            )

    @staticmethod
    def _state(value: object) -> str:
        if value in {"in_progress", "complete"}:
            return str(value)
        return "unexpected"


def _target_lock_key(binding_fingerprint: str) -> int:
    unsigned = int(binding_fingerprint[:16], 16)
    return unsigned if unsigned < (1 << 63) else unsigned - (1 << 64)
