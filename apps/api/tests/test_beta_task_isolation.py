"""Real Beta cookies, fake workflows and isolated in-memory run stores."""
import json
from uuid import uuid4

import pytest

from app.agent_runtime import TeacherAgentEvent, TeacherAgentEventType
from app.modules.search_agent.domain import SearchAgentResponse, SearchIntent, SearchPlan
from app.modules.solve_agent import SolveAgentResponse
from app.routes import search_agent, solve_agent
from app.routes import private_library_agent, question_authoring
from app.modules.private_library_agent import PrivateLibraryAgentResponse
from app.modules.question_authoring_agent import QuestionAuthoringAgentResponse
from app.routes.personal_question_library import get_personal_question_library
from app.main import app
from tests.test_beta_lifecycle import beta_lifecycle  # noqa: F401


class SyntheticWorkflow:
    def __init__(self, kind):
        self.kind = kind
        self.calls = []
        self.cancelled = []
        self.resumed = []

    async def run(self, command, *, session_id=None, request_id="", **kwargs):
        session = session_id if self.kind == "search" else command.session_id
        self.calls.append(session)
        common = dict(run_id=f"run_{uuid4().hex}", session_id=session or f"tch_{uuid4().hex}",
                      request_id=request_id, status="error",
                      error={"code": "MODEL_UNAVAILABLE", "message": "synthetic failure"})
        if self.kind == "search":
            return SearchAgentResponse(**common, raw_query=command,
                                       intent=SearchIntent(raw_query=command), plan_summary=SearchPlan(plan_id="synthetic"))
        return SolveAgentResponse(**common, question_text=command.question_text, solution_mode=command.solution_mode)

    async def stream(self, command, **kwargs):
        result = await self.run(command, **kwargs)
        fields = dict(run_id=result.run_id, session_id=result.session_id, request_id=result.request_id)
        yield TeacherAgentEvent(type=TeacherAgentEventType.RUN_STARTED, **fields)
        yield TeacherAgentEvent(type=TeacherAgentEventType.RUN_COMPLETED, **fields,
                                data={f"{self.kind}_response": result.model_dump(mode="json")})

    async def cancel(self, run_id):
        self.cancelled.append(run_id)
        return {"run_id": run_id, "status": "cancelled"}

    async def resume(self, command, *, session_id, **kwargs):
        self.resumed.append(session_id)
        return await self.run(command.model_copy(update={"session_id": session_id}), **kwargs)


@pytest.fixture
def tasks(beta_lifecycle, monkeypatch):
    clients, settings, *_ = beta_lifecycle
    settings.search_agent_enabled = True
    settings.solve_agent_enabled = True
    workflows = {kind: SyntheticWorkflow(kind) for kind in ("search", "solve")}
    for module in (search_agent, solve_agent):
        monkeypatch.setattr(module, "get_settings", lambda: settings)
        monkeypatch.setattr(module, "_RUNS", {})
    monkeypatch.setattr(search_agent, "get_search_agent_pipeline", lambda: workflows["search"])
    monkeypatch.setattr(solve_agent, "get_solve_agent_workflow", lambda: workflows["solve"])
    return clients, workflows


def start(client, kind, mode="sync", session_id=None):
    body = {"query": "synthetic-private-alpha"} if kind == "search" else {"question_text": "synthetic-private-alpha"}
    if session_id:
        body["session_id"] = session_id
    response = client.post(f"/api/v1/agent/{kind}" + ("/stream" if mode == "stream" else ""), json=body)
    assert response.status_code == 200
    if mode == "stream":
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
        return events[-1]["data"][f"{kind}_response"]
    return response.json()


@pytest.mark.parametrize("kind,operation", [(kind, op) for kind in ("search", "solve")
                                          for op in ("read", "stream", "cancel")] + [("solve", "resume")])
