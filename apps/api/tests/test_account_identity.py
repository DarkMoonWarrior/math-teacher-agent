from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import app
from app.modules.account_identity import (
    AccountIdentityConflict,
    AccountIdentityDenied,
    AccountLogin,
    InMemoryAccountIdentity,
    PersonalAccountRegistration,
    PersonalAccountProvision,
    SqliteAccountIdentity,
)
from app.modules.account_identity.contracts import AccountIdentity, AccountRegistration
from app.modules.account_identity.dependencies import get_account_identity
from app.modules.teacher_memory import TeacherMemory, TeacherMemoryCommand
from app.modules.teacher_memory.dependencies import get_teacher_memory


PASSWORD = "synthetic-password-1234"


def _provision(
    identity: object,
    *,
    email: str = "alpha@example.test",
    owner_id: str = "owner-alpha",
):
    return identity.provision_personal_account(  # type: ignore[attr-defined]
        PersonalAccountProvision(
            email=email,
            password=PASSWORD,
            display_label="Alpha 教师",
            owner_id=owner_id,
        )
    )


@pytest.fixture(params=["memory", "sqlite"])
def identity_adapter(
    request: pytest.FixtureRequest, tmp_path: Path
) -> tuple[AccountIdentity, list[datetime]]:
    now = [datetime(2026, 9, 8, 4, 0, tzinfo=timezone.utc)]
    if request.param == "memory":
        identity: AccountIdentity = InMemoryAccountIdentity(
            session_ttl=timedelta(minutes=30), clock=lambda: now[0]
        )
    else:
        identity = SqliteAccountIdentity(
            database_path=tmp_path / "identity.sqlite3",
            session_ttl=timedelta(minutes=30),
            clock=lambda: now[0],
        )
    return identity, now


def test_account_identity_contract_keeps_account_tenant_and_owner_distinct(
    identity_adapter: tuple[AccountIdentity, list[datetime]],
) -> None:
    identity, _ = identity_adapter
    provisioned = _provision(identity)

    assert provisioned.account_id.startswith("acct_")
    assert provisioned.tenant_id.startswith("tenant_")
    assert provisioned.owner_id == "owner-alpha"
    assert len({provisioned.account_id, provisioned.tenant_id, provisioned.owner_id}) == 3
    assert provisioned.role == "personal_owner"

    grant = identity.authenticate(
        AccountLogin(email=" ALPHA@EXAMPLE.TEST ", password=PASSWORD)
    )
    resolved = identity.resolve(grant.token)
    assert resolved.account_id == provisioned.account_id
    assert resolved.tenant_id == provisioned.tenant_id
    assert resolved.owner_id == provisioned.owner_id
    assert resolved.role == "personal_owner"
    assert set(resolved.capabilities) == {
        "search",
        "solve",
        "library",
        "authoring",
        "lesson",
        "paper",
        "teacher_memory",
    }


def test_registration_contract_generates_owner_identity_in_both_adapters(
    identity_adapter: tuple[AccountIdentity, list[datetime]],
) -> None:
    identity, _ = identity_adapter
    registration = cast(AccountRegistration, identity)

    grant = registration.register_personal_account(
        PersonalAccountRegistration(
            email="new-teacher@example.test",
            display_label="新教师",
            password=PASSWORD,
            password_confirmation=PASSWORD,
        )
    )
    resolved = identity.resolve(grant.token)

    assert resolved.account_id.startswith("acct_")
    assert resolved.tenant_id.startswith("tenant_")
    assert resolved.owner_id.startswith("owner_")
    assert len({resolved.account_id, resolved.tenant_id, resolved.owner_id}) == 3
    assert resolved.role == "personal_owner"


def test_account_identity_rejects_duplicate_email_owner_and_bad_credentials(
    identity_adapter: tuple[AccountIdentity, list[datetime]],
) -> None:
    identity, _ = identity_adapter
    _provision(identity)
    with pytest.raises(AccountIdentityConflict):
        _provision(identity, owner_id="owner-other")
    with pytest.raises(AccountIdentityConflict):
        _provision(
            identity,
            email="other@example.test",
            owner_id="owner-alpha",
        )
    with pytest.raises(AccountIdentityDenied, match="邮箱或密码无效"):
        identity.authenticate(
            AccountLogin(email="missing@example.test", password="wrong")
        )
    with pytest.raises(AccountIdentityDenied, match="邮箱或密码无效"):
        identity.authenticate(
            AccountLogin(email="alpha@example.test", password="wrong")
        )


def test_account_identity_sessions_expire_and_revoke(
    identity_adapter: tuple[AccountIdentity, list[datetime]],
) -> None:
    identity, now = identity_adapter
    _provision(identity)
    first = identity.authenticate(
        AccountLogin(email="alpha@example.test", password=PASSWORD)
    )
    assert identity.revoke(first.token) is True
    assert identity.revoke(first.token) is False
    with pytest.raises(AccountIdentityDenied):
        identity.resolve(first.token)

    second = identity.authenticate(
        AccountLogin(email="alpha@example.test", password=PASSWORD)
    )
    now[0] += timedelta(minutes=31)
    with pytest.raises(AccountIdentityDenied, match="过期"):
        identity.resolve(second.token)


