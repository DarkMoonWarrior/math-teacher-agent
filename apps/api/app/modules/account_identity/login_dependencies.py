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


@lru_cache(maxsize=8)
def _build_login_protection(
    database_path: str,
    secret: str,
    window_minutes: int,
    principal_attempts: int,
    network_attempts: int,
    retention_hours: int,
) -> AccountLoginProtection:
    return SqliteAccountLoginProtection(
        database_path=Path(database_path),
        secret=secret,
        window=timedelta(minutes=window_minutes),
        principal_attempts=principal_attempts,
        network_attempts=network_attempts,
        retention=timedelta(hours=retention_hours),
    )


def get_account_login_protection(
    settings: Settings = Depends(get_settings),
) -> AccountLoginProtection:
    if not settings.production_identity_enabled or settings.beta_access_enabled:
        return _DISABLED
    secret = settings.production_login_security_secret.get_secret_value()
    if len(secret) < 32:
        return _UNAVAILABLE
    try:
        return _build_login_protection(
            str(settings.production_login_security_db),
            secret,
            settings.production_login_window_minutes,
            settings.production_login_principal_attempts,
            settings.production_login_network_attempts,
            settings.production_login_audit_retention_hours,
        )
    except (OSError, ValueError):
        return _UNAVAILABLE
