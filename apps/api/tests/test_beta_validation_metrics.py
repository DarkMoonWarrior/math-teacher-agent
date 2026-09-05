from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.modules.beta_validation import (
    METRIC_CATALOG,
    METRIC_DEFINITION_VERSION,
    BetaValidationMetrics,
    BetaValidationObservation,
)


class MutableClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def _metrics(tmp_path: Path, clock: MutableClock) -> BetaValidationMetrics:
    return BetaValidationMetrics(
        database_path=tmp_path / "beta-validation.sqlite3",
        identity_secret="synthetic-m13-identity-secret-32-bytes-minimum",
        clock=clock,
    )


def _record(
    metrics: BetaValidationMetrics,
    *,
    owner: str,
    task: str,
    workflow: str,
    event_type: str,
    trust_tier: str | None = None,
    duration_ms: int | None = None,
    model_cost_usd: Decimal = Decimal("0"),
) -> None:
    metrics.record(
        owner_id=owner,
        observation=BetaValidationObservation(
            task_ref=task,
            workflow=workflow,
            event_type=event_type,
            trust_tier=trust_tier,
            duration_ms=duration_ms,
            model_cost_usd=model_cost_usd,
        ),
    )


def test_metric_catalog_freezes_every_product_gate_metric() -> None:
    assert METRIC_DEFINITION_VERSION == "m13.v1"
    assert {item.name for item in METRIC_CATALOG} == {
        "activated_teacher",
        "weekly_verified_teacher_tasks",
        "task_acceptance_rate",
        "search_to_selection_rate",
        "paper_generation_to_export_rate",
        "lesson_generation_to_save_rate",
        "private_library_activation_rate",
        "private_question_authoring_acceptance_rate",
        "week_1_retention",
        "week_4_retention",
        "verified_math_error_rate",
        "agent_tool_failure_rate",
        "average_model_cost_per_teacher",
        "average_model_cost_per_completed_task",
        "p50_latency",
        "p95_latency",
    }
    assert all(item.description and item.numerator and item.denominator for item in METRIC_CATALOG)


def test_observation_contract_rejects_content_and_inconsistent_facts() -> None:
    with pytest.raises(ValidationError):
        BetaValidationObservation.model_validate(
            {
                "task_ref": "task_1",
                "workflow": "search",
                "event_type": "search_completed",
                "prompt": "私人题面不得进入指标",
            }
        )
    with pytest.raises(ValidationError):
        BetaValidationObservation(
            task_ref="这不是不透明任务标识",
            workflow="search",
            event_type="search_completed",
        )
    with pytest.raises(ValidationError):
        BetaValidationObservation(
            task_ref="task_1",
            workflow="lesson",
            event_type="paper_exported",
        )
    with pytest.raises(ValidationError):
        BetaValidationObservation(
            task_ref="task_1",
            workflow="solve",
            event_type="task_completed",
            duration_ms=100,
        )


def test_record_hmacs_identity_and_never_persists_raw_owner_or_task(tmp_path: Path) -> None:
    clock = MutableClock(datetime(2026, 9, 5, tzinfo=timezone.utc))
    metrics = _metrics(tmp_path, clock)
    receipt = metrics.record(
        owner_id="teacher_private_001",
        observation=BetaValidationObservation(
            task_ref="private_task_987",
            workflow="solve",
            event_type="task_completed",
            trust_tier="program_verified",
            duration_ms=800,
        ),
    )

    assert receipt.definition_version == "m13.v1"
    with sqlite3.connect(metrics.database_path) as connection:
        row = connection.execute(
            "SELECT participant_key, task_key FROM m13_beta_validation_events"
        ).fetchone()
    assert row is not None
    assert len(row[0]) == len(row[1]) == 64
    serialized = metrics.database_path.read_bytes()
    assert b"teacher_private_001" not in serialized
    assert b"private_task_987" not in serialized


