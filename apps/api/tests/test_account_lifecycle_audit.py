from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import get_type_hints

import pytest

from app.core.config import Settings
from app.modules.account_identity import (
    AccountAdministration,
    AccountAdministrationError,
    AccountDisable,
    AccountIdentityDenied,
    AccountLifecycleAuditError,
    AccountLogin,
    AuditedAccountAdministration,
    PersonalAccountProvision,
    SqliteAccountIdentity,
    SqliteAccountLifecycleAudit,
)
from app.modules.account_identity import operator_cli


PASSWORD = "synthetic-password-1234"
AUDIT_SECRET = "synthetic-account-audit-secret-32-bytes-minimum"


def _identity(tmp_path: Path) -> SqliteAccountIdentity:
    return SqliteAccountIdentity(
        database_path=tmp_path / "identity.sqlite3",
        session_ttl=timedelta(hours=1),
    )


def _audit(tmp_path: Path) -> SqliteAccountLifecycleAudit:
    return SqliteAccountLifecycleAudit(
        database_path=tmp_path / "account-audit.sqlite3",
        secret=AUDIT_SECRET,
    )


def test_account_administration_owns_password_reset_not_login_protection() -> None:
    administration = AccountAdministration.__dict__
    assert "reset_password" in administration
    from app.modules.account_identity import AccountLoginProtection

    assert "reset_password" not in AccountLoginProtection.__dict__
    assert get_type_hints(administration["reset_password"])["return"].__name__ == (
        "AccountLifecycleReceipt"
    )


def test_audited_administration_records_success_and_failure_without_raw_identity(
    tmp_path: Path,
) -> None:
    identity = _identity(tmp_path)
    audit = _audit(tmp_path)
    administration = AuditedAccountAdministration(
        administration=identity,
        audit=audit,
        operator_label="Production Admin One",
    )
    command = PersonalAccountProvision(
        email="Sensitive.Owner@Example.Test",
        password=PASSWORD,
        display_label="测试教师",
    )
    administration.provision_personal_account(command)
    grant = identity.authenticate(
        AccountLogin(email=command.email, password=PASSWORD)
    )
    receipt = administration.disable_account(
        AccountDisable(email=command.email), confirmed=True
    )
    assert receipt.revoked_sessions == 1
    with pytest.raises(AccountAdministrationError, match="ACCOUNT_NOT_ACTIVE"):
        administration.disable_account(
            AccountDisable(email=command.email), confirmed=True
        )

    summary = audit.summary()
    assert summary["total"] == 3
    assert summary["provision_succeeded"] == 1
    assert summary["disable_succeeded"] == 1
    assert summary["disable_failed"] == 1
    with sqlite3.connect(tmp_path / "account-audit.sqlite3") as connection:
        rows = connection.execute(
            "SELECT action, outcome, operator_hash, target_hash, changed, "
            "affected_sessions FROM m14_account_lifecycle_audit ORDER BY rowid"
        ).fetchall()
    assert rows[1][:2] == ("disable", "succeeded")
    assert rows[1][4:] == (1, 1)
    assert all(len(row[2]) == len(row[3]) == 64 for row in rows)
    database_bytes = (tmp_path / "account-audit.sqlite3").read_bytes()
    for forbidden in (
        b"Sensitive.Owner",
        b"sensitive.owner",
        b"Production Admin One",
        b"production admin one",
        PASSWORD.encode("utf-8"),
        grant.token.encode("utf-8"),
        AUDIT_SECRET.encode("utf-8"),
    ):
        assert forbidden not in database_bytes


def test_audit_failure_before_begin_prevents_account_mutation(tmp_path: Path) -> None:
    identity = _identity(tmp_path)

    class UnavailableAudit:
        def begin(self, **_kwargs) -> str:
            raise AccountLifecycleAuditError("ACCOUNT_AUDIT_UNAVAILABLE")

    administration = AuditedAccountAdministration(
        administration=identity,
        audit=UnavailableAudit(),  # type: ignore[arg-type]
        operator_label="local-admin",
    )
    with pytest.raises(AccountLifecycleAuditError, match="ACCOUNT_AUDIT_UNAVAILABLE"):
        administration.provision_personal_account(
            PersonalAccountProvision(
                email="owner@example.test",
                password=PASSWORD,
                display_label="测试教师",
            )
        )
    with pytest.raises(AccountIdentityDenied):
        identity.authenticate(
            AccountLogin(email="owner@example.test", password=PASSWORD)
        )


def test_existing_wrong_audit_store_is_rejected_without_mutation(tmp_path: Path) -> None:
    path = tmp_path / "wrong.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE unrelated (value TEXT)")
        connection.execute("INSERT INTO unrelated VALUES ('preserve-me')")
    with pytest.raises(
        AccountLifecycleAuditError, match="ACCOUNT_AUDIT_SCHEMA_UNEXPECTED"
    ):
        SqliteAccountLifecycleAudit(database_path=path, secret=AUDIT_SECRET)
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT value FROM unrelated").fetchone()[0] == (
            "preserve-me"
        )
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert tables == {"unrelated"}


