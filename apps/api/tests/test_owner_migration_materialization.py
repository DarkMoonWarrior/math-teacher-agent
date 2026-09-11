from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from app.modules.tenant_migration.file_reconciliation import OwnerFileStoreSpec
from app.modules.tenant_migration.inventory import (
    OwnerDirectoryStoreSpec,
    OwnerSqliteStoreSpec,
    OwnerTableSpec,
)
from app.modules.tenant_migration.materialization import (
    OwnerMigrationMaterializationError,
    OwnerMigrationObjectMaterializer,
)
from app.modules.tenant_migration.planning import (
    OwnerMigrationDependency,
    OwnerMigrationPlanner,
    OwnerMigrationQuerySpec,
)


def _database(path: Path, script: str) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(script)


def _catalog(tmp_path: Path) -> tuple[
    tuple[OwnerSqliteStoreSpec | OwnerDirectoryStoreSpec, ...],
    tuple[OwnerFileStoreSpec, ...],
    tuple[OwnerMigrationQuerySpec, ...],
]:
    database = OwnerSqliteStoreSpec(
        "private_library",
        tmp_path / "library.sqlite3",
        (
            OwnerTableSpec(
                "library_items",
                "direct",
                ("library_item_id", "owner_id", "stored_name"),
            ),
            OwnerTableSpec(
                "library_text_revisions",
                "inherited",
                ("revision_id", "library_item_id"),
            ),
        ),
    )
    directory = OwnerDirectoryStoreSpec(
        "private_library_files",
        tmp_path / "files",
        "private_library",
    )
    files = OwnerFileStoreSpec(
        "private_library_files",
        database,
        directory,
        "private_library",
    )
    queries = (
        OwnerMigrationQuerySpec(
            "private_library",
            "library_items",
            "direct",
            ("library_item_id",),
            "SELECT library_item_id, owner_id FROM library_items",
        ),
        OwnerMigrationQuerySpec(
            "private_library",
            "library_text_revisions",
            "inherited",
            ("revision_id",),
            "SELECT r.revision_id, i.library_item_id, i.owner_id "
            "FROM library_text_revisions r LEFT JOIN library_items i "
            "ON i.library_item_id = r.library_item_id",
            (OwnerMigrationDependency("library_items", ("library_item_id",)),),
        ),
    )
    return (database, directory), (files,), queries


def _prepare(tmp_path: Path):
    data_specs, file_specs, queries = _catalog(tmp_path)
    database = data_specs[0]
    assert isinstance(database, OwnerSqliteStoreSpec)
    _database(
        database.path,
        "CREATE TABLE library_items ("
        "library_item_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, "
        "stored_name TEXT NOT NULL UNIQUE, content TEXT NOT NULL, "
        "private_blob BLOB);"
        "CREATE TABLE library_text_revisions ("
        "revision_id INTEGER PRIMARY KEY, library_item_id TEXT NOT NULL, "
        "body TEXT NOT NULL);"
        "INSERT INTO library_items VALUES "
        "('item-alpha', 'owner-alpha', 'alpha.pdf', 'private alpha', X'0001');"
        "INSERT INTO library_items VALUES "
        "('item-beta', 'owner-beta', 'beta.pdf', 'private beta', X'0203');"
        "INSERT INTO library_text_revisions VALUES "
        "(1, 'item-alpha', 'alpha revision');"
        "INSERT INTO library_text_revisions VALUES "
        "(2, 'item-beta', 'beta revision');",
    )
    directory = data_specs[1]
    assert isinstance(directory, OwnerDirectoryStoreSpec)
    directory.path.mkdir()
    (directory.path / "alpha.pdf").write_bytes(b"alpha-private")
    (directory.path / "beta.pdf").write_bytes(b"beta-private")
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
    materializer = OwnerMigrationObjectMaterializer(data_specs, queries)
    return database, materializer, plan


def _materialize(materializer, plan):
    return materializer.materialize(
        plan=plan,
        source_owner_id="owner-alpha",
        target_owner_id="owner-production",
        target_tenant_id="tenant-production",
    )


