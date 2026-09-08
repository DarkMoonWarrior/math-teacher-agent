from __future__ import annotations

import json
from datetime import timedelta
from functools import lru_cache

from fastapi import Depends

from app.core.config import Settings, get_settings
from app.modules.beta_access.access import BetaAccess, BetaAccessDenied
from app.modules.beta_access.schemas import BetaParticipant


class DisabledBetaAccess:
    """No-storage adapter used outside the exclusive Closed Beta mode."""

    @staticmethod
    def issue(access_code: str):
        raise BetaAccessDenied("封闭测试访问未启用。")

    @staticmethod
    def resolve(token: str):
        raise BetaAccessDenied("封闭测试访问未启用。")

    @staticmethod
    def revoke(token: str) -> bool:
        return False

    @staticmethod
    def store_ready() -> bool:
        return False

    @staticmethod
    def has_participants() -> bool:
        return False


_DISABLED_BETA_ACCESS = DisabledBetaAccess()


def _parse_participants(raw: str, *, enabled: bool) -> dict[str, BetaParticipant]:
    if not enabled:
        return {}
    try:
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise TypeError
        return {
            str(code): BetaParticipant.model_validate(participant)
            for code, participant in value.items()
        }
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise RuntimeError("MATH_AI_BETA_ACCESS_ROSTER_JSON 配置无效。") from exc


@lru_cache(maxsize=8)
def _build_beta_access(
    database_path: str,
    roster_json: str,
    enabled: bool,
    ttl_hours: int,
) -> BetaAccess:
    from pathlib import Path

    return BetaAccess(
        database_path=Path(database_path),
        participants=_parse_participants(roster_json, enabled=enabled),
        session_ttl=timedelta(hours=ttl_hours),
    )


def get_beta_access(settings: Settings = Depends(get_settings)) -> BetaAccess:
    if not settings.beta_access_enabled or settings.production_identity_enabled:
        return _DISABLED_BETA_ACCESS  # type: ignore[return-value]
    return _build_beta_access(
        str(settings.beta_session_db),
        settings.beta_access_roster_json,
        settings.beta_access_enabled,
        settings.beta_session_ttl_hours,
    )
