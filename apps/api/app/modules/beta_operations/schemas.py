from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


OperationalCapability = Literal[
    "access",
    "search",
    "solve",
    "library",
    "authoring",
    "lesson",
    "paper",
    "teacher_memory",
    "shared",
    "system",
]

OperationalOutcome = Literal["success", "client_error", "server_error"]


class OperationalEvent(BaseModel):
    """Allow-listed operational facts; request/private content has no field here."""

    request_id: str = Field(min_length=1, max_length=80)
    capability: OperationalCapability
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE", "OTHER"]
    outcome: OperationalOutcome
    status_code: int = Field(ge=100, le=599)
    error_class: str = Field(default="", max_length=80)
    duration_ms: int = Field(ge=0)


class ReadinessComponent(BaseModel):
    name: Literal[
        "api",
        "beta_access",
        "account_identity",
        "login_network_origin",
        "login_protection",
        "agent_runtime",
    ]
    status: Literal["ready", "not_required", "unavailable"]
    code: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=200)


class ReadinessSnapshot(BaseModel):
    status: Literal["ready", "degraded"]
    checked_at: datetime
    components: list[ReadinessComponent]
