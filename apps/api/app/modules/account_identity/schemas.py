from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.capabilities import WorkbenchCapability


AccountRole = Literal["personal_owner"]


def _normalize_email(value: str) -> str:
    normalized = value.strip().casefold()
    if (
        normalized.count("@") != 1
        or normalized.startswith("@")
        or normalized.endswith("@")
    ):
        raise ValueError("邮箱格式无效。")
    return normalized


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
        return _normalize_email(value)


class AccountLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().casefold()


class AccountDisable(BaseModel):
    """Operator-only account lifecycle input."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=254)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return _normalize_email(value)


class AccountPasswordReset(BaseModel):
    """Operator-only credential reset input; never accepted by HTTP or Agent tools."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=254)
    new_password: str = Field(min_length=12, max_length=256)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return _normalize_email(value)


class AccountLifecycleReceipt(BaseModel):
    """Non-identifying operator receipt for lifecycle mutations."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    action: Literal["disabled", "password_reset"]
    changed: bool
    revoked_sessions: int = Field(ge=0)


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
