from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.modules.beta_access.schemas import (
    BetaParticipant,
    BetaSessionGrant,
    BetaTeacherIdentity,
)


class BetaAccessDenied(ValueError):
    pass


class BetaAccess:
    """Issue, resolve and revoke opaque Closed Beta sessions.

    Access-code comparison, token hashing, expiry and persistence stay behind this
    three-operation interface. Callers never receive roster contents.
    """

    def __init__(
        self,
        *,
        database_path: Path,
        participants: dict[str, BetaParticipant],
        session_ttl: timedelta,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if session_ttl <= timedelta(0):
            raise ValueError("Beta 会话有效期必须大于 0。")
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._participants = dict(participants)
        self._session_ttl = session_ttl
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._initialize()

    def issue(self, access_code: str) -> BetaSessionGrant:
        participant = self._participant_for(access_code)
        if participant is None:
            raise BetaAccessDenied("封闭测试访问码无效或不可用。")

        now = self._now()
        expires_at = now + self._session_ttl
        token = secrets.token_urlsafe(48)
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO m12_beta_sessions
                   (token_hash, teacher_id, display_label, capabilities_json,
                    created_at, expires_at, revoked_at)
                   VALUES (?, ?, ?, ?, ?, ?, NULL)""",
                (
                    self._hash(token),
                    participant.teacher_id,
                    participant.display_label,
                    json.dumps(participant.capabilities, ensure_ascii=False),
                    now.isoformat(),
                    expires_at.isoformat(),
                ),
            )
        return BetaSessionGrant(
            token=token,
            teacher=BetaTeacherIdentity(
                teacher_id=participant.teacher_id,
                display_label=participant.display_label,
                capabilities=participant.capabilities,
                expires_at=expires_at,
            ),
        )

    def resolve(self, token: str) -> BetaTeacherIdentity:
        if not token:
            raise BetaAccessDenied("封闭测试会话不存在。")
        with self._connect() as connection:
            row = connection.execute(
                """SELECT teacher_id, display_label, capabilities_json,
                          expires_at, revoked_at
                   FROM m12_beta_sessions WHERE token_hash = ?""",
                (self._hash(token),),
            ).fetchone()
        if row is None or row["revoked_at"] is not None:
            raise BetaAccessDenied("封闭测试会话无效。")
        expires_at = datetime.fromisoformat(row["expires_at"])
        if expires_at <= self._now():
            raise BetaAccessDenied("封闭测试会话已过期。")
        return BetaTeacherIdentity(
            teacher_id=row["teacher_id"],
            display_label=row["display_label"],
            capabilities=json.loads(row["capabilities_json"]),
            expires_at=expires_at,
        )

    def revoke(self, token: str) -> bool:
        if not token:
            return False
        now = self._now().isoformat()
        with self._connect() as connection:
            changed = connection.execute(
                """UPDATE m12_beta_sessions SET revoked_at = ?
                   WHERE token_hash = ? AND revoked_at IS NULL""",
                (now, self._hash(token)),
            ).rowcount
        return changed > 0

    def store_ready(self) -> bool:
        try:
            with self._connect() as connection:
                return connection.execute("SELECT 1").fetchone()[0] == 1
        except sqlite3.Error:
            return False

    def has_participants(self) -> bool:
        return bool(self._participants)

    def _participant_for(self, access_code: str) -> BetaParticipant | None:
        for candidate, participant in self._participants.items():
            if secrets.compare_digest(candidate, access_code):
                return participant
        return None

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise ValueError("BetaAccess clock 必须返回带时区时间。")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS m12_beta_sessions (
                    token_hash TEXT PRIMARY KEY,
                    teacher_id TEXT NOT NULL,
                    display_label TEXT NOT NULL,
                    capabilities_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    revoked_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_m12_beta_sessions_teacher
                    ON m12_beta_sessions (teacher_id, expires_at);
                """
            )
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(m12_beta_sessions)")
            }
            if "capabilities_json" not in columns:
                connection.execute(
                    """ALTER TABLE m12_beta_sessions
                       ADD COLUMN capabilities_json TEXT NOT NULL DEFAULT '[]'"""
                )
