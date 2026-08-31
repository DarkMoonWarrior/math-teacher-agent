from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


LessonType = Literal["new_lesson", "review", "exercise"]
LessonPlanBlock = Literal[
    "objectives",
    "key_points",
    "difficulties",
    "teaching_flow",
    "homework",
    "board_plan",
    "teacher_notes",
]
LessonDraftBlock = Literal[
    "objectives",
    "key_points",
    "difficulties",
    "teaching_flow",
    "questions",
    "assessments",
    "homework",
    "board_plan",
    "teacher_notes",
]


class LessonBlueprintBrief(BaseModel):
    """Teacher-authored planning facts only; identity and trust facts stay server-owned."""

    model_config = ConfigDict(extra="forbid")

    brief: str = Field(min_length=5, max_length=4000)


class LessonBlueprintCurriculumCandidate(BaseModel):
    node_id: str = Field(min_length=1, max_length=160)
    node_type: Literal["section", "knowledge_point"]
    name: str = Field(min_length=1, max_length=160)
    volume: str = Field(min_length=1, max_length=80)
    chapter: str | None = Field(default=None, max_length=160)
    section: str | None = Field(default=None, max_length=160)
    description: str = Field(default="", max_length=1000)
    competencies: list[str] = Field(default_factory=list, max_length=12)
    common_errors: list[str] = Field(default_factory=list, max_length=12)
    catalog_status: str = Field(min_length=1, max_length=80)
    reviewed_by: str = Field(min_length=1, max_length=160)
    match_score: float = Field(ge=0, le=1)


class LessonBlueprintPhase(BaseModel):
    phase_id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=120)
    minutes: int = Field(ge=1, le=120)
    purpose: str = Field(min_length=1, max_length=500)


class LessonBlueprintTrustPolicy(BaseModel):
    curriculum_source: Literal["sealed_pep_a_baseline"] = "sealed_pep_a_baseline"
    question_policy: Literal["not_selected_during_planning"] = (
        "not_selected_during_planning"
    )
    private_resource_policy: Literal["explicit_owner_selection_only"] = (
        "explicit_owner_selection_only"
    )
    ai_content_status: Literal["draft_requires_teacher_review"] = (
        "draft_requires_teacher_review"
    )
    auto_save_allowed: Literal[False] = False
    preserves_source_traceability: Literal[True] = True


