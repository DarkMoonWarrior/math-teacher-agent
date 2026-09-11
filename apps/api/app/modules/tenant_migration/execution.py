from __future__ import annotations

import hashlib
import json
import re
import secrets
from contextlib import AbstractContextManager
from typing import Literal, Protocol

from app.modules.tenant_migration.schemas import (
    OwnerMigrationExecutionReceipt,
    OwnerMigrationPlanReport,
    OwnerMigrationTargetReconciliation,
    OwnerMigrationTargetState,
)


class OwnerMigrationExecutionError(ValueError):
    """Stable execution-boundary failure without private identifiers."""


class OwnerMigrationPlanProvider(Protocol):
    def plan(
        self,
        *,
        source_owner_id: str,
        target_owner_id: str,
        target_tenant_id: str,
        expected_inventory_fingerprint: str,
        expected_file_reconciliation_fingerprint: str,
    ) -> OwnerMigrationPlanReport: ...


class OwnerMigrationTransaction(Protocol):
    def inspect(self) -> OwnerMigrationTargetState: ...

    def apply(self, plan: OwnerMigrationPlanReport) -> None: ...

    def reconcile(self) -> OwnerMigrationTargetReconciliation: ...

    def mark_complete(self) -> None: ...


class OwnerMigrationExecutionAdapter(Protocol):
    def transaction(
        self,
        *,
        target_binding_fingerprint: str,
        plan_fingerprint: str,
    ) -> AbstractContextManager[OwnerMigrationTransaction]: ...


