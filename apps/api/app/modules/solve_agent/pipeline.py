"""Trusted Solve workflow over the product-owned TeacherAgentRuntime seam.

The model may choose a tool and narrate progress, but the final mathematical
result is accepted only from one successful ``solve_question`` Tool output.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from app.agent_runtime import (
    TeacherAgentError,
    TeacherAgentErrorCode,
    TeacherAgentEvent,
    TeacherAgentEventType,
    TeacherAgentRunRequest,
    TeacherAgentRunResult,
    TeacherAgentRunStatus,
    TeacherAgentRuntime,
    TeacherAgentToolCall,
    get_teacher_agent_runtime,
)
from app.modules.solution_assistant import SolutionResult
from app.modules.question_capture import (
    QuestionSolveGrantRegistry,
    get_question_solve_grants,
)

from .domain import SolveAgentCommand, SolveAgentResponse

logger = logging.getLogger("math_ai.solve_agent")


class SolveAgentWorkflow:
    """Deep module that owns Solve orchestration, grounding, and run lifecycle."""

    def __init__(
        self,
        *,
        runtime: TeacherAgentRuntime | None = None,
        grants: QuestionSolveGrantRegistry | None = None,
    ) -> None:
        self._runtime = runtime
        self._grants = grants
        self._active_runs: dict[str, TeacherAgentRuntime] = {}

    @property
    def runtime(self) -> TeacherAgentRuntime:
        return self._runtime or get_teacher_agent_runtime()

    @property
    def grants(self) -> QuestionSolveGrantRegistry:
        return self._grants or get_question_solve_grants()

    async def run(
        self,
        command: SolveAgentCommand,
        *,
        owner_id: str = "owner_teacher",
        request_id: str = "",
    ) -> SolveAgentResponse:
        started = time.monotonic()
        request_id = request_id or f"req_{uuid.uuid4().hex}"
        runtime = self.runtime
        if runtime.runtime_name == "legacy":
            return self._error_response(
                command,
                request_id=request_id,
                code=TeacherAgentErrorCode.UNSUPPORTED_CAPABILITY,
                message="当前 Agent Runtime（legacy）不支持 Solve 编排；请启用 dsh Runtime。",
            )
        try:
            result = await runtime.run(
                self._runtime_request(command, request_id, owner_id=owner_id)
            )
        except Exception:  # pragma: no cover - defensive runtime seam
            logger.exception("solve_agent_runtime_raised", extra={"request_id": request_id})
            return self._error_response(
                command,
                request_id=request_id,
                code=TeacherAgentErrorCode.INTERNAL_ERROR,
                message="Agent Runtime 执行异常",
            )
        response = self._response_from_run(command, result, request_id=request_id)
        response.duration_ms = int((time.monotonic() - started) * 1000)
        return response

    async def resume(
        self,
        command: SolveAgentCommand,
        *,
        session_id: str,
        owner_id: str = "owner_teacher",
        request_id: str = "",
    ) -> SolveAgentResponse:
        started = time.monotonic()
        request_id = request_id or f"req_{uuid.uuid4().hex}"
        runtime = self.runtime
        if runtime.runtime_name == "legacy":
            return self._error_response(
                command,
                request_id=request_id,
                session_id=session_id,
                code=TeacherAgentErrorCode.UNSUPPORTED_CAPABILITY,
                message="当前 Agent Runtime（legacy）不支持恢复 Solve 会话。",
            )
        try:
            result = await runtime.resume(
                session_id,
                self._runtime_request(
                    command,
                    request_id,
                    owner_id=owner_id,
                    session_id=session_id,
                ),
            )
        except Exception:  # pragma: no cover - defensive runtime seam
            logger.exception("solve_agent_resume_raised", extra={"request_id": request_id})
            return self._error_response(
                command,
                request_id=request_id,
                session_id=session_id,
                code=TeacherAgentErrorCode.INTERNAL_ERROR,
                message="Agent Runtime 恢复异常",
            )
        response = self._response_from_run(command, result, request_id=request_id)
        response.duration_ms = int((time.monotonic() - started) * 1000)
        return response

    async def stream(
        self,
        command: SolveAgentCommand,
        *,
        owner_id: str = "owner_teacher",
        request_id: str = "",
    ) -> AsyncIterator[TeacherAgentEvent]:
        """Stream safe progress and one structured ``solve_response`` terminal."""
        started = time.monotonic()
        request_id = request_id or f"req_{uuid.uuid4().hex}"
        runtime = self.runtime
        if runtime.runtime_name == "legacy":
            yield self._failed_event(
                request_id=request_id,
                session_id=command.session_id or "",
                code=TeacherAgentErrorCode.UNSUPPORTED_CAPABILITY,
                message="当前 Agent Runtime（legacy）不支持 Solve 编排。",
            )
            return

        run_id = ""
        session_id = command.session_id or ""
        tool_calls: list[TeacherAgentToolCall] = []
        terminal = False
        try:
            async for event in runtime.stream(
                self._runtime_request(command, request_id, owner_id=owner_id)
            ):
                if event.run_id:
                    run_id = event.run_id
                    session_id = event.session_id
                    self._active_runs[run_id] = runtime

                if event.type == TeacherAgentEventType.ASSISTANT_DELTA:
                    # Unstructured model text is not a mathematical result.
                    continue
                if event.type == TeacherAgentEventType.TOOL_STARTED:
                    yield self._safe_tool_event(event)
                    continue
                if event.type == TeacherAgentEventType.TOOL_FINISHED:
                    tool_calls.append(self._tool_call_from_event(event, request_id))
                    yield self._safe_tool_event(event)
                    continue
                if event.type == TeacherAgentEventType.RUN_COMPLETED:
                    run_result = TeacherAgentRunResult(
                        run_id=run_id or event.run_id,
                        session_id=session_id or event.session_id,
                        request_id=request_id,
                        runtime=runtime.runtime_name,
                        status=TeacherAgentRunStatus.COMPLETED,
                        tool_calls=tool_calls,
                    )
                    response = self._response_from_run(
                        command, run_result, request_id=request_id
                    )
                    response.duration_ms = int((time.monotonic() - started) * 1000)
                    terminal = True
                    terminal_type = (
                        TeacherAgentEventType.RUN_COMPLETED
                        if response.status == "ok"
                        else TeacherAgentEventType.RUN_FAILED
                    )
                    data: dict[str, Any] = (
                        {"solve_response": response.model_dump(mode="json")}
                        if response.status == "ok"
                        else {"error": response.error}
                    )
                    yield TeacherAgentEvent(
                        type=terminal_type,
                        run_id=run_result.run_id,
                        session_id=run_result.session_id,
                        request_id=request_id,
                        data=data,
                        sequence=event.sequence,
                        created_at=event.created_at,
                    )
                    return
                if event.type in {
                    TeacherAgentEventType.RUN_FAILED,
                    TeacherAgentEventType.RUN_CANCELLED,
                }:
                    terminal = True
                    yield event
                    return
                yield event

            terminal = True
            yield self._failed_event(
                request_id=request_id,
                session_id=session_id,
                run_id=run_id,
                code=TeacherAgentErrorCode.INTERNAL_ERROR,
                message="Agent 流在终态前结束",
            )
        finally:
            if run_id and not terminal:
                try:
                    await runtime.cancel(run_id)
                except Exception:  # pragma: no cover - disconnect cleanup
                    logger.exception(
                        "solve_agent_stream_cancel_failed",
                        extra={"request_id": request_id, "run_id": run_id},
                    )
            if run_id:
                self._active_runs.pop(run_id, None)

    async def cancel(self, run_id: str) -> dict[str, Any]:
        runtime = self._active_runs.get(run_id)
        if runtime is None:
            return {
                "run_id": run_id,
                "status": "failed",
                "error": {
                    "code": "RUN_NOT_FOUND",
                    "message": "未知或已结束的 run_id",
                    "request_id": "",
                },
            }
        result = await runtime.cancel(run_id)
        return {
            "run_id": run_id,
            "status": result.status.value,
            "error": result.error.model_dump(mode="json") if result.error else None,
        }

    def _response_from_run(
        self,
        command: SolveAgentCommand,
        result: TeacherAgentRunResult,
        *,
        request_id: str,
    ) -> SolveAgentResponse:
        if result.status == TeacherAgentRunStatus.CANCELLED:
            response = self._error_response(
                command,
                request_id=request_id,
                run_id=result.run_id,
                session_id=result.session_id,
                code=TeacherAgentErrorCode.RUN_CANCELLED,
                message="解题已取消",
            )
            response.status = "cancelled"
            return response
        if result.status == TeacherAgentRunStatus.FAILED:
            error = result.error or TeacherAgentError(
                code=TeacherAgentErrorCode.INTERNAL_ERROR,
                message="Agent run 失败",
                request_id=request_id,
            )
            return self._error_response(
                command,
                request_id=request_id,
                run_id=result.run_id,
                session_id=result.session_id,
                code=error.code,
                message=error.message,
            )

        solve_calls = [
            call for call in result.tool_calls if call.tool_name == "solve_question"
        ]
        if len(result.tool_calls) != 1 or len(solve_calls) != 1:
            return self._error_response(
                command,
                request_id=request_id,
                run_id=result.run_id,
                session_id=result.session_id,
                code=TeacherAgentErrorCode.TOOL_EXECUTION_ERROR,
                message="Solve workflow 必须且只能获得一次 solve_question 结果",
                tool_call_count=len(result.tool_calls),
            )
        call = solve_calls[0]
        output = call.output or {}
        if not self._tool_input_matches(command, call.input):
            return self._error_response(
                command,
                request_id=request_id,
                run_id=result.run_id,
                session_id=result.session_id,
                code=TeacherAgentErrorCode.TOOL_EXECUTION_ERROR,
                message="solve_question 调用参数未通过教师确认意图校验",
                tool_call_count=1,
            )
        if call.status != "ok" or call.error is not None:
            error = call.error or self._parse_tool_error(
                output.get("error"), request_id
            )
            return self._error_response(
                command,
                request_id=request_id,
                run_id=result.run_id,
                session_id=result.session_id,
                code=error.code,
                message=error.message,
                tool_call_count=1,
            )
        if output.get("ok") is not True:
            raw_error = output.get("error")
            error = self._parse_tool_error(raw_error, request_id)
            return self._error_response(
                command,
                request_id=request_id,
                run_id=result.run_id,
                session_id=result.session_id,
                code=error.code,
                message=error.message,
                tool_call_count=len(result.tool_calls),
            )
        try:
            payload = {
                key: value
                for key, value in output.items()
                if key not in {"ok", "error", "request_id"}
            }
            solution = SolutionResult.model_validate(payload)
            if solution.question_text != command.question_text:
                raise ValueError("question_text mismatch")
            if solution.solution_mode != command.solution_mode:
                raise ValueError("solution_mode mismatch")
            if command.question_capture is None:
                if solution.visual_context is not None:
                    raise ValueError("unexpected visual context")
            else:
                visual = solution.visual_context
                reference = command.question_capture
                if visual is None:
                    raise ValueError("missing visual context")
                if (
                    visual.asset_id != reference.asset_id
                    or visual.media_revision != reference.media_revision
                    or visual.recognition_revision != reference.recognition_revision
                    or visual.visual_processing_consent
                    != reference.visual_processing_consent
                ):
                    raise ValueError("visual context mismatch")
        except ValueError:
            return self._error_response(
                command,
                request_id=request_id,
                run_id=result.run_id,
                session_id=result.session_id,
                code=TeacherAgentErrorCode.TOOL_EXECUTION_ERROR,
                message="solve_question 返回的结构或可信字段不一致",
                tool_call_count=len(result.tool_calls),
            )
        return SolveAgentResponse(
            request_id=request_id,
            session_id=result.session_id,
            run_id=result.run_id,
            status="ok",
            question_text=command.question_text,
            solution_mode=command.solution_mode,
            solution=solution,
            tool_request_id=str(output.get("request_id") or ""),
            tool_call_count=len(result.tool_calls),
        )

    @staticmethod
    def _tool_input_matches(
        command: SolveAgentCommand,
        tool_input: dict[str, Any],
    ) -> bool:
        reference = command.question_capture
        if reference is not None:
            # The opaque grant is the only model-relayed capability. The FastAPI
            # Tool resolves the canonical question, mode, instruction, owner and
            # exact media revisions from that one-use server binding; model text
            # and resource identifiers are never treated as authority here.
            return bool(str(tool_input.get("capture_grant", "")).strip()) and not any(
                tool_input.get(key) is not None
                for key in (
                    "capture_asset_id",
                    "capture_media_revision",
                    "capture_recognition_revision",
                    "visual_processing_consent",
                )
            )
        if str(tool_input.get("question_text", "")).strip() != command.question_text:
            return False
        if str(tool_input.get("solution_mode", "standard")) != command.solution_mode:
            return False
        if (
            "teacher_instruction" in tool_input
            and str(tool_input.get("teacher_instruction", "")).strip()
            != command.teacher_instruction.strip()
        ):
            return False
        return not any(
            tool_input.get(key) is not None
            for key in (
                "capture_asset_id",
                "capture_media_revision",
                "capture_recognition_revision",
                "capture_grant",
            )
        ) and tool_input.get("visual_processing_consent", False) is not True

    @staticmethod
    def _parse_tool_error(raw: Any, request_id: str) -> TeacherAgentError:
        if isinstance(raw, dict):
            try:
                return TeacherAgentError.model_validate(raw)
            except ValueError:
                pass
        return TeacherAgentError(
            code=TeacherAgentErrorCode.TOOL_EXECUTION_ERROR,
            message="solve_question 返回了无法解析的错误",
            request_id=request_id,
        )

    def _runtime_request(
        self,
        command: SolveAgentCommand,
        request_id: str,
        *,
        owner_id: str,
        session_id: str | None = None,
    ) -> TeacherAgentRunRequest:
        instruction = command.teacher_instruction.strip() or "无补充要求"
        capture_instruction = ""
        if command.question_capture is not None:
            reference = command.question_capture
            grant = self.grants.issue(
                owner_id=owner_id,
                question_text=command.question_text,
                solution_mode=command.solution_mode,
                teacher_instruction=command.teacher_instruction,
                reference=reference,
            )
            capture_instruction = (
                "\n这次解题已在 FastAPI 内绑定教师确认的题面、图片 revision、"
                "所有者与逐次同意。不要自行填写、转述或改写这些可信字段；"
                "只需把下面的一次性许可原样传给 solve_question："
                f"\ncapture_grant：{grant}"
            )
        return TeacherAgentRunRequest(
            user_message=(
                "请完成下面这道高中数学题的可信解题。必须且只能调用一次 solve_question，"
                "最终事实以 Tool 的结构化输出为准，不得自行升级验证状态。\n"
                f"solution_mode：{command.solution_mode}\n"
                f"教师补充要求：{instruction}\n"
                f"{capture_instruction}\n"
                f"题目：{command.question_text}"
            ),
            session_id=session_id or command.session_id,
            request_id=request_id,
        )

    @staticmethod
    def _tool_call_from_event(
        event: TeacherAgentEvent, request_id: str
    ) -> TeacherAgentToolCall:
        raw_error = event.data.get("error")
        error = None
        if isinstance(raw_error, dict):
            try:
                error = TeacherAgentError.model_validate(raw_error)
            except ValueError:
                error = TeacherAgentError(
                    code=TeacherAgentErrorCode.TOOL_EXECUTION_ERROR,
                    message="工具返回了无法解析的错误",
                    request_id=request_id,
                )
        raw_input = event.data.get("input")
        raw_output = event.data.get("output")
        return TeacherAgentToolCall(
            tool_name=str(event.data.get("tool_name", "")),
            status=str(event.data.get("status", "error")),
            input=raw_input if isinstance(raw_input, dict) else {},
            output=raw_output if isinstance(raw_output, dict) else None,
            error=error,
            started_at=event.created_at,
            finished_at=event.created_at,
        )

    @staticmethod
    def _safe_tool_event(event: TeacherAgentEvent) -> TeacherAgentEvent:
        return TeacherAgentEvent(
            type=event.type,
            run_id=event.run_id,
            session_id=event.session_id,
            request_id=event.request_id,
            data={
                "tool_name": str(event.data.get("tool_name", "")),
                "status": str(event.data.get("status", "running")),
            },
            sequence=event.sequence,
            created_at=event.created_at,
        )

    @staticmethod
    def _failed_event(
        *,
        request_id: str,
        session_id: str,
        code: TeacherAgentErrorCode,
        message: str,
        run_id: str = "",
    ) -> TeacherAgentEvent:
        return TeacherAgentEvent(
            type=TeacherAgentEventType.RUN_FAILED,
            run_id=run_id,
            session_id=session_id,
            request_id=request_id,
            data={
                "error": {
                    "code": code.value,
                    "message": message,
                    "request_id": request_id,
                }
            },
        )

    @staticmethod
    def _error_response(
        command: SolveAgentCommand,
        *,
        request_id: str,
        code: TeacherAgentErrorCode,
        message: str,
        run_id: str = "",
        session_id: str = "",
        tool_call_count: int = 0,
    ) -> SolveAgentResponse:
        return SolveAgentResponse(
            request_id=request_id,
            session_id=session_id,
            run_id=run_id,
            status="error",
            question_text=command.question_text,
            solution_mode=command.solution_mode,
            tool_call_count=tool_call_count,
            error={
                "code": code.value,
                "message": message,
                "request_id": request_id,
            },
        )
