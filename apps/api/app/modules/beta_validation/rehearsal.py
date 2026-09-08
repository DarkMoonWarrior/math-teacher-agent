"""Disposable M13 operations rehearsal; never uses teacher content or a real store."""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from app.modules.beta_validation.maintenance import (
    BetaValidationMaintenanceError,
    BetaValidationRetention,
)
from app.modules.beta_validation.metrics import (
    BetaValidationLifecycleError,
    BetaValidationMetrics,
)
from app.modules.beta_validation.schemas import (
    BetaDeploymentPreflight,
    BetaOperationsRehearsalCheck,
    BetaOperationsRehearsalReport,
    BetaRehearsalBlocker,
    BetaValidationObservation,
)


_SYNTHETIC_SECRET = "m13-disposable-rehearsal-secret-32-bytes-minimum"


class _MutableClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("BETA_VALIDATION_REHEARSAL_CLOCK_TIMEZONE_REQUIRED")
    return value.astimezone(timezone.utc)


def _deployment_preflight(
    *,
    beta_access_enabled: bool,
    collection_enabled: bool,
    database_path: Path,
    identity_secret: str,
    now: datetime,
) -> BetaDeploymentPreflight:
    secret_configured = len(identity_secret) >= 32
    store_exists = database_path.is_file()
    store_readable = False
    if secret_configured and store_exists:
        try:
            BetaValidationRetention(
                database_path=database_path,
                clock=lambda: now,
            ).preview()
            metrics = BetaValidationMetrics(
                database_path=database_path,
                identity_secret=identity_secret,
                clock=lambda: now,
                read_only=True,
            )
            metrics.private_operations_readout(
                window_start=now - timedelta(days=90),
                window_end=now,
            )
            store_readable = True
        except (BetaValidationMaintenanceError, OSError, ValueError):
            store_readable = False

    blockers: list[BetaRehearsalBlocker] = []
    if not beta_access_enabled:
        blockers.append("BETA_ACCESS_DISABLED")
    if not collection_enabled:
        blockers.append("COLLECTION_DISABLED")
    if not secret_configured:
        blockers.append("IDENTITY_SECRET_MISSING")
    if not store_exists:
        blockers.append("METRIC_STORE_MISSING")
    elif not store_readable:
        blockers.append("METRIC_STORE_UNREADABLE")
    return BetaDeploymentPreflight(
        beta_access_enabled=beta_access_enabled,
        collection_enabled=collection_enabled,
        identity_secret_configured=secret_configured,
        metric_store_exists=store_exists,
        metric_store_readable=store_readable,
        ready_for_invitation=not blockers,
        blockers=tuple(blockers),
    )


