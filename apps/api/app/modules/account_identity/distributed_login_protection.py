from __future__ import annotations

from datetime import timedelta
from ipaddress import ip_address
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx

from app.modules.account_identity.contracts import (
    AccountLoginProtectionUnavailable,
    AccountLoginRateLimited,
)
from app.modules.account_identity.hmac_keyring import VersionedHmacKeyRing


_CONTRACT = "m14.login-protection.v1"
_MAX_RESPONSE_BYTES = 8_192


class HttpDistributedAccountLoginProtection:
    """Digest-only adapter for an operator-owned atomic limiting service.

    Raw email and network origins are normalized and HMACed locally. The
    service receives only bounded digest candidates, non-secret key tags and
    deployment policy. Redirects and environment proxies are disabled so the
    bearer token cannot silently leave the configured boundary.
    """

    def __init__(
        self,
        *,
        service_url: str,
        service_token: str,
        key_ring: VersionedHmacKeyRing,
        window: timedelta,
        principal_attempts: int,
        network_attempts: int,
        retention: timedelta,
        timeout_seconds: float,
        require_https: bool = True,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = self._validate_url(service_url, require_https=require_https)
        if len(service_token) < 32 or any(char.isspace() for char in service_token):
            raise AccountLoginProtectionUnavailable("LOGIN_PROTECTION_UNAVAILABLE")
        if window <= timedelta(0) or retention < window:
            raise AccountLoginProtectionUnavailable("LOGIN_PROTECTION_UNAVAILABLE")
        if principal_attempts < 2 or network_attempts < principal_attempts:
            raise AccountLoginProtectionUnavailable("LOGIN_PROTECTION_UNAVAILABLE")
        if not 0.2 <= timeout_seconds <= 10:
            raise AccountLoginProtectionUnavailable("LOGIN_PROTECTION_UNAVAILABLE")
        self._token = service_token
        self._key_ring = key_ring
        self._policy = {
            "window_seconds": int(window.total_seconds()),
            "principal_attempts": principal_attempts,
            "network_attempts": network_attempts,
            "retention_seconds": int(retention.total_seconds()),
        }
        self._timeout = timeout_seconds
        self._client = client

    def assess(self, *, email: str, network_origin: str) -> None:
        payload = self._digest_payload(email=email, network_origin=network_origin)
        response = self._request("POST", "/v1/assess", payload)
        decision = response.get("decision")
        if decision == "allow":
            return
        if decision == "throttle":
            retry_after = response.get("retry_after_seconds")
            if not isinstance(retry_after, int) or not 1 <= retry_after <= 86_400:
                raise AccountLoginProtectionUnavailable(
                    "LOGIN_PROTECTION_UNAVAILABLE"
                )
            raise AccountLoginRateLimited(retry_after_seconds=retry_after)
        raise AccountLoginProtectionUnavailable("LOGIN_PROTECTION_UNAVAILABLE")

    def record(
        self,
        *,
        email: str,
        network_origin: str,
        outcome: Literal["succeeded", "failed"],
    ) -> None:
        payload = self._digest_payload(email=email, network_origin=network_origin)
        payload.update(
            {
                "principal_hash": self._key_ring.digest(
                    "login:principal", email.strip().casefold()
                ),
                "network_hash": self._key_ring.digest(
                    "login:network", network_origin.strip().casefold() or "unknown"
                ),
                "outcome": outcome,
            }
        )
        response = self._request("POST", "/v1/record", payload)
        if response.get("recorded") is not True:
            raise AccountLoginProtectionUnavailable("LOGIN_PROTECTION_UNAVAILABLE")

    def store_ready(self) -> bool:
        try:
            response = self._request("GET", "/ready", None)
        except AccountLoginProtectionUnavailable:
            return False
        return response.get("status") == "ready"

    def _digest_payload(self, *, email: str, network_origin: str) -> dict[str, Any]:
        normalized_email = email.strip().casefold()
        normalized_network = network_origin.strip().casefold() or "unknown"
        return {
            "contract": _CONTRACT,
            "principal_hashes": list(
                self._key_ring.candidates("login:principal", normalized_email)
            ),
            "network_hashes": list(
                self._key_ring.candidates("login:network", normalized_network)
            ),
            "accepted_key_tags": list(self._key_ring.digest_tags),
            "policy": self._policy,
        }

    def _request(
        self, method: str, path: str, payload: dict[str, Any] | None
    ) -> dict[str, Any]:
        client = self._client or httpx.Client(
            timeout=self._timeout,
            follow_redirects=False,
            trust_env=False,
        )
        owns_client = self._client is None
        try:
            response = client.request(
                method,
                f"{self._base_url}{path}",
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if response.status_code != 200 or len(response.content) > _MAX_RESPONSE_BYTES:
                raise AccountLoginProtectionUnavailable(
                    "LOGIN_PROTECTION_UNAVAILABLE"
                )
            decoded = response.json()
        except (httpx.HTTPError, ValueError):
            raise AccountLoginProtectionUnavailable(
                "LOGIN_PROTECTION_UNAVAILABLE"
            ) from None
        finally:
            if owns_client:
                client.close()
        if not isinstance(decoded, dict) or decoded.get("contract") != _CONTRACT:
            raise AccountLoginProtectionUnavailable("LOGIN_PROTECTION_UNAVAILABLE")
        return decoded

    @staticmethod
    def _validate_url(service_url: str, *, require_https: bool) -> str:
        value = service_url.strip().rstrip("/")
        parsed = urlsplit(value)
        if (
            not value
            or parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise AccountLoginProtectionUnavailable("LOGIN_PROTECTION_UNAVAILABLE")
        is_loopback = parsed.hostname.casefold() == "localhost"
        try:
            is_loopback = is_loopback or ip_address(parsed.hostname).is_loopback
        except ValueError:
            pass
        if parsed.scheme != "https" and (require_https or not is_loopback):
            raise AccountLoginProtectionUnavailable("LOGIN_PROTECTION_UNAVAILABLE")
        return value
