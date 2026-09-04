from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from app.core.config import get_settings
from app.modules.beta_recovery import (
    BackupContractError,
    BackupIntegrityError,
    BetaBackupRecovery,
    PrivateBackupDestination,
    owner_store_sources,
)


class _PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        # argparse normally echoes unrecognized argument values (potential secrets).
        print(json.dumps({"error": "BACKUP_ARGUMENTS_INVALID"}))
        raise SystemExit(2)


def main() -> int:
    parser = _PrivateArgumentParser(description="Closed Beta private backup operations")
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

    if args.command == "create" and not args.confirm_private_storage:
        print(json.dumps({"error": "PRIVATE_DESTINATION_CONFIRMATION_REQUIRED"}))
        return 2
    try:
        settings = get_settings()
        sources = owner_store_sources(settings)
    except Exception:
        # Settings validation may include raw environment values in its message.
        print(json.dumps({"error": "BACKUP_CONFIGURATION_UNAVAILABLE"}))
        return 1
    try:
        result = _execute(args, settings, BetaBackupRecovery(sources=sources))
    except BackupContractError:
        print(json.dumps({"error": "BACKUP_CONTRACT_REJECTED"}))
        return 1
    except BackupIntegrityError:
        print(json.dumps({"error": "BACKUP_INTEGRITY_FAILED"}))
        return 1
    except (OSError, sqlite3.Error):
        print(json.dumps({"error": "BACKUP_STORAGE_UNAVAILABLE"}))
        return 1
    except Exception:
        # Fail closed without a traceback containing paths, SQL or private data.
        print(json.dumps({"error": "BACKUP_OPERATION_FAILED"}))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _execute(args, settings, service: BetaBackupRecovery):
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
    return result


if __name__ == "__main__":
    raise SystemExit(main())
