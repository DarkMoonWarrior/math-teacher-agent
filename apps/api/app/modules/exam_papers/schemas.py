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


class ExamPaperHistoryRevisionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(min_length=1, max_length=160)
    section_id: str | None = Field(default=None, max_length=80)
    section_title: str = Field(min_length=1, max_length=120)
    score: float = Field(gt=0, le=50)


class ExamPaperHistoryRevisionCommand(BaseModel):
    """Owner edit intent for a new revision of an existing immutable snapshot."""

    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    title: str = Field(min_length=2, max_length=200)
    duration_minutes: int = Field(ge=10, le=300)
    instructions: str = Field(max_length=1000)
    target_total_score: float | None = Field(default=None, gt=0, le=300)
    selected_public_question_ids: list[str] = Field(default_factory=list, max_length=50)
    selected_private_question_ids: list[str] = Field(default_factory=list, max_length=50)
    items: list[ExamPaperHistoryRevisionItem] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def validate_revision(self) -> "ExamPaperHistoryRevisionCommand":
        public_ids = self.selected_public_question_ids
        private_ids = self.selected_private_question_ids
        if len(public_ids) != len(set(public_ids)):
            raise ValueError("同一道公共题只能新增一次")
        if len(private_ids) != len(set(private_ids)):
            raise ValueError("同一道私题只能新增一次")
        if set(public_ids) & set(private_ids):
            raise ValueError("同一道题不能同时作为公共题和私题新增")
        item_ids = [item.question_id for item in self.items]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("同一份试卷不能重复加入同一道题")
        if self.target_total_score is not None and abs(
            sum(item.score for item in self.items) - self.target_total_score
        ) > 1e-6:
            raise ValueError("试卷总分必须等于所有题目分值之和")
        return self


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
    # A statement-only private question is an explicit owner-stop result.  Keep
    # the status in the immutable paper snapshot so reopening history can still
    # label its solution as missing instead of inferring from display text.
    solution_status: Literal["ready", "needs_teacher_verification"] = "ready"
    solution_issue: str | None = None
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
    section_id: str | None = None
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
    specification: "PaperBidirectionalSpecification | None" = None
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