def test_existing_audit_store_with_trigger_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "triggered.sqlite3"
    SqliteAccountLifecycleAudit(database_path=path, secret=AUDIT_SECRET)
    with sqlite3.connect(path) as connection:
        connection.execute(
            """CREATE TRIGGER unexpected_audit_trigger
               AFTER INSERT ON m14_account_lifecycle_audit
               BEGIN
                   UPDATE m14_account_lifecycle_audit
                   SET changed = 0 WHERE event_id = NEW.event_id;
               END"""
        )
    with pytest.raises(
        AccountLifecycleAuditError, match="ACCOUNT_AUDIT_SCHEMA_UNEXPECTED"
    ):
        SqliteAccountLifecycleAudit(database_path=path, secret=AUDIT_SECRET)


def test_operator_cli_requires_audit_and_exposes_only_aggregate_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = Settings(
        production_identity_enabled=True,
        beta_access_enabled=False,
        production_identity_db=tmp_path / "identity.sqlite3",
        production_account_audit_db=tmp_path / "account-audit.sqlite3",
        production_account_audit_secret=AUDIT_SECRET,
    )
    monkeypatch.setattr(operator_cli, "get_settings", lambda: settings)
    passwords = iter([PASSWORD, PASSWORD])
    monkeypatch.setattr(
        operator_cli.getpass, "getpass", lambda _prompt: next(passwords)
    )
    assert operator_cli.main(
        [
            "provision",
            "--email",
            "owner@example.test",
            "--display-label",
            "测试教师",
            "--operator",
            "local-admin",
            "--confirm",
        ]
    ) == 0
    capsys.readouterr()
    assert operator_cli.main(["audit-summary"]) == 0
    output = capsys.readouterr().out
    summary = json.loads(output)
    assert summary["action"] == "audit-summary"
    assert summary["total"] == 1
    assert summary["provision_succeeded"] == 1
    assert "owner@example.test" not in output
    assert "local-admin" not in output
    assert "aa_" not in output


def test_operator_cli_does_not_create_identity_store_without_audit_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = Settings(
        production_identity_enabled=True,
        beta_access_enabled=False,
        production_identity_db=tmp_path / "identity.sqlite3",
        production_account_audit_db=tmp_path / "account-audit.sqlite3",
        production_account_audit_secret="",
    )
    monkeypatch.setattr(operator_cli, "get_settings", lambda: settings)
    passwords = iter([PASSWORD, PASSWORD])
    monkeypatch.setattr(
        operator_cli.getpass, "getpass", lambda _prompt: next(passwords)
    )
    assert operator_cli.main(
        [
            "provision",
            "--email",
            "owner@example.test",
            "--display-label",
            "测试教师",
            "--operator",
            "local-admin",
            "--confirm",
        ]
    ) == 1
    assert json.loads(capsys.readouterr().out) == {
        "error": "ACCOUNT_AUDIT_UNAVAILABLE"
    }
    assert not settings.production_identity_db.exists()
    assert not settings.production_account_audit_db.exists()


def test_operator_session_prune_is_audited_with_counts_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = Settings(
        production_identity_enabled=True,
        beta_access_enabled=False,
        production_identity_db=tmp_path / "identity.sqlite3",
        production_account_audit_db=tmp_path / "account-audit.sqlite3",
        production_account_audit_secret=AUDIT_SECRET,
    )
    identity = SqliteAccountIdentity(
        database_path=settings.production_identity_db,
        session_ttl=timedelta(hours=1),
    )
    identity.provision_personal_account(
        PersonalAccountProvision(
            email="owner@example.test",
            password=PASSWORD,
            display_label="测试教师",
        )
    )
    identity.authenticate(AccountLogin(email="owner@example.test", password=PASSWORD))
    with sqlite3.connect(settings.production_identity_db) as connection:
        connection.execute(
            "UPDATE m14_account_sessions SET expires_at = ?",
            ((datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),),
        )
    monkeypatch.setattr(operator_cli, "get_settings", lambda: settings)

    assert operator_cli.main(
        ["session-prune", "--operator", "local-admin", "--confirm"]
    ) == 0
    output = capsys.readouterr().out
    assert json.loads(output)["deleted"] == 1
    summary = _audit(tmp_path).summary()
    assert summary["session_prune_succeeded"] == 1
    with sqlite3.connect(settings.production_account_audit_db) as connection:
        row = connection.execute(
            "SELECT changed, affected_sessions FROM m14_account_lifecycle_audit"
        ).fetchone()
    assert row == (1, 1)
    assert "owner@example.test" not in output
