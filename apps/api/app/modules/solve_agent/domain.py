"""Solve Agent product models; never expose raw Harness payloads to callers."""

from __future__ import annotations

import time
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.modules.solution_assistant import SolutionResult


SolveAgentStatus = Literal["pending", "running", "ok", "error", "cancelled"]


class SolveAgentCommand(BaseModel):
    question_text: str = Field(min_length=5, max_length=30000)
    solution_mode: Literal["standard", "alternative"] = "standard"
    teacher_instruction: str = Field(default="", max_length=2000)
    session_id: str | None = Field(default=None, max_length=160)


class SolveAgentResponse(BaseModel):
    request_id: str
    session_id: str = ""
    run_id: str = ""
    status: SolveAgentStatus
    question_text: str
    solution_mode: Literal["standard", "alternative"]
    solution: SolutionResult | None = None
    tool_request_id: str = ""
    duration_ms: int = 0
    tool_call_count: int = 0
    error: dict[str, Any] | None = None


class SolveAgentRunRecord(BaseModel):
    run_id: str
    request_id: str
    session_id: str = ""
    status: SolveAgentStatus = "pending"
    command: SolveAgentCommand
    response: SolveAgentResponse | None = None
    error: dict[str, Any] | None = None
    created_at: float = Field(default_factory=time.time)
    finished_at: float | None = None
