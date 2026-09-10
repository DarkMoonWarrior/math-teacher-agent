from __future__ import annotations

from typing import Literal, Protocol

from app.modules.account_identity.schemas import (
    AccountDisable,
    AccountIdentityContext,
    AccountLifecycleReceipt,
    AccountLogin,
    AccountPasswordReset,
    PersonalAccountRegistration,
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


class AccountRegistration(Protocol):
    """Browser registration Interface with no caller-selected identity fields."""

    def register_personal_account(
        self, command: PersonalAccountRegistration
    ) -> AccountSessionGrant: ...


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


class AccountLoginProtection(Protocol):
    """Server-only login abuse boundary; raw identifiers never leave this seam."""

    def assess(self, *, email: str, network_origin: str) -> None: ...

    def record(
        self,
        *,
        email: str,
        network_origin: str,
        outcome: Literal["succeeded", "failed"],
    ) -> None: ...

    def store_ready(self) -> bool: ...


class LoginNetworkOrigin(Protocol):
    """Resolve a bounded login source from server-owned connection facts."""

    def resolve(self, *, peer_host: str | None, forwarded_for: str | None) -> str: ...

    def configuration_ready(self) -> bool: ...


class AccountLifecycleAudit(Protocol):
    """Operator-only mutation audit; stores only keyed digests and bounded facts."""

    def begin(
        self, *, action: str, operator_label: str, target_hint: str
    ) -> str: ...

    def succeed(
        self, *, event_id: str, changed: bool, affected_sessions: int
    ) -> None: ...

    def fail(self, *, event_id: str) -> None: ...

    def summary(self) -> dict[str, int]: ...

    def store_ready(self) -> bool: ...


class AccountIdentityDenied(ValueError):
    """Public authentication failures intentionally share one exception type."""


class AccountIdentityConflict(ValueError):
    """Operator provisioning conflicts; never returned by the login route."""


class AccountIdentityUnavailable(ValueError):
    """Identity storage/configuration is unavailable and must fail closed."""


class AccountAdministrationError(ValueError):
    """Stable operator error code without account or storage details."""


class AccountLoginProtectionUnavailable(ValueError):
    """Login must fail closed when its protection store is unavailable."""


class LoginNetworkOriginUnavailable(ValueError):
    """Login must fail closed when a trusted source cannot be established."""


class AccountLoginRateLimited(ValueError):
    """Stable throttling signal without disclosing which limit was reached."""

    def __init__(self, *, retry_after_seconds: int) -> None:
        super().__init__("LOGIN_RATE_LIMITED")
        self.retry_after_seconds = max(1, retry_after_seconds)


class AccountLifecycleAuditError(ValueError):
    """Stable operator audit error without identifiers or storage details."""
