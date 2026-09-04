from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from app.core.config import get_settings
from app.modules.beta_access.maintenance import BetaSessionMaintenance, SessionMaintenanceError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="仅维护已到期或已退出的登录会话；默认预览。")
    parser.add_argument("action", nargs="?", choices=("preview", "prune"), default="preview")
    parser.add_argument("--confirm", action="store_true", help="确认删除失效会话记录，不删除教师内容")
    args = parser.parse_args(argv)
    if args.confirm and args.action != "prune":
        parser.error("--confirm 只能用于 prune")
    if args.action == "prune" and not args.confirm:
        print(json.dumps({"error": "SESSION_CLEANUP_CONFIRMATION_REQUIRED"}))
        return 2
    try:
        database_path = get_settings().beta_session_db
    except Exception:
        # Settings validation can include raw environment values in its errors.
        print(json.dumps({"error": "SESSION_CONFIGURATION_UNAVAILABLE"}))
        return 1
    try:
        # Use only the configured session database; never initialize BetaAccess,
        # read its participant roster or accept an arbitrary store from the Agent.
        maintenance = BetaSessionMaintenance(database_path=database_path)
        report = maintenance.prune(confirmed=True) if args.action == "prune" else maintenance.preview()
    except SessionMaintenanceError as error:
        print(json.dumps({"error": str(error)}))
        return 1
    print(json.dumps({"action": args.action, **asdict(report)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
