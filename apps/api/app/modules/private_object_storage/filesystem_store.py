from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import stat
import uuid
from pathlib import Path
from typing import BinaryIO

from app.core.deletion import is_link_or_reparse

from .contracts import (
    PrivateObjectBinding,
    PrivateObjectConflict,
    PrivateObjectDeleteReceipt,
    PrivateObjectIntegrityError,
    PrivateObjectNotFound,
    PrivateObjectPutOutcome,
    PrivateObjectReceipt,
    PrivateObjectScope,
    PrivateObjectStoreError,
)
from .namespace import PrivateObjectNamespace


_ROOT_MARKER = ".math-ai-private-object-root"
_ROOT_MARKER_CONTENT = "math-ai private object store v1\n"
_ENVELOPE_MAGIC = b"MATH_AI_PRIVATE_OBJECT_V1\n"
_ENVELOPE_SCHEMA = "m14.private-object-envelope.v1"
_CHECKSUM = re.compile(r"^[0-9a-f]{64}$")
_MAX_HEADER_BYTES = 512
_MAX_OBJECT_BYTES = 128 * 1024 * 1024


class FilesystemPrivateObjectStore:
    """Atomic, no-overwrite byte storage behind authorized private bindings.

    This Adapter is intentionally local-filesystem only. The namespace owns
    identity and retention decisions; this class owns byte integrity and safe IO.
    """

    def __init__(
        self,
        *,
        root: Path,
        namespace: PrivateObjectNamespace,
        private_storage_confirmed: bool,
    ) -> None:
        if not private_storage_confirmed:
            raise PrivateObjectStoreError(
                "PRIVATE_OBJECT_ROOT_CONFIRMATION_REQUIRED"
            )
        self._requested_root = root.absolute()
        self._namespace = namespace
        self._reject_link_ancestors(self._requested_root)
        self.root = self._requested_root.resolve()

    def prepare(self) -> None:
        self._reject_link_ancestors(self._requested_root)
        if self.root.exists():
            if not self.root.is_dir() or is_link_or_reparse(self.root):
                raise PrivateObjectStoreError("PRIVATE_OBJECT_ROOT_INVALID")
            marker = self.root / _ROOT_MARKER
            if not marker.exists() and any(self.root.iterdir()):
                raise PrivateObjectStoreError("PRIVATE_OBJECT_ROOT_NOT_EMPTY")
        else:
            self.root.mkdir(parents=True, exist_ok=False)
        self._reject_link_ancestors(self.root)
        marker = self.root / _ROOT_MARKER
        if not marker.exists():
            try:
                with marker.open("x", encoding="utf-8") as stream:
                    stream.write(_ROOT_MARKER_CONTENT)
                    stream.flush()
                    os.fsync(stream.fileno())
            except FileExistsError:
                pass
        self._assert_prepared()

    def put_bytes(
        self,
        *,
        scope: PrivateObjectScope,
        binding: PrivateObjectBinding,
        logical_id: str,
        content: bytes,
    ) -> PrivateObjectReceipt:
        if not isinstance(content, bytes) or len(content) > _MAX_OBJECT_BYTES:
            raise PrivateObjectStoreError("PRIVATE_OBJECT_CONTENT_INVALID")
        target = self._authorized_path(
            scope=scope,
            binding=binding,
            logical_id=logical_id,
            create_parent=True,
        )
        checksum = hashlib.sha256(content).hexdigest()
        receipt = PrivateObjectReceipt(
            outcome=PrivateObjectPutOutcome.CREATED,
            byte_length=len(content),
            checksum=checksum,
        )
        pending = target.parent / f".pending-{uuid.uuid4().hex}"
        pending_node: tuple[int, int] | None = None
        try:
            with pending.open("xb") as stream:
                opened = os.fstat(stream.fileno())
                pending_node = (opened.st_dev, opened.st_ino)
                self._write_envelope(stream, content=content, checksum=checksum)
            try:
                os.link(pending, target)
            except FileExistsError:
                existing_content, existing = self._read_envelope(target)
                if not (
                    existing.byte_length == len(content)
                    and hmac.compare_digest(existing.checksum, checksum)
                    and hmac.compare_digest(existing_content, content)
                ):
                    raise PrivateObjectConflict("PRIVATE_OBJECT_CONTENT_CONFLICT")
                return PrivateObjectReceipt(
                    outcome=PrivateObjectPutOutcome.ALREADY_PRESENT,
                    byte_length=existing.byte_length,
                    checksum=existing.checksum,
                )
            return receipt
        except (PrivateObjectConflict, PrivateObjectIntegrityError):
            raise
        except OSError:
            raise PrivateObjectStoreError("PRIVATE_OBJECT_WRITE_FAILED") from None
        finally:
            if pending_node is not None and pending.parent == target.parent:
                try:
                    current = pending.lstat()
                    current_node = (current.st_dev, current.st_ino)
                    if (
                        current_node == pending_node
                        and stat.S_ISREG(current.st_mode)
                        and not is_link_or_reparse(pending)
                    ):
                        pending.unlink()
                except OSError:
                    pass

    def read_bytes(
        self,
        *,
        scope: PrivateObjectScope,
        binding: PrivateObjectBinding,
        logical_id: str,
    ) -> bytes:
        target = self._authorized_path(
            scope=scope,
            binding=binding,
            logical_id=logical_id,
            create_parent=False,
        )
        if not target.exists():
            raise PrivateObjectNotFound("PRIVATE_OBJECT_NOT_FOUND")
        content, _ = self._read_envelope(target)
        return content

    def delete(
        self,
        *,
        scope: PrivateObjectScope,
        binding: PrivateObjectBinding,
        logical_id: str,
        expected_checksum: str,
    ) -> PrivateObjectDeleteReceipt:
        if not isinstance(expected_checksum, str) or not _CHECKSUM.fullmatch(
            expected_checksum
        ):
            raise PrivateObjectStoreError("PRIVATE_OBJECT_CHECKSUM_INVALID")
        target = self._authorized_path(
            scope=scope,
            binding=binding,
            logical_id=logical_id,
            create_parent=False,
        )
        if not target.exists():
            return PrivateObjectDeleteReceipt(deleted=False)
        before = self._safe_file_stat(target)
        _, receipt = self._read_envelope(target)
        if not hmac.compare_digest(receipt.checksum, expected_checksum):
            raise PrivateObjectConflict("PRIVATE_OBJECT_DELETE_CONFLICT")
        after = self._safe_file_stat(target)
        if self._file_identity(before) != self._file_identity(after):
            raise PrivateObjectConflict("PRIVATE_OBJECT_DELETE_CONFLICT")
        try:
            target.unlink()
        except OSError:
            raise PrivateObjectStoreError("PRIVATE_OBJECT_DELETE_FAILED") from None
        return PrivateObjectDeleteReceipt(deleted=True)

    def _authorized_path(
        self,
        *,
        scope: PrivateObjectScope,
        binding: PrivateObjectBinding,
        logical_id: str,
        create_parent: bool,
    ) -> Path:
        storage_key = self._namespace.authorize(
            scope=scope,
            binding=binding,
            logical_id=logical_id,
        )
        self._assert_prepared()
        parts = storage_key.split("/")
        target = self.root.joinpath(*parts)
        try:
            target.relative_to(self.root)
        except ValueError:
            raise PrivateObjectStoreError("PRIVATE_OBJECT_PATH_INVALID") from None
        self._prepare_parent(target.parent, create=create_parent)
        if target.exists() and is_link_or_reparse(target):
            raise PrivateObjectStoreError("PRIVATE_OBJECT_LINK_NOT_ALLOWED")
        return target

    def _prepare_parent(self, parent: Path, *, create: bool) -> None:
        current = self.root
        for part in parent.relative_to(self.root).parts:
            current = current / part
            if current.exists():
                if not current.is_dir() or is_link_or_reparse(current):
                    raise PrivateObjectStoreError("PRIVATE_OBJECT_LINK_NOT_ALLOWED")
            elif create:
                try:
                    current.mkdir()
                except FileExistsError:
                    pass
                if not current.is_dir() or is_link_or_reparse(current):
                    raise PrivateObjectStoreError("PRIVATE_OBJECT_LINK_NOT_ALLOWED")
            else:
                break

    def _assert_prepared(self) -> None:
        self._reject_link_ancestors(self.root)
        marker = self.root / _ROOT_MARKER
        if (
            not self.root.is_dir()
            or is_link_or_reparse(self.root)
            or not marker.is_file()
            or is_link_or_reparse(marker)
        ):
            raise PrivateObjectStoreError("PRIVATE_OBJECT_ROOT_NOT_PREPARED")
        try:
            marker_content = marker.read_text(encoding="utf-8")
        except OSError:
            raise PrivateObjectStoreError("PRIVATE_OBJECT_ROOT_NOT_PREPARED") from None
        if marker_content != _ROOT_MARKER_CONTENT:
            raise PrivateObjectStoreError("PRIVATE_OBJECT_ROOT_NOT_PREPARED")

    @staticmethod
    def _write_envelope(
        stream: BinaryIO,
        *,
        content: bytes,
        checksum: str,
    ) -> None:
        header = json.dumps(
            {
                "byte_length": len(content),
                "checksum": checksum,
                "schema": _ENVELOPE_SCHEMA,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        stream.write(_ENVELOPE_MAGIC)
        stream.write(header)
        stream.write(b"\n")
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())

    @classmethod
    def _read_envelope(cls, path: Path) -> tuple[bytes, PrivateObjectReceipt]:
        info = cls._safe_file_stat(path)
        if info.st_size > _MAX_OBJECT_BYTES + len(_ENVELOPE_MAGIC) + _MAX_HEADER_BYTES:
            raise PrivateObjectIntegrityError("PRIVATE_OBJECT_INTEGRITY_FAILED")
        try:
            with path.open("rb") as stream:
                if stream.readline(len(_ENVELOPE_MAGIC) + 1) != _ENVELOPE_MAGIC:
                    raise PrivateObjectIntegrityError("PRIVATE_OBJECT_INTEGRITY_FAILED")
                header_bytes = stream.readline(_MAX_HEADER_BYTES + 1)
                if not header_bytes.endswith(b"\n") or len(header_bytes) > _MAX_HEADER_BYTES:
                    raise PrivateObjectIntegrityError("PRIVATE_OBJECT_INTEGRITY_FAILED")
                header = json.loads(header_bytes)
                content = stream.read(_MAX_OBJECT_BYTES + 1)
        except PrivateObjectIntegrityError:
            raise
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            raise PrivateObjectIntegrityError("PRIVATE_OBJECT_INTEGRITY_FAILED") from None
        if (
            not isinstance(header, dict)
            or set(header) != {"byte_length", "checksum", "schema"}
            or header.get("schema") != _ENVELOPE_SCHEMA
            or type(header.get("byte_length")) is not int
            or not isinstance(header.get("checksum"), str)
            or not _CHECKSUM.fullmatch(header["checksum"])
            or header["byte_length"] != len(content)
            or len(content) > _MAX_OBJECT_BYTES
        ):
            raise PrivateObjectIntegrityError("PRIVATE_OBJECT_INTEGRITY_FAILED")
        checksum = hashlib.sha256(content).hexdigest()
        if not hmac.compare_digest(checksum, header["checksum"]):
            raise PrivateObjectIntegrityError("PRIVATE_OBJECT_INTEGRITY_FAILED")
        return content, PrivateObjectReceipt(
            outcome=PrivateObjectPutOutcome.ALREADY_PRESENT,
            byte_length=len(content),
            checksum=checksum,
        )

    @staticmethod
    def _safe_file_stat(path: Path) -> os.stat_result:
        if is_link_or_reparse(path):
            raise PrivateObjectStoreError("PRIVATE_OBJECT_LINK_NOT_ALLOWED")
        try:
            info = path.lstat()
        except OSError:
            raise PrivateObjectIntegrityError("PRIVATE_OBJECT_INTEGRITY_FAILED") from None
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise PrivateObjectIntegrityError("PRIVATE_OBJECT_INTEGRITY_FAILED")
        return info

    @staticmethod
    def _file_identity(info: os.stat_result) -> tuple[int, int, int, int]:
        return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)

    @staticmethod
    def _reject_link_ancestors(path: Path) -> None:
        for candidate in (path, *path.parents):
            if is_link_or_reparse(candidate):
                raise PrivateObjectStoreError("PRIVATE_OBJECT_LINK_NOT_ALLOWED")
