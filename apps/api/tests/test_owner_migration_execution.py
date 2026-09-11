from __future__ import annotations

from typing import Literal

import pytest

from app.modules.tenant_migration.execution import (
    OwnerMigrationExecutionError,
    OwnerMigrationExecutor,
)
from app.modules.tenant_migration.schemas import (
    OwnerMigrationFilePlan,
    OwnerMigrationObjectPlan,
    OwnerMigrationPlanReport,
    OwnerMigrationTablePlan,
    OwnerMigrationTargetReconciliation,
    OwnerMigrationTargetState,
)


def _plan() -> OwnerMigrationPlanReport:
    return OwnerMigrationPlanReport(
        source_inventory_fingerprint="c" * 64,
        source_file_reconciliation_fingerprint="d" * 64,
        target_binding_fingerprint="b" * 64,
        object_count=1,
        file_count=1,
        plan_fingerprint="a" * 64,
        tables=(
            OwnerMigrationTablePlan(
                store_id="private_library",
                table_name="library_items",
                ownership="direct",
                sequence=1,
                object_count=1,
                object_set_fingerprint="e" * 64,
                objects=(
                    OwnerMigrationObjectPlan(
                        object_digest="1" * 64,
                        source_record_fingerprint="2" * 64,
                    ),
                ),
            ),
        ),
        files=(
            OwnerMigrationFilePlan(
                store_id="private_library_files",
                sequence=2,
                object_count=1,
                object_set_fingerprint="f" * 64,
                object_digests=("3" * 64,),
            ),
        ),
    )


class _Planner:
    def __init__(self, plan: OwnerMigrationPlanReport) -> None:
        self.result = plan
        self.calls = 0
        self.fail = False

    def plan(self, **kwargs) -> OwnerMigrationPlanReport:
        self.calls += 1
        if self.fail:
            raise RuntimeError("raw source failure")
        return self.result


class _Transaction:
    def __init__(self, target: "_Target") -> None:
        self.target = target
        self.before: tuple[str, str | None] | None = None

    def __enter__(self) -> "_Transaction":
        self.before = (self.target.state, self.target.stored_plan)
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if exc_type is not None:
            assert self.before is not None
            self.target.state, self.target.stored_plan = self.before
            self.target.rollbacks += 1

    def inspect(self) -> OwnerMigrationTargetState:
        return OwnerMigrationTargetState(
            state=self.target.state,
            target_binding_fingerprint=self.target.binding,
            plan_fingerprint=self.target.stored_plan,
        )

    def apply(self, plan: OwnerMigrationPlanReport) -> None:
        self.target.applies += 1
        self.target.state = "in_progress"
        self.target.stored_plan = plan.plan_fingerprint
        self.target.reconciliation = OwnerMigrationExecutor.reconciliation_for(plan)

    def reconcile(self) -> OwnerMigrationTargetReconciliation:
        assert self.target.reconciliation is not None
        if self.target.corrupt_reconciliation:
            return self.target.reconciliation.model_copy(
                update={"object_count": self.target.reconciliation.object_count + 1}
            )
        return self.target.reconciliation

    def mark_complete(self) -> None:
        self.target.state = "complete"


class _Target:
    def __init__(self, plan: OwnerMigrationPlanReport) -> None:
        self.binding = plan.target_binding_fingerprint
        self.state: Literal["empty", "in_progress", "complete", "unexpected"] = (
            "empty"
        )
        self.stored_plan: str | None = None
        self.reconciliation: OwnerMigrationTargetReconciliation | None = None
        self.corrupt_reconciliation = False
        self.applies = 0
        self.rollbacks = 0
        self.transactions = 0

    def transaction(self, **kwargs) -> _Transaction:
        self.transactions += 1
        assert len(kwargs["target_binding_fingerprint"]) == 64
        assert len(kwargs["plan_fingerprint"]) == 64
        return _Transaction(self)


def _execute(executor: OwnerMigrationExecutor):
    return executor.execute(
        source_owner_id="owner-alpha",
        target_owner_id="owner-production",
        target_tenant_id="tenant-production",
        expected_inventory_fingerprint="c" * 64,
        expected_file_reconciliation_fingerprint="d" * 64,
        expected_plan_fingerprint="a" * 64,
        confirmation="执行 owner 数据迁移",
        confirmed=True,
    )


