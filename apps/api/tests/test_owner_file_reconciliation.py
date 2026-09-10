from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from app.modules.tenant_migration.file_reconciliation import (
    OwnerFileReconciliation,
    OwnerFileReconciliationError,
    OwnerFileStoreSpec,
)
from app.modules.tenant_migration.inventory import (
    OwnerDirectoryStoreSpec,
    OwnerSqliteStoreSpec,
    OwnerTableSpec,
)


def _database(path: Path, script: str) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(script)


def _private_spec(tmp_path: Path) -> OwnerFileStoreSpec:
    database = OwnerSqliteStoreSpec(
        "private_library",
        tmp_path / "library.sqlite3",
        (OwnerTableSpec("library_items", "direct", ("owner_id",)),),
    )
    files = OwnerDirectoryStoreSpec(
        "private_library_files", tmp_path / "files", "private_library"
    )
    return OwnerFileStoreSpec(
        "private_library_files", database, files, "private_library"
    )


def _prepare_private(spec: OwnerFileStoreSpec, rows: str) -> None:
    _database(
        spec.database.path,
        "CREATE TABLE library_items "
        "(item_id TEXT, owner_id TEXT NOT NULL, stored_name TEXT NOT NULL);"
        + rows,
    )
    spec.files.path.mkdir()


def test_missing_file_store_is_read_only_and_ready(tmp_path: Path) -> None:
    spec = _private_spec(tmp_path)

    report = OwnerFileReconciliation((spec,)).reconcile(
        source_owner_id="owner-alpha"
    )

    assert report.migration_ready is True
    assert report.missing_store_count == 1
    assert not spec.database.path.exists()
    assert not spec.files.path.exists()


def test_flat_store_reconciles_requested_owner_without_exposing_names(
    tmp_path: Path,
) -> None:
    spec = _private_spec(tmp_path)
    _prepare_private(
        spec,
        "INSERT INTO library_items VALUES "
        "('one', 'owner-alpha', 'one.pdf'), ('two', 'owner-beta', 'two.pdf');",
    )
    (spec.files.path / "one.pdf").write_bytes(b"one")
    (spec.files.path / "two.pdf").write_bytes(b"two")

    report = OwnerFileReconciliation((spec,)).reconcile(
        source_owner_id="owner-alpha"
    )

    assert report.migration_ready is True
    assert report.referenced_files == 1
    assert report.present_files == 1
    serialized = report.model_dump_json()
    assert "owner-alpha" not in serialized
    assert "one.pdf" not in serialized


@pytest.mark.parametrize(
    "rows,files,issue",
    [
        (
            "INSERT INTO library_items VALUES ('one', 'owner-alpha', 'missing.pdf');",
            (),
            "OWNER_REFERENCED_FILE_MISSING",
        ),
        (
            "INSERT INTO library_items VALUES ('one', 'owner-beta', 'known.pdf');",
            ("known.pdf", "orphan.pdf"),
            "UNREFERENCED_FILE_PRESENT",
        ),
        (
            "INSERT INTO library_items VALUES "
            "('one', 'owner-alpha', 'shared.pdf'), "
            "('two', 'owner-beta', 'shared.pdf');",
            ("shared.pdf",),
            "CROSS_OWNER_FILE_REFERENCE",
        ),
        (
            "INSERT INTO library_items VALUES ('one', 'owner-alpha', '../escape.pdf');",
            (),
            "FILE_REFERENCE_PATH_UNSAFE",
        ),
    ],
)
def test_flat_store_blocks_reference_anomalies(
    tmp_path: Path, rows: str, files: tuple[str, ...], issue: str
) -> None:
    spec = _private_spec(tmp_path)
    _prepare_private(spec, rows)
    for name in files:
        (spec.files.path / name).write_bytes(b"test")

    report = OwnerFileReconciliation((spec,)).reconcile(
        source_owner_id="owner-alpha"
    )

    assert report.migration_ready is False
    assert issue in report.stores[0].issues


