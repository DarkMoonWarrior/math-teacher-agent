from __future__ import annotations

from types import SimpleNamespace
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.identity import CurrentTeacher, get_current_teacher
from app.main import app
from app.modules.lesson_plans import (
    ConfirmedLessonBlueprint,
    LessonBlueprintCurriculumCandidate,
    LessonBlueprintPhase,
    LessonBlockEditing,
    LessonBlockEditingConflict,
    LessonBlockEditingError,
    LessonBlockRewriteCommand,
    LessonDraftCommand,
    LessonDrafting,
    LessonDraftingConflict,
    LessonDraftingError,
    LessonSelectedPrivateResource,
    LessonSourceDraft,
    LessonSourceGap,
    LessonSourceQuestionCandidate,
    LessonSourceQuestionOption,
    LessonVersionLifecycleCommand,
    LessonVersionSaveCommand,
    LessonVersioning,
    LessonVersioningConflict,
    LessonSavedExporting,
    LessonSavedExportingError,
)
from app.modules.lesson_exports import SavedLessonPlanDocumentRenderer
from app.routes.lesson_plans import get_lesson_saved_exporting


def _confirmed_blueprint(*, title: str = "高二椭圆新授课教案") -> ConfirmedLessonBlueprint:
    curriculum = LessonBlueprintCurriculumCandidate(
        node_id="kp-ellipse",
        node_type="knowledge_point",
        name="椭圆的定义与标准方程",
        volume="选择性必修第一册",
        chapter="圆锥曲线的方程",
        section="椭圆",
        description="从轨迹定义建立椭圆方程。",
        competencies=["数学抽象"],
        common_errors=["忽略定义条件"],
        catalog_status="sealed_baseline",
        reviewed_by="curriculum_reviewer",
        match_score=1,
    )
    return ConfirmedLessonBlueprint(
        source_brief="为高二准备椭圆新授课，45 分钟，安排 1 道题",
        title=title,
        grade_scope="高二",
        lesson_type="new_lesson",
        lesson_format="新授课",
        duration_minutes=45,
        student_profile="基础中等，需要适度支架",
        focus="建立椭圆定义、图形与标准方程的联系",
        question_count=1,
        curriculum_query="椭圆",
        selected_curriculum_node_id=curriculum.node_id,
        curriculum_candidates=[curriculum],
        objectives=["理解椭圆的定义。", "能推导并使用椭圆标准方程。"],
        key_points=["椭圆定义与标准方程"],
        difficulties=["几何条件代数化"],
        phases=[
            LessonBlueprintPhase(phase_id="intro", title="情境与诊断", minutes=5, purpose="诊断先备知识"),
            LessonBlueprintPhase(phase_id="build", title="概念建构", minutes=20, purpose="建立定义与方程"),
            LessonBlueprintPhase(phase_id="practice", title="例题与练习", minutes=15, purpose="应用方法并反馈"),
            LessonBlueprintPhase(phase_id="summary", title="总结与作业", minutes=5, purpose="回扣目标"),
        ],
        required_blocks=[
            "objectives", "key_points", "difficulties", "teaching_flow",
            "homework", "board_plan", "teacher_notes",
        ],
    )


