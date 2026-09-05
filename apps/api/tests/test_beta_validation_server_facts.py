from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from app.modules.beta_validation import BetaValidationFacts, BetaValidationMetrics


SECRET = "m13-server-fact-tests-use-an-isolated-secret"


def _metrics(tmp_path) -> BetaValidationMetrics:
    return BetaValidationMetrics(
        database_path=tmp_path / "facts.sqlite3",
        identity_secret=SECRET,
        clock=lambda: datetime(2026, 9, 6, 8, 0, tzinfo=timezone.utc),
    )


def test_disabled_server_facts_are_a_noop() -> None:
    result = BetaValidationFacts.disabled().record_checkpoint(
        owner_id="teacher_1",
        fact="search_completed",
        task_ref="search_run_1",
        duration_ms=120,
        trust_tier="teacher_review_required",
    )

    assert result.state == "disabled"
    assert result.recorded_events == 0


def test_server_facts_require_current_participation_without_breaking_workflow(
    tmp_path,
) -> None:
    result = BetaValidationFacts(_metrics(tmp_path)).record_checkpoint(
        owner_id="teacher_1",
        fact="solve_completed",
        task_ref="solve_run_1",
        duration_ms=250,
        trust_tier="program_verified",
    )

    assert result.state == "not_participating"


def test_completion_checkpoint_records_primary_and_completion_atomically(
    tmp_path,
) -> None:
    metrics = _metrics(tmp_path)
    metrics.acknowledge(owner_id="teacher_1")

    result = BetaValidationFacts(metrics).record_checkpoint(
        owner_id="teacher_1",
        fact="search_completed",
        task_ref="search_run_1",
        duration_ms=120,
        trust_tier="teacher_review_required",
    )

    assert result.state == "recorded"
    assert result.recorded_events == 2
    exported = metrics.export_participant(owner_id="teacher_1")
    assert exported.event_count == 2
    assert exported.metrics["activated_teacher"].value == 1
    assert exported.metrics["search_to_selection_rate"].denominator == 1

    with sqlite3.connect(metrics.database_path) as connection:
        rows = connection.execute(
            "SELECT event_type, task_key FROM m13_beta_validation_events ORDER BY rowid"
        ).fetchall()
    assert [row[0] for row in rows] == ["search_completed", "task_completed"]
    assert rows[0][1] == rows[1][1]


def test_invalid_completion_fact_is_ignored() -> None:
    class RecordingMustNotRun:
        def _record_batch(self, **_kwargs):
            raise AssertionError("invalid fact must not reach storage")

    result = BetaValidationFacts(RecordingMustNotRun()).record_checkpoint(
        owner_id="teacher_1",
        fact="authoring_completed",
        task_ref="draft_1",
    )

    assert result.state == "invalid"


def test_agent_tool_outcomes_are_derived_from_server_call_count(tmp_path) -> None:
    metrics = _metrics(tmp_path)
    metrics.acknowledge(owner_id="teacher_1")
    facts = BetaValidationFacts(metrics)

    completed = facts.record_checkpoint(
        owner_id="teacher_1",
        fact="solve_completed",
        task_ref="solve_run_2",
        duration_ms=240,
        trust_tier="program_verified",
        tool_call_count=2,
    )
    failed = facts.record_tool_failure(
        owner_id="teacher_1",
        workflow="solve",
        task_ref="solve_run_3",
        tool_call_count=1,
    )

    assert completed.recorded_events == 3
    assert failed.recorded_events == 1
    exported = metrics.export_participant(owner_id="teacher_1")
    rate = exported.metrics["agent_tool_failure_rate"]
    assert rate.numerator == 1
    assert rate.denominator == 3
    assert rate.value == 1 / 3
