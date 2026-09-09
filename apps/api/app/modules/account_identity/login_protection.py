from __future__ import annotations

import hashlib
import hmac
import sqlite3
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from app.modules.account_identity.contracts import (
    AccountLoginProtectionUnavailable,
    AccountLoginRateLimited,
)


LoginOutcome = Literal["succeeded", "failed", "throttled"]


class SqliteAccountLoginProtection:
    """Bounded SQLite adapter for privacy-safe login throttling and audit facts.

    Only keyed digests, an allow-listed outcome and time are persisted. This is
    a replaceable application-layer control; a production edge must also limit
    traffic before it reaches the application.
    """

    def __init__(
        self,
        *,
        database_path: Path,
        secret: str,
        window: timedelta,
        principal_attempts: int,
        network_attempts: int,
        retention: timedelta,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if len(secret) < 32:
            raise AccountLoginProtectionUnavailable("LOGIN_PROTECTION_UNAVAILABLE")
        if window <= timedelta(0) or retention < window:
            raise ValueError("登录防护窗口或保留期无效。")
        if principal_attempts < 2 or network_attempts < principal_attempts:
            raise ValueError("登录防护阈值无效。")
        self._path = database_path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._secret = secret.encode("utf-8")
        self._window = window
        self._principal_attempts = principal_attempts
        self._network_attempts = network_attempts
        self._retention = retention
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._initialize()

    def assess(self, *, email: str, network_origin: str) -> None:
        principal_hash, network_hash = self._keys(email, network_origin)
        now = self._now()
        cutoff = now - self._window
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                self._prune_expired(connection, now=now)
                last_success_row = connection.execute(
                    """SELECT MAX(event_id) FROM m14_login_security_events
                       WHERE principal_hash = ? AND outcome = 'succeeded'
                         AND occurred_at >= ?""",
                    (principal_hash, cutoff.isoformat()),
                ).fetchone()
                last_success_id = (
                    int(last_success_row[0])
                    if last_success_row is not None and last_success_row[0] is not None
                    else 0
                )
                principal_failures = connection.execute(
                    """SELECT COUNT(*) FROM m14_login_security_events
                       WHERE principal_hash = ? AND outcome = 'failed'
                         AND occurred_at >= ? AND event_id > ?""",
                    (principal_hash, cutoff.isoformat(), last_success_id),
                ).fetchone()[0]
                network_failures = connection.execute(
                    """SELECT COUNT(*) FROM m14_login_security_events
                       WHERE network_hash = ? AND outcome = 'failed'
                         AND occurred_at > ?""",
                    (network_hash, cutoff.isoformat()),
                ).fetchone()[0]
                if (
                    principal_failures >= self._principal_attempts
                    or network_failures >= self._network_attempts
                ):
                    self._insert(
                        connection,
                        principal_hash=principal_hash,
                        network_hash=network_hash,
                        outcome="throttled",
                        occurred_at=now,
                    )
                    connection.commit()
                    raise AccountLoginRateLimited(
                        retry_after_seconds=max(1, int(self._window.total_seconds()))
                    )
        except AccountLoginRateLimited:
            raise
        except sqlite3.Error:
            raise AccountLoginProtectionUnavailable(
                "LOGIN_PROTECTION_UNAVAILABLE"
            ) from None

    def record(
        self,
        *,
        email: str,
        network_origin: str,
        outcome: Literal["succeeded", "failed"],
    ) -> None:
        principal_hash, network_hash = self._keys(email, network_origin)
        now = self._now()
        try:
            with self._connect() as connection:
                self._insert(
                    connection,
                    principal_hash=principal_hash,
                    network_hash=network_hash,
                    outcome=outcome,
                    occurred_at=now,
                )
        except sqlite3.Error:
            raise AccountLoginProtectionUnavailable(
                "LOGIN_PROTECTION_UNAVAILABLE"
            ) from None

    def store_ready(self) -> bool:
        try:
            with self._connect() as connection:
                columns = {
                    row[1]
                    for row in connection.execute(
                        "PRAGMA table_info(m14_login_security_events)"
                    ).fetchall()
                }
            return columns == {
                "event_id",
                "principal_hash",
                "network_hash",
                "outcome",
                "occurred_at",
            }
        except sqlite3.Error:
            return False

    def _keys(self, email: str, network_origin: str) -> tuple[str, str]:
        normalized_email = email.strip().casefold()
        normalized_network = network_origin.strip().casefold() or "unknown"
        return (
            self._digest("principal", normalized_email),
            self._digest("network", normalized_network),
        )

    def _digest(self, scope: str, value: str) -> str:
        return hmac.new(
            self._secret,
            f"m14:{scope}:{value}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise AccountLoginProtectionUnavailable("LOGIN_PROTECTION_UNAVAILABLE")
        return value.astimezone(timezone.utc)

    def _prune_expired(self, connection: sqlite3.Connection, *, now: datetime) -> None:
        connection.execute(
            "DELETE FROM m14_login_security_events WHERE occurred_at < ?",
            ((now - self._retention).isoformat(),),
        )

    @staticmethod
    def _insert(
        connection: sqlite3.Connection,
        *,
        principal_hash: str,
        network_hash: str,
        outcome: LoginOutcome,
        occurred_at: datetime,
    ) -> None:
        connection.execute(
            """INSERT INTO m14_login_security_events
               (principal_hash, network_hash, outcome, occurred_at)
               VALUES (?, ?, ?, ?)""",
            (principal_hash, network_hash, outcome, occurred_at.isoformat()),
        )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)

    def _initialize(self) -> None:
        try:
            with self._connect() as connection:
                connection.executescript(
                    """
                    PRAGMA journal_mode = WAL;
                    CREATE TABLE IF NOT EXISTS m14_login_security_events (
                        event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        principal_hash TEXT NOT NULL,
                        network_hash TEXT NOT NULL,
                        outcome TEXT NOT NULL
                            CHECK (outcome IN ('succeeded', 'failed', 'throttled')),
                        occurred_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_m14_login_principal_time
                        ON m14_login_security_events (principal_hash, occurred_at);
                    CREATE INDEX IF NOT EXISTS idx_m14_login_network_time
                        ON m14_login_security_events (network_hash, occurred_at);
                    """
                )
        except sqlite3.Error:
            raise AccountLoginProtectionUnavailable(
                "LOGIN_PROTECTION_UNAVAILABLE"
            ) from None