def _source_draft(*, revision: int = 2, complete: bool = True) -> LessonSourceDraft:
    blueprint = _confirmed_blueprint()
    question = LessonSourceQuestionCandidate(
        question_id="public-1",
        source_kind="public_question_bank",
        name="省级公开题库",
        question_type="single_choice",
        stem_plain="已知椭圆标准方程，则其焦点坐标为（ ）",
        options=[
            LessonSourceQuestionOption(key="A", text="(1,0)"),
            LessonSourceQuestionOption(key="B", text="(2,0)"),
        ],
        difficulty=3,
        chapter="圆锥曲线的方程",
        knowledge_points=["椭圆"],
        source_document="省级公开题库",
        source_revision=revision,
        rights_basis="licensed_for_teaching",
        verification_status="passed",
        review_status="approved",
        owner_scope="public_catalog",
    )
    resource = LessonSelectedPrivateResource(
        library_item_id="resource-1",
        title="椭圆课堂札记",
        file_kind="docx",
        source_version=3,
        rights_basis="original",
        corrected_char_count=200,
        content_excerpt="教师已确认的课堂引入和追问设计。",
        rights_statement="本人原创，仅用于本人教学。",
    )
    gaps = [] if complete else [
        LessonSourceGap(
            source_kind="question",
            required_count=1,
            selected_count=0,
            missing_count=1,
            reason="题目不足",
        )
    ]
    return LessonSourceDraft(
        selection_complete=complete,
        blueprint=blueprint,
        curriculum=blueprint.curriculum_candidates[0],
        questions=[question] if complete else [],
        private_resources=[resource],
        gaps=gaps,
    )


class _QuestionBank:
    def __init__(self, *, revision: int = 2, complete: bool = True) -> None:
        self.revision = revision
        self.complete = complete

    def get_question(self, question_id: str):
        assert question_id == "public-1"
        return SimpleNamespace(
            revision_count=self.revision,
            answer_value="B" if self.complete else "",
            raw={
                "solutions": [{
                    "steps_latex": ["由 a^2-b^2=c^2 求得 c=2"] if self.complete else [],
                    "final_answer": "B" if self.complete else "",
                }]
            },
        )


class _SourceSelection:
    def __init__(self, current: LessonSourceDraft, *, question_bank=None) -> None:
        self.current = current
        self.question_bank = question_bank or _QuestionBank()
        self.personal_question_library = SimpleNamespace()

    def select(self, command, *, owner_id: str):
        assert owner_id == "teacher-a"
        assert command.selected_public_question_ids == ["public-1"] or not self.current.selection_complete
        assert command.selected_private_resource_ids == ["resource-1"]
        return self.current


def test_builds_complete_traceable_unsaved_lesson_with_closed_loop_alignment() -> None:
    source = _source_draft()
    draft = LessonDrafting(source_selection=_SourceSelection(source)).build(
        LessonDraftCommand(source_draft=source),
        owner_id="teacher-a",
    )

    assert draft.status == "lesson_editable_draft"
    assert draft.content_status == "draft_requires_teacher_review"
    assert draft.saved is False
    assert draft.side_effects == []
    assert sum(item.minutes for item in draft.teaching_flow) == 45
    assert {item.objective_id for item in draft.objectives} <= {
        objective_id for phase in draft.teaching_flow for objective_id in phase.objective_ids
    }
    assert {item.objective_id for item in draft.objectives} <= {
        objective_id for assessment in draft.assessments for objective_id in assessment.objective_ids
    }
    assert draft.questions[0].answer_value == "B"
    assert draft.questions[0].solution_steps
    assert draft.questions[0].final_answer == "B"
    assert {item.source_kind for item in draft.source_manifest} == {
        "curriculum", "public_question", "private_resource",
    }
    assert draft.integrity.questions_complete is True


def test_rejects_incomplete_source_draft_instead_of_delivering_half_lesson() -> None:
    source = _source_draft(complete=False)
    with pytest.raises(LessonDraftingError, match="真实缺口"):
        LessonDrafting(source_selection=_SourceSelection(source)).build(
            LessonDraftCommand(source_draft=source),
            owner_id="teacher-a",
        )


def test_rejects_changed_question_revision_and_incomplete_solution() -> None:
    submitted = _source_draft(revision=2)
    changed = _source_draft(revision=3)
    with pytest.raises(LessonDraftingConflict, match="revision"):
        LessonDrafting(source_selection=_SourceSelection(changed)).build(
            LessonDraftCommand(source_draft=submitted),
            owner_id="teacher-a",
        )

    with pytest.raises(LessonDraftingError, match="缺少完整答案或解析"):
        LessonDrafting(
            source_selection=_SourceSelection(
                submitted,
                question_bank=_QuestionBank(complete=False),
            )
        ).build(LessonDraftCommand(source_draft=submitted), owner_id="teacher-a")


