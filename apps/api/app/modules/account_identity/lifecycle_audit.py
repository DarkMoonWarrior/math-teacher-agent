from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import stat
from collections.abc import Callable
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from app.modules.account_identity.contracts import (
    AccountAdministration,
    AccountLifecycleAudit,
    AccountLifecycleAuditError,
)
from app.modules.account_identity.schemas import (
    AccountDisable,
    AccountLifecycleReceipt,
    AccountPasswordReset,
    PersonalAccountProvision,
    ProvisionedAccount,
)


AuditAction = Literal["provision", "disable", "password_reset", "session_prune"]
_ACTIONS: tuple[AuditAction, ...] = (
    "provision",
    "disable",
    "password_reset",
    "session_prune",
)


class SqliteAccountLifecycleAudit:
    """Transitional append-first audit for operator account mutations.

    Raw operator labels and account hints never cross this boundary. Every
    mutation first persists a started event. A failed or interrupted completion
    remains visible as failed or started for operator investigation.
    """

    def __init__(
        self,
        *,
        database_path: Path,
        secret: str,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if len(secret) < 32:
            raise AccountLifecycleAuditError("ACCOUNT_AUDIT_UNAVAILABLE")
        self._path = database_path.absolute()
        self._secret = secret.encode("utf-8")
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._prepare_path()
        if self._path.exists():
            self._validate_existing_schema()
        self._initialize()

    def begin(
        self, *, action: str, operator_label: str, target_hint: str
    ) -> str:
        if action not in _ACTIONS:
            raise AccountLifecycleAuditError("ACCOUNT_AUDIT_ACTION_INVALID")
        operator = operator_label.strip().casefold()
        target = target_hint.strip().casefold()
        if not operator or len(operator) > 120 or not target or len(target) > 254:
            raise AccountLifecycleAuditError("ACCOUNT_AUDIT_SUBJECT_INVALID")
        event_id = f"aa_{secrets.token_urlsafe(18)}"
        try:
            with self._connect() as connection:
                connection.execute(
                    """INSERT INTO m14_account_lifecycle_audit
                       (event_id, action, outcome, operator_hash, target_hash,
                        started_at, finished_at, changed, affected_sessions)
                       VALUES (?, ?, 'started', ?, ?, ?, NULL, NULL, NULL)""",
                    (
                        event_id,
                        action,
                        self._digest("operator", operator),
                        self._digest("target", target),
                        self._now().isoformat(),
                    ),
                )
        except sqlite3.Error:
            raise AccountLifecycleAuditError("ACCOUNT_AUDIT_UNAVAILABLE") from None
        return event_id

    def succeed(
        self, *, event_id: str, changed: bool, affected_sessions: int
    ) -> None:
        if affected_sessions < 0:
            raise AccountLifecycleAuditError("ACCOUNT_AUDIT_RESULT_INVALID")
        self._finish(
            event_id=event_id,
            outcome="succeeded",
            changed=changed,
            affected_sessions=affected_sessions,
        )

    def fail(self, *, event_id: str) -> None:
        self._finish(
            event_id=event_id,
            outcome="failed",
            changed=False,
            affected_sessions=0,
        )

    def summary(self) -> dict[str, int]:
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    """SELECT action, outcome, COUNT(*)
                       FROM m14_account_lifecycle_audit
                       GROUP BY action, outcome"""
                ).fetchall()
        except sqlite3.Error:
            raise AccountLifecycleAuditError("ACCOUNT_AUDIT_UNAVAILABLE") from None
        result = {"total": sum(int(row[2]) for row in rows)}
        for action in _ACTIONS:
            for outcome in ("started", "succeeded", "failed"):
                result[f"{action}_{outcome}"] = 0
        for action, outcome, count in rows:
            result[f"{action}_{outcome}"] = int(count)
        return result

    def store_ready(self) -> bool:
        try:
            self._validate_existing_schema()
            return True
        except AccountLifecycleAuditError:
            return False

    def _finish(
        self,
        *,
        event_id: str,
        outcome: Literal["succeeded", "failed"],
        changed: bool,
        affected_sessions: int,
    ) -> None:
        try:
            with self._connect() as connection:
                updated = connection.execute(
                    """UPDATE m14_account_lifecycle_audit
                       SET outcome = ?, finished_at = ?, changed = ?,
                           affected_sessions = ?
                       WHERE event_id = ? AND outcome = 'started'""",
                    (
                        outcome,
                        self._now().isoformat(),
                        1 if changed else 0,
                        affected_sessions,
                        event_id,
                    ),
                ).rowcount
            if updated != 1:
                raise AccountLifecycleAuditError("ACCOUNT_AUDIT_EVENT_INVALID")
        except sqlite3.Error:
            raise AccountLifecycleAuditError("ACCOUNT_AUDIT_UNAVAILABLE") from None

    def _digest(self, scope: str, value: str) -> str:
        return hmac.new(
            self._secret,
            f"m14:account-audit:{scope}:{value}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise AccountLifecycleAuditError("ACCOUNT_AUDIT_CLOCK_INVALID")
        return value.astimezone(timezone.utc)

    def _prepare_path(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            for item in (self._path.parent, *self._path.parent.parents):
                info = item.lstat()
                if stat.S_ISLNK(info.st_mode) or (
                    getattr(info, "st_file_attributes", 0)
                    & stat.FILE_ATTRIBUTE_REPARSE_POINT
                ):
                    raise AccountLifecycleAuditError("ACCOUNT_AUDIT_PATH_UNSAFE")
            if self._path.exists():
                info = self._path.lstat()
                if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode) or (
                    getattr(info, "st_file_attributes", 0)
                    & stat.FILE_ATTRIBUTE_REPARSE_POINT
                ):
                    raise AccountLifecycleAuditError("ACCOUNT_AUDIT_PATH_UNSAFE")
        except OSError:
            raise AccountLifecycleAuditError("ACCOUNT_AUDIT_UNAVAILABLE") from None

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)

    def _validate_existing_schema(self) -> None:
        try:
            with closing(
                sqlite3.connect(f"{self._path.as_uri()}?mode=ro", uri=True)
            ) as connection:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master "
                        "WHERE type='table' AND name NOT GLOB 'sqlite_*'"
                    ).fetchall()
                }
                column_rows = connection.execute(
                    "PRAGMA table_info(m14_account_lifecycle_audit)"
                ).fetchall()
                triggers = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='trigger'"
                ).fetchone()
            columns = {row[1] for row in column_rows}
            event_id_is_primary = any(
                row[1] == "event_id" and row[5] == 1 for row in column_rows
            )
            if (
                tables != {"m14_account_lifecycle_audit"}
                or columns
                != {
                    "event_id",
                    "action",
                    "outcome",
                    "operator_hash",
                    "target_hash",
                    "started_at",
                    "finished_at",
                    "changed",
                    "affected_sessions",
                }
                or not event_id_is_primary
                or triggers is not None
            ):
                raise AccountLifecycleAuditError("ACCOUNT_AUDIT_SCHEMA_UNEXPECTED")
        except sqlite3.Error:
            raise AccountLifecycleAuditError("ACCOUNT_AUDIT_UNAVAILABLE") from None

    def _initialize(self) -> None:
        try:
            with self._connect() as connection:
                connection.executescript(
                    """
                    PRAGMA journal_mode = WAL;
                    CREATE TABLE IF NOT EXISTS m14_account_lifecycle_audit (
                        event_id TEXT PRIMARY KEY,
                        action TEXT NOT NULL CHECK (
                            action IN ('provision', 'disable', 'password_reset',
                                       'session_prune')
                        ),
                        outcome TEXT NOT NULL CHECK (
                            outcome IN ('started', 'succeeded', 'failed')
                        ),
                        operator_hash TEXT NOT NULL,
                        target_hash TEXT NOT NULL,
                        started_at TEXT NOT NULL,
                        finished_at TEXT,
                        changed INTEGER CHECK (changed IN (0, 1)),
                        affected_sessions INTEGER CHECK (affected_sessions >= 0)
                    );
                    CREATE INDEX IF NOT EXISTS idx_m14_account_audit_action_time
                        ON m14_account_lifecycle_audit (action, started_at);
                    """
                )
        except sqlite3.Error:
            raise AccountLifecycleAuditError("ACCOUNT_AUDIT_UNAVAILABLE") from None


