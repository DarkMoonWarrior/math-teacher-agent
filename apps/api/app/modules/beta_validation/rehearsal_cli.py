from __future__ import annotations

import json

from app.core.config import get_settings
from app.modules.beta_validation.rehearsal import run_beta_operations_rehearsal


def main() -> int:
    try:
        settings = get_settings()
        report = run_beta_operations_rehearsal(
            beta_access_enabled=settings.beta_access_enabled,
            collection_enabled=settings.beta_validation_enabled,
            database_path=settings.beta_validation_db,
            identity_secret=(
                settings.beta_validation_identity_secret.get_secret_value()
            ),
        )
    except Exception:
        print(json.dumps({"error": "BETA_VALIDATION_REHEARSAL_FAILED"}))
        return 1
    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
    if not report.all_checks_passed:
        return 1
    return 0 if report.deployment.ready_for_invitation else 2


if __name__ == "__main__":
    raise SystemExit(main())
