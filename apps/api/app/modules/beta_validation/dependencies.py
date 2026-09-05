from __future__ import annotations

import sqlite3
from functools import lru_cache

from fastapi import Depends, HTTPException

from app.core.config import Settings, get_settings
from app.modules.beta_validation.metrics import BetaValidationMetrics


@lru_cache(maxsize=8)
def _build_beta_validation_metrics(
    database_path: str,
    identity_secret: str,
) -> BetaValidationMetrics:
    from pathlib import Path

    return BetaValidationMetrics(
        database_path=Path(database_path),
        identity_secret=identity_secret,
    )


def get_beta_validation_metrics(
    settings: Settings = Depends(get_settings),
) -> BetaValidationMetrics:
    if not settings.beta_validation_enabled:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "BETA_VALIDATION_COLLECTION_DISABLED",
                "message": "当前未启用封闭测试指标采集。",
            },
        )
    return get_beta_validation_store(settings)


def get_beta_validation_store(
    settings: Settings = Depends(get_settings),
) -> BetaValidationMetrics:
    """Open configured storage for teacher export/delete even when collection is off."""

    secret = settings.beta_validation_identity_secret.get_secret_value()
    if len(secret) < 32:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "BETA_VALIDATION_CONFIGURATION_UNAVAILABLE",
                "message": "封闭测试指标配置尚未就绪。",
            },
        )
    try:
        return _build_beta_validation_metrics(
            str(settings.beta_validation_db),
            secret,
        )
    except (OSError, ValueError, sqlite3.Error):
        raise HTTPException(
            status_code=503,
            detail={
                "code": "BETA_VALIDATION_CONFIGURATION_UNAVAILABLE",
                "message": "封闭测试指标配置尚未就绪。",
            },
        ) from None
