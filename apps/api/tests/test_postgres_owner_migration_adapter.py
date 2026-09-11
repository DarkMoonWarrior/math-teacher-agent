from __future__ import annotations

import hashlib
import io
from contextlib import AbstractContextManager
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from app.modules.tenant_migration.execution import (
    OwnerMigrationExecutionError,
    OwnerMigrationExecutor,
)
from app.modules.tenant_migration.file_materialization import (
    MaterializedMigrationFile,
    OwnerMigrationFileBatch,
)
from app.modules.tenant_migration.fingerprints import target_binding_fingerprint
from app.modules.tenant_migration.materialization import (
    MaterializedMigrationObject,
    OwnerMigrationObjectBatch,
)
from app.modules.tenant_migration.postgres_adapter import (
    PostgresOwnerMigrationAdapter,
    PostgresOwnerMigrationAdapterError,
)
from app.modules.tenant_migration.schemas import (
    OwnerMigrationFileObjectPlan,
    OwnerMigrationFilePlan,
    OwnerMigrationObjectPlan,
    OwnerMigrationPlanReport,
    OwnerMigrationTablePlan,
)


def _plan() -> OwnerMigrationPlanReport:
    return OwnerMigrationPlanReport(
        source_inventory_fingerprint="c" * 64,
        source_file_reconciliation_fingerprint="d" * 64,
        target_binding_fingerprint=target_binding_fingerprint(
            "owner-production", "tenant-production"
        ),
        object_count=1,
        file_count=1,
        plan_fingerprint="a" * 64,
        tables=(
            OwnerMigrationTablePlan(
                store_id="private_library",
                table_name="library_items",
                ownership="direct",
                sequence=1,
                object_count=1,
                object_set_fingerprint="e" * 64,
                objects=(
                    OwnerMigrationObjectPlan(
                        object_digest="1" * 64,
                        source_record_fingerprint="2" * 64,
                    ),
                ),
            ),
        ),
        files=(
            OwnerMigrationFilePlan(
                store_id="private_library_files",
                sequence=2,
                object_count=1,
                object_set_fingerprint="f" * 64,
                objects=(
                    OwnerMigrationFileObjectPlan(
                        object_digest="3" * 64,
                        source_checksum=hashlib.sha256(b"private-file").hexdigest(),
                        byte_length=12,
                    ),
                ),
            ),
        ),
    )


class _Planner:
    def __init__(self, plan: OwnerMigrationPlanReport) -> None:
        self.plan_result = plan

    def plan(self, **kwargs) -> OwnerMigrationPlanReport:
        return self.plan_result


class _Objects:
    def __init__(self) -> None:
        self.calls = 0

    def materialize(self, **kwargs) -> OwnerMigrationObjectBatch:
        self.calls += 1
        plan = kwargs["plan"]
        return OwnerMigrationObjectBatch(
            plan_fingerprint=plan.plan_fingerprint,
            target_binding_fingerprint=plan.target_binding_fingerprint,
            object_count=1,
            objects=(
                MaterializedMigrationObject(
                    sequence=1,
                    store_id="private_library",
                    table_name="library_items",
                    object_digest="1" * 64,
                    source_record_fingerprint="2" * 64,
                    dependency_digests=(),
                    payload_json='{"owner_id":"target","content":"private"}',
                ),
            ),
        )


class _Files:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.calls = 0

    def materialize(self, **kwargs) -> OwnerMigrationFileBatch:
        self.calls += 1
        plan = kwargs["plan"]
        return OwnerMigrationFileBatch(
            plan_fingerprint=plan.plan_fingerprint,
            target_binding_fingerprint=plan.target_binding_fingerprint,
            file_count=1,
            files=(
                MaterializedMigrationFile(
                    sequence=1,
                    store_id="private_library_files",
                    object_digest="3" * 64,
                    source_checksum=hashlib.sha256(b"private-file").hexdigest(),
                    byte_length=12,
                    _path=self.path,
                ),
            ),
        )


class _Cursor:
    def __init__(self, rows=(), rowcount: int = 0) -> None:
        self.rows = tuple(rows)
        self.rowcount = rowcount

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class _Database:
    def __init__(self) -> None:
        self.runs: dict[str, dict[str, Any]] = {}
        self.objects: dict[str, dict[str, Any]] = {}
        self.files: dict[str, dict[str, Any]] = {}
        self.connections = 0
        self.fail_commit = False
        self.omit_objects_on_read = False
        self.queries: list[str] = []

    def connect(self):
        self.connections += 1
        return _Connection(self)


