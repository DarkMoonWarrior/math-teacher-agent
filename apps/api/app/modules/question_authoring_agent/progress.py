from __future__ import annotations

import time
from dataclasses import dataclass
from threading import RLock
from typing import Literal

from pydantic import BaseModel

from app.modules.question_authoring import QuestionAuthoringStatementPreview


QuestionAuthoringProgressStage = Literal[
    "brief",
    "composing",
    "reauthoring",
    "reviewing",
    "refining",
    "solving",
    "reviewing_solution",
    "regenerating_solution",
    "staging",
]


class QuestionAuthoringProgressSnapshot(BaseModel):
    progress_id: str
    stage: QuestionAuthoringProgressStage
    elapsed_seconds: int
    statement: QuestionAuthoringStatementPreview | None = None
    statement_revision: int = 0
    statement_state: Literal["pending", "approved", "adjusting"] = "pending"


@dataclass
class _ProgressEntry:
    owner_id: str
    stage: QuestionAuthoringProgressStage
    started_at: float
    updated_at: float
    statement: QuestionAuthoringStatementPreview | None = None
    statement_revision: int = 0
    statement_state: Literal["pending", "approved", "adjusting"] = "pending"


class QuestionAuthoringProgressRegistry:
    """Process-local, content-free progress state for one active authoring request."""

    def __init__(self, *, ttl_seconds: int = 1800, max_entries: int = 512) -> None:
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._entries: dict[str, _ProgressEntry] = {}
        self._lock = RLock()

    def register(self, progress_id: str, *, owner_id: str) -> None:
        now = time.monotonic()
        with self._lock:
            self._prune(now)
            existing = self._entries.get(progress_id)
            if existing is not None and existing.owner_id != owner_id:
                raise ValueError("进度标识已被占用")
            if len(self._entries) >= self._max_entries and progress_id not in self._entries:
                oldest = min(self._entries, key=lambda key: self._entries[key].updated_at)
                self._entries.pop(oldest, None)
            self._entries[progress_id] = _ProgressEntry(
                owner_id=owner_id,
                stage="brief",
                started_at=now,
                updated_at=now,
            )

    def update(self, progress_id: str | None, stage: QuestionAuthoringProgressStage) -> bool:
        if not progress_id:
            return False
        now = time.monotonic()
        with self._lock:
            entry = self._entries.get(progress_id)
            if entry is None:
                return False
            entry.stage = stage
            if entry.statement is not None and stage in {"refining", "reauthoring"}:
                entry.statement_state = "adjusting"
            entry.updated_at = now
            return True

    def publish_statement(
        self,
        progress_id: str | None,
        statement: QuestionAuthoringStatementPreview,
    ) -> bool:
        """Publish one owner-bound statement only after its independent review passes."""

        if not progress_id:
            return False
        now = time.monotonic()
        with self._lock:
            entry = self._entries.get(progress_id)
            if entry is None:
                return False
            if entry.statement != statement:
                entry.statement_revision += 1
            entry.statement = statement.model_copy(deep=True)
            entry.statement_state = "approved"
            entry.updated_at = now
            return True

    def discard_statement(self, progress_id: str | None) -> bool:
        if not progress_id:
            return False
        now = time.monotonic()
        with self._lock:
            entry = self._entries.get(progress_id)
            if entry is None:
                return False
            entry.statement = None
            entry.statement_revision = 0
            entry.statement_state = "pending"
            entry.updated_at = now
            return True

    def snapshot(self, progress_id: str, *, owner_id: str) -> QuestionAuthoringProgressSnapshot:
        now = time.monotonic()
        with self._lock:
            self._prune(now)
            entry = self._entries.get(progress_id)
            if entry is None or entry.owner_id != owner_id:
                raise KeyError(progress_id)
            return QuestionAuthoringProgressSnapshot(
                progress_id=progress_id,
                stage=entry.stage,
                elapsed_seconds=max(0, int(now - entry.started_at)),
                statement=(entry.statement.model_copy(deep=True) if entry.statement else None),
                statement_revision=entry.statement_revision,
                statement_state=entry.statement_state,
            )

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def _prune(self, now: float) -> None:
        expired = [
            progress_id
            for progress_id, entry in self._entries.items()
            if now - entry.updated_at > self._ttl_seconds
        ]
        for progress_id in expired:
            self._entries.pop(progress_id, None)


_progress_registry = QuestionAuthoringProgressRegistry()


def get_question_authoring_progress_registry() -> QuestionAuthoringProgressRegistry:
    return _progress_registry
