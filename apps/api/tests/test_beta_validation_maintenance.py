from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.modules.beta_validation import (
    BetaValidationMaintenanceError,
    BetaValidationMetrics,
    BetaValidationObservation,
    BetaValidationRetention,
)
from app.modules.beta_validation import maintenance_cli


SECRET = "synthetic-m13-maintenance-secret-32-bytes-minimum"


class MutableClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def _event(metrics: BetaValidationMetrics, owner: str, task: str) -> None:
    metrics.record(
        owner_id=owner,
        observation=BetaValidationObservation(
            task_ref=task,
            workflow="search",
            event_type="search_completed",
        ),
    )


@pytest.fixture
def validation_store(tmp_path):
    now = datetime(2026, 9, 5, tzinfo=timezone.utc)
    clock = MutableClock(now - timedelta(days=91))
    path = tmp_path / "validation.sqlite3"
    metrics = BetaValidationMetrics(
        database_path=path,
        identity_secret=SECRET,
        clock=clock,
    )
    metrics.acknowledge(owner_id="teacher_alpha")
    _event(metrics, "teacher_alpha", "expired_task")
    clock.now = now - timedelta(days=90)
    _event(metrics, "teacher_alpha", "cutoff_task")
    clock.now = now
    _event(metrics, "teacher_alpha", "retained_task")
    return path, now


def _events(path):
    with sqlite3.connect(path) as connection:
        return connection.execute(
            "SELECT event_id, occurred_at FROM m13_beta_validation_events ORDER BY occurred_at"
        ).fetchall()


def test_retention_preview_then_confirm_prunes_only_older_than_90_days(
    validation_store,
) -> None:
    path, now = validation_store
    maintenance = BetaValidationRetention(
        database_path=path,
        clock=lambda: now,
    )
    before = _events(path)
    preview = maintenance.preview()
    assert preview.total_events == 3
    assert preview.expired_events == 1
    assert preview.retained_events == 2
    assert preview.deleted_events == 0
    assert _events(path) == before
    with pytest.raises(
        BetaValidationMaintenanceError,
        match="CONFIRMATION_REQUIRED",
    ):
        maintenance.prune()
    assert maintenance.prune(confirmed=True).deleted_events == 1
    assert _events(path) == before[1:]


def test_malformed_events_are_never_deleted(validation_store) -> None:
    path, now = validation_store
    with sqlite3.connect(path) as connection:
        connection.execute(
            """UPDATE m13_beta_validation_events
               SET participant_key = 'invalid'
               WHERE occurred_at = (SELECT MIN(occurred_at) FROM m13_beta_validation_events)"""
        )
    report = BetaValidationRetention(
        database_path=path,
        clock=lambda: now,
    ).prune(confirmed=True)
    assert report.unclassified_events == 1
    assert report.deleted_events == 0
    assert len(_events(path)) == 3


def test_missing_or_unexpected_store_fails_without_creating_or_changing_data(
    tmp_path,
) -> None:
    missing = tmp_path / "missing.sqlite3"
    with pytest.raises(BetaValidationMaintenanceError):
        BetaValidationRetention(database_path=missing).preview()
    assert not missing.exists()

    unexpected = tmp_path / "private-content.sqlite3"
    with sqlite3.connect(unexpected) as connection:
        connection.execute("CREATE TABLE private_content (body TEXT)")
        connection.execute("INSERT INTO private_content VALUES ('synthetic-only')")
    before = unexpected.read_bytes()
    with pytest.raises(BetaValidationMaintenanceError, match="SCHEMA_UNEXPECTED"):
        BetaValidationRetention(database_path=unexpected).prune(confirmed=True)
    assert unexpected.read_bytes() == before


def test_cli_defaults_to_preview_and_requires_confirmation(
    validation_store,
    monkeypatch,
    capsys,
) -> None:
    path, now = validation_store
    maintenance = BetaValidationRetention(
        database_path=path,
        clock=lambda: now,
    )
    monkeypatch.setattr(
        maintenance_cli,
        "get_settings",
        lambda: SimpleNamespace(beta_validation_db=path),
    )
    monkeypatch.setattr(
        maintenance_cli,
        "BetaValidationRetention",
        lambda **kwargs: maintenance,
    )
    assert maintenance_cli.main([]) == 0
    assert json.loads(capsys.readouterr().out)["deleted_events"] == 0
    assert maintenance_cli.main(["prune"]) == 2
    assert "CONFIRMATION_REQUIRED" in capsys.readouterr().out
    assert maintenance_cli.main(["prune", "--confirm"]) == 0
    assert json.loads(capsys.readouterr().out)["deleted_events"] == 1
