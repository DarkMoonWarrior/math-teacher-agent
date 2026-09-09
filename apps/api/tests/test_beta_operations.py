from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from app.agent_runtime import TeacherAgentHealth, get_teacher_agent_runtime
from app.core.config import Settings, get_settings
from app.main import app
from app.modules.account_identity import (
    DirectLoginNetworkOrigin,
    InMemoryAccountIdentity,
    SqliteAccountLoginProtection,
    VersionedHmacKeyRing,
)
from app.modules.account_identity.dependencies import get_account_identity
from app.modules.beta_access import BetaAccess
from app.modules.beta_access.dependencies import get_beta_access
from app.modules.beta_operations import PrivacySafeOperations, ReadinessProbe


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


class _UnavailableRuntime:
    async def health(self) -> TeacherAgentHealth:
        raise OSError("private internal failure details")


def _access(tmp_path: Path, *, participants=None) -> BetaAccess:
    return BetaAccess(
        database_path=tmp_path / "beta-sessions.sqlite3",
        participants=participants or {},
        session_ttl=timedelta(hours=12),
    )


def test_operation_classifier_and_event_schema_have_no_content_fields() -> None:
    operations = PrivacySafeOperations()
    assert operations.classify("/api/v1/agent/search/stream") == "search"
    assert operations.classify("/api/v1/exam-papers/paper_1") == "paper"
    assert operations.classify("/ready") == "system"

    event = operations.complete(
        operations.begin(method="POST", path="/api/v1/library/items/private-id"),
        status_code=403,
    )
    assert event.capability == "library"
    assert event.outcome == "client_error"
    assert set(event.model_dump()) == {
        "request_id",
        "capability",
        "method",
        "outcome",
        "status_code",
        "error_class",
        "duration_ms",
    }


def test_http_operation_log_never_reads_access_code_or_request_body(
    caplog,
) -> None:
    caplog.set_level(logging.INFO, logger="math_ai.beta_operations")
    sentinel = "SECRET_ACCESS_SENTINEL_不可记录"
    response = TestClient(app).post(
        "/api/v1/beta-session",
        json={"access_code": sentinel},
    )

    assert response.headers["x-request-id"].startswith("op_")
    records = [record for record in caplog.records if hasattr(record, "operation_event")]
    assert records
    event = records[-1].operation_event
    assert event["capability"] == "access"
    assert event["status_code"] == response.status_code
    assert sentinel not in caplog.text
    assert sentinel not in str(event)


def test_readiness_explains_ready_components_without_configuration_secrets(
    tmp_path: Path,
) -> None:
    settings = Settings(
        beta_access_enabled=False,
        search_agent_enabled=False,
        solve_agent_enabled=False,
        question_authoring_agent_enabled=False,
        beta_session_db=tmp_path / "unused.sqlite3",
    )
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_beta_access] = lambda: _access(tmp_path)
    app.dependency_overrides[get_account_identity] = lambda: InMemoryAccountIdentity(
        session_ttl=timedelta(hours=1)
    )
    app.dependency_overrides[get_teacher_agent_runtime] = lambda: _HealthyRuntime()
    try:
        response = TestClient(app).get("/ready")
    finally:
        app.dependency_overrides.pop(get_teacher_agent_runtime, None)
        app.dependency_overrides.pop(get_account_identity, None)
        app.dependency_overrides.pop(get_beta_access, None)
        app.dependency_overrides.pop(get_settings, None)

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert {item["code"] for item in response.json()["components"]} == {
        "API_READY",
        "BETA_ACCESS_NOT_REQUIRED",
        "AGENT_NOT_REQUIRED",
    }
    serialized = response.text.lower()
    assert "token" not in serialized
    assert "roster" not in serialized
    assert "http://" not in serialized


def test_readiness_degrades_without_leaking_runtime_exception(tmp_path: Path) -> None:
    settings = Settings(
        beta_access_enabled=True,
        beta_access_roster_json="{}",
        search_agent_enabled=True,
        solve_agent_enabled=False,
        question_authoring_agent_enabled=False,
        agent_runtime="dsh",
        beta_session_db=tmp_path / "unused.sqlite3",
    )
    snapshot = asyncio.run(ReadinessProbe().check(
        settings=settings,
        account_identity=InMemoryAccountIdentity(session_ttl=timedelta(hours=1)),
        beta_access=_access(tmp_path),
        runtime=_UnavailableRuntime(),  # type: ignore[arg-type]
    ))

    assert snapshot.status == "degraded"
    assert {item.code for item in snapshot.components if item.status == "unavailable"} == {
        "BETA_ACCESS_UNAVAILABLE",
        "AGENT_UNAVAILABLE",
    }
    assert "private internal failure" not in snapshot.model_dump_json()


def test_readiness_uses_production_identity_store_when_that_mode_is_active(
    tmp_path: Path,
) -> None:
    settings = Settings(
        production_identity_enabled=True,
        beta_access_enabled=False,
        search_agent_enabled=False,
        solve_agent_enabled=False,
        question_authoring_agent_enabled=False,
    )
    identity = InMemoryAccountIdentity(session_ttl=timedelta(hours=1))
    login_protection = SqliteAccountLoginProtection(
        database_path=tmp_path / "login-security.sqlite3",
        key_ring=VersionedHmacKeyRing(
            current_key_id="login-v1",
            current_secret="test-login-security-secret-32-bytes-minimum",
        ),
        window=timedelta(minutes=15),
        principal_attempts=5,
        network_attempts=30,
        retention=timedelta(days=7),
    )
    snapshot = asyncio.run(
        ReadinessProbe().check(
            settings=settings,
            account_identity=identity,
            beta_access=_access(tmp_path),
            runtime=_HealthyRuntime(),  # type: ignore[arg-type]
            login_protection=login_protection,
            login_network_origin=DirectLoginNetworkOrigin(),
        )
    )

    assert snapshot.status == "ready"
    assert {item.code for item in snapshot.components} == {
        "API_READY",
        "PRODUCTION_IDENTITY_READY",
        "LOGIN_NETWORK_ORIGIN_READY",
        "LOGIN_PROTECTION_READY",
        "AGENT_NOT_REQUIRED",
    }


def test_readiness_fails_closed_when_identity_modes_conflict(tmp_path: Path) -> None:
    settings = Settings(
        production_identity_enabled=True,
        beta_access_enabled=True,
        search_agent_enabled=False,
        solve_agent_enabled=False,
        question_authoring_agent_enabled=False,
    )
    snapshot = asyncio.run(
        ReadinessProbe().check(
            settings=settings,
            account_identity=InMemoryAccountIdentity(
                session_ttl=timedelta(hours=1)
            ),
            beta_access=_access(tmp_path),
            runtime=_HealthyRuntime(),  # type: ignore[arg-type]
        )
    )

    assert snapshot.status == "degraded"
    assert "IDENTITY_MODE_CONFLICT" in {
        item.code for item in snapshot.components
    }
