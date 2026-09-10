from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.capabilities import ALL_WORKBENCH_CAPABILITIES
from app.core.config import Settings, get_settings
from app.main import app
from app.modules.account_identity import (
    AccountIdentityUnavailable,
    AccountLogin,
    POSTGRES_IDENTITY_SCHEMA_VERSION,
    PostgresAccountIdentity,
    PostgresAccountIdentitySchema,
    PostgresIdentitySchemaError,
    PersonalAccountRegistration,
)
from app.modules.account_identity.crypto import hash_password, hash_session_token
from app.modules.account_identity.dependencies import get_account_identity


PASSWORD = "synthetic-password-1234"


class _Cursor:
    def __init__(self, row: dict[str, Any] | None = None, *, rowcount: int = 0) -> None:
        self._row = row
        self.rowcount = rowcount

    def fetchone(self) -> dict[str, Any] | None:
        return self._row


class _Connection:
    def __init__(self, execute) -> None:
        self._execute = execute

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def execute(self, query: str, params=None) -> _Cursor:
        return self._execute(query, params)


def test_postgres_schema_is_previewed_before_explicit_apply() -> None:
    state = {"installed": False, "writes": 0}

    def execute(query: str, params) -> _Cursor:
        normalized = " ".join(query.split())
        if normalized.startswith("SELECT to_regclass"):
            return _Cursor(
                {"metadata_table": "schema_versions" if state["installed"] else None}
            )
        if "information_schema.tables" in normalized:
            return _Cursor({"table_count": 0})
        if normalized.startswith("SELECT schema_version"):
            return _Cursor({"schema_version": POSTGRES_IDENTITY_SCHEMA_VERSION})
        if "WHERE FALSE" in normalized:
            return _Cursor()
        if normalized.startswith("SELECT pg_advisory_xact_lock"):
            return _Cursor()
        state["writes"] += 1
        if normalized.startswith("INSERT INTO") and "schema_versions" in normalized:
            state["installed"] = True
        return _Cursor()

    schema = PostgresAccountIdentitySchema(
        connect=lambda: _Connection(execute)  # type: ignore[arg-type]
    )
    plan = schema.preview()
    assert plan.state == "empty"
    assert plan.changed is False
    assert len(plan.fingerprint) == 64
    assert state["writes"] == 0

    with pytest.raises(
        PostgresIdentitySchemaError,
        match="POSTGRES_IDENTITY_SCHEMA_CONFIRMATION_REQUIRED",
    ):
        schema.apply(expected_fingerprint=plan.fingerprint)
    with pytest.raises(
        PostgresIdentitySchemaError, match="POSTGRES_IDENTITY_SCHEMA_PLAN_CHANGED"
    ):
        schema.apply(expected_fingerprint="0" * 64, confirmed=True)
    assert state["writes"] == 0

    applied = schema.apply(expected_fingerprint=plan.fingerprint, confirmed=True)
    assert applied.changed is True
    assert state["installed"] is True
    assert state["writes"] == plan.statement_count
    assert schema.preview().state == "current"


def test_postgres_schema_refuses_unknown_existing_target() -> None:
    def execute(query: str, params) -> _Cursor:
        if "to_regclass" in query:
            return _Cursor({"metadata_table": "schema_versions"})
        return _Cursor(None)

    schema = PostgresAccountIdentitySchema(
        connect=lambda: _Connection(execute)  # type: ignore[arg-type]
    )
    plan = schema.preview()
    assert plan.state == "unexpected"
    with pytest.raises(
        PostgresIdentitySchemaError, match="POSTGRES_IDENTITY_SCHEMA_UNEXPECTED"
    ):
        schema.apply(expected_fingerprint=plan.fingerprint, confirmed=True)


