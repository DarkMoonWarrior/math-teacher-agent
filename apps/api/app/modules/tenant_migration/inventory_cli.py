"""Read-only owner-data inventory; never exposed to HTTP or Agent."""
from __future__ import annotations

import argparse
import json

from app.core.config import get_settings
from app.modules.tenant_migration import OwnerDataInventory, owner_data_store_specs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="只读清点 M14 owner 数据迁移边界。")
    parser.add_argument("--source-owner-id", required=True)
    args = parser.parse_args(argv)
    try:
        settings = get_settings()
        report = OwnerDataInventory(owner_data_store_specs(settings)).inspect(
            source_owner_id=args.source_owner_id
        )
    except Exception:
        print(json.dumps({"error": "OWNER_DATA_INVENTORY_UNAVAILABLE"}))
        return 1
    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0 if report.blocked_store_count == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
