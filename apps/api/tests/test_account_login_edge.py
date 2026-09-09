from __future__ import annotations

import asyncio
import json
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.agent_runtime import TeacherAgentHealth
from app.core.config import Settings, get_settings
from app.main import app
from app.modules.account_identity import (
    AccountLoginProtectionUnavailable,
    AccountLoginRateLimited,
    DirectLoginNetworkOrigin,
    HttpDistributedAccountLoginProtection,
    InMemoryAccountIdentity,
    LoginNetworkOriginUnavailable,
    PersonalAccountProvision,
    TrustedProxyLoginNetworkOrigin,
    VersionedHmacKeyRing,
)
from app.modules.account_identity.dependencies import get_account_identity
from app.modules.account_identity.login_dependencies import (
    get_account_login_protection,
    get_login_network_origin,
)
from app.modules.beta_access import BetaAccess
from app.modules.beta_operations import ReadinessProbe


LOGIN_SECRET = "synthetic-login-secret-with-at-least-32-bytes"
OLD_LOGIN_SECRET = "synthetic-old-login-secret-with-at-least-32-bytes"
SERVICE_TOKEN = "synthetic-service-token-with-at-least-32-bytes"
CONTRACT = "m14.login-protection.v1"


class _HealthyRuntime:
    async def health(self) -> TeacherAgentHealth:
        return TeacherAgentHealth(
            status="ok",
            runtime="dsh",
            initialized=True,
            model_configured=True,
            tool_registry_ready=True,
            visible_tool_count=9,
            runtime_version="test",
        )


class _CapturingProtection:
    def __init__(self) -> None:
        self.origins: list[str] = []

    def assess(self, *, email: str, network_origin: str) -> None:
        del email
        self.origins.append(network_origin)

    def record(self, *, email: str, network_origin: str, outcome: str) -> None:
        del email, outcome
        self.origins.append(network_origin)

    def store_ready(self) -> bool:
        return True


def _ring() -> VersionedHmacKeyRing:
    return VersionedHmacKeyRing(
        current_key_id="login-v2",
        current_secret=LOGIN_SECRET,
        previous_keys={"login-v1": OLD_LOGIN_SECRET},
    )


def _distributed(client: httpx.Client) -> HttpDistributedAccountLoginProtection:
    return HttpDistributedAccountLoginProtection(
        service_url="http://127.0.0.1:8787",
        service_token=SERVICE_TOKEN,
        key_ring=_ring(),
        window=timedelta(minutes=15),
        principal_attempts=5,
        network_attempts=30,
        retention=timedelta(days=7),
        timeout_seconds=1,
        require_https=False,
        client=client,
    )


def test_direct_origin_ignores_forwarding_headers_and_normalizes_peer() -> None:
    resolver = DirectLoginNetworkOrigin()
    assert resolver.resolve(
        peer_host="2001:0db8::1", forwarded_for="198.51.100.9"
    ) == "2001:db8::1"
    assert resolver.configuration_ready() is True


def test_trusted_proxy_accepts_only_one_canonical_ip_from_allowlisted_peer() -> None:
    resolver = TrustedProxyLoginNetworkOrigin(
        trusted_proxy_cidrs="10.10.0.0/16,2001:db8:1::/48"
    )
    assert resolver.resolve(
        peer_host="10.10.2.3", forwarded_for="198.51.100.19"
    ) == "198.51.100.19"
    with pytest.raises(LoginNetworkOriginUnavailable):
        resolver.resolve(
            peer_host="10.11.2.3", forwarded_for="198.51.100.19"
        )
    with pytest.raises(LoginNetworkOriginUnavailable):
        resolver.resolve(
            peer_host="10.10.2.3",
            forwarded_for="198.51.100.19, 10.10.2.3",
        )


def test_login_route_uses_canonical_source_from_trusted_proxy() -> None:
    identity = InMemoryAccountIdentity(session_ttl=timedelta(hours=1))
    identity.provision_personal_account(
        PersonalAccountProvision(
            email="owner@example.test",
            password="synthetic-password-1234",
            display_label="测试教师",
        )
    )
    protection = _CapturingProtection()
    settings = Settings(
        production_identity_enabled=True,
        beta_access_enabled=False,
        production_login_network_source="trusted_proxy",
        production_trusted_proxy_cidrs="10.10.0.0/16",
        production_session_secure_cookie=False,
    )
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_account_identity] = lambda: identity
    app.dependency_overrides[get_account_login_protection] = lambda: protection
    try:
        with TestClient(app, client=("10.10.2.3", 50000)) as client:
            response = client.post(
                "/api/v1/account-session",
                headers={"x-forwarded-for": "198.51.100.19"},
                json={
                    "email": "owner@example.test",
                    "password": "synthetic-password-1234",
                },
            )
        assert response.status_code == 200
        assert protection.origins == ["198.51.100.19", "198.51.100.19"]
    finally:
        app.dependency_overrides.pop(get_account_login_protection, None)
        app.dependency_overrides.pop(get_account_identity, None)
        app.dependency_overrides.pop(get_settings, None)


