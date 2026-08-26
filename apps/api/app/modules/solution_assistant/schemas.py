from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator


SolutionMode = Literal["standard", "alternative"]
SolutionConfidence = Literal[
    "program_verified",
    "model_reviewed",
    "teacher_review_required",
]
MathVerificationStatus = Literal["passed", "failed", "inconclusive"]
MathVerificationCapability = Literal["supported", "unsupported"]
MathVerificationScope = Literal[
    "question_answer",
    "matched_question_record",
    "generated_solution",
]
MathVerificationEvidenceSource = Literal[
    "math_verifier",
    "teacher_evidence",
    "stored_status",
    "none",
]


class SolutionRequest(BaseModel):
    question_text: str = Field(min_length=5, max_length=30000)
    solution_mode: SolutionMode = "standard"
    teacher_instruction: str = Field(default="", max_length=2000)
    teacher_id: str = Field(default="owner_teacher", min_length=1, max_length=120)


class SolutionExplanation(BaseModel):
    method: str = Field(min_length=1, max_length=500)
    steps: list[str] = Field(min_length=1, max_length=100)
    final_answer: str = Field(min_length=1, max_length=4000)


class GeneratedSolution(BaseModel):
    explanation: SolutionExplanation
    knowledge_points: list[str] = Field(default_factory=list, max_length=30)
    common_mistakes: list[str] = Field(default_factory=list, max_length=20)
    teaching_notes: list[str] = Field(default_factory=list, max_length=20)


@dataclass(frozen=True, slots=True)
class SolutionVisualInput:
    """Internal-only visual payload. It is never serialized to Agent or browser."""

    asset_id: str
    media_revision: int
    recognition_revision: int
    requires_visual_reasoning: bool
    visual_processing_consent: bool
    image_bytes: bytes | None
    image_mime_type: str | None


class SolutionVisualContext(BaseModel):
    model_config = {"extra": "forbid"}

    asset_id: str
    media_revision: int = Field(ge=1)
    recognition_revision: int = Field(ge=1)
    requires_visual_reasoning: bool
    visual_processing_consent: bool
    image_used: bool
    provider: str
    model: str


class MathVerificationAssessment(BaseModel):
    """Independent verification state; scope prevents evidence over-claiming."""

    status: MathVerificationStatus
    capability: MathVerificationCapability
    scope: MathVerificationScope
    evidence_source: MathVerificationEvidenceSource
    method: str | None = None
    computed_answer: str | None = None
    source_answer: str | None = None
    details: list[str] = Field(default_factory=list, max_length=100)
    verifier_version: str | None = None


class SolutionResult(BaseModel):
    question_text: str
    solution_mode: SolutionMode
    explanation: SolutionExplanation
    knowledge_points: list[str]
    common_mistakes: list[str]
    teaching_notes: list[str]
    confidence_status: SolutionConfidence
    math_verification: MathVerificationAssessment
    verification_evidence: list[str]
    provider: str
    model: str
    mode: Literal["verified_bank", "live_ai"]
    matched_question_id: str | None = None
    matched_question_revision_count: int | None = Field(default=None, ge=0)
    match_score: float | None = Field(default=None, ge=0, le=1)
    alternative_available: bool = False
    warnings: list[str] = Field(default_factory=list)
    visual_context: SolutionVisualContext | None = None

    @model_validator(mode="after")
    def enforce_trust_invariants(self) -> Self:
        if self.mode == "live_ai" and self.confidence_status == "program_verified":
            raise ValueError("模型实时生成结果不能标记为 program_verified")
        if (
            self.math_verification.status in {"failed", "inconclusive"}
            and self.confidence_status == "program_verified"
        ):
            raise ValueError("验证未通过或不确定时不能标记为 program_verified")
        if self.confidence_status == "program_verified":
            if self.mode != "verified_bank":
                raise ValueError("program_verified 只能来自 verified_bank")
            if (
                self.math_verification.status != "passed"
                or self.math_verification.capability != "supported"
                or self.math_verification.scope != "question_answer"
            ):
                raise ValueError("program_verified 必须有题库答案范围内的独立验证通过证据")
        if self.verification_evidence != self.math_verification.details:
            raise ValueError("verification_evidence 必须与 math_verification.details 一致")
        if self.visual_context is not None:
            visual = self.visual_context
            if visual.image_used and not visual.visual_processing_consent:
                raise ValueError("原图参与推理必须有本次视觉处理同意")
            if visual.requires_visual_reasoning and not visual.image_used:
                raise ValueError("依赖原图的题目必须实际使用视觉输入")
            if visual.image_used and self.mode != "live_ai":
                raise ValueError("视觉模型新解不能冒充已验证题库解析")
            if visual.image_used and self.confidence_status != "teacher_review_required":
                raise ValueError("视觉模型新解必须由教师复核")
        return self
