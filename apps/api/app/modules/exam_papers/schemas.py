from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.question_bank.schemas import QuestionSummary


ExamPaperEdition = Literal["student", "answer", "blueprint"]
ExamPaperExportFormat = Literal["docx", "pdf"]
ExamPaperDifficultyProfile = Literal["foundation", "balanced", "challenge"]
ExamPaperReviewPolicy = Literal["approved_only", "verified"]
PaperBlueprintQuestionType = Literal[
    "single_choice", "multiple_choice", "fill_blank", "open_response"
]


class ExamPaperItemInput(BaseModel):
    question_id: str = Field(min_length=1, max_length=160)
    score: float = Field(gt=0, le=50)


class ExamPaperCreateCommand(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    duration_minutes: int = Field(default=90, ge=10, le=300)
    instructions: str = Field(default="答题前请填写姓名和班级；所有解答须写出必要过程。", max_length=1000)
    items: list[ExamPaperItemInput] = Field(min_length=1, max_length=50)
    teacher_id: str = Field(default="owner_teacher", min_length=1, max_length=120)


class ExamPaperUpdateCommand(ExamPaperCreateCommand):
    pass


class ExamPaperOptionSnapshot(BaseModel):
    key: str
    text: str


class ExamPaperImageSnapshot(BaseModel):
    asset_id: str
    original_filename: str
    mime_type: str
    width: int
    height: int
    alt_text: str
    caption: str


class ExamPaperQuestionSnapshot(BaseModel):
    question_id: str
    source_revision_count: int
    question_type: str
    stem_plain: str
    stem_latex: str | None = None
    options: list[ExamPaperOptionSnapshot] = Field(default_factory=list)
    answer_value: str | None = None
    solution_method: str | None = None
    solution_steps: list[str] = Field(default_factory=list)
    final_answer: str | None = None
    volume: str | None = None
    chapter: str | None = None
    section: str | None = None
    knowledge_point_ids: list[str] = Field(default_factory=list)
    difficulty: int
    verification_status: str
    review_status: str
    source_document: str
    license_status: str
    images: list[ExamPaperImageSnapshot] = Field(default_factory=list)


class ExamPaperItemView(BaseModel):
    item_id: str
    position: int
    section_title: str
    score: float
    question: ExamPaperQuestionSnapshot


class ExamPaperBreakdownItem(BaseModel):
    label: str
    question_count: int
    score: float


class ExamPaperView(BaseModel):
    exam_paper_id: str
    status: Literal["draft"] = "draft"
    version: int
    title: str
    duration_minutes: int
    instructions: str
    total_score: float
    items: list[ExamPaperItemView]
    chapter_breakdown: list[ExamPaperBreakdownItem]
    difficulty_breakdown: list[ExamPaperBreakdownItem]
    warnings: list[str] = Field(default_factory=list)
    created_at: str
    updated_at: str
    lifecycle_state: Literal["active", "trashed"] = "active"
    trashed_at: str | None = None


class ExamPaperSummary(BaseModel):
    exam_paper_id: str
    title: str
    status: str
    version: int
    duration_minutes: int
    total_score: float
    question_count: int
    updated_at: str
    lifecycle_state: Literal["active", "trashed"] = "active"
    trashed_at: str | None = None


class ExamPaperLifecycleCommand(BaseModel):
    action: Literal["trash", "restore"]
    actor_id: str = Field(default="owner_teacher", min_length=1, max_length=120)
    reason: str = Field(default="用户删除", max_length=2000)


class ExamPaperList(BaseModel):
    items: list[ExamPaperSummary]
    total: int


class ExamPaperTypeQuota(BaseModel):
    question_type: str = Field(min_length=1, max_length=80)
    count: int = Field(ge=1, le=30)


class ExamPaperComposeCommand(BaseModel):
    target_score: float = Field(ge=5, le=300)
    difficulty_profile: ExamPaperDifficultyProfile = "balanced"
    type_quotas: list[ExamPaperTypeQuota] = Field(min_length=1, max_length=8)
    chapters: list[str] = Field(default_factory=list, max_length=12)
    review_policy: ExamPaperReviewPolicy = "approved_only"
    exclude_question_ids: list[str] = Field(default_factory=list, max_length=100)
    item_scores: list[float] = Field(default_factory=list, max_length=50)
    seed: str = Field(default="default", max_length=120)

    @model_validator(mode="after")
    def validate_blueprint(self) -> "ExamPaperComposeCommand":
        question_types = [item.question_type for item in self.type_quotas]
        if len(question_types) != len(set(question_types)):
            raise ValueError("同一题型只能设置一次数量")
        if sum(item.count for item in self.type_quotas) > 50:
            raise ValueError("自动组卷最多选择 50 道题")
        if self.target_score * 2 != round(self.target_score * 2):
            raise ValueError("目标总分必须以 0.5 分为最小单位")
        total_count = sum(item.count for item in self.type_quotas)
        if self.item_scores:
            if len(self.item_scores) != total_count:
                raise ValueError("固定分值数量必须与题目总数一致")
            if any(score < 0.5 or score > 50 for score in self.item_scores):
                raise ValueError("固定分值必须介于 0.5 至 50 分")
            if any(score * 2 != round(score * 2) for score in self.item_scores):
                raise ValueError("固定分值必须以 0.5 分为最小单位")
            if abs(sum(self.item_scores) - self.target_score) > 1e-6:
                raise ValueError("固定分值合计必须等于目标总分")
        return self


class ExamPaperProposalItem(BaseModel):
    question: QuestionSummary
    score: float
    selection_reason: str


class ExamPaperProposal(BaseModel):
    target_score: float
    actual_score: float
    average_difficulty: float
    items: list[ExamPaperProposalItem]
    chapter_breakdown: list[ExamPaperBreakdownItem]
    difficulty_breakdown: list[ExamPaperBreakdownItem]
    warnings: list[str] = Field(default_factory=list)
    template_id: str | None = None
    template_name: str | None = None


class ExamPaperTemplateSection(BaseModel):
    section_title: str
    question_type: str
    count: int
    item_scores: list[float]


class ExamPaperTemplate(BaseModel):
    template_id: str
    name: str
    description: str
    region_scope: str
    duration_minutes: int
    target_score: float
    difficulty_profile: ExamPaperDifficultyProfile
    sections: list[ExamPaperTemplateSection]
    structure_status: Literal["recent_reference"]
    reviewed_on: str
    verification_note: str
    evidence_urls: list[str]


class ExamPaperTemplateList(BaseModel):
    items: list[ExamPaperTemplate]
    total: int


class ExamPaperTemplateComposeCommand(BaseModel):
    template_id: str = Field(min_length=1, max_length=120)
    chapters: list[str] = Field(default_factory=list, max_length=12)
    review_policy: ExamPaperReviewPolicy = "approved_only"
    exclude_question_ids: list[str] = Field(default_factory=list, max_length=100)
    seed: str = Field(default="default", max_length=120)


class PaperBlueprintBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brief: str = Field(min_length=5, max_length=4000)


class PaperBlueprintSection(BaseModel):
    section_id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=120)
    question_type: PaperBlueprintQuestionType
    question_count: int = Field(ge=0, le=30)
    target_score: float = Field(ge=0, le=300)


