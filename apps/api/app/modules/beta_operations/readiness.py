from __future__ import annotations

from datetime import datetime, timezone

from app.agent_runtime import TeacherAgentRuntime
from app.core.config import Settings
from app.modules.beta_access import BetaAccess
from app.modules.beta_operations.schemas import (
    ReadinessComponent,
    ReadinessSnapshot,
)


class ReadinessProbe:
    """Describe dependency health with stable codes and no secret configuration."""

    async def check(
        self,
        *,
        settings: Settings,
        beta_access: BetaAccess,
        runtime: TeacherAgentRuntime,
    ) -> ReadinessSnapshot:
        components = [
            ReadinessComponent(
                name="api",
                status="ready",
                code="API_READY",
                message="API 已可接收请求。",
            )
        ]

        beta_ready = beta_access.store_ready() and (
            not settings.beta_access_enabled or beta_access.has_participants()
        )
        components.append(ReadinessComponent(
            name="beta_access",
            status="ready" if beta_ready else "unavailable",
            code="BETA_ACCESS_READY" if beta_ready else "BETA_ACCESS_UNAVAILABLE",
            message="封闭测试会话存储可用。" if beta_ready else "封闭测试准入配置或会话存储不可用。",
        ))

        agent_required = any((
            settings.search_agent_enabled,
            settings.solve_agent_enabled,
            settings.question_authoring_agent_enabled,
        ))
        if not agent_required:
            components.append(ReadinessComponent(
                name="agent_runtime",
                status="not_required",
                code="AGENT_NOT_REQUIRED",
                message="当前未启用 Agent 工作流。",
            ))
        else:
            try:
                health = await runtime.health()
                agent_ready = (
                    health.status == "ok"
                    and health.initialized
                    and health.model_configured
                    and (settings.agent_runtime != "dsh" or health.tool_registry_ready)
                )
                components.append(ReadinessComponent(
                    name="agent_runtime",
                    status="ready" if agent_ready else "unavailable",
                    code="AGENT_READY" if agent_ready else "AGENT_UNAVAILABLE",
                    message="Agent Runtime 与受控工具可用。" if agent_ready else "Agent Runtime、模型或受控工具尚未就绪。",
                ))
            except Exception:
                components.append(ReadinessComponent(
                    name="agent_runtime",
                    status="unavailable",
                    code="AGENT_UNAVAILABLE",
                    message="Agent Runtime 健康检查暂不可用。",
                ))

        return ReadinessSnapshot(
            status="ready" if all(
                component.status in {"ready", "not_required"}
                for component in components
            ) else "degraded",
            checked_at=datetime.now(timezone.utc),
            components=components,
        )
