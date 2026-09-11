from __future__ import annotations

import io
import sqlite3
from pathlib import Path

import pytest

from app.modules.tenant_migration.file_materialization import (
    OwnerMigrationFileMaterializationError,
    OwnerMigrationFileMaterializer,
)
from app.modules.tenant_migration.file_reconciliation import OwnerFileStoreSpec
from app.modules.tenant_migration.inventory import (
    OwnerDirectoryStoreSpec,
    OwnerSqliteStoreSpec,
    OwnerTableSpec,
)
from app.modules.tenant_migration.planning import (
    OwnerMigrationPlanner,
    OwnerMigrationQuerySpec,
)
from app.modules.tenant_migration.source_files import OwnerMigrationSourceFiles


def _prepare(tmp_path: Path):
    database = OwnerSqliteStoreSpec(
        "private_library",
        tmp_path / "library.sqlite3",
        (
            OwnerTableSpec(
                "library_items",
                "direct",
                ("library_item_id", "owner_id", "stored_name"),
            ),
        ),
    )
    directory = OwnerDirectoryStoreSpec(
        "private_library_files",
        tmp_path / "files",
        "private_library",
    )
    file_specs = (
        OwnerFileStoreSpec(
            "private_library_files",
            database,
            directory,
            "private_library",
        ),
    )
    queries = (
        OwnerMigrationQuerySpec(
            "private_library",
            "library_items",
            "direct",
            ("library_item_id",),
            "SELECT library_item_id, owner_id FROM library_items",
        ),
    )
    with sqlite3.connect(database.path) as connection:
        connection.executescript(
            "CREATE TABLE library_items ("
            "library_item_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, "
            "stored_name TEXT NOT NULL UNIQUE, content TEXT NOT NULL);"
            "INSERT INTO library_items VALUES "
            "('alpha', 'owner-alpha', 'alpha.pdf', 'private alpha');"
            "INSERT INTO library_items VALUES "
            "('beta', 'owner-beta', 'beta.pdf', 'private beta');"
        )
    directory.path.mkdir()
    source_path = directory.path / "alpha.pdf"
    source_path.write_bytes(b"alpha-private-file")
    (directory.path / "beta.pdf").write_bytes(b"beta-private-file")

    data_specs = (database, directory)
    planner = OwnerMigrationPlanner(data_specs, file_specs, queries)
    inventory = planner._inventory.inspect(source_owner_id="owner-alpha")
    files = planner._reconciliation.reconcile(source_owner_id="owner-alpha")
    plan = planner.plan(
        source_owner_id="owner-alpha",
        target_owner_id="owner-production",
        target_tenant_id="tenant-production",
        expected_inventory_fingerprint=inventory.report_fingerprint,
        expected_file_reconciliation_fingerprint=files.report_fingerprint,
    )
    materializer = OwnerMigrationFileMaterializer(
        OwnerMigrationSourceFiles(file_specs)
    )
    return database.path, source_path, materializer, plan


def _materialize(materializer, plan):
    return materializer.materialize(
        plan=plan,
        source_owner_id="owner-alpha",
        target_owner_id="owner-production",
        target_tenant_id="tenant-production",
    )


def test_file_materializer_streams_only_planned_owner_file(tmp_path: Path) -> None:
    database_path, source_path, materializer, plan = _prepare(tmp_path)
    database_before = database_path.read_bytes()
    source_before = source_path.read_bytes()

    batch = _materialize(materializer, plan)
    sink = io.BytesIO()

    assert batch.file_count == 1
    assert batch.files[0].sequence == 1
    assert batch.files[0].copy_to(sink) == len(source_before)
    assert sink.getvalue() == source_before
    assert database_path.read_bytes() == database_before
    assert source_path.read_bytes() == source_before
    assert "alpha.pdf" not in repr(batch)
    assert "owner-alpha" not in repr(batch)
    assert "alpha-private-file" not in repr(batch)


def test_file_materializer_rejects_drift_after_plan(tmp_path: Path) -> None:
    _, source_path, materializer, plan = _prepare(tmp_path)
    source_path.write_bytes(b"changed-before-materialization")

    with pytest.raises(
        OwnerMigrationFileMaterializationError,
        match="MIGRATION_FILE_MATERIALIZATION_SOURCE_CHANGED",
    ):
        _materialize(materializer, plan)


def test_file_stream_rechecks_content_after_materialization(tmp_path: Path) -> None:
    _, source_path, materializer, plan = _prepare(tmp_path)
    batch = _materialize(materializer, plan)
    source_path.write_bytes(b"changed-before-copy")

    with pytest.raises(
        OwnerMigrationFileMaterializationError,
        match="MIGRATION_FILE_MATERIALIZATION_SOURCE_CHANGED",
    ):
        batch.files[0].copy_to(io.BytesIO())


def test_file_materializer_rejects_wrong_target_before_source_read(
    tmp_path: Path,
) -> None:
    _, _, _, plan = _prepare(tmp_path)
    calls = 0

    class UnexpectedSource:
        def inspect(self, **kwargs):
            nonlocal calls
            calls += 1
            raise AssertionError("source must not be read")

    materializer = OwnerMigrationFileMaterializer(UnexpectedSource())
    with pytest.raises(
        OwnerMigrationFileMaterializationError,
        match="MIGRATION_FILE_MATERIALIZATION_TARGET_CHANGED",
    ):
        materializer.materialize(
            plan=plan,
            source_owner_id="owner-alpha",
            target_owner_id="other-target",
            target_tenant_id="tenant-production",
        )
    assert calls == 0


def test_file_materializer_rejects_tampered_plan_before_source_read(
    tmp_path: Path,
) -> None:
    _, _, _, plan = _prepare(tmp_path)
    tampered = plan.model_copy(update={"file_count": plan.file_count + 1})
    calls = 0

    class UnexpectedSource:
        def inspect(self, **kwargs):
            nonlocal calls
            calls += 1
            raise AssertionError("source must not be read")

    materializer = OwnerMigrationFileMaterializer(UnexpectedSource())
    with pytest.raises(
        OwnerMigrationFileMaterializationError,
        match="MIGRATION_FILE_MATERIALIZATION_PLAN_INVALID",
    ):
        _materialize(materializer, tampered)
    assert calls == 0
