from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import app
from app.modules.beta_access import (
    BetaAccess,
    BetaAccessDenied,
    BetaParticipant,
)
from app.modules.beta_access.dependencies import get_beta_access
from app.modules.teacher_memory import TeacherMemory, TeacherMemoryCommand
from app.modules.teacher_memory.dependencies import get_teacher_memory


def _participants() -> dict[str, BetaParticipant]:
    return {
        "alpha-code": BetaParticipant(
            teacher_id="teacher-alpha",
            display_label="Alpha 教师",
            capabilities=["search", "teacher_memory"],
        ),
        "beta-code": BetaParticipant(
            teacher_id="teacher-beta",
            display_label="Beta 教师",
            capabilities=["teacher_memory"],
        ),
    }


def test_beta_access_issues_resolves_and_revokes_opaque_sessions(tmp_path: Path) -> None:
    now = datetime(2026, 9, 1, 4, 0, tzinfo=timezone.utc)
    participants = _participants()
    access = BetaAccess(
        database_path=tmp_path / "beta-sessions.sqlite3",
        participants=participants,
        session_ttl=timedelta(hours=12),
        clock=lambda: now,
    )

    try:
        access.issue("wrong-code")
    except BetaAccessDenied as exc:
        assert "访问码" in str(exc)
    else:
        raise AssertionError("an unknown beta access code was accepted")

    grant = access.issue("alpha-code")
    assert grant.token
    assert grant.teacher.display_label == "Alpha 教师"
    assert grant.teacher.expires_at == now + timedelta(hours=12)
    assert grant.teacher.teacher_id == "teacher-alpha"
    assert grant.teacher.capabilities == ["search", "teacher_memory"]
    participants["alpha-code"].capabilities = ["paper"]
    assert access.resolve(grant.token).capabilities == ["search", "teacher_memory"]
    assert access.resolve(grant.token).teacher_id == "teacher-alpha"
    with sqlite3.connect(tmp_path / "beta-sessions.sqlite3") as connection:
        stored_hash = connection.execute(
            "SELECT token_hash FROM m12_beta_sessions"
        ).fetchone()[0]
    assert stored_hash != grant.token
    assert len(stored_hash) == 64

    assert access.revoke(grant.token) is True
    try:
        access.resolve(grant.token)
    except BetaAccessDenied:
        pass
    else:
        raise AssertionError("a revoked beta session was replayed")


