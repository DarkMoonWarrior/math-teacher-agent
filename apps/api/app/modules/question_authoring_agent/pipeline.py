from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from app.agent_runtime import (
    TeacherAgentError,
    TeacherAgentErrorCode,
    TeacherAgentRunRequest,
    TeacherAgentRunResult,
    TeacherAgentRunStatus,
    TeacherAgentRuntime,
    get_teacher_agent_runtime,
)
from app.modules.question_authoring import GeneratedQuestionDraft
from app.modules.question_authoring_agent.domain import (
    QuestionAuthoringAgentCommand,
    QuestionAuthoringAgentResponse,
)


logger = logging.getLogger("math_ai.question_authoring_agent")


class QuestionAuthoringAgentWorkflow:
    """Accepts only one exact create_question_draft Tool result."""

    def __init__(self, *, runtime: TeacherAgentRuntime | None = None) -> None:
        self._runtime = runtime

    @property
    def runtime(self) -> TeacherAgentRuntime:
        return self._runtime or get_teacher_agent_runtime()

    async def run(
        self,
        command: QuestionAuthoringAgentCommand,
        *,
        owner_id: str,
        request_id: str = "",
    ) -> QuestionAuthoringAgentResponse:
        request_id = request_id or f"req_{uuid.uuid4().hex}"
        runtime = self.runtime
        if runtime.runtime_name == "legacy":
            return self._error_response(
                request_id=request_id,
                code=TeacherAgentErrorCode.UNSUPPORTED_CAPABILITY,
                message="当前 Agent Runtime（legacy）不支持辅助命题；请启用 dsh Runtime。",
            )
        try:
            result = await runtime.run(
                self._runtime_request(
                    command,
                    request_id=request_id,
                    session_id=command.session_id,
                    owner_id=owner_id,
                )
            )
        except Exception:  # pragma: no cover - defensive runtime seam
            logger.exception(
                "question_authoring_runtime_raised",
                extra={"request_id": request_id},
            )
            return self._error_response(
                request_id=request_id,
                code=TeacherAgentErrorCode.INTERNAL_ERROR,
                message="辅助命题 Agent Runtime 执行异常",
            )
        return self._response_from_run(command, result, request_id=request_id)

    def _response_from_run(
        self,
        command: QuestionAuthoringAgentCommand,
        result: TeacherAgentRunResult,
        *,
        request_id: str,
    ) -> QuestionAuthoringAgentResponse:
        if result.status == TeacherAgentRunStatus.CANCELLED:
            response = self._error_response(
                request_id=request_id,
                run_id=result.run_id,
                session_id=result.session_id,
                code=TeacherAgentErrorCode.RUN_CANCELLED,
                message="辅助命题已取消",
            )
            response.status = "cancelled"
            return response
        if result.status == TeacherAgentRunStatus.FAILED:
            error = result.error or TeacherAgentError(
                code=TeacherAgentErrorCode.INTERNAL_ERROR,
                message="辅助命题 Agent run 失败",
                request_id=request_id,
            )
            return self._error_response(
                request_id=request_id,
                run_id=result.run_id,
                session_id=result.session_id,
                code=error.code,
                message=error.message,
            )

        authoring_calls = [
            call
            for call in result.tool_calls
            if call.tool_name == "create_question_draft"
        ]
        if len(result.tool_calls) != 1 or len(authoring_calls) != 1:
            return self._error_response(
                request_id=request_id,
                run_id=result.run_id,
                session_id=result.session_id,
                code=TeacherAgentErrorCode.TOOL_EXECUTION_ERROR,
                message="辅助命题 workflow 必须且只能获得一次 create_question_draft 结果",
                tool_call_count=len(result.tool_calls),
            )
        call = authoring_calls[0]
        brief = command.brief
        expected_input = brief.model_dump(mode="json", exclude_none=True)
        if command.progress_id:
            expected_input["progress_id"] = command.progress_id
        if call.input != expected_input:
            return self._error_response(
                request_id=request_id,
                run_id=result.run_id,
                session_id=result.session_id,
                code=TeacherAgentErrorCode.TOOL_EXECUTION_ERROR,
                message="create_question_draft 调用参数未通过教师确认意图校验",
                tool_call_count=1,
            )
        output = call.output or {}
        if call.status != "ok" or call.error is not None or output.get("ok") is not True:
            error = call.error or self._parse_tool_error(output.get("error"), request_id)
            return self._error_response(
                request_id=request_id,
                run_id=result.run_id,
                session_id=result.session_id,
                code=error.code,
                message=error.message,
                tool_call_count=1,
            )
        try:
            draft = GeneratedQuestionDraft.model_validate(output.get("draft"))
            if draft.request_text != brief.request_text.strip():
                raise ValueError("request_text mismatch")
        except (TypeError, ValueError):
            return self._error_response(
                request_id=request_id,
                run_id=result.run_id,
                session_id=result.session_id,
                code=TeacherAgentErrorCode.TOOL_EXECUTION_ERROR,
                message="create_question_draft 返回的结构或私有状态不一致",
                tool_call_count=1,
            )
        return QuestionAuthoringAgentResponse(
            request_id=request_id,
            session_id=result.session_id,
            run_id=result.run_id,
            status="ok",
            draft=draft,
            tool_request_id=str(output.get("request_id") or ""),
            tool_call_count=1,
        )

    @staticmethod
    def _runtime_request(
        command: QuestionAuthoringAgentCommand,
        *,
        request_id: str,
        session_id: str | None,
        owner_id: str,
    ) -> TeacherAgentRunRequest:
        tool_input = command.brief.model_dump(mode="json", exclude_none=True)
        if command.progress_id:
            tool_input["progress_id"] = command.progress_id
        brief_json = json.dumps(
            tool_input,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return TeacherAgentRunRequest(
            user_message=(
                "这是受控的私有辅助命题任务。必须且只能调用一次 create_question_draft；"
                "把下列 JSON 字段和值原样传给工具，不得增加 owner_id、保存、发布、共享或删除参数。\n"
                f"命题请求JSON：{brief_json}"
            ),
            session_id=session_id,
            request_id=request_id,
            teacher_user_id=owner_id,
        )

    @staticmethod
    def _parse_tool_error(raw: Any, request_id: str) -> TeacherAgentError:
        if isinstance(raw, dict):
            try:
                return TeacherAgentError.model_validate(raw)
            except ValueError:
                pass
        return TeacherAgentError(
            code=TeacherAgentErrorCode.TOOL_EXECUTION_ERROR,
            message="create_question_draft 返回了无法解析的错误",
            request_id=request_id,
        )

    @staticmethod
    def _error_response(
        *,
        request_id: str,
        code: TeacherAgentErrorCode,
        message: str,
        run_id: str = "",
        session_id: str = "",
        tool_call_count: int = 0,
    ) -> QuestionAuthoringAgentResponse:
        return QuestionAuthoringAgentResponse(
            request_id=request_id,
            session_id=session_id,
            run_id=run_id,
            status="error",
            tool_call_count=tool_call_count,
            error={
                "code": code.value,
                "message": message,
                "request_id": request_id,
            },
        )