def test_postgres_adapter_preserves_identity_contract_and_hashes_session() -> None:
    now = datetime(2026, 9, 10, 4, 0, tzinfo=timezone.utc)
    inserted_token_hashes: list[str] = []
    revoked_token_hashes: list[str] = []
    account_row = {
        "account_id": "acct_alpha",
        "tenant_id": "tenant_alpha",
        "owner_id": "owner_alpha",
        "password_hash": hash_password(PASSWORD),
        "display_label": "Alpha 教师",
        "status": "active",
        "role": "personal_owner",
        "capabilities_json": list(ALL_WORKBENCH_CAPABILITIES),
        "active": True,
    }

    def execute(query: str, params) -> _Cursor:
        normalized = " ".join(query.split())
        if normalized.startswith("SELECT a.account_id"):
            assert params == ("alpha@example.test",)
            return _Cursor(account_row)
        if normalized.startswith("INSERT INTO") and "account_sessions" in normalized:
            inserted_token_hashes.append(params[0])
            assert params[1:3] == ("acct_alpha", "tenant_alpha")
            return _Cursor(rowcount=1)
        if normalized.startswith("SELECT s.expires_at"):
            assert params == (inserted_token_hashes[-1],)
            return _Cursor(
                {
                    **account_row,
                    "expires_at": now + timedelta(hours=1),
                    "revoked_at": None,
                }
            )
        if normalized.startswith("UPDATE") and "account_sessions" in normalized:
            revoked_token_hashes.append(params[1])
            return _Cursor(rowcount=1)
        if normalized.startswith("SELECT schema_version"):
            return _Cursor({"schema_version": POSTGRES_IDENTITY_SCHEMA_VERSION})
        if "WHERE FALSE" in normalized:
            return _Cursor()
        raise AssertionError(normalized)

    calls = {"connections": 0}

    def connect() -> _Connection:
        calls["connections"] += 1
        return _Connection(execute)

    identity = PostgresAccountIdentity(
        dsn="",
        session_ttl=timedelta(hours=1),
        clock=lambda: now,
        connect=connect,  # type: ignore[arg-type]
    )
    assert calls["connections"] == 0
    grant = identity.authenticate(
        AccountLogin(email="alpha@example.test", password=PASSWORD)
    )
    assert grant.identity.account_id == "acct_alpha"
    assert grant.identity.tenant_id == "tenant_alpha"
    assert grant.identity.owner_id == "owner_alpha"
    assert grant.token not in inserted_token_hashes
    assert inserted_token_hashes == [hash_session_token(grant.token)]
    assert identity.resolve(grant.token).owner_id == "owner_alpha"
    assert identity.store_ready() is True
    assert identity.revoke(grant.token) is True
    assert revoked_token_hashes == [hash_session_token(grant.token)]


def test_postgres_registration_keeps_first_session_in_the_account_transaction() -> None:
    state: dict[str, Any] = {"inserts": [], "exit_exception": None}

    class RegistrationConnection(_Connection):
        def __exit__(self, exc_type, exc, traceback) -> None:
            state["exit_exception"] = exc_type
            return None

    def execute(query: str, params) -> _Cursor:
        if query.lstrip().startswith("INSERT INTO"):
            state["inserts"].append(" ".join(query.split()))
        if "account_sessions" in query:
            raise RuntimeError("synthetic session failure")
        return _Cursor(rowcount=1)

    identity = PostgresAccountIdentity(
        dsn="",
        session_ttl=timedelta(hours=1),
        connect=lambda: RegistrationConnection(execute),  # type: ignore[arg-type]
    )
    with pytest.raises(
        AccountIdentityUnavailable, match="POSTGRES_IDENTITY_WRITE_UNAVAILABLE"
    ):
        identity.register_personal_account(
            PersonalAccountRegistration(
                email="new@example.test",
                display_label="新教师",
                password=PASSWORD,
                password_confirmation=PASSWORD,
            )
        )
    assert len(state["inserts"]) == 4
    assert state["exit_exception"] is RuntimeError


@pytest.mark.parametrize(
    ("settings", "expected_provider"),
    [
        (
            Settings(
                environment="production",
                production_identity_enabled=True,
                production_identity_provider="sqlite",
            ),
            "unavailable",
        ),
        (
            Settings(
                production_identity_enabled=True,
                production_identity_provider="postgresql",
                production_identity_postgres_dsn="",
            ),
            "unavailable",
        ),
        (
            Settings(
                production_identity_enabled=True,
                production_identity_provider="postgresql",
                production_identity_postgres_dsn="postgresql://example.invalid/app",
            ),
            "postgresql",
        ),
    ],
)
def test_identity_dependency_selects_backend_without_connecting(
    settings: Settings, expected_provider: str
) -> None:
    identity = get_account_identity(settings)
    if expected_provider == "postgresql":
        assert isinstance(identity, PostgresAccountIdentity)
    else:
        assert identity.store_ready() is False
        with pytest.raises(AccountIdentityUnavailable):
            identity.authenticate(
                AccountLogin(email="alpha@example.test", password=PASSWORD)
            )


def test_unavailable_production_identity_is_reported_as_service_failure() -> None:
    settings = Settings(
        production_identity_enabled=True,
        production_identity_provider="postgresql",
        production_identity_postgres_dsn="",
        production_login_security_secret="test-login-security-secret-32-bytes-minimum",
        production_session_secure_cookie=False,
    )
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            status = client.get("/api/v1/account-session")
            assert status.status_code == 503
            assert status.json()["detail"]["code"] == "PRODUCTION_IDENTITY_UNAVAILABLE"
    finally:
        app.dependency_overrides.pop(get_settings, None)