class PaperBlueprintTrustPolicy(BaseModel):
    verification_policy: Literal["passed_only"] = "passed_only"
    review_policy: ExamPaperReviewPolicy = "approved_only"
    private_question_policy: Literal["explicit_owner_selection_only"] = (
        "explicit_owner_selection_only"
    )
    auto_authoring_allowed: Literal[False] = False
    preserves_source_and_rights: Literal[True] = True


class PaperBlueprintDraft(BaseModel):
    status: Literal["draft"] = "draft"
    editable: Literal[True] = True
    confirmed: Literal[False] = False
    saved: Literal[False] = False
    source_brief: str
    title: str = Field(min_length=2, max_length=200)
    grade_scope: str = Field(min_length=2, max_length=40)
    teaching_usage: str = Field(min_length=2, max_length=80)
    duration_minutes: int = Field(ge=10, le=300)
    target_score: float = Field(ge=5, le=300)
    difficulty_profile: ExamPaperDifficultyProfile
    knowledge_points: list[str] = Field(min_length=1, max_length=20)
    sections: list[PaperBlueprintSection] = Field(min_length=1, max_length=8)
    assumptions: list[str] = Field(default_factory=list, max_length=20)
    trust_policy: PaperBlueprintTrustPolicy = Field(default_factory=PaperBlueprintTrustPolicy)
    side_effects: list[str] = Field(default_factory=list, max_length=0)

    @model_validator(mode="after")
    def validate_blueprint_totals(self) -> "PaperBlueprintDraft":
        section_ids = [item.section_id for item in self.sections]
        if len(section_ids) != len(set(section_ids)):
            raise ValueError("蓝图分区编号不能重复")
        if sum(item.question_count for item in self.sections) < 1:
            raise ValueError("蓝图至少需要一道题")
        if sum(item.question_count for item in self.sections) > 50:
            raise ValueError("蓝图最多规划 50 道题")
        if abs(sum(item.target_score for item in self.sections) - self.target_score) > 1e-6:
            raise ValueError("各分区分值合计必须等于目标总分")
        return self
