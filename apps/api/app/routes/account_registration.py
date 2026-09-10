from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.core.config import Settings, get_settings
from app.modules.account_identity import (
    AccountIdentity,
    AccountIdentityConflict,
    AccountIdentityUnavailable,
    AccountLoginProtection,
    AccountLoginProtectionUnavailable,
    AccountLoginRateLimited,
    AccountRegistration,
    AccountSessionStatus,
    LoginNetworkOrigin,
    LoginNetworkOriginUnavailable,
    PersonalAccountRegistration,
)
from app.modules.account_identity.dependencies import (
    get_account_identity,
    get_account_registration,
)
from app.modules.account_identity.login_dependencies import (
    get_account_login_protection,
    get_login_network_origin,
)


router = APIRouter(prefix="/account-registration", tags=["account-registration"])


def _require_registration_enabled(settings: Settings) -> None:
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
    if not settings.production_self_registration_enabled:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "ACCOUNT_REGISTRATION_DISABLED",
                "message": "当前部署未开放网页注册。",
            },
        )


def _record_or_fail(
    protection: AccountLoginProtection,
    *,
    email: str,
    network_origin: str,
    outcome: Literal["succeeded", "failed"],
) -> None:
    try:
        protection.record(
            email=email,
            network_origin=network_origin,
            outcome=outcome,
        )
    except AccountLoginProtectionUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "LOGIN_PROTECTION_UNAVAILABLE",
                "message": "账号访问防护暂不可用。",
            },
        ) from exc


@router.post("", response_model=AccountSessionStatus)
def register_personal_account(
    command: PersonalAccountRegistration,
    request: Request,
    response: Response,
    settings: Settings = Depends(get_settings),
    registration: AccountRegistration = Depends(get_account_registration),
    identity: AccountIdentity = Depends(get_account_identity),
    protection: AccountLoginProtection = Depends(get_account_login_protection),
    network_origin_resolver: LoginNetworkOrigin = Depends(get_login_network_origin),
) -> AccountSessionStatus:
    _require_registration_enabled(settings)
    try:
        network_origin = network_origin_resolver.resolve(
            peer_host=request.client.host if request.client is not None else None,
            forwarded_for=request.headers.get("x-forwarded-for"),
        )
    except LoginNetworkOriginUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "LOGIN_NETWORK_ORIGIN_UNAVAILABLE",
                "message": "注册来源校验暂不可用。",
            },
        ) from exc
    try:
        protection.assess(email=command.email, network_origin=network_origin)
    except AccountLoginRateLimited as exc:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "LOGIN_RATE_LIMITED",
                "message": "尝试过多，请稍后再试。",
            },
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    except AccountLoginProtectionUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "LOGIN_PROTECTION_UNAVAILABLE",
                "message": "账号访问防护暂不可用。",
            },
        ) from exc

    try:
        grant = registration.register_personal_account(command)
    except AccountIdentityUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "PRODUCTION_IDENTITY_UNAVAILABLE",
                "message": "正式账号服务暂不可用。",
            },
        ) from exc
    except AccountIdentityConflict as exc:
        _record_or_fail(
            protection,
            email=command.email,
            network_origin=network_origin,
            outcome="failed",
        )
        raise HTTPException(
            status_code=409,
            detail={
                "code": "ACCOUNT_REGISTRATION_CONFLICT",
                "message": "无法创建账号，请检查信息或直接登录。",
            },
        ) from exc

    try:
        _record_or_fail(
            protection,
            email=command.email,
            network_origin=network_origin,
            outcome="succeeded",
        )
    except HTTPException:
        identity.revoke(grant.token)
        raise

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
        registration_enabled=True,
        display_label=grant.identity.display_label,
        expires_at=grant.identity.expires_at,
        capabilities=grant.identity.capabilities,
    )