class OwnerMigrationExecutor:
    """Run one confirmed plan through an injected atomic target transaction.

    The controller owns confirmation, live-plan verification, idempotency state,
    and target reconciliation. Concrete source reads, target writes, commit, and
    rollback stay behind the execution adapter and have no HTTP or Agent seam.
    """

    _FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")
    _CONFIRMATION = "执行 owner 数据迁移"

    def __init__(
        self,
        planner: OwnerMigrationPlanProvider,
        target: OwnerMigrationExecutionAdapter,
    ) -> None:
        self._planner = planner
        self._target = target

    def execute(
        self,
        *,
        source_owner_id: str,
        target_owner_id: str,
        target_tenant_id: str,
        expected_inventory_fingerprint: str,
        expected_file_reconciliation_fingerprint: str,
        expected_plan_fingerprint: str,
        confirmation: str,
        confirmed: bool = False,
    ) -> OwnerMigrationExecutionReceipt:
        self._require_confirmation(
            expected_plan_fingerprint,
            confirmation,
            confirmed,
        )
        try:
            plan = self._planner.plan(
                source_owner_id=source_owner_id,
                target_owner_id=target_owner_id,
                target_tenant_id=target_tenant_id,
                expected_inventory_fingerprint=expected_inventory_fingerprint,
                expected_file_reconciliation_fingerprint=(
                    expected_file_reconciliation_fingerprint
                ),
            )
        except Exception as error:
            raise OwnerMigrationExecutionError(
                "MIGRATION_PLAN_RECHECK_FAILED"
            ) from error
        if not secrets.compare_digest(plan.plan_fingerprint, expected_plan_fingerprint):
            raise OwnerMigrationExecutionError("MIGRATION_PLAN_CHANGED")

        try:
            with self._target.transaction(
                target_binding_fingerprint=plan.target_binding_fingerprint,
                plan_fingerprint=plan.plan_fingerprint,
            ) as transaction:
                state = transaction.inspect()
                self._require_target_binding(state, plan)
                if state.state == "complete":
                    self._require_reconciled(transaction.reconcile(), plan)
                    return self._receipt("already_applied", plan)
                if state.state != "empty":
                    raise OwnerMigrationExecutionError(
                        "MIGRATION_TARGET_STATE_UNEXPECTED"
                    )
                transaction.apply(plan)
                self._require_reconciled(transaction.reconcile(), plan)
                transaction.mark_complete()
        except OwnerMigrationExecutionError:
            raise
        except Exception as error:
            raise OwnerMigrationExecutionError("MIGRATION_EXECUTION_FAILED") from error
        return self._receipt("applied", plan)

    @classmethod
    def _require_confirmation(
        cls,
        expected: str,
        confirmation: str,
        confirmed: bool,
    ) -> None:
        if (
            confirmed is not True
            or confirmation != cls._CONFIRMATION
            or not cls._FINGERPRINT.fullmatch(expected)
        ):
            raise OwnerMigrationExecutionError(
                "MIGRATION_EXECUTION_CONFIRMATION_REQUIRED"
            )

    @staticmethod
    def _require_target_binding(
        state: OwnerMigrationTargetState,
        plan: OwnerMigrationPlanReport,
    ) -> None:
        if not secrets.compare_digest(
            state.target_binding_fingerprint,
            plan.target_binding_fingerprint,
        ):
            raise OwnerMigrationExecutionError("MIGRATION_TARGET_BINDING_MISMATCH")
        if state.state in {"in_progress", "complete"} and (
            state.plan_fingerprint is None
            or not secrets.compare_digest(
                state.plan_fingerprint,
                plan.plan_fingerprint,
            )
        ):
            raise OwnerMigrationExecutionError("MIGRATION_TARGET_PLAN_MISMATCH")
        if state.state == "empty" and state.plan_fingerprint is not None:
            raise OwnerMigrationExecutionError("MIGRATION_TARGET_PLAN_MISMATCH")

    @classmethod
    def _require_reconciled(
        cls,
        actual: OwnerMigrationTargetReconciliation,
        plan: OwnerMigrationPlanReport,
    ) -> None:
        expected_objects = cls._set_fingerprint(
            "m14-target-objects-v1",
            tuple(
                item.object_digest
                for table in plan.tables
                for item in table.objects
            ),
        )
        expected_files = cls._set_fingerprint(
            "m14-target-files-v1",
            tuple(
                digest
                for file_plan in plan.files
                for digest in file_plan.object_digests
            ),
        )
        if (
            not secrets.compare_digest(
                actual.plan_fingerprint,
                plan.plan_fingerprint,
            )
            or actual.object_count != plan.object_count
            or actual.file_count != plan.file_count
            or not secrets.compare_digest(
                actual.object_set_fingerprint,
                expected_objects,
            )
            or not secrets.compare_digest(
                actual.file_set_fingerprint,
                expected_files,
            )
        ):
            raise OwnerMigrationExecutionError(
                "MIGRATION_TARGET_RECONCILIATION_FAILED"
            )

    @classmethod
    def reconciliation_for(
        cls,
        plan: OwnerMigrationPlanReport,
    ) -> OwnerMigrationTargetReconciliation:
        """Build expected digest-only evidence for target adapter checks."""

        return OwnerMigrationTargetReconciliation(
            plan_fingerprint=plan.plan_fingerprint,
            object_count=plan.object_count,
            file_count=plan.file_count,
            object_set_fingerprint=cls._set_fingerprint(
                "m14-target-objects-v1",
                tuple(
                    item.object_digest
                    for table in plan.tables
                    for item in table.objects
                ),
            ),
            file_set_fingerprint=cls._set_fingerprint(
                "m14-target-files-v1",
                tuple(
                    digest
                    for file_plan in plan.files
                    for digest in file_plan.object_digests
                ),
            ),
        )

    @staticmethod
    def _set_fingerprint(namespace: str, digests: tuple[str, ...]) -> str:
        payload = json.dumps(
            (namespace, *sorted(digests)),
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    @staticmethod
    def _receipt(
        outcome: Literal["applied", "already_applied"],
        plan: OwnerMigrationPlanReport,
    ) -> OwnerMigrationExecutionReceipt:
        return OwnerMigrationExecutionReceipt(
            outcome=outcome,
            plan_fingerprint=plan.plan_fingerprint,
            target_binding_fingerprint=plan.target_binding_fingerprint,
            object_count=plan.object_count,
            file_count=plan.file_count,
        )
