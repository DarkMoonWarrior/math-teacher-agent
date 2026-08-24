from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


QuestionType = Literal[
    "single_choice",
    "multiple_choice",
    "fill_blank",
    "open_response",
]
GradeLevel = Literal["高一", "高二", "高三"]


class QuestionDesignBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_text: str = Field(min_length=5, max_length=4000)
    grade: GradeLevel | None = None
    curriculum_node_id: str | None = Field(default=None, max_length=160)
    knowledge_point_query: str | None = Field(default=None, max_length=300)
    question_type: QuestionType | None = None
    target_difficulty: int = Field(default=3, ge=1, le=5)
    teaching_purpose: str = Field(default="课堂练习", max_length=300)
    expected_minutes: int | None = Field(default=None, ge=1, le=120)
    assessed_method: str = Field(default="", max_length=1000)
    misconception_requirements: str = Field(default="", max_length=1000)
    additional_constraints: str = Field(default="", max_length=2000)
    reference_question_id: str | None = Field(default=None, max_length=160)


class QuestionDraftOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=12)
    text: str = Field(min_length=1, max_length=4000)


class QuestionDraftCurriculum(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    name: str
    volume: str
    chapter: str
    section: str
    mapping_source: Literal["teacher_selected", "brief_match"]
    match_confidence: float = Field(ge=0, le=1)
    curriculum_status: str
    reviewed_by: str


class QuestionDraftVerification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["not_run"] = "not_run"
    math_verifier_checked: Literal[False] = False
    teacher_review_required: Literal[True] = True
    details: list[str] = Field(default_factory=list)


class GeneratedQuestionDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_id: str
    request_text: str
    question_type: QuestionType
    stem_plain: str = Field(min_length=5, max_length=20000)
    stem_latex: str | None = Field(default=None, max_length=20000)
    options: list[QuestionDraftOption] = Field(default_factory=list, max_length=20)
    answer_value: str = Field(min_length=1, max_length=4000)
    solution_method: str = Field(min_length=1, max_length=500)
    solution_steps: list[str] = Field(min_length=1, max_length=100)
    final_answer: str = Field(min_length=1, max_length=4000)
    authoring_intent: str = Field(min_length=1, max_length=2000)
    curriculum: QuestionDraftCurriculum
    target_difficulty: int = Field(ge=1, le=5)
    estimated_difficulty: int = Field(ge=1, le=5)
    difficulty_source: Literal["model_estimated"] = "model_estimated"
    verification: QuestionDraftVerification
    source_type: Literal["ai_generated"] = "ai_generated"
    visibility: Literal["owner_only"] = "owner_only"
    public_search_allowed: Literal[False] = False
    share_allowed: Literal[False] = False
    commercial_use_allowed: Literal[False] = False
    model_training_allowed: Literal[False] = False
    saved: Literal[False] = False
    provider: str
    model: str
    prompt_revision: str
    warnings: list[str] = Field(default_factory=list)
    created_at: str


class ProviderQuestionDraft(BaseModel):
    """Internal provider output; trust/privacy fields are never model-controlled."""

    model_config = ConfigDict(extra="forbid")

    question_type: QuestionType
    stem_plain: str = Field(min_length=5, max_length=20000)
    stem_latex: str | None = Field(default=None, max_length=20000)
    options: list[QuestionDraftOption] = Field(default_factory=list, max_length=20)
    answer_value: str = Field(min_length=1, max_length=4000)
    solution_method: str = Field(min_length=1, max_length=500)
    solution_steps: list[str] = Field(min_length=1, max_length=100)
    final_answer: str = Field(min_length=1, max_length=4000)
    authoring_intent: str = Field(min_length=1, max_length=2000)
    estimated_difficulty: int = Field(ge=1, le=5)
