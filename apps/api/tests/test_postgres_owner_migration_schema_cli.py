from __future__ import annotations

import json
from dataclasses import replace

import pytest

from app.core.config import Settings
from app.modules.tenant_migration import postgres_schema_cli
from app.modules.tenant_migration.postgres_schema import (
    POSTGRES_OWNER_MIGRATION_SCHEMA_VERSION,
    PostgresOwnerMigrationSchemaError,
    PostgresOwnerMigrationSchemaPlan,
)


def _settings(dsn: str = "postgresql://operator:secret@example.invalid/app"):
    return Settings(
        production_identity_enabled=True,
        production_identity_provider="postgresql",
        production_owner_migration_postgres_dsn=dsn,
    )


def test_cli_previews_then_applies_only_the_matching_plan(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[tuple[str, object]] = []
    fingerprint = "a" * 64
    plan = PostgresOwnerMigrationSchemaPlan(
        state="empty",
        schema_version=POSTGRES_OWNER_MIGRATION_SCHEMA_VERSION,
        statement_count=9,
        fingerprint=fingerprint,
    )

    class Schema:
        @classmethod
        def from_dsn(cls, dsn: str):
            calls.append(("dsn", dsn))
            return cls()

        def preview(self):
            calls.append(("preview", None))
            return plan

        def apply(self, *, expected_fingerprint: str, confirmed: bool):
            calls.append(("apply", (expected_fingerprint, confirmed)))
            return replace(plan, state="current", changed=True)

    monkeypatch.setattr(postgres_schema_cli, "get_settings", _settings)
    monkeypatch.setattr(postgres_schema_cli, "PostgresOwnerMigrationSchema", Schema)

    assert postgres_schema_cli.main(["preview"]) == 0
    preview = json.loads(capsys.readouterr().out)
    assert preview["fingerprint"] == fingerprint
    assert preview["changed"] is False

    assert (
        postgres_schema_cli.main(
            ["apply", "--expected-fingerprint", fingerprint, "--confirm"]
        )
        == 0
    )
    applied = json.loads(capsys.readouterr().out)
    assert applied["state"] == "current"
    assert applied["changed"] is True
    assert calls[-1] == ("apply", (fingerprint, True))
    assert "secret" not in json.dumps((preview, applied))


def test_cli_rejects_unconfirmed_apply_before_loading_private_settings(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_settings():
        raise AssertionError("settings must not load before confirmation")

    monkeypatch.setattr(postgres_schema_cli, "get_settings", fail_settings)
    result = postgres_schema_cli.main(
        ["apply", "--expected-fingerprint", "a" * 64]
    )

    assert result == 2
    assert json.loads(capsys.readouterr().out) == {
        "error": "POSTGRES_OWNER_MIGRATION_SCHEMA_CONFIRMATION_REQUIRED"
    }


@pytest.mark.parametrize(
    ("settings", "error"),
    (
        (Settings(), "POSTGRES_OWNER_MIGRATION_NOT_ACTIVE"),
        (
            _settings(""),
            "POSTGRES_OWNER_MIGRATION_DSN_REQUIRED",
        ),
    ),
)
def test_cli_fails_closed_without_an_active_dedicated_target(
    settings: Settings,
    error: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(postgres_schema_cli, "get_settings", lambda: settings)

    assert postgres_schema_cli.main(["preview"]) == 1
    assert json.loads(capsys.readouterr().out) == {"error": error}
