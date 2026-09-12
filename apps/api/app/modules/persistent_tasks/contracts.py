from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


PERSISTENT_TASK_SCHEMA_VERSION = "m14.persistent-task.v1"


class PersistentTaskError(RuntimeError):
    """The durable task boundary could not complete a safe operation."""


class PersistentTaskConflict(PersistentTaskError):
    """An idempotency key was reused for a different task command."""


class PersistentTaskUnavailable(PersistentTaskError):
    """The durable task store is unavailable or has an unknown shape."""


class PersistentTaskPayloadError(PersistentTaskError):
    """A private task command or result could not be verified."""


class PersistentTaskView(BaseModel):
    task_id: str
    kind: str
    subject_id: str
    status: Literal[
        "queued",
        "running",
        "succeeded",
        "failed",
        "cancelled",
        "interrupted",
    ]
    current: int = 0
    total: int = 0
    message: str = ""
    error: str = ""
    result: dict = Field(default_factory=dict)
    attempt: int = 0
    created_at: str
    updated_at: str
