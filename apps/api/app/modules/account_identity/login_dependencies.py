from __future__ import annotations

from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from typing import Literal

from fastapi import Depends

from app.core.config import Settings, get_settings
from app.modules.account_identity.contracts import (
    AccountLoginProtection,
    AccountLoginProtectionUnavailable,
    LoginNetworkOrigin,
)
from app.modules.account_identity.distributed_login_protection import (
    HttpDistributedAccountLoginProtection,
)
from app.modules.account_identity.hmac_keyring import VersionedHmacKeyRing
from app.modules.account_identity.login_network_origin import (
    DirectLoginNetworkOrigin,
    TrustedProxyLoginNetworkOrigin,
    UnavailableLoginNetworkOrigin,
)
from app.modules.account_identity.login_protection import SqliteAccountLoginProtection


class DisabledAccountLoginProtection:
    def assess(self, *, email: str, network_origin: str) -> None:
        return None

    def record(
        self,
        *,
        email: str,
        network_origin: str,
        outcome: Literal["succeeded", "failed"],
    ) -> None:
        return None

    def store_ready(self) -> bool:
        return False


class UnavailableAccountLoginProtection(DisabledAccountLoginProtection):
    @staticmethod
    def _deny() -> None:
        raise AccountLoginProtectionUnavailable("LOGIN_PROTECTION_UNAVAILABLE")

    def assess(self, *, email: str, network_origin: str) -> None:
        self._deny()

    def record(
        self,
        *,
        email: str,
        network_origin: str,
        outcome: Literal["succeeded", "failed"],
    ) -> None:
        self._deny()


_DISABLED = DisabledAccountLoginProtection()
_UNAVAILABLE = UnavailableAccountLoginProtection()
_DIRECT_ORIGIN = DirectLoginNetworkOrigin()
_UNAVAILABLE_ORIGIN = UnavailableLoginNetworkOrigin()


@lru_cache(maxsize=8)
def _build_login_protection(
    provider: str,
    environment: str,
    database_path: str,
    current_key_id: str,
    secret: str,
    previous_keys_json: str,
    window_minutes: int,
    principal_attempts: int,
    network_attempts: int,
    retention_hours: int,
    service_url: str,
    service_token: str,
    service_timeout_seconds: float,
) -> AccountLoginProtection:
    key_ring = VersionedHmacKeyRing.from_config(
        current_key_id=current_key_id,
        current_secret=secret,
        previous_keys_json=previous_keys_json,
    )
    window = timedelta(minutes=window_minutes)
    retention = timedelta(hours=retention_hours)
    if provider == "distributed_http":
        return HttpDistributedAccountLoginProtection(
            service_url=service_url,
            service_token=service_token,
            key_ring=key_ring,
            window=window,
            principal_attempts=principal_attempts,
            network_attempts=network_attempts,
            retention=retention,
            timeout_seconds=service_timeout_seconds,
            require_https=environment.strip().casefold() == "production",
        )
    if provider != "sqlite" or environment.strip().casefold() == "production":
        raise AccountLoginProtectionUnavailable("LOGIN_PROTECTION_UNAVAILABLE")
    return SqliteAccountLoginProtection(
        database_path=Path(database_path),
        key_ring=key_ring,
        window=window,
        principal_attempts=principal_attempts,
        network_attempts=network_attempts,
        retention=retention,
    )


def get_account_login_protection(
    settings: Settings = Depends(get_settings),
) -> AccountLoginProtection:
    if not settings.production_identity_enabled or settings.beta_access_enabled:
        return _DISABLED
    try:
        return _build_login_protection(
            settings.production_login_protection_provider,
            settings.environment,
            str(settings.production_login_security_db),
            settings.production_login_security_key_id,
            settings.production_login_security_secret.get_secret_value(),
            settings.production_login_security_previous_keys_json.get_secret_value(),
            settings.production_login_window_minutes,
            settings.production_login_principal_attempts,
            settings.production_login_network_attempts,
            settings.production_login_audit_retention_hours,
            settings.production_login_protection_service_url,
            settings.production_login_protection_service_token.get_secret_value(),
            settings.production_login_protection_service_timeout_seconds,
        )
    except (OSError, ValueError):
        return _UNAVAILABLE


@lru_cache(maxsize=8)
def _build_network_origin(
    source: str, trusted_proxy_cidrs: str, environment: str
) -> LoginNetworkOrigin:
    production = environment.strip().casefold() == "production"
    if source == "trusted_proxy":
        return TrustedProxyLoginNetworkOrigin(
            trusted_proxy_cidrs=trusted_proxy_cidrs
        )
    if source == "direct" and not production:
        return _DIRECT_ORIGIN
    return _UNAVAILABLE_ORIGIN


def get_login_network_origin(
    settings: Settings = Depends(get_settings),
) -> LoginNetworkOrigin:
    if not settings.production_identity_enabled or settings.beta_access_enabled:
        return _DIRECT_ORIGIN
    try:
        return _build_network_origin(
            settings.production_login_network_source,
            settings.production_trusted_proxy_cidrs,
            settings.environment,
        )
    except (OSError, ValueError):
        return _UNAVAILABLE_ORIGIN
