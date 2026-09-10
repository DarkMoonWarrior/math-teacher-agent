"""Explicit PostgreSQL identity schema deployment; never exposed to HTTP or Agent."""
from __future__ import annotations

import argparse
import json

from app.core.config import get_settings
from app.modules.account_identity.postgres_adapter import (
    PostgresAccountIdentitySchema,
    PostgresIdentitySchemaError,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="预演或明确确认 M14 PostgreSQL 身份 schema。"
    )
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("preview", help="只读检查目标 schema")
    apply = commands.add_parser("apply", help="应用已预演且指纹一致的 schema")
    apply.add_argument("--expected-fingerprint", required=True)
    apply.add_argument("--confirm", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        settings = get_settings()
        if (
            not settings.production_identity_enabled
            or settings.beta_access_enabled
            or settings.production_identity_provider != "postgresql"
        ):
            raise PostgresIdentitySchemaError("POSTGRES_IDENTITY_NOT_ACTIVE")
        schema = PostgresAccountIdentitySchema.from_dsn(
            settings.production_identity_postgres_dsn.get_secret_value()
        )
        if args.action == "preview":
            plan = schema.preview()
        else:
            plan = schema.apply(
                expected_fingerprint=args.expected_fingerprint,
                confirmed=args.confirm,
            )
        output = {
            "action": args.action,
            "state": plan.state,
            "schema_version": plan.schema_version,
            "statement_count": plan.statement_count,
            "fingerprint": plan.fingerprint,
            "changed": plan.changed,
        }
    except Exception as exc:
        if isinstance(exc, PostgresIdentitySchemaError):
            code = str(exc)
        else:
            code = "POSTGRES_IDENTITY_CONFIGURATION_UNAVAILABLE"
        print(json.dumps({"error": code}))
        return 1
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
