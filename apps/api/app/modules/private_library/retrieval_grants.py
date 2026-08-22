"""Short-lived, one-use consent receipts for private-content retrieval."""

from __future__ import annotations

import hashlib
import re
import secrets
import threading
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable


class PrivateRetrievalConsentError(ValueError):
    pass


@dataclass(frozen=True)
class _Grant:
    owner_id: str
    query: str
    limit: int
    expires_at: float


class PrivateRetrievalGrantRegistry:
    """Binds opaque consent to owner/query/limit and consumes it exactly once."""

    def __init__(self, *, ttl_seconds: float = 120, clock: Callable[[], float] = time.monotonic) -> None:
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._grants: dict[str, _Grant] = {}
        self._lock = threading.Lock()

    def issue(self, *, owner_id: str, query: str, limit: int) -> str:
        token = secrets.token_urlsafe(32)
        now = self._clock()
        grant = _Grant(owner_id, self._normalize(query), limit, now + self._ttl_seconds)
        with self._lock:
            self._discard_expired(now)
            self._grants[self._digest(token)] = grant
        return token

    def consume(
        self,
        token: str,
        *,
        query: str,
        limit: int,
        owner_id: str | None = None,
    ) -> str:
        now = self._clock()
        with self._lock:
            grant = self._grants.pop(self._digest(token), None)
            self._discard_expired(now)
        if grant is None or grant.expires_at <= now:
            raise PrivateRetrievalConsentError("本次私人检索许可无效或已使用")
        if (grant.query, grant.limit) != (self._normalize(query), limit):
            raise PrivateRetrievalConsentError("私人检索许可与当前教师或查询不匹配")
        if owner_id is not None and grant.owner_id != owner_id:
            raise PrivateRetrievalConsentError("私人检索许可与当前教师或查询不匹配")
        return grant.owner_id

    def _discard_expired(self, now: float) -> None:
        expired = [key for key, grant in self._grants.items() if grant.expires_at <= now]
        for key in expired:
            self._grants.pop(key, None)

    @staticmethod
    def _normalize(query: str) -> str:
        return re.sub(r"\s+", " ", query).strip()

    @staticmethod
    def _digest(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()


@lru_cache
def get_private_retrieval_grants() -> PrivateRetrievalGrantRegistry:
    return PrivateRetrievalGrantRegistry()
