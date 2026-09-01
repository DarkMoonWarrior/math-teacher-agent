from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from app.core.config import Settings
from app.modules.beta_recovery import (
    BackupContractError,
    BackupIntegrityError,
    BetaBackupRecovery,
    OwnerStoreSource,
    PrivateBackupDestination,
    owner_store_sources,
)


def _sqlite(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("INSERT INTO notes(value) VALUES (?)", ("private sentinel",))


def _service(tmp_path: Path) -> tuple[BetaBackupRecovery, Path, Path]:
    database = tmp_path / "owner.sqlite3"
    files = tmp_path / "files"
    files.mkdir()
    (files / "document.bin").write_bytes(b"private document bytes")
    _sqlite(database)
    service = BetaBackupRecovery(
        sources=(
            OwnerStoreSource("owner_database", "sqlite", database),
            OwnerStoreSource("owner_files", "directory", files),
            OwnerStoreSource("missing_store", "sqlite", tmp_path / "missing.sqlite3"),
        )
    )
    return service, database, files


def test_inventory_is_path_free_and_excludes_beta_sessions(tmp_path: Path) -> None:
    settings = Settings(
        question_bank_db=tmp_path / "question-bank.sqlite3",
        question_media_dir=tmp_path / "question-media",
        private_library_db=tmp_path / "private-library.sqlite3",
        private_library_dir=tmp_path / "private-library-files",
        question_capture_db=tmp_path / "question-capture.sqlite3",
        question_capture_dir=tmp_path / "question-capture-files",
        personal_question_library_db=tmp_path / "personal.sqlite3",
        pdf_import_db=tmp_path / "pdf.sqlite3",
        pdf_import_dir=tmp_path / "pdf-files",
        lesson_plan_db=tmp_path / "lesson.sqlite3",
        exam_paper_db=tmp_path / "paper.sqlite3",
        exam_paper_asset_dir=tmp_path / "paper-assets",
        teacher_memory_db=tmp_path / "memory.sqlite3",
        beta_session_db=tmp_path / "sessions.sqlite3",
    )
    sources = owner_store_sources(settings)
    inventory = BetaBackupRecovery(sources=sources).inventory()
    serialized = json.dumps([item.model_dump() for item in inventory])

    assert "beta_session" not in {source.store_id for source in sources}
    assert str(tmp_path) not in serialized
    assert all(set(item.model_dump()) == {"store_id", "kind", "status", "file_count"} for item in inventory)


def test_private_confirmation_is_required(tmp_path: Path) -> None:
    with pytest.raises(BackupContractError, match="PRIVATE_DESTINATION_CONFIRMATION_REQUIRED"):
        PrivateBackupDestination(tmp_path / "backups", private_storage_confirmed=False)


def test_backup_verify_and_restore_drill_are_content_complete_and_non_destructive(
    tmp_path: Path,
) -> None:
    service, database, source_files = _service(tmp_path)
    destination = PrivateBackupDestination(
        tmp_path / "backups", private_storage_confirmed=True
    )

    manifest = service.create_backup(destination)
    backup_root = destination.root / manifest.backup_id
    verification = service.verify_backup(backup_root)
    drill = service.restore_drill(backup_root)

    assert [store.status for store in manifest.stores] == ["captured", "captured", "missing"]
    assert verification.status == "verified"
    assert verification.file_count == 2
    assert drill.status == "restored_and_verified"
    assert drill.sqlite_integrity_checks == 1
    assert database.exists()
    assert (source_files / "document.bin").read_bytes() == b"private document bytes"
    with sqlite3.connect(backup_root / "payload" / "owner_database" / "store.sqlite3") as connection:
        assert connection.execute("SELECT value FROM notes").fetchone()[0] == "private sentinel"


def test_payload_tampering_fails_verification_and_restore_drill(tmp_path: Path) -> None:
    service, _, _ = _service(tmp_path)
    destination = PrivateBackupDestination(
        tmp_path / "backups", private_storage_confirmed=True
    )
    manifest = service.create_backup(destination)
    backup_root = destination.root / manifest.backup_id
    target = backup_root / "payload" / "owner_files" / "document.bin"
    target.write_bytes(b"tampered")

    with pytest.raises(BackupIntegrityError, match="BACKUP_FILE_SIZE_MISMATCH"):
        service.verify_backup(backup_root)
    with pytest.raises(BackupIntegrityError):
        service.restore_drill(backup_root)


def test_manifest_tampering_fails_before_payload_is_read(tmp_path: Path) -> None:
    service, _, _ = _service(tmp_path)
    destination = PrivateBackupDestination(
        tmp_path / "backups", private_storage_confirmed=True
    )
    manifest = service.create_backup(destination)
    backup_root = destination.root / manifest.backup_id
    manifest_path = backup_root / "manifest.json"
    manifest_path.write_text(
        manifest_path.read_text(encoding="utf-8").replace("owner_files", "other_files"),
        encoding="utf-8",
    )

    with pytest.raises(BackupIntegrityError, match="BACKUP_MANIFEST_CHECKSUM_MISMATCH"):
        service.verify_backup(backup_root)


def test_unlisted_payload_file_fails_closed(tmp_path: Path) -> None:
    service, _, _ = _service(tmp_path)
    destination = PrivateBackupDestination(
        tmp_path / "backups", private_storage_confirmed=True
    )
    manifest = service.create_backup(destination)
    backup_root = destination.root / manifest.backup_id
    (backup_root / "payload" / "unexpected.bin").write_bytes(b"not in manifest")

    with pytest.raises(BackupIntegrityError, match="BACKUP_PAYLOAD_FILE_SET_MISMATCH"):
        service.verify_backup(backup_root)
