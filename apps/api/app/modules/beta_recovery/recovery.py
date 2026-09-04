from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.modules.beta_recovery.schemas import (
    BackupFileRecord,
    BackupInventoryItem,
    BackupManifest,
    BackupRetentionPreview,
    BackupRetentionResult,
    BackupSourceKind,
    BackupStoreRecord,
    BackupVerification,
    RestoreDrillReport,
)
from app.modules.data_lifecycle import OwnerDeletionLedger, RestoredOwnerDataFilter


class BackupContractError(ValueError):
    pass


class BackupIntegrityError(RuntimeError):
    pass


@dataclass(frozen=True)
class OwnerStoreSource:
    """Internal source descriptor; filesystem paths never enter public schemas."""

    store_id: str
    kind: BackupSourceKind
    path: Path


class PrivateBackupDestination:
    """Explicit operator-owned destination for private Beta backups.

    The confirmation is intentionally required at construction. Production operators
    should point this root at an encrypted private volume or an equivalently protected
    storage mount; it must never be a public/static directory.
    """

    def __init__(self, root: Path, *, private_storage_confirmed: bool) -> None:
        if not private_storage_confirmed:
            raise BackupContractError("PRIVATE_DESTINATION_CONFIRMATION_REQUIRED")
        # Keep the lexical path until every existing component has been checked.
        # resolve() first would hide a link/junction supplied by the operator.
        self._requested_root = root.absolute()
        self._reject_links_in_existing_ancestors(self._requested_root)
        self.root = self._requested_root.resolve()

    def prepare(self, *, sources: tuple[OwnerStoreSource, ...]) -> None:
        self._reject_links_in_existing_ancestors(self._requested_root)
        self._reject_links_in_existing_ancestors(self.root)
        for source in sources:
            self._reject_links_in_existing_ancestors(source.path.absolute())
            resolved_source = source.path.resolve()
            if self.root == resolved_source or self._is_within(resolved_source, self.root):
                raise BackupContractError("BACKUP_DESTINATION_CONTAINS_SOURCE")
            if source.kind == "directory" and self._is_within(self.root, resolved_source):
                raise BackupContractError("BACKUP_DESTINATION_INSIDE_SOURCE")
        self.root.mkdir(parents=True, exist_ok=True)
        if not self.root.is_dir() or self._is_link_or_junction(self.root):
            raise BackupContractError("PRIVATE_DESTINATION_INVALID")
        marker = self.root / ".math-ai-private-backup-root"
        if self._is_link_or_junction(marker):
            raise BackupContractError("PRIVATE_DESTINATION_MARKER_INVALID")
        if not marker.exists():
            marker.write_text("private closed beta backups\n", encoding="utf-8")

    @staticmethod
    def _is_within(candidate: Path, parent: Path) -> bool:
        try:
            candidate.relative_to(parent)
            return True
        except ValueError:
            return False

    @classmethod
    def _reject_links_in_existing_ancestors(cls, path: Path) -> None:
        for current in (path, *path.parents):
            if cls._is_link_or_junction(current):
                raise BackupContractError("PRIVATE_DESTINATION_LINK_NOT_ALLOWED")

    @staticmethod
    def _is_link_or_junction(path: Path) -> bool:
        # All Windows reparse points are unsafe here, not just directory junctions.
        is_junction = getattr(path, "is_junction", None)
        if path.is_symlink() or bool(is_junction and is_junction()):
            return True
        try:
            info = path.lstat()
        except FileNotFoundError:
            return False
        return stat.S_ISLNK(info.st_mode) or bool(
            getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
        )


