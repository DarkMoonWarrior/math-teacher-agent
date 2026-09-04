from __future__ import annotations

import json
import hashlib
import sqlite3
import stat
from datetime import datetime, timedelta, timezone
from io import BytesIO
from types import SimpleNamespace
from pathlib import Path

import pytest
from PIL import Image

from app.core.config import Settings
from app.modules.beta_recovery import (
    BackupContractError,
    BackupIntegrityError,
    BetaBackupRecovery,
    BetaBackupRetention,
    OwnerStoreSource,
    PrivateBackupDestination,
    owner_store_sources,
)
from app.modules.data_lifecycle import OwnerDeletionLedger
from app.modules.private_library import LibraryIngestCommand, PrivateLibrary


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
    assert "owner_deletion_ledger" not in {source.store_id for source in sources}
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


def _mark_reparse(monkeypatch, path: Path) -> None:
    """Exercise Windows reparse handling without requiring symlink privileges."""
    original = Path.lstat

    def lstat(item, *args, **kwargs):
        info = original(item, *args, **kwargs)
        if item.absolute() == path.absolute():
            return SimpleNamespace(st_mode=info.st_mode,
                                   st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT)
        return info

    monkeypatch.setattr(Path, "lstat", lstat)


@pytest.mark.parametrize("entry", ["destination", "source_parent", "backup", "payload"])
def test_backup_rejects_reparse_paths_before_reading_or_writing(tmp_path, monkeypatch, entry):
    live = tmp_path / "live"
    live.mkdir()
    service, _, _ = _service(live)
    destination = PrivateBackupDestination(tmp_path / "backups", private_storage_confirmed=True)
    manifest = service.create_backup(destination)
    backup = destination.root / manifest.backup_id
    blocked = {"destination": destination.root, "source_parent": live,
               "backup": backup, "payload": backup / "payload"}[entry]
    _mark_reparse(monkeypatch, blocked)
    with pytest.raises((BackupContractError, BackupIntegrityError)):
        if entry in ("backup", "payload"):
            service.verify_backup(backup)
        else:
            service.create_backup(destination)
    assert len(list(destination.root.glob("backup_*"))) == 1


def test_source_descriptor_cannot_escape_payload_before_snapshot(tmp_path):
    database = tmp_path / "owner.sqlite3"
    _sqlite(database)
    with pytest.raises(BackupContractError):
        BetaBackupRecovery(sources=(OwnerStoreSource("../escape", "sqlite", database),))


def test_normalized_link_is_rejected_at_destination_input(tmp_path, monkeypatch):
    # Model resolve() dereferencing a link: validation must see the original path.
    alias, target = tmp_path / "alias", tmp_path / "target"
    alias.mkdir()
    target.mkdir()
    original_resolve = Path.resolve
    original_link = Path.is_symlink
    monkeypatch.setattr(Path, "resolve", lambda path, *a, **kw:
                        target if path == alias else original_resolve(path, *a, **kw))
    monkeypatch.setattr(Path, "is_symlink", lambda path: path == alias or original_link(path))
    with pytest.raises(BackupContractError):
        destination = PrivateBackupDestination(alias, private_storage_confirmed=True)
        destination.prepare(sources=())
    assert not (target / ".math-ai-private-backup-root").exists()


def _set_backup_created_at(backup: Path, created_at: datetime) -> None:
    manifest_path = backup / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["created_at"] = created_at.isoformat()
    encoded = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    manifest_path.write_bytes(encoded)
    (backup / "manifest.sha256").write_text(
        hashlib.sha256(encoded).hexdigest() + "\n",
        encoding="ascii",
    )


def test_backup_retention_is_preview_first_and_only_prunes_verified_expired_backups(tmp_path: Path) -> None:
    service, _, _ = _service(tmp_path)
    destination = PrivateBackupDestination(tmp_path / "backups", private_storage_confirmed=True)
    old_manifest = service.create_backup(destination)
    recent_manifest = service.create_backup(destination)
    now = datetime(2026, 9, 5, tzinfo=timezone.utc)
    old = destination.root / old_manifest.backup_id
    recent = destination.root / recent_manifest.backup_id
    _set_backup_created_at(old, now - timedelta(days=31))
    _set_backup_created_at(recent, now - timedelta(days=2))
    malformed = destination.root / "backup_malformed"
    malformed.mkdir()

    retention = BetaBackupRetention(service)
    preview = retention.preview(destination.root, now=now)
    assert preview.expired_backups == 1
    assert preview.retained_backups == 1
    assert preview.unclassifiable_entries == 1
    assert old.exists() and recent.exists() and malformed.exists()

    with pytest.raises(BackupContractError, match="BACKUP_RETENTION_CONFIRMATION_REQUIRED"):
        retention.prune(destination.root, confirmed=False, now=now)
    assert old.exists()

    result = retention.prune(destination.root, confirmed=True, now=now)
    assert result.deleted_backups == 1
    assert not old.exists()
    assert recent.exists()
    assert malformed.exists()


def test_restore_drill_suppresses_owner_deleted_object_from_older_backup(tmp_path: Path) -> None:
    library = PrivateLibrary(tmp_path / "library.sqlite3", tmp_path / "library-files")
    image = BytesIO()
    Image.new("RGB", (400, 240), "white").save(image, format="PNG")
    item = library.ingest(
        LibraryIngestCommand(title="synthetic", owner_id="alpha"),
        filename="synthetic.png",
        content=image.getvalue(),
    )
    ledger = OwnerDeletionLedger(tmp_path / "ledger.sqlite3")
    service = BetaBackupRecovery(
        sources=(
            OwnerStoreSource("private_library", "sqlite", library.database_path),
            OwnerStoreSource("private_library_files", "directory", library.file_root),
        ),
        deletion_ledger=ledger,
    )
    destination = PrivateBackupDestination(tmp_path / "backups", private_storage_confirmed=True)
    manifest = service.create_backup(destination)
    ledger.record(object_kind="library_item", object_id=item.library_item_id, owner_id="alpha")

    report = service.restore_drill(destination.root / manifest.backup_id)
    assert report.suppressed_deletions == 1
