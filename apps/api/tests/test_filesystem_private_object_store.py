from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.modules.account_identity import VersionedHmacKeyRing
from app.modules.private_object_storage import (
    FilesystemPrivateObjectStore,
    PrivateObjectAccessDenied,
    PrivateObjectConflict,
    PrivateObjectDomain,
    PrivateObjectIntegrityError,
    PrivateObjectNamespace,
    PrivateObjectNotFound,
    PrivateObjectPutOutcome,
    PrivateObjectScope,
    PrivateObjectStoreError,
)


def _namespace() -> PrivateObjectNamespace:
    return PrivateObjectNamespace(
        key_ring=VersionedHmacKeyRing(
            current_key_id="object-2026-09",
            current_secret="filesystem-private-object-secret-0000001",
        )
    )


def _scope(*, tenant="tenant-a", owner="owner-a") -> PrivateObjectScope:
    return PrivateObjectScope(tenant_id=tenant, owner_id=owner)


def _binding(namespace: PrivateObjectNamespace):
    return namespace.bind(
        scope=_scope(),
        domain=PrivateObjectDomain.PDF_IMPORT_SOURCE,
        logical_id="document-123",
    )


def _store(root: Path, namespace: PrivateObjectNamespace):
    store = FilesystemPrivateObjectStore(
        root=root,
        namespace=namespace,
        private_storage_confirmed=True,
    )
    store.prepare()
    return store


def test_store_requires_an_explicit_private_root_and_prepare(tmp_path: Path) -> None:
    namespace = _namespace()
    with pytest.raises(
        PrivateObjectStoreError,
        match="^PRIVATE_OBJECT_ROOT_CONFIRMATION_REQUIRED$",
    ):
        FilesystemPrivateObjectStore(
            root=tmp_path / "objects",
            namespace=namespace,
            private_storage_confirmed=False,
        )

    unprepared = FilesystemPrivateObjectStore(
        root=tmp_path / "unprepared",
        namespace=namespace,
        private_storage_confirmed=True,
    )
    with pytest.raises(
        PrivateObjectStoreError,
        match="^PRIVATE_OBJECT_ROOT_NOT_PREPARED$",
    ):
        unprepared.read_bytes(
            scope=_scope(),
            binding=_binding(namespace),
            logical_id="document-123",
        )


def test_prepare_refuses_to_claim_a_nonempty_unmarked_directory(tmp_path: Path) -> None:
    root = tmp_path / "objects"
    root.mkdir()
    (root / "unrelated.txt").write_text("not this store", encoding="utf-8")
    store = FilesystemPrivateObjectStore(
        root=root,
        namespace=_namespace(),
        private_storage_confirmed=True,
    )

    with pytest.raises(
        PrivateObjectStoreError,
        match="^PRIVATE_OBJECT_ROOT_NOT_EMPTY$",
    ):
        store.prepare()

    assert (root / "unrelated.txt").read_text(encoding="utf-8") == "not this store"


def test_put_read_and_retry_are_atomic_and_idempotent(tmp_path: Path) -> None:
    namespace = _namespace()
    binding = _binding(namespace)
    store = _store(tmp_path / "objects", namespace)
    content = b"private pdf bytes"

    created = store.put_bytes(
        scope=_scope(),
        binding=binding,
        logical_id="document-123",
        content=content,
    )
    repeated = store.put_bytes(
        scope=_scope(),
        binding=binding,
        logical_id="document-123",
        content=content,
    )

    assert created.outcome == PrivateObjectPutOutcome.CREATED
    assert repeated.outcome == PrivateObjectPutOutcome.ALREADY_PRESENT
    assert created.byte_length == len(content)
    assert created.checksum == hashlib.sha256(content).hexdigest()
    assert created.checksum not in repr(created)
    assert store.read_bytes(
        scope=_scope(),
        binding=binding,
        logical_id="document-123",
    ) == content
    assert list((tmp_path / "objects").rglob(".pending-*")) == []


def test_conflicting_retry_never_overwrites_existing_content(tmp_path: Path) -> None:
    namespace = _namespace()
    binding = _binding(namespace)
    store = _store(tmp_path / "objects", namespace)
    original = b"original private bytes"
    store.put_bytes(
        scope=_scope(),
        binding=binding,
        logical_id="document-123",
        content=original,
    )

    with pytest.raises(
        PrivateObjectConflict,
        match="^PRIVATE_OBJECT_CONTENT_CONFLICT$",
    ):
        store.put_bytes(
            scope=_scope(),
            binding=binding,
            logical_id="document-123",
            content=b"different bytes",
        )

    assert store.read_bytes(
        scope=_scope(),
        binding=binding,
        logical_id="document-123",
    ) == original


@pytest.mark.parametrize("operation", ["put", "read", "delete"])
def test_cross_owner_operations_fail_before_inspecting_storage(
    tmp_path: Path,
    operation: str,
) -> None:
    namespace = _namespace()
    binding = _binding(namespace)
    store = _store(tmp_path / "objects", namespace)
    kwargs = {
        "scope": _scope(owner="owner-b"),
        "binding": binding,
        "logical_id": "document-123",
    }

    with pytest.raises(
        PrivateObjectAccessDenied,
        match="^PRIVATE_OBJECT_ACCESS_DENIED$",
    ):
        if operation == "put":
            store.put_bytes(**kwargs, content=b"other owner")
        elif operation == "read":
            store.read_bytes(**kwargs)
        else:
            store.delete(**kwargs, expected_checksum="0" * 64)


