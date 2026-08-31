from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.modules.lesson_plans import (
    LessonBlueprintCurriculumCandidate,
    LessonBlueprintDraft,
    LessonBlueprintPhase,
    LessonSourceOptionsCommand,
    LessonSourceSelection,
    LessonSourceSelectionCommand,
    LessonSourceSelectionError,
)


def _blueprint(*, question_count: int = 1, title: str = "高二椭圆新授课教案") -> LessonBlueprintDraft:
    candidate = LessonBlueprintCurriculumCandidate(
        node_id="kp-ellipse",
        node_type="knowledge_point",
        name="椭圆的定义与标准方程",
        volume="选择性必修第一册",
        chapter="圆锥曲线的方程",
        section="椭圆",
        description="从轨迹定义建立椭圆标准方程。",
        competencies=["数学抽象"],
        common_errors=["忽略定义条件"],
        catalog_status="sealed_baseline",
        reviewed_by="curriculum_reviewer",
        match_score=0.96,
    )
    return LessonBlueprintDraft(
        source_brief="为高二准备椭圆新授课，45 分钟",
        title=title,
        grade_scope="高二",
        lesson_type="new_lesson",
        lesson_format="新授课",
        duration_minutes=45,
        student_profile="基础中等，需要适度支架",
        focus="建立椭圆定义与标准方程的联系",
        question_count=question_count,
        curriculum_query="椭圆",
        selected_curriculum_node_id=candidate.node_id,
        curriculum_candidates=[candidate],
        objectives=["理解椭圆定义"],
        key_points=["椭圆定义"],
        difficulties=["几何条件代数化"],
        phases=[
            LessonBlueprintPhase(phase_id="a", title="诊断", minutes=5, purpose="诊断起点"),
            LessonBlueprintPhase(phase_id="b", title="建构", minutes=30, purpose="建构概念"),
            LessonBlueprintPhase(phase_id="c", title="总结", minutes=10, purpose="总结评价"),
        ],
        required_blocks=[
            "objectives",
            "key_points",
            "difficulties",
            "teaching_flow",
            "homework",
            "board_plan",
            "teacher_notes",
        ],
    )


class _Curriculum:
    def get_node(self, node_id: str):
        if node_id != "kp-ellipse":
            raise KeyError(node_id)
        return SimpleNamespace(status="sealed_baseline", reviewed_by="curriculum_reviewer")


class _QuestionBank:
    def __init__(self) -> None:
        self.summary = SimpleNamespace(
            question_id="public-1",
            status="published",
            review_status="approved",
            visibility="public",
            question_type="single_choice",
            stem_plain="已知椭圆的标准方程，则其焦点坐标为（ ）",
            difficulty=3,
            chapter="圆锥曲线的方程",
            knowledge_point_ids=["椭圆"],
            verification_status="passed",
            source_document="省级公开题库",
            license_status="licensed_for_teaching",
            publication_blockers=[],
            library_state="active",
        )

    def search(self, **kwargs):
        assert kwargs["usage_owner_id"] == "teacher-a"
        return SimpleNamespace(items=[self.summary], total=1, page_size=100)

    def get_question(self, question_id: str):
        assert question_id == "public-1"
        return SimpleNamespace(
            revision_count=4,
            raw={"options": [{"key": "A", "plain_text": "(1,0)"}]},
        )


class _PersonalQuestions:
    def list_questions(self, **kwargs):
        assert kwargs["owner_id"] == "teacher-a"
        return SimpleNamespace(items=[])

    def get_question(self, question_id: str, *, owner_id: str):
        raise KeyError((question_id, owner_id))


class _PrivateLibrary:
    def __init__(self) -> None:
        self.item = SimpleNamespace(
            library_item_id="resource-1",
            title="椭圆备课札记",
            file_kind="docx",
            version=3,
            rights_basis="original",
            text_review_status="confirmed",
            corrected_char_count=42,
            lifecycle_state="active",
            corrected_text="教师已校对的椭圆定义课堂引入与追问设计。",
            rights_statement="本人原创，仅用于本人教学。",
        )

    def list(self, **kwargs):
        assert kwargs["owner_id"] == "teacher-a"
        return SimpleNamespace(items=[self.item])

    def get(self, item_id: str, *, owner_id: str):
        if item_id != "resource-1" or owner_id != "teacher-a":
            raise KeyError(item_id)
        return self.item


def _selection() -> LessonSourceSelection:
    return LessonSourceSelection(
        curriculum_catalog=_Curriculum(),
        question_bank=_QuestionBank(),
        personal_question_library=_PersonalQuestions(),
        private_library=_PrivateLibrary(),
    )


def test_confirmation_lists_only_gated_metadata_without_private_content_or_side_effects() -> None:
    options = _selection().options(_blueprint(), owner_id="teacher-a")

    assert options.blueprint.confirmed is True
    assert options.blueprint.saved is False
    assert options.public_questions[0].question_id == "public-1"
    assert options.public_questions[0].source_revision == 4
    assert options.private_resources[0].library_item_id == "resource-1"
    assert "content_excerpt" not in options.private_resources[0].model_dump()
    assert options.side_effects == []


def test_explicit_selection_resolves_exact_sources_and_reports_no_gap() -> None:
    options = _selection().options(_blueprint(), owner_id="teacher-a")
    draft = _selection().select(
        LessonSourceSelectionCommand(
            blueprint=options.blueprint,
            selected_public_question_ids=["public-1"],
            selected_private_resource_ids=["resource-1"],
        ),
        owner_id="teacher-a",
    )

    assert draft.selection_complete is True
    assert draft.gaps == []
    assert draft.questions[0].owner_scope == "public_catalog"
    assert draft.private_resources[0].source_version == 3
    assert "课堂引入" in draft.private_resources[0].content_excerpt
    assert draft.saved is False
    assert draft.side_effects == []


def test_selection_never_fills_missing_questions_and_blocks_cross_owner_private_ids() -> None:
    options = _selection().options(_blueprint(question_count=2), owner_id="teacher-a")
    draft = _selection().select(
        LessonSourceSelectionCommand(blueprint=options.blueprint),
        owner_id="teacher-a",
    )
    assert draft.selection_complete is False
    assert draft.questions == []
    assert draft.gaps[0].source_kind == "question"
    assert draft.gaps[0].missing_count == 2
    assert "没有临时编题" in draft.gaps[0].reason

    with pytest.raises(LessonSourceSelectionError, match="不属于当前教师"):
        _selection().select(
            LessonSourceSelectionCommand(
                blueprint=options.blueprint,
                selected_private_resource_ids=["resource-from-other-owner"],
            ),
            owner_id="teacher-a",
        )


def test_browser_cannot_submit_owner_or_trust_overrides() -> None:
    with pytest.raises(ValidationError):
        LessonSourceOptionsCommand.model_validate(
            {"blueprint": _blueprint().model_dump(), "owner_id": "teacher-b"}
        )
    options = _selection().options(_blueprint(), owner_id="teacher-a")
    with pytest.raises(ValidationError):
        LessonSourceSelectionCommand.model_validate(
            {
                "blueprint": options.blueprint.model_dump(),
                "selected_public_question_ids": ["public-1"],
                "verification_status": "passed",
            }
        )


def test_university_scope_remains_blocked_after_blueprint_planning() -> None:
    with pytest.raises(LessonSourceSelectionError, match="只支持中国普通高中数学"):
        _selection().options(
            _blueprint(title="大学数学分析专题教案"),
            owner_id="teacher-a",
        )