class LessonBlueprintDraft(BaseModel):
    """Editable, side-effect-free lesson requirements before retrieval or generation."""

    status: Literal["lesson_blueprint_draft"] = "lesson_blueprint_draft"
    editable: Literal[True] = True
    confirmed: Literal[False] = False
    saved: Literal[False] = False
    source_brief: str
    title: str = Field(min_length=2, max_length=200)
    grade_scope: str = Field(min_length=2, max_length=40)
    lesson_type: LessonType
    lesson_format: str = Field(min_length=2, max_length=80)
    duration_minutes: int = Field(ge=20, le=120)
    student_profile: str = Field(min_length=2, max_length=500)
    focus: str = Field(min_length=2, max_length=500)
    question_count: int = Field(ge=0, le=8)
    curriculum_query: str = Field(min_length=1, max_length=160)
    selected_curriculum_node_id: str | None = Field(default=None, max_length=160)
    curriculum_candidates: list[LessonBlueprintCurriculumCandidate] = Field(
        default_factory=list,
        max_length=5,
    )
    objectives: list[str] = Field(min_length=1, max_length=8)
    key_points: list[str] = Field(min_length=1, max_length=6)
    difficulties: list[str] = Field(min_length=1, max_length=6)
    phases: list[LessonBlueprintPhase] = Field(min_length=3, max_length=8)
    required_blocks: list[LessonPlanBlock] = Field(min_length=7, max_length=7)
    assumptions: list[str] = Field(default_factory=list, max_length=20)
    trust_policy: LessonBlueprintTrustPolicy = Field(
        default_factory=LessonBlueprintTrustPolicy
    )
    side_effects: list[str] = Field(default_factory=list, max_length=0)

    @model_validator(mode="after")
    def validate_blueprint(self) -> "LessonBlueprintDraft":
        if sum(phase.minutes for phase in self.phases) != self.duration_minutes:
            raise ValueError("课堂阶段分钟数之和必须等于课时长度")
        candidate_ids = [item.node_id for item in self.curriculum_candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("教材候选节点不能重复")
        if (
            self.selected_curriculum_node_id is not None
            and self.selected_curriculum_node_id not in candidate_ids
        ):
            raise ValueError("首选教材节点必须来自当前候选列表")
        if len(self.required_blocks) != len(set(self.required_blocks)):
            raise ValueError("教案内容块不能重复")
        return self


class ConfirmedLessonBlueprint(LessonBlueprintDraft):
    """Teacher-confirmed blueprint used by later read-only M10 interfaces."""

    status: Literal["lesson_blueprint_confirmed"] = "lesson_blueprint_confirmed"
    confirmed: Literal[True] = True


class LessonSourceOptionsCommand(BaseModel):
    """Explicit confirmation request; identity and trust overrides are forbidden."""

    model_config = ConfigDict(extra="forbid")

    blueprint: LessonBlueprintDraft


class LessonSourceQuestionOption(BaseModel):
    key: str = Field(min_length=1, max_length=12)
    text: str = Field(default="", max_length=4000)


class LessonSourceQuestionCandidate(BaseModel):
    question_id: str = Field(min_length=1, max_length=160)
    source_kind: Literal["public_question_bank", "personal_question_library"]
    name: str = Field(min_length=1, max_length=200)
    question_type: str = Field(min_length=1, max_length=80)
    stem_plain: str = Field(min_length=1, max_length=20000)
    options: list[LessonSourceQuestionOption] = Field(default_factory=list, max_length=20)
    difficulty: int = Field(ge=1, le=5)
    chapter: str | None = Field(default=None, max_length=300)
    knowledge_points: list[str] = Field(default_factory=list, max_length=30)
    source_document: str = Field(min_length=1, max_length=500)
    source_revision: int = Field(ge=0)
    rights_basis: str = Field(min_length=1, max_length=120)
    verification_status: str = Field(min_length=1, max_length=160)
    review_status: str = Field(min_length=1, max_length=160)
    owner_scope: Literal["public_catalog", "current_owner_only"]


class LessonSourceResourceCandidate(BaseModel):
    library_item_id: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=300)
    file_kind: Literal["pdf", "docx", "image"]
    source_version: int = Field(ge=1)
    rights_basis: Literal["original", "licensed", "private_teaching_only"]
    text_review_status: Literal["confirmed"] = "confirmed"
    corrected_char_count: int = Field(ge=1)
    owner_scope: Literal["current_owner_only"] = "current_owner_only"


class LessonSourceOptions(BaseModel):
    status: Literal["lesson_source_options"] = "lesson_source_options"
    blueprint: ConfirmedLessonBlueprint
    public_questions: list[LessonSourceQuestionCandidate] = Field(default_factory=list)
    private_questions: list[LessonSourceQuestionCandidate] = Field(default_factory=list)
    private_resources: list[LessonSourceResourceCandidate] = Field(default_factory=list)
    trust_statement: str = (
        "公共题已通过公开、在架、权利、教师审核、数学验证与高中范围门禁；"
        "私题和私人资料仅展示当前教师可明确选择的内容。"
    )
    side_effects: list[str] = Field(default_factory=list, max_length=0)


class LessonSourceSelectionCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    blueprint: ConfirmedLessonBlueprint
    selected_public_question_ids: list[str] = Field(default_factory=list, max_length=20)
    selected_private_question_ids: list[str] = Field(default_factory=list, max_length=20)
    selected_private_resource_ids: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_ids(self) -> "LessonSourceSelectionCommand":
        groups = (
            self.selected_public_question_ids,
            self.selected_private_question_ids,
            self.selected_private_resource_ids,
        )
        if any(len(values) != len(set(values)) for values in groups):
            raise ValueError("来源 ID 不能重复")
        if set(self.selected_public_question_ids) & set(self.selected_private_question_ids):
            raise ValueError("同一题目不能同时声明为公共题和私题")
        return self


class LessonSelectedPrivateResource(LessonSourceResourceCandidate):
    content_excerpt: str = Field(min_length=1, max_length=480)
    rights_statement: str = Field(min_length=1, max_length=2000)


class LessonSourceGap(BaseModel):
    source_kind: Literal["curriculum", "question"]
    required_count: int = Field(ge=1)
    selected_count: int = Field(ge=0)
    missing_count: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=500)


class LessonSourceDraft(BaseModel):
    status: Literal["lesson_source_draft"] = "lesson_source_draft"
    editable: Literal[True] = True
    saved: Literal[False] = False
    selection_complete: bool
    blueprint: ConfirmedLessonBlueprint
    curriculum: LessonBlueprintCurriculumCandidate | None = None
    questions: list[LessonSourceQuestionCandidate] = Field(default_factory=list)
    private_resources: list[LessonSelectedPrivateResource] = Field(default_factory=list)
    gaps: list[LessonSourceGap] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list, max_length=20)
    trust_policy: dict[str, str | bool] = Field(
        default_factory=lambda: {
            "public_questions": "passed_approved_active_public_rights_high_school_only",
            "private_questions": "explicit_current_owner_selection_only",
            "private_resources": "explicit_current_owner_confirmed_text_only",
            "auto_authoring_allowed": False,
            "auto_save_allowed": False,
        }
    )
    side_effects: list[str] = Field(default_factory=list, max_length=0)


class LessonDraftCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_draft: LessonSourceDraft


class LessonDraftObjective(BaseModel):
    objective_id: str = Field(pattern=r"^O\d+$")
    text: str = Field(min_length=2, max_length=500)
    observable_evidence: str = Field(min_length=2, max_length=500)


class LessonDraftAssessment(BaseModel):
    assessment_id: str = Field(pattern=r"^A\d+$")
    title: str = Field(min_length=2, max_length=160)
    method: str = Field(min_length=2, max_length=500)
    success_criteria: str = Field(min_length=2, max_length=500)
    objective_ids: list[str] = Field(min_length=1, max_length=8)


class LessonDraftTeachingPhase(BaseModel):
    phase_id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=120)
    minutes: int = Field(ge=1, le=120)
    purpose: str = Field(min_length=1, max_length=500)
    teacher_activity: str = Field(min_length=2, max_length=2000)
    student_activity: str = Field(min_length=2, max_length=2000)
    assessment: str = Field(min_length=2, max_length=1000)
    objective_ids: list[str] = Field(min_length=1, max_length=8)
    question_ids: list[str] = Field(default_factory=list, max_length=8)
    resource_ids: list[str] = Field(default_factory=list, max_length=20)


class LessonDraftQuestionUse(BaseModel):
    question_id: str = Field(min_length=1, max_length=160)
    source_kind: Literal["public_question_bank", "personal_question_library"]
    source_revision: int = Field(ge=0)
    rights_basis: str = Field(min_length=1, max_length=120)
    verification_status: str = Field(min_length=1, max_length=160)
    review_status: str = Field(min_length=1, max_length=160)
    owner_scope: Literal["public_catalog", "current_owner_only"]
    phase_id: str = Field(min_length=1, max_length=80)
    usage: str = Field(min_length=2, max_length=500)
    stem_plain: str = Field(min_length=1, max_length=20000)
    options: list[LessonSourceQuestionOption] = Field(default_factory=list, max_length=20)
    answer_value: str = Field(min_length=1, max_length=4000)
    solution_steps: list[str] = Field(min_length=1, max_length=100)
    final_answer: str = Field(min_length=1, max_length=4000)


