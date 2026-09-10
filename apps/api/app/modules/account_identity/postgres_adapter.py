from __future__ import annotations

import hashlib
import json
import secrets
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from app.core.capabilities import ALL_WORKBENCH_CAPABILITIES
from app.modules.account_identity.contracts import (
    AccountAdministrationError,
    AccountIdentityConflict,
    AccountIdentityDenied,
    AccountIdentityUnavailable,
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
    PersonalAccountRegistration,
    PersonalAccountProvision,
    ProvisionedAccount,
)


POSTGRES_IDENTITY_SCHEMA = "math_teacher_identity"
POSTGRES_IDENTITY_SCHEMA_VERSION = "m14.identity.v1"
_SCHEMA_TABLE = f"{POSTGRES_IDENTITY_SCHEMA}.schema_versions"
_ACCOUNTS = f"{POSTGRES_IDENTITY_SCHEMA}.accounts"
_TENANTS = f"{POSTGRES_IDENTITY_SCHEMA}.tenants"
_MEMBERSHIPS = f"{POSTGRES_IDENTITY_SCHEMA}.memberships"
_SESSIONS = f"{POSTGRES_IDENTITY_SCHEMA}.account_sessions"
_DUMMY_PASSWORD_HASH = hash_password(
    "not-a-real-account-password", salt=b"m14-postgres-dummy-login"
)


class _Cursor(Protocol):
    rowcount: int

    def fetchone(self) -> Mapping[str, Any] | None: ...


class _Connection(Protocol):
    def __enter__(self) -> "_Connection": ...

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None: ...

    def execute(
        self, query: str, params: Sequence[Any] | None = None
    ) -> _Cursor: ...


Connect = Callable[[], _Connection]


def _psycopg_connect(dsn: str) -> _Connection:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise AccountIdentityUnavailable("POSTGRES_DRIVER_UNAVAILABLE") from exc
    try:
        return psycopg.connect(dsn, row_factory=dict_row)
    except Exception as exc:
        raise AccountIdentityUnavailable("POSTGRES_CONNECTION_UNAVAILABLE") from exc


POSTGRES_IDENTITY_SCHEMA_STATEMENTS = (
    f"CREATE SCHEMA IF NOT EXISTS {POSTGRES_IDENTITY_SCHEMA}",
    f"""CREATE TABLE IF NOT EXISTS {_SCHEMA_TABLE} (
        component TEXT PRIMARY KEY,
        schema_version TEXT NOT NULL,
        installed_at TIMESTAMPTZ NOT NULL
    )""",
    f"""CREATE TABLE IF NOT EXISTS {_ACCOUNTS} (
        account_id TEXT PRIMARY KEY,
        email_normalized TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        display_label TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('active', 'disabled')),
        created_at TIMESTAMPTZ NOT NULL
    )""",
    f"""CREATE TABLE IF NOT EXISTS {_TENANTS} (
        tenant_id TEXT PRIMARY KEY,
        tenant_kind TEXT NOT NULL CHECK (tenant_kind = 'personal'),
        created_at TIMESTAMPTZ NOT NULL
    )""",
    f"""CREATE TABLE IF NOT EXISTS {_MEMBERSHIPS} (
        account_id TEXT NOT NULL REFERENCES {_ACCOUNTS}(account_id),
        tenant_id TEXT NOT NULL REFERENCES {_TENANTS}(tenant_id),
        owner_id TEXT NOT NULL UNIQUE,
        role TEXT NOT NULL CHECK (role = 'personal_owner'),
        capabilities_json JSONB NOT NULL,
        active BOOLEAN NOT NULL,
        PRIMARY KEY (account_id, tenant_id)
    )""",
    f"""CREATE TABLE IF NOT EXISTS {_SESSIONS} (
        token_hash TEXT PRIMARY KEY,
        account_id TEXT NOT NULL REFERENCES {_ACCOUNTS}(account_id),
        tenant_id TEXT NOT NULL REFERENCES {_TENANTS}(tenant_id),
        created_at TIMESTAMPTZ NOT NULL,
        expires_at TIMESTAMPTZ NOT NULL,
        revoked_at TIMESTAMPTZ
    )""",
    f"""CREATE INDEX IF NOT EXISTS account_sessions_account_expiry_idx
        ON {_SESSIONS} (account_id, expires_at)""",
    f"""INSERT INTO {_SCHEMA_TABLE}
        (component, schema_version, installed_at)
        VALUES ('account_identity', %s, %s)
        ON CONFLICT (component) DO NOTHING""",
)


