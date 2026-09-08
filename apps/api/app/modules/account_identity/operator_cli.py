"""Closed operator CLI for M14 account lifecycle and session maintenance."""
from __future__ import annotations

import argparse
import getpass
import json
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path

from pydantic import ValidationError

from app.core.config import Settings, get_settings
from app.modules.account_identity.contracts import (
    AccountAdministrationError,
    AccountIdentityConflict,
)
from app.modules.account_identity.maintenance import (
    AccountSessionMaintenance,
    AccountSessionMaintenanceError,
)
from app.modules.account_identity.schemas import (
    AccountDisable,
    AccountPasswordReset,
    PersonalAccountProvision,
)
from app.modules.account_identity.sqlite_adapter import SqliteAccountIdentity


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="正式账号操作者工具；不开放给网页或 Agent。"
    )
    commands = parser.add_subparsers(dest="action", required=True)

    provision = commands.add_parser("provision", help="创建个人账号")
    provision.add_argument("--email", required=True)
    provision.add_argument("--display-label", required=True)
    provision.add_argument("--confirm", action="store_true")

    disable = commands.add_parser("disable", help="停用账号并撤销全部会话")
    disable.add_argument("--email", required=True)
    disable.add_argument("--confirm", action="store_true")

    reset = commands.add_parser("reset-password", help="重置密码并撤销全部会话")
    reset.add_argument("--email", required=True)
    reset.add_argument("--confirm", action="store_true")

    commands.add_parser("session-preview", help="预览可清理的失效会话")
    prune = commands.add_parser("session-prune", help="清理失效会话")
    prune.add_argument("--confirm", action="store_true")
    return parser


def _settings() -> Settings:
    try:
        settings = get_settings()
    except Exception:
        raise AccountAdministrationError("ACCOUNT_CONFIGURATION_UNAVAILABLE") from None
    if not settings.production_identity_enabled or settings.beta_access_enabled:
        raise AccountAdministrationError("PRODUCTION_IDENTITY_NOT_ACTIVE")
    return settings


def _identity(settings: Settings, *, allow_create: bool) -> SqliteAccountIdentity:
    path = Path(settings.production_identity_db)
    if path.exists():
        # Validate an existing file read-only before the adapter can run schema
        # initialization. This prevents a misconfigured path from being altered.
        AccountSessionMaintenance(database_path=path).preview()
    elif not allow_create:
        raise AccountAdministrationError("ACCOUNT_STORE_UNAVAILABLE")
    return SqliteAccountIdentity(
        database_path=path,
        session_ttl=timedelta(hours=settings.production_session_ttl_hours),
    )


def _secret(prompt: str) -> str:
    first = getpass.getpass(prompt)
    second = getpass.getpass("再次输入新密码：")
    if first != second:
        raise AccountAdministrationError("PASSWORD_CONFIRMATION_MISMATCH")
    return first


def _require_confirmation(confirmed: bool, code: str) -> None:
    if confirmed is not True:
        raise AccountAdministrationError(code)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        settings = _settings()
        if args.action == "session-preview":
            report = AccountSessionMaintenance(
                database_path=settings.production_identity_db
            ).preview()
            output = {"action": args.action, **asdict(report)}
        elif args.action == "session-prune":
            _require_confirmation(
                args.confirm, "ACCOUNT_SESSION_CLEANUP_CONFIRMATION_REQUIRED"
            )
            report = AccountSessionMaintenance(
                database_path=settings.production_identity_db
            ).prune(confirmed=True)
            output = {"action": args.action, **asdict(report)}
        elif args.action == "provision":
            _require_confirmation(args.confirm, "ACCOUNT_PROVISION_CONFIRMATION_REQUIRED")
            command = PersonalAccountProvision(
                email=args.email,
                display_label=args.display_label,
                password=_secret("输入新账号密码："),
            )
            _identity(settings, allow_create=True).provision_personal_account(command)
            output = {"action": "provisioned", "changed": True}
        elif args.action == "disable":
            _require_confirmation(args.confirm, "ACCOUNT_DISABLE_CONFIRMATION_REQUIRED")
            receipt = _identity(settings, allow_create=False).disable_account(
                AccountDisable(email=args.email), confirmed=True
            )
            output = receipt.model_dump()
        else:
            _require_confirmation(
                args.confirm, "PASSWORD_RESET_CONFIRMATION_REQUIRED"
            )
            receipt = _identity(settings, allow_create=False).reset_password(
                AccountPasswordReset(
                    email=args.email,
                    new_password=_secret("输入新密码："),
                ),
                confirmed=True,
            )
            output = receipt.model_dump()
    except ValidationError:
        print(json.dumps({"error": "ACCOUNT_COMMAND_INVALID"}))
        return 2
    except (
        AccountAdministrationError,
        AccountIdentityConflict,
        AccountSessionMaintenanceError,
    ) as error:
        print(json.dumps({"error": str(error)}))
        return 1
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
