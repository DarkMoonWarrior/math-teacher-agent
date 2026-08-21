"""SolveAgentWorkflow trust, lifecycle, cancel, and resume tests."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from app.agent_runtime import (
    TeacherAgentCapabilities,
    TeacherAgentError,
    TeacherAgentErrorCode,
    TeacherAgentEvent,
    TeacherAgentEventType,
    TeacherAgentHealth,
    TeacherAgentRunRequest,
    TeacherAgentRunResult,
    TeacherAgentRunStatus,
    TeacherAgentRuntime,
    TeacherAgentSession,
    TeacherAgentSessionStatus,
    TeacherAgentToolCall,
)
from app.modules.solve_agent import SolveAgentCommand, SolveAgentWorkflow


def _solution_output(*, ok: bool = True) -> dict:
    return {
        "ok": ok,
        "question_text": "解方程 2x-4=0。",
        "solution_mode": "standard",
        "explanation": {
            "method": "代数法",
            "steps": ["移项并合并同类项。", "解得 x=2。"],
            "final_answer": "x=2",
        },
        "knowledge_points": ["一元一次方程"],
        "common_mistakes": ["移项忘记变号"],
        "teaching_notes": ["请教师复核"],
        "confidence_status": "teacher_review_required",
        "math_verification": {
            "status": "inconclusive",
            "capability": "unsupported",
            "scope": "generated_solution",
            "evidence_source": "none",
            "method": None,
            "computed_answer": None,
            "source_answer": None,
            "details": ["当前 MathVerifier 不支持对此完整推导做独立验证。"],
            "verifier_version": None,
        },
        "verification_evidence": ["当前 MathVerifier 不支持对此完整推导做独立验证。"],
        "provider": "fake_model",
        "model": "fake-solver-v1",
        "mode": "live_ai",
        "matched_question_id": None,
        "match_score": None,
        "alternative_available": True,
        "warnings": ["请由教师复核"],
        "request_id": "req_tool_solve",
        "error": None,
    }


def _solve_call(output: dict | None = None) -> TeacherAgentToolCall:
    return TeacherAgentToolCall(
        tool_name="solve_question",
        status="ok",
        input={"question_text": "解方程 2x-4=0。"},
        output=output or _solution_output(),
        started_at=1,
        finished_at=2,
    )


def _result(
    *,
    tool_calls: list[TeacherAgentToolCall] | None = None,
    status: TeacherAgentRunStatus = TeacherAgentRunStatus.COMPLETED,
    error: TeacherAgentError | None = None,
    run_id: str = "run_solve_1",
    session_id: str = "tch_solve_1",
) -> TeacherAgentRunResult:
    return TeacherAgentRunResult(
        run_id=run_id,
        session_id=session_id,
        request_id="req_solve_1",
        runtime="dsh",
        status=status,
        final_text="模型声称已经程序验证通过，但该文本不可信。",
        tool_calls=tool_calls if tool_calls is not None else [_solve_call()],
        error=error,
    )


class FakeSolveRuntime(TeacherAgentRuntime):
    runtime_name = "dsh"
    runtime_version = "test"

    def __init__(self, result: TeacherAgentRunResult | None = None) -> None:
        self.result = result or _result()
        self.resume_result = _result(run_id="run_solve_resumed")
        self.requests: list[TeacherAgentRunRequest] = []
        self.resume_requests: list[tuple[str, TeacherAgentRunRequest]] = []
        self.cancelled_runs: list[str] = []

    async def run(self, request: TeacherAgentRunRequest) -> TeacherAgentRunResult:
        self.requests.append(request)
        return self.result

    async def stream(
        self, request: TeacherAgentRunRequest
    ) -> AsyncIterator[TeacherAgentEvent]:
        self.requests.append(request)
        yield TeacherAgentEvent(
            type=TeacherAgentEventType.RUN_STARTED,
            run_id=self.result.run_id,
            session_id=self.result.session_id,
            request_id=request.request_id,
            sequence=0,
        )
        call = self.result.tool_calls[0]
        yield TeacherAgentEvent(
            type=TeacherAgentEventType.TOOL_STARTED,
            run_id=self.result.run_id,
            session_id=self.result.session_id,
            request_id=request.request_id,
            data={"tool_name": call.tool_name, "input": call.input},
            sequence=1,
        )
        yield TeacherAgentEvent(
            type=TeacherAgentEventType.TOOL_FINISHED,
            run_id=self.result.run_id,
            session_id=self.result.session_id,
            request_id=request.request_id,
            data={
                "tool_name": call.tool_name,
                "status": call.status,
                "input": call.input,
                "output": call.output,
            },
            sequence=2,
        )
        yield TeacherAgentEvent(
            type=TeacherAgentEventType.RUN_COMPLETED,
            run_id=self.result.run_id,
            session_id=self.result.session_id,
            request_id=request.request_id,
            data={"final_text": self.result.final_text},
            sequence=3,
        )

    async def cancel(self, run_id: str) -> TeacherAgentRunResult:
        self.cancelled_runs.append(run_id)
        return _result(
            status=TeacherAgentRunStatus.CANCELLED,
            error=TeacherAgentError(
                code=TeacherAgentErrorCode.RUN_CANCELLED,
                message="已取消",
                request_id="req_cancel",
            ),
            run_id=run_id,
        )

    async def resume(
        self, session_id: str, request: TeacherAgentRunRequest
    ) -> TeacherAgentRunResult:
        self.resume_requests.append((session_id, request))
        return self.resume_result.model_copy(update={"session_id": session_id})

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
            visible_tool_count=6,
        )

    async def capabilities(self) -> TeacherAgentCapabilities:
        return TeacherAgentCapabilities(
            run=True,
            stream=True,
            cancel=True,
            resume=True,
            get_session=True,
            health=True,
        )


def _run(coro):
    return asyncio.run(coro)


def test_run_accepts_only_the_structured_solve_tool_result() -> None:
    runtime = FakeSolveRuntime()
    workflow = SolveAgentWorkflow(runtime=runtime)
    command = SolveAgentCommand(question_text="解方程 2x-4=0。")

    response = _run(workflow.run(command, request_id="req_workflow"))

    assert response.status == "ok"
    assert response.solution is not None
    assert response.solution.confidence_status == "teacher_review_required"
    assert response.solution.math_verification.status == "inconclusive"
    assert response.tool_request_id == "req_tool_solve"
    assert "程序验证通过" not in response.model_dump_json()
    assert "必须且只能调用一次 solve_question" in runtime.requests[0].user_message


def test_run_rejects_missing_duplicate_or_forged_solve_evidence() -> None:
    command = SolveAgentCommand(question_text="解方程 2x-4=0。")
    missing = SolveAgentWorkflow(runtime=FakeSolveRuntime(_result(tool_calls=[])))
    duplicate = SolveAgentWorkflow(
        runtime=FakeSolveRuntime(_result(tool_calls=[_solve_call(), _solve_call()]))
    )
    unrelated = TeacherAgentToolCall(
        tool_name="search_questions",
        status="ok",
        output={"ok": True, "items": []},
    )
    extra_tool = SolveAgentWorkflow(
        runtime=FakeSolveRuntime(_result(tool_calls=[unrelated, _solve_call()]))
    )
    forged_output = _solution_output()
    forged_output["confidence_status"] = "program_verified"
    forged = SolveAgentWorkflow(
        runtime=FakeSolveRuntime(_result(tool_calls=[_solve_call(forged_output)]))
    )

    assert _run(missing.run(command)).error["code"] == "TOOL_EXECUTION_ERROR"
    assert _run(duplicate.run(command)).error["code"] == "TOOL_EXECUTION_ERROR"
    assert _run(extra_tool.run(command)).error["code"] == "TOOL_EXECUTION_ERROR"
    assert _run(forged.run(command)).error["code"] == "TOOL_EXECUTION_ERROR"


def test_run_rejects_failed_tool_even_if_payload_claims_success() -> None:
    call = _solve_call()
    call.status = "error"
    call.error = TeacherAgentError(
        code=TeacherAgentErrorCode.TOOL_TIMEOUT,
        message="解题工具超时",
        request_id="req_tool_timeout",
    )
    workflow = SolveAgentWorkflow(
        runtime=FakeSolveRuntime(_result(tool_calls=[call]))
    )

    response = _run(
        workflow.run(
            SolveAgentCommand(question_text="解方程 2x-4=0。"),
            request_id="req_workflow",
        )
    )

    assert response.status == "error"
    assert response.error["code"] == "TOOL_TIMEOUT"


def test_failed_tool_preserves_error_embedded_in_tool_output() -> None:
    output = _solution_output(ok=False)
    output["error"] = {
        "code": "MODEL_UNAVAILABLE",
        "message": "模型暂不可用",
        "request_id": "req_tool_model",
    }
    call = _solve_call(output)
    call.status = "error"
    workflow = SolveAgentWorkflow(
        runtime=FakeSolveRuntime(_result(tool_calls=[call]))
    )

    response = _run(
        workflow.run(
            SolveAgentCommand(question_text="解方程 2x-4=0。"),
            request_id="req_workflow",
        )
    )

    assert response.status == "error"
    assert response.error["code"] == "MODEL_UNAVAILABLE"
    assert response.error["request_id"] == "req_workflow"


def test_tool_verification_failure_is_preserved() -> None:
    output = _solution_output(ok=False)
    output["error"] = {
        "code": "VERIFICATION_FAILED",
        "message": "独立数学验证未通过",
        "request_id": "req_tool_failed",
    }
    workflow = SolveAgentWorkflow(
        runtime=FakeSolveRuntime(_result(tool_calls=[_solve_call(output)]))
    )

    response = _run(
        workflow.run(SolveAgentCommand(question_text="解方程 2x-4=0。"))
    )

    assert response.status == "error"
    assert response.error["code"] == "VERIFICATION_FAILED"
    assert response.solution is None


def test_stream_hides_raw_tool_payload_and_emits_structured_terminal() -> None:
    async def scenario():
        workflow = SolveAgentWorkflow(runtime=FakeSolveRuntime())
        return [
            event
            async for event in workflow.stream(
                SolveAgentCommand(question_text="解方程 2x-4=0。"),
                request_id="req_stream",
            )
        ]

    events = _run(scenario())

    assert [event.type for event in events] == [
        TeacherAgentEventType.RUN_STARTED,
        TeacherAgentEventType.TOOL_STARTED,
        TeacherAgentEventType.TOOL_FINISHED,
        TeacherAgentEventType.RUN_COMPLETED,
    ]
    assert "input" not in events[1].data
    assert "output" not in events[2].data
    terminal = events[-1].data["solve_response"]
    assert terminal["solution"]["math_verification"]["status"] == "inconclusive"


def test_resume_uses_the_same_command_and_existing_session() -> None:
    runtime = FakeSolveRuntime()
    workflow = SolveAgentWorkflow(runtime=runtime)
    command = SolveAgentCommand(
        question_text="解方程 2x-4=0。", teacher_instruction="使用配方法"
    )

    response = _run(
        workflow.resume(
            command,
            session_id="tch_existing",
            request_id="req_resume_solve",
        )
    )

    assert response.status == "ok"
    assert response.run_id == "run_solve_resumed"
    assert response.session_id == "tch_existing"
    assert runtime.resume_requests[0][0] == "tch_existing"
    assert runtime.resume_requests[0][1].session_id == "tch_existing"
    assert "使用配方法" in runtime.resume_requests[0][1].user_message


def test_active_stream_can_be_cancelled_through_runtime() -> None:
    class BlockingRuntime(FakeSolveRuntime):
        def __init__(self) -> None:
            super().__init__()
            self.release = asyncio.Event()

        async def stream(
            self, request: TeacherAgentRunRequest
        ) -> AsyncIterator[TeacherAgentEvent]:
            self.requests.append(request)
            yield TeacherAgentEvent(
                type=TeacherAgentEventType.RUN_STARTED,
                run_id=self.result.run_id,
                session_id=self.result.session_id,
                request_id=request.request_id,
            )
            await self.release.wait()
            yield TeacherAgentEvent(
                type=TeacherAgentEventType.RUN_CANCELLED,
                run_id=self.result.run_id,
                session_id=self.result.session_id,
                request_id=request.request_id,
                data={
                    "error": {
                        "code": "RUN_CANCELLED",
                        "message": "已取消",
                        "request_id": request.request_id,
                    }
                },
            )

        async def cancel(self, run_id: str) -> TeacherAgentRunResult:
            result = await super().cancel(run_id)
            self.release.set()
            return result

    async def scenario():
        runtime = BlockingRuntime()
        workflow = SolveAgentWorkflow(runtime=runtime)
        events = workflow.stream(
            SolveAgentCommand(question_text="解方程 2x-4=0。"),
            request_id="req_cancel_stream",
        )
        started = await anext(events)
        outcome = await workflow.cancel(started.run_id)
        remaining = [event async for event in events]
        return runtime, workflow, outcome, remaining

    runtime, workflow, outcome, remaining = _run(scenario())

    assert outcome["status"] == "cancelled"
    assert runtime.cancelled_runs == ["run_solve_1"]
    assert remaining[-1].type == TeacherAgentEventType.RUN_CANCELLED
    assert workflow._active_runs == {}