@pytest.mark.parametrize("mode", ["sync", "stream"])
def test_another_teacher_cannot_access_or_control_a_run(tasks, kind, operation, mode):
    clients, workflows = tasks
    result = start(clients["alpha"], kind, mode)
    path = f"/api/v1/agent/{kind}/{result['run_id']}"
    module = search_agent if kind == "search" else solve_agent
    if operation == "cancel":
        module._RUNS[result["run_id"]].status = "running"
    before = module._RUNS[result["run_id"]].model_copy(deep=True)
    method = "GET" if operation in ("read", "stream") else "POST"
    path += "" if operation == "read" else f"/{operation}"
    response = clients["beta"].request(method, path, headers={"X-Owner-Id": "alpha"}, params={"owner_id": "alpha"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RUN_NOT_FOUND"
    assert "synthetic-private-alpha" not in response.text
    assert module._RUNS[result["run_id"]] == before
    assert workflows[kind].cancelled == [] and workflows[kind].resumed == []
    own = clients["alpha"].request(method, path)
    assert own.status_code == 200
    assert "owner_id" not in own.text


@pytest.mark.parametrize("kind", ["search", "solve"])
def test_browser_session_alias_cannot_share_model_context_between_teachers(tasks, kind):
    clients, workflows = tasks
    start(clients["alpha"], kind, session_id="same-browser-alias")
    start(clients["beta"], kind, session_id="same-browser-alias")
    assert workflows[kind].calls[0] != workflows[kind].calls[1]


@pytest.mark.parametrize("kind", ["search", "solve"])
@pytest.mark.parametrize("mode", ["sync", "stream"])
def test_foreign_signed_session_rejected_before_execution(tasks, kind, mode):
    clients, workflows = tasks
    own = start(clients["alpha"], kind)
    before = len(workflows[kind].calls)
    body = {"query": "synthetic"} if kind == "search" else {"question_text": "synthetic"}
    body["session_id"] = own["session_id"]
    path = f"/api/v1/agent/{kind}" + ("/stream" if mode == "stream" else "")
    response = clients["beta"].post(path, json=body)
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "SESSION_NOT_AVAILABLE"
    assert len(workflows[kind].calls) == before
    assert clients["alpha"].post(path, json=body).status_code == 200


@pytest.mark.parametrize("kind", ["search", "solve"])
def test_run_id_collision_never_overwrites_another_owner(tasks, monkeypatch, kind):
    clients, workflows = tasks
    result = start(clients["alpha"], kind)
    module = search_agent if kind == "search" else solve_agent
    before = module._RUNS[result["run_id"]].model_copy(deep=True)
    original = workflows[kind].run

    async def collide(*args, **kwargs):
        response = await original(*args, **kwargs)
        return response.model_copy(update={"run_id": result["run_id"]})

    monkeypatch.setattr(workflows[kind], "run", collide)
    body = {"query": "synthetic beta"} if kind == "search" else {"question_text": "synthetic beta"}
    response = clients["beta"].post(f"/api/v1/agent/{kind}", json=body)
    assert response.status_code == 409
    assert module._RUNS[result["run_id"]] == before


@pytest.mark.parametrize("kind", ["search", "solve"])
def test_legacy_ownerless_run_is_never_claimed_by_caller(tasks, kind):
    clients, _ = tasks
    result = start(clients["alpha"], kind)
    module = search_agent if kind == "search" else solve_agent
    module._RUNS[result["run_id"]].owner_id = ""
    assert clients["alpha"].get(f"/api/v1/agent/{kind}/{result['run_id']}").status_code == 404


@pytest.mark.parametrize("kind", ["library", "authoring"])
def test_other_agent_entries_use_the_same_scoping_contract(beta_lifecycle, monkeypatch, kind):
    clients, settings, *_ = beta_lifecycle
    settings.question_authoring_agent_enabled = True
    calls = []

    class Workflow:
        async def run(self, command, *, owner_id, request_id="synthetic"):
            calls.append((owner_id, command.session_id))
            common = dict(request_id=request_id, session_id=command.session_id, status="error")
            if kind == "library":
                return PrivateLibraryAgentResponse(**common, query=command.query)
            return QuestionAuthoringAgentResponse(**common)

    if kind == "library":
        path = "/api/v1/agent/private-library/search"
        body = {"query": "synthetic", "private_content_consent": True}
        monkeypatch.setattr(private_library_agent, "get_private_library_agent_workflow", lambda: Workflow())
    else:
        path = "/api/v1/agent/question-authoring/draft"
        body = {"brief": {"request_text": "测试用高中数学单选题", "question_type": "single_choice", "target_difficulty": 2}}
        monkeypatch.setattr(question_authoring, "get_settings", lambda: settings)
        monkeypatch.setattr(question_authoring, "get_question_authoring_agent_workflow", lambda: Workflow())
        monkeypatch.setitem(app.dependency_overrides, get_personal_question_library, lambda: None)
    body["session_id"] = "same-browser-alias"
    first = clients["alpha"].post(path, json=body)
    assert first.status_code == 200
    assert clients["beta"].post(path, json=body).status_code == 200
    assert calls[0][1] != calls[1][1]
    body["session_id"] = first.json()["session_id"]
    assert clients["beta"].post(path, json=body).status_code == 404
    assert len(calls) == 2
    assert clients["alpha"].post(path, json=body).status_code == 200
    assert calls[-1] == calls[0]
    # The background authoring entry must reject before starting its worker too.
    if kind == "authoring":
        def no_worker():
            raise AssertionError("Foreign session must not start a background worker")
        monkeypatch.setattr(question_authoring, "get_question_authoring_job_registry", no_worker)
        assert clients["beta"].post("/api/v1/agent/question-authoring/jobs", json=body).status_code == 404
