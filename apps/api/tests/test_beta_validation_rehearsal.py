from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from types import SimpleNamespace

from pydantic import SecretStr

from app.modules.beta_validation import (
    BetaValidationMetrics,
    run_beta_operations_rehearsal,
)
from app.modules.beta_validation import rehearsal_cli


SECRET = "synthetic-m13-rehearsal-secret-32-bytes-minimum"
NOW = datetime(2026, 9, 8, 12, tzinfo=timezone.utc)


def test_rehearsal_exercises_every_disposable_operations_check(tmp_path) -> None:
    deployment_path = tmp_path / "missing.sqlite3"

    report = run_beta_operations_rehearsal(
        beta_access_enabled=False,
        collection_enabled=False,
        database_path=deployment_path,
        identity_secret="",
        clock=lambda: NOW,
    )

    assert report.synthetic_only is True
    assert report.all_checks_passed is True
    assert {check.name for check in report.checks} == {
        "notice_required",
        "owner_export_isolated",
        "retention_preview_safe",
        "retention_prune_exact",
        "operations_readout_private",
        "owner_exit_exact",
        "temporary_store_removed",
    }
    assert all(check.passed for check in report.checks)
    assert report.deployment.ready_for_invitation is False
    assert report.deployment.blockers == (
        "BETA_ACCESS_DISABLED",
        "COLLECTION_DISABLED",
        "IDENTITY_SECRET_MISSING",
        "METRIC_STORE_MISSING",
    )
    assert not deployment_path.exists()


def test_preflight_reports_ready_only_for_enabled_valid_existing_store(tmp_path) -> None:
    deployment_path = tmp_path / "validation.sqlite3"
    BetaValidationMetrics(
        database_path=deployment_path,
        identity_secret=SECRET,
        clock=lambda: NOW,
    )

    report = run_beta_operations_rehearsal(
        beta_access_enabled=True,
        collection_enabled=True,
        database_path=deployment_path,
        identity_secret=SECRET,
        clock=lambda: NOW,
    )

    assert report.all_checks_passed is True
    assert report.deployment.beta_access_enabled is True
    assert report.deployment.collection_enabled is True
    assert report.deployment.identity_secret_configured is True
    assert report.deployment.metric_store_exists is True
    assert report.deployment.metric_store_readable is True
    assert report.deployment.ready_for_invitation is True
    assert report.deployment.blockers == ()


def test_preflight_rejects_unexpected_store_without_modifying_it(tmp_path) -> None:
    deployment_path = tmp_path / "unrelated.sqlite3"
    with sqlite3.connect(deployment_path) as connection:
        connection.execute("CREATE TABLE private_content (body TEXT)")
        connection.execute("INSERT INTO private_content VALUES ('synthetic-only')")
    before = deployment_path.read_bytes()

    report = run_beta_operations_rehearsal(
        beta_access_enabled=True,
        collection_enabled=True,
        database_path=deployment_path,
        identity_secret=SECRET,
        clock=lambda: NOW,
    )

    assert report.all_checks_passed is True
    assert report.deployment.metric_store_exists is True
    assert report.deployment.metric_store_readable is False
    assert report.deployment.ready_for_invitation is False
    assert report.deployment.blockers == ("METRIC_STORE_UNREADABLE",)
    assert deployment_path.read_bytes() == before


def test_rehearsal_cli_emits_no_secret_path_or_synthetic_identifiers(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    deployment_path = tmp_path / "missing-private-validation.sqlite3"
    monkeypatch.setattr(
        rehearsal_cli,
        "get_settings",
        lambda: SimpleNamespace(
            beta_access_enabled=False,
            beta_validation_enabled=False,
            beta_validation_db=deployment_path,
            beta_validation_identity_secret=SecretStr(SECRET),
        ),
    )

    assert rehearsal_cli.main() == 2
    output = capsys.readouterr().out
    payload = json.loads(output)
    assert payload["all_checks_passed"] is True
    assert payload["deployment"]["ready_for_invitation"] is False
    assert str(deployment_path) not in output
    assert SECRET not in output
    assert "synthetic_teacher_alpha" not in output
    assert "synthetic_alpha_task" not in output
    assert not deployment_path.exists()
