from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.capabilities import (
    ALL_WORKBENCH_CAPABILITIES,
    WorkbenchCapability,
)

# Compatibility names for the Closed Beta adapter. Capability vocabulary belongs
# to the workbench, not to the temporary access mechanism.
BetaCapability = WorkbenchCapability
ALL_BETA_CAPABILITIES = ALL_WORKBENCH_CAPABILITIES


class BetaParticipant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    teacher_id: str = Field(min_length=1, max_length=120)
    display_label: str = Field(min_length=1, max_length=80)
    capabilities: list[BetaCapability] = Field(default_factory=list)

    @field_validator("capabilities")
    @classmethod
    def normalize_capabilities(
        cls,
        value: list[BetaCapability],
    ) -> list[BetaCapability]:
        selected = set(value)
        return [
            capability
            for capability in ALL_BETA_CAPABILITIES
            if capability in selected
        ]


class BetaTeacherIdentity(BetaParticipant):
    expires_at: datetime


class BetaSessionGrant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=32)
    teacher: BetaTeacherIdentity


class BetaSessionStart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_code: str = Field(min_length=1, max_length=200)


class BetaSessionStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["local_development", "closed_beta"]
    authenticated: bool
    display_label: str = ""
    expires_at: datetime | None = None
    capabilities: list[BetaCapability] = Field(default_factory=list)
