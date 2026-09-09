from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import app
from app.modules.account_identity import (
    AccountIdentityDenied,
    AccountLogin,
    AccountLoginProtectionUnavailable,
    AccountLoginRateLimited,
    HmacKeyRingConfigurationError,
    InMemoryAccountIdentity,
    PersonalAccountProvision,
    SqliteAccountLoginProtection,
    VersionedHmacKeyRing,
)
from app.modules.account_identity.dependencies import get_account_identity


PASSWORD = "synthetic-password-1234"
SECRET = "test-login-security-secret-32-bytes-minimum"
ROTATED_SECRET = "rotated-login-security-secret-32-bytes-minimum"


def _protection(tmp_path: Path, now: list[datetime], **overrides):
    values = {
        "database_path": tmp_path / "login-security.sqlite3",
        "key_ring": VersionedHmacKeyRing(
            current_key_id="login-v1", current_secret=SECRET
        ),
        "window": timedelta(minutes=15),
        "principal_attempts": 3,
        "network_attempts": 6,
        "retention": timedelta(days=7),
        "clock": lambda: now[0],
    }
    values.update(overrides)
    return SqliteAccountLoginProtection(**values)


def test_login_protection_throttles_principal_and_success_resets_its_failures(
    tmp_path: Path,
) -> None:
    now = [datetime(2026, 9, 9, 3, 0, tzinfo=timezone.utc)]
    protection = _protection(tmp_path, now)
    for _ in range(2):
        protection.assess(email="owner@example.test", network_origin="192.0.2.10")
        protection.record(
            email="owner@example.test",
            network_origin="192.0.2.10",
            outcome="failed",
        )
    protection.record(
        email="owner@example.test",
        network_origin="192.0.2.10",
        outcome="succeeded",
    )
    now[0] += timedelta(seconds=1)
    protection.assess(email="owner@example.test", network_origin="192.0.2.10")
    for _ in range(3):
        protection.record(
            email="owner@example.test",
            network_origin="192.0.2.10",
            outcome="failed",
        )
    with pytest.raises(AccountLoginRateLimited) as limited:
        protection.assess(email="owner@example.test", network_origin="192.0.2.10")
    assert limited.value.retry_after_seconds == 900


def test_login_protection_applies_network_limit_across_principals(
    tmp_path: Path,
) -> None:
    now = [datetime(2026, 9, 9, 3, 0, tzinfo=timezone.utc)]
    protection = _protection(
        tmp_path,
        now,
        principal_attempts=3,
        network_attempts=4,
    )
    for index in range(4):
        protection.record(
            email=f"unknown-{index}@example.test",
            network_origin="192.0.2.11",
            outcome="failed",
        )
    with pytest.raises(AccountLoginRateLimited):
        protection.assess(
            email="another@example.test", network_origin="192.0.2.11"
        )


def test_login_security_store_contains_only_keyed_digests_and_bounded_facts(
    tmp_path: Path,
) -> None:
    now = [datetime(2026, 9, 9, 3, 0, tzinfo=timezone.utc)]
    protection = _protection(tmp_path, now)
    protection.record(
        email="Sensitive.Owner@Example.Test",
        network_origin="203.0.113.42",
        outcome="failed",
    )
    with sqlite3.connect(tmp_path / "login-security.sqlite3") as connection:
        row = connection.execute(
            "SELECT principal_hash, network_hash, outcome, occurred_at "
            "FROM m14_login_security_events"
        ).fetchone()
        columns = {
            item[1]
            for item in connection.execute(
                "PRAGMA table_info(m14_login_security_events)"
            ).fetchall()
        }
    assert row[0].startswith("k1:login-v1:")
    assert row[1].startswith("k1:login-v1:")
    assert len(row[0].rsplit(":", 1)[1]) == 64
    assert len(row[1].rsplit(":", 1)[1]) == 64
    assert row[2] == "failed"
    assert "Sensitive.Owner" not in repr(row)
    assert "203.0.113.42" not in repr(row)
    database_bytes = (tmp_path / "login-security.sqlite3").read_bytes()
    assert b"Sensitive.Owner" not in database_bytes
    assert b"sensitive.owner" not in database_bytes
    assert b"203.0.113.42" not in database_bytes
    assert SECRET.encode("utf-8") not in database_bytes
    assert columns == {
        "event_id",
        "principal_hash",
        "network_hash",
        "outcome",
        "occurred_at",
    }


