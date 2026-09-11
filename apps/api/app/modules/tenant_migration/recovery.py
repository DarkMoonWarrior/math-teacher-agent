from __future__ import annotations

import re
import secrets
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from app.modules.tenant_migration.fingerprints import (
    canonical_digest,
    target_advisory_lock_key,
)
from app.modules.tenant_migration.postgres_schema import (
    POSTGRES_OWNER_MIGRATION_SCHEMA,
)
from app.modules.tenant_migration.schemas import (
    OwnerMigrationRecoveryPlan,
    OwnerMigrationRecoveryReceipt,
)


_RUNS = f"{POSTGRES_OWNER_MIGRATION_SCHEMA}.owner_migration_runs"
_FILES = f"{POSTGRES_OWNER_MIGRATION_SCHEMA}.owner_migration_files"
_FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")


class PostgresOwnerMigrationRecoveryError(ValueError):
    """Stable recovery failure without owner, path, key, or content details."""


FileState = Literal["missing", "matching", "mismatch"]


class OwnerMigrationRecoveryFiles(Protocol):
    """Inspect and atomically restore target objects behind private storage keys."""

    def inspect(
        self,
        *,
        storage_key: str,
        expected_checksum: str,
        expected_length: int,
    ) -> FileState: ...

    def restore(
        self,
        *,
        staged_storage_key: str,
        published_storage_key: str,
        expected_checksum: str,
        expected_length: int,
    ) -> None: ...


class _Cursor(Protocol):
    def fetchone(self) -> Mapping[str, Any] | None: ...

    def fetchall(self) -> Sequence[Mapping[str, Any]]: ...


class _Connection(Protocol):
    def __enter__(self) -> "_Connection": ...

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None: ...

    def execute(
        self,
        query: str,
        params: Sequence[Any] | None = None,
    ) -> _Cursor: ...


Connect = Callable[[], _Connection]


def _psycopg_connect(dsn: str) -> _Connection:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as error:
        raise PostgresOwnerMigrationRecoveryError(
            "POSTGRES_OWNER_MIGRATION_RECOVERY_DRIVER_UNAVAILABLE"
        ) from error
    try:
        return psycopg.connect(dsn, row_factory=dict_row)
    except Exception as error:
        raise PostgresOwnerMigrationRecoveryError(
            "POSTGRES_OWNER_MIGRATION_RECOVERY_CONNECTION_UNAVAILABLE"
        ) from error


@dataclass(frozen=True, repr=False)
class _RecoveryFile:
    object_digest: str
    source_checksum: str
    byte_length: int
    staged_storage_key: str
    published_storage_key: str
    state: Literal["healthy", "repairable", "blocked"]
    issue: str | None = None


@dataclass(frozen=True, repr=False)
class _RecoveryEvidence:
    files: tuple[_RecoveryFile, ...]
    plan: OwnerMigrationRecoveryPlan