class LessonDraftSourceRef(BaseModel):
    source_kind: Literal["curriculum", "public_question", "private_question", "private_resource"]
    source_id: str = Field(min_length=1, max_length=160)
    source_revision: str = Field(min_length=1, max_length=160)
    rights_basis: str = Field(min_length=1, max_length=160)
    verification_status: str = Field(min_length=1, max_length=160)
    owner_scope: Literal["sealed_catalog", "public_catalog", "current_owner_only"]


class LessonDraftIntegrity(BaseModel):
    required_blocks_complete: Literal[True] = True
    time_total_matches: Literal[True] = True
    objective_activity_alignment: Literal[True] = True
    objective_assessment_alignment: Literal[True] = True
    questions_complete: Literal[True] = True
    high_school_scope: Literal[True] = True
    source_traceability_complete: Literal[True] = True


class LessonDraftRewriteRecord(BaseModel):
    draft_revision: int = Field(ge=2)
    target_block: LessonDraftBlock
    instruction: str = Field(min_length=2, max_length=1000)
    provider: str = Field(min_length=1, max_length=120)
    model: str = Field(min_length=1, max_length=160)


class LessonEditableDraft(BaseModel):
    status: Literal["lesson_editable_draft"] = "lesson_editable_draft"
    content_status: Literal["draft_requires_teacher_review"] = (
        "draft_requires_teacher_review"
    )
    editable: Literal[True] = True
    saved: Literal[False] = False
    draft_revision: int = Field(default=1, ge=1)
    title: str = Field(min_length=2, max_length=200)
    source_draft: LessonSourceDraft
    objectives: list[LessonDraftObjective] = Field(min_length=1, max_length=8)
    key_points: list[str] = Field(min_length=1, max_length=6)
    difficulties: list[str] = Field(min_length=1, max_length=6)
    teaching_flow: list[LessonDraftTeachingPhase] = Field(min_length=3, max_length=8)
    questions: list[LessonDraftQuestionUse] = Field(default_factory=list, max_length=8)
    assessments: list[LessonDraftAssessment] = Field(min_length=1, max_length=8)
    homework: list[str] = Field(min_length=1, max_length=8)
    board_plan: list[str] = Field(min_length=1, max_length=8)
    teacher_notes: list[str] = Field(min_length=1, max_length=8)
    locked_blocks: list[LessonDraftBlock] = Field(default_factory=list, max_length=9)
    rewrite_history: list[LessonDraftRewriteRecord] = Field(
        default_factory=list,
        max_length=50,
    )
    source_manifest: list[LessonDraftSourceRef] = Field(min_length=1, max_length=50)
    integrity: LessonDraftIntegrity = Field(default_factory=LessonDraftIntegrity)
    generation: dict[str, str | bool] = Field(
        default_factory=lambda: {
            "provider": "structured_lesson_drafting",
            "model": "closed_loop_template_v1",
            "ai_text_status": "draft_requires_teacher_review",
            "auto_save": False,
        }
    )
    side_effects: list[str] = Field(default_factory=list, max_length=0)

    @model_validator(mode="after")
    def validate_complete_draft(self) -> "LessonEditableDraft":
        if not self.source_draft.selection_complete or self.source_draft.gaps:
            raise ValueError("完整教案只能基于没有来源缺口的来源草案")
        if sum(phase.minutes for phase in self.teaching_flow) != self.source_draft.blueprint.duration_minutes:
            raise ValueError("教学流程分钟数之和必须等于课时长度")
        objective_ids = {item.objective_id for item in self.objectives}
        if len(objective_ids) != len(self.objectives):
            raise ValueError("教学目标 ID 不能重复")
        phase_objective_ids = {
            objective_id
            for phase in self.teaching_flow
            for objective_id in phase.objective_ids
        }
        assessment_objective_ids = {
            objective_id
            for assessment in self.assessments
            for objective_id in assessment.objective_ids
        }
        if not objective_ids <= phase_objective_ids:
            raise ValueError("每个教学目标必须对应至少一个课堂活动")
        if not objective_ids <= assessment_objective_ids:
            raise ValueError("每个教学目标必须对应至少一个评价证据")
        if (phase_objective_ids | assessment_objective_ids) - objective_ids:
            raise ValueError("课堂活动或评价引用了不存在的教学目标")
        question_ids = {item.question_id for item in self.questions}
        if question_ids != {item.question_id for item in self.source_draft.questions}:
            raise ValueError("教案例题必须与已确认来源题目完全一致")
        used_question_ids = {
            question_id
            for phase in self.teaching_flow
            for question_id in phase.question_ids
        }
        if not question_ids <= used_question_ids:
            raise ValueError("每道已选题目必须进入至少一个课堂阶段")
        if len(self.locked_blocks) != len(set(self.locked_blocks)):
            raise ValueError("锁定内容块不能重复")
        return self
