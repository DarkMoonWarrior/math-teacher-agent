from __future__ import annotations

from typing import Protocol

from app.modules.account_identity.schemas import (
    AccountIdentityContext,
    AccountLogin,
    AccountSessionGrant,
    PersonalAccountProvision,
    ProvisionedAccount,
)


class AccountIdentity(Protocol):
    """Production identity Interface; transports and business modules depend on this."""

    def provision_personal_account(
        self, command: PersonalAccountProvision
    ) -> ProvisionedAccount: ...

    def authenticate(self, command: AccountLogin) -> AccountSessionGrant: ...

    def resolve(self, token: str) -> AccountIdentityContext: ...

    def revoke(self, token: str) -> bool: ...

    def store_ready(self) -> bool: ...


class AccountIdentityDenied(ValueError):
    """Public authentication failures intentionally share one exception type."""


class AccountIdentityConflict(ValueError):
    """Operator provisioning conflicts; never returned by the login route."""