class ConfirmedPaperBlueprint(BaseModel):
    """Teacher-editable blueprint facts accepted by the controlled selection seam."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=2, max_length=200)
    grade_scope: str = Field(min_length=2, max_length=40)
    teaching_usage: str = Field(min_length=2, max_length=80)
    duration_minutes: int = Field(ge=10, le=300)
    target_score: float = Field(ge=5, le=300)
    difficulty_profile: ExamPaperDifficultyProfile
    knowledge_points: list[str] = Field(min_length=1, max_length=20)
    sections: list[PaperBlueprintSection] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def validate_blueprint_totals(self) -> "ConfirmedPaperBlueprint":
        section_ids = [item.section_id for item in self.sections]
        if len(section_ids) != len(set(section_ids)):
            raise ValueError("蓝图分区编号不能重复")
        question_count = sum(item.question_count for item in self.sections)
        if not 1 <= question_count <= 50:
            raise ValueError("确认蓝图的题量必须介于 1 至 50 道")
        for section in self.sections:
            if section.question_count == 0 and section.target_score != 0:
                raise ValueError("零题量分区的分值必须为 0")
            if section.question_count > 0 and not (
                section.question_count * 0.5
                <= section.target_score
                <= section.question_count * 50
            ):
                raise ValueError("每个分区的单题分值必须介于 0.5 至 50 分")
        if abs(sum(item.target_score for item in self.sections) - self.target_score) > 1e-6:
            raise ValueError("各分区分值合计必须等于目标总分")
        return self


class PaperBlueprintSelectionCommand(BaseModel):
    """Browser-owned facts only; identity and trust conclusions stay server-owned."""

    model_config = ConfigDict(extra="forbid")

    blueprint: ConfirmedPaperBlueprint
    selected_public_question_ids: list[str] = Field(default_factory=list, max_length=50)
    selected_private_question_ids: list[str] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def validate_explicit_selection(self) -> "PaperBlueprintSelectionCommand":
        if len(self.selected_public_question_ids) != len(set(self.selected_public_question_ids)):
            raise ValueError("同一道公共题只能选择一次")
        if len(self.selected_private_question_ids) != len(set(self.selected_private_question_ids)):
            raise ValueError("同一道私题只能选择一次")
        if set(self.selected_public_question_ids) & set(self.selected_private_question_ids):
            raise ValueError("同一道题不能同时作为公共题和私题选择")
        return self


class PaperSelectionOption(BaseModel):
    key: str
    text: str


class PaperPublicQuestionCandidate(BaseModel):
    question_id: str
    question_type: str
    stem_plain: str
    options: list[PaperSelectionOption] = Field(default_factory=list)
    difficulty: int = Field(ge=1, le=5)
    chapter: str | None = None
    knowledge_points: list[str] = Field(default_factory=list)
    source_document: str


class PaperPublicQuestionCandidateList(BaseModel):
    items: list[PaperPublicQuestionCandidate] = Field(default_factory=list, max_length=100)
    total: int = Field(ge=0)
    trust_statement: Literal[
        "仅展示通过公共可见性、权利、数学验证、教师审核和在架门禁的题目"
    ] = "仅展示通过公共可见性、权利、数学验证、教师审核和在架门禁的题目"
    side_effects: list[str] = Field(default_factory=list, max_length=0)


class PaperSelectionItem(BaseModel):
    section_id: str
    section_title: str
    position: int = Field(ge=1)
    question_id: str
    source_kind: Literal["public_question_bank", "personal_question_library"]
    question_type: str
    stem_plain: str
    options: list[PaperSelectionOption] = Field(default_factory=list)
    score: float = Field(gt=0, le=50)
    difficulty: int = Field(ge=1, le=5)
    chapter: str | None = None
    knowledge_points: list[str] = Field(default_factory=list)
    source_document: str
    source_page_start: int | None = None
    source_page_end: int | None = None
    license_status: str
    revision_count: int = Field(ge=0)
    verification_status: str
    review_status: str
    visibility: str
    owner_scope: Literal["public_catalog", "current_owner_only"]
    solution_status: Literal["ready", "needs_teacher_verification"] = "ready"
    solution_issue: str | None = None
    source_preserved: Literal[True] = True
    copied: Literal[False] = False
    selection_reason: str


class PaperSelectionGap(BaseModel):
    section_id: str
    section_title: str
    question_type: PaperBlueprintQuestionType
    required_count: int = Field(ge=1)
    selected_count: int = Field(ge=0)
    missing_count: int = Field(ge=1)
    missing_score: float = Field(gt=0)
    reason: str
    suggestions: list[str] = Field(min_length=1, max_length=5)


class PaperSimilarityExclusion(BaseModel):
    question_id: str
    matched_question_id: str
    relation: Literal["exact_duplicate", "variant"]
    confidence: float = Field(ge=0, le=1)
    reason: str


class PaperSectionCoverage(BaseModel):
    section_id: str
    section_title: str
    target_question_count: int = Field(ge=0, le=30)
    actual_question_count: int = Field(ge=0, le=30)
    target_score: float = Field(ge=0, le=300)
    actual_score: float = Field(ge=0, le=300)
    status: Literal["met", "short"]


class PaperKnowledgeCoverage(BaseModel):
    knowledge_point: str
    actual_question_count: int = Field(ge=0, le=50)
    actual_score: float = Field(ge=0, le=300)
    status: Literal["covered", "missing"]


class PaperDifficultyBand(BaseModel):
    difficulty: int = Field(ge=1, le=5)
    target_question_count: int = Field(ge=0, le=50)
    actual_question_count: int = Field(ge=0, le=50)
    actual_score: float = Field(ge=0, le=300)


class PaperBlueprintCoverageAudit(BaseModel):
    status: Literal["matched", "needs_adjustment"]
    coverage_complete: bool
    difficulty_status: Literal["matched", "deviated", "insufficient_supply"]
    target_average_difficulty: float = Field(ge=1, le=5)
    actual_average_difficulty: float | None = Field(default=None, ge=1, le=5)
    average_difficulty_gap: float | None = Field(default=None, ge=0, le=4)
    sections: list[PaperSectionCoverage] = Field(default_factory=list, max_length=8)
    knowledge_points: list[PaperKnowledgeCoverage] = Field(default_factory=list, max_length=20)
    difficulty_bands: list[PaperDifficultyBand] = Field(min_length=5, max_length=5)
    side_effects: list[str] = Field(default_factory=list, max_length=0)


class PaperBlueprintSelectionDraft(BaseModel):
    status: Literal["selection_draft"] = "selection_draft"
    blueprint_confirmed: Literal[True] = True
    editable: Literal[True] = True
    saved: Literal[False] = False
    selection_complete: bool
    blueprint: ConfirmedPaperBlueprint
    target_question_count: int = Field(ge=1, le=50)
    actual_question_count: int = Field(ge=0, le=50)
    target_score: float
    actual_score: float
    items: list[PaperSelectionItem] = Field(default_factory=list, max_length=50)
    gaps: list[PaperSelectionGap] = Field(default_factory=list, max_length=8)
    similarity_exclusions: list[PaperSimilarityExclusion] = Field(default_factory=list)
    coverage_audit: PaperBlueprintCoverageAudit
    unselected_public_question_ids: list[str] = Field(default_factory=list)
    unselected_private_question_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    trust_policy: PaperBlueprintTrustPolicy = Field(default_factory=PaperBlueprintTrustPolicy)
    auto_authoring_used: Literal[False] = False
    side_effects: list[str] = Field(default_factory=list, max_length=0)


class PaperDraftItemEdit(BaseModel):
    """Teacher-owned paper layout facts; trust and source facts are never accepted."""

    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(min_length=1, max_length=160)
    position: int = Field(ge=1, le=50)
    section_id: str = Field(min_length=1, max_length=80)
    score: float = Field(gt=0, le=50)


class PaperEditableDraftCommand(BaseModel):
    """Rebuilds the gated selection before applying a complete editable layout."""

    model_config = ConfigDict(extra="forbid")

    selection_request: PaperBlueprintSelectionCommand
    edits: list[PaperDraftItemEdit] = Field(default_factory=list, max_length=50)


class PaperDraftChange(BaseModel):
    question_id: str
    kind: Literal["position", "section", "score"]
    before: str
    after: str
    description: str


class PaperSpecificationForwardRow(BaseModel):
    position: int = Field(ge=1, le=50)
    question_id: str
    section_title: str
    question_type: str
    chapter: str
    knowledge_points: list[str] = Field(default_factory=list)
    difficulty: int = Field(ge=1, le=5)
    score: float = Field(gt=0, le=50)
    verification_status: str
    review_status: str
    source_kind: Literal["public_question_bank", "personal_question_library"]


class PaperSpecificationReverseRow(BaseModel):
    dimension: Literal["section", "question_type", "knowledge_point", "difficulty"]
    label: str
    positions: list[int] = Field(default_factory=list, max_length=50)
    question_ids: list[str] = Field(default_factory=list, max_length=50)
    question_count: int = Field(ge=1, le=50)
    score: float = Field(gt=0, le=300)


class PaperBidirectionalSpecification(BaseModel):
    question_to_dimensions: list[PaperSpecificationForwardRow] = Field(
        default_factory=list, max_length=50
    )
    dimension_to_questions: list[PaperSpecificationReverseRow] = Field(
        default_factory=list, max_length=100
    )


class PaperEditableDraft(BaseModel):
    status: Literal["editable_paper_draft"] = "editable_paper_draft"
    editable: Literal[True] = True
    saved: Literal[False] = False
    version_created: Literal[False] = False
    export_ready: Literal[False] = False
    draft_fingerprint: str = Field(min_length=64, max_length=64)
    selection_complete: bool
    draft_consistent: bool
    score_status: Literal["matched", "mismatch"]
    blueprint: ConfirmedPaperBlueprint
    target_question_count: int = Field(ge=1, le=50)
    actual_question_count: int = Field(ge=0, le=50)
    target_score: float = Field(ge=5, le=300)
    actual_score: float = Field(ge=0, le=300)
    items: list[PaperSelectionItem] = Field(default_factory=list, max_length=50)
    gaps: list[PaperSelectionGap] = Field(default_factory=list, max_length=8)
    coverage_audit: PaperBlueprintCoverageAudit
    change_log: list[PaperDraftChange] = Field(default_factory=list, max_length=150)
    specification: PaperBidirectionalSpecification
    warnings: list[str] = Field(default_factory=list)
    trust_policy: PaperBlueprintTrustPolicy = Field(default_factory=PaperBlueprintTrustPolicy)
    auto_authoring_used: Literal[False] = False
    side_effects: list[str] = Field(default_factory=list, max_length=0)


class PaperVersionSaveCommand(BaseModel):
    """Teacher save intent; identity, trust facts and version numbers stay server-owned."""

    model_config = ConfigDict(extra="forbid")

    draft_command: PaperEditableDraftCommand
    expected_draft_fingerprint: str = Field(min_length=64, max_length=64)
    instructions: str = Field(
        default="答题前请填写姓名和班级；所有解答须写出必要过程。",
        max_length=1000,
    )


class PaperSavedExportOption(BaseModel):
    edition: ExamPaperEdition
    format: ExamPaperExportFormat
    label: str


class PaperSavedVersion(BaseModel):
    status: Literal["saved_paper_version"] = "saved_paper_version"
    saved: Literal[True] = True
    version_created: Literal[True] = True
    export_ready: Literal[True] = True
    exam_paper_id: str
    version: int = Field(ge=1)
    title: str
    question_count: int = Field(ge=1, le=50)
    total_score: float = Field(gt=0, le=300)
    draft_fingerprint: str = Field(min_length=64, max_length=64)
    specification: PaperBidirectionalSpecification
    available_exports: list[PaperSavedExportOption] = Field(min_length=6, max_length=6)
    saved_at: str
    side_effects: list[Literal["created_exam_paper_version"]] = Field(
        default_factory=lambda: ["created_exam_paper_version"],
        min_length=1,
        max_length=1,
    )
