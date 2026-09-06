from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from pydantic import ValidationError

from app.modules.beta_validation.metrics import (
    BetaValidationLifecycleError,
    BetaValidationMetrics,
)
from app.modules.beta_validation.schemas import (
    BetaTrustTier,
    BetaValidationEventType,
    BetaValidationObservation,
    BetaWorkflow,
)


BetaServerFact = Literal[
    "search_completed",
    "solve_completed",
    "paper_generated",
    "paper_exported",
    "lesson_generated",
    "lesson_saved",
    "private_library_import_confirmed",
    "authoring_completed",
    "authoring_saved",
]
BetaFactState = Literal[
    "recorded",
    "disabled",
    "not_participating",
    "unavailable",
    "invalid",
]
BetaTaskDecision = Literal["accepted", "rejected"]


@dataclass(frozen=True, slots=True)
class BetaFactResult:
    state: BetaFactState
    recorded_events: int = 0


@dataclass(frozen=True, slots=True)
class _FactDefinition:
    workflow: BetaWorkflow
    event_type: BetaValidationEventType | None
    completes_task: bool


_FACTS: dict[BetaServerFact, _FactDefinition] = {
    "search_completed": _FactDefinition("search", "search_completed", True),
    "solve_completed": _FactDefinition("solve", None, True),
    "paper_generated": _FactDefinition("paper", "paper_generated", True),
    "paper_exported": _FactDefinition("paper", "paper_exported", False),
    "lesson_generated": _FactDefinition("lesson", "lesson_generated", True),
    "lesson_saved": _FactDefinition("lesson", "lesson_saved", False),
    "private_library_import_confirmed": _FactDefinition(
        "library", "private_library_import_confirmed", False
    ),
    "authoring_completed": _FactDefinition(
        "authoring", "authoring_completed", True
    ),
    "authoring_saved": _FactDefinition("authoring", "authoring_saved", False),
}

_MODEL_FEATURE_WORKFLOWS: dict[str, BetaWorkflow] = {
    "question_authoring": "authoring",
    "solution_assistant": "solve",
    "private_resource_ocr": "library",
    "private_question_ocr": "solve",
    "lesson_plan_generation": "lesson",
    "lesson_block_rewrite": "lesson",
    "question_variant": "solve",
    "question_variant_polish": "solve",
}


class BetaValidationFacts:
    """Translate successful server-owned checkpoints into content-blind metrics.

    Product routes only name the fact they have completed. Consent, event mapping,
    paired completion events and analytics failures remain behind this Interface.
    """

    def __init__(
        self,
        metrics: BetaValidationMetrics | None,
        *,
        unavailable: bool = False,
    ) -> None:
        self._metrics = metrics
        self._unavailable = unavailable

    @classmethod
    def disabled(cls) -> BetaValidationFacts:
        return cls(None)

    @classmethod
    def unavailable(cls) -> BetaValidationFacts:
        return cls(None, unavailable=True)

    def record_checkpoint(
        self,
        *,
        owner_id: str,
        fact: BetaServerFact,
        task_ref: str,
        duration_ms: int | None = None,
        trust_tier: BetaTrustTier | None = None,
        tool_call_count: int = 0,
    ) -> BetaFactResult:
        if self._metrics is None:
            return BetaFactResult(
                "unavailable" if self._unavailable else "disabled"
            )
        definition = _FACTS.get(fact)
        if definition is None:
            return BetaFactResult("invalid")
        if definition.completes_task and (
            duration_ms is None or trust_tier is None
        ):
            return BetaFactResult("invalid")
        observations: list[BetaValidationObservation] = []
        if definition.event_type is not None:
            observations.append(
                BetaValidationObservation(
                    workflow=definition.workflow,
                    event_type=definition.event_type,
                    task_ref=task_ref,
                )
            )
        if definition.completes_task:
            observations.append(
                BetaValidationObservation(
                    workflow=definition.workflow,
                    event_type="task_completed",
                    task_ref=task_ref,
                    trust_tier=trust_tier,
                    duration_ms=duration_ms,
                )
            )
        if tool_call_count < 0:
            return BetaFactResult("invalid")
        observations.extend(
            BetaValidationObservation(
                workflow=definition.workflow,
                event_type="agent_tool_succeeded",
                task_ref=task_ref,
            )
            for _ in range(tool_call_count)
        )
        return self._record(owner_id=owner_id, observations=tuple(observations))

    def record_search_selection(
        self,
        *,
        owner_id: str,
        task_ref: str,
    ) -> BetaFactResult:
        """Record an owner-validated result choice and its acceptance together."""

        return self._record(
            owner_id=owner_id,
            observations=(
                BetaValidationObservation(
                    workflow="search",
                    event_type="search_result_selected",
                    task_ref=task_ref,
                ),
                BetaValidationObservation(
                    workflow="search",
                    event_type="task_accepted",
                    task_ref=task_ref,
                ),
            ),
        )

    def record_task_decision(
        self,
        *,
        owner_id: str,
        workflow: BetaWorkflow,
        task_ref: str,
        decision: BetaTaskDecision,
    ) -> BetaFactResult:
        return self._record(
            owner_id=owner_id,
            observations=(
                BetaValidationObservation(
                    workflow=workflow,
                    event_type=(
                        "task_accepted" if decision == "accepted" else "task_rejected"
                    ),
                    task_ref=task_ref,
                ),
            ),
        )

    def record_model_usage(
        self,
        *,
        owner_id: str,
        feature: str,
        task_ref: str,
        model_cost_usd: Decimal,
    ) -> BetaFactResult:
        """Accept only an already-priced, server-attributed model run."""

        workflow = _MODEL_FEATURE_WORKFLOWS.get(feature)
        if workflow is None:
            return BetaFactResult("invalid")
        if model_cost_usd <= 0:
            return BetaFactResult("invalid")
        return self._record(
            owner_id=owner_id,
            observations=(
                BetaValidationObservation(
                    workflow=workflow,
                    event_type="model_usage",
                    task_ref=task_ref,
                    model_cost_usd=model_cost_usd,
                ),
            ),
        )

    def record_tool_failure(
        self,
        *,
        owner_id: str,
        workflow: BetaWorkflow,
        task_ref: str,
        tool_call_count: int,
    ) -> BetaFactResult:
        if tool_call_count <= 0:
            return BetaFactResult("invalid")
        return self._record(
            owner_id=owner_id,
            observations=tuple(
                BetaValidationObservation(
                    workflow=workflow,
                    event_type="agent_tool_failed",
                    task_ref=task_ref,
                )
                for _ in range(tool_call_count)
            ),
        )

    def _record(
        self,
        *,
        owner_id: str,
        observations: tuple[BetaValidationObservation, ...],
    ) -> BetaFactResult:
        if self._metrics is None:
            return BetaFactResult(
                "unavailable" if self._unavailable else "disabled"
            )
        try:
            receipts = self._metrics._record_batch(
                owner_id=owner_id,
                observations=observations,
            )
        except BetaValidationLifecycleError:
            return BetaFactResult("not_participating")
        except (OSError, sqlite3.Error):
            return BetaFactResult("unavailable")
        except (TypeError, ValueError, ValidationError):
            return BetaFactResult("invalid")
        return BetaFactResult("recorded", len(receipts))
