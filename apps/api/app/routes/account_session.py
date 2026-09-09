from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.core.config import Settings, get_settings
from app.modules.account_identity import (
    AccountIdentity,
    AccountIdentityDenied,
    AccountLogin,
    AccountLoginProtection,
    AccountLoginProtectionUnavailable,
    AccountLoginRateLimited,
    AccountSessionStatus,
)
from app.modules.account_identity.dependencies import get_account_identity
from app.modules.account_identity.login_dependencies import get_account_login_protection


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
    request: Request,
    response: Response,
    settings: Settings = Depends(get_settings),
    identity: AccountIdentity = Depends(get_account_identity),
    protection: AccountLoginProtection = Depends(get_account_login_protection),
) -> AccountSessionStatus:
    _require_enabled(settings)
    network_origin = request.client.host if request.client is not None else "unknown"
    try:
        protection.assess(email=command.email, network_origin=network_origin)
    except AccountLoginRateLimited as exc:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "LOGIN_RATE_LIMITED",
                "message": "登录尝试过多，请稍后再试。",
            },
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    except AccountLoginProtectionUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "LOGIN_PROTECTION_UNAVAILABLE",
                "message": "登录防护暂不可用。",
            },
        ) from exc
    try:
        grant = identity.authenticate(command)
    except AccountIdentityDenied as exc:
        try:
            protection.record(
                email=command.email,
                network_origin=network_origin,
                outcome="failed",
            )
        except AccountLoginProtectionUnavailable as protection_exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "LOGIN_PROTECTION_UNAVAILABLE",
                    "message": "登录防护暂不可用。",
                },
            ) from protection_exc
        raise HTTPException(status_code=401, detail="邮箱或密码无效。") from exc
    try:
        protection.record(
            email=command.email,
            network_origin=network_origin,
            outcome="succeeded",
        )
    except AccountLoginProtectionUnavailable as exc:
        identity.revoke(grant.token)
        raise HTTPException(
            status_code=503,
            detail={
                "code": "LOGIN_PROTECTION_UNAVAILABLE",
                "message": "登录防护暂不可用。",
            },
        ) from exc
    previous_token = request.cookies.get(settings.production_session_cookie_name, "")
    if previous_token:
        identity.revoke(previous_token)
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