def test_distributed_adapter_sends_only_bounded_digests_and_current_writes() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        path = request.url.path
        if path.endswith("/assess"):
            return httpx.Response(
                200, json={"contract": CONTRACT, "decision": "allow"}
            )
        if path.endswith("/record"):
            return httpx.Response(
                200, json={"contract": CONTRACT, "recorded": True}
            )
        return httpx.Response(200, json={"contract": CONTRACT, "status": "ready"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        protection = _distributed(client)
        protection.assess(
            email="Sensitive.Owner@Example.Test", network_origin="203.0.113.42"
        )
        protection.record(
            email="Sensitive.Owner@Example.Test",
            network_origin="203.0.113.42",
            outcome="failed",
        )
        assert protection.store_ready() is True

    serialized = b"".join(request.content for request in requests)
    assert b"Sensitive.Owner" not in serialized
    assert b"sensitive.owner" not in serialized
    assert b"203.0.113.42" not in serialized
    assert LOGIN_SECRET.encode() not in serialized
    assert OLD_LOGIN_SECRET.encode() not in serialized
    assert SERVICE_TOKEN.encode() not in serialized
    record = json.loads(requests[1].content)
    assert record["principal_hash"].startswith("k1:login-v2:")
    assert record["network_hash"].startswith("k1:login-v2:")
    assert len(record["principal_hashes"]) == 4
    assert record["accepted_key_tags"] == list(_ring().digest_tags)
    assert requests[1].headers["authorization"] == f"Bearer {SERVICE_TOKEN}"


def test_distributed_adapter_propagates_bounded_throttle_and_fails_closed() -> None:
    decisions = iter(
        [
            {"contract": CONTRACT, "decision": "throttle", "retry_after_seconds": 37},
            {"contract": "wrong-contract", "decision": "allow"},
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=next(decisions))

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        protection = _distributed(client)
        with pytest.raises(AccountLoginRateLimited) as limited:
            protection.assess(email="owner@example.test", network_origin="192.0.2.9")
        assert limited.value.retry_after_seconds == 37
        with pytest.raises(AccountLoginProtectionUnavailable):
            protection.assess(email="owner@example.test", network_origin="192.0.2.9")


def test_distributed_adapter_rejects_insecure_non_loopback_or_weak_token() -> None:
    values = {
        "key_ring": _ring(),
        "window": timedelta(minutes=15),
        "principal_attempts": 5,
        "network_attempts": 30,
        "retention": timedelta(days=7),
        "timeout_seconds": 1,
    }
    with pytest.raises(AccountLoginProtectionUnavailable):
        HttpDistributedAccountLoginProtection(
            service_url="http://limiter.internal",
            service_token=SERVICE_TOKEN,
            **values,
        )
    with pytest.raises(AccountLoginProtectionUnavailable):
        HttpDistributedAccountLoginProtection(
            service_url="https://limiter.internal",
            service_token="too-short",
            **values,
        )


def test_production_environment_requires_trusted_proxy_and_distributed_adapter(
    tmp_path: Path,
) -> None:
    settings = Settings(
        environment="production",
        production_identity_enabled=True,
        beta_access_enabled=False,
        production_identity_db=tmp_path / "identity.sqlite3",
        production_login_security_db=tmp_path / "login-security.sqlite3",
        production_login_security_secret=LOGIN_SECRET,
        production_login_network_source="direct",
        production_login_protection_provider="sqlite",
    )
    origin = get_login_network_origin(settings)
    protection = get_account_login_protection(settings)
    assert origin.configuration_ready() is False
    with pytest.raises(LoginNetworkOriginUnavailable):
        origin.resolve(peer_host="127.0.0.1", forwarded_for=None)
    with pytest.raises(AccountLoginProtectionUnavailable):
        protection.assess(email="owner@example.test", network_origin="127.0.0.1")
    assert not (tmp_path / "login-security.sqlite3").exists()

    snapshot = asyncio.run(
        ReadinessProbe().check(
            settings=settings,
            account_identity=InMemoryAccountIdentity(
                session_ttl=timedelta(hours=1)
            ),
            beta_access=BetaAccess(
                database_path=tmp_path / "unused-beta.sqlite3",
                participants={},
                session_ttl=timedelta(hours=1),
            ),
            runtime=_HealthyRuntime(),  # type: ignore[arg-type]
            login_protection=protection,
            login_network_origin=origin,
        )
    )
    assert snapshot.status == "degraded"
    assert {
        component.code
        for component in snapshot.components
        if component.status == "unavailable"
    } == {
        "LOGIN_NETWORK_ORIGIN_UNAVAILABLE",
        "LOGIN_PROTECTION_UNAVAILABLE",
    }
