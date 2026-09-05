from __future__ import annotations

import argparse
import json

from app.core.config import get_settings
from app.modules.beta_validation.maintenance import (
    BetaValidationMaintenanceError,
    BetaValidationRetention,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="仅维护超过 90 天的 M13 匿名指标事件；默认预览。"
    )
    parser.add_argument(
        "action",
        nargs="?",
        choices=("preview", "prune"),
        default="preview",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="确认删除已过期指标事件，不删除教师内容",
    )
    args = parser.parse_args(argv)
    if args.confirm and args.action != "prune":
        parser.error("--confirm 只能用于 prune")
    if args.action == "prune" and not args.confirm:
        print(
            json.dumps(
                {"error": "BETA_VALIDATION_RETENTION_CONFIRMATION_REQUIRED"}
            )
        )
        return 2
    try:
        database_path = get_settings().beta_validation_db
    except Exception:
        print(json.dumps({"error": "BETA_VALIDATION_CONFIGURATION_UNAVAILABLE"}))
        return 1
    try:
        maintenance = BetaValidationRetention(database_path=database_path)
        report = (
            maintenance.prune(confirmed=True)
            if args.action == "prune"
            else maintenance.preview()
        )
    except BetaValidationMaintenanceError as error:
        print(json.dumps({"error": str(error)}))
        return 1
    print(
        json.dumps(
            {"action": args.action, **report.model_dump(mode="json")},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
