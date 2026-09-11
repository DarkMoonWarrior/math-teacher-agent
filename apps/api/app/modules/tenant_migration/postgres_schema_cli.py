"""Explicit owner-migration schema deployment; no HTTP or Agent entrypoint."""

from __future__ import annotations

import argparse
import json

from app.core.config import get_settings
from app.modules.tenant_migration.postgres_schema import (
    PostgresOwnerMigrationSchema,
    PostgresOwnerMigrationSchemaError,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="预演或明确确认 M14 PostgreSQL owner 迁移落地区域。"
    )
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("preview", help="只读检查目标迁移 schema")
    apply = commands.add_parser("apply", help="应用已预演且指纹一致的 schema")
    apply.add_argument("--expected-fingerprint", required=True)
    apply.add_argument("--confirm", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.action == "apply" and args.confirm is not True:
        _print_error("POSTGRES_OWNER_MIGRATION_SCHEMA_CONFIRMATION_REQUIRED")
        return 2
    try:
        settings = get_settings()
        if (
            not settings.production_identity_enabled
            or settings.beta_access_enabled
            or settings.production_identity_provider != "postgresql"
        ):
            raise PostgresOwnerMigrationSchemaError(
                "POSTGRES_OWNER_MIGRATION_NOT_ACTIVE"
            )
        schema = PostgresOwnerMigrationSchema.from_dsn(
            settings.production_owner_migration_postgres_dsn.get_secret_value()
        )
        if args.action == "preview":
            plan = schema.preview()
        else:
            plan = schema.apply(
                expected_fingerprint=args.expected_fingerprint,
                confirmed=True,
            )
        output = {
            "action": args.action,
            "state": plan.state,
            "schema_version": plan.schema_version,
            "statement_count": plan.statement_count,
            "fingerprint": plan.fingerprint,
            "changed": plan.changed,
        }
    except Exception as error:
        if isinstance(error, PostgresOwnerMigrationSchemaError):
            code = str(error)
        else:
            code = "POSTGRES_OWNER_MIGRATION_CONFIGURATION_UNAVAILABLE"
        _print_error(code)
        return 1
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def _print_error(code: str) -> None:
    print(json.dumps({"error": code}))


if __name__ == "__main__":
    raise SystemExit(main())