class AuditedAccountAdministration:
    """Records a durable audit intent before delegating account mutations."""

    def __init__(
        self,
        *,
        administration: AccountAdministration,
        audit: AccountLifecycleAudit,
        operator_label: str,
    ) -> None:
        self._administration = administration
        self._audit = audit
        self._operator_label = operator_label

    def provision_personal_account(
        self, command: PersonalAccountProvision
    ) -> ProvisionedAccount:
        event_id = self._audit.begin(
            action="provision",
            operator_label=self._operator_label,
            target_hint=command.email,
        )
        try:
            result = self._administration.provision_personal_account(command)
        except Exception:
            self._audit.fail(event_id=event_id)
            raise
        self._audit.succeed(event_id=event_id, changed=True, affected_sessions=0)
        return result

    def disable_account(
        self, command: AccountDisable, *, confirmed: bool = False
    ) -> AccountLifecycleReceipt:
        event_id = self._audit.begin(
            action="disable",
            operator_label=self._operator_label,
            target_hint=command.email,
        )
        try:
            result = self._administration.disable_account(command, confirmed=confirmed)
        except Exception:
            self._audit.fail(event_id=event_id)
            raise
        self._audit.succeed(
            event_id=event_id,
            changed=result.changed,
            affected_sessions=result.revoked_sessions,
        )
        return result

    def reset_password(
        self, command: AccountPasswordReset, *, confirmed: bool = False
    ) -> AccountLifecycleReceipt:
        event_id = self._audit.begin(
            action="password_reset",
            operator_label=self._operator_label,
            target_hint=command.email,
        )
        try:
            result = self._administration.reset_password(command, confirmed=confirmed)
        except Exception:
            self._audit.fail(event_id=event_id)
            raise
        self._audit.succeed(
            event_id=event_id,
            changed=result.changed,
            affected_sessions=result.revoked_sessions,
        )
        return result