def test_sqlite_adapter_hashes_passwords_and_session_tokens(tmp_path: Path) -> None:
    database_path = tmp_path / "identity.sqlite3"
    identity = SqliteAccountIdentity(
        database_path=database_path,
        session_ttl=timedelta(hours=1),
    )
    _provision(identity)
    grant = identity.authenticate(
        AccountLogin(email="alpha@example.test", password=PASSWORD)
    )
    with sqlite3.connect(database_path) as connection:
        password_hash = connection.execute(
            "SELECT password_hash FROM m14_accounts"
        ).fetchone()[0]
        token_hash = connection.execute(
            "SELECT token_hash FROM m14_account_sessions"
        ).fetchone()[0]
    assert PASSWORD not in password_hash
    assert password_hash.startswith("scrypt$")
    assert grant.token != token_hash
    assert len(token_hash) == 64


def test_production_session_http_is_owner_scoped_and_hides_internal_ids(
    tmp_path: Path,
) -> None:
    identity = InMemoryAccountIdentity(session_ttl=timedelta(hours=1))
    _provision(identity)
    _provision(identity, email="beta@example.test", owner_id="owner-beta")
    memory = TeacherMemory(database_path=tmp_path / "memory.sqlite3")
    for owner, grade in (("owner-alpha", "高一"), ("owner-beta", "高三")):
        memory.apply(
            TeacherMemoryCommand(operation="upsert", key="default_grade", value=grade),
            owner_id=owner,
        )
    settings = Settings(
        production_identity_enabled=True,
        production_self_registration_enabled=False,
        beta_access_enabled=False,
        production_session_cookie_name="account_test_session",
        production_session_secure_cookie=False,
        production_identity_db=tmp_path / "unused.sqlite3",
        production_login_security_db=tmp_path / "login-security.sqlite3",
        production_login_security_secret="test-login-security-secret-32-bytes-minimum",
    )
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_account_identity] = lambda: identity
    app.dependency_overrides[get_teacher_memory] = lambda: memory
    try:
        with TestClient(app) as anonymous:
            assert anonymous.get("/api/v1/account-session").json() == {
                "enabled": True,
                "authenticated": False,
                "registration_enabled": False,
                "display_label": "",
                "expires_at": None,
                "capabilities": [],
            }
            assert anonymous.get("/api/v1/teacher-memory/profile").status_code == 401

        with TestClient(app) as alpha:
            login = alpha.post(
                "/api/v1/account-session",
                json={"email": "alpha@example.test", "password": PASSWORD},
            )
            assert login.status_code == 200
            assert login.json()["display_label"] == "Alpha 教师"
            assert "account_id" not in login.text
            assert "tenant_id" not in login.text
            assert "owner-alpha" not in login.text
            assert "HttpOnly" in login.headers["set-cookie"]
            assert "SameSite=strict" in login.headers["set-cookie"]
            profile = alpha.get(
                "/api/v1/teacher-memory/profile", params={"owner_id": "owner-beta"}
            )
            assert profile.status_code == 200
            assert profile.json()["preferences"][0]["value"] == "高一"
            assert alpha.delete("/api/v1/account-session").status_code == 200
            assert alpha.get("/api/v1/teacher-memory/profile").status_code == 401


        with TestClient(app) as beta:
            assert beta.post(
                "/api/v1/account-session",
                json={"email": "beta@example.test", "password": PASSWORD},
            ).status_code == 200
            profile = beta.get("/api/v1/teacher-memory/profile")
            assert profile.json()["preferences"][0]["value"] == "高三"
    finally:
        app.dependency_overrides.pop(get_teacher_memory, None)
        app.dependency_overrides.pop(get_account_identity, None)
        app.dependency_overrides.pop(get_settings, None)


def test_identity_modes_are_mutually_exclusive_before_business_access(
    tmp_path: Path,
) -> None:
    identity = InMemoryAccountIdentity(session_ttl=timedelta(hours=1))
    settings = Settings(
        production_identity_enabled=True,
        beta_access_enabled=True,
        production_identity_db=tmp_path / "unused.sqlite3",
    )
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_account_identity] = lambda: identity
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/teacher-memory/profile")
            assert response.status_code == 503
            assert response.json()["detail"]["code"] == "IDENTITY_MODE_CONFLICT"
            session = client.get("/api/v1/account-session")
            assert session.status_code == 503
            assert session.json()["detail"]["code"] == "IDENTITY_MODE_CONFLICT"
    finally:
        app.dependency_overrides.pop(get_account_identity, None)
        app.dependency_overrides.pop(get_settings, None)


def test_account_session_route_stays_closed_while_feature_is_disabled(
    tmp_path: Path,
) -> None:
    settings = Settings(
        production_identity_enabled=False,
        beta_access_enabled=False,
        production_identity_db=tmp_path / "unused.sqlite3",
    )
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/account-session")
            assert response.status_code == 409
            assert response.json()["detail"]["code"] == "PRODUCTION_IDENTITY_DISABLED"
    finally:
        app.dependency_overrides.pop(get_settings, None)
    assert not settings.production_identity_db.exists()


def test_production_mode_disables_legacy_single_user_routes(tmp_path: Path) -> None:
    settings = Settings(
        production_identity_enabled=True,
        beta_access_enabled=False,
        production_identity_db=tmp_path / "unused.sqlite3",
    )
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/questions")
            assert response.status_code == 403
            assert response.json()["detail"]["code"] == "LEGACY_WORKFLOW_UNAVAILABLE"
    finally:
        app.dependency_overrides.pop(get_settings, None)
