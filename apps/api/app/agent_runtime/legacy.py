"""LegacyTeacherAgentRuntime：默认运行时。

设计目标：在开发者不改任何配置时，现有产品行为完全不变。
本运行时是独立的新模块，现有路由不依赖它；它仅通过既有
model provider 配置（MATH_AI_DEEPSEEK_*）做单轮纯文本补全，
没有任何 Tool，也不访问数据库。
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import httpx

from app.agent_runtime.base import TeacherAgentRuntime
from app.agent_runtime.models import (
    TeacherAgentCapabilities,
    TeacherAgentError,
    TeacherAgentErrorCode,
    TeacherAgentEvent,
    TeacherAgentEventType,
    TeacherAgentHealth,
    TeacherAgentRunRequest,
    TeacherAgentRunResult,
    TeacherAgentRunStatus,
    TeacherAgentSession,
    TeacherAgentSessionStatus,
)
from app.core.config import get_settings

CompletionFn = Callable[[TeacherAgentRunRequest, Any | None], Awaitable[str]]


async def _default_completion(request: TeacherAgentRunRequest, _signal: Any | None) -> str:
    """默认补全实现：走既有 DeepSeek OpenAI-compatible 配置。

    不触碰题库、不提供工具；只消费环境中的 MATH_AI_DEEPSEEK_* 配置。
    """
    settings = get_settings()
    if not settings.deepseek_api_key:
        raise _LegacyModelUnavailable("DeepSeek API Key 未配置")
    payload = {
        "model": settings.deepseek_model,
        "messages": [{"role": "user", "content": request.user_message}],
        "stream": False,
    }
    timeout = httpx.Timeout(settings.deepseek_timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{settings.deepseek_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
            json=payload,
        )
    if response.status_code != 200:
        raise _LegacyModelUnavailable(f"模型服务返回 HTTP {response.status_code}")
    try:
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise _LegacyModelUnavailable("模型返回结构异常") from exc


class _LegacyModelUnavailable(RuntimeError):
    pass


class LegacyTeacherAgentRuntime(TeacherAgentRuntime):
    runtime_name = "legacy"
    runtime_version = "0.1.0"

    def __init__(self, completion_fn: CompletionFn | None = None) -> None:
        self._completion_fn = completion_fn or _default_completion
        self._sessions: dict[str, TeacherAgentSession] = {}
        self._tasks: dict[str, asyncio.Task[TeacherAgentRunResult]] = {}

    # -- 内部工具 ---------------------------------------------------------

    def _event(
        self,
        event_type: TeacherAgentEventType,
        run_id: str,
        session_id: str,
        request_id: str,
        *,
        sequence: int,
        data: dict[str, Any] | None = None,
    ) -> TeacherAgentEvent:
        return TeacherAgentEvent(
            type=event_type,
            run_id=run_id,
            session_id=session_id,
            request_id=request_id,
            data=data or {},
            sequence=sequence,
        )

    # -- TeacherAgentRuntime ---------------------------------------------

    async def run(self, request: TeacherAgentRunRequest) -> TeacherAgentRunResult:
        run_id = f"run_{uuid.uuid4().hex}"
        session_id = request.session_id or f"session_{uuid.uuid4().hex}"
        request_id = request.request_id or f"req_{uuid.uuid4().hex}"
        session = self._sessions.setdefault(
            session_id,
            TeacherAgentSession(
                session_id=session_id,
                runtime=self.runtime_name,
                status=TeacherAgentSessionStatus.RUNNING,
                teacher_user_id=request.teacher_user_id,
                tenant_id=request.tenant_id,
            ),
        )
        session.status = TeacherAgentSessionStatus.RUNNING
        session.run_ids.append(run_id)
        session.updated_at = time.time()

        settings = get_settings()
        if not settings.deepseek_api_key:
            error = TeacherAgentError(
                code=TeacherAgentErrorCode.MODEL_UNAVAILABLE,
                message="DeepSeek API Key 未配置",
                request_id=request_id,
            )
            result = TeacherAgentRunResult(
                run_id=run_id,
                session_id=session_id,
                request_id=request_id,
                runtime=self.runtime_name,
                status=TeacherAgentRunStatus.FAILED,
                error=error,
            )
            session.status = TeacherAgentSessionStatus.FAILED
            return result

        task = asyncio.create_task(
            self._execute_run(run_id, session_id, request_id, request)
        )
        self._tasks[run_id] = task
        try:
            result = await task
        finally:
            self._tasks.pop(run_id, None)
            session.updated_at = time.time()
            if session.status == TeacherAgentSessionStatus.RUNNING:
                session.status = TeacherAgentSessionStatus.IDLE
        return result

    async def _execute_run(
        self, run_id: str, session_id: str, request_id: str, request: TeacherAgentRunRequest
    ) -> TeacherAgentRunResult:
        try:
            text = await self._completion_fn(request, None)
            return TeacherAgentRunResult(
                run_id=run_id,
                session_id=session_id,
                request_id=request_id,
                runtime=self.runtime_name,
                status=TeacherAgentRunStatus.COMPLETED,
                final_text=str(text or "").strip(),
            )
        except asyncio.CancelledError:
            session = self._sessions.get(session_id)
            if session is not None:
                session.status = TeacherAgentSessionStatus.CANCELLED
            return TeacherAgentRunResult(
                run_id=run_id,
                session_id=session_id,
                request_id=request_id,
                runtime=self.runtime_name,
                status=TeacherAgentRunStatus.CANCELLED,
                error=TeacherAgentError(
                    code=TeacherAgentErrorCode.RUN_CANCELLED,
                    message="run 已被取消",
                    request_id=request_id,
                ),
            )
        except _LegacyModelUnavailable as exc:
            session = self._sessions.get(session_id)
            if session is not None:
                session.status = TeacherAgentSessionStatus.FAILED
            return TeacherAgentRunResult(
                run_id=run_id,
                session_id=session_id,
                request_id=request_id,
                runtime=self.runtime_name,
                status=TeacherAgentRunStatus.FAILED,
                error=TeacherAgentError(
                    code=TeacherAgentErrorCode.MODEL_UNAVAILABLE,
                    message=str(exc),
                    request_id=request_id,
                ),
            )
        except Exception as exc:  # pragma: no cover - 防御边界
            session = self._sessions.get(session_id)
            if session is not None:
                session.status = TeacherAgentSessionStatus.FAILED
            return TeacherAgentRunResult(
                run_id=run_id,
                session_id=session_id,
                request_id=request_id,
                runtime=self.runtime_name,
                status=TeacherAgentRunStatus.FAILED,
                error=TeacherAgentError(
                    code=TeacherAgentErrorCode.INTERNAL_ERROR,
                    message="legacy runtime 内部错误",
                    request_id=request_id,
                ),
            )

    async def stream(
        self, request: TeacherAgentRunRequest
    ) -> AsyncIterator[TeacherAgentEvent]:
        run_id = f"run_{uuid.uuid4().hex}"
        session_id = request.session_id or f"session_{uuid.uuid4().hex}"
        request_id = request.request_id or f"req_{uuid.uuid4().hex}"
        sequence = 0
        yield self._event(
            TeacherAgentEventType.RUN_STARTED, run_id, session_id, request_id, sequence=sequence
        )
        sequence += 1
        settings = get_settings()
        if not settings.deepseek_api_key:
            yield self._event(
                TeacherAgentEventType.RUN_FAILED,
                run_id,
                session_id,
                request_id,
                sequence=sequence,
                data={
                    "error": TeacherAgentError(
                        code=TeacherAgentErrorCode.MODEL_UNAVAILABLE,
                        message="DeepSeek API Key 未配置",
                        request_id=request_id,
                    ).model_dump(mode="json"),
                },
            )
            return
        try:
            text = await self._completion_fn(request, None)
        except asyncio.CancelledError:
            yield self._event(
                TeacherAgentEventType.RUN_CANCELLED,
                run_id,
                session_id,
                request_id,
                sequence=sequence,
                data={
                    "error": TeacherAgentError(
                        code=TeacherAgentErrorCode.RUN_CANCELLED,
                        message="run 已被取消",
                        request_id=request_id,
                    ).model_dump(mode="json"),
                },
            )
            return
        except _LegacyModelUnavailable as exc:
            yield self._event(
                TeacherAgentEventType.RUN_FAILED,
                run_id,
                session_id,
                request_id,
                sequence=sequence,
                data={
                    "error": TeacherAgentError(
                        code=TeacherAgentErrorCode.MODEL_UNAVAILABLE,
                        message=str(exc),
                        request_id=request_id,
                    ).model_dump(mode="json"),
                },
            )
            return
        yield self._event(
            TeacherAgentEventType.ASSISTANT_DELTA,
            run_id,
            session_id,
            request_id,
            sequence=sequence,
            data={"text": text},
        )
        sequence += 1
        yield self._event(
            TeacherAgentEventType.RUN_COMPLETED,
            run_id,
            session_id,
            request_id,
            sequence=sequence,
            data={"final_text": text},
        )

    async def cancel(self, run_id: str) -> TeacherAgentRunResult:
        task = self._tasks.get(run_id)
        if task is None:
            request_id = f"req_{uuid.uuid4().hex}"
            return TeacherAgentRunResult(
                run_id=run_id,
                session_id="",
                request_id=request_id,
                runtime=self.runtime_name,
                status=TeacherAgentRunStatus.FAILED,
                error=TeacherAgentError(
                    code=TeacherAgentErrorCode.INTERNAL_ERROR,
                    message=f"未知 run：{run_id}",
                    request_id=request_id,
                ),
            )
        task.cancel()
        result = await asyncio.wait_for(task, timeout=30)
        return result

    async def resume(
        self, session_id: str, request: TeacherAgentRunRequest
    ) -> TeacherAgentRunResult:
        request_id = request.request_id or f"req_{uuid.uuid4().hex}"
        return TeacherAgentRunResult(
            run_id=f"run_{uuid.uuid4().hex}",
            session_id=session_id,
            request_id=request_id,
            runtime=self.runtime_name,
            status=TeacherAgentRunStatus.FAILED,
            error=TeacherAgentError(
                code=TeacherAgentErrorCode.UNSUPPORTED_CAPABILITY,
                message="legacy runtime 不支持 resume",
                request_id=request_id,
            ),
        )

    async def get_session(self, session_id: str) -> TeacherAgentSession:
        if session_id not in self._sessions:
            raise KeyError(session_id)
        return self._sessions[session_id]

    async def health(self) -> TeacherAgentHealth:
        settings = get_settings()
        configured = bool(settings.deepseek_api_key)
        return TeacherAgentHealth(
            status="ok",
            runtime=self.runtime_name,
            initialized=True,
            model_configured=configured,
            tool_registry_ready=False,
            visible_tool_count=0,
            runtime_version=self.runtime_version,
        )

    async def capabilities(self) -> TeacherAgentCapabilities:
        settings = get_settings()
        return TeacherAgentCapabilities(
            run=True,
            stream=True,
            cancel=True,
            resume=False,
            get_session=True,
            health=True,
            model_configured=bool(settings.deepseek_api_key),
            visible_tool_names=[],
            runtime_version=self.runtime_version,
        )
