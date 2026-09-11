from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.modules.tenant_migration.file_reconciliation import OwnerFileStoreSpec
from app.modules.tenant_migration.inventory import (
    OwnerDirectoryStoreSpec,
    OwnerSqliteStoreSpec,
    OwnerTableSpec,
)
from app.modules.tenant_migration.planning import (
    OwnerMigrationDependency,
    OwnerMigrationPlanner,
    OwnerMigrationPlanningError,
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
    files = OwnerDirectoryStoreSpec(
        "private_library_files", tmp_path / "files", "private_library"
    )
    file_spec = OwnerFileStoreSpec(
        "private_library_files", database, files, "private_library"
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
            (
                OwnerMigrationDependency(
                    "library_items", ("library_item_id",)
                ),
            ),
        ),
    )
    return (database, files), (file_spec,), queries


def _prepare(
    tmp_path: Path, *, stored_name: str = "alpha.pdf"
) -> OwnerMigrationPlanner:
    data_specs, file_specs, queries = _catalog(tmp_path)
    database = data_specs[0]
    assert isinstance(database, OwnerSqliteStoreSpec)
    _database(
        database.path,
        "CREATE TABLE library_items ("
        "library_item_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, "
        "stored_name TEXT NOT NULL UNIQUE, content TEXT NOT NULL);"
        "CREATE TABLE library_text_revisions ("
        "revision_id INTEGER PRIMARY KEY, library_item_id TEXT NOT NULL);"
        "INSERT INTO library_items VALUES "
        f"('item-alpha', 'owner-alpha', '{stored_name}', 'private alpha');"
        "INSERT INTO library_items VALUES "
        "('item-beta', 'owner-beta', 'beta.pdf', 'private beta');"
        "INSERT INTO library_text_revisions VALUES (1, 'item-alpha');"
        "INSERT INTO library_text_revisions VALUES (2, 'item-beta');",
    )
    files = data_specs[1]
    assert isinstance(files, OwnerDirectoryStoreSpec)
    files.path.mkdir()
    (files.path / stored_name).write_bytes(b"alpha-private")
    (files.path / "beta.pdf").write_bytes(b"beta-private")
    return OwnerMigrationPlanner(data_specs, file_specs, queries)


def _evidence(
    planner: OwnerMigrationPlanner,
) -> tuple[str, str]:
    inventory = planner._inventory.inspect(source_owner_id="owner-alpha")
    files = planner._reconciliation.reconcile(source_owner_id="owner-alpha")
    return inventory.report_fingerprint, files.report_fingerprint


def _plan(planner: OwnerMigrationPlanner):
    inventory, files = _evidence(planner)
    return planner.plan(
        source_owner_id="owner-alpha",
        target_owner_id="owner-production",
        target_tenant_id="tenant-production",
        expected_inventory_fingerprint=inventory,
        expected_file_reconciliation_fingerprint=files,
    )


def test_plan_is_per_object_dependency_ordered_and_digest_only(
    tmp_path: Path,
) -> None:
    planner = _prepare(tmp_path)

    report = _plan(planner)

    assert report.execution_allowed is False
    assert report.migration_ready is True
    assert report.object_count == 2
    assert report.file_count == 1
    assert [table.table_name for table in report.tables] == [
        "library_items",
        "library_text_revisions",
    ]
    assert report.tables[0].sequence < report.tables[1].sequence
    assert report.tables[1].objects[0].dependency_digests == (
        report.tables[0].objects[0].object_digest,
    )
    serialized = report.model_dump_json()
    for secret in (
        "owner-alpha",
        "owner-production",
        "tenant-production",
        "item-alpha",
        "alpha.pdf",
    ):
        assert secret not in serialized


def test_plan_is_stable_and_does_not_mutate_sources(tmp_path: Path) -> None:
    planner = _prepare(tmp_path)
    database = planner._data_specs[0]
    files = planner._data_specs[1]
    assert isinstance(database, OwnerSqliteStoreSpec)
    assert isinstance(files, OwnerDirectoryStoreSpec)
    database_before = database.path.read_bytes()
    file_before = (files.path / "alpha.pdf").read_bytes()

    first = _plan(planner)
    second = _plan(planner)

    assert first.plan_fingerprint == second.plan_fingerprint
    assert database.path.read_bytes() == database_before
    assert (files.path / "alpha.pdf").read_bytes() == file_before


