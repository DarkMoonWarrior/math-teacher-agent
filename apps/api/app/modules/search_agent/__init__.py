"""Search Agent（Prompt 3）：可信、grounded 的高中数学教师搜题能力。"""

from .domain import (
    CurriculumMapping,
    CurriculumNodeRef,
    MatchReason,
    Relaxation,
    SearchAgentResponse,
    SearchAgentResultItem,
    SearchAgentRunRecord,
    SearchConstraint,
    SearchIntent,
    SearchPlan,
    SearchPlanStep,
    UnmetConstraint,
)
from .intent_parser import SearchIntentParser
from .pipeline import SearchAgentPipeline
from .planner import build_search_plan

__all__ = [
    "CurriculumMapping",
    "CurriculumNodeRef",
    "MatchReason",
    "Relaxation",
    "SearchAgentResponse",
    "SearchAgentResultItem",
    "SearchAgentRunRecord",
    "SearchConstraint",
    "SearchIntent",
    "SearchAgentPipeline",
    "SearchIntentParser",
    "SearchPlan",
    "SearchPlanStep",
    "UnmetConstraint",
    "build_search_plan",
]
