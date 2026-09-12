from __future__ import annotations

import hmac
import json
import re

from app.modules.account_identity.hmac_keyring import VersionedHmacKeyRing

from .contracts import (
    PRIVATE_OBJECT_BINDING_SCHEMA_VERSION,
    PrivateObjectAccessDenied,
    PrivateObjectBinding,
    PrivateObjectBindingError,
    PrivateObjectDomain,
    PrivateObjectRetention,
    PrivateObjectScope,
)


_VERSIONED_DIGEST = re.compile(
    r"^k1:(?P<key_id>[A-Za-z0-9][A-Za-z0-9_-]{0,31}):"
    r"(?P<fingerprint>[0-9a-f]{16}):(?P<digest>[0-9a-f]{64})$"
)
_STORAGE_KEY = re.compile(
    r"^private/v1/[a-z0-9-]+/[A-Za-z0-9_-]{1,32}-[0-9a-f]{16}/"
    r"[0-9a-f]{2}/[0-9a-f]{64}$"
)
_MAX_ID_LENGTH = 512

_RETENTION_BY_DOMAIN = {
    PrivateObjectDomain.PRIVATE_LIBRARY_SOURCE: PrivateObjectRetention.OWNER_LIFECYCLE,
    PrivateObjectDomain.QUESTION_CAPTURE_REVISION: PrivateObjectRetention.OWNER_LIFECYCLE,
    PrivateObjectDomain.PDF_IMPORT_SOURCE: PrivateObjectRetention.OWNER_LIFECYCLE,
    PrivateObjectDomain.PDF_IMPORT_CROP: PrivateObjectRetention.OWNER_LIFECYCLE,
    PrivateObjectDomain.PAPER_VERSION_ASSET: PrivateObjectRetention.OWNER_LIFECYCLE,
    PrivateObjectDomain.LESSON_VERSION_ASSET: PrivateObjectRetention.OWNER_LIFECYCLE,
    PrivateObjectDomain.EPHEMERAL_EXPORT: PrivateObjectRetention.RESPONSE_COMPLETE,
    PrivateObjectDomain.BACKGROUND_JOB_RESULT: PrivateObjectRetention.TERMINAL_24H,
}


class PrivateObjectNamespace:
    """Bind private object keys to one tenant, owner, domain, and logical object.

    Raw account identifiers never enter the storage key. Access is granted only
    by recomputing the binding under the authenticated scope. The key ring keeps
    already-issued bindings readable during bounded HMAC key rotation.
    """

    def __init__(self, *, key_ring: VersionedHmacKeyRing) -> None:
        self._key_ring = key_ring

    def bind(
        self,
        *,
        scope: PrivateObjectScope,
        domain: PrivateObjectDomain,
        logical_id: str,
    ) -> PrivateObjectBinding:
        normalized_scope, normalized_domain, normalized_logical_id = self._validate(
            scope=scope,
            domain=domain,
            logical_id=logical_id,
        )
        value = self._binding_value(
            scope=normalized_scope,
            domain=normalized_domain,
            logical_id=normalized_logical_id,
        )
        digest = self._key_ring.digest("private-object-storage", value)
        return PrivateObjectBinding(
            storage_key=self._storage_key(normalized_domain, digest),
            domain=normalized_domain,
            retention=_RETENTION_BY_DOMAIN[normalized_domain],
        )

    def authorize(
        self,
        *,
        scope: PrivateObjectScope,
        binding: PrivateObjectBinding,
        logical_id: str,
    ) -> str:
        try:
            normalized_scope, normalized_domain, normalized_logical_id = self._validate(
                scope=scope,
                domain=binding.domain,
                logical_id=logical_id,
            )
            if (
                binding.schema_version != PRIVATE_OBJECT_BINDING_SCHEMA_VERSION
                or binding.retention != _RETENTION_BY_DOMAIN[normalized_domain]
                or not _STORAGE_KEY.fullmatch(binding.storage_key)
            ):
                raise PrivateObjectAccessDenied("PRIVATE_OBJECT_ACCESS_DENIED")
            value = self._binding_value(
                scope=normalized_scope,
                domain=normalized_domain,
                logical_id=normalized_logical_id,
            )
            candidates = (
                self._storage_key(normalized_domain, digest)
                for digest in self._key_ring.candidates(
                    "private-object-storage",
                    value,
                )
                if digest.startswith("k1:")
            )
            if not any(
                hmac.compare_digest(binding.storage_key, candidate)
                for candidate in candidates
            ):
                raise PrivateObjectAccessDenied("PRIVATE_OBJECT_ACCESS_DENIED")
        except PrivateObjectAccessDenied:
            raise
        except (AttributeError, KeyError, TypeError, ValueError):
            raise PrivateObjectAccessDenied("PRIVATE_OBJECT_ACCESS_DENIED") from None
        return binding.storage_key

    @staticmethod
    def retention_for(domain: PrivateObjectDomain) -> PrivateObjectRetention:
        if not isinstance(domain, PrivateObjectDomain):
            raise PrivateObjectBindingError("PRIVATE_OBJECT_DOMAIN_INVALID")
        try:
            return _RETENTION_BY_DOMAIN[domain]
        except KeyError:
            raise PrivateObjectBindingError("PRIVATE_OBJECT_DOMAIN_INVALID") from None

    @classmethod
    def _validate(
        cls,
        *,
        scope: PrivateObjectScope,
        domain: PrivateObjectDomain,
        logical_id: str,
    ) -> tuple[PrivateObjectScope, PrivateObjectDomain, str]:
        if not isinstance(scope, PrivateObjectScope):
            raise PrivateObjectBindingError("PRIVATE_OBJECT_SCOPE_INVALID")
        tenant_id = cls._validated_id(scope.tenant_id, "TENANT")
        owner_id = cls._validated_id(scope.owner_id, "OWNER")
        object_id = cls._validated_id(logical_id, "LOGICAL_ID")
        if not isinstance(domain, PrivateObjectDomain):
            raise PrivateObjectBindingError("PRIVATE_OBJECT_DOMAIN_INVALID")
        return PrivateObjectScope(tenant_id=tenant_id, owner_id=owner_id), domain, object_id

    @staticmethod
    def _validated_id(value: str, label: str) -> str:
        if (
            not isinstance(value, str)
            or not value
            or value != value.strip()
            or len(value) > _MAX_ID_LENGTH
            or any(ord(character) < 32 or ord(character) == 127 for character in value)
        ):
            raise PrivateObjectBindingError(f"PRIVATE_OBJECT_{label}_INVALID")
        return value

    @staticmethod
    def _binding_value(
        *,
        scope: PrivateObjectScope,
        domain: PrivateObjectDomain,
        logical_id: str,
    ) -> str:
        return json.dumps(
            {
                "domain": domain.value,
                "logical_id": logical_id,
                "owner_id": scope.owner_id,
                "schema": PRIVATE_OBJECT_BINDING_SCHEMA_VERSION,
                "tenant_id": scope.tenant_id,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    @staticmethod
    def _storage_key(domain: PrivateObjectDomain, versioned_digest: str) -> str:
        matched = _VERSIONED_DIGEST.fullmatch(versioned_digest)
        if matched is None:
            raise PrivateObjectBindingError("PRIVATE_OBJECT_DIGEST_INVALID")
        key_id = matched.group("key_id")
        fingerprint = matched.group("fingerprint")
        digest = matched.group("digest")
        return (
            f"private/v1/{domain.value}/{key_id}-{fingerprint}/"
            f"{digest[:2]}/{digest}"
        )