def test_beta_access_migrates_slice_one_session_storage_without_escalating_it(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "beta-sessions.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """CREATE TABLE m12_beta_sessions (
                token_hash TEXT PRIMARY KEY,
                teacher_id TEXT NOT NULL,
                display_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                revoked_at TEXT
            )"""
        )

    access = BetaAccess(
        database_path=database_path,
        participants=_participants(),
        session_ttl=timedelta(hours=12),
    )
    with sqlite3.connect(database_path) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(m12_beta_sessions)")
        }
    assert "capabilities_json" in columns
    assert access.issue("alpha-code").teacher.capabilities == [
        "search",
        "teacher_memory",
    ]


def test_beta_access_expires_sessions_and_keeps_participants_isolated(tmp_path: Path) -> None:
    current = datetime(2026, 9, 1, 4, 0, tzinfo=timezone.utc)
    access = BetaAccess(
        database_path=tmp_path / "beta-sessions.sqlite3",
        participants=_participants(),
        session_ttl=timedelta(minutes=30),
        clock=lambda: current,
    )
    alpha = access.issue("alpha-code")
    beta = access.issue("beta-code")
    assert alpha.token != beta.token
    assert access.resolve(alpha.token).teacher_id == "teacher-alpha"
    assert access.resolve(beta.token).teacher_id == "teacher-beta"

    current += timedelta(minutes=31)
    for token in (alpha.token, beta.token):
        try:
            access.resolve(token)
        except BetaAccessDenied as exc:
            assert "过期" in str(exc)
        else:
            raise AssertionError("an expired beta session was accepted")


def test_beta_session_http_cookie_is_fail_closed_and_owner_scoped(tmp_path: Path) -> None:
    access = BetaAccess(
        database_path=tmp_path / "beta-sessions.sqlite3",
        participants=_participants(),
        session_ttl=timedelta(hours=12),
    )
    memory = TeacherMemory(database_path=tmp_path / "teacher-memory.sqlite3")
    memory.apply(
        TeacherMemoryCommand(operation="upsert", key="default_grade", value="高一"),
        owner_id="teacher-alpha",
    )
    memory.apply(
        TeacherMemoryCommand(operation="upsert", key="default_grade", value="高三"),
        owner_id="teacher-beta",
    )
    beta_settings = Settings(
        beta_access_enabled=True,
        beta_session_cookie_name="beta_test_session",
        beta_session_secure_cookie=False,
        beta_session_db=tmp_path / "unused.sqlite3",
        beta_access_roster_json="{}",
    )
    app.dependency_overrides[get_settings] = lambda: beta_settings
    app.dependency_overrides[get_beta_access] = lambda: access
    app.dependency_overrides[get_teacher_memory] = lambda: memory
    try:
        with TestClient(app) as anonymous:
            status = anonymous.get("/api/v1/beta-session")
            assert status.status_code == 200
            assert status.json() == {
                "mode": "closed_beta",
                "authenticated": False,
                "display_label": "",
                "expires_at": None,
                "capabilities": [],
            }
            protected = anonymous.get("/api/v1/teacher-memory/profile")
            assert protected.status_code == 401

            denied = anonymous.post(
                "/api/v1/beta-session",
                json={"access_code": "wrong-code"},
            )
            assert denied.status_code == 401
            assert "teacher" not in denied.text.lower()

        with TestClient(app) as alpha_client:
            login = alpha_client.post(
                "/api/v1/beta-session",
                json={"access_code": "alpha-code"},
            )
            assert login.status_code == 200
            assert login.json()["display_label"] == "Alpha 教师"
            assert login.json()["capabilities"] == ["search", "teacher_memory"]
            assert "teacher_id" not in login.text
            cookie = login.headers["set-cookie"]
            assert "HttpOnly" in cookie
            assert "SameSite=strict" in cookie
            alpha_profile = alpha_client.get("/api/v1/teacher-memory/profile")
            assert alpha_profile.status_code == 200
            assert alpha_profile.json()["preferences"][0]["value"] == "高一"
            unavailable = alpha_client.get("/api/v1/exam-papers")
            assert unavailable.status_code == 403
            assert unavailable.json()["detail"] == {
                "code": "CAPABILITY_UNAVAILABLE",
                "capability": "paper",
                "message": "当前封闭测试尚未开放组卷。",
            }

            logout = alpha_client.delete("/api/v1/beta-session")
            assert logout.status_code == 200
            replay = alpha_client.get("/api/v1/teacher-memory/profile")
            assert replay.status_code == 401

        with TestClient(app) as beta_client:
            assert beta_client.post(
                "/api/v1/beta-session",
                json={"access_code": "beta-code"},
            ).status_code == 200
            beta_profile = beta_client.get("/api/v1/teacher-memory/profile")
            assert beta_profile.status_code == 200
            assert beta_profile.json()["preferences"][0]["value"] == "高三"
    finally:
        app.dependency_overrides.pop(get_teacher_memory, None)
        app.dependency_overrides.pop(get_beta_access, None)
        app.dependency_overrides.pop(get_settings, None)


def test_local_development_identity_remains_available_only_when_beta_is_disabled(tmp_path: Path) -> None:
    local_settings = Settings(
        beta_access_enabled=False,
        beta_session_db=tmp_path / "beta.sqlite3",
    )
    app.dependency_overrides[get_settings] = lambda: local_settings
    try:
        with TestClient(app) as client:
            status = client.get("/api/v1/beta-session")
            assert status.status_code == 200
            assert status.json() == {
                "mode": "local_development",
                "authenticated": True,
                "display_label": "本地开发教师",
                "expires_at": None,
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
            assert client.get("/api/v1/teacher-memory/profile").status_code == 200
    finally:
        app.dependency_overrides.pop(get_settings, None)
