from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.agent_runtime import (
    TeacherAgentCapabilities,
    TeacherAgentError,
    TeacherAgentErrorCode,
    TeacherAgentEvent,
    TeacherAgentHealth,
    TeacherAgentRunRequest,
    TeacherAgentRunResult,
    TeacherAgentRunStatus,
    TeacherAgentRuntime,
    TeacherAgentSession,
    TeacherAgentSessionStatus,
    TeacherAgentToolCall,
)
from app.core.identity import CurrentTeacher, get_current_teacher
from app.main import app
from app.modules.question_authoring import (
    QuestionAuthoringStatementPreview,
    QuestionDesignBrief,
)
from app.modules.question_authoring_agent import (
    QuestionAuthoringAgentCommand,
    QuestionAuthoringAgentResponse,
    QuestionAuthoringCancelCommand,
    QuestionAuthoringAgentWorkflow,
    QuestionAuthoringProgressRegistry,
    get_question_authoring_progress_registry,
)
from app.modules.personal_question_library import PersonalQuestionLibrary
from app.routes import question_authoring as question_authoring_routes
from app.routes.personal_question_library import get_personal_question_library


def draft_payload() -> dict:
    return {
        "draft_id": "qad_synthetic_1",
        "request_text": "围绕函数单调性命制一道单选题。",
        "question_type": "single_choice",
        "stem_plain": "已知函数 f(x)=x²，判断其单调性。",
        "stem_latex": r"已知函数 $f(x)=x^2$，判断其单调性。",
        "options": [
            {"key": "A", "text": "恒增"},
            {"key": "B", "text": "先减后增"},
            {"key": "C", "text": "恒减"},
            {"key": "D", "text": "不是函数"},
        ],
        "answer_value": "B",
        "solution_method": "定义法",
        "solution_steps": ["分区间判断。"],
        "final_answer": "先减后增。",
        "authoring_intent": "考查函数单调性。",
        "curriculum": {
            "node_id": "kp_monotonicity",
            "name": "函数单调性的判断",
            "volume": "必修第一册",
            "chapter": "函数",
            "section": "单调性",
            "mapping_source": "teacher_selected",
            "match_confidence": 1,
            "curriculum_status": "reviewed",
            "reviewed_by": "teacher",
        },
        "target_difficulty": 2,
        "estimated_difficulty": 2,
        "difficulty_source": "model_estimated",
        "verification": {
            "status": "teacher_review_required",
            "math_verifier_status": "unsupported",
            "math_verifier_checked": False,
            "teacher_review_required": True,
            "verifier_version": "math-v0.3.0",
            "checks": [
                {
                    "code": "solvability",
                    "status": "inconclusive",
                    "capability": "unsupported",
                    "evidence_source": "none",
                    "summary": "一般数学可解性尚无独立证据",
                    "details": [],
                },
                {
                    "code": "answer_solution_consistency",
                    "status": "passed",
                    "capability": "supported",
                    "evidence_source": "deterministic_structure",
                    "summary": "答案表达一致",
                    "details": [],
                },
                {
                    "code": "choice_answer_cardinality",
                    "status": "passed",
                    "capability": "supported",
                    "evidence_source": "deterministic_structure",
                    "summary": "答案数量合格",
                    "details": [],
                },
                {
                    "code": "distractor_quality",
                    "status": "inconclusive",
                    "capability": "unsupported",
                    "evidence_source": "none",
                    "summary": "干扰项语义待教师复核",
                    "details": [],
                },
                {
                    "code": "math_verifier",
                    "status": "inconclusive",
                    "capability": "unsupported",
                    "evidence_source": "none",
                    "summary": "当前 MathVerifier 不支持该生成题",
                    "details": [],
                },
                {
                    "code": "difficulty_disclosure",
                    "status": "passed",
                    "capability": "supported",
                    "evidence_source": "model_estimate",
                    "summary": "预计难度接近目标",
                    "details": [],
                },
            ],
            "details": ["结构检查不等于完整数学验证。"],
        },
        "source_type": "ai_generated",
        "visibility": "owner_only",
        "public_search_allowed": False,
        "share_allowed": False,
        "commercial_use_allowed": False,
        "model_training_allowed": False,
        "saved": False,
        "provider": "synthetic_provider",
        "model": "synthetic-author-v1",
        "prompt_revision": "question-authoring-v1",
        "warnings": ["必须由教师复核。"],
        "created_at": "2026-08-24T00:00:00+00:00",
    }