def test_plan_fingerprint_binds_source_record_content(tmp_path: Path) -> None:
    planner = _prepare(tmp_path)
    first = _plan(planner)
    database = planner._data_specs[0]
    assert isinstance(database, OwnerSqliteStoreSpec)
    with sqlite3.connect(database.path) as connection:
        connection.execute(
            "UPDATE library_items SET content = ? WHERE library_item_id = ?",
            ("revised private alpha", "item-alpha"),
        )

    second = _plan(planner)

    assert first.source_inventory_fingerprint == second.source_inventory_fingerprint
    assert (
        first.source_file_reconciliation_fingerprint
        == second.source_file_reconciliation_fingerprint
    )
    assert first.plan_fingerprint != second.plan_fingerprint
    assert (
        first.tables[0].objects[0].source_record_fingerprint
        != second.tables[0].objects[0].source_record_fingerprint
    )


def test_plan_fingerprint_binds_source_file_content(tmp_path: Path) -> None:
    planner = _prepare(tmp_path)
    first = _plan(planner)
    files = planner._data_specs[1]
    assert isinstance(files, OwnerDirectoryStoreSpec)
    (files.path / "alpha.pdf").write_bytes(b"changed-private")

    second = _plan(planner)

    assert (
        first.source_file_reconciliation_fingerprint
        == second.source_file_reconciliation_fingerprint
    )
    assert first.plan_fingerprint != second.plan_fingerprint
    assert (
        first.files[0].objects[0].source_checksum
        != second.files[0].objects[0].source_checksum
    )
    assert first.files[0].objects[0].byte_length == len(b"alpha-private")
    assert second.files[0].objects[0].byte_length == len(b"changed-private")


def test_stale_evidence_and_unchanged_binding_are_rejected(tmp_path: Path) -> None:
    planner = _prepare(tmp_path)
    inventory, files = _evidence(planner)

    with pytest.raises(OwnerMigrationPlanningError, match="MIGRATION_EVIDENCE_CHANGED"):
        planner.plan(
            source_owner_id="owner-alpha",
            target_owner_id="owner-production",
            target_tenant_id="tenant-production",
            expected_inventory_fingerprint="0" * 64,
            expected_file_reconciliation_fingerprint=files,
        )

    with pytest.raises(
        OwnerMigrationPlanningError, match="MIGRATION_BINDING_UNCHANGED"
    ):
        planner.plan(
            source_owner_id="owner-alpha",
            target_owner_id="owner-alpha",
            target_tenant_id="tenant-production",
            expected_inventory_fingerprint=inventory,
            expected_file_reconciliation_fingerprint=files,
        )


def test_dangling_inherited_owner_blocks_plan_even_when_summary_is_ready(
    tmp_path: Path,
) -> None:
    planner = _prepare(tmp_path)
    database = planner._data_specs[0]
    assert isinstance(database, OwnerSqliteStoreSpec)
    with sqlite3.connect(database.path) as connection:
        connection.execute(
            "INSERT INTO library_text_revisions VALUES (3, 'missing-parent')"
        )
    inventory, files = _evidence(planner)

    with pytest.raises(
        OwnerMigrationPlanningError,
        match="MIGRATION_OWNER_RELATIONSHIP_UNRESOLVED",
    ):
        planner.plan(
            source_owner_id="owner-alpha",
            target_owner_id="owner-production",
            target_tenant_id="tenant-production",
            expected_inventory_fingerprint=inventory,
            expected_file_reconciliation_fingerprint=files,
        )


def test_missing_owner_file_blocks_plan(tmp_path: Path) -> None:
    planner = _prepare(tmp_path, stored_name="missing.pdf")
    files = planner._data_specs[1]
    assert isinstance(files, OwnerDirectoryStoreSpec)
    (files.path / "missing.pdf").unlink()
    inventory, reconciliation = _evidence(planner)

    with pytest.raises(
        OwnerMigrationPlanningError,
        match="MIGRATION_FILE_RECONCILIATION_BLOCKED",
    ):
        planner.plan(
            source_owner_id="owner-alpha",
            target_owner_id="owner-production",
            target_tenant_id="tenant-production",
            expected_inventory_fingerprint=inventory,
            expected_file_reconciliation_fingerprint=reconciliation,
        )


def test_catalog_must_cover_each_nonlegacy_table(tmp_path: Path) -> None:
    data_specs, file_specs, queries = _catalog(tmp_path)

    with pytest.raises(
        OwnerMigrationPlanningError, match="MIGRATION_PLAN_CATALOG_INVALID"
    ):
        OwnerMigrationPlanner(data_specs, file_specs, queries[:1])