def test_confirmation_is_required_before_plan_or_target_access() -> None:
    plan = _plan()
    planner = _Planner(plan)
    target = _Target(plan)
    executor = OwnerMigrationExecutor(planner, target)

    with pytest.raises(
        OwnerMigrationExecutionError,
        match="MIGRATION_EXECUTION_CONFIRMATION_REQUIRED",
    ):
        executor.execute(
            source_owner_id="owner-alpha",
            target_owner_id="owner-production",
            target_tenant_id="tenant-production",
            expected_inventory_fingerprint="c" * 64,
            expected_file_reconciliation_fingerprint="d" * 64,
            expected_plan_fingerprint="a" * 64,
            confirmation="执行迁移",
            confirmed=True,
        )

    assert planner.calls == 0
    assert target.transactions == 0


def test_changed_plan_is_rejected_before_target_access() -> None:
    plan = _plan().model_copy(update={"plan_fingerprint": "8" * 64})
    planner = _Planner(plan)
    target = _Target(plan)

    with pytest.raises(OwnerMigrationExecutionError, match="MIGRATION_PLAN_CHANGED"):
        _execute(OwnerMigrationExecutor(planner, target))

    assert planner.calls == 1
    assert target.transactions == 0


def test_execution_reconciles_before_commit_and_returns_digest_only_receipt() -> None:
    plan = _plan()
    target = _Target(plan)

    receipt = _execute(OwnerMigrationExecutor(_Planner(plan), target))

    assert receipt.outcome == "applied"
    assert receipt.reconciled is True
    assert receipt.object_count == 1
    assert receipt.file_count == 1
    assert target.state == "complete"
    assert target.applies == 1
    serialized = receipt.model_dump_json()
    assert "owner-alpha" not in serialized
    assert "owner-production" not in serialized
    assert "tenant-production" not in serialized


def test_completed_matching_plan_is_idempotent() -> None:
    plan = _plan()
    target = _Target(plan)
    executor = OwnerMigrationExecutor(_Planner(plan), target)

    first = _execute(executor)
    second = _execute(executor)

    assert first.outcome == "applied"
    assert second.outcome == "already_applied"
    assert target.applies == 1
    assert target.rollbacks == 0


def test_reconciliation_failure_rolls_back_atomic_target_transaction() -> None:
    plan = _plan()
    target = _Target(plan)
    target.corrupt_reconciliation = True

    with pytest.raises(
        OwnerMigrationExecutionError,
        match="MIGRATION_TARGET_RECONCILIATION_FAILED",
    ):
        _execute(OwnerMigrationExecutor(_Planner(plan), target))

    assert target.state == "empty"
    assert target.stored_plan is None
    assert target.rollbacks == 1


@pytest.mark.parametrize("state", ["in_progress", "unexpected"])
def test_unfinished_or_unexpected_target_state_fails_closed(state: str) -> None:
    plan = _plan()
    target = _Target(plan)
    target.state = state  # type: ignore[assignment]
    if state == "in_progress":
        target.stored_plan = plan.plan_fingerprint

    with pytest.raises(
        OwnerMigrationExecutionError,
        match="MIGRATION_TARGET_STATE_UNEXPECTED",
    ):
        _execute(OwnerMigrationExecutor(_Planner(plan), target))

    assert target.applies == 0
    assert target.rollbacks == 1


@pytest.mark.parametrize(
    ("mismatch", "code"),
    (
        ("binding", "MIGRATION_TARGET_BINDING_MISMATCH"),
        ("plan", "MIGRATION_TARGET_PLAN_MISMATCH"),
    ),
)
def test_existing_target_for_another_binding_or_plan_fails_closed(
    mismatch: str,
    code: str,
) -> None:
    plan = _plan()
    target = _Target(plan)
    if mismatch == "binding":
        target.binding = "7" * 64
    else:
        target.state = "complete"
        target.stored_plan = "6" * 64

    with pytest.raises(OwnerMigrationExecutionError, match=code):
        _execute(OwnerMigrationExecutor(_Planner(plan), target))

    assert target.applies == 0
    assert target.rollbacks == 1


def test_planner_failure_is_sanitized_before_target_access() -> None:
    plan = _plan()
    planner = _Planner(plan)
    planner.fail = True
    target = _Target(plan)

    with pytest.raises(
        OwnerMigrationExecutionError,
        match="MIGRATION_PLAN_RECHECK_FAILED",
    ):
        _execute(OwnerMigrationExecutor(planner, target))

    assert target.transactions == 0