class PostgresIdentitySchemaError(ValueError):
    """Stable operator error without exposing the target DSN."""


@dataclass(frozen=True)
class PostgresIdentitySchemaPlan:
    state: str
    schema_version: str
    statement_count: int
    fingerprint: str
    changed: bool = False


class PostgresAccountIdentitySchema:
    """Explicit schema deployment boundary; construction never mutates PostgreSQL."""

    def __init__(self, *, connect: Connect) -> None:
        self._connect = connect

    @classmethod
    def from_dsn(cls, dsn: str) -> "PostgresAccountIdentitySchema":
        if not dsn.strip():
            raise PostgresIdentitySchemaError("POSTGRES_IDENTITY_DSN_REQUIRED")
        return cls(connect=lambda: _psycopg_connect(dsn))

    @staticmethod
    def _fingerprint() -> str:
        encoded = "\n".join(POSTGRES_IDENTITY_SCHEMA_STATEMENTS).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def preview(self) -> PostgresIdentitySchemaPlan:
        try:
            with self._connect() as connection:
                state = _schema_state(connection)
        except AccountIdentityUnavailable as exc:
            raise PostgresIdentitySchemaError("POSTGRES_IDENTITY_TARGET_UNAVAILABLE") from exc
        except Exception as exc:
            raise PostgresIdentitySchemaError("POSTGRES_IDENTITY_TARGET_UNAVAILABLE") from exc
        return PostgresIdentitySchemaPlan(
            state=state,
            schema_version=POSTGRES_IDENTITY_SCHEMA_VERSION,
            statement_count=len(POSTGRES_IDENTITY_SCHEMA_STATEMENTS),
            fingerprint=self._fingerprint(),
        )

    def apply(
        self, *, expected_fingerprint: str, confirmed: bool = False
    ) -> PostgresIdentitySchemaPlan:
        if confirmed is not True:
            raise PostgresIdentitySchemaError(
                "POSTGRES_IDENTITY_SCHEMA_CONFIRMATION_REQUIRED"
            )
        if not secrets.compare_digest(expected_fingerprint, self._fingerprint()):
            raise PostgresIdentitySchemaError("POSTGRES_IDENTITY_SCHEMA_PLAN_CHANGED")
        try:
            with self._connect() as connection:
                # Serialize schema deployment for this component. The lock is
                # transaction-scoped and cannot leak into later connections.
                connection.execute("SELECT pg_advisory_xact_lock(%s)", (1414001,))
                state = _schema_state(connection)
                plan = PostgresIdentitySchemaPlan(
                    state=state,
                    schema_version=POSTGRES_IDENTITY_SCHEMA_VERSION,
                    statement_count=len(POSTGRES_IDENTITY_SCHEMA_STATEMENTS),
                    fingerprint=self._fingerprint(),
                )
                if state == "unexpected":
                    raise PostgresIdentitySchemaError(
                        "POSTGRES_IDENTITY_SCHEMA_UNEXPECTED"
                    )
                if state == "current":
                    return plan
                now = datetime.now(timezone.utc)
                for statement in POSTGRES_IDENTITY_SCHEMA_STATEMENTS[:-1]:
                    connection.execute(statement)
                connection.execute(
                    POSTGRES_IDENTITY_SCHEMA_STATEMENTS[-1],
                    (POSTGRES_IDENTITY_SCHEMA_VERSION, now),
                )
        except PostgresIdentitySchemaError:
            raise
        except Exception as exc:
            raise PostgresIdentitySchemaError("POSTGRES_IDENTITY_SCHEMA_APPLY_FAILED") from exc
        return PostgresIdentitySchemaPlan(**{**plan.__dict__, "changed": True})


