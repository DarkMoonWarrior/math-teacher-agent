from __future__ import annotations

import json
from datetime import timedelta
from functools import lru_cache

from fastapi import Depends

from app.core.config import Settings, get_settings
from app.modules.beta_access.access import BetaAccess
from app.modules.beta_access.schemas import BetaParticipant


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
    return _build_beta_access(
        str(settings.beta_session_db),
        settings.beta_access_roster_json,
        settings.beta_access_enabled,
        settings.beta_session_ttl_hours,
    )
