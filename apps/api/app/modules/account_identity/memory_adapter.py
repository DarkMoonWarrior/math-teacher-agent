from __future__ import annotations

import secrets
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from app.core.capabilities import ALL_WORKBENCH_CAPABILITIES
from app.modules.account_identity.contracts import (
    AccountIdentityConflict,
    AccountIdentityDenied,
)
from app.modules.account_identity.crypto import hash_password, verify_password
from app.modules.account_identity.schemas import (
    AccountIdentityContext,
    AccountLogin,
    AccountSessionGrant,
    PersonalAccountProvision,
    ProvisionedAccount,
)


_DUMMY_PASSWORD_HASH = hash_password(
    "not-a-real-account-password", salt=b"m14-dummy-login"
)


class InMemoryAccountIdentity:
    """Deterministic test adapter for the same production identity Interface."""

    def __init__(
        self,
        *,
        session_ttl: timedelta,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if session_ttl <= timedelta(0):
            raise ValueError("正式账号会话有效期必须大于 0。")
        self._session_ttl = session_ttl
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._accounts: dict[str, dict[str, object]] = {}
        self._owners: set[str] = set()
        self._sessions: dict[str, dict[str, object]] = {}

    def provision_personal_account(
        self, command: PersonalAccountProvision
    ) -> ProvisionedAccount:
        if command.email in self._accounts:
            raise AccountIdentityConflict("邮箱或 owner 已存在。")
        account_id = f"acct_{secrets.token_urlsafe(18)}"
        tenant_id = f"tenant_{secrets.token_urlsafe(18)}"
        owner_id = command.owner_id or account_id
        if owner_id in self._owners:
            raise AccountIdentityConflict("邮箱或 owner 已存在。")
        self._owners.add(owner_id)
        self._accounts[command.email] = {
            "account_id": account_id,
            "tenant_id": tenant_id,
            "owner_id": owner_id,
            "display_label": command.display_label,
            "password_hash": hash_password(command.password),
            "active": True,
        }
        return ProvisionedAccount(
            account_id=account_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
            role="personal_owner",
            display_label=command.display_label,
        )

    def authenticate(self, command: AccountLogin) -> AccountSessionGrant:
        account = self._accounts.get(command.email)
        password_valid = verify_password(
            command.password,
            str(account["password_hash"]) if account is not None else _DUMMY_PASSWORD_HASH,
        )
        if account is None or account["active"] is not True or not password_valid:
            raise AccountIdentityDenied("邮箱或密码无效。")
        token = secrets.token_urlsafe(48)
        expires_at = self._now() + self._session_ttl
        self._sessions[token] = {
            "account": account,
            "expires_at": expires_at,
            "revoked": False,
        }
        return AccountSessionGrant(
            token=token,
            identity=self._context(account, expires_at=expires_at),
        )

    def resolve(self, token: str) -> AccountIdentityContext:
        session = self._sessions.get(token)
        if session is None or session["revoked"] is True:
            raise AccountIdentityDenied("正式账号会话无效。")
        expires_at = session["expires_at"]
        if not isinstance(expires_at, datetime) or expires_at <= self._now():
            raise AccountIdentityDenied("正式账号会话已过期。")
        account = session["account"]
        if not isinstance(account, dict) or account["active"] is not True:
            raise AccountIdentityDenied("正式账号会话无效。")
        return self._context(account, expires_at=expires_at)

    def revoke(self, token: str) -> bool:
        session = self._sessions.get(token)
        if session is None or session["revoked"] is True:
            return False
        session["revoked"] = True
        return True

    def store_ready(self) -> bool:
        return True

    def _context(
        self, account: dict[str, object], *, expires_at: datetime
    ) -> AccountIdentityContext:
        return AccountIdentityContext(
            account_id=str(account["account_id"]),
            tenant_id=str(account["tenant_id"]),
            owner_id=str(account["owner_id"]),
            role="personal_owner",
            display_label=str(account["display_label"]),
            capabilities=list(ALL_WORKBENCH_CAPABILITIES),
            expires_at=expires_at,
        )

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise ValueError("AccountIdentity clock 必须返回带时区时间。")
        return value.astimezone(timezone.utc)
