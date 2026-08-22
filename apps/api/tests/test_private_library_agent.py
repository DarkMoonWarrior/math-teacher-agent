from __future__ import annotations

import asyncio
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agent_runtime import (
    TeacherAgentRunResult,
    TeacherAgentRunStatus,
    TeacherAgentToolCall,
)
from app.modules.private_library import PrivateRetrievalGrantRegistry
from app.modules.private_library_agent import (
    PrivateLibraryAgentCommand,
    PrivateLibraryAgentResponse,
    PrivateLibraryAgentWorkflow,
)
from app.core.identity import CurrentTeacher, get_current_teacher
from app.routes import private_library_agent as route_mod
from app.routes.private_library_agent import router


class FakePrivateRuntime:
    runtime_name = "dsh"

    def __init__(self) -> None:
        self.requests = []

    async def run(self, request):
        self.requests.append(request)
        query = request.user_message.split("检索查询：", 1)[1].splitlines()[0]
        limit = int(request.user_message.split("返回上限：", 1)[1].splitlines()[0])
        token = request.user_message.split("检索许可：", 1)[1].splitlines()[0]
        return TeacherAgentRunResult(
            run_id="run_private_1",
            session_id="tch_private_1",
            request_id=request.request_id,
            runtime="dsh",
            status=TeacherAgentRunStatus.COMPLETED,
            tool_calls=[TeacherAgentToolCall(
                tool_name="search_private_library",
                status="ok",
                input={"query": query, "limit": limit, "consent_token": token},
                output={
                    "ok": True,
                    "query": query,
                    "items": [{
                        "library_item_id": "lib_1",
                        "title": "函数讲义",
                        "excerpt": "函数单调性例题。",
                        "source_version": 2,
                        "rights_basis": "original",
                        "text_review_status": "confirmed",
                        "visibility": "private",
                    }],
                    "total": 1,
                    "truncated": False,
                    "content_scope": "matching_excerpts",
                    "visibility": "private",
                    "request_id": "req_tool_1",
                    "error": None,
                },
            )],
        )


def test_workflow_returns_only_grounded_private_search_contract() -> None:
    runtime = FakePrivateRuntime()
    workflow = PrivateLibraryAgentWorkflow(
        runtime=runtime, grants=PrivateRetrievalGrantRegistry()
    )
    response = asyncio.run(
        workflow.run(
            PrivateLibraryAgentCommand(
                query="函数单调性", private_content_consent=True, limit=5
            ),
            owner_id="teacher_a",
            request_id="req_private_1",
        )
    )

    assert response.status == "ok"
    assert response.result is not None
    assert response.result.items[0].visibility == "private"
    assert response.result.items[0].excerpt == "函数单调性例题。"
    payload = response.model_dump()
    assert "consent_token" not in payload
    assert "owner_id" not in payload
    assert "检索许可" in runtime.requests[0].user_message


def test_command_requires_literal_per_action_consent() -> None:
    with pytest.raises(ValueError):
        PrivateLibraryAgentCommand(query="函数", private_content_consent=False)


def test_public_route_gets_owner_from_server_identity_and_rejects_missing_consent(monkeypatch) -> None:
    owners: list[str] = []

    class FakeWorkflow:
        async def run(self, command, *, owner_id: str):
            owners.append(owner_id)
            return PrivateLibraryAgentResponse(
                request_id="req_route",
                status="ok",
                query=command.query,
                result={
                    "query": command.query,
                    "items": [],
                    "total": 0,
                    "truncated": False,
                    "content_scope": "matching_excerpts",
                    "visibility": "private",
                },
            )

    monkeypatch.setattr(route_mod, "get_private_library_agent_workflow", lambda: FakeWorkflow())
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_current_teacher] = lambda: CurrentTeacher(
        teacher_id="server_teacher", source="authenticated_session"
    )
    client = TestClient(app)

    accepted = client.post(
        "/api/v1/agent/private-library/search",
        json={"query": "函数", "private_content_consent": True, "owner_id": "attacker"},
    )
    assert accepted.status_code == 422
    accepted = client.post(
        "/api/v1/agent/private-library/search",
        json={"query": "函数", "private_content_consent": True},
    )
    assert accepted.status_code == 200
    assert owners == ["server_teacher"]
    rejected = client.post(
        "/api/v1/agent/private-library/search", json={"query": "函数"}
    )
    assert rejected.status_code == 422
