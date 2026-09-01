from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.core.config import Settings, get_settings
from app.modules.beta_access import (
    ALL_BETA_CAPABILITIES,
    BetaAccess,
    BetaAccessDenied,
    BetaSessionStart,
    BetaSessionStatus,
)
from app.modules.beta_access.dependencies import get_beta_access


router = APIRouter(prefix="/beta-session", tags=["beta-session"])


def _status_for_token(
    request: Request,
    *,
    settings: Settings,
    access: BetaAccess,
) -> BetaSessionStatus:
    if not settings.beta_access_enabled:
        return BetaSessionStatus(
            mode="local_development",
            authenticated=True,
            display_label="本地开发教师",
            capabilities=list(ALL_BETA_CAPABILITIES),
        )
    token = request.cookies.get(settings.beta_session_cookie_name, "")
    try:
        teacher = access.resolve(token)
    except BetaAccessDenied:
        return BetaSessionStatus(mode="closed_beta", authenticated=False)
    return BetaSessionStatus(
        mode="closed_beta",
        authenticated=True,
        display_label=teacher.display_label,
        expires_at=teacher.expires_at,
        capabilities=teacher.capabilities,
    )


@router.get("", response_model=BetaSessionStatus)
def session_status(
    request: Request,
    settings: Settings = Depends(get_settings),
    access: BetaAccess = Depends(get_beta_access),
) -> BetaSessionStatus:
    return _status_for_token(request, settings=settings, access=access)


@router.post("", response_model=BetaSessionStatus)
def start_session(
    command: BetaSessionStart,
    response: Response,
    settings: Settings = Depends(get_settings),
    access: BetaAccess = Depends(get_beta_access),
) -> BetaSessionStatus:
    if not settings.beta_access_enabled:
        raise HTTPException(status_code=409, detail="当前未启用封闭测试访问模式。")
    try:
        grant = access.issue(command.access_code)
    except BetaAccessDenied as exc:
        raise HTTPException(status_code=401, detail="访问码无效或不可用。") from exc
    response.set_cookie(
        key=settings.beta_session_cookie_name,
        value=grant.token,
        max_age=settings.beta_session_ttl_hours * 60 * 60,
        httponly=True,
        secure=settings.beta_session_secure_cookie,
        samesite="strict",
        path="/",
    )
    return BetaSessionStatus(
        mode="closed_beta",
        authenticated=True,
        display_label=grant.teacher.display_label,
        expires_at=grant.teacher.expires_at,
        capabilities=grant.teacher.capabilities,
    )


@router.delete("", response_model=BetaSessionStatus)
def end_session(
    request: Request,
    response: Response,
    settings: Settings = Depends(get_settings),
    access: BetaAccess = Depends(get_beta_access),
) -> BetaSessionStatus:
    token = request.cookies.get(settings.beta_session_cookie_name, "")
    if settings.beta_access_enabled and token:
        access.revoke(token)
    response.delete_cookie(
        key=settings.beta_session_cookie_name,
        httponly=True,
        secure=settings.beta_session_secure_cookie,
        samesite="strict",
        path="/",
    )
    if settings.beta_access_enabled:
        return BetaSessionStatus(mode="closed_beta", authenticated=False)
    return BetaSessionStatus(
        mode="local_development",
        authenticated=True,
        display_label="本地开发教师",
        capabilities=list(ALL_BETA_CAPABILITIES),
    )
