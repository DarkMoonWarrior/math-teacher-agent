"""Solve Agent HTTP feature gate, records, SSE recovery, cancel, and resume."""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agent_runtime import (
    TeacherAgentError,
    TeacherAgentErrorCode,
    TeacherAgentRunStatus,
)
from app.core.config import Settings
from app.modules.solve_agent import SolveAgentWorkflow
from app.routes import solve_agent as route_mod
from app.routes.solve_agent import (
    _SolveAgentHttpError,
    router as solve_agent_router,
    solve_agent_error_handler,
)

from tests.test_solve_agent_workflow import FakeSolveRuntime, _result


@pytest.fixture()
def api_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    route_mod._RUNS.clear()
    runtime = FakeSolveRuntime()
    workflow = SolveAgentWorkflow(runtime=runtime)
    monkeypatch.setattr(
        route_mod,
        "get_settings",
        lambda: Settings(solve_agent_enabled=True, agent_runtime="dsh"),
    )
    monkeypatch.setattr(route_mod, "get_solve_agent_workflow", lambda: workflow)
    app = FastAPI()
    app.add_exception_handler(_SolveAgentHttpError, solve_agent_error_handler)
    app.include_router(solve_agent_router, prefix="/api/v1")
    return TestClient(app)


def test_feature_disabled_returns_structured_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    route_mod._RUNS.clear()
    monkeypatch.setattr(
        route_mod, "get_settings", lambda: Settings(solve_agent_enabled=False)
    )
    app = FastAPI()
    app.add_exception_handler(_SolveAgentHttpError, solve_agent_error_handler)
    app.include_router(solve_agent_router, prefix="/api/v1")
    client = TestClient(app)

    for method, path in [
        ("post", "/api/v1/agent/solve"),
        ("post", "/api/v1/agent/solve/stream"),
        ("get", "/api/v1/agent/solve/run_x"),
        ("get", "/api/v1/agent/solve/run_x/stream"),
        ("post", "/api/v1/agent/solve/run_x/cancel"),
        ("post", "/api/v1/agent/solve/run_x/resume"),
    ]:
        kwargs = (
            {"json": {"question_text": "解方程 2x-4=0。"}}
            if path.endswith("/solve") or path.endswith("/stream") and "run_x" not in path
            else {}
        )
        response = getattr(client, method)(path, **kwargs)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "FEATURE_DISABLED"


def test_post_solve_and_get_record(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/v1/agent/solve",
        json={"question_text": "解方程 2x-4=0。", "teacher_instruction": "分步讲解"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["solution"]["confidence_status"] == "teacher_review_required"
    assert payload["solution"]["math_verification"]["status"] == "inconclusive"
    record = api_client.get(f"/api/v1/agent/solve/{payload['run_id']}")
    assert record.status_code == 200
    assert record.json()["response"]["solution"]["explanation"]["final_answer"] == "x=2"


def test_stream_runs_once_and_terminal_snapshot_does_not_rerun(
    api_client: TestClient,
) -> None:
    workflow = route_mod.get_solve_agent_workflow()
    before = len(workflow.runtime.requests)
    with api_client.stream(
        "POST",
        "/api/v1/agent/solve/stream",
        json={"question_text": "解方程 2x-4=0。", "session_id": "tch_stream"},
    ) as stream:
        body = "".join(stream.iter_text())
    events = [
        json.loads(line[len("data: ") :])
        for line in body.splitlines()
        if line.startswith("data: ")
    ]
    assert events[0]["type"] == "run_started"
    assert events[-1]["type"] == "run_completed"
    assert events[-1]["data"]["solve_response"]["solution"]["mode"] == "live_ai"
    assert len(workflow.runtime.requests) == before + 1

    run_id = events[0]["run_id"]
    with api_client.stream(
        "GET", f"/api/v1/agent/solve/{run_id}/stream"
    ) as snapshot:
        snapshot_body = "".join(snapshot.iter_text())
    assert "solve_response" in snapshot_body
    assert len(workflow.runtime.requests) == before + 1


def test_cancel_completed_run_is_idempotent(api_client: TestClient) -> None:
    payload = api_client.post(
        "/api/v1/agent/solve", json={"question_text": "解方程 2x-4=0。"}
    ).json()
    response = api_client.post(f"/api/v1/agent/solve/{payload['run_id']}/cancel")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert route_mod.get_solve_agent_workflow().runtime.cancelled_runs == []


def test_failed_run_can_resume_same_session(api_client: TestClient) -> None:
    workflow = route_mod.get_solve_agent_workflow()
    workflow.runtime.result = _result(
        status=TeacherAgentRunStatus.FAILED,
        error=TeacherAgentError(
            code=TeacherAgentErrorCode.MODEL_UNAVAILABLE,
            message="模型暂不可用",
            request_id="req_failed",
        ),
        run_id="run_failed_solve",
    )
    failed = api_client.post(
        "/api/v1/agent/solve", json={"question_text": "解方程 2x-4=0。"}
    ).json()
    assert failed["status"] == "error"

    resumed = api_client.post(
        f"/api/v1/agent/solve/{failed['run_id']}/resume"
    )
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "ok"
    assert resumed.json()["run_id"] == "run_solve_resumed"
    assert workflow.runtime.resume_requests[0][0] == "tch_solve_1"


def test_completed_or_unknown_run_cannot_resume(api_client: TestClient) -> None:
    payload = api_client.post(
        "/api/v1/agent/solve", json={"question_text": "解方程 2x-4=0。"}
    ).json()
    completed = api_client.post(f"/api/v1/agent/solve/{payload['run_id']}/resume")
    missing = api_client.post("/api/v1/agent/solve/run_missing/resume")
    assert completed.status_code == 409
    assert completed.json()["error"]["code"] == "RUN_NOT_RESUMABLE"
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "RUN_NOT_FOUND"


def test_invalid_payload_is_rejected(api_client: TestClient) -> None:
    assert api_client.post("/api/v1/agent/solve", json={}).status_code == 422
    assert (
        api_client.post(
            "/api/v1/agent/solve", json={"question_text": "太短"}
        ).status_code
        == 422
    )