class PostgresAccountIdentity:
    """PostgreSQL adapter for the unchanged M14 AccountIdentity Interface.

    The adapter never installs or migrates schema during construction. Operators
    must deploy the exact schema plan separately before enabling this backend.
    """

    def __init__(
        self,
        *,
        dsn: str,
        session_ttl: timedelta,
        clock: Callable[[], datetime] | None = None,
        connect: Connect | None = None,
    ) -> None:
        if session_ttl <= timedelta(0):
            raise ValueError("正式账号会话有效期必须大于 0。")
        if not dsn.strip() and connect is None:
            raise ValueError("PostgreSQL DSN 不能为空。")
        self._session_ttl = session_ttl
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._connect = connect or (lambda: _psycopg_connect(dsn))

    def provision_personal_account(
        self, command: PersonalAccountProvision
    ) -> ProvisionedAccount:
        now = self._now()
        account_id = f"acct_{secrets.token_urlsafe(18)}"
        tenant_id = f"tenant_{secrets.token_urlsafe(18)}"
        owner_id = command.owner_id or account_id
        try:
            with self._connect() as connection:
                self._insert_personal_account(
                    connection,
                    command=command,
                    account_id=account_id,
                    tenant_id=tenant_id,
                    owner_id=owner_id,
                    now=now,
                )
        except Exception as exc:
            if getattr(exc, "sqlstate", None) == "23505":
                raise AccountIdentityConflict("邮箱或 owner 已存在。") from exc
            raise AccountIdentityUnavailable("POSTGRES_IDENTITY_WRITE_UNAVAILABLE") from exc
        return ProvisionedAccount(
            account_id=account_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
            role="personal_owner",
            display_label=command.display_label,
        )

    def authenticate(self, command: AccountLogin) -> AccountSessionGrant:
        row = self._login_row(command.email)
        password_valid = verify_password(
            command.password,
            str(row["password_hash"]) if row is not None else _DUMMY_PASSWORD_HASH,
        )
        if (
            row is None
            or row.get("status") != "active"
            or row.get("active") is not True
            or not password_valid
        ):
            raise AccountIdentityDenied("邮箱或密码无效。")
        now = self._now()
        expires_at = now + self._session_ttl
        token = secrets.token_urlsafe(48)
        try:
            with self._connect() as connection:
                connection.execute(
                    f"""INSERT INTO {_SESSIONS}
                    (token_hash, account_id, tenant_id, created_at, expires_at, revoked_at)
                    VALUES (%s, %s, %s, %s, %s, NULL)""",
                    (
                        hash_session_token(token),
                        row["account_id"],
                        row["tenant_id"],
                        now,
                        expires_at,
                    ),
                )
        except Exception as exc:
            raise AccountIdentityUnavailable("POSTGRES_SESSION_WRITE_UNAVAILABLE") from exc
        return AccountSessionGrant(
            token=token,
            identity=self._context(row, expires_at=expires_at),
        )

    def register_personal_account(
        self, command: PersonalAccountRegistration
    ) -> AccountSessionGrant:
        account_id = f"acct_{secrets.token_urlsafe(18)}"
        tenant_id = f"tenant_{secrets.token_urlsafe(18)}"
        owner_id = f"owner_{secrets.token_urlsafe(18)}"
        now = self._now()
        expires_at = now + self._session_ttl
        token = secrets.token_urlsafe(48)
        provision = PersonalAccountProvision(
            email=command.email,
            password=command.password,
            display_label=command.display_label,
            owner_id=owner_id,
        )
        try:
            # Account, tenant, membership and first session either all commit or
            # all roll back. A failed session write cannot strand a new account.
            with self._connect() as connection:
                self._insert_personal_account(
                    connection,
                    command=provision,
                    account_id=account_id,
                    tenant_id=tenant_id,
                    owner_id=owner_id,
                    now=now,
                )
                connection.execute(
                    f"""INSERT INTO {_SESSIONS}
                    (token_hash, account_id, tenant_id, created_at, expires_at, revoked_at)
                    VALUES (%s, %s, %s, %s, %s, NULL)""",
                    (
                        hash_session_token(token),
                        account_id,
                        tenant_id,
                        now,
                        expires_at,
                    ),
                )
        except Exception as exc:
            if getattr(exc, "sqlstate", None) == "23505":
                raise AccountIdentityConflict("邮箱或 owner 已存在。") from exc
            raise AccountIdentityUnavailable("POSTGRES_IDENTITY_WRITE_UNAVAILABLE") from exc
        return AccountSessionGrant(
            token=token,
            identity=AccountIdentityContext(
                account_id=account_id,
                tenant_id=tenant_id,
                owner_id=owner_id,
                role="personal_owner",
                display_label=command.display_label,
                capabilities=list(ALL_WORKBENCH_CAPABILITIES),
                expires_at=expires_at,
            ),
        )

    def resolve(self, token: str) -> AccountIdentityContext:
        if not token:
            raise AccountIdentityDenied("正式账号会话不存在。")
        try:
            with self._connect() as connection:
                row = connection.execute(
                    f"""SELECT s.expires_at, s.revoked_at,
                    a.account_id, a.display_label, a.status,
                    m.tenant_id, m.owner_id, m.role, m.capabilities_json, m.active
                    FROM {_SESSIONS} AS s
                    JOIN {_ACCOUNTS} AS a ON a.account_id = s.account_id
                    JOIN {_MEMBERSHIPS} AS m
                      ON m.account_id = s.account_id AND m.tenant_id = s.tenant_id
                    WHERE s.token_hash = %s""",
                    (hash_session_token(token),),
                ).fetchone()
        except Exception as exc:
            raise AccountIdentityUnavailable("POSTGRES_IDENTITY_READ_UNAVAILABLE") from exc
        if (
            row is None
            or row.get("revoked_at") is not None
            or row.get("status") != "active"
            or row.get("active") is not True
        ):
            raise AccountIdentityDenied("正式账号会话无效。")
        expires_at = self._datetime(row.get("expires_at"))
        if expires_at <= self._now():
            raise AccountIdentityDenied("正式账号会话已过期。")
        return self._context(row, expires_at=expires_at)

    def revoke(self, token: str) -> bool:
        if not token:
            return False
        try:
            with self._connect() as connection:
                changed = connection.execute(
                    f"""UPDATE {_SESSIONS} SET revoked_at = %s
                    WHERE token_hash = %s AND revoked_at IS NULL""",
                    (self._now(), hash_session_token(token)),
                ).rowcount
        except Exception as exc:
            raise AccountIdentityUnavailable("POSTGRES_SESSION_WRITE_UNAVAILABLE") from exc
        return changed > 0

    def store_ready(self) -> bool:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    f"SELECT schema_version FROM {_SCHEMA_TABLE} WHERE component = %s",
                    ("account_identity",),
                ).fetchone()
                if (
                    row is None
                    or row.get("schema_version") != POSTGRES_IDENTITY_SCHEMA_VERSION
                ):
                    return False
                _validate_schema_shape(connection)
            return True
        except Exception:
            return False

    def disable_account(
        self, command: AccountDisable, *, confirmed: bool = False
    ) -> AccountLifecycleReceipt:
        if confirmed is not True:
            raise AccountAdministrationError("ACCOUNT_DISABLE_CONFIRMATION_REQUIRED")
        now = self._now()
        try:
            with self._connect() as connection:
                row = connection.execute(
                    f"SELECT account_id, status FROM {_ACCOUNTS} "
                    "WHERE email_normalized = %s FOR UPDATE",
                    (command.email,),
                ).fetchone()
                if row is None or row.get("status") != "active":
                    raise AccountAdministrationError("ACCOUNT_NOT_ACTIVE")
                connection.execute(
                    f"UPDATE {_ACCOUNTS} SET status = 'disabled' WHERE account_id = %s",
                    (row["account_id"],),
                )
                revoked = connection.execute(
                    f"""UPDATE {_SESSIONS} SET revoked_at = %s
                    WHERE account_id = %s AND revoked_at IS NULL""",
                    (now, row["account_id"]),
                ).rowcount
        except AccountAdministrationError:
            raise
        except Exception as exc:
            raise AccountAdministrationError("ACCOUNT_STORE_UNAVAILABLE") from exc
        return AccountLifecycleReceipt(
            action="disabled", changed=True, revoked_sessions=revoked
        )

    def reset_password(
        self, command: AccountPasswordReset, *, confirmed: bool = False
    ) -> AccountLifecycleReceipt:
        if confirmed is not True:
            raise AccountAdministrationError("PASSWORD_RESET_CONFIRMATION_REQUIRED")
        now = self._now()
        try:
            with self._connect() as connection:
                row = connection.execute(
                    f"SELECT account_id, status FROM {_ACCOUNTS} "
                    "WHERE email_normalized = %s FOR UPDATE",
                    (command.email,),
                ).fetchone()
                if row is None or row.get("status") != "active":
                    raise AccountAdministrationError("ACCOUNT_NOT_ACTIVE")
                connection.execute(
                    f"UPDATE {_ACCOUNTS} SET password_hash = %s WHERE account_id = %s",
                    (hash_password(command.new_password), row["account_id"]),
                )
                revoked = connection.execute(
                    f"""UPDATE {_SESSIONS} SET revoked_at = %s
                    WHERE account_id = %s AND revoked_at IS NULL""",
                    (now, row["account_id"]),
                ).rowcount
        except AccountAdministrationError:
            raise
        except Exception as exc:
            raise AccountAdministrationError("ACCOUNT_STORE_UNAVAILABLE") from exc
        return AccountLifecycleReceipt(
            action="password_reset", changed=True, revoked_sessions=revoked
        )

    def _login_row(self, email: str) -> Mapping[str, Any] | None:
        try:
            with self._connect() as connection:
                return connection.execute(
                    f"""SELECT a.account_id, a.password_hash, a.display_label, a.status,
                    m.tenant_id, m.owner_id, m.role, m.capabilities_json, m.active
                    FROM {_ACCOUNTS} AS a
                    JOIN {_MEMBERSHIPS} AS m ON m.account_id = a.account_id
                    WHERE a.email_normalized = %s""",
                    (email,),
                ).fetchone()
        except Exception as exc:
            raise AccountIdentityUnavailable("POSTGRES_IDENTITY_READ_UNAVAILABLE") from exc

    @staticmethod
    def _insert_personal_account(
        connection: _Connection,
        *,
        command: PersonalAccountProvision,
        account_id: str,
        tenant_id: str,
        owner_id: str,
        now: datetime,
    ) -> None:
        connection.execute(
            f"""INSERT INTO {_ACCOUNTS}
            (account_id, email_normalized, password_hash, display_label,
             status, created_at) VALUES (%s, %s, %s, %s, 'active', %s)""",
            (
                account_id,
                command.email,
                hash_password(command.password),
                command.display_label,
                now,
            ),
        )
        connection.execute(
            f"""INSERT INTO {_TENANTS}
            (tenant_id, tenant_kind, created_at)
            VALUES (%s, 'personal', %s)""",
            (tenant_id, now),
        )
        connection.execute(
            f"""INSERT INTO {_MEMBERSHIPS}
            (account_id, tenant_id, owner_id, role, capabilities_json, active)
            VALUES (%s, %s, %s, 'personal_owner', %s::jsonb, TRUE)""",
            (
                account_id,
                tenant_id,
                owner_id,
                json.dumps(ALL_WORKBENCH_CAPABILITIES, ensure_ascii=False),
            ),
        )

    def _context(
        self, row: Mapping[str, Any], *, expires_at: datetime
    ) -> AccountIdentityContext:
        capabilities = row.get("capabilities_json", [])
        if isinstance(capabilities, str):
            capabilities = json.loads(capabilities)
        return AccountIdentityContext(
            account_id=str(row["account_id"]),
            tenant_id=str(row["tenant_id"]),
            owner_id=str(row["owner_id"]),
            role=str(row["role"]),
            display_label=str(row["display_label"]),
            capabilities=list(capabilities),
            expires_at=expires_at,
        )

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("AccountIdentity clock 必须返回带时区时间。")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _datetime(value: Any) -> datetime:
        if isinstance(value, datetime):
            result = value
        elif isinstance(value, str):
            result = datetime.fromisoformat(value)
        else:
            raise AccountIdentityUnavailable("POSTGRES_IDENTITY_TIME_INVALID")
        if result.tzinfo is None or result.utcoffset() is None:
            raise AccountIdentityUnavailable("POSTGRES_IDENTITY_TIME_INVALID")
        return result.astimezone(timezone.utc)


