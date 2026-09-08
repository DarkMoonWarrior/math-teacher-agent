from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.core.config import Settings
from app.modules.account_identity import (
    AccountAdministrationError,
    AccountDisable,
    AccountIdentityDenied,
    AccountLogin,
    AccountPasswordReset,
    AccountSessionMaintenance,
    AccountSessionMaintenanceError,
    InMemoryAccountIdentity,
    PersonalAccountProvision,
    SqliteAccountIdentity,
)
from app.modules.account_identity import operator_cli


OLD_PASSWORD = "synthetic-old-password-1234"
NEW_PASSWORD = "synthetic-new-password-5678"


def _provision(identity: object) -> None:
    identity.provision_personal_account(  # type: ignore[attr-defined]
        PersonalAccountProvision(
            email="owner@example.test",
            password=OLD_PASSWORD,
            display_label="测试教师",
        )
    )


@pytest.fixture(params=["memory", "sqlite"])
def lifecycle_identity(request: pytest.FixtureRequest, tmp_path: Path):
    now = [datetime(2026, 9, 9, 1, 0, tzinfo=timezone.utc)]
    if request.param == "memory":
        identity = InMemoryAccountIdentity(
            session_ttl=timedelta(hours=1), clock=lambda: now[0]
        )
    else:
        identity = SqliteAccountIdentity(
            database_path=tmp_path / "identity.sqlite3",
            session_ttl=timedelta(hours=1),
            clock=lambda: now[0],
        )
    _provision(identity)
    return identity


def test_password_reset_requires_confirmation_and_revokes_every_session(
    lifecycle_identity,
) -> None:
    identity = lifecycle_identity
    first = identity.authenticate(
        AccountLogin(email="owner@example.test", password=OLD_PASSWORD)
    )
    second = identity.authenticate(
        AccountLogin(email="owner@example.test", password=OLD_PASSWORD)
    )

    command = AccountPasswordReset(
        email=" OWNER@EXAMPLE.TEST ", new_password=NEW_PASSWORD
    )
    with pytest.raises(
        AccountAdministrationError, match="PASSWORD_RESET_CONFIRMATION_REQUIRED"
    ):
        identity.reset_password(command)

    receipt = identity.reset_password(command, confirmed=True)
    assert receipt.model_dump() == {
        "action": "password_reset",
        "changed": True,
        "revoked_sessions": 2,
    }
    for token in (first.token, second.token):
        with pytest.raises(AccountIdentityDenied):
            identity.resolve(token)
    with pytest.raises(AccountIdentityDenied, match="邮箱或密码无效"):
        identity.authenticate(
            AccountLogin(email="owner@example.test", password=OLD_PASSWORD)
        )
    identity.authenticate(
        AccountLogin(email="owner@example.test", password=NEW_PASSWORD)
    )


def test_disable_requires_confirmation_revokes_sessions_and_blocks_login(
    lifecycle_identity,
) -> None:
    identity = lifecycle_identity
    grant = identity.authenticate(
        AccountLogin(email="owner@example.test", password=OLD_PASSWORD)
    )
    command = AccountDisable(email="owner@example.test")
    with pytest.raises(
        AccountAdministrationError, match="ACCOUNT_DISABLE_CONFIRMATION_REQUIRED"
    ):
        identity.disable_account(command)

    receipt = identity.disable_account(command, confirmed=True)
    assert receipt.action == "disabled"
    assert receipt.revoked_sessions == 1
    with pytest.raises(AccountIdentityDenied):
        identity.resolve(grant.token)
    with pytest.raises(AccountIdentityDenied, match="邮箱或密码无效"):
        identity.authenticate(
            AccountLogin(email="owner@example.test", password=OLD_PASSWORD)
        )
    with pytest.raises(AccountAdministrationError, match="ACCOUNT_NOT_ACTIVE"):
        identity.disable_account(command, confirmed=True)


def _session_store(tmp_path: Path):
    now = [datetime(2026, 9, 9, 1, 0, tzinfo=timezone.utc)]
    database_path = tmp_path / "identity.sqlite3"
    identity = SqliteAccountIdentity(
        database_path=database_path,
        session_ttl=timedelta(hours=1),
        clock=lambda: now[0],
    )
    _provision(identity)
    grants = [
        identity.authenticate(
            AccountLogin(email="owner@example.test", password=OLD_PASSWORD)
        )
        for _ in range(4)
    ]
    identity.revoke(grants[1].token)
    with sqlite3.connect(database_path) as connection:
        hashes = connection.execute(
            "SELECT token_hash FROM m14_account_sessions ORDER BY rowid"
        ).fetchall()
        connection.execute(
            "UPDATE m14_account_sessions SET expires_at = ? WHERE token_hash = ?",
            ((now[0] - timedelta(minutes=1)).isoformat(), hashes[2][0]),
        )
        connection.execute(
            "UPDATE m14_account_sessions SET expires_at = 'not-a-time' WHERE token_hash = ?",
            (hashes[3][0],),
        )
    return database_path, now


