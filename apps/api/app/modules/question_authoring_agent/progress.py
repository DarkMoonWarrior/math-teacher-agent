from __future__ import annotations

import time
from dataclasses import dataclass
from threading import RLock
from typing import Literal

from pydantic import BaseModel


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


@dataclass
class _ProgressEntry:
    owner_id: str
    stage: QuestionAuthoringProgressStage
    started_at: float
    updated_at: float


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