def brief() -> QuestionDesignBrief:
    return QuestionDesignBrief(
        request_text="围绕函数单调性命制一道单选题。",
        curriculum_node_id="kp_monotonicity",
        question_type="single_choice",
        target_difficulty=2,
    )


def tool_call(*, input_: dict | None = None, output: dict | None = None) -> TeacherAgentToolCall:
    return TeacherAgentToolCall(
        tool_name="create_question_draft",
        status="ok",
        input=input_ or brief().model_dump(mode="json", exclude_none=True),
        output=output
        or {
            "ok": True,
            "draft": draft_payload(),
            "request_id": "req_tool_authoring",
            "error": None,
        },
    )


class FakeRuntime(TeacherAgentRuntime):
    runtime_name = "dsh"
    runtime_version = "test"

    def __init__(self, *, tool_calls: list[TeacherAgentToolCall] | None = None) -> None:
        self.requests: list[TeacherAgentRunRequest] = []
        self.tool_calls = tool_calls if tool_calls is not None else [tool_call()]

    async def run(self, request: TeacherAgentRunRequest) -> TeacherAgentRunResult:
        self.requests.append(request)
        return TeacherAgentRunResult(
            run_id="run_authoring_1",
            session_id="session_authoring_1",
            request_id=request.request_id,
            runtime="dsh",
            status=TeacherAgentRunStatus.COMPLETED,
            final_text="模型声称题目已经发布，但该文本不可信。",
            tool_calls=self.tool_calls,
        )

    async def stream(
        self,
        request: TeacherAgentRunRequest,
    ) -> AsyncIterator[TeacherAgentEvent]:
        del request
        if False:
            yield TeacherAgentEvent(
                type="run_started",
                run_id="",
                session_id="",
                request_id="",
            )

    async def cancel(self, run_id: str) -> TeacherAgentRunResult:
        return TeacherAgentRunResult(
            run_id=run_id,
            session_id="session_authoring_1",
            request_id="req_cancel",
            runtime="dsh",
            status=TeacherAgentRunStatus.CANCELLED,
            error=TeacherAgentError(
                code=TeacherAgentErrorCode.RUN_CANCELLED,
                message="已取消",
            ),
        )

    async def resume(
        self,
        session_id: str,
        request: TeacherAgentRunRequest,
    ) -> TeacherAgentRunResult:
        del session_id
        return await self.run(request)

    async def get_session(self, session_id: str) -> TeacherAgentSession:
        return TeacherAgentSession(
            session_id=session_id,
            runtime="dsh",
            status=TeacherAgentSessionStatus.IDLE,
        )

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

    async def capabilities(self) -> TeacherAgentCapabilities:
        return TeacherAgentCapabilities()


def run(coro):
    return asyncio.run(coro)


def test_progress_registry_exposes_stage_only_to_the_bound_owner() -> None:
    registry = QuestionAuthoringProgressRegistry()
    progress_id = "qap_1234567890abcdefghij"
    registry.register(progress_id, owner_id="teacher_a")

    assert registry.update(progress_id, "reviewing") is True
    assert registry.snapshot(progress_id, owner_id="teacher_a").stage == "reviewing"
    with pytest.raises(KeyError):
        registry.snapshot(progress_id, owner_id="teacher_b")


def test_progress_registry_publishes_only_versioned_reviewed_statement_snapshots() -> None:
    registry = QuestionAuthoringProgressRegistry()
    progress_id = "qap_statement_preview_1234567890"
    registry.register(progress_id, owner_id="teacher_a")
    first = QuestionAuthoringStatementPreview(
        question_type="fill_blank",
        stem_plain="已知函数 f(x)=x²，则 f(2)=______。",
        stem_latex=r"已知函数 $f(x)=x^2$，则 $f(2)=\_\_\_\_$。",
        estimated_difficulty=1,
    )
    second = first.model_copy(
        update={"stem_plain": "已知函数 f(x)=x²+1，则 f(2)=______。"}
    )

    assert registry.publish_statement(progress_id, first) is True
    approved = registry.snapshot(progress_id, owner_id="teacher_a")
    assert approved.statement == first
    assert approved.statement_revision == 1
    assert approved.statement_state == "approved"

    registry.update(progress_id, "refining")
    assert registry.snapshot(
        progress_id, owner_id="teacher_a"
    ).statement_state == "adjusting"

    assert registry.publish_statement(progress_id, second) is True
    repaired = registry.snapshot(progress_id, owner_id="teacher_a")
    assert repaired.statement == second
    assert repaired.statement_revision == 2
    assert repaired.statement_state == "approved"


