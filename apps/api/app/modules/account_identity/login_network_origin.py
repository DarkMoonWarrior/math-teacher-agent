from __future__ import annotations

import ipaddress

from app.modules.account_identity.contracts import LoginNetworkOriginUnavailable


_MAX_PEER_LENGTH = 255
_MAX_CIDR_COUNT = 32


class DirectLoginNetworkOrigin:
    """Use only the ASGI peer and ignore all browser forwarding headers."""

    def resolve(self, *, peer_host: str | None, forwarded_for: str | None) -> str:
        del forwarded_for
        value = (peer_host or "").strip()
        if not value or len(value) > _MAX_PEER_LENGTH:
            raise LoginNetworkOriginUnavailable("LOGIN_NETWORK_ORIGIN_UNAVAILABLE")
        try:
            return ipaddress.ip_address(value).compressed
        except ValueError:
            # ASGI test transports and local development can expose a bounded
            # host label instead of an IP address. Production rejects this mode.
            return value.casefold()

    def configuration_ready(self) -> bool:
        return True


class TrustedProxyLoginNetworkOrigin:
    """Accept one canonical client IP only from an allow-listed immediate peer.

    The edge must replace, rather than append to, X-Forwarded-For. Requiring one
    address avoids treating a client-injected left-most hop as trusted.
    """

    def __init__(self, *, trusted_proxy_cidrs: str) -> None:
        entries = [item.strip() for item in trusted_proxy_cidrs.split(",") if item.strip()]
        if not entries or len(entries) > _MAX_CIDR_COUNT:
            raise LoginNetworkOriginUnavailable("LOGIN_NETWORK_ORIGIN_UNAVAILABLE")
        try:
            self._networks = tuple(
                ipaddress.ip_network(item, strict=True) for item in entries
            )
        except ValueError:
            raise LoginNetworkOriginUnavailable(
                "LOGIN_NETWORK_ORIGIN_UNAVAILABLE"
            ) from None

    def resolve(self, *, peer_host: str | None, forwarded_for: str | None) -> str:
        try:
            peer = ipaddress.ip_address((peer_host or "").strip())
        except ValueError:
            raise LoginNetworkOriginUnavailable(
                "LOGIN_NETWORK_ORIGIN_UNAVAILABLE"
            ) from None
        if not any(peer in network for network in self._networks):
            raise LoginNetworkOriginUnavailable("LOGIN_NETWORK_ORIGIN_UNAVAILABLE")

        forwarded = (forwarded_for or "").strip()
        if not forwarded or "," in forwarded or len(forwarded) > _MAX_PEER_LENGTH:
            raise LoginNetworkOriginUnavailable("LOGIN_NETWORK_ORIGIN_UNAVAILABLE")
        try:
            return ipaddress.ip_address(forwarded).compressed
        except ValueError:
            raise LoginNetworkOriginUnavailable(
                "LOGIN_NETWORK_ORIGIN_UNAVAILABLE"
            ) from None

    def configuration_ready(self) -> bool:
        return bool(self._networks)


class UnavailableLoginNetworkOrigin:
    def resolve(self, *, peer_host: str | None, forwarded_for: str | None) -> str:
        del peer_host, forwarded_for
        raise LoginNetworkOriginUnavailable("LOGIN_NETWORK_ORIGIN_UNAVAILABLE")

    def configuration_ready(self) -> bool:
        return False
