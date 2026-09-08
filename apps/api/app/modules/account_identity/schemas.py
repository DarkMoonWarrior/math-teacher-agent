from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.capabilities import WorkbenchCapability


AccountRole = Literal["personal_owner"]


class PersonalAccountProvision(BaseModel):
    """Operator-only input. It is intentionally not exposed as an HTTP route."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=256)
    display_label: str = Field(min_length=1, max_length=80)
    owner_id: str | None = Field(default=None, min_length=1, max_length=120)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if (
            normalized.count("@") != 1
            or normalized.startswith("@")
            or normalized.endswith("@")
        ):
            raise ValueError("邮箱格式无效。")
        return normalized


class AccountLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().casefold()


class AccountIdentityContext(BaseModel):
    """Trusted server-owned identity handed to business modules."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    account_id: str = Field(min_length=1, max_length=120)
    tenant_id: str = Field(min_length=1, max_length=120)
    owner_id: str = Field(min_length=1, max_length=120)
    role: AccountRole
    display_label: str = Field(min_length=1, max_length=80)
    capabilities: list[WorkbenchCapability] = Field(default_factory=list)
    expires_at: datetime


class ProvisionedAccount(BaseModel):
    """Operator-facing account receipt without a login session or credential data."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    account_id: str = Field(min_length=1, max_length=120)
    tenant_id: str = Field(min_length=1, max_length=120)
    owner_id: str = Field(min_length=1, max_length=120)
    role: AccountRole
    display_label: str = Field(min_length=1, max_length=80)


class AccountSessionGrant(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    token: str = Field(min_length=32)
    identity: AccountIdentityContext


class AccountSessionStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    authenticated: bool
    display_label: str = ""
    expires_at: datetime | None = None
    capabilities: list[WorkbenchCapability] = Field(default_factory=list)