def test_workflow_accepts_only_exact_structured_tool_result() -> None:
    runtime = FakeRuntime()
    workflow = QuestionAuthoringAgentWorkflow(runtime=runtime)

    response = run(
        workflow.run(
            QuestionAuthoringAgentCommand(brief=brief()),
            owner_id="teacher_a",
            request_id="req_authoring",
        )
    )

    assert response.status == "ok"
    assert response.draft is not None
    assert response.draft.visibility == "owner_only"
    assert response.draft.saved is False
    assert response.draft.verification.status == "teacher_review_required"
    assert response.draft.verification.math_verifier_status == "unsupported"
    assert response.tool_call_count == 1
    request = runtime.requests[0]
    assert request.teacher_user_id == "teacher_a"
    assert "必须且只能调用一次 create_question_draft" in request.user_message
    assert "owner_id" not in request.user_message.split("命题请求JSON：", 1)[1]
    assert "已经发布" not in response.model_dump_json()


def test_workflow_requires_agent_to_preserve_the_progress_identifier() -> None:
    progress_id = "qap_1234567890abcdefghij"
    exact_input = brief().model_dump(mode="json", exclude_none=True)
    exact_input["progress_id"] = progress_id
    runtime = FakeRuntime(tool_calls=[tool_call(input_=exact_input)])

    response = run(
        QuestionAuthoringAgentWorkflow(runtime=runtime).run(
            QuestionAuthoringAgentCommand(brief=brief(), progress_id=progress_id),
            owner_id="teacher_a",
        )
    )

    assert response.status == "ok"
    assert progress_id in runtime.requests[0].user_message

    changed_input = {**exact_input, "progress_id": "qap_abcdefghij1234567890"}
    changed = run(
        QuestionAuthoringAgentWorkflow(
            runtime=FakeRuntime(tool_calls=[tool_call(input_=changed_input)])
        ).run(
            QuestionAuthoringAgentCommand(brief=brief(), progress_id=progress_id),
            owner_id="teacher_a",
        )
    )
    assert changed.status == "error"
    assert changed.error["code"] == "TOOL_EXECUTION_ERROR"


def test_workflow_rejects_model_changed_input_extra_calls_and_invalid_private_state() -> None:
    changed = brief().model_dump(mode="json", exclude_none=True)
    changed["target_difficulty"] = 5
    changed_runtime = FakeRuntime(tool_calls=[tool_call(input_=changed)])
    changed_response = run(
        QuestionAuthoringAgentWorkflow(runtime=changed_runtime).run(
            QuestionAuthoringAgentCommand(brief=brief()),
            owner_id="teacher_a",
        )
    )
    assert changed_response.status == "error"
    assert changed_response.error["code"] == "TOOL_EXECUTION_ERROR"

    extra_runtime = FakeRuntime(tool_calls=[tool_call(), tool_call()])
    extra_response = run(
        QuestionAuthoringAgentWorkflow(runtime=extra_runtime).run(
            QuestionAuthoringAgentCommand(brief=brief()),
            owner_id="teacher_a",
        )
    )
    assert extra_response.status == "error"
    assert extra_response.tool_call_count == 2

    invalid = draft_payload()
    invalid["visibility"] = "public"
    invalid_runtime = FakeRuntime(
        tool_calls=[
            tool_call(
                output={
                    "ok": True,
                    "draft": invalid,
                    "request_id": "req_bad",
                }
            )
        ]
    )
    invalid_response = run(
        QuestionAuthoringAgentWorkflow(runtime=invalid_runtime).run(
            QuestionAuthoringAgentCommand(brief=brief()),
            owner_id="teacher_a",
        )
    )
    assert invalid_response.status == "error"
    assert "私有状态" in invalid_response.error["message"]

    inconsistent_trust = draft_payload()
    inconsistent_trust["verification"]["status"] = "checks_failed"
    trust_runtime = FakeRuntime(
        tool_calls=[
            tool_call(
                output={
                    "ok": True,
                    "draft": inconsistent_trust,
                    "request_id": "req_bad_trust",
                }
            )
        ]
    )
    trust_response = run(
        QuestionAuthoringAgentWorkflow(runtime=trust_runtime).run(
            QuestionAuthoringAgentCommand(brief=brief()),
            owner_id="teacher_a",
        )
    )
    assert trust_response.status == "error"
    assert "私有状态" in trust_response.error["message"]


