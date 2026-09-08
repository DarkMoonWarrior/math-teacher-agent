from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.core.config import Settings, get_settings
from app.modules.account_identity import (
    AccountIdentity,
    AccountIdentityDenied,
    AccountLogin,
    AccountSessionStatus,
)
from app.modules.account_identity.dependencies import get_account_identity


router = APIRouter(prefix="/account-session", tags=["account-session"])


def _require_enabled(settings: Settings) -> None:
    if not settings.production_identity_enabled:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "PRODUCTION_IDENTITY_DISABLED",
                "message": "正式账号尚未启用。",
            },
        )
    if settings.beta_access_enabled:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "IDENTITY_MODE_CONFLICT",
                "message": "正式账号与封闭测试访问不能同时启用。",
            },
        )


@router.get("", response_model=AccountSessionStatus)
def session_status(
    request: Request,
    settings: Settings = Depends(get_settings),
    identity: AccountIdentity = Depends(get_account_identity),
) -> AccountSessionStatus:
    _require_enabled(settings)
    token = request.cookies.get(settings.production_session_cookie_name, "")
    try:
        context = identity.resolve(token)
    except AccountIdentityDenied:
        return AccountSessionStatus(enabled=True, authenticated=False)
    return AccountSessionStatus(
        enabled=True,
        authenticated=True,
        display_label=context.display_label,
        expires_at=context.expires_at,
        capabilities=context.capabilities,
    )


@router.post("", response_model=AccountSessionStatus)
def start_session(
    command: AccountLogin,
    response: Response,
    settings: Settings = Depends(get_settings),
    identity: AccountIdentity = Depends(get_account_identity),
) -> AccountSessionStatus:
    _require_enabled(settings)
    try:
        grant = identity.authenticate(command)
    except AccountIdentityDenied as exc:
        raise HTTPException(status_code=401, detail="邮箱或密码无效。") from exc
    response.set_cookie(
        key=settings.production_session_cookie_name,
        value=grant.token,
        max_age=settings.production_session_ttl_hours * 60 * 60,
        httponly=True,
        secure=settings.production_session_secure_cookie,
        samesite="strict",
        path="/",
    )
    return AccountSessionStatus(
        enabled=True,
        authenticated=True,
        display_label=grant.identity.display_label,
        expires_at=grant.identity.expires_at,
        capabilities=grant.identity.capabilities,
    )


@router.delete("", response_model=AccountSessionStatus)
def end_session(
    request: Request,
    response: Response,
    settings: Settings = Depends(get_settings),
    identity: AccountIdentity = Depends(get_account_identity),
) -> AccountSessionStatus:
    _require_enabled(settings)
    token = request.cookies.get(settings.production_session_cookie_name, "")
    if token:
        identity.revoke(token)
    response.delete_cookie(
        key=settings.production_session_cookie_name,
        httponly=True,
        secure=settings.production_session_secure_cookie,
        samesite="strict",
        path="/",
    )
    return AccountSessionStatus(enabled=True, authenticated=False)
