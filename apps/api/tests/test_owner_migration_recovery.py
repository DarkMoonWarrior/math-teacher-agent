from __future__ import annotations

import hashlib
from typing import Any

import pytest

from app.modules.tenant_migration import (
    PostgresOwnerMigrationRecovery,
    PostgresOwnerMigrationRecoveryError,
)


_PLAN = "a" * 64
_BINDING = "b" * 64
_DIGEST = "c" * 64
_CONTENT = b"private-migration-file"
_CHECKSUM = hashlib.sha256(_CONTENT).hexdigest()
_STAGED = "private/staged/object"
_PUBLISHED = "private/published/object"


class _Cursor:
    def __init__(self, rows=()) -> None:
        self.rows = tuple(rows)

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class _Database:
    def __init__(self) -> None:
        self.run: dict[str, Any] | None = {
            "target_binding_fingerprint": _BINDING,
            "status": "complete",
            "file_count": 1,
        }
        self.rows: list[dict[str, Any]] = [
            {
                "object_digest": _DIGEST,
                "source_checksum": _CHECKSUM,
                "byte_length": len(_CONTENT),
                "staged_storage_key": _STAGED,
                "published_storage_key": _PUBLISHED,
            }
        ]
        self.connections = 0
        self.queries: list[str] = []

    def connect(self):
        self.connections += 1
        return _Connection(self)


class _Connection:
    def __init__(self, database: _Database) -> None:
        self.database = database

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def execute(self, query: str, params=None) -> _Cursor:
        normalized = " ".join(query.split())
        self.database.queries.append(normalized)
        values = tuple(params or ())
        if normalized == "SELECT pg_advisory_xact_lock(%s)":
            assert len(values) == 1
            assert -(1 << 63) <= values[0] < (1 << 63)
            return _Cursor()
        if normalized.startswith("SELECT target_binding_fingerprint"):
            assert values == (_PLAN,)
            return _Cursor((self.database.run,) if self.database.run else ())
        if normalized.startswith("SELECT object_digest"):
            assert values == (_PLAN,)
            return _Cursor(self.database.rows)
        raise AssertionError(normalized)


class _Files:
    def __init__(self) -> None:
        self.content: dict[str, bytes] = {_STAGED: _CONTENT}
        self.restores = 0
        self.fail_restore_key: str | None = None

    def inspect(
        self,
        *,
        storage_key: str,
        expected_checksum: str,
        expected_length: int,
    ):
        content = self.content.get(storage_key)
        if content is None:
            return "missing"
        if (
            len(content) == expected_length
            and hashlib.sha256(content).hexdigest() == expected_checksum
        ):
            return "matching"
        return "mismatch"

    def restore(
        self,
        *,
        staged_storage_key: str,
        published_storage_key: str,
        expected_checksum: str,
        expected_length: int,
    ) -> None:
        self.restores += 1
        if self.fail_restore_key == staged_storage_key:
            raise RuntimeError(f"failed private key {staged_storage_key}")
        assert (
            self.inspect(
                storage_key=staged_storage_key,
                expected_checksum=expected_checksum,
                expected_length=expected_length,
            )
            == "matching"
        )
        existing = self.inspect(
            storage_key=published_storage_key,
            expected_checksum=expected_checksum,
            expected_length=expected_length,
        )
        if existing == "mismatch":
            raise RuntimeError("refuse overwrite")
        self.content[published_storage_key] = self.content[staged_storage_key]


def _setup():
    database = _Database()
    files = _Files()
    recovery = PostgresOwnerMigrationRecovery(
        connect=database.connect,
        files=files,
    )
    return database, files, recovery


def _preview(recovery: PostgresOwnerMigrationRecovery):
    return recovery.preview(
        plan_fingerprint=_PLAN,
        target_binding_fingerprint=_BINDING,
    )


