from __future__ import annotations

from datetime import timedelta
from functools import lru_cache
from pathlib import Path

from fastapi import Depends

from app.core.config import Settings, get_settings
from app.modules.account_identity.contracts import AccountIdentity, AccountIdentityDenied
from app.modules.account_identity.schemas import (
    AccountIdentityContext,
    AccountLogin,
    AccountSessionGrant,
    PersonalAccountProvision,
    ProvisionedAccount,
)
from app.modules.account_identity.sqlite_adapter import SqliteAccountIdentity


class DisabledAccountIdentity:
    """No-storage adapter used whenever production identity is not the active mode."""

    @staticmethod
    def _deny() -> None:
        raise AccountIdentityDenied("正式账号未启用。")

    def provision_personal_account(
        self, command: PersonalAccountProvision
    ) -> ProvisionedAccount:
        self._deny()

    def authenticate(self, command: AccountLogin) -> AccountSessionGrant:
        self._deny()

    def resolve(self, token: str) -> AccountIdentityContext:
        self._deny()

    def revoke(self, token: str) -> bool:
        return False

    def store_ready(self) -> bool:
        return False


_DISABLED_ACCOUNT_IDENTITY = DisabledAccountIdentity()


@lru_cache(maxsize=8)
def _build_account_identity(database_path: str, ttl_hours: int) -> AccountIdentity:
    return SqliteAccountIdentity(
        database_path=Path(database_path),
        session_ttl=timedelta(hours=ttl_hours),
    )


def get_account_identity(
    settings: Settings = Depends(get_settings),
) -> AccountIdentity:
    if not settings.production_identity_enabled or settings.beta_access_enabled:
        return _DISABLED_ACCOUNT_IDENTITY
    return _build_account_identity(
        str(settings.production_identity_db),
        settings.production_session_ttl_hours,
    )