def test_snapshot_calculates_versioned_gate_metrics_without_identity_output(tmp_path: Path) -> None:
    started = datetime(2026, 7, 1, tzinfo=timezone.utc)
    clock = MutableClock(started)
    metrics = _metrics(tmp_path, clock)

    _record(metrics, owner="teacher_a", task="a_task_1", workflow="search", event_type="task_completed", trust_tier="verified_source", duration_ms=100)
    _record(metrics, owner="teacher_a", task="a_task_1", workflow="search", event_type="task_accepted")
    _record(metrics, owner="teacher_a", task="a_task_1", workflow="search", event_type="search_completed")
    _record(metrics, owner="teacher_a", task="a_task_1", workflow="search", event_type="search_result_selected")
    _record(metrics, owner="teacher_a", task="a_paper", workflow="paper", event_type="paper_generated")
    _record(metrics, owner="teacher_a", task="a_paper", workflow="paper", event_type="paper_exported")
    _record(metrics, owner="teacher_a", task="a_lesson", workflow="lesson", event_type="lesson_generated")
    _record(metrics, owner="teacher_a", task="a_library", workflow="library", event_type="private_library_import_confirmed")
    _record(metrics, owner="teacher_a", task="a_authoring", workflow="authoring", event_type="authoring_completed")
    _record(metrics, owner="teacher_a", task="a_authoring", workflow="authoring", event_type="authoring_saved")
    _record(metrics, owner="teacher_a", task="a_tool_1", workflow="search", event_type="agent_tool_succeeded")
    _record(metrics, owner="teacher_a", task="a_tool_2", workflow="search", event_type="agent_tool_failed")
    _record(metrics, owner="teacher_a", task="a_task_1", workflow="search", event_type="serious_math_error_confirmed", trust_tier="verified_source")
    _record(metrics, owner="teacher_a", task="a_cost", workflow="search", event_type="model_usage", model_cost_usd=Decimal("0.25"))

    _record(metrics, owner="teacher_b", task="b_task_1", workflow="search", event_type="task_completed", trust_tier="model_reviewed", duration_ms=300)
    _record(metrics, owner="teacher_b", task="b_task_1", workflow="search", event_type="task_rejected")
    _record(metrics, owner="teacher_b", task="b_task_1", workflow="search", event_type="search_completed")
    _record(metrics, owner="teacher_b", task="b_tool_1", workflow="search", event_type="agent_tool_succeeded")
    _record(metrics, owner="teacher_b", task="b_cost", workflow="search", event_type="model_usage", model_cost_usd=Decimal("0.15"))

    clock.now = started + timedelta(days=8)
    _record(metrics, owner="teacher_a", task="a_task_2", workflow="solve", event_type="task_completed", trust_tier="program_verified", duration_ms=200)
    clock.now = started + timedelta(days=29)
    _record(metrics, owner="teacher_a", task="a_task_3", workflow="solve", event_type="task_completed", trust_tier="program_verified", duration_ms=400)
    clock.now = started + timedelta(days=36)

    snapshot = metrics.snapshot(window_start=started, window_end=clock.now)
    values = snapshot.metrics

    assert values["activated_teacher"].value == 2
    assert values["weekly_verified_teacher_tasks"].value == 1
    assert values["task_acceptance_rate"].value == 0.5
    assert values["search_to_selection_rate"].value == 0.5
    assert values["paper_generation_to_export_rate"].value == 1
    assert values["lesson_generation_to_save_rate"].value == 0
    assert values["private_library_activation_rate"].value == 0.5
    assert values["private_question_authoring_acceptance_rate"].value == 1
    assert values["week_1_retention"].value == 0.5
    assert values["week_4_retention"].value == 0.5
    assert values["verified_math_error_rate"].value == pytest.approx(1 / 3)
    assert values["agent_tool_failure_rate"].value == pytest.approx(1 / 3)
    assert values["average_model_cost_per_teacher"].value == 0.2
    assert values["average_model_cost_per_completed_task"].value == 0.1
    assert values["p50_latency"].value == 200
    assert values["p95_latency"].value == 400
    assert snapshot.trust_tier_error_rates["verified_source"].value == 1
    assert snapshot.trust_tier_error_rates["program_verified"].value == 0
    assert "teacher_a" not in snapshot.model_dump_json()
    assert "a_task_1" not in snapshot.model_dump_json()


def test_snapshot_requires_timezone_and_nonempty_window(tmp_path: Path) -> None:
    clock = MutableClock(datetime(2026, 9, 5, tzinfo=timezone.utc))
    metrics = _metrics(tmp_path, clock)
    with pytest.raises(ValueError, match="时区"):
        metrics.snapshot(
            window_start=datetime(2026, 9, 1),
            window_end=datetime(2026, 9, 2, tzinfo=timezone.utc),
        )
    with pytest.raises(ValueError, match="结束时间"):
        metrics.snapshot(window_start=clock.now, window_end=clock.now)


def test_latest_acceptance_decision_uses_insertion_order_when_clock_is_equal(
    tmp_path: Path,
) -> None:
    started = datetime(2026, 9, 5, tzinfo=timezone.utc)
    clock = MutableClock(started)
    metrics = _metrics(tmp_path, clock)
    _record(
        metrics,
        owner="teacher_a",
        task="task_1",
        workflow="solve",
        event_type="task_accepted",
    )
    _record(
        metrics,
        owner="teacher_a",
        task="task_1",
        workflow="solve",
        event_type="task_rejected",
    )

    snapshot = metrics.snapshot(
        window_start=started - timedelta(seconds=1),
        window_end=started + timedelta(seconds=1),
    )

    acceptance = snapshot.metrics["task_acceptance_rate"]
    assert acceptance.numerator == 0
    assert acceptance.denominator == 1
    assert acceptance.value == 0
