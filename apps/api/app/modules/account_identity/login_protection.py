from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from app.modules.account_identity.contracts import (
    AccountLoginProtectionUnavailable,
    AccountLoginRateLimited,
)
from app.modules.account_identity.hmac_keyring import VersionedHmacKeyRing


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
        key_ring: VersionedHmacKeyRing,
        window: timedelta,
        principal_attempts: int,
        network_attempts: int,
        retention: timedelta,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if window <= timedelta(0) or retention < window:
            raise ValueError("登录防护窗口或保留期无效。")
        if principal_attempts < 2 or network_attempts < principal_attempts:
            raise ValueError("登录防护阈值无效。")
        self._path = database_path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._key_ring = key_ring
        self._window = window
        self._principal_attempts = principal_attempts
        self._network_attempts = network_attempts
        self._retention = retention
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._initialize()

    def assess(self, *, email: str, network_origin: str) -> None:
        principal_hashes, network_hashes = self._candidate_keys(email, network_origin)
        principal_hash = principal_hashes[0]
        network_hash = network_hashes[0]
        now = self._now()
        cutoff = now - self._window
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                self._prune_expired(connection, now=now)
                self._require_recognized_digests(connection, now=now)
                principal_placeholders = ", ".join("?" for _ in principal_hashes)
                last_success_row = connection.execute(
                    f"""SELECT MAX(event_id) FROM m14_login_security_events
                       WHERE principal_hash IN ({principal_placeholders})
                         AND outcome = 'succeeded' AND occurred_at >= ?""",
                    (*principal_hashes, cutoff.isoformat()),
                ).fetchone()
                last_success_id = (
                    int(last_success_row[0])
                    if last_success_row is not None and last_success_row[0] is not None
                    else 0
                )
                principal_failures = connection.execute(
                    f"""SELECT COUNT(*) FROM m14_login_security_events
                       WHERE principal_hash IN ({principal_placeholders})
                         AND outcome = 'failed'
                         AND occurred_at >= ? AND event_id > ?""",
                    (*principal_hashes, cutoff.isoformat(), last_success_id),
                ).fetchone()[0]
                network_placeholders = ", ".join("?" for _ in network_hashes)
                network_failures = connection.execute(
                    f"""SELECT COUNT(*) FROM m14_login_security_events
                       WHERE network_hash IN ({network_placeholders})
                         AND outcome = 'failed'
                         AND occurred_at > ?""",
                    (*network_hashes, cutoff.isoformat()),
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
        principal_hash = self._key_ring.digest(
            "login:principal", email.strip().casefold()
        )
        network_hash = self._key_ring.digest(
            "login:network", network_origin.strip().casefold() or "unknown"
        )
        now = self._now()
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                self._prune_expired(connection, now=now)
                self._require_recognized_digests(connection, now=now)
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
                recognized = self._digests_are_recognized(
                    connection, now=self._now()
                )
            return recognized and columns == {
                "event_id",
                "principal_hash",
                "network_hash",
                "outcome",
                "occurred_at",
            }
        except (sqlite3.Error, AccountLoginProtectionUnavailable):
            return False

    def _candidate_keys(
        self, email: str, network_origin: str
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        normalized_email = email.strip().casefold()
        normalized_network = network_origin.strip().casefold() or "unknown"
        return (
            self._key_ring.candidates("login:principal", normalized_email),
            self._key_ring.candidates("login:network", normalized_network),
        )

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

    def _require_recognized_digests(
        self, connection: sqlite3.Connection, *, now: datetime
    ) -> None:
        if not self._digests_are_recognized(connection, now=now):
            raise AccountLoginProtectionUnavailable(
                "LOGIN_PROTECTION_UNAVAILABLE"
            )

    def _digests_are_recognized(
        self, connection: sqlite3.Connection, *, now: datetime
    ) -> bool:
        rows = connection.execute(
            """SELECT DISTINCT principal_hash, network_hash
               FROM m14_login_security_events WHERE occurred_at >= ?""",
            ((now - self._retention).isoformat(),),
        ).fetchall()
        return all(
            self._key_ring.recognizes(principal_hash)
            and self._key_ring.recognizes(network_hash)
            for principal_hash, network_hash in rows
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