def run_beta_operations_rehearsal(
    *,
    beta_access_enabled: bool,
    collection_enabled: bool,
    database_path: Path,
    identity_secret: str,
    clock: Callable[[], datetime] | None = None,
) -> BetaOperationsRehearsalReport:
    """Exercise the M13 operator lifecycle in an isolated temporary database.

    The configured deployment store is only checked in read-only mode. Every
    mutation below targets a disposable synthetic database removed before the
    report is returned.
    """

    now = _utc((clock or (lambda: datetime.now(timezone.utc)))())
    checks: list[BetaOperationsRehearsalCheck] = []
    with TemporaryDirectory(prefix="m13-beta-rehearsal-") as directory:
        rehearsal_path = Path(directory) / "validation.sqlite3"
        synthetic_clock = _MutableClock(now - timedelta(days=91))
        metrics = BetaValidationMetrics(
            database_path=rehearsal_path,
            identity_secret=_SYNTHETIC_SECRET,
            clock=synthetic_clock,
        )
        try:
            metrics.record(
                owner_id="synthetic_unacknowledged",
                observation=BetaValidationObservation(
                    task_ref="synthetic_unacknowledged_task",
                    workflow="search",
                    event_type="search_completed",
                ),
            )
            notice_required = False
        except BetaValidationLifecycleError as error:
            notice_required = (
                str(error) == "BETA_VALIDATION_NOTICE_ACKNOWLEDGMENT_REQUIRED"
            )
        checks.append(
            BetaOperationsRehearsalCheck(
                name="notice_required",
                passed=notice_required,
            )
        )

        owner_alpha = "synthetic_teacher_alpha"
        owner_beta = "synthetic_teacher_beta"
        metrics.acknowledge(owner_id=owner_alpha)
        metrics.record(
            owner_id=owner_alpha,
            observation=BetaValidationObservation(
                task_ref="synthetic_expired_search",
                workflow="search",
                event_type="search_completed",
            ),
        )
        synthetic_clock.now = now
        metrics.acknowledge(owner_id=owner_beta)
        metrics.record(
            owner_id=owner_alpha,
            observation=BetaValidationObservation(
                task_ref="synthetic_alpha_task",
                workflow="solve",
                event_type="task_completed",
                trust_tier="program_verified",
                duration_ms=240,
            ),
        )
        metrics.record(
            owner_id=owner_alpha,
            observation=BetaValidationObservation(
                task_ref="synthetic_alpha_task",
                workflow="solve",
                event_type="task_accepted",
            ),
        )
        metrics.record(
            owner_id=owner_beta,
            observation=BetaValidationObservation(
                task_ref="synthetic_beta_task",
                workflow="search",
                event_type="task_completed",
                trust_tier="verified_source",
                duration_ms=180,
            ),
        )

        alpha_export = metrics.export_participant(owner_id=owner_alpha)
        beta_export = metrics.export_participant(owner_id=owner_beta)
        export_json = alpha_export.model_dump_json()
        checks.append(
            BetaOperationsRehearsalCheck(
                name="owner_export_isolated",
                passed=(
                    alpha_export.event_count == 2
                    and beta_export.event_count == 1
                    and owner_alpha not in export_json
                    and owner_beta not in export_json
                    and "synthetic_alpha_task" not in export_json
                ),
            )
        )

        read_only_metrics = BetaValidationMetrics(
            database_path=rehearsal_path,
            identity_secret=_SYNTHETIC_SECRET,
            clock=synthetic_clock,
            read_only=True,
        )
        operations = read_only_metrics.private_operations_readout(
            window_start=now - timedelta(days=90),
            window_end=now + timedelta(microseconds=1),
        )
        operations_json = operations.model_dump_json()
        checks.append(
            BetaOperationsRehearsalCheck(
                name="operations_readout_private",
                passed=(
                    operations.event_count == 3
                    and operations.activated_teachers == 2
                    and owner_alpha not in operations_json
                    and owner_beta not in operations_json
                    and "synthetic_alpha_task" not in operations_json
                ),
            )
        )

        retention = BetaValidationRetention(
            database_path=rehearsal_path,
            clock=synthetic_clock,
        )
        preview = retention.preview()
        checks.append(
            BetaOperationsRehearsalCheck(
                name="retention_preview_safe",
                passed=(
                    preview.total_events == 4
                    and preview.expired_events == 1
                    and preview.retained_events == 3
                    and preview.deleted_events == 0
                ),
            )
        )
        pruned = retention.prune(confirmed=True)
        checks.append(
            BetaOperationsRehearsalCheck(
                name="retention_prune_exact",
                passed=(
                    pruned.deleted_events == 1
                    and retention.preview().total_events == 3
                ),
            )
        )

        deleted = metrics.delete_participant(owner_id=owner_alpha, confirmed=True)
        checks.append(
            BetaOperationsRehearsalCheck(
                name="owner_exit_exact",
                passed=(
                    deleted.deleted_events == 2
                    and deleted.participation_removed
                    and metrics.export_participant(owner_id=owner_alpha).event_count == 0
                    and metrics.export_participant(owner_id=owner_beta).event_count == 1
                ),
            )
        )

    checks.append(
        BetaOperationsRehearsalCheck(
            name="temporary_store_removed",
            passed=not rehearsal_path.exists(),
        )
    )
    deployment = _deployment_preflight(
        beta_access_enabled=beta_access_enabled,
        collection_enabled=collection_enabled,
        database_path=database_path,
        identity_secret=identity_secret,
        now=now,
    )
    return BetaOperationsRehearsalReport(
        generated_at=now,
        all_checks_passed=all(check.passed for check in checks),
        checks=tuple(checks),
        deployment=deployment,
    )