class _Connection:
    def __init__(self, database: _Database) -> None:
        self.database = database
        self.before = None

    def __enter__(self):
        self.before = deepcopy(
            (self.database.runs, self.database.objects, self.database.files)
        )
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if exc_type is not None or self.database.fail_commit:
            assert self.before is not None
            (
                self.database.runs,
                self.database.objects,
                self.database.files,
            ) = self.before
        if exc_type is None and self.database.fail_commit:
            raise RuntimeError("synthetic commit failure")

    def execute(self, query: str, params=None) -> _Cursor:
        normalized = " ".join(query.split())
        self.database.queries.append(normalized)
        values = tuple(params or ())
        if normalized == "SELECT pg_advisory_xact_lock(%s)":
            assert len(values) == 1
            assert -(1 << 63) <= values[0] < (1 << 63)
            return _Cursor()
        if normalized.startswith("SELECT target_binding_fingerprint"):
            row = self.database.runs.get(values[0])
            return _Cursor((row,) if row else ())
        if normalized.startswith(
            "SELECT plan_fingerprint"
        ) and "owner_migration_runs" in normalized:
            rows = tuple(
                {"plan_fingerprint": fingerprint}
                for fingerprint, row in self.database.runs.items()
                if row["target_binding_fingerprint"] == values[0]
                and row["status"] in {"in_progress", "complete"}
            )
            return _Cursor(rows[:2])
        if normalized.startswith("INSERT INTO") and "owner_migration_runs" in normalized:
            self.database.runs[values[0]] = {
                "target_binding_fingerprint": values[1],
                "status": "in_progress",
            }
            return _Cursor(rowcount=1)
        if normalized.startswith("INSERT INTO") and "owner_migration_objects" in normalized:
            self.database.objects[values[6]] = {"plan": values[0], "payload": values[9]}
            return _Cursor(rowcount=1)
        if normalized.startswith("INSERT INTO") and "owner_migration_files" in normalized:
            self.database.files[values[5]] = {
                "plan": values[0],
                "staged": values[8],
                "published": None,
            }
            return _Cursor(rowcount=1)
        if normalized.startswith(
            "SELECT object_digest"
        ) and "owner_migration_objects" in normalized:
            rows = tuple(
                {"object_digest": digest}
                for digest, row in self.database.objects.items()
                if row["plan"] == values[0]
            )
            return _Cursor(()) if self.database.omit_objects_on_read else _Cursor(rows)
        if normalized.startswith("SELECT object_digest") and "owner_migration_files" in normalized:
            return _Cursor(
                tuple(
                    {"object_digest": digest}
                    for digest, row in self.database.files.items()
                    if row["plan"] == values[0]
                )
            )
        if normalized.startswith("UPDATE") and "owner_migration_files" in normalized:
            row = self.database.files.get(values[2])
            if row is None or row["plan"] != values[1] or row["published"] is not None:
                return _Cursor()
            row["published"] = values[0]
            return _Cursor(rowcount=1)
        if normalized.startswith("UPDATE") and "owner_migration_runs" in normalized:
            row = self.database.runs.get(values[1])
            if row is None or row["status"] != "in_progress":
                return _Cursor()
            row["status"] = "complete"
            return _Cursor(rowcount=1)
        raise AssertionError(normalized)


class _StagingTransaction:
    def __init__(self, staging: "_Staging") -> None:
        self.staging = staging

    def stage(self, item: MaterializedMigrationFile) -> str:
        sink = io.BytesIO()
        item.copy_to(sink)
        self.staging.staged[item.object_digest] = sink.getvalue()
        return f"staged/{item.object_digest}"

    def publish(self):
        if self.staging.bad_publish:
            return {}
        for digest, content in self.staging.staged.items():
            self.staging.published[digest] = content
        return {digest: f"published/{digest}" for digest in self.staging.staged}


class _StagingContext(AbstractContextManager[_StagingTransaction]):
    def __init__(self, staging: "_Staging") -> None:
        self.staging = staging
        self.before = None

    def __enter__(self) -> _StagingTransaction:
        self.before = deepcopy((self.staging.staged, self.staging.published))
        return _StagingTransaction(self.staging)

    def __exit__(self, exc_type, exc, traceback) -> None:
        if exc_type is not None:
            assert self.before is not None
            self.staging.staged, self.staging.published = self.before


