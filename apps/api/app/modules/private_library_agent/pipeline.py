"""Trusted private retrieval over the product-owned TeacherAgentRuntime seam."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app.agent_runtime import (
    TeacherAgentErrorCode,
    TeacherAgentRunRequest,
    TeacherAgentRunStatus,
    TeacherAgentRuntime,
    get_teacher_agent_runtime,
)
from app.modules.private_library import (
    PrivateLibrarySearchResult,
    PrivateRetrievalGrantRegistry,
    get_private_retrieval_grants,
)

from .domain import PrivateLibraryAgentCommand, PrivateLibraryAgentResponse

logger = logging.getLogger("math_ai.private_library_agent")


class PrivateLibraryAgentWorkflow:
    """Issues one-use consent and accepts only one grounded retrieval Tool call."""

    def __init__(
        self,
        *,
        runtime: TeacherAgentRuntime | None = None,
        grants: PrivateRetrievalGrantRegistry | None = None,
    ) -> None:
        self._runtime = runtime
        self._grants = grants

    @property
    def runtime(self) -> TeacherAgentRuntime:
        return self._runtime or get_teacher_agent_runtime()

    @property
    def grants(self) -> PrivateRetrievalGrantRegistry:
        return self._grants or get_private_retrieval_grants()

    async def run(
        self,
        command: PrivateLibraryAgentCommand,
        *,
        owner_id: str,
        request_id: str = "",
    ) -> PrivateLibraryAgentResponse:
        request_id = request_id or f"req_{uuid.uuid4().hex}"
        query = command.query.strip()
        if self.runtime.runtime_name == "legacy":
            return self._error(command, request_id, TeacherAgentErrorCode.UNSUPPORTED_CAPABILITY, "当前 Runtime 不支持私人检索")
        receipt = self.grants.issue(owner_id=owner_id, query=query, limit=command.limit)
        try:
            run = await self.runtime.run(
                TeacherAgentRunRequest(
                    user_message=(
                        "执行本次教师已明确同意的私人资料检索。必须且只能调用一次 "
                        "search_private_library；不得改写查询或返回 Tool 以外的私人内容。\n"
                        f"检索查询：{query}\n返回上限：{command.limit}\n检索许可：{receipt}"
                    ),
                    session_id=command.session_id,
                    request_id=request_id,
                )
            )
        except Exception:
            logger.exception("private_library_agent_runtime_raised", extra={"request_id": request_id})
            return self._error(command, request_id, TeacherAgentErrorCode.INTERNAL_ERROR, "Agent Runtime 执行异常")
        if run.status != TeacherAgentRunStatus.COMPLETED:
            error = run.error
            response = self._error(
                command,
                request_id,
                error.code if error else (
                    TeacherAgentErrorCode.RUN_CANCELLED
                    if run.status == TeacherAgentRunStatus.CANCELLED
                    else TeacherAgentErrorCode.INTERNAL_ERROR
                ),
                error.message if error else (
                    "私人检索已取消"
                    if run.status == TeacherAgentRunStatus.CANCELLED
                    else "私人检索执行失败"
                ),
                run_id=run.run_id,
                session_id=run.session_id,
            )
            if run.status == TeacherAgentRunStatus.CANCELLED:
                response.status = "cancelled"
            return response
        calls = [call for call in run.tool_calls if call.tool_name == "search_private_library"]
        if len(run.tool_calls) != 1 or len(calls) != 1:
            return self._error(command, request_id, TeacherAgentErrorCode.TOOL_EXECUTION_ERROR, "私人检索必须且只能调用一次受控 Tool", run_id=run.run_id, session_id=run.session_id, tool_call_count=len(run.tool_calls))
        call = calls[0]
        output = call.output or {}
        if call.status != "ok" or output.get("ok") is not True:
            raw_error = output.get("error") if isinstance(output, dict) else None
            code = TeacherAgentErrorCode.TOOL_EXECUTION_ERROR
            message = "私人检索 Tool 执行失败"
            if isinstance(raw_error, dict):
                try:
                    code = TeacherAgentErrorCode(str(raw_error.get("code")))
                except ValueError:
                    pass
                message = str(raw_error.get("message") or message)[:500]
            return self._error(command, request_id, code, message, run_id=run.run_id, session_id=run.session_id, tool_call_count=1)
        try:
            result = PrivateLibrarySearchResult.model_validate(
                {key: value for key, value in output.items() if key not in {"ok", "error", "request_id"}}
            )
            if result.query != query or result.visibility != "private" or result.content_scope != "matching_excerpts":
                raise ValueError("retrieval scope mismatch")
        except ValueError:
            return self._error(command, request_id, TeacherAgentErrorCode.TOOL_EXECUTION_ERROR, "私人检索 Tool 返回了不可信的结构", run_id=run.run_id, session_id=run.session_id, tool_call_count=1)
        return PrivateLibraryAgentResponse(
            request_id=request_id,
            session_id=run.session_id,
            run_id=run.run_id,
            status="ok",
            query=query,
            result=result,
            tool_request_id=str(output.get("request_id") or ""),
            tool_call_count=1,
        )

    @staticmethod
    def _error(
        command: PrivateLibraryAgentCommand,
        request_id: str,
        code: TeacherAgentErrorCode,
        message: str,
        *,
        run_id: str = "",
        session_id: str = "",
        tool_call_count: int = 0,
    ) -> PrivateLibraryAgentResponse:
        return PrivateLibraryAgentResponse(
            request_id=request_id,
            run_id=run_id,
            session_id=session_id,
            status="error",
            query=command.query.strip(),
            tool_call_count=tool_call_count,
            error={"code": code.value, "message": message, "request_id": request_id},
        )
