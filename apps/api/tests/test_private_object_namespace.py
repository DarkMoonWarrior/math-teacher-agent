from __future__ import annotations

from dataclasses import replace

import pytest

from app.modules.account_identity import VersionedHmacKeyRing
from app.modules.private_object_storage import (
    PrivateObjectAccessDenied,
    PrivateObjectBindingError,
    PrivateObjectDomain,
    PrivateObjectNamespace,
    PrivateObjectRetention,
    PrivateObjectScope,
)


_CURRENT_SECRET = "current-private-object-secret-0000000001"
_PREVIOUS_SECRET = "previous-private-object-secret-00000001"


def _namespace(*, previous=False) -> PrivateObjectNamespace:
    return PrivateObjectNamespace(
        key_ring=VersionedHmacKeyRing(
            current_key_id="object-2026-09",
            current_secret=_CURRENT_SECRET,
            previous_keys=(
                {"object-2026-08": _PREVIOUS_SECRET} if previous else None
            ),
        )
    )


def _scope(*, tenant="tenant-a", owner="owner-a") -> PrivateObjectScope:
    return PrivateObjectScope(tenant_id=tenant, owner_id=owner)


def test_bind_is_deterministic_and_does_not_expose_private_identifiers() -> None:
    namespace = _namespace()

    first = namespace.bind(
        scope=_scope(),
        domain=PrivateObjectDomain.PDF_IMPORT_SOURCE,
        logical_id="document-123",
    )
    repeated = namespace.bind(
        scope=_scope(),
        domain=PrivateObjectDomain.PDF_IMPORT_SOURCE,
        logical_id="document-123",
    )

    assert repeated == first
    assert first.storage_key.startswith("private/v1/pdf-import-source/")
    assert first.retention == PrivateObjectRetention.OWNER_LIFECYCLE
    for private_value in ("tenant-a", "owner-a", "document-123"):
        assert private_value not in first.storage_key
        assert private_value not in repr(first)
    assert first.storage_key not in repr(first)
    assert "tenant-a" not in repr(_scope())
    assert "owner-a" not in repr(_scope())


@pytest.mark.parametrize(
    ("scope", "domain", "logical_id"),
    [
        (_scope(tenant="tenant-b"), PrivateObjectDomain.PDF_IMPORT_SOURCE, "document-123"),
        (_scope(owner="owner-b"), PrivateObjectDomain.PDF_IMPORT_SOURCE, "document-123"),
        (_scope(), PrivateObjectDomain.PDF_IMPORT_CROP, "document-123"),
        (_scope(), PrivateObjectDomain.PDF_IMPORT_SOURCE, "document-456"),
    ],
)
def test_tenant_owner_domain_and_logical_object_have_separate_bindings(
    scope: PrivateObjectScope,
    domain: PrivateObjectDomain,
    logical_id: str,
) -> None:
    namespace = _namespace()
    original = namespace.bind(
        scope=_scope(),
        domain=PrivateObjectDomain.PDF_IMPORT_SOURCE,
        logical_id="document-123",
    )
    changed = namespace.bind(scope=scope, domain=domain, logical_id=logical_id)

    assert changed.storage_key != original.storage_key


@pytest.mark.parametrize(
    ("scope", "logical_id"),
    [
        (_scope(owner="owner-b"), "document-123"),
        (_scope(tenant="tenant-b"), "document-123"),
        (_scope(), "document-456"),
    ],
)
def test_authorize_fails_closed_for_a_different_authenticated_scope(
    scope: PrivateObjectScope,
    logical_id: str,
) -> None:
    namespace = _namespace()
    binding = namespace.bind(
        scope=_scope(),
        domain=PrivateObjectDomain.PDF_IMPORT_SOURCE,
        logical_id="document-123",
    )

    with pytest.raises(
        PrivateObjectAccessDenied,
        match="^PRIVATE_OBJECT_ACCESS_DENIED$",
    ):
        namespace.authorize(scope=scope, binding=binding, logical_id=logical_id)


