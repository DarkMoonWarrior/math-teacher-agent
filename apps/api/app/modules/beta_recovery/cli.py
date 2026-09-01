from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.core.config import get_settings
from app.modules.beta_recovery import (
    BetaBackupRecovery,
    PrivateBackupDestination,
    owner_store_sources,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Closed Beta private backup operations")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("inventory")
    create = commands.add_parser("create")
    create.add_argument("--destination", type=Path)
    create.add_argument("--confirm-private-storage", action="store_true")
    verify = commands.add_parser("verify")
    verify.add_argument("backup", type=Path)
    drill = commands.add_parser("drill")
    drill.add_argument("backup", type=Path)
    args = parser.parse_args()

    settings = get_settings()
    service = BetaBackupRecovery(sources=owner_store_sources(settings))
    if args.command == "inventory":
        result = [item.model_dump(mode="json") for item in service.inventory()]
    elif args.command == "create":
        destination = PrivateBackupDestination(
            args.destination or settings.beta_backup_dir,
            private_storage_confirmed=args.confirm_private_storage,
        )
        manifest = service.create_backup(destination)
        result = service.verify_backup(
            destination.root / manifest.backup_id
        ).model_dump(mode="json")
    elif args.command == "verify":
        result = service.verify_backup(args.backup).model_dump(mode="json")
    else:
        result = service.restore_drill(args.backup).model_dump(mode="json")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