class FakeQuestionAuthoringWorkflow:
    def __init__(self) -> None:
        self.calls: list[tuple[QuestionAuthoringAgentCommand, str, str]] = []

    async def run(
        self,
        command: QuestionAuthoringAgentCommand,
        *,
        owner_id: str,
        request_id: str,
    ) -> QuestionAuthoringAgentResponse:
        self.calls.append((command, owner_id, request_id))
        return QuestionAuthoringAgentResponse(
            request_id=request_id,
            session_id="session_http_authoring",
            run_id="run_http_authoring",
            status="ok",
            draft=draft_payload(),
            tool_request_id="req_http_tool",
            tool_call_count=1,
        )


def test_http_route_is_feature_gated(monkeypatch) -> None:
    monkeypatch.setattr(
        question_authoring_routes,
        "get_settings",
        lambda: SimpleNamespace(question_authoring_agent_enabled=False),
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/agent/question-authoring/draft",
            json={"brief": brief().model_dump(mode="json", exclude_none=True)},
        )
    assert response.status_code == 503


def test_http_route_binds_current_teacher_and_stages_only_for_that_owner(
    monkeypatch,
    tmp_path: Path,
) -> None:
    workflow = FakeQuestionAuthoringWorkflow()
    library = PersonalQuestionLibrary(tmp_path / "personal-question-library.sqlite3")
    monkeypatch.setattr(
        question_authoring_routes,
        "get_settings",
        lambda: SimpleNamespace(question_authoring_agent_enabled=True),
    )
    monkeypatch.setattr(
        question_authoring_routes,
        "get_question_authoring_agent_workflow",
        lambda: workflow,
    )
    app.dependency_overrides[get_current_teacher] = lambda: CurrentTeacher(
        teacher_id="teacher_http_a",
        source="authenticated_session",
    )
    app.dependency_overrides[get_personal_question_library] = lambda: library
    progress_registry = get_question_authoring_progress_registry()
    progress_registry.clear()
    try:
        progress_id = "qap_http_authoring_1234567890"
        payload = {
            "brief": brief().model_dump(mode="json", exclude_none=True),
            "progress_id": progress_id,
        }
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/agent/question-authoring/draft",
                headers={"X-Request-Id": "req_http_authoring"},
                json=payload,
            )
            forged_top = client.post(
                "/api/v1/agent/question-authoring/draft",
                json={**payload, "owner_id": "teacher_b"},
            )
            forged_brief = client.post(
                "/api/v1/agent/question-authoring/draft",
                json={"brief": {**payload["brief"], "owner_id": "teacher_b"}},
            )
            progress = client.get(
                f"/api/v1/agent/question-authoring/progress/{progress_id}"
            )
    finally:
        app.dependency_overrides.pop(get_current_teacher, None)
        app.dependency_overrides.pop(get_personal_question_library, None)
        progress_registry.clear()

    assert response.status_code == 200
    assert response.json()["draft"]["visibility"] == "owner_only"
    assert response.json()["draft"]["saved"] is False
    assert progress.status_code == 200
    assert progress.json()["stage"] == "staging"
    staged = library.get_authoring_draft("qad_synthetic_1", owner_id="teacher_http_a")
    assert staged.current_revision == 1
    assert staged.saved is False
    assert workflow.calls[0][1:] == ("teacher_http_a", "req_http_authoring")
    assert forged_top.status_code == 422
    assert forged_brief.status_code == 422
    assert len(workflow.calls) == 1