def _recover(
    recovery: PostgresOwnerMigrationRecovery,
    fingerprint: str,
):
    return recovery.recover(
        plan_fingerprint=_PLAN,
        target_binding_fingerprint=_BINDING,
        expected_recovery_fingerprint=fingerprint,
        confirmation="修复已提交 owner 迁移",
        confirmed=True,
    )


def test_recovery_previews_repairs_and_then_returns_idempotently() -> None:
    database, files, recovery = _setup()

    plan = _preview(recovery)
    receipt = _recover(recovery, plan.recovery_fingerprint)
    healthy = _preview(recovery)
    repeated = _recover(recovery, healthy.recovery_fingerprint)

    assert plan.state == "repairable"
    assert plan.execution_allowed is False
    assert plan.repairable_file_count == 1
    assert _STAGED not in repr(plan)
    assert _PUBLISHED not in repr(plan)
    assert receipt.outcome == "repaired"
    assert receipt.repaired_file_count == 1
    assert healthy.state == "healthy"
    assert repeated.outcome == "already_healthy"
    assert files.restores == 1
    assert database.queries[0] == "SELECT pg_advisory_xact_lock(%s)"


def test_recovery_requires_confirmation_before_opening_targets() -> None:
    database, files, recovery = _setup()

    with pytest.raises(
        PostgresOwnerMigrationRecoveryError,
        match="POSTGRES_OWNER_MIGRATION_RECOVERY_CONFIRMATION_REQUIRED",
    ):
        recovery.recover(
            plan_fingerprint=_PLAN,
            target_binding_fingerprint=_BINDING,
            expected_recovery_fingerprint="d" * 64,
            confirmation="wrong",
            confirmed=True,
        )

    assert database.connections == 0
    assert files.restores == 0


def test_recovery_rejects_a_stale_preview_without_restoring() -> None:
    _, files, recovery = _setup()
    plan = _preview(recovery)
    files.content[_PUBLISHED] = _CONTENT

    with pytest.raises(
        PostgresOwnerMigrationRecoveryError,
        match="POSTGRES_OWNER_MIGRATION_RECOVERY_PLAN_CHANGED",
    ):
        _recover(recovery, plan.recovery_fingerprint)

    assert files.restores == 0


def test_recovery_fingerprint_binds_private_storage_keys_without_exposing_them() -> None:
    database, files, recovery = _setup()
    plan = _preview(recovery)
    replacement_staged = "private/staged/replacement"
    replacement_published = "private/published/replacement"
    database.rows[0]["staged_storage_key"] = replacement_staged
    database.rows[0]["published_storage_key"] = replacement_published
    files.content[replacement_staged] = _CONTENT

    changed = _preview(recovery)

    assert changed.state == "repairable"
    assert changed.recovery_fingerprint != plan.recovery_fingerprint
    assert replacement_staged not in repr(changed)
    assert replacement_published not in repr(changed)
    with pytest.raises(
        PostgresOwnerMigrationRecoveryError,
        match="POSTGRES_OWNER_MIGRATION_RECOVERY_PLAN_CHANGED",
    ):
        _recover(recovery, plan.recovery_fingerprint)
    assert files.restores == 0


@pytest.mark.parametrize(
    ("content", "issue"),
    [
        ({_PUBLISHED: b"wrong", _STAGED: _CONTENT}, "PUBLISHED_CONTENT_MISMATCH"),
        ({}, "STAGED_CONTENT_MISSING"),
    ],
)
def test_recovery_blocks_missing_or_conflicting_content(
    content: dict[str, bytes],
    issue: str,
) -> None:
    _, files, recovery = _setup()
    files.content = content

    plan = _preview(recovery)

    assert plan.state == "blocked"
    assert plan.blocked_file_count == 1
    assert plan.issues == (issue,)
    with pytest.raises(
        PostgresOwnerMigrationRecoveryError,
        match="POSTGRES_OWNER_MIGRATION_RECOVERY_BLOCKED",
    ):
        _recover(recovery, plan.recovery_fingerprint)
    assert files.restores == 0