def test_university_content_and_browser_identity_override_remain_blocked() -> None:
    source = _source_draft()
    source.blueprint.title = "大学数学分析教案"
    with pytest.raises(LessonDraftingError, match="只支持中国普通高中数学"):
        LessonDrafting(source_selection=_SourceSelection(source)).build(
            LessonDraftCommand(source_draft=source),
            owner_id="teacher-a",
        )

    with pytest.raises(ValidationError):
        LessonDraftCommand.model_validate(
            {"source_draft": _source_draft().model_dump(), "owner_id": "teacher-b"}
        )


def _complete_lesson_draft():
    source = _source_draft()
    drafting = LessonDrafting(source_selection=_SourceSelection(source))
    return drafting, drafting.build(
        LessonDraftCommand(source_draft=source),
        owner_id="teacher-a",
    )


def test_block_rewrite_changes_only_target_and_preserves_local_non_target_edits() -> None:
    drafting, draft = _complete_lesson_draft()
    draft.key_points = ["教师本地修改后的重点"]
    before = draft.model_dump(mode="python")

    result = LessonBlockEditing(drafting=drafting).rewrite(
        LessonBlockRewriteCommand(
            draft=draft,
            target_block="homework",
            instruction="增加一道分层迁移任务",
            expected_draft_revision=1,
        ),
        owner_id="teacher-a",
    )

    assert result.draft_revision == 2
    assert result.homework != draft.homework
    assert result.key_points == ["教师本地修改后的重点"]
    for block in (
        "objectives", "key_points", "difficulties", "teaching_flow",
        "questions", "assessments", "board_plan", "teacher_notes",
    ):
        assert result.model_dump(mode="python")[block] == before[block]
    assert result.rewrite_history[-1].target_block == "homework"
    assert result.saved is False
    assert result.side_effects == []


def test_locked_block_cannot_be_rewritten_and_question_facts_cannot_drift() -> None:
    drafting, draft = _complete_lesson_draft()
    draft.locked_blocks = ["homework"]
    with pytest.raises(LessonBlockEditingConflict, match="已锁定"):
        LessonBlockEditing(drafting=drafting).rewrite(
            LessonBlockRewriteCommand(
                draft=draft,
                target_block="homework",
                instruction="调整作业",
                expected_draft_revision=1,
            ),
            owner_id="teacher-a",
        )

    draft.locked_blocks = []
    original = draft.questions[0].model_dump(exclude={"usage"})
    result = LessonBlockEditing(drafting=drafting).rewrite(
        LessonBlockRewriteCommand(
            draft=draft,
            target_block="questions",
            instruction="改为先独立判断再同伴互评",
            expected_draft_revision=1,
        ),
        owner_id="teacher-a",
    )
    assert result.questions[0].usage != draft.questions[0].usage
    assert result.questions[0].model_dump(exclude={"usage"}) == original

    draft.questions[0].final_answer = "A"
    with pytest.raises(LessonBlockEditingConflict, match="题面、选项、答案或解析已变化"):
        LessonBlockEditing(drafting=drafting).rewrite(
            LessonBlockRewriteCommand(
                draft=draft,
                target_block="teacher_notes",
                instruction="补充课后观察点",
                expected_draft_revision=1,
            ),
            owner_id="teacher-a",
        )


def test_rewrite_rechecks_high_school_scope_revision_and_browser_identity() -> None:
    drafting, draft = _complete_lesson_draft()
    editing = LessonBlockEditing(drafting=drafting)
    with pytest.raises(LessonBlockEditingError, match="只支持中国普通高中数学"):
        editing.rewrite(
            LessonBlockRewriteCommand(
                draft=draft,
                target_block="teacher_notes",
                instruction="补充傅里叶分析",
                expected_draft_revision=1,
            ),
            owner_id="teacher-a",
        )

    with pytest.raises(ValidationError):
        LessonBlockRewriteCommand.model_validate({
            "draft": draft.model_dump(),
            "target_block": "homework",
            "instruction": "调整作业",
            "expected_draft_revision": 2,
        })
    with pytest.raises(ValidationError):
        LessonBlockRewriteCommand.model_validate({
            "draft": draft.model_dump(),
            "target_block": "homework",
            "instruction": "调整作业",
            "expected_draft_revision": 1,
            "owner_id": "teacher-b",
        })


