"""Digest-only owner migration planning; never exposed to HTTP or Agent."""
from __future__ import annotations

import argparse
import json

from app.core.config import get_settings
from app.modules.tenant_migration import (
    OwnerMigrationPlanner,
    owner_data_store_specs,
    owner_file_store_specs,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="只读生成 M14 owner 逐对象迁移计划；不执行写入。"
    )
    parser.add_argument("--source-owner-id", required=True)
    parser.add_argument("--target-owner-id", required=True)
    parser.add_argument("--target-tenant-id", required=True)
    parser.add_argument("--inventory-fingerprint", required=True)
    parser.add_argument("--file-reconciliation-fingerprint", required=True)
    args = parser.parse_args(argv)
    try:
        settings = get_settings()
        report = OwnerMigrationPlanner(
            owner_data_store_specs(settings),
            owner_file_store_specs(settings),
        ).plan(
            source_owner_id=args.source_owner_id,
            target_owner_id=args.target_owner_id,
            target_tenant_id=args.target_tenant_id,
            expected_inventory_fingerprint=args.inventory_fingerprint,
            expected_file_reconciliation_fingerprint=(
                args.file_reconciliation_fingerprint
            ),
        )
    except Exception:
        print(json.dumps({"error": "OWNER_MIGRATION_PLAN_UNAVAILABLE"}))
        return 1
    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