def test_materializer_rewrites_owner_and_preserves_private_payload(
    tmp_path: Path,
) -> None:
    _, materializer, plan = _prepare(tmp_path)

    batch = _materialize(materializer, plan)

    assert batch.object_count == 2
    assert [item.sequence for item in batch.objects] == [1, 2]
    parent = batch.objects[0]
    child = batch.objects[1]
    payload = json.loads(parent.payload_json)
    values = dict(zip(payload["columns"], payload["values"], strict=True))
    assert values["owner_id"] == "owner-production"
    assert values["content"] == "private alpha"
    assert values["private_blob"] == {
        "base64": "AAE=",
        "encoding": "base64",
    }
    assert "owner-beta" not in parent.payload_json
    assert "private beta" not in parent.payload_json
    assert child.dependency_digests == (parent.object_digest,)


def test_materializer_is_read_only_and_hides_payload_from_repr(
    tmp_path: Path,
) -> None:
    database, materializer, plan = _prepare(tmp_path)
    before = database.path.read_bytes()

    batch = _materialize(materializer, plan)

    assert database.path.read_bytes() == before
    assert "private alpha" not in repr(batch)
    assert "owner-production" not in repr(batch)


def test_materializer_rejects_source_drift_after_planning(tmp_path: Path) -> None:
    database, materializer, plan = _prepare(tmp_path)
    with sqlite3.connect(database.path) as connection:
        connection.execute(
            "UPDATE library_items SET content = ? WHERE library_item_id = ?",
            ("changed after plan", "item-alpha"),
        )

    with pytest.raises(
        OwnerMigrationMaterializationError,
        match="MIGRATION_MATERIALIZATION_SOURCE_CHANGED",
    ):
        _materialize(materializer, plan)


def test_materializer_rejects_tampered_plan_before_reading_source(
    tmp_path: Path,
) -> None:
    data_specs, file_specs, queries = _catalog(tmp_path)
    database = data_specs[0]
    assert isinstance(database, OwnerSqliteStoreSpec)
    _database(
        database.path,
        "CREATE TABLE library_items ("
        "library_item_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, "
        "stored_name TEXT NOT NULL);"
        "CREATE TABLE library_text_revisions ("
        "revision_id INTEGER PRIMARY KEY, library_item_id TEXT NOT NULL);",
    )
    directory = data_specs[1]
    assert isinstance(directory, OwnerDirectoryStoreSpec)
    directory.path.mkdir()
    planner = OwnerMigrationPlanner(data_specs, file_specs, queries)
    inventory = planner._inventory.inspect(source_owner_id="owner-alpha")
    files = planner._reconciliation.reconcile(source_owner_id="owner-alpha")
    plan = planner.plan(
        source_owner_id="owner-alpha",
        target_owner_id="owner-production",
        target_tenant_id="tenant-production",
        expected_inventory_fingerprint=inventory.report_fingerprint,
        expected_file_reconciliation_fingerprint=files.report_fingerprint,
    ).model_copy(update={"object_count": 1})
    calls = 0

    def unexpected_connect(path: Path) -> sqlite3.Connection:
        nonlocal calls
        calls += 1
        return sqlite3.connect(path)

    materializer = OwnerMigrationObjectMaterializer(
        data_specs,
        queries,
        connect=unexpected_connect,
    )
    with pytest.raises(
        OwnerMigrationMaterializationError,
        match="MIGRATION_MATERIALIZATION_PLAN_INVALID",
    ):
        _materialize(materializer, plan)
    assert calls == 0


def test_materializer_rejects_wrong_target_before_reading_source(
    tmp_path: Path,
) -> None:
    data_specs, _, queries = _catalog(tmp_path)
    source_path = tmp_path / "source"
    source_path.mkdir()
    _, _, plan = _prepare(source_path)
    calls = 0

    def unexpected_connect(path: Path) -> sqlite3.Connection:
        nonlocal calls
        calls += 1
        raise AssertionError("source must not be opened")

    materializer = OwnerMigrationObjectMaterializer(
        data_specs,
        queries,
        connect=unexpected_connect,
    )
    with pytest.raises(
        OwnerMigrationMaterializationError,
        match="MIGRATION_MATERIALIZATION_TARGET_CHANGED",
    ):
        materializer.materialize(
            plan=plan,
            source_owner_id="owner-alpha",
            target_owner_id="different-target",
            target_tenant_id="tenant-production",
        )
    assert calls == 0
