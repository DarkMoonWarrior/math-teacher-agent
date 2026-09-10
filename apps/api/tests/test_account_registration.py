from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import app
from app.modules.account_identity import InMemoryAccountIdentity
from app.modules.account_identity.dependencies import get_account_identity
from app.modules.account_identity.login_dependencies import (
    get_account_login_protection,
    get_login_network_origin,
)


PASSWORD = "synthetic-registration-password-1234"


class _AllowingProtection:
    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []

    def assess(self, *, email: str, network_origin: str) -> None:
        self.events.append(("assess", network_origin))

    def record(self, *, email: str, network_origin: str, outcome: str) -> None:
        self.events.append((outcome, network_origin))

    def store_ready(self) -> bool:
        return True


class _DirectOrigin:
    def resolve(self, *, peer_host: str | None, forwarded_for: str | None) -> str:
        del forwarded_for
        return peer_host or "unknown"

    def configuration_ready(self) -> bool:
        return True


def _settings(tmp_path: Path, *, registration_enabled: bool = True) -> Settings:
    return Settings(
        production_identity_enabled=True,
        production_self_registration_enabled=registration_enabled,
        beta_access_enabled=False,
        production_session_secure_cookie=False,
        production_identity_db=tmp_path / "unused.sqlite3",
    )


def test_web_registration_creates_server_owned_personal_identity_and_session(
    tmp_path: Path,
) -> None:
    identity = InMemoryAccountIdentity(session_ttl=timedelta(hours=1))
    protection = _AllowingProtection()
    settings = _settings(tmp_path)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_account_identity] = lambda: identity
    app.dependency_overrides[get_account_login_protection] = lambda: protection
    app.dependency_overrides[get_login_network_origin] = lambda: _DirectOrigin()
    try:
        with TestClient(app) as client:
            status = client.get("/api/v1/account-session")
            assert status.status_code == 200
            assert status.json()["registration_enabled"] is True

            response = client.post(
                "/api/v1/account-registration",
                json={
                    "email": " Teacher@Example.Test ",
                    "display_label": "王老师",
                    "password": PASSWORD,
                    "password_confirmation": PASSWORD,
                },
            )
            assert response.status_code == 200
            assert response.json() == {
                "enabled": True,
                "authenticated": True,
                "registration_enabled": True,
                "display_label": "王老师",
                "expires_at": response.json()["expires_at"],
                "capabilities": [
                    "search",
                    "solve",
                    "library",
                    "authoring",
                    "lesson",
                    "paper",
                    "teacher_memory",
                ],
            }
            assert "account_id" not in response.text
            assert "tenant_id" not in response.text
            assert "owner_id" not in response.text
            assert "HttpOnly" in response.headers["set-cookie"]

            context = identity.resolve(client.cookies[settings.production_session_cookie_name])
            assert context.owner_id.startswith("owner_")
            assert len({context.account_id, context.tenant_id, context.owner_id}) == 3
            assert context.role == "personal_owner"
            assert protection.events == [
                ("assess", "testclient"),
                ("succeeded", "testclient"),
            ]
    finally:
        app.dependency_overrides.clear()


def test_web_registration_rejects_browser_owned_identity_fields_and_duplicates(
    tmp_path: Path,
) -> None:
    identity = InMemoryAccountIdentity(session_ttl=timedelta(hours=1))
    settings = _settings(tmp_path)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_account_identity] = lambda: identity
    app.dependency_overrides[get_account_login_protection] = lambda: _AllowingProtection()
    app.dependency_overrides[get_login_network_origin] = lambda: _DirectOrigin()
    try:
        with TestClient(app) as client:
            payload = {
                "email": "teacher@example.test",
                "display_label": "王老师",
                "password": PASSWORD,
                "password_confirmation": PASSWORD,
            }
            assert client.post("/api/v1/account-registration", json=payload).status_code == 200
            duplicate = client.post("/api/v1/account-registration", json=payload)
            assert duplicate.status_code == 409
            assert duplicate.json()["detail"]["code"] == "ACCOUNT_REGISTRATION_CONFLICT"
            assert "teacher@example.test" not in duplicate.text

            injected = client.post(
                "/api/v1/account-registration",
                json={**payload, "owner_id": "owner-attacker", "role": "admin"},
            )
            assert injected.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_web_registration_is_fail_closed_when_not_enabled(tmp_path: Path) -> None:
    settings = _settings(tmp_path, registration_enabled=False)
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            status = client.get("/api/v1/account-session")
            assert status.status_code == 200
            assert status.json()["registration_enabled"] is False
            response = client.post(
                "/api/v1/account-registration",
                json={
                    "email": "teacher@example.test",
                    "display_label": "王老师",
                    "password": PASSWORD,
                    "password_confirmation": PASSWORD,
                },
            )
            assert response.status_code == 403
            assert response.json()["detail"]["code"] == "ACCOUNT_REGISTRATION_DISABLED"
    finally:
        app.dependency_overrides.clear()
