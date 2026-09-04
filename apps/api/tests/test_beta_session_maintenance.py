import json
import sqlite3
import stat
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from pathlib import Path

import pytest

from app.modules.beta_access import BetaAccess, BetaParticipant
from app.modules.beta_access.access import BetaAccessDenied
from app.modules.beta_access.maintenance import BetaSessionMaintenance, SessionMaintenanceError
from app.modules.beta_access import maintenance_cli


@pytest.fixture
def sessions(tmp_path):
    now = [datetime(2026, 9, 4, tzinfo=timezone.utc)]
    path = tmp_path / "synthetic sessions.sqlite3"
    participants = {
        code: BetaParticipant(teacher_id=code, display_label=code)
        for code in ("synthetic-alpha", "synthetic-beta")
    }
    access = BetaAccess(database_path=path, participants=participants,
                        session_ttl=timedelta(hours=1), clock=lambda: now[0])
    expired = access.issue("synthetic-alpha")
    both = access.issue("synthetic-beta")
    access.revoke(both.token)
    now[0] += timedelta(hours=1)
    active = access.issue("synthetic-alpha")
    revoked = access.issue("synthetic-beta")
    access.revoke(revoked.token)
    maintenance = BetaSessionMaintenance(database_path=path, clock=lambda: now[0])
    return path, now, access, maintenance, (expired, both, active, revoked)


def snapshot(path):
    with sqlite3.connect(path) as connection:
        return connection.execute("SELECT * FROM m12_beta_sessions ORDER BY token_hash").fetchall()


def test_preview_then_confirm_only_removes_invalid_sessions(sessions):
    path, now, access, maintenance, grants = sessions
    before = snapshot(path)
    report = maintenance.preview()
    assert asdict(report) == dict(cutoff=now[0].isoformat(), total=4, active=1,
                                  expired=1, revoked=2, unclassified=0, deleted=0)
    assert snapshot(path) == before
    rendered = json.dumps(asdict(report))
    assert "synthetic-alpha" not in rendered
    assert all(grant.token not in rendered for grant in grants)
    with pytest.raises(SessionMaintenanceError, match="CONFIRMATION_REQUIRED"):
        maintenance.prune()
    assert snapshot(path) == before
    result = maintenance.prune(confirmed=True)
    assert result.deleted == 3
    assert access.resolve(grants[2].token).teacher_id == "synthetic-alpha"
    reopened = BetaAccess(database_path=path, participants={}, session_ttl=timedelta(hours=1),
                          clock=lambda: now[0])
    for grant in (grants[0], grants[1], grants[3]):
        with pytest.raises(BetaAccessDenied):
            reopened.resolve(grant.token)
    assert snapshot(path) == [row for row in before if row[0] == access._hash(grants[2].token)]
    assert maintenance.prune(confirmed=True).deleted == 0


def test_cleanup_rechecks_current_rows_not_stale_preview(sessions):
    path, now, access, maintenance, grants = sessions
    assert maintenance.preview().active == 1
    # A preview is not a deletion plan. A subsequent operator correction to an
    # expiry must be respected, and newly issued valid logins must survive.
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE m12_beta_sessions SET expires_at=? WHERE token_hash=?",
                           ((now[0] + timedelta(hours=1)).isoformat(), access._hash(grants[0].token)))
    new = access.issue("synthetic-beta")
    assert maintenance.prune(confirmed=True).deleted == 2
    assert access.resolve(new.token).teacher_id == "synthetic-beta"
    assert access.resolve(grants[0].token).teacher_id == "synthetic-alpha"


@pytest.mark.parametrize("expiry,eligible", [
    ("2026-09-04T09:00:00+08:00", True),  # exact expiry == 01:00 UTC
    ("2026-09-04T09:00:01+08:00", False),
    ("2026-09-04T00:00:00Z", True),
    ("not-a-time", False), ("2026-09-04T00:00:00", False), ("", False),
])
def test_expiry_timezone_and_malformed_record_conservatism(sessions, expiry, eligible):
    path, _, access, maintenance, grants = sessions
    key = access._hash(grants[2].token)
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE m12_beta_sessions SET expires_at=? WHERE token_hash=?", (expiry, key))
    assert maintenance.prune(confirmed=True).deleted == 3 + int(eligible)
    assert any(row[0] == key for row in snapshot(path)) is not eligible


def test_corrupt_key_is_preserved(sessions):
    path, _, _, maintenance, _ = sessions
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE m12_beta_sessions SET token_hash='invalid' WHERE revoked_at IS NULL AND expires_at=(SELECT MIN(expires_at) FROM m12_beta_sessions)")
    assert maintenance.preview().unclassified == 1
    assert maintenance.prune(confirmed=True).deleted == 2
    assert any(row[0] == "invalid" for row in snapshot(path))