@pytest.mark.parametrize(
    "binding_change",
    [
        {"storage_key": "private/v1/pdf-import-source/invalid"},
        {"retention": PrivateObjectRetention.TERMINAL_24H},
        {"schema_version": "m14.private-object-binding.v2"},
        {"domain": PrivateObjectDomain.PDF_IMPORT_CROP},
    ],
)
def test_authorize_rejects_tampered_bindings_with_one_sanitized_error(
    binding_change: dict[str, object],
) -> None:
    namespace = _namespace()
    binding = namespace.bind(
        scope=_scope(),
        domain=PrivateObjectDomain.PDF_IMPORT_SOURCE,
        logical_id="document-123",
    )

    with pytest.raises(PrivateObjectAccessDenied) as caught:
        namespace.authorize(
            scope=_scope(),
            binding=replace(binding, **binding_change),
            logical_id="document-123",
        )

    assert str(caught.value) == "PRIVATE_OBJECT_ACCESS_DENIED"
    assert "owner-a" not in str(caught.value)


def test_old_binding_remains_authorized_during_bounded_key_rotation() -> None:
    old_namespace = PrivateObjectNamespace(
        key_ring=VersionedHmacKeyRing(
            current_key_id="object-2026-08",
            current_secret=_PREVIOUS_SECRET,
        )
    )
    binding = old_namespace.bind(
        scope=_scope(),
        domain=PrivateObjectDomain.PAPER_VERSION_ASSET,
        logical_id="paper-version-7",
    )
    rotated = _namespace(previous=True)

    assert (
        rotated.authorize(
            scope=_scope(),
            binding=binding,
            logical_id="paper-version-7",
        )
        == binding.storage_key
    )


def test_retention_is_service_owned_and_fixed_per_domain() -> None:
    namespace = _namespace()

    assert (
        namespace.retention_for(PrivateObjectDomain.EPHEMERAL_EXPORT)
        == PrivateObjectRetention.RESPONSE_COMPLETE
    )
    assert (
        namespace.retention_for(PrivateObjectDomain.BACKGROUND_JOB_RESULT)
        == PrivateObjectRetention.TERMINAL_24H
    )
    assert (
        namespace.retention_for(PrivateObjectDomain.PRIVATE_LIBRARY_SOURCE)
        == PrivateObjectRetention.OWNER_LIFECYCLE
    )


def test_every_declared_domain_has_one_fixed_retention_policy() -> None:
    namespace = _namespace()

    assert {
        domain: namespace.retention_for(domain) for domain in PrivateObjectDomain
    } == {
        PrivateObjectDomain.PRIVATE_LIBRARY_SOURCE: PrivateObjectRetention.OWNER_LIFECYCLE,
        PrivateObjectDomain.QUESTION_CAPTURE_REVISION: PrivateObjectRetention.OWNER_LIFECYCLE,
        PrivateObjectDomain.PDF_IMPORT_SOURCE: PrivateObjectRetention.OWNER_LIFECYCLE,
        PrivateObjectDomain.PDF_IMPORT_CROP: PrivateObjectRetention.OWNER_LIFECYCLE,
        PrivateObjectDomain.PAPER_VERSION_ASSET: PrivateObjectRetention.OWNER_LIFECYCLE,
        PrivateObjectDomain.LESSON_VERSION_ASSET: PrivateObjectRetention.OWNER_LIFECYCLE,
        PrivateObjectDomain.EPHEMERAL_EXPORT: PrivateObjectRetention.RESPONSE_COMPLETE,
        PrivateObjectDomain.BACKGROUND_JOB_RESULT: PrivateObjectRetention.TERMINAL_24H,
    }


@pytest.mark.parametrize(
    ("scope", "logical_id", "error"),
    [
        (PrivateObjectScope(tenant_id="", owner_id="owner-a"), "object", "TENANT"),
        (PrivateObjectScope(tenant_id="tenant-a", owner_id=" owner-a"), "object", "OWNER"),
        (_scope(), "line\nbreak", "LOGICAL_ID"),
    ],
)
def test_invalid_binding_inputs_are_rejected_before_key_generation(
    scope: PrivateObjectScope,
    logical_id: str,
    error: str,
) -> None:
    namespace = _namespace()

    with pytest.raises(
        PrivateObjectBindingError,
        match=f"^PRIVATE_OBJECT_{error}_INVALID$",
    ):
        namespace.bind(
            scope=scope,
            domain=PrivateObjectDomain.PRIVATE_LIBRARY_SOURCE,
            logical_id=logical_id,
        )
