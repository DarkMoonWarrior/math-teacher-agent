from __future__ import annotations

from typing import Literal

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.config import Settings, get_settings
from app.modules.beta_access import (
    ALL_BETA_CAPABILITIES,
    BetaAccess,
    BetaAccessDenied,
    BetaCapability,
)
from app.modules.beta_access.dependencies import get_beta_access


class CurrentTeacher(BaseModel):
    """Server-owned teacher identity presented to business modules.

    Closed Beta sessions and local development are adapters behind the same
    dependency, which stays replaceable in owner-isolation tests. Browser and
    model payloads never choose this value.
    """

    teacher_id: str = Field(min_length=1, max_length=120)
    source: Literal["local_development", "authenticated_session", "beta_session"]
    capabilities: list[BetaCapability] = Field(
        default_factory=lambda: list(ALL_BETA_CAPABILITIES)
    )


def get_current_teacher(
    request: Request,
    settings: Settings = Depends(get_settings),
    access: BetaAccess = Depends(get_beta_access),
) -> CurrentTeacher:
    if settings.beta_access_enabled:
        token = request.cookies.get(settings.beta_session_cookie_name, "")
        try:
            teacher = access.resolve(token)
        except BetaAccessDenied as exc:
            raise HTTPException(
                status_code=401,
                detail="封闭测试会话无效或已过期，请重新输入访问码。",
            ) from exc
        return CurrentTeacher(
            teacher_id=teacher.teacher_id,
            source="beta_session",
            capabilities=teacher.capabilities,
        )
    return CurrentTeacher(
        teacher_id="owner_teacher",
        source="local_development",
    )


_CAPABILITY_LABELS: dict[BetaCapability, str] = {
    "search": "搜题",
    "solve": "解题",
    "library": "资料库",
    "authoring": "命题",
    "lesson": "教案",
    "paper": "组卷",
    "teacher_memory": "教师偏好",
}


def require_beta_capability(capability: BetaCapability):
    def requirement(
        current_teacher: CurrentTeacher = Depends(get_current_teacher),
    ) -> CurrentTeacher:
        if capability not in current_teacher.capabilities:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "CAPABILITY_UNAVAILABLE",
                    "capability": capability,
                    "message": f"当前封闭测试尚未开放{_CAPABILITY_LABELS[capability]}。",
                },
            )
        return current_teacher

    return requirement


def require_any_beta_capability(*capabilities: BetaCapability):
    if not capabilities:
        raise ValueError("至少需要一个封闭测试能力。")

    def requirement(
        current_teacher: CurrentTeacher = Depends(get_current_teacher),
    ) -> CurrentTeacher:
        if not any(
            capability in current_teacher.capabilities for capability in capabilities
        ):
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "CAPABILITY_UNAVAILABLE",
                    "capability": capabilities[0],
                    "message": "当前封闭测试尚未开放此工作区。",
                },
            )
        return current_teacher

    return requirement
