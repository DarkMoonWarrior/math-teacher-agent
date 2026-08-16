"""运行时选择注册表。

- MATH_AI_AGENT_RUNTIME=legacy（默认）→ LegacyTeacherAgentRuntime。
- MATH_AI_AGENT_RUNTIME=dsh → DeepSeekHarnessRuntime。
- 不允许静默 fallback：只有 MATH_AI_AGENT_ALLOW_LEGACY_FALLBACK=true 时，
  dsh 不可达才会显式降级，并且必须记录 fallback happened / original error /
  runtime used（日志不含 private content）。
"""

from __future__ import annotations

import logging
from functools import lru_cache

from app.agent_runtime.base import TeacherAgentRuntime
from app.agent_runtime.dsh import DeepSeekHarnessRuntime
from app.agent_runtime.legacy import LegacyTeacherAgentRuntime
from app.core.config import get_settings

logger = logging.getLogger("math_ai.agent_runtime.registry")

_RUNTIMES = ("legacy", "dsh")


def select_runtime_name() -> str:
    name = get_settings().agent_runtime.strip().lower()
    if name not in _RUNTIMES:
        logger.warning(
            "agent_runtime_unknown",
            extra={"configured": name, "defaulting_to": "legacy"},
        )
        return "legacy"
    return name


@lru_cache
def get_teacher_agent_runtime() -> TeacherAgentRuntime:
    name = select_runtime_name()
    if name == "dsh":
        return DeepSeekHarnessRuntime()
    return LegacyTeacherAgentRuntime()


class FallbackAwareRuntime(TeacherAgentRuntime):
    """可选显式降级包装器：只在配置允许时把 dsh 的 RUNTIME_UNAVAILABLE 降级为 legacy。

    默认 MATH_AI_AGENT_ALLOW_LEGACY_FALLBACK=false，因此默认行为是直接报错、绝不静默降级。
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._primary_name = select_runtime_name()
        self._primary = get_teacher_agent_runtime()
        self._legacy = LegacyTeacherAgentRuntime()
        self._allow_fallback = settings.agent_allow_legacy_fallback

    @property
    def runtime_name(self) -> str:
        return self._primary_name

    @property
    def runtime_version(self) -> str:
        return self._primary.runtime_version

    def _should_fallback(self, result) -> bool:
        error = getattr(result, "error", None)
        if error is None:
            return False
        from app.agent_runtime.models import TeacherAgentErrorCode

        if error.code != TeacherAgentErrorCode.RUNTIME_UNAVAILABLE:
            return False
        if not self._allow_fallback:
            logger.info(
                "agent_fallback_denied",
                extra={"runtime": self._primary_name, "reason": "fallback disabled"},
            )
            return False
        logger.warning(
            "agent_fallback_happened",
            extra={
                "original_error": error.code.value,
                "runtime_used": "legacy",
                "request_id": error.request_id,
            },
        )
        return True

    async def run(self, request):
        result = await self._primary.run(request)
        if self._should_fallback(result):
            return await self._legacy.run(request)
        return result

    async def stream(self, request):
        async for event in self._primary.stream(request):
            if (
                event.type.value == "run_failed"
                and event.data.get("error", {}).get("code") == "RUNTIME_UNAVAILABLE"
                and self._allow_fallback
            ):
                logger.warning(
                    "agent_fallback_happened",
                    extra={
                        "original_error": "RUNTIME_UNAVAILABLE",
                        "runtime_used": "legacy",
                        "request_id": getattr(event, "request_id", ""),
                    },
                )
                async for fallback_event in self._legacy.stream(request):
                    yield fallback_event
                return
            yield event

    async def cancel(self, run_id: str):
        return await self._primary.cancel(run_id)

    async def resume(self, session_id: str, request):
        return await self._primary.resume(session_id, request)

    async def get_session(self, session_id: str):
        return await self._primary.get_session(session_id)

    async def health(self):
        return await self._primary.health()

    async def capabilities(self):
        return await self._primary.capabilities()