class BetaBackupRecovery:
    """Create, verify and drill private backups without touching live restore targets."""

    _MANIFEST_NAME = "manifest.json"
    _MANIFEST_CHECKSUM_NAME = "manifest.sha256"
    _PAYLOAD_DIR = "payload"

    def __init__(
        self,
        *,
        sources: tuple[OwnerStoreSource, ...],
        deletion_ledger: OwnerDeletionLedger | None = None,
        restored_data_filter: RestoredOwnerDataFilter | None = None,
    ) -> None:
        if any(not re.fullmatch(r"[a-z][a-z0-9_]{1,63}", source.store_id)
               or source.kind not in ("sqlite", "directory") for source in sources):
            raise BackupContractError("SOURCE_DESCRIPTOR_INVALID")
        store_ids = [source.store_id for source in sources]
        if len(store_ids) != len(set(store_ids)):
            raise BackupContractError("DUPLICATE_STORE_ID")
        self.sources = sources
        self.deletion_ledger = deletion_ledger
        self.restored_data_filter = restored_data_filter or RestoredOwnerDataFilter()

    def inventory(self) -> list[BackupInventoryItem]:
        items: list[BackupInventoryItem] = []
        for source in self.sources:
            PrivateBackupDestination._reject_links_in_existing_ancestors(source.path.absolute())
            file_count = 0
            if source.path.exists():
                if source.kind == "sqlite" and not source.path.is_file():
                    raise BackupContractError("SQLITE_SOURCE_INVALID")
                file_count = 1 if source.kind == "sqlite" else len(self._directory_files(source.path))
            items.append(
                BackupInventoryItem(
                    store_id=source.store_id,
                    kind=source.kind,
                    status="ready" if source.path.exists() else "missing",
                    file_count=file_count,
                )
            )
        return items

    def create_backup(self, destination: PrivateBackupDestination) -> BackupManifest:
        destination.prepare(sources=self.sources)
        backup_id = f"backup_{uuid.uuid4().hex}"
        staging = (destination.root / f".{backup_id}.staging").resolve()
        final = (destination.root / backup_id).resolve()
        self._assert_child(staging, destination.root)
        self._assert_child(final, destination.root)
        staging.mkdir(parents=False, exist_ok=False)
        payload_root = staging / self._PAYLOAD_DIR
        payload_root.mkdir()

        try:
            stores = [self._capture_source(source, payload_root) for source in self.sources]
            manifest = BackupManifest(
                backup_id=backup_id,
                created_at=datetime.now(timezone.utc),
                stores=stores,
            )
            manifest_bytes = manifest.model_dump_json(indent=2).encode("utf-8")
            (staging / self._MANIFEST_NAME).write_bytes(manifest_bytes)
            (staging / self._MANIFEST_CHECKSUM_NAME).write_text(
                self._sha256_bytes(manifest_bytes) + "\n", encoding="ascii"
            )
            self.verify_backup(staging)
            staging.rename(final)
            return manifest
        except Exception:
            if staging.exists() and staging.parent == destination.root:
                # Never recursively clean a staging tree that acquired a link.
                PrivateBackupDestination._reject_links_in_existing_ancestors(staging)
                self._directory_files(staging)
                shutil.rmtree(staging)
            raise

    def verify_backup(self, backup_root: Path) -> BackupVerification:
        PrivateBackupDestination._reject_links_in_existing_ancestors(backup_root.absolute())
        root = backup_root.resolve()
        if not root.is_dir() or self._is_link_or_junction(root):
            raise BackupIntegrityError("BACKUP_DIRECTORY_INVALID")
        manifest_path = root / self._MANIFEST_NAME
        checksum_path = root / self._MANIFEST_CHECKSUM_NAME
        if any(
            not path.is_file() or self._is_link_or_junction(path)
            for path in (manifest_path, checksum_path)
        ):
            raise BackupIntegrityError("BACKUP_MANIFEST_MISSING")
        try:
            manifest_bytes = manifest_path.read_bytes()
            expected_manifest_checksum = checksum_path.read_text(encoding="ascii").strip()
        except OSError as exc:
            raise BackupIntegrityError("BACKUP_MANIFEST_MISSING") from exc
        if self._sha256_bytes(manifest_bytes) != expected_manifest_checksum:
            raise BackupIntegrityError("BACKUP_MANIFEST_CHECKSUM_MISMATCH")
        try:
            manifest = BackupManifest.model_validate(json.loads(manifest_bytes))
        except (json.JSONDecodeError, ValueError) as exc:
            raise BackupIntegrityError("BACKUP_MANIFEST_INVALID") from exc

        file_count = 0
        total_bytes = 0
        seen_paths: set[str] = set()
        payload_path = root / self._PAYLOAD_DIR
        PrivateBackupDestination._reject_links_in_existing_ancestors(payload_path)
        payload_root = payload_path.resolve()
        actual_paths = {
            path.relative_to(payload_root).as_posix()
            for path in self._directory_files(payload_root)
        }
        for store in manifest.stores:
            for record in store.files:
                if record.relative_path in seen_paths:
                    raise BackupIntegrityError("BACKUP_FILE_DUPLICATED")
                seen_paths.add(record.relative_path)
                relative = Path(record.relative_path)
                if (relative.is_absolute() or relative.drive or ".." in relative.parts
                        or "\\" in record.relative_path or ":" in record.relative_path):
                    raise BackupIntegrityError("BACKUP_PATH_OUTSIDE_ROOT")
                original = payload_root / relative
                PrivateBackupDestination._reject_links_in_existing_ancestors(original)
                candidate = original.resolve()
                self._assert_payload_file(candidate, payload_root)
                if candidate.stat().st_size != record.size_bytes:
                    raise BackupIntegrityError("BACKUP_FILE_SIZE_MISMATCH")
                if self._sha256_file(candidate) != record.sha256:
                    raise BackupIntegrityError("BACKUP_FILE_CHECKSUM_MISMATCH")
                file_count += 1
                total_bytes += record.size_bytes
        if actual_paths != seen_paths:
            raise BackupIntegrityError("BACKUP_PAYLOAD_FILE_SET_MISMATCH")
        return BackupVerification(
            backup_id=manifest.backup_id,
            store_count=len(manifest.stores),
            file_count=file_count,
            total_bytes=total_bytes,
        )

    def restore_drill(self, backup_root: Path) -> RestoreDrillReport:
        verification = self.verify_backup(backup_root)
        manifest = BackupManifest.model_validate_json(
            (backup_root.resolve() / self._MANIFEST_NAME).read_text(encoding="utf-8")
        )
        sqlite_checks = 0
        suppressed_deletions = 0
        with tempfile.TemporaryDirectory(prefix="math-ai-beta-restore-drill-") as temp_name:
            restored_root = Path(temp_name) / self._PAYLOAD_DIR
            restored_root.mkdir()
            source_root = (backup_root.resolve() / self._PAYLOAD_DIR).resolve()
            restored_sqlite: list[Path] = []
            for store in manifest.stores:
                for record in store.files:
                    source_file = (source_root / record.relative_path).resolve()
                    self._assert_payload_file(source_file, source_root)
                    restored_file = (restored_root / record.relative_path).resolve()
                    self._assert_child(restored_file, restored_root.resolve())
                    restored_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source_file, restored_file)
                    self._assert_payload_file(restored_file, restored_root.resolve())
                    if restored_file.stat().st_size != record.size_bytes:
                        raise BackupIntegrityError("RESTORE_FILE_SIZE_MISMATCH")
                    if self._sha256_file(restored_file) != record.sha256:
                        raise BackupIntegrityError("RESTORE_FILE_CHECKSUM_MISMATCH")
                    if store.kind == "sqlite":
                        restored_sqlite.append(restored_file)
            if self.deletion_ledger is not None:
                suppressed_deletions = self.restored_data_filter.apply(
                    restored_root,
                    self.deletion_ledger.list(),
                )
            for restored_file in restored_sqlite:
                self._verify_sqlite_integrity(restored_file)
                sqlite_checks += 1
        return RestoreDrillReport(
            backup_id=verification.backup_id,
            store_count=verification.store_count,
            file_count=verification.file_count,
            sqlite_integrity_checks=sqlite_checks,
            suppressed_deletions=suppressed_deletions,
            total_bytes=verification.total_bytes,
        )

    def _capture_source(self, source: OwnerStoreSource, payload_root: Path) -> BackupStoreRecord:
        PrivateBackupDestination._reject_links_in_existing_ancestors(source.path.absolute())
        if not source.path.exists():
            return BackupStoreRecord(
                store_id=source.store_id,
                kind=source.kind,
                status="missing",
                files=[],
            )
        store_root = payload_root / source.store_id
        store_root.mkdir()
        if source.kind == "sqlite":
            if not source.path.is_file() or self._is_link_or_junction(source.path):
                raise BackupContractError("SQLITE_SOURCE_INVALID")
            target = store_root / "store.sqlite3"
            self._snapshot_sqlite(source.path, target)
            files = [self._file_record(target, payload_root)]
        else:
            if not source.path.is_dir() or self._is_link_or_junction(source.path):
                raise BackupContractError("DIRECTORY_SOURCE_INVALID")
            files = []
            for source_file in self._directory_files(source.path):
                relative = source_file.relative_to(source.path)
                target = store_root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source_file, target)
                files.append(self._file_record(target, payload_root))
        return BackupStoreRecord(
            store_id=source.store_id,
            kind=source.kind,
            status="captured",
            files=files,
        )

    @classmethod
    def _directory_files(cls, root: Path) -> list[Path]:
        PrivateBackupDestination._reject_links_in_existing_ancestors(root.absolute())
        if not root.is_dir() or cls._is_link_or_junction(root):
            raise BackupContractError("DIRECTORY_SOURCE_LINK_NOT_ALLOWED")
        files: list[Path] = []
        pending = [root]
        while pending:
            current = pending.pop()
            with os.scandir(current) as entries:
                for entry in sorted(entries, key=lambda item: item.name):
                    candidate = Path(entry.path)
                    if cls._is_link_or_junction(candidate):
                        raise BackupContractError("DIRECTORY_SOURCE_LINK_NOT_ALLOWED")
                    if entry.is_dir(follow_symlinks=False):
                        pending.append(candidate)
                    elif entry.is_file(follow_symlinks=False):
                        files.append(candidate)
                    else:
                        raise BackupContractError("DIRECTORY_SOURCE_ENTRY_INVALID")
        files.sort()
        return files

    @staticmethod
    def _snapshot_sqlite(source: Path, target: Path) -> None:
        source_uri = f"{source.resolve().as_uri()}?mode=ro"
        source_connection = sqlite3.connect(source_uri, uri=True)
        target_connection = sqlite3.connect(target)
        try:
            source_connection.backup(target_connection)
            target_connection.commit()
        finally:
            target_connection.close()
            source_connection.close()

    @staticmethod
    def _verify_sqlite_integrity(path: Path) -> None:
        uri = f"{path.resolve().as_uri()}?mode=ro"
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(uri, uri=True)
            result = connection.execute("PRAGMA integrity_check").fetchone()
        except sqlite3.Error as exc:
            raise BackupIntegrityError("RESTORE_SQLITE_INVALID") from exc
        finally:
            if connection is not None:
                connection.close()
        if result is None or result[0] != "ok":
            raise BackupIntegrityError("RESTORE_SQLITE_INTEGRITY_FAILED")

    @classmethod
    def _file_record(cls, path: Path, payload_root: Path) -> BackupFileRecord:
        return BackupFileRecord(
            relative_path=path.relative_to(payload_root).as_posix(),
            size_bytes=path.stat().st_size,
            sha256=cls._sha256_file(path),
        )

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _sha256_bytes(value: bytes) -> str:
        return hashlib.sha256(value).hexdigest()

    @classmethod
    def _assert_payload_file(cls, candidate: Path, payload_root: Path) -> None:
        cls._assert_child(candidate, payload_root)
        if not candidate.is_file() or cls._is_link_or_junction(candidate):
            raise BackupIntegrityError("BACKUP_FILE_INVALID")

    @staticmethod
    def _assert_child(candidate: Path, parent: Path) -> None:
        try:
            candidate.relative_to(parent)
        except ValueError as exc:
            raise BackupIntegrityError("BACKUP_PATH_OUTSIDE_ROOT") from exc

    @staticmethod
    def _is_link_or_junction(path: Path) -> bool:
        return PrivateBackupDestination._is_link_or_junction(path)


