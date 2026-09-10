from __future__ import annotations

from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from typing import cast

from fastapi import Depends

from app.core.config import Settings, get_settings

from app.modules.account_identity.contracts import (
    AccountIdentity,
    AccountIdentityDenied,
    AccountIdentityUnavailable,
    AccountRegistration,
)
from app.modules.account_identity.schemas import (
    AccountIdentityContext,
    AccountLogin,
    AccountSessionGrant,
    PersonalAccountRegistration,
)
from app.modules.account_identity.sqlite_adapter import SqliteAccountIdentity
from app.modules.account_identity.postgres_adapter import PostgresAccountIdentity


class DisabledAccountIdentity:
    """No-storage adapter used whenever production identity is not the active mode."""

    @staticmethod
    def _deny() -> None:
        raise AccountIdentityDenied("正式账号未启用。")

    def authenticate(self, command: AccountLogin) -> AccountSessionGrant:
        self._deny()

    def resolve(self, token: str) -> AccountIdentityContext:
        self._deny()

    def revoke(self, token: str) -> bool:
        return False

    def register_personal_account(
        self, command: PersonalAccountRegistration
    ) -> AccountSessionGrant:
        self._deny()

    def store_ready(self) -> bool:
        return False


_DISABLED_ACCOUNT_IDENTITY = DisabledAccountIdentity()


class UnavailableAccountIdentity:
    """Fail-closed adapter for an invalid or unavailable production backend."""

    @staticmethod
    def _unavailable() -> None:
        raise AccountIdentityUnavailable("PRODUCTION_IDENTITY_UNAVAILABLE")

    def authenticate(self, command: AccountLogin) -> AccountSessionGrant:
        self._unavailable()

    def resolve(self, token: str) -> AccountIdentityContext:
        self._unavailable()

    def revoke(self, token: str) -> bool:
        return False

    def register_personal_account(
        self, command: PersonalAccountRegistration
    ) -> AccountSessionGrant:
        self._unavailable()

    def store_ready(self) -> bool:
        return False


_UNAVAILABLE_ACCOUNT_IDENTITY = UnavailableAccountIdentity()


@lru_cache(maxsize=8)
def _build_account_identity(database_path: str, ttl_hours: int) -> AccountIdentity:
    return SqliteAccountIdentity(
        database_path=Path(database_path),
        session_ttl=timedelta(hours=ttl_hours),
    )


@lru_cache(maxsize=8)
def _build_postgres_account_identity(dsn: str, ttl_hours: int) -> AccountIdentity:
    return PostgresAccountIdentity(
        dsn=dsn,
        session_ttl=timedelta(hours=ttl_hours),
    )


def get_account_identity(
    settings: Settings = Depends(get_settings),
) -> AccountIdentity:
    if not settings.production_identity_enabled or settings.beta_access_enabled:
        return _DISABLED_ACCOUNT_IDENTITY
    if settings.production_identity_provider == "postgresql":
        dsn = settings.production_identity_postgres_dsn.get_secret_value().strip()
        if not dsn:
            return _UNAVAILABLE_ACCOUNT_IDENTITY
        return _build_postgres_account_identity(
            dsn,
            settings.production_session_ttl_hours,
        )
    if settings.environment.casefold() == "production":
        return _UNAVAILABLE_ACCOUNT_IDENTITY
    return _build_account_identity(
        str(settings.production_identity_db),
        settings.production_session_ttl_hours,
    )


def get_account_registration(
    identity: AccountIdentity = Depends(get_account_identity),
) -> AccountRegistration:
    return cast(AccountRegistration, identity)
