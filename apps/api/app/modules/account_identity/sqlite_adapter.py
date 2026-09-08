from __future__ import annotations

import json
import secrets
import sqlite3
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.core.capabilities import ALL_WORKBENCH_CAPABILITIES
from app.modules.account_identity.contracts import (
    AccountAdministrationError,
    AccountIdentityConflict,
    AccountIdentityDenied,
)
from app.modules.account_identity.crypto import (
    hash_password,
    hash_session_token,
    verify_password,
)
from app.modules.account_identity.schemas import (
    AccountDisable,
    AccountIdentityContext,
    AccountLifecycleReceipt,
    AccountLogin,
    AccountPasswordReset,
    AccountSessionGrant,
    PersonalAccountProvision,
    ProvisionedAccount,
)


_DUMMY_PASSWORD_HASH = hash_password(
    "not-a-real-account-password", salt=b"m14-dummy-login"
)


class SqliteAccountIdentity:
    """Local persistent adapter for the M14 identity Interface.

    This proves the account/tenant/owner seam without claiming SQLite is the
    production database. PostgreSQL is a later adapter.
    """

    def __init__(
        self,
        *,
        database_path: Path,
        session_ttl: timedelta,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if session_ttl <= timedelta(0):
            raise ValueError("正式账号会话有效期必须大于 0。")
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._session_ttl = session_ttl
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._initialize()

    def provision_personal_account(
        self, command: PersonalAccountProvision
    ) -> ProvisionedAccount:
        now = self._now()
        account_id = f"acct_{secrets.token_urlsafe(18)}"
        tenant_id = f"tenant_{secrets.token_urlsafe(18)}"
        owner_id = command.owner_id or account_id
        capabilities = list(ALL_WORKBENCH_CAPABILITIES)
        try:
            with self._connect() as connection:
                connection.execute(
                    """INSERT INTO m14_accounts
                       (account_id, email_normalized, password_hash, display_label,
                        status, created_at)
                       VALUES (?, ?, ?, ?, 'active', ?)""",
                    (
                        account_id,
                        command.email,
                        hash_password(command.password),
                        command.display_label,
                        now.isoformat(),
                    ),
                )
                connection.execute(
                    """INSERT INTO m14_tenants (tenant_id, tenant_kind, created_at)
                       VALUES (?, 'personal', ?)""",
                    (tenant_id, now.isoformat()),
                )
                connection.execute(
                    """INSERT INTO m14_memberships
                       (account_id, tenant_id, owner_id, role, capabilities_json, active)
                       VALUES (?, ?, ?, 'personal_owner', ?, 1)""",
                    (
                        account_id,
                        tenant_id,
                        owner_id,
                        json.dumps(capabilities, ensure_ascii=False),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise AccountIdentityConflict("邮箱或 owner 已存在。") from exc
        return ProvisionedAccount(
            account_id=account_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
            role="personal_owner",
            display_label=command.display_label,
        )

    def authenticate(self, command: AccountLogin) -> AccountSessionGrant:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT a.account_id, a.password_hash, a.display_label, a.status,
                          m.tenant_id, m.owner_id, m.role, m.capabilities_json, m.active
                   FROM m14_accounts AS a
                   JOIN m14_memberships AS m ON m.account_id = a.account_id
                   WHERE a.email_normalized = ?""",
                (command.email,),
            ).fetchone()
        password_valid = verify_password(
            command.password,
            row["password_hash"] if row is not None else _DUMMY_PASSWORD_HASH,
        )
        if (
            row is None
            or row["status"] != "active"
            or row["active"] != 1
            or not password_valid
        ):
            raise AccountIdentityDenied("邮箱或密码无效。")

        now = self._now()
        expires_at = now + self._session_ttl
        token = secrets.token_urlsafe(48)
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO m14_account_sessions
                   (token_hash, account_id, tenant_id, created_at, expires_at, revoked_at)
                   VALUES (?, ?, ?, ?, ?, NULL)""",
                (
                    hash_session_token(token),
                    row["account_id"],
                    row["tenant_id"],
                    now.isoformat(),
                    expires_at.isoformat(),
                ),
            )
        return AccountSessionGrant(
            token=token,
            identity=self._context(row, expires_at=expires_at),
        )

    def resolve(self, token: str) -> AccountIdentityContext:
        if not token:
            raise AccountIdentityDenied("正式账号会话不存在。")
        with self._connect() as connection:
            row = connection.execute(
                """SELECT s.expires_at, s.revoked_at,
                          a.account_id, a.display_label, a.status,
                          m.tenant_id, m.owner_id, m.role, m.capabilities_json, m.active
                   FROM m14_account_sessions AS s
                   JOIN m14_accounts AS a ON a.account_id = s.account_id
                   JOIN m14_memberships AS m
                     ON m.account_id = s.account_id AND m.tenant_id = s.tenant_id
                   WHERE s.token_hash = ?""",
                (hash_session_token(token),),
            ).fetchone()
        if (
            row is None
            or row["revoked_at"] is not None
            or row["status"] != "active"
            or row["active"] != 1
        ):
            raise AccountIdentityDenied("正式账号会话无效。")
        expires_at = datetime.fromisoformat(row["expires_at"])
        if expires_at <= self._now():
            raise AccountIdentityDenied("正式账号会话已过期。")
        return self._context(row, expires_at=expires_at)

    def revoke(self, token: str) -> bool:
        if not token:
            return False
        with self._connect() as connection:
            changed = connection.execute(
                """UPDATE m14_account_sessions SET revoked_at = ?
                   WHERE token_hash = ? AND revoked_at IS NULL""",
                (self._now().isoformat(), hash_session_token(token)),
            ).rowcount
        return changed > 0

    def store_ready(self) -> bool:
        try:
            with self._connect() as connection:
                return connection.execute("SELECT 1").fetchone()[0] == 1
        except sqlite3.Error:
            return False

    def disable_account(
        self, command: AccountDisable, *, confirmed: bool = False
    ) -> AccountLifecycleReceipt:
        if confirmed is not True:
            raise AccountAdministrationError("ACCOUNT_DISABLE_CONFIRMATION_REQUIRED")
        now = self._now().isoformat()
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT account_id, status FROM m14_accounts WHERE email_normalized = ?",
                    (command.email,),
                ).fetchone()
                if row is None or row["status"] != "active":
                    raise AccountAdministrationError("ACCOUNT_NOT_ACTIVE")
                connection.execute(
                    "UPDATE m14_accounts SET status = 'disabled' WHERE account_id = ?",
                    (row["account_id"],),
                )
                revoked = connection.execute(
                    """UPDATE m14_account_sessions SET revoked_at = ?
                       WHERE account_id = ? AND revoked_at IS NULL""",
                    (now, row["account_id"]),
                ).rowcount
        except sqlite3.Error:
            raise AccountAdministrationError("ACCOUNT_STORE_UNAVAILABLE") from None
        return AccountLifecycleReceipt(
            action="disabled", changed=True, revoked_sessions=revoked
        )

    def reset_password(
        self, command: AccountPasswordReset, *, confirmed: bool = False
    ) -> AccountLifecycleReceipt:
        if confirmed is not True:
            raise AccountAdministrationError("PASSWORD_RESET_CONFIRMATION_REQUIRED")
        now = self._now().isoformat()
        password_hash = hash_password(command.new_password)
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT account_id, status FROM m14_accounts WHERE email_normalized = ?",
                    (command.email,),
                ).fetchone()
                if row is None or row["status"] != "active":
                    raise AccountAdministrationError("ACCOUNT_NOT_ACTIVE")
                connection.execute(
                    "UPDATE m14_accounts SET password_hash = ? WHERE account_id = ?",
                    (password_hash, row["account_id"]),
                )
                revoked = connection.execute(
                    """UPDATE m14_account_sessions SET revoked_at = ?
                       WHERE account_id = ? AND revoked_at IS NULL""",
                    (now, row["account_id"]),
                ).rowcount
        except sqlite3.Error:
            raise AccountAdministrationError("ACCOUNT_STORE_UNAVAILABLE") from None
        return AccountLifecycleReceipt(
            action="password_reset", changed=True, revoked_sessions=revoked
        )

    def _context(self, row: sqlite3.Row, *, expires_at: datetime) -> AccountIdentityContext:
        return AccountIdentityContext(
            account_id=row["account_id"],
            tenant_id=row["tenant_id"],
            owner_id=row["owner_id"],
            role=row["role"],
            display_label=row["display_label"],
            capabilities=json.loads(row["capabilities_json"]),
            expires_at=expires_at,
        )

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise ValueError("AccountIdentity clock 必须返回带时区时间。")
        return value.astimezone(timezone.utc)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS m14_accounts (
                    account_id TEXT PRIMARY KEY,
                    email_normalized TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    display_label TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('active', 'disabled')),
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS m14_tenants (
                    tenant_id TEXT PRIMARY KEY,
                    tenant_kind TEXT NOT NULL CHECK (tenant_kind = 'personal'),
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS m14_memberships (
                    account_id TEXT NOT NULL REFERENCES m14_accounts(account_id),
                    tenant_id TEXT NOT NULL REFERENCES m14_tenants(tenant_id),
                    owner_id TEXT NOT NULL UNIQUE,
                    role TEXT NOT NULL CHECK (role = 'personal_owner'),
                    capabilities_json TEXT NOT NULL,
                    active INTEGER NOT NULL CHECK (active IN (0, 1)),
                    PRIMARY KEY (account_id, tenant_id)
                );
                CREATE TABLE IF NOT EXISTS m14_account_sessions (
                    token_hash TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL REFERENCES m14_accounts(account_id),
                    tenant_id TEXT NOT NULL REFERENCES m14_tenants(tenant_id),
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    revoked_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_m14_sessions_account_expiry
                    ON m14_account_sessions (account_id, expires_at);
                """
            )