def test_background_authoring_job_stages_complete_result_and_is_resumable(
    monkeypatch, tmp_path: Path
) -> None:
    workflow = FakeQuestionAuthoringWorkflow()
    library = PersonalQuestionLibrary(tmp_path / "background-authoring.sqlite3")
    monkeypatch.setattr(
        question_authoring_routes,
        "get_settings",
        lambda: SimpleNamespace(question_authoring_agent_enabled=True),
    )
    monkeypatch.setattr(
        question_authoring_routes,
        "get_question_authoring_agent_workflow",
        lambda: workflow,
    )
    app.dependency_overrides[get_current_teacher] = lambda: CurrentTeacher(
        teacher_id="teacher_background", source="authenticated_session"
    )
    app.dependency_overrides[get_personal_question_library] = lambda: library
    jobs = question_authoring_routes.get_question_authoring_job_registry()
    jobs.clear()
    get_question_authoring_progress_registry().clear()
    try:
        with TestClient(app) as client:
            started = client.post(
                "/api/v1/agent/question-authoring/jobs",
                json={"brief": brief().model_dump(mode="json", exclude_none=True)},
            )
            assert started.status_code == 202
            job = started.json()
            for _ in range(100):
                current = client.get(
                    f"/api/v1/agent/question-authoring/jobs/{job['job_id']}"
                )
                assert current.status_code == 200
                job = current.json()
                if job["status"] == "succeeded":
                    break
                import time
                time.sleep(0.01)
            latest = client.get("/api/v1/agent/question-authoring/jobs/latest")
        assert job["status"] == "succeeded"
        assert job["result"]["draft_id"] == "qad_synthetic_1"
        assert latest.json()["job_id"] == job["job_id"]
        assert library.get_authoring_draft(
            "qad_synthetic_1", owner_id="teacher_background"
        ).current_revision == 1
    finally:
        app.dependency_overrides.pop(get_current_teacher, None)
        app.dependency_overrides.pop(get_personal_question_library, None)
        jobs.clear()
        get_question_authoring_progress_registry().clear()


def test_background_authoring_cancel_does_not_stage_a_partial_draft(
    monkeypatch, tmp_path: Path
) -> None:
    from threading import Event

    class BlockingWorkflow:
        def __init__(self) -> None:
            self.entered = Event()
            self.release = Event()

        async def run(self, command, *, owner_id: str, request_id: str):
            self.entered.set()
            await asyncio.to_thread(self.release.wait, 2)
            return QuestionAuthoringAgentResponse(
                request_id=request_id,
                status="ok",
                draft=draft_payload(),
            )

    workflow = BlockingWorkflow()
    library = PersonalQuestionLibrary(tmp_path / "background-authoring-cancel.sqlite3")
    monkeypatch.setattr(
        question_authoring_routes,
        "get_settings",
        lambda: SimpleNamespace(question_authoring_agent_enabled=True),
    )
    monkeypatch.setattr(
        question_authoring_routes,
        "get_question_authoring_agent_workflow",
        lambda: workflow,
    )
    app.dependency_overrides[get_current_teacher] = lambda: CurrentTeacher(
        teacher_id="teacher_cancel", source="authenticated_session"
    )
    app.dependency_overrides[get_personal_question_library] = lambda: library
    jobs = question_authoring_routes.get_question_authoring_job_registry()
    jobs.clear()
    get_question_authoring_progress_registry().clear()
    try:
        with TestClient(app) as client:
            started = client.post(
                "/api/v1/agent/question-authoring/jobs",
                json={"brief": brief().model_dump(mode="json", exclude_none=True)},
            ).json()
            assert workflow.entered.wait(timeout=1)
            cancelled = client.post(
                f"/api/v1/agent/question-authoring/jobs/{started['job_id']}/cancel"
            )
            assert cancelled.status_code == 200
            assert cancelled.json()["status"] == "cancelled"
            workflow.release.set()
            for _ in range(50):
                current = client.get(
                    f"/api/v1/agent/question-authoring/jobs/{started['job_id']}"
                ).json()
                if (
                    current["status"] == "cancelled"
                    and current["updated_at"] != cancelled.json()["updated_at"]
                ):
                    break
                import time

                time.sleep(0.01)
        assert current["status"] == "cancelled"
        assert current["result"] == {}
        with pytest.raises(KeyError):
            library.get_authoring_draft(
                "qad_synthetic_1", owner_id="teacher_cancel"
            )
    finally:
        workflow.release.set()
        app.dependency_overrides.pop(get_current_teacher, None)
        app.dependency_overrides.pop(get_personal_question_library, None)
        jobs.clear()
        get_question_authoring_progress_registry().clear()