class LessonBlockRewriteCommand(BaseModel):
    """Teacher-editable facts only; owner and trust selectors stay server-owned."""

    model_config = ConfigDict(extra="forbid")

    draft: LessonEditableDraft
    target_block: LessonDraftBlock
    instruction: str = Field(min_length=2, max_length=1000)
    expected_draft_revision: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_revision(self) -> "LessonBlockRewriteCommand":
        if self.expected_draft_revision != self.draft.draft_revision:
            raise ValueError("页面草稿 revision 与改写请求不一致")
        return self


class LessonVersionSaveCommand(BaseModel):
    """Explicit teacher save; identity, trust and lifecycle remain server-owned."""

    model_config = ConfigDict(extra="forbid")

    draft: LessonEditableDraft
    lesson_plan_id: str | None = Field(default=None, max_length=80)
    confirmed: Literal[True]


class LessonSavedExportOption(BaseModel):
    format: Literal["docx", "pdf"]
    label: str = Field(min_length=1, max_length=80)


def lesson_saved_export_options() -> list[LessonSavedExportOption]:
    return [
        LessonSavedExportOption(format="docx", label="教师教案 · DOCX"),
        LessonSavedExportOption(format="pdf", label="教师教案 · PDF"),
    ]


class LessonSavedVersion(BaseModel):
    status: Literal["saved_lesson_version"] = "saved_lesson_version"
    saved: Literal[True] = True
    lesson_plan_id: str
    version: int = Field(ge=1)
    title: str
    content_status: Literal["draft_requires_teacher_review"] = (
        "draft_requires_teacher_review"
    )
    owner_scope: Literal["current_owner_only"] = "current_owner_only"
    lifecycle_state: Literal["active", "trashed"] = "active"
    draft_fingerprint: str = Field(min_length=64, max_length=64)
    draft: LessonEditableDraft
    created_at: str
    saved_at: str
    available_exports: list[LessonSavedExportOption] = Field(
        default_factory=lesson_saved_export_options,
        min_length=2,
        max_length=2,
    )
    side_effects: list[Literal["created_lesson_plan_version"]] = Field(
        default_factory=lambda: ["created_lesson_plan_version"],
        min_length=1,
        max_length=1,
    )


class LessonVersionHistoryItem(BaseModel):
    lesson_plan_id: str
    title: str
    version: int = Field(ge=1)
    duration_minutes: int = Field(ge=20, le=120)
    lesson_type: LessonType
    updated_at: str
    lifecycle_state: Literal["active", "trashed"]
    trashed_at: str | None = None


class LessonVersionHistoryList(BaseModel):
    items: list[LessonVersionHistoryItem]
    total: int


class LessonVersionLifecycleCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["trash", "restore"]