def test_login_security_retention_removes_only_old_security_events(
    tmp_path: Path,
) -> None:
    now = [datetime(2026, 9, 9, 3, 0, tzinfo=timezone.utc)]
    protection = _protection(tmp_path, now, retention=timedelta(hours=24))
    protection.record(
        email="old@example.test",
        network_origin="192.0.2.1",
        outcome="failed",
    )
    now[0] += timedelta(hours=25)
    protection.assess(email="new@example.test", network_origin="192.0.2.2")
    with sqlite3.connect(tmp_path / "login-security.sqlite3") as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM m14_login_security_events"
        ).fetchone()[0] == 0


def test_versioned_hmac_key_ring_validates_bounded_secret_configuration() -> None:
    ring = VersionedHmacKeyRing.from_config(
        current_key_id="login-2026-09",
        current_secret=ROTATED_SECRET,
        previous_keys_json=json.dumps({"login-2026-08": SECRET}),
    )
    digest = ring.digest("login:principal", "owner@example.test")
    assert digest.startswith("k1:login-2026-09:")
    assert ring.current_key_id == "login-2026-09"
    assert ring.previous_key_count == 1
    assert ring.recognizes(digest) is True
    assert SECRET not in repr(ring)
    assert ROTATED_SECRET not in repr(ring)

    with pytest.raises(
        HmacKeyRingConfigurationError, match="HMAC_PREVIOUS_KEYS_INVALID"
    ):
        VersionedHmacKeyRing.from_config(
            current_key_id="login-v2",
            current_secret=ROTATED_SECRET,
            previous_keys_json="[]",
        )
    with pytest.raises(
        HmacKeyRingConfigurationError, match="HMAC_KEY_SECRET_REUSED"
    ):
        VersionedHmacKeyRing(
            current_key_id="login-v2",
            current_secret=ROTATED_SECRET,
            previous_keys={"login-v1": ROTATED_SECRET},
        )


def test_login_rotation_counts_previous_key_events_and_writes_current_version(
    tmp_path: Path,
) -> None:
    now = [datetime(2026, 9, 9, 3, 0, tzinfo=timezone.utc)]
    old = _protection(tmp_path, now)
    for _ in range(3):
        old.record(
            email="owner@example.test",
            network_origin="192.0.2.10",
            outcome="failed",
        )

    rotated = _protection(
        tmp_path,
        now,
        key_ring=VersionedHmacKeyRing(
            current_key_id="login-v2",
            current_secret=ROTATED_SECRET,
            previous_keys={"login-v1": SECRET},
        ),
    )
    with pytest.raises(AccountLoginRateLimited):
        rotated.assess(
            email="owner@example.test", network_origin="192.0.2.10"
        )
    with sqlite3.connect(tmp_path / "login-security.sqlite3") as connection:
        last_hash = connection.execute(
            "SELECT principal_hash FROM m14_login_security_events "
            "ORDER BY event_id DESC LIMIT 1"
        ).fetchone()[0]
    assert last_hash.startswith("k1:login-v2:")
    database_bytes = (tmp_path / "login-security.sqlite3").read_bytes()
    assert SECRET.encode("utf-8") not in database_bytes
    assert ROTATED_SECRET.encode("utf-8") not in database_bytes


