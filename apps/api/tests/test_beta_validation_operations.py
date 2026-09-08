from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from pydantic import SecretStr

from app.modules.beta_validation import BetaValidationMetrics, BetaValidationObservation
from app.modules.beta_validation import operations_cli


SECRET = "synthetic-m13-operations-secret-32-bytes-minimum"


class MutableClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def _complete(metrics: BetaValidationMetrics, owner: str, task: str) -> None:
    metrics.acknowledge(owner_id=owner)
    metrics.record(
        owner_id=owner,
        observation=BetaValidationObservation(
            task_ref=task,
            workflow="solve",
            event_type="task_completed",
            trust_tier="program_verified",
            duration_ms=120,
        ),
    )


def test_private_operations_readout_is_aggregate_only_and_shows_denominators(tmp_path) -> None:
    started = datetime(2026, 7, 6, 9, tzinfo=timezone.utc)
    clock = MutableClock(started)
    metrics = BetaValidationMetrics(
        database_path=tmp_path / "validation.sqlite3",
        identity_secret=SECRET,
        clock=clock,
    )
    _complete(metrics, "teacher_private_alpha", "private_task_alpha")
    clock.now = started + timedelta(days=8)
    _complete(metrics, "teacher_private_alpha", "private_task_alpha_week_1")
    clock.now = started + timedelta(days=36)

    report = metrics.private_operations_readout(
        window_start=started - timedelta(days=1),
        window_end=clock.now,
    )

    assert report.event_count == 2
    assert report.acknowledged_participants == 1
    assert report.activated_teachers == 1
    assert report.sample_status == "below_target"
    assert len(report.cohorts) == 1
    cohort = report.cohorts[0]
    assert cohort.activated_teachers == 1
    assert cohort.week_1_retention.numerator == 1
    assert cohort.week_1_retention.denominator == 1
    assert cohort.week_4_retention.value == 0
    serialized = report.model_dump_json()
    assert "teacher_private_alpha" not in serialized
    assert "private_task_alpha" not in serialized


def test_private_operations_empty_readout_keeps_zero_denominators_visible(tmp_path) -> None:
    now = datetime(2026, 9, 8, tzinfo=timezone.utc)
    metrics = BetaValidationMetrics(
        database_path=tmp_path / "validation.sqlite3",
        identity_secret=SECRET,
        clock=lambda: now,
    )

    report = metrics.private_operations_readout(
        window_start=now - timedelta(days=90),
        window_end=now,
    )

    assert report.sample_status == "empty"
    assert report.activated_teachers == 0
    assert report.metrics["task_acceptance_rate"].value is None
    assert report.metrics["task_acceptance_rate"].denominator == 0
    assert report.cohorts == ()


def test_private_operations_cli_outputs_only_aggregate_report(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    database_path = tmp_path / "validation.sqlite3"
    metrics = BetaValidationMetrics(
        database_path=database_path,
        identity_secret=SECRET,
    )
    _complete(metrics, "teacher_private_beta", "private_task_beta")
    monkeypatch.setattr(
        operations_cli,
        "get_settings",
        lambda: SimpleNamespace(
            beta_validation_db=database_path,
            beta_validation_identity_secret=SecretStr(SECRET),
        ),
    )

    assert operations_cli.main(["--days", "30"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["activated_teachers"] == 1
    assert payload["metrics"]["task_acceptance_rate"]["denominator"] == 0
    serialized = json.dumps(payload)
    assert "teacher_private_beta" not in serialized
    assert "private_task_beta" not in serialized


def test_private_operations_cli_never_creates_a_missing_store(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    database_path = tmp_path / "missing.sqlite3"
    monkeypatch.setattr(
        operations_cli,
        "get_settings",
        lambda: SimpleNamespace(
            beta_validation_db=database_path,
            beta_validation_identity_secret=SecretStr(SECRET),
        ),
    )

    assert operations_cli.main([]) == 1
    assert json.loads(capsys.readouterr().out) == {
        "error": "BETA_VALIDATION_OPERATIONS_UNAVAILABLE"
    }
    assert not database_path.exists()