class BetaBackupRetention:
    """Preview and explicitly prune verified backups older than 30 days."""

    RETENTION_DAYS = 30

    def __init__(self, recovery: BetaBackupRecovery) -> None:
        self.recovery = recovery

    def preview(
        self, root: Path, *, now: datetime | None = None
    ) -> BackupRetentionPreview:
        evaluated_at = now or datetime.now(timezone.utc)
        if evaluated_at.tzinfo is None:
            raise BackupContractError("RETENTION_TIME_INVALID")
        cutoff = evaluated_at - timedelta(days=self.RETENTION_DAYS)
        expired, retained, unclassifiable = self._classify(root, cutoff=cutoff)
        return BackupRetentionPreview(
            evaluated_at=evaluated_at,
            cutoff_at=cutoff,
            retained_backups=len(retained),
            expired_backups=len(expired),
            unclassifiable_entries=unclassifiable,
        )

    def prune(
        self,
        root: Path,
        *,
        confirmed: bool,
        now: datetime | None = None,
    ) -> BackupRetentionResult:
        if not confirmed:
            raise BackupContractError("BACKUP_RETENTION_CONFIRMATION_REQUIRED")
        evaluated_at = now or datetime.now(timezone.utc)
        if evaluated_at.tzinfo is None:
            raise BackupContractError("RETENTION_TIME_INVALID")
        cutoff = evaluated_at - timedelta(days=self.RETENTION_DAYS)
        expired, retained, unclassifiable = self._classify(root, cutoff=cutoff)
        deleted = 0
        for backup in expired:
            self.recovery.verify_backup(backup)
            self.recovery._directory_files(backup)
            shutil.rmtree(backup)
            deleted += 1
        return BackupRetentionResult(
            evaluated_at=evaluated_at,
            cutoff_at=cutoff,
            retained_backups=len(retained),
            expired_backups=len(expired),
            unclassifiable_entries=unclassifiable,
            deleted_backups=deleted,
        )

    def _classify(
        self, root: Path, *, cutoff: datetime
    ) -> tuple[list[Path], list[Path], int]:
        PrivateBackupDestination._reject_links_in_existing_ancestors(root.absolute())
        resolved_root = root.resolve()
        marker = resolved_root / ".math-ai-private-backup-root"
        if (
            not resolved_root.is_dir()
            or self.recovery._is_link_or_junction(resolved_root)
            or not marker.is_file()
            or self.recovery._is_link_or_junction(marker)
        ):
            raise BackupContractError("PRIVATE_DESTINATION_INVALID")
        expired: list[Path] = []
        retained: list[Path] = []
        unclassifiable = 0
        for entry in resolved_root.iterdir():
            if entry == marker:
                continue
            if not entry.name.startswith("backup_") or not entry.is_dir():
                unclassifiable += 1
                continue
            try:
                self.recovery.verify_backup(entry)
                manifest = BackupManifest.model_validate_json(
                    (entry / self.recovery._MANIFEST_NAME).read_text(encoding="utf-8")
                )
            except (BackupContractError, BackupIntegrityError, OSError, ValueError):
                unclassifiable += 1
                continue
            if manifest.created_at.tzinfo is None:
                unclassifiable += 1
            elif manifest.created_at <= cutoff:
                expired.append(entry)
            else:
                retained.append(entry)
        return expired, retained, unclassifiable