class LessonPlanGenerationRequest(BaseModel):
    curriculum_node_id: str
    lesson_type: LessonType = "new_lesson"
    duration_minutes: int = Field(default=45, ge=20, le=120)
    student_profile: str = Field(
        default="基础中等，能够完成教材基础练习，抽象概括能力需要支架",
        min_length=2,
        max_length=500,
    )
    focus: str = Field(default="", max_length=500)
    question_count: int = Field(default=3, ge=0, le=8)
    teacher_id: str = Field(default="owner_teacher", min_length=1, max_length=120)


class LessonCurriculumContext(BaseModel):
    node_id: str
    volume: str
    chapter: str
    section: str
    topic: str
    description: str
    competencies: list[str]
    common_errors: list[str]
    knowledge_points: list[str]
    baseline_id: str = "legacy-unversioned"
    standard_title: str = "普通高中数学课程标准"
    textbook_edition: str = "人教 A 版"


class TeachingPhase(BaseModel):
    phase: str
    minutes: int = Field(ge=1, le=120)
    teacher_activity: str
    student_activity: str
    assessment: str


class RecommendedQuestion(BaseModel):
    question_id: str
    stem: str
    difficulty: int
    usage: str
    verification_status: str


class GeneratedLessonPlanContent(BaseModel):
    title: str
    objectives: list[str] = Field(min_length=1, max_length=8)
    key_points: list[str] = Field(min_length=1, max_length=6)
    difficulties: list[str] = Field(min_length=1, max_length=6)
    teaching_flow: list[TeachingPhase] = Field(min_length=2, max_length=10)
    homework: list[str] = Field(min_length=1, max_length=8)
    board_plan: list[str] = Field(min_length=1, max_length=8)
    teacher_notes: list[str] = Field(default_factory=list, max_length=8)


class LessonPlanContent(GeneratedLessonPlanContent):
    recommended_questions: list[RecommendedQuestion] = Field(default_factory=list)


class LessonPlanGenerationMeta(BaseModel):
    provider: str
    model: str
    mode: str
    retrieved_question_ids: list[str]
    warnings: list[str] = Field(default_factory=list)


class LessonPlanView(BaseModel):
    lesson_plan_id: str
    status: str
    version: int
    created_at: str
    updated_at: str
    request: LessonPlanGenerationRequest
    curriculum: LessonCurriculumContext
    content: LessonPlanContent
    generation: LessonPlanGenerationMeta
    locked_blocks: list[LessonPlanBlock] = Field(default_factory=list, max_length=7)
    lifecycle_state: Literal["active", "trashed"] = "active"
    trashed_at: str | None = None


class LessonPlanSummary(BaseModel):
    lesson_plan_id: str
    title: str
    status: str
    version: int
    curriculum_node_id: str
    topic: str
    provider: str
    updated_at: str
    lifecycle_state: Literal["active", "trashed"] = "active"
    trashed_at: str | None = None


class LessonPlanLifecycleCommand(BaseModel):
    action: Literal["trash", "restore"]
    actor_id: str = Field(default="owner_teacher", min_length=1, max_length=120)
    reason: str = Field(default="用户删除", max_length=2000)


class LessonPlanList(BaseModel):
    items: list[LessonPlanSummary]
    total: int


class LessonPlanUpdateCommand(BaseModel):
    content: LessonPlanContent
    editor_id: str = Field(default="owner_teacher", min_length=1, max_length=120)


class LessonPlanBlockLockCommand(BaseModel):
    locked: bool
    editor_id: str = Field(default="owner_teacher", min_length=1, max_length=120)


class LessonPlanBlockRewriteCommand(BaseModel):
    instruction: str = Field(min_length=2, max_length=500)
    content: LessonPlanContent
    teacher_id: str = Field(default="owner_teacher", min_length=1, max_length=120)


class LessonPlanBlockRewriteResult(BaseModel):
    block: LessonPlanBlock
    value: list[str] | list[TeachingPhase]
    provider: str
    model: str
    mode: str
    warnings: list[str] = Field(default_factory=list)
