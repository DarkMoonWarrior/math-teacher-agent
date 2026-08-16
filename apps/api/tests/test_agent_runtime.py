"""TeacherAgentRuntime 边界测试。

- Legacy runtime：默认、无 key 报 MODEL_UNAVAILABLE、可注入补全、可取消、不支持 resume。
- DSH runtime（HTTP 适配器）：映射 Agent Service 响应、连接失败 -> RUNTIME_UNAVAILABLE、
  health/capabilities 的不可达状态、auth header、固定 base URL。
- Fallback 语义：默认禁止静默降级。
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

from app.agent_runtime import (
    DeepSeekHarnessRuntime,
    LegacyTeacherAgentRuntime,
    TeacherAgentErrorCode,
    TeacherAgentEventType,
    TeacherAgentRunRequest,
    TeacherAgentRunStatus,
)
from app.agent_runtime.registry import FallbackAwareRuntime, select_runtime_name
from app.core.config import get_settings


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


async def _collect_events(runtime, request: TeacherAgentRunRequest) -> list:
    return [event async for event in runtime.stream(request)]


def test_select_runtime_name_defaults_to_legacy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MATH_AI_AGENT_RUNTIME", "")
    get_settings.cache_clear()
    try:
        assert select_runtime_name() == "legacy"
    finally:
        get_settings.cache_clear()


def test_select_runtime_name_unknown_falls_back_to_legacy_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MATH_AI_AGENT_RUNTIME", "quantum")
    get_settings.cache_clear()
    try:
        assert select_runtime_name() == "legacy"
    finally:
        get_settings.cache_clear()


def test_legacy_run_without_key_returns_model_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        runtime = LegacyTeacherAgentRuntime()
        result = await runtime.run(TeacherAgentRunRequest(user_message="你好"))
        assert result.status == TeacherAgentRunStatus.FAILED
        assert result.error is not None
        assert result.error.code == TeacherAgentErrorCode.MODEL_UNAVAILABLE

    monkeypatch.setenv("MATH_AI_DEEPSEEK_API_KEY", "")
    get_settings.cache_clear()
    try:
        _run(scenario())
    finally:
        get_settings.cache_clear()


def test_legacy_run_with_injected_completion(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_completion(request: TeacherAgentRunRequest, _signal: Any) -> str:
        return f"回声：{request.user_message}"

    async def scenario() -> None:
        runtime = LegacyTeacherAgentRuntime(completion_fn=fake_completion)
        result = await runtime.run(
            TeacherAgentRunRequest(user_message="若 x+2=5，求 x。", request_id="req_1")
        )
        assert result.status == TeacherAgentRunStatus.COMPLETED
        assert result.final_text == "回声：若 x+2=5，求 x。"
        session = await runtime.get_session(result.session_id)
        assert result.run_id in session.run_ids

    monkeypatch.setenv("MATH_AI_DEEPSEEK_API_KEY", "present")
    get_settings.cache_clear()
    try:
        _run(scenario())
    finally:
        get_settings.cache_clear()


def test_legacy_stream_event_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_completion(request: TeacherAgentRunRequest, _signal: Any) -> str:
        return "答：x=3"

    async def scenario() -> None:
        runtime = LegacyTeacherAgentRuntime(completion_fn=fake_completion)
        events = await _collect_events(
            runtime, TeacherAgentRunRequest(user_message="求 x", request_id="req_s")
        )
        types = [event.type for event in events]
        assert types[0] == TeacherAgentEventType.RUN_STARTED
        assert TeacherAgentEventType.ASSISTANT_DELTA in types
        assert types[-1] == TeacherAgentEventType.RUN_COMPLETED

    monkeypatch.setenv("MATH_AI_DEEPSEEK_API_KEY", "present")
    get_settings.cache_clear()
    try:
        _run(scenario())
    finally:
        get_settings.cache_clear()


def test_legacy_cancel_produces_run_cancelled(monkeypatch: pytest.MonkeyPatch) -> None:
    async def slow_completion(request: TeacherAgentRunRequest, signal: Any) -> str:
        await asyncio.sleep(30)
        return "不会到达"

    async def scenario() -> None:
        runtime = LegacyTeacherAgentRuntime(completion_fn=slow_completion)
        task = asyncio.create_task(
            runtime.run(TeacherAgentRunRequest(user_message="慢任务", request_id="req_c"))
        )
        for _ in range(200):
            if runtime._tasks:
                break
            await asyncio.sleep(0.01)
        assert runtime._tasks, "run 应该已进入执行注册表"
        run_id = next(iter(runtime._tasks))
        cancelled = await runtime.cancel(run_id)
        final = await task
        assert cancelled.status == TeacherAgentRunStatus.CANCELLED
        assert cancelled.error is not None
        assert cancelled.error.code == TeacherAgentErrorCode.RUN_CANCELLED
        assert final.status == TeacherAgentRunStatus.CANCELLED

    monkeypatch.setenv("MATH_AI_DEEPSEEK_API_KEY", "present")
    get_settings.cache_clear()
    try:
        _run(scenario())
    finally:
        get_settings.cache_clear()


def test_legacy_resume_unsupported() -> None:
    async def scenario() -> None:
        runtime = LegacyTeacherAgentRuntime()
        result = await runtime.resume(
            "session_x", TeacherAgentRunRequest(user_message="继续")
        )
        assert result.error is not None
        assert result.error.code == TeacherAgentErrorCode.UNSUPPORTED_CAPABILITY

    _run(scenario())


def test_legacy_capabilities_are_honest(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        runtime = LegacyTeacherAgentRuntime()
        capabilities = await runtime.capabilities()
        assert capabilities.run is True
        assert capabilities.resume is False
        assert capabilities.model_configured is False
        assert capabilities.visible_tool_names == []
        health = await runtime.health()
        assert health.status == "ok"
        assert health.model_configured is False

    monkeypatch.setenv("MATH_AI_DEEPSEEK_API_KEY", "")
    get_settings.cache_clear()
    try:
        _run(scenario())
    finally:
        get_settings.cache_clear()


# -- DeepSeekHarnessRuntime（HTTP 适配器） ---------------------------------

_RUN_PAYLOAD = {
    "run_id": "run_dsh_1",
    "session_id": "session_dsh_1",
    "request_id": "req_dsh_1",
    "runtime": "dsh",
    "status": "completed",
    "final_text": "答案：A",
    "tool_calls": [],
    "error": None,
}


def _mock_dsh_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://127.0.0.1:4100"
    )


def _auth_ok(request: httpx.Request) -> httpx.Response:
    assert request.headers.get("authorization") == "Bearer agent-token"
    return httpx.Response(200, json=_RUN_PAYLOAD)


def _unavailable(_request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection refused")


@pytest.fixture()
def dsh_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MATH_AI_AGENT_SERVICE_URL", "http://127.0.0.1:4100")
    monkeypatch.setenv("MATH_AI_AGENT_SERVICE_TOKEN", "agent-token")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_dsh_run_maps_result_and_sends_service_token(dsh_settings) -> None:
    async def scenario() -> None:
        runtime = DeepSeekHarnessRuntime(client=_mock_dsh_client(_auth_ok))
        result = await runtime.run(
            TeacherAgentRunRequest(user_message="搜索集合题", request_id="req_dsh_1")
        )
        assert result.status == TeacherAgentRunStatus.COMPLETED
        assert result.final_text == "答案：A"
        assert result.runtime == "dsh"

    _run(scenario())


def test_dsh_unreachable_returns_runtime_unavailable(dsh_settings) -> None:
    async def scenario() -> None:
        runtime = DeepSeekHarnessRuntime(client=_mock_dsh_client(_unavailable))
        result = await runtime.run(
            TeacherAgentRunRequest(user_message="搜索集合题", request_id="req_dsh_2")
        )
        assert result.status == TeacherAgentRunStatus.FAILED
        assert result.error is not None
        assert result.error.code == TeacherAgentErrorCode.RUNTIME_UNAVAILABLE

    _run(scenario())


def test_dsh_health_and_capabilities_when_unreachable(dsh_settings) -> None:
    async def scenario() -> None:
        runtime = DeepSeekHarnessRuntime(client=_mock_dsh_client(_unavailable))
        health = await runtime.health()
        assert health.status == "unavailable"
        assert health.initialized is False
        capabilities = await runtime.capabilities()
        assert capabilities.run is False

    _run(scenario())


def test_dsh_error_body_mapped_to_vocabulary(dsh_settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"error": {"code": "TOOL_UNAUTHORIZED", "message": "token 不正确"}},
        )

    async def scenario() -> None:
        runtime = DeepSeekHarnessRuntime(client=_mock_dsh_client(handler))
        result = await runtime.run(
            TeacherAgentRunRequest(user_message="x", request_id="req_dsh_3")
        )
        assert result.error is not None
        assert result.error.code == TeacherAgentErrorCode.TOOL_UNAUTHORIZED

    _run(scenario())


def test_fallback_denied_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        runtime = DeepSeekHarnessRuntime(client=_mock_dsh_client(_unavailable))
        wrapper = FallbackAwareRuntime.__new__(FallbackAwareRuntime)
        wrapper._primary = runtime
        wrapper._primary_name = "dsh"
        wrapper._legacy = LegacyTeacherAgentRuntime()
        wrapper._allow_fallback = False
        result = await wrapper.run(
            TeacherAgentRunRequest(user_message="x", request_id="req_fb")
        )
        assert result.error is not None
        assert result.error.code == TeacherAgentErrorCode.RUNTIME_UNAVAILABLE

    monkeypatch.setenv("MATH_AI_AGENT_RUNTIME", "dsh")
    monkeypatch.setenv("MATH_AI_AGENT_ALLOW_LEGACY_FALLBACK", "false")
    monkeypatch.setenv("MATH_AI_AGENT_SERVICE_URL", "http://127.0.0.1:4100")
    monkeypatch.setenv("MATH_AI_AGENT_SERVICE_TOKEN", "agent-token")
    get_settings.cache_clear()
    try:
        _run(scenario())
    finally:
        get_settings.cache_clear()