class _Staging:
    def __init__(self) -> None:
        self.staged: dict[str, bytes] = {}
        self.published: dict[str, bytes] = {}
        self.transactions = 0
        self.bad_publish = False

    def transaction(self, **kwargs) -> _StagingContext:
        self.transactions += 1
        assert len(kwargs["plan_fingerprint"]) == 64
        return _StagingContext(self)


def _setup(tmp_path: Path):
    source = tmp_path / "private.bin"
    source.write_bytes(b"private-file")
    plan = _plan()
    database = _Database()
    staging = _Staging()
    objects = _Objects()
    files = _Files(source)
    adapter = PostgresOwnerMigrationAdapter(
        connect=database.connect,
        object_materializer=objects,
        file_materializer=files,
        file_staging=staging,
        source_owner_id="owner-alpha",
        target_owner_id="owner-production",
        target_tenant_id="tenant-production",
    )
    executor = OwnerMigrationExecutor(_Planner(plan), adapter)
    return plan, database, staging, objects, files, adapter, executor


def _execute(executor: OwnerMigrationExecutor):
    return executor.execute(
        source_owner_id="owner-alpha",
        target_owner_id="owner-production",
        target_tenant_id="tenant-production",
        expected_inventory_fingerprint="c" * 64,
        expected_file_reconciliation_fingerprint="d" * 64,
        expected_plan_fingerprint="a" * 64,
        confirmation="执行 owner 数据迁移",
        confirmed=True,
    )


def test_postgres_adapter_applies_reconciles_and_is_idempotent(tmp_path: Path) -> None:
    _, database, staging, objects, files, _, executor = _setup(tmp_path)

    first = _execute(executor)
    second = _execute(executor)

    assert first.outcome == "applied"
    assert second.outcome == "already_applied"
    assert next(iter(database.runs.values()))["status"] == "complete"
    assert next(iter(database.objects.values()))["payload"].endswith("private\"}")
    assert staging.published["3" * 64] == b"private-file"
    assert database.queries[0] == "SELECT pg_advisory_xact_lock(%s)"
    assert objects.calls == 1
    assert files.calls == 1


def test_postgres_adapter_rolls_back_database_and_files_on_reconcile_failure(
    tmp_path: Path,
) -> None:
    _, database, staging, _, _, _, executor = _setup(tmp_path)
    database.omit_objects_on_read = True

    with pytest.raises(
        OwnerMigrationExecutionError,
        match="MIGRATION_TARGET_RECONCILIATION_FAILED",
    ):
        _execute(executor)

    assert database.runs == {}
    assert database.objects == {}
    assert database.files == {}
    assert staging.staged == {}
    assert staging.published == {}


def test_postgres_adapter_reverses_file_publish_when_database_commit_fails(
    tmp_path: Path,
) -> None:
    _, database, staging, _, _, _, executor = _setup(tmp_path)
    database.fail_commit = True

    with pytest.raises(OwnerMigrationExecutionError, match="MIGRATION_EXECUTION_FAILED"):
        _execute(executor)

    assert database.runs == {}
    assert staging.staged == {}
    assert staging.published == {}


def test_postgres_adapter_rejects_incomplete_publish_and_rolls_back(
    tmp_path: Path,
) -> None:
    _, database, staging, _, _, _, executor = _setup(tmp_path)
    staging.bad_publish = True

    with pytest.raises(OwnerMigrationExecutionError, match="MIGRATION_EXECUTION_FAILED"):
        _execute(executor)

    assert database.runs == {}
    assert staging.staged == {}


def test_postgres_adapter_rejects_wrong_binding_before_opening_targets(
    tmp_path: Path,
) -> None:
    _, database, staging, _, _, adapter, _ = _setup(tmp_path)

    with pytest.raises(
        PostgresOwnerMigrationAdapterError,
        match="POSTGRES_OWNER_MIGRATION_TARGET_CHANGED",
    ):
        with adapter.transaction(
            target_binding_fingerprint="9" * 64,
            plan_fingerprint="a" * 64,
        ):
            pass

    assert database.connections == 0
    assert staging.transactions == 0
