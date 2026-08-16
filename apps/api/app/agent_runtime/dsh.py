"""DeepSeekHarnessRuntime：通过 HTTP 调用独立 Agent Service 的适配器。

本模块是 Python 侧与 Agent Service 之间唯一的 HTTP 边界：
- 只允许请求固定 base URL（环境变量提供，禁止模型/用户提供 URL）。
- 使用独立 service token（MATH_AI_AGENT_SERVICE_TOKEN）。
- 不直接 import 任何 DeepSeek Harness 类型。
- Agent Service 不可达时返回 RUNTIME_UNAVAILABLE，绝不静默降级。
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
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
)
from app.core.config import get_settings

logger = logging.getLogger("math_ai.agent_runtime.dsh")


class DeepSeekHarnessRuntime(TeacherAgentRuntime):
    runtime_name = "dsh"
    runtime_version = "0.1.0"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        settings = get_settings()
        self._base_url = settings.agent_service_url.rstrip("/")
        self._token = settings.agent_service_token
        self._request_timeout = httpx.Timeout(settings.agent_request_timeout_seconds)
        self._client = client

    def _headers(self, request_id: str) -> dict[str, str]:
        headers = {"X-Request-Id": request_id}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def _parse_error(self, body: str, request_id: str) -> TeacherAgentError:
        try:
            payload = json.loads(body)
            error = payload.get("error") or payload
            code_raw = error.get("code", "INTERNAL_ERROR")
            code = TeacherAgentErrorCode(code_raw)
            return TeacherAgentError(
                code=code,
                message=str(error.get("message", "Agent Service 返回错误"))[:500],
                request_id=request_id,
            )
        except (ValueError, TypeError, json.JSONDecodeError):
            return TeacherAgentError(
                code=TeacherAgentErrorCode.INTERNAL_ERROR,
                message="Agent Service 返回无法解析的错误",
                request_id=request_id,
            )

    async def _post_json(
        self, path: str, payload: dict[str, Any], request_id: str
    ) -> tuple[int, Any | None, TeacherAgentError | None]:
        try:
            client = self._client or httpx.AsyncClient(timeout=self._request_timeout)
            owns_client = self._client is None
            try:
                response = await client.post(
                    f"{self._base_url}{path}",
                    headers=self._headers(request_id),
                    json=payload,
                )
            finally:
                if owns_client:
                    await client.aclose()
        except httpx.HTTPError as exc:
            return 0, None, TeacherAgentError(
                code=TeacherAgentErrorCode.RUNTIME_UNAVAILABLE,
                message="Agent Service 不可达",
                request_id=request_id,
            )
        if response.status_code >= 400:
            return (
                response.status_code,
                None,
                self._parse_error(response.text, request_id),
            )
        try:
            return response.status_code, response.json(), None
        except json.JSONDecodeError:
            return response.status_code, None, TeacherAgentError(
                code=TeacherAgentErrorCode.INTERNAL_ERROR,
                message="Agent Service 返回非 JSON 响应",
                request_id=request_id,
            )

    # -- TeacherAgentRuntime ---------------------------------------------

    async def run(self, request: TeacherAgentRunRequest) -> TeacherAgentRunResult:
        request_id = request.request_id or f"req_{uuid.uuid4().hex}"
        status, payload, error = await self._post_json(
            "/v1/run",
            {
                "session_id": request.session_id,
                "user_message": request.user_message,
                "request_id": request_id,
                "teacher_user_id": request.teacher_user_id,
                "tenant_id": request.tenant_id,
            },
            request_id,
        )
        if error is not None:
            return TeacherAgentRunResult(
                run_id=f"run_{uuid.uuid4().hex}",
                session_id=request.session_id or "",
                request_id=request_id,
                runtime=self.runtime_name,
                status=TeacherAgentRunStatus.FAILED,
                error=error,
            )
        try:
            return TeacherAgentRunResult(**payload)
        except Exception:
            return TeacherAgentRunResult(
                run_id=f"run_{uuid.uuid4().hex}",
                session_id=request.session_id or "",
                request_id=request_id,
                runtime=self.runtime_name,
                status=TeacherAgentRunStatus.FAILED,
                error=TeacherAgentError(
                    code=TeacherAgentErrorCode.INTERNAL_ERROR,
                    message="Agent Service 返回结构异常",
                    request_id=request_id,
                ),
            )

    async def stream(
        self, request: TeacherAgentRunRequest
    ) -> AsyncIterator[TeacherAgentEvent]:
        request_id = request.request_id or f"req_{uuid.uuid4().hex}"
        client = self._client or httpx.AsyncClient(timeout=httpx.Timeout(None))
        owns_client = self._client is None
        try:
            try:
                async with client.stream(
                    "POST",
                    f"{self._base_url}/v1/stream",
                    headers=self._headers(request_id),
                    json={
                        "session_id": request.session_id,
                        "user_message": request.user_message,
                        "request_id": request_id,
                        "teacher_user_id": request.teacher_user_id,
                        "tenant_id": request.tenant_id,
                    },
                ) as response:
                    if response.status_code >= 400:
                        error = self._parse_error(await response.aread(), request_id)
                        yield TeacherAgentEvent(
                            type=TeacherAgentEventType.RUN_FAILED,
                            run_id="",
                            session_id=request.session_id or "",
                            request_id=request_id,
                            data={"error": error.model_dump(mode="json")},
                        )
                        return
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        raw = line[len("data:") :].strip()
                        if not raw:
                            continue
                        try:
                            yield TeacherAgentEvent(**json.loads(raw))
                        except (ValueError, TypeError, json.JSONDecodeError):
                            continue
            except httpx.HTTPError:
                yield TeacherAgentEvent(
                    type=TeacherAgentEventType.RUN_FAILED,
                    run_id="",
                    session_id=request.session_id or "",
                    request_id=request_id,
                    data={
                        "error": TeacherAgentError(
                            code=TeacherAgentErrorCode.RUNTIME_UNAVAILABLE,
                            message="Agent Service 不可达",
                            request_id=request_id,
                        ).model_dump(mode="json")
                    },
                )
        finally:
            if owns_client:
                await client.aclose()

    async def cancel(self, run_id: str) -> TeacherAgentRunResult:
        request_id = f"req_{uuid.uuid4().hex}"
        status, payload, error = await self._post_json(
            "/v1/cancel", {"run_id": run_id}, request_id
        )
        if error is not None:
            return TeacherAgentRunResult(
                run_id=run_id,
                session_id="",
                request_id=request_id,
                runtime=self.runtime_name,
                status=TeacherAgentRunStatus.FAILED,
                error=error,
            )
        try:
            return TeacherAgentRunResult(**payload)
        except Exception:
            return TeacherAgentRunResult(
                run_id=run_id,
                session_id="",
                request_id=request_id,
                runtime=self.runtime_name,
                status=TeacherAgentRunStatus.FAILED,
                error=TeacherAgentError(
                    code=TeacherAgentErrorCode.INTERNAL_ERROR,
                    message="Agent Service 返回结构异常",
                    request_id=request_id,
                ),
            )

    async def resume(
        self, session_id: str, request: TeacherAgentRunRequest
    ) -> TeacherAgentRunResult:
        request_id = request.request_id or f"req_{uuid.uuid4().hex}"
        status, payload, error = await self._post_json(
            "/v1/resume",
            {
                "session_id": session_id,
                "user_message": request.user_message,
                "request_id": request_id,
                "teacher_user_id": request.teacher_user_id,
                "tenant_id": request.tenant_id,
            },
            request_id,
        )
        if error is not None:
            return TeacherAgentRunResult(
                run_id=f"run_{uuid.uuid4().hex}",
                session_id=session_id,
                request_id=request_id,
                runtime=self.runtime_name,
                status=TeacherAgentRunStatus.FAILED,
                error=error,
            )
        try:
            return TeacherAgentRunResult(**payload)
        except Exception:
            return TeacherAgentRunResult(
                run_id=f"run_{uuid.uuid4().hex}",
                session_id=session_id,
                request_id=request_id,
                runtime=self.runtime_name,
                status=TeacherAgentRunStatus.FAILED,
                error=TeacherAgentError(
                    code=TeacherAgentErrorCode.INTERNAL_ERROR,
                    message="Agent Service 返回结构异常",
                    request_id=request_id,
                ),
            )

    async def get_session(self, session_id: str) -> TeacherAgentSession:
        request_id = f"req_{uuid.uuid4().hex}"
        try:
            client = self._client or httpx.AsyncClient(timeout=self._request_timeout)
            owns_client = self._client is None
            try:
                response = await client.get(
                    f"{self._base_url}/v1/sessions/{session_id}",
                    headers=self._headers(request_id),
                )
            finally:
                if owns_client:
                    await client.aclose()
        except httpx.HTTPError as exc:
            raise KeyError(session_id) from exc
        if response.status_code == 404:
            raise KeyError(session_id)
        if response.status_code >= 400:
            raise RuntimeError(self._parse_error(response.text, request_id).message)
        try:
            return TeacherAgentSession(**response.json())
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError("Agent Service 返回结构异常") from exc

    async def health(self) -> TeacherAgentHealth:
        request_id = f"req_{uuid.uuid4().hex}"
        try:
            client = self._client or httpx.AsyncClient(timeout=self._request_timeout)
            owns_client = self._client is None
            try:
                response = await client.get(
                    f"{self._base_url}/health", headers=self._headers(request_id)
                )
            finally:
                if owns_client:
                    await client.aclose()
        except httpx.HTTPError:
            return TeacherAgentHealth(
                status="unavailable",
                runtime=self.runtime_name,
                initialized=False,
                model_configured=False,
                tool_registry_ready=False,
                visible_tool_count=0,
                runtime_version=self.runtime_version,
            )
        if response.status_code >= 400:
            return TeacherAgentHealth(
                status="unavailable",
                runtime=self.runtime_name,
                initialized=False,
                model_configured=False,
                tool_registry_ready=False,
                visible_tool_count=0,
                runtime_version=self.runtime_version,
            )
        try:
            return TeacherAgentHealth(**response.json())
        except (ValueError, TypeError, json.JSONDecodeError):
            return TeacherAgentHealth(
                status="unavailable",
                runtime=self.runtime_name,
                initialized=False,
                model_configured=False,
                tool_registry_ready=False,
                visible_tool_count=0,
                runtime_version=self.runtime_version,
            )

    async def capabilities(self) -> TeacherAgentCapabilities:
        request_id = f"req_{uuid.uuid4().hex}"
        try:
            client = self._client or httpx.AsyncClient(timeout=self._request_timeout)
            owns_client = self._client is None
            try:
                response = await client.get(
                    f"{self._base_url}/capabilities",
                    headers=self._headers(request_id),
                )
            finally:
                if owns_client:
                    await client.aclose()
        except httpx.HTTPError:
            return TeacherAgentCapabilities(
                run=False,
                stream=False,
                cancel=False,
                resume=False,
                get_session=False,
                health=False,
                runtime_version=self.runtime_version,
            )
        if response.status_code >= 400:
            return TeacherAgentCapabilities(
                run=False,
                stream=False,
                cancel=False,
                resume=False,
                get_session=False,
                health=False,
                runtime_version=self.runtime_version,
            )
        try:
            return TeacherAgentCapabilities(**response.json())
        except (ValueError, TypeError, json.JSONDecodeError):
            return TeacherAgentCapabilities(
                run=False,
                stream=False,
                cancel=False,
                resume=False,
                get_session=False,
                health=False,
                runtime_version=self.runtime_version,
            )