def test_background_authoring_cancel_can_preserve_the_latest_reviewed_statement(
    monkeypatch, tmp_path: Path
) -> None:
    from threading import Event

    statement = QuestionAuthoringStatementPreview(
        question_type="single_choice",
        stem_plain="已知函数 f(x)=x²，判断其单调性。",
        stem_latex=r"已知函数 $f(x)=x^2$，判断其单调性。",
        options=[
            {"key": "A", "text": "恒增"},
            {"key": "B", "text": "先减后增"},
            {"key": "C", "text": "恒减"},
            {"key": "D", "text": "不是函数"},
        ],
        estimated_difficulty=2,
    )

    class BlockingWorkflow:
        def __init__(self) -> None:
            self.entered = Event()
            self.release = Event()

        async def run(self, command, *, owner_id: str, request_id: str):
            get_question_authoring_progress_registry().publish_statement(
                command.progress_id,
                statement,
            )
            get_question_authoring_progress_registry().update(
                command.progress_id,
                "solving",
            )
            self.entered.set()
            await asyncio.to_thread(self.release.wait, 2)
            return QuestionAuthoringAgentResponse(
                request_id=request_id,
                status="ok",
                draft=draft_payload(),
            )

    workflow = BlockingWorkflow()
    library = PersonalQuestionLibrary(tmp_path / "background-authoring-preserve.sqlite3")
    monkeypatch.setattr(
        question_authoring_routes,
        "get_settings",
        lambda: SimpleNamespace(question_authoring_agent_enabled=True),
    )
    monkeypatch.setattr(
        question_authoring_routes,
        "get_question_authoring_agent_workflow",
        lambda: workflow,
    )
    app.dependency_overrides[get_current_teacher] = lambda: CurrentTeacher(
        teacher_id="teacher_preserve", source="authenticated_session"
    )
    app.dependency_overrides[get_personal_question_library] = lambda: library
    jobs = question_authoring_routes.get_question_authoring_job_registry()
    jobs.clear()
    get_question_authoring_progress_registry().clear()
    try:
        with TestClient(app) as client:
            started = client.post(
                "/api/v1/agent/question-authoring/jobs",
                json={"brief": brief().model_dump(mode="json", exclude_none=True)},
            ).json()
            assert workflow.entered.wait(timeout=1)
            progress = client.get(
                f"/api/v1/agent/question-authoring/progress/{started['subject_id']}"
            )
            cancelled = client.post(
                f"/api/v1/agent/question-authoring/jobs/{started['job_id']}/cancel",
                json={"preserve_statement": True},
            )
            workflow.release.set()
            for _ in range(50):
                current = client.get(
                    f"/api/v1/agent/question-authoring/jobs/{started['job_id']}"
                ).json()
                if current["status"] == "cancelled":
                    break
                import time

                time.sleep(0.01)

        assert progress.status_code == 200
        assert progress.json()["statement"]["stem_plain"] == statement.stem_plain
        assert progress.json()["statement_revision"] == 1
        assert current["status"] == "cancelled"
        assert current["result"]["statement_preserved"] is True
        assert current["result"]["statement"]["stem_plain"] == statement.stem_plain
        preserved_id = current["result"]["draft_id"]
        assert current["result"]["solution_missing"] is True
        preserved = library.get_authoring_draft(
            preserved_id,
            owner_id="teacher_preserve",
        )
        assert preserved.saved is False
        assert preserved.current.draft.stem_plain == statement.stem_plain
        assert preserved.current.draft.answer_value == "无"
        assert preserved.current.draft.solution_method == "无"
        assert preserved.current.draft.solution_steps == ["无"]
        assert preserved.current.draft.final_answer == "无"
        assert preserved.current.draft.solution_status == "needs_teacher_verification"
        assert "解析未生成" in (preserved.current.draft.solution_issue or "")
        with pytest.raises(KeyError):
            library.get_authoring_draft(
                "qad_synthetic_1", owner_id="teacher_preserve"
            )
    finally:
        workflow.release.set()
        app.dependency_overrides.pop(get_current_teacher, None)
        app.dependency_overrides.pop(get_personal_question_library, None)
        jobs.clear()
        get_question_authoring_progress_registry().clear()


