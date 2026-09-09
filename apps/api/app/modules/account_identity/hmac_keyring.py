from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping


_KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$")
_HEX_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_FINGERPRINT = re.compile(r"^[0-9a-f]{16}$")
_MAX_PREVIOUS_KEYS = 3


class HmacKeyRingConfigurationError(ValueError):
    pass


class VersionedHmacKeyRing:
    """Versioned HMAC writes with bounded, backwards-compatible verification.

    New digests always use the current key. Candidate generation additionally
    covers configured previous keys and the unversioned format used before the
    key-ring migration. Key material is never returned or included in repr.
    """

    def __init__(
        self,
        *,
        current_key_id: str,
        current_secret: str,
        previous_keys: Mapping[str, str] | None = None,
    ) -> None:
        previous = dict(previous_keys or {})
        if not _KEY_ID.fullmatch(current_key_id):
            raise HmacKeyRingConfigurationError("HMAC_KEY_ID_INVALID")
        if len(previous) > _MAX_PREVIOUS_KEYS:
            raise HmacKeyRingConfigurationError("HMAC_PREVIOUS_KEYS_LIMIT_EXCEEDED")
        if current_key_id in previous:
            raise HmacKeyRingConfigurationError("HMAC_KEY_ID_DUPLICATED")

        ordered = [(current_key_id, current_secret), *previous.items()]
        seen_secrets: set[str] = set()
        keys: list[tuple[str, bytes]] = []
        for key_id, secret in ordered:
            if not isinstance(key_id, str) or not _KEY_ID.fullmatch(key_id):
                raise HmacKeyRingConfigurationError("HMAC_KEY_ID_INVALID")
            if not isinstance(secret, str) or len(secret) < 32:
                raise HmacKeyRingConfigurationError("HMAC_KEY_SECRET_INVALID")
            if secret in seen_secrets:
                raise HmacKeyRingConfigurationError("HMAC_KEY_SECRET_REUSED")
            seen_secrets.add(secret)
            keys.append((key_id, secret.encode("utf-8")))

        self._current_key_id = current_key_id
        self._keys = tuple(keys)
        self._tags = frozenset(self._tag(key_id, secret) for key_id, secret in keys)

    @classmethod
    def from_config(
        cls,
        *,
        current_key_id: str,
        current_secret: str,
        previous_keys_json: str,
    ) -> VersionedHmacKeyRing:
        try:
            decoded = json.loads(previous_keys_json or "{}")
        except (TypeError, json.JSONDecodeError):
            raise HmacKeyRingConfigurationError("HMAC_PREVIOUS_KEYS_INVALID") from None
        if not isinstance(decoded, dict) or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in decoded.items()
        ):
            raise HmacKeyRingConfigurationError("HMAC_PREVIOUS_KEYS_INVALID")
        return cls(
            current_key_id=current_key_id,
            current_secret=current_secret,
            previous_keys=decoded,
        )

    @property
    def current_key_id(self) -> str:
        return self._current_key_id

    @property
    def previous_key_count(self) -> int:
        return len(self._keys) - 1

    @property
    def digest_tags(self) -> tuple[str, ...]:
        """Return only non-secret version tags for remote store validation."""

        return tuple(self._tag(key_id, secret) for key_id, secret in self._keys)

    def digest(self, scope: str, value: str) -> str:
        key_id, secret = self._keys[0]
        return self._versioned_digest(key_id, secret, scope=scope, value=value)

    def candidates(self, scope: str, value: str) -> tuple[str, ...]:
        candidates: list[str] = []
        for key_id, secret in self._keys:
            raw = self._raw_digest(secret, scope=scope, value=value)
            candidates.extend((f"{self._tag(key_id, secret)}:{raw}", raw))
        return tuple(candidates)

    def recognizes(self, persisted_digest: str) -> bool:
        if _HEX_DIGEST.fullmatch(persisted_digest):
            return True
        parts = persisted_digest.split(":")
        if len(parts) != 4 or parts[0] != "k1":
            return False
        _, key_id, fingerprint, digest = parts
        if (
            not _KEY_ID.fullmatch(key_id)
            or not _FINGERPRINT.fullmatch(fingerprint)
            or not _HEX_DIGEST.fullmatch(digest)
        ):
            return False
        return ":".join(parts[:3]) in self._tags

    def __repr__(self) -> str:
        return (
            "VersionedHmacKeyRing("
            f"current_key_id={self._current_key_id!r}, "
            f"previous_key_count={self.previous_key_count})"
        )

    @classmethod
    def _versioned_digest(
        cls, key_id: str, secret: bytes, *, scope: str, value: str
    ) -> str:
        return (
            f"{cls._tag(key_id, secret)}:"
            f"{cls._raw_digest(secret, scope=scope, value=value)}"
        )

    @staticmethod
    def _raw_digest(secret: bytes, *, scope: str, value: str) -> str:
        if not scope or not value:
            raise ValueError("HMAC_DIGEST_INPUT_INVALID")
        return hmac.new(
            secret,
            f"m14:{scope}:{value}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def _tag(key_id: str, secret: bytes) -> str:
        fingerprint = hmac.new(
            secret,
            f"m14:key-fingerprint:{key_id}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()[:16]
        return f"k1:{key_id}:{fingerprint}"