class PostgresOwnerMigrationRecovery:
    """Preview and explicitly repair a committed migration's published files."""

    _CONFIRMATION = "修复已提交 owner 迁移"

    def __init__(
        self,
        *,
        connect: Connect,
        files: OwnerMigrationRecoveryFiles,
    ) -> None:
        self._connect = connect
        self._files = files

    @classmethod
    def from_dsn(
        cls,
        *,
        dsn: str,
        files: OwnerMigrationRecoveryFiles,
    ) -> "PostgresOwnerMigrationRecovery":
        if not dsn.strip():
            raise PostgresOwnerMigrationRecoveryError(
                "POSTGRES_OWNER_MIGRATION_RECOVERY_DSN_REQUIRED"
            )
        return cls(connect=lambda: _psycopg_connect(dsn), files=files)

    def preview(
        self,
        *,
        plan_fingerprint: str,
        target_binding_fingerprint: str,
    ) -> OwnerMigrationRecoveryPlan:
        self._validate_fingerprints(plan_fingerprint, target_binding_fingerprint)
        try:
            with self._connect() as connection:
                self._lock(connection, target_binding_fingerprint)
                return self._inspect(
                    connection=connection,
                    plan_fingerprint=plan_fingerprint,
                    target_binding_fingerprint=target_binding_fingerprint,
                ).plan
        except PostgresOwnerMigrationRecoveryError:
            raise
        except Exception as error:
            raise PostgresOwnerMigrationRecoveryError(
                "POSTGRES_OWNER_MIGRATION_RECOVERY_INSPECTION_FAILED"
            ) from error

    def recover(
        self,
        *,
        plan_fingerprint: str,
        target_binding_fingerprint: str,
        expected_recovery_fingerprint: str,
        confirmation: str,
        confirmed: bool = False,
    ) -> OwnerMigrationRecoveryReceipt:
        self._validate_fingerprints(plan_fingerprint, target_binding_fingerprint)
        if (
            confirmed is not True
            or confirmation != self._CONFIRMATION
            or not _FINGERPRINT.fullmatch(expected_recovery_fingerprint)
        ):
            raise PostgresOwnerMigrationRecoveryError(
                "POSTGRES_OWNER_MIGRATION_RECOVERY_CONFIRMATION_REQUIRED"
            )
        try:
            with self._connect() as connection:
                self._lock(connection, target_binding_fingerprint)
                evidence = self._inspect(
                    connection=connection,
                    plan_fingerprint=plan_fingerprint,
                    target_binding_fingerprint=target_binding_fingerprint,
                )
                if not secrets.compare_digest(
                    evidence.plan.recovery_fingerprint,
                    expected_recovery_fingerprint,
                ):
                    raise PostgresOwnerMigrationRecoveryError(
                        "POSTGRES_OWNER_MIGRATION_RECOVERY_PLAN_CHANGED"
                    )
                if evidence.plan.state == "blocked":
                    raise PostgresOwnerMigrationRecoveryError(
                        "POSTGRES_OWNER_MIGRATION_RECOVERY_BLOCKED"
                    )
                if evidence.plan.state == "healthy":
                    return self._receipt(
                        outcome="already_healthy",
                        plan=evidence.plan,
                        repaired_file_count=0,
                    )
                repairable = tuple(
                    item for item in evidence.files if item.state == "repairable"
                )
                for item in repairable:
                    self._files.restore(
                        staged_storage_key=item.staged_storage_key,
                        published_storage_key=item.published_storage_key,
                        expected_checksum=item.source_checksum,
                        expected_length=item.byte_length,
                    )
                reconciled = self._inspect(
                    connection=connection,
                    plan_fingerprint=plan_fingerprint,
                    target_binding_fingerprint=target_binding_fingerprint,
                )
                if reconciled.plan.state != "healthy":
                    raise PostgresOwnerMigrationRecoveryError(
                        "POSTGRES_OWNER_MIGRATION_RECOVERY_RECONCILIATION_FAILED"
                    )
                return self._receipt(
                    outcome="repaired",
                    plan=reconciled.plan,
                    repaired_file_count=len(repairable),
                )
        except PostgresOwnerMigrationRecoveryError:
            raise
        except Exception as error:
            raise PostgresOwnerMigrationRecoveryError(
                "POSTGRES_OWNER_MIGRATION_RECOVERY_FAILED"
            ) from error

    @staticmethod
    def _validate_fingerprints(
        plan_fingerprint: str,
        target_binding_fingerprint: str,
    ) -> None:
        if not _FINGERPRINT.fullmatch(
            plan_fingerprint
        ) or not _FINGERPRINT.fullmatch(target_binding_fingerprint):
            raise PostgresOwnerMigrationRecoveryError(
                "POSTGRES_OWNER_MIGRATION_RECOVERY_TARGET_INVALID"
            )

    @staticmethod
    def _lock(connection: _Connection, target_binding_fingerprint: str) -> None:
        connection.execute(
            "SELECT pg_advisory_xact_lock(%s)",
            (target_advisory_lock_key(target_binding_fingerprint),),
        )

    def _inspect(
        self,
        *,
        connection: _Connection,
        plan_fingerprint: str,
        target_binding_fingerprint: str,
    ) -> _RecoveryEvidence:
        run = connection.execute(
            f"SELECT target_binding_fingerprint, status, file_count FROM {_RUNS} "
            "WHERE plan_fingerprint = %s",
            (plan_fingerprint,),
        ).fetchone()
        if run is None or run.get("status") != "complete":
            raise PostgresOwnerMigrationRecoveryError(
                "POSTGRES_OWNER_MIGRATION_RECOVERY_TARGET_NOT_COMMITTED"
            )
        actual_binding = str(run.get("target_binding_fingerprint", ""))
        if not secrets.compare_digest(actual_binding, target_binding_fingerprint):
            raise PostgresOwnerMigrationRecoveryError(
                "POSTGRES_OWNER_MIGRATION_RECOVERY_TARGET_CHANGED"
            )
        rows = connection.execute(
            f"SELECT object_digest, source_checksum, byte_length, "
            f"staged_storage_key, published_storage_key FROM {_FILES} "
            "WHERE plan_fingerprint = %s ORDER BY sequence, object_digest",
            (plan_fingerprint,),
        ).fetchall()
        expected_count = run.get("file_count")
        if (
            not isinstance(expected_count, int)
            or expected_count < 0
            or len(rows) != expected_count
        ):
            raise PostgresOwnerMigrationRecoveryError(
                "POSTGRES_OWNER_MIGRATION_RECOVERY_TARGET_INCONSISTENT"
            )
        files = tuple(self._inspect_file(row) for row in rows)
        if (
            len({item.object_digest for item in files}) != len(files)
            or len({item.staged_storage_key for item in files}) != len(files)
            or len({item.published_storage_key for item in files}) != len(files)
        ):
            raise PostgresOwnerMigrationRecoveryError(
                "POSTGRES_OWNER_MIGRATION_RECOVERY_TARGET_INCONSISTENT"
            )
        return _RecoveryEvidence(
            files=files,
            plan=self._build_plan(
                files=files,
                plan_fingerprint=plan_fingerprint,
                target_binding_fingerprint=target_binding_fingerprint,
            ),
        )

    def _inspect_file(self, row: Mapping[str, Any]) -> _RecoveryFile:
        digest = row.get("object_digest")
        checksum = row.get("source_checksum")
        length = row.get("byte_length")
        staged = row.get("staged_storage_key")
        published = row.get("published_storage_key")
        if (
            not isinstance(digest, str)
            or not _FINGERPRINT.fullmatch(digest)
            or not isinstance(checksum, str)
            or not _FINGERPRINT.fullmatch(checksum)
            or not isinstance(length, int)
            or length < 0
            or not isinstance(staged, str)
            or not staged
            or len(staged) > 500
            or not isinstance(published, str)
            or not published
            or len(published) > 500
        ):
            raise PostgresOwnerMigrationRecoveryError(
                "POSTGRES_OWNER_MIGRATION_RECOVERY_TARGET_INCONSISTENT"
            )
        published_state = self._inspect_storage(published, checksum, length)
        if published_state == "matching":
            return _RecoveryFile(digest, checksum, length, staged, published, "healthy")
        if published_state == "mismatch":
            return _RecoveryFile(
                digest,
                checksum,
                length,
                staged,
                published,
                "blocked",
                "PUBLISHED_CONTENT_MISMATCH",
            )
        staged_state = self._inspect_storage(staged, checksum, length)
        if staged_state == "matching":
            return _RecoveryFile(
                digest, checksum, length, staged, published, "repairable"
            )
        issue = (
            "STAGED_CONTENT_MISSING"
            if staged_state == "missing"
            else "STAGED_CONTENT_MISMATCH"
        )
        return _RecoveryFile(
            digest, checksum, length, staged, published, "blocked", issue
        )

    def _inspect_storage(
        self,
        storage_key: str,
        checksum: str,
        length: int,
    ) -> FileState:
        state = self._files.inspect(
            storage_key=storage_key,
            expected_checksum=checksum,
            expected_length=length,
        )
        if state not in {"missing", "matching", "mismatch"}:
            raise PostgresOwnerMigrationRecoveryError(
                "POSTGRES_OWNER_MIGRATION_RECOVERY_STORAGE_INVALID"
            )
        return state

    @staticmethod
    def _build_plan(
        *,
        files: tuple[_RecoveryFile, ...],
        plan_fingerprint: str,
        target_binding_fingerprint: str,
    ) -> OwnerMigrationRecoveryPlan:
        healthy = sum(item.state == "healthy" for item in files)
        repairable = sum(item.state == "repairable" for item in files)
        blocked = sum(item.state == "blocked" for item in files)
        issues = tuple(sorted({item.issue for item in files if item.issue is not None}))
        state: Literal["healthy", "repairable", "blocked"]
        state = "blocked" if blocked else "repairable" if repairable else "healthy"
        recovery_fingerprint = canonical_digest(
            (
                "m14-owner-migration-recovery-v1",
                plan_fingerprint,
                target_binding_fingerprint,
                tuple(
                    (
                        item.object_digest,
                        item.source_checksum,
                        item.byte_length,
                        canonical_digest(
                            ("m14-staged-storage-key-v1", item.staged_storage_key)
                        ),
                        canonical_digest(
                            ("m14-published-storage-key-v1", item.published_storage_key)
                        ),
                        item.state,
                        item.issue,
                    )
                    for item in files
                ),
            )
        )
        return OwnerMigrationRecoveryPlan(
            state=state,
            plan_fingerprint=plan_fingerprint,
            target_binding_fingerprint=target_binding_fingerprint,
            file_count=len(files),
            healthy_file_count=healthy,
            repairable_file_count=repairable,
            blocked_file_count=blocked,
            issues=issues,
            recovery_fingerprint=recovery_fingerprint,
        )

    @staticmethod
    def _receipt(
        *,
        outcome: Literal["repaired", "already_healthy"],
        plan: OwnerMigrationRecoveryPlan,
        repaired_file_count: int,
    ) -> OwnerMigrationRecoveryReceipt:
        return OwnerMigrationRecoveryReceipt(
            outcome=outcome,
            plan_fingerprint=plan.plan_fingerprint,
            target_binding_fingerprint=plan.target_binding_fingerprint,
            repaired_file_count=repaired_file_count,
            recovery_fingerprint=plan.recovery_fingerprint,
        )