def test_login_rotation_counts_unversioned_events_from_before_key_ring_upgrade(
    tmp_path: Path,
) -> None:
    now = [datetime(2026, 9, 9, 3, 0, tzinfo=timezone.utc)]
    legacy_ring = VersionedHmacKeyRing(
        current_key_id="login-v1", current_secret=SECRET
    )
    _protection(tmp_path, now, key_ring=legacy_ring)
    with sqlite3.connect(tmp_path / "login-security.sqlite3") as connection:
        for _ in range(3):
            connection.execute(
                """INSERT INTO m14_login_security_events
                   (principal_hash, network_hash, outcome, occurred_at)
                   VALUES (?, ?, 'failed', ?)""",
                (
                    legacy_ring.candidates(
                        "login:principal", "owner@example.test"
                    )[1],
                    legacy_ring.candidates("login:network", "192.0.2.10")[1],
                    now[0].isoformat(),
                ),
            )

    rotated = _protection(
        tmp_path,
        now,
        key_ring=VersionedHmacKeyRing(
            current_key_id="login-v2",
            current_secret=ROTATED_SECRET,
            previous_keys={"login-v1": SECRET},
        ),
    )
    with pytest.raises(AccountLoginRateLimited):
        rotated.assess(
            email="owner@example.test", network_origin="192.0.2.10"
        )


def test_login_rotation_fails_closed_until_retained_previous_key_expires(
    tmp_path: Path,
) -> None:
    now = [datetime(2026, 9, 9, 3, 0, tzinfo=timezone.utc)]
    old = _protection(tmp_path, now)
    old.record(
        email="owner@example.test",
        network_origin="192.0.2.10",
        outcome="failed",
    )
    rotated_without_previous = _protection(
        tmp_path,
        now,
        key_ring=VersionedHmacKeyRing(
            current_key_id="login-v2", current_secret=ROTATED_SECRET
        ),
    )
    assert rotated_without_previous.store_ready() is False
    with pytest.raises(
        AccountLoginProtectionUnavailable, match="LOGIN_PROTECTION_UNAVAILABLE"
    ):
        rotated_without_previous.assess(
            email="owner@example.test", network_origin="192.0.2.10"
        )

    now[0] += timedelta(days=8)
    rotated_without_previous.assess(
        email="owner@example.test", network_origin="192.0.2.10"
    )
    assert rotated_without_previous.store_ready() is True


def test_http_login_is_rate_limited_without_account_enumeration(
    tmp_path: Path,
) -> None:
    identity = InMemoryAccountIdentity(session_ttl=timedelta(hours=1))
    identity.provision_personal_account(
        PersonalAccountProvision(
            email="owner@example.test",
            password=PASSWORD,
            display_label="测试教师",
        )
    )
    settings = Settings(
        production_identity_enabled=True,
        beta_access_enabled=False,
        production_identity_db=tmp_path / "identity.sqlite3",
        production_login_security_db=tmp_path / "login-security.sqlite3",
        production_login_security_secret=SECRET,
        production_login_principal_attempts=2,
        production_login_network_attempts=10,
        production_session_secure_cookie=False,
    )
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_account_identity] = lambda: identity
    try:
        with TestClient(app) as client:
            for email in ("owner@example.test", "missing@example.test"):
                response = client.post(
                    "/api/v1/account-session",
                    json={"email": email, "password": "wrong-password"},
                )
                assert response.status_code == 401
                assert response.json() == {"detail": "邮箱或密码无效。"}
            second_existing_failure = client.post(
                "/api/v1/account-session",
                json={"email": "owner@example.test", "password": "wrong-password"},
            )
            assert second_existing_failure.status_code == 401
            limited = client.post(
                "/api/v1/account-session",
                json={"email": "owner@example.test", "password": PASSWORD},
            )
            assert limited.status_code == 429
            assert limited.json()["detail"]["code"] == "LOGIN_RATE_LIMITED"
            assert limited.headers["retry-after"] == "900"
            assert "owner@example.test" not in limited.text
    finally:
        app.dependency_overrides.pop(get_account_identity, None)
        app.dependency_overrides.pop(get_settings, None)