def test_lesson_versions_are_explicit_owner_scoped_and_immutable(tmp_path) -> None:
    drafting, draft = _complete_lesson_draft()
    versioning = LessonVersioning(database_path=tmp_path / "lessons.db", drafting=drafting)

    first = versioning.save(
        LessonVersionSaveCommand(draft=draft, confirmed=True),
        owner_id="teacher-a",
    )
    changed = draft.model_copy(deep=True)
    changed.teacher_notes = ["第二版本的教师备注"]
    second = versioning.save(
        LessonVersionSaveCommand(
            draft=changed,
            lesson_plan_id=first.lesson_plan_id,
            confirmed=True,
        ),
        owner_id="teacher-a",
    )

    assert first.version == 1
    assert second.version == 2
    assert versioning.get(first.lesson_plan_id, owner_id="teacher-a", version=1).draft.teacher_notes != changed.teacher_notes
    assert versioning.get(first.lesson_plan_id, owner_id="teacher-a").draft.teacher_notes == changed.teacher_notes
    assert versioning.list(owner_id="teacher-a").total == 1
    assert versioning.list(owner_id="teacher-b").total == 0
    with pytest.raises(KeyError):
        versioning.get(first.lesson_plan_id, owner_id="teacher-b")


def test_lesson_version_lifecycle_is_recoverable_and_trashed_plan_cannot_be_overwritten(tmp_path) -> None:
    drafting, draft = _complete_lesson_draft()
    versioning = LessonVersioning(database_path=tmp_path / "lessons.db", drafting=drafting)
    saved = versioning.save(
        LessonVersionSaveCommand(draft=draft, confirmed=True),
        owner_id="teacher-a",
    )

    trashed = versioning.change_lifecycle(
        saved.lesson_plan_id,
        LessonVersionLifecycleCommand(action="trash"),
        owner_id="teacher-a",
    )
    assert trashed.lifecycle_state == "trashed"
    assert versioning.list(owner_id="teacher-a", lifecycle_state="active").total == 0
    assert versioning.list(owner_id="teacher-a", lifecycle_state="trashed").total == 1
    with pytest.raises(LessonVersioningConflict, match="先恢复"):
        versioning.save(
            LessonVersionSaveCommand(
                draft=draft,
                lesson_plan_id=saved.lesson_plan_id,
                confirmed=True,
            ),
            owner_id="teacher-a",
        )
    restored = versioning.change_lifecycle(
        saved.lesson_plan_id,
        LessonVersionLifecycleCommand(action="restore"),
        owner_id="teacher-a",
    )
    assert restored.lifecycle_state == "active"


def test_lesson_save_revalidates_sources_and_rejects_browser_owned_facts(tmp_path) -> None:
    drafting, draft = _complete_lesson_draft()
    versioning = LessonVersioning(database_path=tmp_path / "lessons.db", drafting=drafting)
    draft.questions[0].answer_value = "A"
    with pytest.raises(LessonVersioningConflict, match="题面、选项、答案或解析已变化"):
        versioning.save(
            LessonVersionSaveCommand(draft=draft, confirmed=True),
            owner_id="teacher-a",
        )
    assert versioning.list(owner_id="teacher-a").total == 0

    with pytest.raises(ValidationError):
        LessonVersionSaveCommand.model_validate({
            "draft": draft.model_dump(),
            "confirmed": True,
            "owner_id": "teacher-b",
            "content_status": "verified",
        })


