from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


TeacherPreferenceKey = Literal[
    "default_grade",
    "default_difficulty",
    "default_lesson_minutes",
    "solution_detail_level",
    "preferred_question_types",
]
TeacherPreferenceValue = str | int | list[str]
TeacherPreferenceEvidenceCategory = Literal[
    "confirmed_lesson_version",
    "confirmed_paper_version",
]


class TeacherPreferenceSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["teacher_explicit"] = "teacher_explicit"
    label: str = "教师明确设置"
    confidence: float = Field(default=1.0, ge=0, le=1)


class TeacherPreference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: TeacherPreferenceKey
    label: str
    value: TeacherPreferenceValue
    source: TeacherPreferenceSource
    updated_at: str


class TeacherPlanningPreference(BaseModel):
    """One provenance-preserving preference that a planner may use as a default."""

    model_config = ConfigDict(extra="forbid")

    key: TeacherPreferenceKey
    label: str
    value: TeacherPreferenceValue
    source: TeacherPreferenceSource


class TeacherPlanningDefaults(BaseModel):
    """Allowlisted defaults exposed to planning modules without owner identity."""

    model_config = ConfigDict(extra="forbid")

    preferences: list[TeacherPlanningPreference] = Field(default_factory=list)

    def get(self, key: TeacherPreferenceKey) -> TeacherPlanningPreference | None:
        return next((item for item in self.preferences if item.key == key), None)


class TeacherPreferenceProposalEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: TeacherPreferenceEvidenceCategory
    label: str
    occurrence_count: int = Field(ge=3)


class TeacherPreferenceProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: str
    key: TeacherPreferenceKey
    label: str
    value: TeacherPreferenceValue
    status: Literal["pending_teacher_review"] = "pending_teacher_review"
    confidence: float = Field(gt=0, lt=1)
    evidence: TeacherPreferenceProposalEvidence
    created_at: str
    updated_at: str


class TeacherPreferenceFeedback(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feedback_id: str
    proposal_id: str
    key: TeacherPreferenceKey
    label: str
    proposed_value: TeacherPreferenceValue
    resolved_value: TeacherPreferenceValue | None = None
    action: Literal["accept", "reject", "correct"]
    confidence: float = Field(gt=0, lt=1)
    evidence: TeacherPreferenceProposalEvidence
    created_at: str


class TeacherPreferenceSignal(BaseModel):
    """Product-owned structured evidence; this type is never an HTTP request model."""

    model_config = ConfigDict(extra="forbid")

    key: TeacherPreferenceKey
    value: TeacherPreferenceValue
    evidence_category: TeacherPreferenceEvidenceCategory
    evidence_id: str = Field(min_length=1, max_length=200)


class TeacherMemoryProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=0)
    auto_learning_enabled: bool = False
    preferences: list[TeacherPreference] = Field(default_factory=list)
    proposals: list[TeacherPreferenceProposal] = Field(default_factory=list)
    feedback: list[TeacherPreferenceFeedback] = Field(default_factory=list)
    privacy_note: str = "仅保存结构化教学偏好与可解释提议，不保存题目、解析、教案或私人资料正文。"
    retention_note: str = "结构化偏好、提议与反馈保留至教师修改、处理或执行“删除全部教师记忆”；不保留任务正文。"


class TeacherMemoryCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: Literal[
        "upsert",
        "remove",
        "set_auto_learning",
        "accept_proposal",
        "reject_proposal",
        "correct_proposal",
        "delete_all",
    ]
    key: TeacherPreferenceKey | None = None
    value: TeacherPreferenceValue | None = None
    enabled: bool | None = None
    proposal_id: str | None = Field(default=None, min_length=1, max_length=80)
    confirmation: str | None = Field(default=None, max_length=40)
    expected_version: int | None = Field(default=None, ge=0)