def test_successful_http_login_rotates_the_previous_session(tmp_path: Path) -> None:
    identity = InMemoryAccountIdentity(session_ttl=timedelta(hours=1))
    identity.provision_personal_account(
        PersonalAccountProvision(
            email="owner@example.test",
            password=PASSWORD,
            display_label="测试教师",
        )
    )
    settings = Settings(
        production_identity_enabled=True,
        beta_access_enabled=False,
        production_identity_db=tmp_path / "identity.sqlite3",
        production_login_security_db=tmp_path / "login-security.sqlite3",
        production_login_security_secret=SECRET,
        production_session_cookie_name="rotation_test_session",
        production_session_secure_cookie=False,
    )
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_account_identity] = lambda: identity
    try:
        with TestClient(app) as client:
            first = client.post(
                "/api/v1/account-session",
                json={"email": "owner@example.test", "password": PASSWORD},
            )
            assert first.status_code == 200
            first_token = client.cookies.get("rotation_test_session")
            assert first_token
            second = client.post(
                "/api/v1/account-session",
                json={"email": "owner@example.test", "password": PASSWORD},
            )
            assert second.status_code == 200
            second_token = client.cookies.get("rotation_test_session")
            assert second_token and second_token != first_token
            with pytest.raises(AccountIdentityDenied):
                identity.resolve(first_token)
            assert identity.resolve(second_token).display_label == "测试教师"
    finally:
        app.dependency_overrides.pop(get_account_identity, None)
        app.dependency_overrides.pop(get_settings, None)


def test_login_fails_closed_when_security_secret_is_missing(tmp_path: Path) -> None:
    identity = InMemoryAccountIdentity(session_ttl=timedelta(hours=1))
    identity.provision_personal_account(
        PersonalAccountProvision(
            email="owner@example.test",
            password=PASSWORD,
            display_label="测试教师",
        )
    )
    settings = Settings(
        production_identity_enabled=True,
        beta_access_enabled=False,
        production_identity_db=tmp_path / "identity.sqlite3",
        production_login_security_db=tmp_path / "login-security.sqlite3",
        production_login_security_secret="",
        production_session_secure_cookie=False,
    )
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_account_identity] = lambda: identity
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/account-session",
                json={"email": "owner@example.test", "password": PASSWORD},
            )
            assert response.status_code == 503
            assert response.json()["detail"]["code"] == "LOGIN_PROTECTION_UNAVAILABLE"
            assert not (tmp_path / "login-security.sqlite3").exists()
            ready = client.get("/ready")
            assert ready.status_code == 503
            assert "LOGIN_PROTECTION_UNAVAILABLE" in {
                item["code"] for item in ready.json()["components"]
            }
    finally:
        app.dependency_overrides.pop(get_account_identity, None)
        app.dependency_overrides.pop(get_settings, None)


def test_login_network_limit_ignores_untrusted_forwarding_headers(
    tmp_path: Path,
) -> None:
    identity = InMemoryAccountIdentity(session_ttl=timedelta(hours=1))
    settings = Settings(
        production_identity_enabled=True,
        beta_access_enabled=False,
        production_identity_db=tmp_path / "identity.sqlite3",
        production_login_security_db=tmp_path / "login-security.sqlite3",
        production_login_security_secret=SECRET,
        production_login_principal_attempts=5,
        production_login_network_attempts=5,
        production_session_secure_cookie=False,
    )
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_account_identity] = lambda: identity
    try:
        with TestClient(app) as client:
            for index in range(5):
                response = client.post(
                    "/api/v1/account-session",
                    headers={"x-forwarded-for": f"198.51.100.{index}"},
                    json={
                        "email": f"unknown-{index}@example.test",
                        "password": "wrong-password",
                    },
                )
                assert response.status_code == 401
            limited = client.post(
                "/api/v1/account-session",
                headers={"x-forwarded-for": "198.51.100.250"},
                json={
                    "email": "another-unknown@example.test",
                    "password": "wrong-password",
                },
            )
            assert limited.status_code == 429
    finally:
        app.dependency_overrides.pop(get_account_identity, None)
        app.dependency_overrides.pop(get_settings, None)