def test_recovery_requires_an_exact_committed_target() -> None:
    database, _, recovery = _setup()
    database.run = {
        "target_binding_fingerprint": _BINDING,
        "status": "in_progress",
        "file_count": 1,
    }

    with pytest.raises(
        PostgresOwnerMigrationRecoveryError,
        match="POSTGRES_OWNER_MIGRATION_RECOVERY_TARGET_NOT_COMMITTED",
    ):
        _preview(recovery)

    database.run = {
        "target_binding_fingerprint": "e" * 64,
        "status": "complete",
        "file_count": 1,
    }
    with pytest.raises(
        PostgresOwnerMigrationRecoveryError,
        match="POSTGRES_OWNER_MIGRATION_RECOVERY_TARGET_CHANGED",
    ):
        _preview(recovery)


def test_recovery_rejects_inconsistent_database_evidence() -> None:
    database, _, recovery = _setup()
    assert database.run is not None
    database.run["file_count"] = 2

    with pytest.raises(
        PostgresOwnerMigrationRecoveryError,
        match="POSTGRES_OWNER_MIGRATION_RECOVERY_TARGET_INCONSISTENT",
    ):
        _preview(recovery)


def test_recovery_sanitizes_storage_failures() -> None:
    _, files, recovery = _setup()
    plan = _preview(recovery)
    files.fail_restore_key = _STAGED

    with pytest.raises(PostgresOwnerMigrationRecoveryError) as caught:
        _recover(recovery, plan.recovery_fingerprint)

    assert str(caught.value) == "POSTGRES_OWNER_MIGRATION_RECOVERY_FAILED"
    assert _STAGED not in str(caught.value)


def test_partial_forward_repair_requires_a_fresh_preview_for_remaining_files() -> None:
    database, files, recovery = _setup()
    second_content = b"second-private-file"
    second_staged = "private/staged/second"
    second_published = "private/published/second"
    database.rows.append(
        {
            "object_digest": "d" * 64,
            "source_checksum": hashlib.sha256(second_content).hexdigest(),
            "byte_length": len(second_content),
            "staged_storage_key": second_staged,
            "published_storage_key": second_published,
        }
    )
    assert database.run is not None
    database.run["file_count"] = 2
    files.content[second_staged] = second_content
    files.fail_restore_key = second_staged
    first_plan = _preview(recovery)

    with pytest.raises(
        PostgresOwnerMigrationRecoveryError,
        match="POSTGRES_OWNER_MIGRATION_RECOVERY_FAILED",
    ):
        _recover(recovery, first_plan.recovery_fingerprint)

    assert files.content[_PUBLISHED] == _CONTENT
    assert second_published not in files.content
    remaining = _preview(recovery)
    assert remaining.healthy_file_count == 1
    assert remaining.repairable_file_count == 1
    assert remaining.recovery_fingerprint != first_plan.recovery_fingerprint

    files.fail_restore_key = None
    receipt = _recover(recovery, remaining.recovery_fingerprint)
    assert receipt.outcome == "repaired"
    assert receipt.repaired_file_count == 1
    assert files.content[second_published] == second_content


def test_recovery_rejects_invalid_fingerprints_before_connecting() -> None:
    database, _, recovery = _setup()

    with pytest.raises(
        PostgresOwnerMigrationRecoveryError,
        match="POSTGRES_OWNER_MIGRATION_RECOVERY_TARGET_INVALID",
    ):
        recovery.preview(
            plan_fingerprint="not-a-fingerprint",
            target_binding_fingerprint=_BINDING,
        )

    assert database.connections == 0
    with pytest.raises(
        PostgresOwnerMigrationRecoveryError,
        match="POSTGRES_OWNER_MIGRATION_RECOVERY_DSN_REQUIRED",
    ):
        PostgresOwnerMigrationRecovery.from_dsn(dsn=" ", files=_Files())
