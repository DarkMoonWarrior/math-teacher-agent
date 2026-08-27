from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.question_authoring import GeneratedQuestionDraft, QuestionDesignBrief


class QuestionAuthoringAgentCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brief: QuestionDesignBrief
    session_id: str | None = Field(default=None, max_length=160)
    progress_id: str | None = Field(
        default=None,
        min_length=20,
        max_length=160,
        pattern=r"^qap_[A-Za-z0-9_-]+$",
    )


class QuestionAuthoringAgentResponse(BaseModel):
    request_id: str
    session_id: str = ""
    run_id: str = ""
    status: Literal["ok", "error", "cancelled"]
    draft: GeneratedQuestionDraft | None = None
    tool_request_id: str = ""
    tool_call_count: int = 0
    error: dict[str, Any] | None = None