def test_joined_file_reference_requires_resolvable_owner(tmp_path: Path) -> None:
    database = OwnerSqliteStoreSpec(
        "question_capture",
        tmp_path / "capture.sqlite3",
        (
            OwnerTableSpec("question_capture_assets", "direct", ("asset_id",)),
            OwnerTableSpec(
                "question_capture_revisions", "inherited", ("asset_id",)
            ),
        ),
    )
    files = OwnerDirectoryStoreSpec(
        "question_capture_files", tmp_path / "files", "question_capture"
    )
    spec = OwnerFileStoreSpec(
        "question_capture_files", database, files, "question_capture"
    )
    _database(
        database.path,
        "CREATE TABLE question_capture_assets (asset_id TEXT, owner_id TEXT);"
        "CREATE TABLE question_capture_revisions (asset_id TEXT, stored_name TEXT);"
        "INSERT INTO question_capture_revisions VALUES ('missing', 'orphan.png');",
    )
    files.path.mkdir()
    (files.path / "orphan.png").write_bytes(b"image")

    report = OwnerFileReconciliation((spec,)).reconcile(
        source_owner_id="owner-alpha"
    )

    assert report.stores[0].unresolved_owner_references == 1
    assert "FILE_REFERENCE_OWNER_UNRESOLVED" in report.stores[0].issues


def test_exam_store_reconciles_assets_across_immutable_versions(
    tmp_path: Path,
) -> None:
    database = OwnerSqliteStoreSpec(
        "exam_papers",
        tmp_path / "papers.sqlite3",
        (
            OwnerTableSpec("exam_papers", "direct", ("exam_paper_id",)),
            OwnerTableSpec(
                "exam_paper_revisions", "direct", ("exam_paper_id",)
            ),
        ),
    )
    files = OwnerDirectoryStoreSpec(
        "exam_paper_assets", tmp_path / "assets", "exam_papers"
    )
    spec = OwnerFileStoreSpec("exam_paper_assets", database, files, "exam_papers")
    current = json.dumps(
        {"items": [{"question": {"images": [{"asset_id": "asset_new"}]}}]}
    )
    previous = json.dumps(
        {"items": [{"question": {"images": [{"asset_id": "asset_old"}]}}]}
    )
    _database(
        database.path,
        "CREATE TABLE exam_papers "
        "(exam_paper_id TEXT, owner_id TEXT, raw_json TEXT);"
        "CREATE TABLE exam_paper_revisions "
        "(exam_paper_id TEXT, owner_id TEXT, raw_json TEXT);"
        "INSERT INTO exam_papers VALUES ('paper_one', 'owner-alpha', "
        + repr(current)
        + "); INSERT INTO exam_paper_revisions VALUES "
        "('paper_one', 'owner-alpha', "
        + repr(previous)
        + ");",
    )
    paper_root = files.path / "paper_one"
    paper_root.mkdir(parents=True)
    (paper_root / "asset_new.png").write_bytes(b"new")
    (paper_root / "asset_old.jpg").write_bytes(b"old")

    report = OwnerFileReconciliation((spec,)).reconcile(
        source_owner_id="owner-alpha"
    )

    assert report.migration_ready is True
    assert report.referenced_files == 2
    assert report.present_files == 2


def test_file_catalog_rejects_aliased_paths_before_access(tmp_path: Path) -> None:
    first = _private_spec(tmp_path)
    second = OwnerFileStoreSpec(
        "other_files",
        OwnerSqliteStoreSpec(
            "other_database", first.database.path, first.database.tables
        ),
        OwnerDirectoryStoreSpec(
            "other_files", tmp_path / "other", "other_database"
        ),
        "question_capture",
    )

    with pytest.raises(
        OwnerFileReconciliationError, match="OWNER_FILE_CATALOG_INVALID"
    ):
        OwnerFileReconciliation((first, second))