def test_cancel_preserve_rejects_statement_that_is_being_repaired(
    tmp_path: Path,
) -> None:
    """The API must not preserve an obsolete snapshot while it is marked adjusting."""
    from threading import Event

    statement = QuestionAuthoringStatementPreview(
        question_type="fill_blank",
        stem_plain="函数 f(x)=x² 在 x=1 处的函数值为______。",
        stem_latex=r"函数 $f(x)=x^2$ 在 $x=1$ 处的函数值为______。",
        options=[],
        estimated_difficulty=1,
    )
    entered = Event()
    release = Event()

    def runner(_report):
        entered.set()
        release.wait(2)
        return {}

    teacher = CurrentTeacher(teacher_id="teacher_adjusting", source="authenticated_session")
    jobs = question_authoring_routes.get_question_authoring_job_registry()
    progress = get_question_authoring_progress_registry()
    jobs.clear()
    progress.clear()
    progress_id = "qap_adjusting"
    progress.register(progress_id, owner_id=teacher.teacher_id)
    progress.publish_statement(progress_id, statement)
    progress.update(progress_id, "refining")
    try:
        started = jobs.start(
            kind=question_authoring_routes.AUTHORING_JOB_KIND,
            subject_id=progress_id,
            owner_id=teacher.teacher_id,
            runner=runner,
        )
        assert entered.wait(timeout=1)
        cancelled = asyncio.run(
            question_authoring_routes.cancel_question_authoring_job(
                started.job_id,
                QuestionAuthoringCancelCommand(preserve_statement=True),
                teacher,
            )
        )
        assert cancelled.status == "cancelled"
        assert cancelled.result == {}
        assert "没有可保留" in cancelled.message
    finally:
        release.set()
        jobs.clear()
        progress.clear()


def test_background_authoring_retries_dict_shaped_agent_errors_without_exposing_them(
    monkeypatch, tmp_path: Path
) -> None:
    class RetryWorkflow:
        def __init__(self) -> None:
            self.calls = 0

        async def run(self, command, *, owner_id: str, request_id: str):
            self.calls += 1
            if self.calls == 1:
                return QuestionAuthoringAgentResponse(
                    request_id=request_id,
                    status="error",
                    error={"code": "QUESTION_AUTHORING_FAILED", "message": "本轮解析未通过审核"},
                )
            return QuestionAuthoringAgentResponse(
                request_id=request_id,
                status="ok",
                draft=draft_payload(),
            )

    workflow = RetryWorkflow()
    library = PersonalQuestionLibrary(tmp_path / "background-authoring-retry.sqlite3")
    monkeypatch.setattr(question_authoring_routes, "time", SimpleNamespace(sleep=lambda _: None))
    monkeypatch.setattr(
        question_authoring_routes,
        "get_settings",
        lambda: SimpleNamespace(question_authoring_agent_enabled=True),
    )
    monkeypatch.setattr(
        question_authoring_routes,
        "get_question_authoring_agent_workflow",
        lambda: workflow,
    )
    app.dependency_overrides[get_current_teacher] = lambda: CurrentTeacher(
        teacher_id="teacher_retry", source="authenticated_session"
    )
    app.dependency_overrides[get_personal_question_library] = lambda: library
    jobs = question_authoring_routes.get_question_authoring_job_registry()
    jobs.clear()
    get_question_authoring_progress_registry().clear()
    try:
        with TestClient(app) as client:
            started = client.post(
                "/api/v1/agent/question-authoring/jobs",
                json={"brief": brief().model_dump(mode="json", exclude_none=True)},
            ).json()
            for _ in range(100):
                job = client.get(
                    f"/api/v1/agent/question-authoring/jobs/{started['job_id']}"
                ).json()
                if job["status"] == "succeeded":
                    break
                import time as clock
                clock.sleep(0.01)
        assert job["status"] == "succeeded"
        assert workflow.calls == 2
        assert "dict" not in job["error"]
    finally:
        app.dependency_overrides.pop(get_current_teacher, None)
        app.dependency_overrides.pop(get_personal_question_library, None)
        jobs.clear()
        get_question_authoring_progress_registry().clear()