@pytest.mark.parametrize("target", ["missing", "directory", "wrong-schema", "extra-table", "trigger"])
def test_unsafe_store_fails_without_changes(tmp_path, sessions, target):
    path = tmp_path / "not-sessions.sqlite3"
    if target == "directory":
        path.mkdir()
    elif target == "wrong-schema":
        with sqlite3.connect(path) as connection:
            connection.execute("CREATE TABLE private_content (body TEXT)")
            connection.execute("INSERT INTO private_content VALUES ('synthetic-only')")
    elif target in ("extra-table", "trigger"):
        path = sessions[0]
        with sqlite3.connect(path) as connection:
            if target == "extra-table":
                connection.execute("CREATE TABLE private_content (body TEXT)")
            else:
                connection.execute("CREATE TRIGGER unexpected AFTER DELETE ON m12_beta_sessions BEGIN DELETE FROM m12_beta_sessions; END")
    maintenance = BetaSessionMaintenance(database_path=path)
    before = snapshot(sessions[0])
    for operation in (maintenance.preview, lambda: maintenance.prune(confirmed=True)):
        with pytest.raises(SessionMaintenanceError):
            operation()
    assert snapshot(sessions[0]) == before
    if target == "missing":
        assert not path.exists()
    if target == "wrong-schema":
        with sqlite3.connect(path) as connection:
            assert connection.execute("SELECT body FROM private_content").fetchall() == [("synthetic-only",)]


def test_linked_store_is_refused(tmp_path, sessions):
    link = tmp_path / "session-link.sqlite3"
    try:
        link.symlink_to(sessions[0])
    except OSError:
        pytest.skip("Creating symlinks requires OS privileges")
    before = snapshot(sessions[0])
    with pytest.raises(SessionMaintenanceError, match="LINK_UNSAFE"):
        BetaSessionMaintenance(database_path=link).prune(confirmed=True)
    assert snapshot(sessions[0]) == before


@pytest.mark.parametrize("component", ["file", "parent"])
def test_windows_reparse_points_fail_closed_without_symlink_privileges(sessions, monkeypatch, component):
    path = sessions[0]
    target = path if component == "file" else path.parent
    real_lstat = Path.lstat
    before = snapshot(path)

    def with_reparse_flag(item):
        info = real_lstat(item)
        if item == target:
            return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT)
        return info

    monkeypatch.setattr(Path, "lstat", with_reparse_flag)
    with pytest.raises(SessionMaintenanceError, match="LINK_UNSAFE"):
        sessions[3].prune(confirmed=True)
    assert snapshot(path) == before


def test_naive_clock_refused_before_changes(sessions):
    before = snapshot(sessions[0])
    maintenance = BetaSessionMaintenance(database_path=sessions[0], clock=lambda: datetime(2026, 9, 4))
    with pytest.raises(SessionMaintenanceError, match="TIMEZONE_REQUIRED"):
        maintenance.prune(confirmed=True)
    assert snapshot(sessions[0]) == before


def test_failed_deletion_rolls_back_entire_transaction(sessions, monkeypatch):
    path, _, _, maintenance, _ = sessions
    connect = sqlite3.connect

    class FailingConnection(sqlite3.Connection):
        def executemany(self, sql, parameters):
            super().executemany(sql, parameters[:1])
            raise sqlite3.OperationalError("synthetic confidential error")

    before = snapshot(path)
    with monkeypatch.context() as patch:
        patch.setattr(sqlite3, "connect", lambda *args, **kwargs: connect(*args, **kwargs, factory=FailingConnection))
        with pytest.raises(SessionMaintenanceError) as error:
            maintenance.prune(confirmed=True)
        assert str(error.value) == "SESSION_STORE_UNAVAILABLE"
    assert snapshot(path) == before


def test_cli_defaults_to_preview_and_requires_confirmation(sessions, monkeypatch, capsys):
    path, _, _, maintenance, _ = sessions
    monkeypatch.setattr(maintenance_cli, "get_settings", lambda: SimpleNamespace(beta_session_db=path))
    monkeypatch.setattr(maintenance_cli, "BetaSessionMaintenance", lambda **kwargs: maintenance)
    before = snapshot(path)
    assert maintenance_cli.main([]) == 0
    assert json.loads(capsys.readouterr().out)["deleted"] == 0
    assert snapshot(path) == before
    assert maintenance_cli.main(["prune"]) == 2
    assert "CONFIRMATION_REQUIRED" in capsys.readouterr().out
    assert snapshot(path) == before
    assert maintenance_cli.main(["prune", "--confirm"]) == 0
    assert json.loads(capsys.readouterr().out)["deleted"] == 3


def test_cli_failure_does_not_echo_paths_or_initialize_store(tmp_path, monkeypatch, capsys):
    path = tmp_path / "private-missing.sqlite3"
    monkeypatch.setattr(maintenance_cli, "get_settings", lambda: SimpleNamespace(beta_session_db=path))
    assert maintenance_cli.main([]) == 1
    assert json.loads(capsys.readouterr().out) == {"error": "SESSION_STORE_UNAVAILABLE"}
    assert not path.exists()


def test_cli_bad_configuration_is_redacted_and_unconfirmed_cleanup_does_not_load_it(monkeypatch, capsys):
    calls = []

    def invalid_settings():
        calls.append(True)
        raise ValueError("synthetic-secret-roster")

    monkeypatch.setattr(maintenance_cli, "get_settings", invalid_settings)
    assert maintenance_cli.main(["prune"]) == 2
    capsys.readouterr()
    assert calls == []
    assert maintenance_cli.main([]) == 1
    assert json.loads(capsys.readouterr().out) == {"error": "SESSION_CONFIGURATION_UNAVAILABLE"}