def test_corrupt_envelope_fails_closed_without_returning_bytes(tmp_path: Path) -> None:
    namespace = _namespace()
    binding = _binding(namespace)
    store = _store(tmp_path / "objects", namespace)
    store.put_bytes(
        scope=_scope(),
        binding=binding,
        logical_id="document-123",
        content=b"trusted bytes",
    )
    target = store.root.joinpath(*binding.storage_key.split("/"))
    envelope = target.read_bytes()
    target.write_bytes(envelope[:-1] + b"X")

    with pytest.raises(
        PrivateObjectIntegrityError,
        match="^PRIVATE_OBJECT_INTEGRITY_FAILED$",
    ):
        store.read_bytes(
            scope=_scope(),
            binding=binding,
            logical_id="document-123",
        )


def test_boolean_length_cannot_masquerade_as_envelope_integer(tmp_path: Path) -> None:
    namespace = _namespace()
    binding = _binding(namespace)
    store = _store(tmp_path / "objects", namespace)
    store.put_bytes(
        scope=_scope(),
        binding=binding,
        logical_id="document-123",
        content=b"X",
    )
    target = store.root.joinpath(*binding.storage_key.split("/"))
    header = json.dumps(
        {
            "byte_length": True,
            "checksum": hashlib.sha256(b"X").hexdigest(),
            "schema": "m14.private-object-envelope.v1",
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    target.write_bytes(b"MATH_AI_PRIVATE_OBJECT_V1\n" + header + b"\nX")

    with pytest.raises(
        PrivateObjectIntegrityError,
        match="^PRIVATE_OBJECT_INTEGRITY_FAILED$",
    ):
        store.read_bytes(
            scope=_scope(),
            binding=binding,
            logical_id="document-123",
        )


def test_delete_is_checksum_guarded_and_missing_is_idempotent(tmp_path: Path) -> None:
    namespace = _namespace()
    binding = _binding(namespace)
    store = _store(tmp_path / "objects", namespace)
    content = b"delete only these private bytes"
    receipt = store.put_bytes(
        scope=_scope(),
        binding=binding,
        logical_id="document-123",
        content=content,
    )

    with pytest.raises(
        PrivateObjectConflict,
        match="^PRIVATE_OBJECT_DELETE_CONFLICT$",
    ):
        store.delete(
            scope=_scope(),
            binding=binding,
            logical_id="document-123",
            expected_checksum="0" * 64,
        )

    deleted = store.delete(
        scope=_scope(),
        binding=binding,
        logical_id="document-123",
        expected_checksum=receipt.checksum,
    )
    repeated = store.delete(
        scope=_scope(),
        binding=binding,
        logical_id="document-123",
        expected_checksum=receipt.checksum,
    )

    assert deleted.deleted is True
    assert repeated.deleted is False
    with pytest.raises(PrivateObjectNotFound, match="^PRIVATE_OBJECT_NOT_FOUND$"):
        store.read_bytes(
            scope=_scope(),
            binding=binding,
            logical_id="document-123",
        )


def test_tampered_root_marker_blocks_all_io(tmp_path: Path) -> None:
    namespace = _namespace()
    binding = _binding(namespace)
    store = _store(tmp_path / "objects", namespace)
    (store.root / ".math-ai-private-object-root").write_text(
        "wrong store\n",
        encoding="utf-8",
    )

    with pytest.raises(
        PrivateObjectStoreError,
        match="^PRIVATE_OBJECT_ROOT_NOT_PREPARED$",
    ):
        store.put_bytes(
            scope=_scope(),
            binding=binding,
            logical_id="document-123",
            content=b"must not write",
        )


def test_pending_name_collision_never_deletes_unowned_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    namespace = _namespace()
    binding = _binding(namespace)
    store = _store(tmp_path / "objects", namespace)
    target = store.root.joinpath(*binding.storage_key.split("/"))
    target.parent.mkdir(parents=True)
    pending = target.parent / ".pending-fixed"
    pending.write_bytes(b"preexisting private operator file")
    monkeypatch.setattr(
        "app.modules.private_object_storage.filesystem_store.uuid.uuid4",
        lambda: SimpleNamespace(hex="fixed"),
    )

    with pytest.raises(
        PrivateObjectStoreError,
        match="^PRIVATE_OBJECT_WRITE_FAILED$",
    ):
        store.put_bytes(
            scope=_scope(),
            binding=binding,
            logical_id="document-123",
            content=b"new bytes",
        )

    assert pending.read_bytes() == b"preexisting private operator file"


def test_link_inside_object_key_is_rejected(tmp_path: Path) -> None:
    namespace = _namespace()
    binding = _binding(namespace)
    store = _store(tmp_path / "objects", namespace)
    outside = tmp_path / "outside"
    outside.mkdir()
    link = store.root / "private"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (NotImplementedError, OSError):
        pytest.skip("directory symlinks are unavailable on this platform")

    with pytest.raises(
        PrivateObjectStoreError,
        match="^PRIVATE_OBJECT_LINK_NOT_ALLOWED$",
    ):
        store.put_bytes(
            scope=_scope(),
            binding=binding,
            logical_id="document-123",
            content=b"must stay inside root",
        )

    assert list(outside.iterdir()) == []


def test_hard_linked_object_is_rejected_as_ambiguous_storage(tmp_path: Path) -> None:
    namespace = _namespace()
    binding = _binding(namespace)
    store = _store(tmp_path / "objects", namespace)
    store.put_bytes(
        scope=_scope(),
        binding=binding,
        logical_id="document-123",
        content=b"one private object",
    )
    target = store.root.joinpath(*binding.storage_key.split("/"))
    alias = target.parent / "alias"
    try:
        os.link(target, alias)
    except OSError:
        pytest.skip("hard links are unavailable on this platform")

    with pytest.raises(
        PrivateObjectIntegrityError,
        match="^PRIVATE_OBJECT_INTEGRITY_FAILED$",
    ):
        store.read_bytes(
            scope=_scope(),
            binding=binding,
            logical_id="document-123",
        )
