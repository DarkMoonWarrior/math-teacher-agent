"""Short-lived, one-use capabilities for confirmed question-bundle Solve access."""

from __future__ import annotations

import hashlib
import secrets
import threading
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable

from .schemas import QuestionSolveReference


class QuestionSolveGrantError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class QuestionSolveGrantBinding:
    owner_id: str
    question_text: str
    solution_mode: str
    teacher_instruction: str
    reference: QuestionSolveReference


@dataclass(frozen=True, slots=True)
class _Grant:
    binding: QuestionSolveGrantBinding
    expires_at: float


class QuestionSolveGrantRegistry:
    """Binds an opaque capability to one complete server-authorized Solve intent."""

    def __init__(
        self,
        *,
        ttl_seconds: float = 180,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._grants: dict[str, _Grant] = {}
        self._lock = threading.Lock()

    def issue(
        self,
        *,
        owner_id: str,
        question_text: str,
        solution_mode: str,
        teacher_instruction: str,
        reference: QuestionSolveReference,
    ) -> str:
        token = secrets.token_urlsafe(32)
        now = self._clock()
        grant = _Grant(
            binding=QuestionSolveGrantBinding(
                owner_id=owner_id,
                question_text=question_text.strip(),
                solution_mode=solution_mode,
                teacher_instruction=teacher_instruction.strip(),
                reference=reference,
            ),
            expires_at=now + self._ttl_seconds,
        )
        with self._lock:
            self._discard_expired(now)
            self._grants[self._token_digest(token)] = grant
        return token

    def consume(
        self,
        token: str,
    ) -> QuestionSolveGrantBinding:
        now = self._clock()
        with self._lock:
            grant = self._grants.pop(self._token_digest(token), None)
            self._discard_expired(now)
        if grant is None or grant.expires_at <= now:
            raise QuestionSolveGrantError("本次题目图片 Solve 许可无效或已使用")
        return grant.binding

    def _discard_expired(self, now: float) -> None:
        expired = [key for key, grant in self._grants.items() if grant.expires_at <= now]
        for key in expired:
            self._grants.pop(key, None)

    @staticmethod
    def _token_digest(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()


@lru_cache
def get_question_solve_grants() -> QuestionSolveGrantRegistry:
    return QuestionSolveGrantRegistry()