def test_saved_lesson_export_uses_exact_owner_version_with_full_question_and_sources(tmp_path) -> None:
    drafting, draft = _complete_lesson_draft()
    versioning = LessonVersioning(database_path=tmp_path / "lessons.db", drafting=drafting)
    first = versioning.save(
        LessonVersionSaveCommand(draft=draft, confirmed=True),
        owner_id="teacher-a",
    )
    changed = draft.model_copy(deep=True)
    changed.teacher_notes = ["只属于第二版本的备注"]
    versioning.save(
        LessonVersionSaveCommand(
            draft=changed,
            lesson_plan_id=first.lesson_plan_id,
            confirmed=True,
        ),
        owner_id="teacher-a",
    )
    exporting = LessonSavedExporting(
        versioning=versioning,
        renderer=SavedLessonPlanDocumentRenderer(output_root=tmp_path / "exports"),
    )

    docx = exporting.export(
        lesson_plan_id=first.lesson_plan_id,
        version=1,
        owner_id="teacher-a",
        export_format="docx",
    )
    pdf = exporting.export(
        lesson_plan_id=first.lesson_plan_id,
        version=1,
        owner_id="teacher-a",
        export_format="pdf",
    )

    with ZipFile(docx.path) as archive:
        xml = archive.read("word/document.xml").decode("utf-8")
    assert draft.title in xml
    assert draft.questions[0].stem_plain in xml
    assert draft.questions[0].final_answer in xml
    assert draft.source_manifest[0].source_id in xml
    assert "只属于第二版本的备注" not in xml
    assert docx.path.read_bytes().startswith(b"PK")
    assert pdf.path.read_bytes().startswith(b"%PDF")
    assert pdf.path.read_bytes().rstrip().endswith(b"%%EOF")
    assert "v1" in docx.download_name
    assert first.available_exports[0].format == "docx"

    with pytest.raises(LessonSavedExportingError, match="不属于当前教师"):
        exporting.export(
            lesson_plan_id=first.lesson_plan_id,
            version=1,
            owner_id="teacher-b",
            export_format="docx",
        )
    with pytest.raises(LessonSavedExportingError, match="不存在"):
        exporting.export(
            lesson_plan_id=first.lesson_plan_id,
            version=99,
            owner_id="teacher-a",
            export_format="docx",
        )


def test_saved_lesson_export_http_binds_current_teacher_and_exact_version(tmp_path) -> None:
    drafting, draft = _complete_lesson_draft()
    versioning = LessonVersioning(database_path=tmp_path / "lessons.db", drafting=drafting)
    saved = versioning.save(
        LessonVersionSaveCommand(draft=draft, confirmed=True),
        owner_id="teacher-a",
    )
    exporting = LessonSavedExporting(
        versioning=versioning,
        renderer=SavedLessonPlanDocumentRenderer(output_root=tmp_path / "exports"),
    )
    app.dependency_overrides[get_lesson_saved_exporting] = lambda: exporting
    app.dependency_overrides[get_current_teacher] = lambda: CurrentTeacher(
        teacher_id="teacher-a",
        source="authenticated_session",
    )
    client = TestClient(app)
    try:
        response = client.get(
            f"/api/v1/lesson-plans/versions/{saved.lesson_plan_id}/export",
            params={"version": 1, "format": "docx"},
        )
        assert response.status_code == 200
        assert response.content.startswith(b"PK")
        assert response.headers["content-type"].startswith(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        assert "owner_id" not in str(response.request.url)

        unknown = client.get(
            f"/api/v1/lesson-plans/versions/{saved.lesson_plan_id}/export",
            params={"version": 99, "format": "pdf"},
        )
        assert unknown.status_code == 404

        app.dependency_overrides[get_current_teacher] = lambda: CurrentTeacher(
            teacher_id="teacher-b",
            source="authenticated_session",
        )
        cross_owner = client.get(
            f"/api/v1/lesson-plans/versions/{saved.lesson_plan_id}/export",
            params={"version": 1, "format": "pdf"},
        )
        assert cross_owner.status_code == 404
    finally:
        app.dependency_overrides.clear()