def _validate_schema_shape(connection: _Connection) -> None:
    """Read expected columns without returning identity data."""

    connection.execute(
        f"""SELECT account_id, email_normalized, password_hash, display_label,
        status, created_at FROM {_ACCOUNTS} WHERE FALSE"""
    )
    connection.execute(
        f"SELECT tenant_id, tenant_kind, created_at FROM {_TENANTS} WHERE FALSE"
    )
    connection.execute(
        f"""SELECT account_id, tenant_id, owner_id, role, capabilities_json, active
        FROM {_MEMBERSHIPS} WHERE FALSE"""
    )
    connection.execute(
        f"""SELECT token_hash, account_id, tenant_id, created_at, expires_at, revoked_at
        FROM {_SESSIONS} WHERE FALSE"""
    )


def _schema_state(connection: _Connection) -> str:
    marker = connection.execute(
        "SELECT to_regclass(%s) AS metadata_table",
        (f"{POSTGRES_IDENTITY_SCHEMA}.schema_versions",),
    ).fetchone()
    if marker is None or marker.get("metadata_table") is None:
        table_count = connection.execute(
            "SELECT COUNT(*) AS table_count FROM information_schema.tables "
            "WHERE table_schema = %s",
            (POSTGRES_IDENTITY_SCHEMA,),
        ).fetchone()
        return (
            "empty"
            if table_count is not None and table_count.get("table_count") == 0
            else "unexpected"
        )
    row = connection.execute(
        f"SELECT schema_version FROM {_SCHEMA_TABLE} WHERE component = %s",
        ("account_identity",),
    ).fetchone()
    if row is None or row.get("schema_version") != POSTGRES_IDENTITY_SCHEMA_VERSION:
        return "unexpected"
    try:
        _validate_schema_shape(connection)
    except Exception:
        return "unexpected"
    return "current"
