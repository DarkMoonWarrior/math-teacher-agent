from __future__ import annotations

from typing import Protocol

from app.modules.account_identity.schemas import (
    AccountDisable,
    AccountIdentityContext,
    AccountLifecycleReceipt,
    AccountLogin,
    AccountPasswordReset,
    AccountSessionGrant,
    PersonalAccountProvision,
    ProvisionedAccount,
)


class AccountIdentity(Protocol):
    """Production identity Interface; transports and business modules depend on this."""

    def authenticate(self, command: AccountLogin) -> AccountSessionGrant: ...

    def resolve(self, token: str) -> AccountIdentityContext: ...

    def revoke(self, token: str) -> bool: ...

    def store_ready(self) -> bool: ...


class AccountAdministration(Protocol):
    """Operator-only account lifecycle Interface; never exposed to transports."""

    def provision_personal_account(
        self, command: PersonalAccountProvision
    ) -> ProvisionedAccount: ...

    def disable_account(
        self, command: AccountDisable, *, confirmed: bool = False
    ) -> AccountLifecycleReceipt: ...

    def reset_password(
        self, command: AccountPasswordReset, *, confirmed: bool = False
    ) -> AccountLifecycleReceipt: ...


class AccountIdentityDenied(ValueError):
    """Public authentication failures intentionally share one exception type."""


class AccountIdentityConflict(ValueError):
    """Operator provisioning conflicts; never returned by the login route."""


class AccountAdministrationError(ValueError):
    """Stable operator error code without account or storage details."""
