"""Operator CLI privacy: synthetic failures must never expose their raw context."""
import json
import sqlite3
import sys
from types import SimpleNamespace

import pytest

from app.modules.beta_recovery import BackupContractError, BackupIntegrityError
from app.modules.beta_recovery import cli
from tests.test_beta_recovery import _service


@pytest.mark.parametrize("failure,code", [
    (OSError("synthetic private path and file contents"), "BACKUP_STORAGE_UNAVAILABLE"),
    (sqlite3.DatabaseError("synthetic private SQL"), "BACKUP_STORAGE_UNAVAILABLE"),
    (RuntimeError("synthetic unexpected private exception"), "BACKUP_OPERATION_FAILED"),
    (BackupContractError("synthetic private contract details"), "BACKUP_CONTRACT_REJECTED"),
    (BackupIntegrityError("synthetic private manifest details"), "BACKUP_INTEGRITY_FAILED"),
])
def test_cli_operation_failures_are_redacted(tmp_path, monkeypatch, capsys, failure, code):
    monkeypatch.setattr(sys, "argv", ["beta-backup", "inventory"])
    monkeypatch.setattr(cli, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(cli, "owner_store_sources", lambda _: ())

    def fail(_):
        raise failure

    monkeypatch.setattr(cli.BetaBackupRecovery, "inventory", fail)
    assert cli.main() == 1
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"error": code}
    assert captured.err == ""


@pytest.mark.parametrize("confirmed", [False, True])
def test_create_requires_confirmation_before_loading_private_settings(monkeypatch, capsys, confirmed):
    monkeypatch.setattr(sys, "argv", ["beta-backup", "create"] + (["--confirm-private-storage"] if confirmed else []))
    calls = []

    def fail():
        calls.append(True)
        raise ValueError("synthetic API key from invalid environment")

    monkeypatch.setattr(cli, "get_settings", fail)
    assert cli.main() == (1 if confirmed else 2)
    assert len(calls) == (1 if confirmed else 0)
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"error": (
        "BACKUP_CONFIGURATION_UNAVAILABLE" if confirmed else "PRIVATE_DESTINATION_CONFIRMATION_REQUIRED"
    )}
    assert captured.err == ""


def test_unknown_argument_does_not_echo_private_value(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["beta-backup", "inventory", "--synthetic-private-token"])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2
    captured = capsys.readouterr()
    assert "synthetic-private-token" not in captured.out + captured.err
    assert json.loads(captured.out) == {"error": "BACKUP_ARGUMENTS_INVALID"}


def test_cli_create_verify_and_drill_still_work_with_summary_only(tmp_path, monkeypatch, capsys):
    service, _, _ = _service(tmp_path)
    backup_dir = tmp_path / "backups"
    monkeypatch.setattr(cli, "get_settings", lambda: SimpleNamespace(beta_backup_dir=backup_dir))
    monkeypatch.setattr(cli, "owner_store_sources", lambda _: service.sources)
    monkeypatch.setattr(sys, "argv", ["beta-backup", "create", "--confirm-private-storage"])
    assert cli.main() == 0
    first = json.loads(capsys.readouterr().out)
    for operation in ("verify", "drill"):
        monkeypatch.setattr(sys, "argv", ["beta-backup", operation, str(backup_dir / first["backup_id"])])
        assert cli.main() == 0
        captured = capsys.readouterr()
        assert json.loads(captured.out)["file_count"] == 2
        assert str(tmp_path) not in captured.out
        assert "private sentinel" not in captured.out
        assert captured.err == ""
