"""Search Agent 领域模型。

这些类型属于 math-teacher-agent 产品本身，绝不是 LLM JSON 的透传：
- LLM 只能参与“理解需求 / 选择工具调用 / 解释结果”；
- SearchIntent / SearchPlan / SearchAgentResponse 由本模块定义、校验、构建；
- 结果事实字段必须来自 Tool / Business Service 证据（grounding）。
"""

from __future__ import annotations

import time
from typing import Any, Literal

from pydantic import BaseModel, Field

ConstraintStrength = Literal["hard", "soft", "default"]
ConstraintOrigin = Literal["explicit", "inferred", "system_default"]
TeachingUsage = Literal[
    "classroom_example",
    "in_class_practice",
    "homework",
    "exam_review",
    "diagnostic",
    "warm_up",
    "challenge",
    "general",
]
SearchConfidence = Literal["high", "medium", "low"]
SearchPlanStepStatus = Literal["pending", "completed", "skipped", "failed"]
SearchAgentStatus = Literal["pending", "running", "ok", "error", "cancelled"]

SEARCH_DEFAULT_COUNT = 5
SEARCH_HARD_MAX_COUNT = 20


class SearchConstraint(BaseModel):
    """单条检索约束：必须可追溯 strength / origin / confidence。"""

    field: str
    value: Any
    strength: ConstraintStrength
    origin: ConstraintOrigin
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    reason: str = ""


class CurriculumNodeRef(BaseModel):
    node_id: str
    code: str = ""
    name: str = ""
    node_type: str = "knowledge_point"


class CurriculumMapping(BaseModel):
    """教材映射：node_id 只允许来自真实 Curriculum Catalog。"""

    version: str | None = None
    textbook: str | None = None
    volume: str | None = None
    chapter: str | None = None
    section: str | None = None
    knowledge_point_ids: list[str] = Field(default_factory=list)
    knowledge_point_names: list[str] = Field(default_factory=list)
    matched_nodes: list[CurriculumNodeRef] = Field(default_factory=list)


class SearchIntent(BaseModel):
    """本产品自有的结构化搜索意图（domain model）。"""

    raw_query: str
    subject: str = "math"
    school_stage: str = "high_school"
    grade: str | None = None
    curriculum_version: str | None = None
    book: str | None = None
    volume: str | None = None
    chapter: str | None = None
    knowledge_points: list[str] = Field(default_factory=list)
    sub_knowledge_points: list[str] = Field(default_factory=list)
    question_types: list[str] = Field(default_factory=list)
    difficulty: int | None = None
    difficulty_range: list[int] = Field(default_factory=list, max_length=2)
    requested_count: int | None = None
    count: int = SEARCH_DEFAULT_COUNT
    limit_applied: bool = False
    year_from: int | None = None
    year_to: int | None = None
    regions: list[str] = Field(default_factory=list)
    source_preferences: list[str] = Field(default_factory=list)
    teaching_usage: TeachingUsage = "general"
    exclude_question_ids: list[str] = Field(default_factory=list)
    exclude_similar_to: list[str] = Field(default_factory=list)
    require_verified: bool = False
    allow_related_fallback: bool = False
    deduplicate: bool = True
    diversify: bool = True
    curriculum: CurriculumMapping = Field(default_factory=CurriculumMapping)
    constraints: list[SearchConstraint] = Field(default_factory=list)
    parse_warnings: list[str] = Field(default_factory=list)

    def hard_constraints(self) -> list[SearchConstraint]:
        return [item for item in self.constraints if item.strength == "hard"]

    def soft_constraints(self) -> list[SearchConstraint]:
        return [item for item in self.constraints if item.strength == "soft"]


class SearchPlanStep(BaseModel):
    step: int
    title: str
    status: SearchPlanStepStatus = "pending"
    detail: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""


class SearchPlan(BaseModel):
    plan_id: str
    intent_summary: dict[str, Any] = Field(default_factory=dict)
    steps: list[SearchPlanStep] = Field(default_factory=list)
    applied_filters: dict[str, Any] = Field(default_factory=dict)
    soft_preferences: list[str] = Field(default_factory=list)
    relaxations: list[dict[str, Any]] = Field(default_factory=list)
    candidate_count: int = 0
    selected_count: int = 0
    generated_at: float = Field(default_factory=time.time)


class MatchReason(BaseModel):
    code: str
    label: str
    strength: str = "hard"


class Relaxation(BaseModel):
    field: str
    from_value: Any = None
    to_value: Any = None
    reason: str = ""
    disclosed: bool = True


class UnmetConstraint(BaseModel):
    field: str
    requested: Any = None
    matched_count: int = 0
    reason: str = ""


class SearchAgentResultItem(BaseModel):
    question_id: str
    stem: str = ""
    stem_preview: str = ""
    question_type: str = ""
    knowledge_points: list[str] = Field(default_factory=list)
    difficulty: int = 0
    verification_status: str = ""
    source_status: str = ""
    visibility: str = ""
    chapter: str | None = None
    section: str | None = None
    volume: str | None = None
    year: int | None = None
    region: str | None = None
    match_reasons: list[MatchReason] = Field(default_factory=list)
    relaxed_fields: list[str] = Field(default_factory=list)
    similarity_group: str | None = None
    grounded: bool = True


class SearchAgentResponse(BaseModel):
    """Search Agent 最终响应：事实字段全部 grounded，前端绝不解析 Markdown。"""

    request_id: str
    session_id: str = ""
    run_id: str = ""
    raw_query: str
    status: SearchAgentStatus = "pending"
    intent: SearchIntent
    plan_summary: SearchPlan
    results: list[SearchAgentResultItem] = Field(default_factory=list)
    requested_count: int = SEARCH_DEFAULT_COUNT
    effective_count: int = 0
    returned_count: int = 0
    exact_match_count: int = 0
    exact_match: bool = False
    relaxations: list[Relaxation] = Field(default_factory=list)
    unmet_constraints: list[UnmetConstraint] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    answer_summary: str = ""
    assistant_explanation: str | None = None
    search_confidence: SearchConfidence = "low"
    suggestions: list[str] = Field(default_factory=list)
    duration_ms: int = 0
    tool_call_count: int = 0
    candidate_count: int = 0
    error: dict[str, Any] | None = None


class SearchAgentRunRecord(BaseModel):
    run_id: str
    request_id: str
    session_id: str = ""
    status: SearchAgentStatus = "pending"
    raw_query: str = ""
    intent: SearchIntent | None = None
    plan_summary: SearchPlan | None = None
    response: SearchAgentResponse | None = None
    error: dict[str, Any] | None = None
    created_at: float = Field(default_factory=time.time)
    finished_at: float | None = None
