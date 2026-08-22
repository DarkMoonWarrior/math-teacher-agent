from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CurrentTeacher(BaseModel):
    """Server-owned teacher identity presented to business modules.

    The local adapter is intentionally simple until M12 production identity,
    while the dependency itself is already replaceable and overrideable in
    owner-isolation tests. Browser and model payloads never choose this value.
    """

    teacher_id: str = Field(min_length=1, max_length=120)
    source: Literal["local_development", "authenticated_session"]


def get_current_teacher() -> CurrentTeacher:
    return CurrentTeacher(
        teacher_id="owner_teacher",
        source="local_development",
    )
