from __future__ import annotations

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
    match_score: float | None = Field(default=None, ge=0, le=1)
    alternative_available: bool = False
    warnings: list[str] = Field(default_factory=list)

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
        return self
