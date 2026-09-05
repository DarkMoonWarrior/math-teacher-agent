from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import SecretStr

from app.modules.beta_validation import (
    NOTICE_VERSION,
    BetaValidationLifecycleError,
    BetaValidationMetrics,
    BetaValidationNotice,
    BetaValidationObservation,
)
from tests.test_beta_lifecycle import beta_lifecycle  # noqa: F401


SECRET = "synthetic-m13-lifecycle-secret-32-bytes-minimum"


class MutableClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def _metrics(tmp_path, clock) -> BetaValidationMetrics:
    return BetaValidationMetrics(
        database_path=tmp_path / "validation.sqlite3",
        identity_secret=SECRET,
        clock=clock,
    )


def _completed(metrics: BetaValidationMetrics, owner: str, task: str) -> None:
    metrics.record(
        owner_id=owner,
        observation=BetaValidationObservation(
            task_ref=task,
            workflow="solve",
            event_type="task_completed",
            trust_tier="program_verified",
            duration_ms=200,
        ),
    )


def test_collection_requires_current_notice_acknowledgment(tmp_path) -> None:
    clock = MutableClock(datetime(2026, 9, 5, tzinfo=timezone.utc))
    metrics = _metrics(tmp_path, clock)

    with pytest.raises(
        BetaValidationLifecycleError,
        match="NOTICE_ACKNOWLEDGMENT_REQUIRED",
    ):
        _completed(metrics, "teacher_alpha", "task_1")

    participation = metrics.acknowledge(owner_id="teacher_alpha")
    assert participation.notice_version == NOTICE_VERSION
    assert participation.collection_active is True
    _completed(metrics, "teacher_alpha", "task_1")
    assert metrics.export_participant(owner_id="teacher_alpha").event_count == 1


def test_export_is_owner_scoped_aggregated_and_content_free(tmp_path) -> None:
    clock = MutableClock(datetime(2026, 9, 5, tzinfo=timezone.utc))
    metrics = _metrics(tmp_path, clock)
    for owner in ("teacher_alpha", "teacher_beta"):
        metrics.acknowledge(owner_id=owner)
    _completed(metrics, "teacher_alpha", "private_alpha_task")
    _completed(metrics, "teacher_beta", "private_beta_task")
    metrics.record(
        owner_id="teacher_beta",
        observation=BetaValidationObservation(
            task_ref="private_beta_cost",
            workflow="solve",
            event_type="model_usage",
            model_cost_usd=Decimal("9.50"),
        ),
    )

    exported = metrics.export_participant(owner_id="teacher_alpha")
    assert exported.retention_days == 90
    assert exported.event_count == 1
    assert exported.metrics["activated_teacher"].value == 1
    assert exported.metrics["average_model_cost_per_teacher"].value == 0
    serialized = exported.model_dump_json()
    assert "teacher_alpha" not in serialized
    assert "teacher_beta" not in serialized
    assert "private_alpha_task" not in serialized
    assert "private_beta_task" not in serialized


def test_confirmed_exit_deletes_only_current_participant_and_stops_collection(
    tmp_path,
) -> None:
    clock = MutableClock(datetime(2026, 9, 5, tzinfo=timezone.utc))
    metrics = _metrics(tmp_path, clock)
    for owner in ("teacher_alpha", "teacher_beta"):
        metrics.acknowledge(owner_id=owner)
        _completed(metrics, owner, f"{owner}_task")

    with pytest.raises(
        BetaValidationLifecycleError,
        match="DELETE_CONFIRMATION_REQUIRED",
    ):
        metrics.delete_participant(owner_id="teacher_alpha")

    deleted = metrics.delete_participant(
        owner_id="teacher_alpha",
        confirmed=True,
    )
    assert deleted.deleted_events == 1
    assert deleted.participation_removed is True
    assert metrics.export_participant(owner_id="teacher_alpha").event_count == 0
    assert metrics.export_participant(owner_id="teacher_alpha").acknowledged_at is None
    assert metrics.export_participant(owner_id="teacher_beta").event_count == 1
    with pytest.raises(BetaValidationLifecycleError):
        _completed(metrics, "teacher_alpha", "new_task")


def test_teacher_routes_require_session_and_never_cross_export_or_delete(
    beta_lifecycle,
) -> None:
    clients, settings, *_ = beta_lifecycle
    settings.beta_validation_enabled = True
    settings.beta_validation_db = settings.beta_session_db.with_name(
        "validation.sqlite3"
    )
    settings.beta_validation_identity_secret = SecretStr(SECRET)

    assert clients["anonymous"].get(
        "/api/v1/beta-validation/notice"
    ).status_code == 401
    notice = clients["alpha"].get("/api/v1/beta-validation/notice")
    assert notice.status_code == 200
    assert notice.json()["collection_enabled"] is True
    assert clients["alpha"].post(
        "/api/v1/beta-validation/participation"
    ).status_code == 200
    assert clients["beta"].post(
        "/api/v1/beta-validation/participation"
    ).status_code == 200

    metrics = BetaValidationMetrics(
        database_path=settings.beta_validation_db,
        identity_secret=SECRET,
    )
    _completed(metrics, "alpha", "alpha_task")
    _completed(metrics, "beta", "beta_task")

    alpha_export = clients["alpha"].get("/api/v1/beta-validation/export")
    assert alpha_export.status_code == 200
    assert alpha_export.json()["event_count"] == 1
    deleted = clients["alpha"].request(
        "DELETE",
        "/api/v1/beta-validation/participation",
        json={"confirm_delete_my_validation_data": True},
    )
    assert deleted.status_code == 200
    assert deleted.json()["deleted_events"] == 1
    assert clients["beta"].get(
        "/api/v1/beta-validation/export"
    ).json()["event_count"] == 1


def test_notice_is_available_without_opening_disabled_metric_store(
    beta_lifecycle,
) -> None:
    clients, settings, *_ = beta_lifecycle
    settings.beta_validation_enabled = False
    settings.beta_validation_db = settings.beta_session_db.with_name(
        "must-not-exist.sqlite3"
    )

    notice = clients["alpha"].get("/api/v1/beta-validation/notice")
    assert notice.status_code == 200
    assert notice.json() == BetaValidationNotice(
        collection_enabled=False
    ).model_dump(mode="json")
    assert clients["alpha"].post(
        "/api/v1/beta-validation/participation"
    ).status_code == 409
    assert not settings.beta_validation_db.exists()


def test_disabling_collection_preserves_export_and_delete_rights(
    beta_lifecycle,
) -> None:
    clients, settings, *_ = beta_lifecycle
    settings.beta_validation_enabled = True
    settings.beta_validation_db = settings.beta_session_db.with_name(
        "disabled-after-participation.sqlite3"
    )
    settings.beta_validation_identity_secret = SecretStr(SECRET)
    assert clients["alpha"].post(
        "/api/v1/beta-validation/participation"
    ).status_code == 200
    metrics = BetaValidationMetrics(
        database_path=settings.beta_validation_db,
        identity_secret=SECRET,
    )
    _completed(metrics, "alpha", "alpha_task")

    settings.beta_validation_enabled = False
    assert clients["alpha"].get(
        "/api/v1/beta-validation/export"
    ).json()["event_count"] == 1
    deleted = clients["alpha"].request(
        "DELETE",
        "/api/v1/beta-validation/participation",
        json={"confirm_delete_my_validation_data": True},
    )
    assert deleted.status_code == 200
    assert deleted.json()["deleted_events"] == 1
