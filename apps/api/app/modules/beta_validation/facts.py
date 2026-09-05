from __future__ import annotations

import sqlite3
from dataclasses import dataclass
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
        try:
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
            receipts = self._metrics._record_batch(
                owner_id=owner_id,
                observations=tuple(observations),
            )
        except BetaValidationLifecycleError:
            return BetaFactResult("not_participating")
        except (OSError, sqlite3.Error):
            return BetaFactResult("unavailable")
        except (TypeError, ValueError, ValidationError):
            return BetaFactResult("invalid")
        return BetaFactResult("recorded", len(receipts))

    def record_tool_failure(
        self,
        *,
        owner_id: str,
        workflow: BetaWorkflow,
        task_ref: str,
        tool_call_count: int,
    ) -> BetaFactResult:
        if self._metrics is None:
            return BetaFactResult(
                "unavailable" if self._unavailable else "disabled"
            )
        if tool_call_count <= 0:
            return BetaFactResult("invalid")
        try:
            receipts = self._metrics._record_batch(
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
        except BetaValidationLifecycleError:
            return BetaFactResult("not_participating")
        except (OSError, sqlite3.Error):
            return BetaFactResult("unavailable")
        except (TypeError, ValueError, ValidationError):
            return BetaFactResult("invalid")
        return BetaFactResult("recorded", len(receipts))
