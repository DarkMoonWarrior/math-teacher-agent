from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timedelta, timezone

from app.core.config import get_settings
from app.modules.beta_validation.metrics import BetaValidationMetrics


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="输出不含教师或任务明细的 M13 私有运营聚合读数。"
    )
    parser.add_argument(
        "--days",
        type=int,
        choices=range(1, 91),
        default=90,
        metavar="1-90",
        help="统计窗口天数，默认 90 天。",
    )
    args = parser.parse_args(argv)
    try:
        settings = get_settings()
        secret = settings.beta_validation_identity_secret.get_secret_value()
        if len(secret) < 32:
            raise ValueError
        metrics = BetaValidationMetrics(
            database_path=settings.beta_validation_db,
            identity_secret=secret,
            read_only=True,
        )
        window_end = datetime.now(timezone.utc)
        report = metrics.private_operations_readout(
            window_start=window_end - timedelta(days=args.days),
            window_end=window_end,
        )
    except (OSError, ValueError, sqlite3.Error):
        print(json.dumps({"error": "BETA_VALIDATION_OPERATIONS_UNAVAILABLE"}))
        return 1
    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