def test_account_session_cleanup_previews_then_requires_confirmation_and_prunes(
    tmp_path: Path,
) -> None:
    database_path, now = _session_store(tmp_path)
    maintenance = AccountSessionMaintenance(
        database_path=database_path, clock=lambda: now[0]
    )

    preview = maintenance.preview()
    assert (preview.total, preview.active, preview.revoked) == (4, 1, 1)
    assert (preview.expired, preview.unclassified, preview.deleted) == (1, 1, 0)
    with pytest.raises(
        AccountSessionMaintenanceError,
        match="ACCOUNT_SESSION_CLEANUP_CONFIRMATION_REQUIRED",
    ):
        maintenance.prune()

    report = maintenance.prune(confirmed=True)
    assert report.deleted == 2
    after = maintenance.preview()
    assert (after.total, after.active, after.unclassified) == (2, 1, 1)


def test_account_session_maintenance_does_not_create_or_accept_another_schema(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing.sqlite3"
    with pytest.raises(
        AccountSessionMaintenanceError, match="ACCOUNT_SESSION_STORE_UNAVAILABLE"
    ):
        AccountSessionMaintenance(database_path=missing).preview()
    assert not missing.exists()

    wrong = tmp_path / "wrong.sqlite3"
    with sqlite3.connect(wrong) as connection:
        connection.execute("CREATE TABLE unrelated (value TEXT)")
    with pytest.raises(
        AccountSessionMaintenanceError, match="ACCOUNT_SESSION_STORE_SCHEMA_UNEXPECTED"
    ):
        AccountSessionMaintenance(database_path=wrong).preview()


def test_operator_cli_prompts_for_password_and_returns_non_identifying_receipts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = Settings(
        production_identity_enabled=True,
        beta_access_enabled=False,
        production_identity_db=tmp_path / "identity.sqlite3",
    )
    monkeypatch.setattr(operator_cli, "get_settings", lambda: settings)
    secrets = iter([OLD_PASSWORD, OLD_PASSWORD, NEW_PASSWORD, NEW_PASSWORD])
    monkeypatch.setattr(operator_cli.getpass, "getpass", lambda _prompt: next(secrets))

    assert operator_cli.main(
        [
            "provision",
            "--email",
            "owner@example.test",
            "--display-label",
            "测试教师",
            "--confirm",
        ]
    ) == 0
    provision_output = capsys.readouterr().out
    assert json.loads(provision_output) == {"action": "provisioned", "changed": True}
    assert "owner@example.test" not in provision_output
    assert "acct_" not in provision_output
    assert OLD_PASSWORD not in provision_output

    identity = SqliteAccountIdentity(
        database_path=settings.production_identity_db,
        session_ttl=timedelta(hours=1),
    )
    identity.authenticate(
        AccountLogin(email="owner@example.test", password=OLD_PASSWORD)
    )
    assert operator_cli.main(
        ["reset-password", "--email", "owner@example.test", "--confirm"]
    ) == 0
    reset_output = capsys.readouterr().out
    assert json.loads(reset_output) == {
        "action": "password_reset",
        "changed": True,
        "revoked_sessions": 1,
    }
    assert NEW_PASSWORD not in reset_output


def test_operator_cli_refuses_mutations_without_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = Settings(
        production_identity_enabled=True,
        beta_access_enabled=False,
        production_identity_db=tmp_path / "identity.sqlite3",
    )
    monkeypatch.setattr(operator_cli, "get_settings", lambda: settings)
    assert operator_cli.main(
        ["disable", "--email", "owner@example.test"]
    ) == 1
    assert json.loads(capsys.readouterr().out) == {
        "error": "ACCOUNT_DISABLE_CONFIRMATION_REQUIRED"
    }
    assert not settings.production_identity_db.exists()


def test_operator_cli_does_not_mutate_an_unexpected_existing_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    database_path = tmp_path / "unexpected.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE unrelated (value TEXT)")
        connection.execute("INSERT INTO unrelated VALUES ('preserve-me')")
    settings = Settings(
        production_identity_enabled=True,
        beta_access_enabled=False,
        production_identity_db=database_path,
    )
    monkeypatch.setattr(operator_cli, "get_settings", lambda: settings)

    assert operator_cli.main(
        ["disable", "--email", "owner@example.test", "--confirm"]
    ) == 1
    assert json.loads(capsys.readouterr().out) == {
        "error": "ACCOUNT_SESSION_STORE_SCHEMA_UNEXPECTED"
    }
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT value FROM unrelated").fetchone()[0] == "preserve-me"
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert tables == {"unrelated"}
