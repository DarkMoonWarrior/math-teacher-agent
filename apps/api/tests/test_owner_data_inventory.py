from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.modules.tenant_migration.inventory import (
    OwnerDataInventory,
    OwnerDataInventoryError,
    OwnerDirectoryStoreSpec,
    OwnerSqliteStoreSpec,
    OwnerTableSpec,
)


def _database(path: Path, script: str) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(script)


def _owned_store(path: Path) -> OwnerSqliteStoreSpec:
    return OwnerSqliteStoreSpec(
        "private_questions",
        path,
        (
            OwnerTableSpec("items", "direct", ("item_id", "owner_id")),
            OwnerTableSpec("revisions", "inherited", ("item_id",)),
        ),
    )


def test_missing_store_is_reported_without_creating_it(tmp_path: Path) -> None:
    path = tmp_path / "missing.sqlite3"

    report = OwnerDataInventory((_owned_store(path),)).inspect(
        source_owner_id="owner-alpha"
    )

    assert report.migration_ready is True
    assert report.missing_store_count == 1
    assert report.stores[0].status == "missing"
    assert not path.exists()


def test_read_only_uri_handles_reserved_path_characters(tmp_path: Path) -> None:
    path = tmp_path / "owned#snapshot.sqlite3"
    _database(
        path,
        "CREATE TABLE items (item_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL);",
    )

    report = OwnerDataInventory((_owned_store(path),)).inspect(
        source_owner_id="owner-alpha"
    )

    assert report.migration_ready is True
    assert report.stores[0].status == "ready"


def test_inventory_counts_only_direct_owner_rows_and_hides_owner_value(
    tmp_path: Path,
) -> None:
    path = tmp_path / "owned.sqlite3"
    _database(
        path,
        """
        CREATE TABLE items (item_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL);
        CREATE TABLE revisions (item_id TEXT NOT NULL, revision INTEGER NOT NULL);
        INSERT INTO items VALUES ('one', 'owner-alpha'), ('two', 'owner-beta');
        INSERT INTO revisions VALUES ('one', 1), ('two', 1);
        """,
    )

    report = OwnerDataInventory((_owned_store(path),)).inspect(
        source_owner_id="owner-alpha"
    )

    assert report.migration_ready is True
    assert report.matching_owner_rows == 1
    assert report.stores[0].tables[0].matching_owner_rows == 1
    assert report.stores[0].tables[1].matching_owner_rows is None
    assert "owner-alpha" not in report.model_dump_json()
    assert len(report.report_fingerprint) == 64


def test_legacy_unowned_rows_block_migration(tmp_path: Path) -> None:
    path = tmp_path / "lesson.sqlite3"
    _database(
        path,
        """
        CREATE TABLE legacy_plans (plan_id TEXT PRIMARY KEY);
        INSERT INTO legacy_plans VALUES ('plan-one');
        """,
    )
    store = OwnerSqliteStoreSpec(
        "lesson_plans",
        path,
        (OwnerTableSpec("legacy_plans", "legacy_unowned", ("plan_id",)),),
    )

    report = OwnerDataInventory((store,)).inspect(source_owner_id="owner-alpha")

    assert report.migration_ready is False
    assert report.blocked_store_count == 1
    assert report.stores[0].issues == ("LEGACY_UNOWNED_ROWS_PRESENT",)


@pytest.mark.parametrize(
    "script, expected_issue",
    [
        (
            "CREATE TABLE items (item_id TEXT PRIMARY KEY); "
            "CREATE TABLE revisions (item_id TEXT NOT NULL);",
            "OWNER_STORE_COLUMN_SET_MISMATCH",
        ),
        (
            "CREATE TABLE items (item_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL); "
            "CREATE TABLE revisions (item_id TEXT NOT NULL); "
            "CREATE TABLE forgotten (value TEXT);",
            "OWNER_STORE_TABLE_SET_MISMATCH",
        ),
    ],
)
def test_schema_drift_blocks_inventory(
    tmp_path: Path, script: str, expected_issue: str
) -> None:
    path = tmp_path / "drift.sqlite3"
    _database(path, script)

    report = OwnerDataInventory((_owned_store(path),)).inspect(
        source_owner_id="owner-alpha"
    )

    assert report.stores[0].status == "blocked"
    assert expected_issue in report.stores[0].issues


def test_absent_lazily_initialized_known_table_does_not_block(tmp_path: Path) -> None:
    path = tmp_path / "partial.sqlite3"
    _database(
        path,
        "CREATE TABLE items (item_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL);",
    )

    report = OwnerDataInventory((_owned_store(path),)).inspect(
        source_owner_id="owner-alpha"
    )

    assert report.stores[0].status == "ready"
    assert [table.table_name for table in report.stores[0].tables] == ["items"]


def test_nonempty_directory_waits_for_reference_reconciliation(
    tmp_path: Path,
) -> None:
    database = tmp_path / "owned.sqlite3"
    files = tmp_path / "files"
    files.mkdir()
    (files / "private.bin").write_bytes(b"private")
    directory = OwnerDirectoryStoreSpec("private_files", files, "private_questions")

    report = OwnerDataInventory((_owned_store(database), directory)).inspect(
        source_owner_id="owner-alpha"
    )

    assert report.stores[1].file_count == 1
    assert report.stores[1].status == "blocked"
    assert report.stores[1].issues == (
        "INDIRECT_FILE_OWNERSHIP_REQUIRES_RECONCILIATION",
    )


def test_invalid_catalog_is_rejected_before_storage_access(tmp_path: Path) -> None:
    duplicate = _owned_store(tmp_path / "one.sqlite3")

    with pytest.raises(OwnerDataInventoryError, match="OWNER_DATA_CATALOG_INVALID"):
        OwnerDataInventory((duplicate, duplicate))


def test_catalog_rejects_aliased_paths_and_directory_owner_sources(
    tmp_path: Path,
) -> None:
    first = _owned_store(tmp_path / "shared.sqlite3")
    second = OwnerSqliteStoreSpec("other_store", first.path, first.tables)

    with pytest.raises(OwnerDataInventoryError, match="OWNER_DATA_CATALOG_INVALID"):
        OwnerDataInventory((first, second))

    files = OwnerDirectoryStoreSpec("private_files", tmp_path / "files", "private_files")
    with pytest.raises(OwnerDataInventoryError, match="OWNER_DATA_CATALOG_INVALID"):
        OwnerDataInventory((files,))
