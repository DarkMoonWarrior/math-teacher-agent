from __future__ import annotations

from typing import Literal

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.capabilities import ALL_WORKBENCH_CAPABILITIES, WorkbenchCapability
from app.core.config import Settings, get_settings
from app.modules.account_identity import (
    AccountIdentity,
    AccountIdentityDenied,
    AccountRole,
)
from app.modules.account_identity.dependencies import get_account_identity
from app.modules.beta_access import BetaAccess, BetaAccessDenied
from app.modules.beta_access.dependencies import get_beta_access


class CurrentTeacher(BaseModel):
    """Server-owned teacher identity presented to business modules.

    Closed Beta sessions and local development are adapters behind the same
    dependency, which stays replaceable in owner-isolation tests. Browser and
    model payloads never choose this value.
    """

    teacher_id: str = Field(min_length=1, max_length=120)
    source: Literal[
        "local_development",
        "authenticated_session",
        "beta_session",
        "production_session",
    ]
    capabilities: list[WorkbenchCapability] = Field(
        default_factory=lambda: list(ALL_WORKBENCH_CAPABILITIES)
    )
    account_id: str | None = None
    tenant_id: str | None = None
    role: AccountRole | None = None


def get_current_teacher(
    request: Request,
    settings: Settings = Depends(get_settings),
    access: BetaAccess = Depends(get_beta_access),
    account_identity: AccountIdentity = Depends(get_account_identity),
) -> CurrentTeacher:
    if settings.production_identity_enabled and settings.beta_access_enabled:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "IDENTITY_MODE_CONFLICT",
                "message": "正式账号与封闭测试访问不能同时启用。",
            },
        )
    if settings.production_identity_enabled:
        token = request.cookies.get(settings.production_session_cookie_name, "")
        try:
            identity = account_identity.resolve(token)
        except AccountIdentityDenied as exc:
            raise HTTPException(
                status_code=401,
                detail="正式账号会话无效或已过期，请重新登录。",
            ) from exc
        return CurrentTeacher(
            teacher_id=identity.owner_id,
            source="production_session",
            capabilities=identity.capabilities,
            account_id=identity.account_id,
            tenant_id=identity.tenant_id,
            role=identity.role,
        )
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


_CAPABILITY_LABELS: dict[WorkbenchCapability, str] = {
    "search": "搜题",
    "solve": "解题",
    "library": "资料库",
    "authoring": "命题",
    "lesson": "教案",
    "paper": "组卷",
    "teacher_memory": "教师偏好",
}


def require_local_legacy_access(
    settings: Settings = Depends(get_settings),
) -> None:
    """Legacy single-user REST workflows must never operate on Beta stores.

    Check deployment mode, not an overridable teacher/source field. This is not
    a substitute for owner checks in the supported product interfaces.
    """
    if settings.beta_access_enabled or settings.production_identity_enabled:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "LEGACY_WORKFLOW_UNAVAILABLE",
                "message": "账号模式不开放旧版工作流，请使用当前教师工作台。",
            },
        )


def require_capability(capability: WorkbenchCapability):
    def requirement(
        current_teacher: CurrentTeacher = Depends(get_current_teacher),
    ) -> CurrentTeacher:
        if capability not in current_teacher.capabilities:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "CAPABILITY_UNAVAILABLE",
                    "capability": capability,
                    "message": f"当前账号尚未开放{_CAPABILITY_LABELS[capability]}。",
                },
            )
        return current_teacher

    return requirement


def require_any_capability(*capabilities: WorkbenchCapability):
    if not capabilities:
        raise ValueError("至少需要一个工作台能力。")

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
                    "message": "当前账号尚未开放此工作区。",
                },
            )
        return current_teacher

    return requirement
