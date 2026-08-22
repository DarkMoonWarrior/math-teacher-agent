"""Product-owned contracts for consented private-library retrieval."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.private_library import PrivateLibrarySearchResult


class PrivateLibraryAgentCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=500)
    private_content_consent: Literal[True]
    limit: int = Field(default=5, ge=1, le=8)
    session_id: str | None = Field(default=None, max_length=160)


class PrivateLibraryAgentResponse(BaseModel):
    request_id: str
    session_id: str = ""
    run_id: str = ""
    status: Literal["ok", "error", "cancelled"]
    query: str
    result: PrivateLibrarySearchResult | None = None
    consent_applied: bool = True
    tool_request_id: str = ""
    tool_call_count: int = 0
    error: dict[str, Any] | None = None
