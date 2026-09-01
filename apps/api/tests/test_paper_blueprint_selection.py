from types import SimpleNamespace
from pathlib import Path
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient

from app.core.identity import CurrentTeacher, get_current_teacher
from app.main import app
from app.modules.exam_exports import ExamPaperDocumentRenderer
from app.modules.exam_papers import (
    ExamPaperStudio,
    PaperEditableDraftCommand,
    PaperEditableDrafting,
    PaperEditableDraftingError,
    PaperBlueprintSelection,
    PaperBlueprintSelectionCommand,
    PaperBlueprintSelectionError,
    PaperVersionSaveCommand,
)
from app.modules.exam_papers.versioning import (
    PaperSavedExporting,
    PaperSavedExportingError,
    PaperVersioning,
    PaperVersioningConflict,
)
from app.modules.question_bank.schemas import QuestionDetail, QuestionSearchPage, QuestionSummary
from app.modules.teacher_memory import TeacherMemory, TeacherMemoryCommand
from app.modules.teacher_memory.dependencies import get_teacher_memory
from app.routes.exam_papers import (
    get_paper_blueprint_selection,
    get_paper_editable_drafting,
    get_paper_saved_exporting,
    get_paper_versioning,
)


def public_question(
    question_id: str,
    *,
    stem: str,
    question_type: str = "single_choice",
    chapter: str = "函数",
    difficulty: int = 3,
    blockers: list[str] | None = None,
) -> QuestionSummary:
    return QuestionSummary(
        question_id=question_id,
        status="published",
        review_status="approved",
        visibility="public",
        question_type=question_type,
        stem_plain=stem,
        answer_value="A",
        volume="必修第一册",
        chapter=chapter,
        section="函数的概念与性质",
        knowledge_point_ids=["函数"],
        difficulty=difficulty,
        verification_status="passed",
        source_document="synthetic-public.json",
        source_page_start=1,
        source_page_end=1,
        license_status="public_permissive",
        publication_blockers=blockers or [],
    )


class SelectionQuestionBank:
    def __init__(self, questions: list[QuestionSummary]) -> None:
        self.questions = questions

    def search(self, **kwargs) -> QuestionSearchPage:
        page = kwargs.get("page", 1)
        page_size = kwargs.get("page_size", 100)
        start = (page - 1) * page_size
        return QuestionSearchPage(
            items=self.questions[start : start + page_size],
            total=len(self.questions),
            page=page,
            page_size=page_size,
        )

    def get_question(self, question_id: str) -> QuestionDetail:
        summary = next((item for item in self.questions if item.question_id == question_id), None)
        if summary is None:
            raise KeyError(question_id)
        return QuestionDetail.model_validate(
            {
                **summary.model_dump(mode="json"),
                "raw": {
                    "stem": {"plain_text": summary.stem_plain, "latex": None},
                    "options": [
                        {"key": "A", "plain_text": "1", "latex": None},
                        {"key": "B", "plain_text": "2", "latex": None},
                    ],
                    "solutions": [
                        {
                            "method": "按题意求解",
                            "steps_latex": ["整理条件。", "完成计算并核对答案。"],
                            "final_answer": summary.answer_value,
                        }
                    ],
                },
                "reviews": [],
                "images": [],
                "revision_count": 0,
            }
        )

    def image_path(self, question_id: str, image_id: str):
        raise KeyError((question_id, image_id))


class SelectionPersonalLibrary:
    def __init__(self, questions: dict[str, object] | None = None) -> None:
        self.questions = questions or {}

    def get_question(self, question_id: str, *, owner_id: str):
        value = self.questions.get(f"{owner_id}:{question_id}")
        if value is None:
            raise KeyError(question_id)
        return value


def private_question(
    question_id: str = "private-1",
    *,
    question_type: str = "single_choice",
    knowledge_point: str = "函数",
    stem: str = "设函数 f(x)=x²，则 f(1) 的值为（ ）",
    name: str = "我的函数题",
) -> object:
    draft = SimpleNamespace(
        solution_status="ready",
        verification=SimpleNamespace(
            status="teacher_review_required",
            math_verifier_status="unsupported",
            checks=[SimpleNamespace(status="passed")],
        ),
        stem_plain=stem,
        stem_latex=None,
        question_type=question_type,
        answer_value="A",
        curriculum=SimpleNamespace(
            volume="必修第一册",
            chapter=knowledge_point,
            section=knowledge_point,
        ),
        knowledge_points=[knowledge_point],
        estimated_difficulty=2,
        options=[
            SimpleNamespace(key="A", text="1"),
            SimpleNamespace(key="B", text="2"),
        ] if question_type in {"single_choice", "multiple_choice"} else [],
        solution_method="代入求值",
        solution_steps=["将 x=1 代入函数。", "得到 f(1)=1。"],
        final_answer="A",
        source_document="教师私有题库",
    )
    return SimpleNamespace(
        question_id=question_id,
        lifecycle_state="active",
        question=draft,
        name=name,
        selected_revision=3,
    )


def command(
    *,
    count: int = 2,
    score: float = 10,
    private_ids: list[str] | None = None,
    public_ids: list[str] | None = None,
    knowledge_points: list[str] | None = None,
):
    return PaperBlueprintSelectionCommand.model_validate(
        {
            "blueprint": {
                "title": "高二函数测验",
                "grade_scope": "高二",
                "teaching_usage": "专题测验",
                "duration_minutes": 30,
                "target_score": score,
                "difficulty_profile": "balanced",
                "knowledge_points": knowledge_points or ["函数"],
                "sections": [
                    {
                        "section_id": "section-1",
                        "title": "单项选择题",
                        "question_type": "single_choice",
                        "question_count": count,
                        "target_score": score,
                    }
                ],
            },
            "selected_public_question_ids": public_ids or [],
            "selected_private_question_ids": private_ids or [],
        }
    )


def test_selects_only_gated_public_questions_without_side_effects() -> None:
    selection = PaperBlueprintSelection(
        question_bank=SelectionQuestionBank(
            [
                public_question("q1", stem="函数 f(x)=x+1 的零点是（ ）", difficulty=2),
                public_question("q2", stem="函数 f(x)=x² 的最小值是（ ）", difficulty=4),
                public_question(
                    "blocked",
                    stem="函数 f(x)=2x 的单调性是（ ）",
                    blockers=["commercial_rights_required"],
                ),
            ]
        ),
        personal_question_library=SelectionPersonalLibrary(),
    )

    result = selection.select(command(), owner_id="teacher-a")

    assert result.selection_complete is True
    assert result.blueprint_confirmed is True
    assert result.saved is False
    assert result.actual_question_count == 2
    assert result.actual_score == result.target_score == 10
    assert {item.question_id for item in result.items} == {"q1", "q2"}
    assert all(item.owner_scope == "public_catalog" for item in result.items)
    assert all(item.source_preserved and not item.copied for item in result.items)
    assert result.coverage_audit.status == "matched"
    assert result.coverage_audit.coverage_complete is True


def test_owner_can_explicitly_select_a_saved_statement_without_solution() -> None:
    partial = private_question(question_id="private-statement-only")
    partial.question.solution_status = "needs_teacher_verification"
    partial.question.solution_issue = "解析未生成：用户在解析完成前停止任务。"
    partial.question.answer_value = "无"
    partial.question.solution_method = "无"
    partial.question.solution_steps = ["无"]
    partial.question.final_answer = "无"
    selection = PaperBlueprintSelection(
        question_bank=SelectionQuestionBank([]),
        personal_question_library=SelectionPersonalLibrary(
            {"teacher-a:private-statement-only": partial}
        ),
    )

    result = selection.select(
        command(count=1, score=5, private_ids=["private-statement-only"]),
        owner_id="teacher-a",
    )

    assert result.selection_complete is True
    assert len(result.items) == 1
    assert result.items[0].solution_status == "needs_teacher_verification"
    assert "解析未生成" in (result.items[0].solution_issue or "")


def test_statement_only_private_question_can_be_saved_and_reopened_with_no_solution(
    tmp_path: Path,
) -> None:
    partial = private_question(question_id="private-statement-only")
    partial.question.solution_status = "needs_teacher_verification"
    partial.question.solution_issue = "解析未生成：用户在解析完成前停止任务。"
    partial.question.answer_value = "无"
    partial.question.solution_method = "无"
    partial.question.solution_steps = ["无"]
    partial.question.final_answer = "无"
    bank = SelectionQuestionBank([])
    selection = PaperBlueprintSelection(
        question_bank=bank,
        personal_question_library=SelectionPersonalLibrary(
            {"teacher-a:private-statement-only": partial}
        ),
    )
    request = command(count=1, score=5, private_ids=["private-statement-only"])
    drafting = PaperEditableDrafting(selection=selection)
    draft_command = PaperEditableDraftCommand(
        selection_request=request,
        edits=[],
    )
    draft = drafting.build(draft_command, owner_id="teacher-a")
    studio = ExamPaperStudio(
        database_path=tmp_path / "statement-only-paper.sqlite3",
        asset_root=tmp_path / "statement-only-paper-assets",
        question_bank=bank,
    )
    saved = PaperVersioning(drafting=drafting, studio=studio).save(
        PaperVersionSaveCommand(
            draft_command=draft_command,
            expected_draft_fingerprint=draft.draft_fingerprint,
        ),
        owner_id="teacher-a",
    )

    reopened = studio.get_owned(saved.exam_paper_id, owner_id="teacher-a")
    snapshot = reopened.items[0].question
    assert snapshot.answer_value == "无"
    assert snapshot.solution_method == "无"
    assert snapshot.solution_steps == ["无"]
    assert snapshot.final_answer == "无"
    assert snapshot.solution_status == "needs_teacher_verification"
    assert "解析未生成" in (snapshot.solution_issue or "")


def test_all_explicit_private_questions_with_available_type_capacity_are_kept() -> None:
    questions = [
        private_question("private-choice", knowledge_point="集合", stem="设集合 A={1}，则（ ）", name="并集题"),
        private_question("private-fill-1", question_type="fill_blank", knowledge_point="数列", stem="数列首项为 1，则首项为____。", name="数列题"),
        private_question("private-fill-2", question_type="fill_blank", knowledge_point="圆锥曲线", stem="椭圆焦点在 x 轴上，则____。", name="椭圆题"),
        private_question("private-open", question_type="open_response", knowledge_point="导数", stem="已知函数 f，求其导数。", name="导数题"),
    ]
    library = SelectionPersonalLibrary({f"teacher-a:{item.question_id}": item for item in questions})
    selection = PaperBlueprintSelection(
        question_bank=SelectionQuestionBank([]),
        personal_question_library=library,
    )
    request = PaperBlueprintSelectionCommand.model_validate(
        {
            "blueprint": {
                "title": "高二函数测验",
                "grade_scope": "高二",
                "teaching_usage": "专题测验",
                "duration_minutes": 60,
                "target_score": 40,
                "difficulty_profile": "balanced",
                "knowledge_points": ["函数"],
                "sections": [
                    {"section_id": "choice", "title": "单项选择题", "question_type": "single_choice", "question_count": 1, "target_score": 5},
                    {"section_id": "fill", "title": "填空题", "question_type": "fill_blank", "question_count": 2, "target_score": 10},
                    {"section_id": "open", "title": "解答题", "question_type": "open_response", "question_count": 1, "target_score": 25},
                ],
            },
            "selected_private_question_ids": [item.question_id for item in questions],
        }
    )

    result = selection.select(request, owner_id="teacher-a")

    assert result.actual_question_count == 4
    assert {item.question_id for item in result.items} == {item.question_id for item in questions}
    assert result.unselected_private_question_ids == []


def test_teacher_can_list_and_explicitly_select_a_gated_public_question() -> None:
    selected = public_question(
        "public-set",
        stem="设集合 A={1}，则 A∪A 等于（ ）",
        chapter="集合",
    )
    selection = PaperBlueprintSelection(
        question_bank=SelectionQuestionBank([selected]),
        personal_question_library=SelectionPersonalLibrary(),
    )

    catalog = selection.list_public_candidates(owner_id="teacher-a")
    result = selection.select(
        command(count=1, score=5, public_ids=[selected.question_id]),
        owner_id="teacher-a",
    )

    assert catalog.total == 1
    assert catalog.items[0].question_id == selected.question_id
    assert result.actual_question_count == 1
    assert result.items[0].question_id == selected.question_id
    assert result.items[0].owner_scope == "public_catalog"
    assert "明确选择" in result.items[0].selection_reason
    assert result.unselected_public_question_ids == []
    assert result.coverage_audit.difficulty_status == "matched"
    assert result.coverage_audit.actual_average_difficulty == 3
    assert result.coverage_audit.sections[0].status == "met"
    assert result.coverage_audit.knowledge_points[0].status == "covered"
    assert result.auto_authoring_used is False
    assert result.side_effects == []


def test_returns_real_supply_gap_instead_of_error_or_auto_authoring() -> None:
    selection = PaperBlueprintSelection(
        question_bank=SelectionQuestionBank(
            [public_question("q1", stem="函数 f(x)=x+1 的零点是（ ）")]
        ),
        personal_question_library=SelectionPersonalLibrary(),
    )

    result = selection.select(command(count=3, score=15), owner_id="teacher-a")

    assert result.selection_complete is False
    assert result.actual_question_count == 1
    assert result.gaps[0].missing_count == 2
    assert result.gaps[0].missing_score == 10
    assert result.coverage_audit.status == "needs_adjustment"
    assert result.coverage_audit.coverage_complete is False
    assert result.coverage_audit.difficulty_status == "insufficient_supply"
    assert result.auto_authoring_used is False
    assert result.side_effects == []


def test_explicit_current_owner_private_question_is_referenced_without_copying() -> None:
    own = private_question()
    selection = PaperBlueprintSelection(
        question_bank=SelectionQuestionBank(
            [public_question("q1", stem="函数 f(x)=x+1 的零点是（ ）")]
        ),
        personal_question_library=SelectionPersonalLibrary(
            {"teacher-a:private-1": own, "teacher-b:other-private": private_question("other-private")}
        ),
    )

    result = selection.select(
        command(private_ids=["private-1"]),
        owner_id="teacher-a",
    )

    private_item = next(item for item in result.items if item.question_id == "private-1")
    assert private_item.source_kind == "personal_question_library"
    assert private_item.owner_scope == "current_owner_only"
    assert private_item.visibility == "owner_only"
    assert private_item.revision_count == 3
    assert private_item.copied is False
    with pytest.raises(PaperBlueprintSelectionError, match="不属于当前教师"):
        selection.select(command(private_ids=["other-private"]), owner_id="teacher-a")


def test_duplicate_gate_excludes_normalized_duplicate_before_selection() -> None:
    selection = PaperBlueprintSelection(
        question_bank=SelectionQuestionBank(
            [
                public_question("q1", stem="1. 函数 f(x)=x+1 的零点是（ ）"),
                public_question("q2", stem="函数 f(x)=x+1 的零点是（ ）"),
            ]
        ),
        personal_question_library=SelectionPersonalLibrary(),
    )

    result = selection.select(command(), owner_id="teacher-a")

    assert result.selection_complete is False
    assert result.actual_question_count == 1
    assert result.similarity_exclusions[0].relation == "exact_duplicate"


def test_audit_exposes_missing_knowledge_coverage_and_difficulty_deviation() -> None:
    selection = PaperBlueprintSelection(
        question_bank=SelectionQuestionBank(
            [
                public_question("q1", stem="函数 f(x)=x+1 的零点是（ ）", difficulty=5),
                public_question("q2", stem="函数 f(x)=x² 的最小值是（ ）", difficulty=5),
            ]
        ),
        personal_question_library=SelectionPersonalLibrary(),
    )

    result = selection.select(
        command(knowledge_points=["函数", "导数"]),
        owner_id="teacher-a",
    )

    assert result.selection_complete is True
    assert result.coverage_audit.status == "needs_adjustment"
    assert result.coverage_audit.coverage_complete is False
    assert result.coverage_audit.difficulty_status == "deviated"
    assert result.coverage_audit.actual_average_difficulty == 5
    coverage = {
        item.knowledge_point: item.status
        for item in result.coverage_audit.knowledge_points
    }
    assert coverage == {"函数": "covered", "导数": "missing"}
    assert [item.target_question_count for item in result.coverage_audit.difficulty_bands] == [
        0,
        1,
        1,
        0,
        0,
    ]
    assert [item.actual_question_count for item in result.coverage_audit.difficulty_bands] == [
        0,
        0,
        0,
        0,
        2,
    ]


def test_teacher_selection_can_be_saved_when_only_knowledge_or_difficulty_deviates(
    tmp_path: Path,
) -> None:
    bank = SelectionQuestionBank(
        [
            public_question("q1", stem="函数 f(x)=x+1 的零点是（ ）", difficulty=5),
            public_question("q2", stem="函数 f(x)=x² 的最小值是（ ）", difficulty=5),
        ]
    )
    selection = PaperBlueprintSelection(
        question_bank=bank,
        personal_question_library=SelectionPersonalLibrary(),
    )
    drafting = PaperEditableDrafting(selection=selection)
    draft_command = PaperEditableDraftCommand(
        selection_request=command(
            public_ids=["q1", "q2"],
            knowledge_points=["函数", "导数"],
        ),
        edits=[],
    )
    draft = drafting.build(draft_command, owner_id="teacher-a")

    assert draft.selection_complete is True
    assert draft.score_status == "matched"
    assert all(section.status == "met" for section in draft.coverage_audit.sections)
    assert draft.coverage_audit.status == "needs_adjustment"
    assert draft.coverage_audit.difficulty_status == "deviated"
    assert draft.draft_consistent is True

    versioning = PaperVersioning(
        drafting=drafting,
        studio=ExamPaperStudio(
            database_path=tmp_path / "nonblocking-analysis.sqlite3",
            asset_root=tmp_path / "nonblocking-analysis-assets",
            question_bank=bank,
        ),
    )
    saved = versioning.save(
        PaperVersionSaveCommand(
            draft_command=draft_command,
            expected_draft_fingerprint=draft.draft_fingerprint,
        ),
        owner_id="teacher-a",
    )

    assert saved.saved is True
    assert saved.question_count == 2


def test_http_binds_owner_server_side_and_rejects_forged_trust_fields() -> None:
    selection = PaperBlueprintSelection(
        question_bank=SelectionQuestionBank(
            [
                public_question("q1", stem="函数 f(x)=x+1 的零点是（ ）"),
                public_question("q2", stem="函数 f(x)=x² 的最小值是（ ）"),
            ]
        ),
        personal_question_library=SelectionPersonalLibrary(),
    )
    app.dependency_overrides[get_paper_blueprint_selection] = lambda: selection
    app.dependency_overrides[get_current_teacher] = lambda: CurrentTeacher(
        teacher_id="server-owner",
        source="authenticated_session",
    )
    try:
        client = TestClient(app)
        payload = command().model_dump(mode="json")
        response = client.post("/api/v1/exam-papers/blueprints/select", json=payload)
        forged = client.post(
            "/api/v1/exam-papers/blueprints/select",
            json={**payload, "owner_id": "another-owner", "verification_policy": "bypass"},
        )
    finally:
        app.dependency_overrides.pop(get_paper_blueprint_selection, None)
        app.dependency_overrides.pop(get_current_teacher, None)

    assert response.status_code == 200
    assert response.json()["actual_question_count"] == 2
    assert response.json()["coverage_audit"]["status"] == "matched"
    assert forged.status_code == 422


def test_builds_unsaved_editable_paper_and_bidirectional_specification() -> None:
    selection = PaperBlueprintSelection(
        question_bank=SelectionQuestionBank(
            [
                public_question("q1", stem="函数 f(x)=x+1 的零点是（ ）", difficulty=2),
                public_question("q2", stem="函数 f(x)=x² 的最小值是（ ）", difficulty=4),
            ]
        ),
        personal_question_library=SelectionPersonalLibrary(),
    )
    request = command()
    original = selection.select(request, owner_id="teacher-a")
    first, second = original.items
    drafting = PaperEditableDrafting(selection=selection)

    result = drafting.build(
        PaperEditableDraftCommand.model_validate(
            {
                "selection_request": request.model_dump(mode="json"),
                "edits": [
                    {
                        "question_id": first.question_id,
                        "position": 2,
                        "section_id": "section-1",
                        "score": 4,
                    },
                    {
                        "question_id": second.question_id,
                        "position": 1,
                        "section_id": "section-1",
                        "score": 6,
                    },
                ],
            }
        ),
        owner_id="teacher-a",
    )

    assert result.status == "editable_paper_draft"
    assert result.editable is True
    assert result.saved is False
    assert result.version_created is False
    assert result.export_ready is False
    assert result.score_status == "matched"
    assert result.actual_score == result.target_score == 10
    assert [item.question_id for item in result.items] == [
        second.question_id,
        first.question_id,
    ]
    assert len(result.change_log) == 4
    assert len(result.specification.question_to_dimensions) == 2
    reverse = {
        (row.dimension, row.label): row
        for row in result.specification.dimension_to_questions
    }
    assert reverse[("section", "单项选择题")].positions == [1, 2]
    assert reverse[("knowledge_point", "函数")].score == 10
    assert result.auto_authoring_used is False
    assert result.side_effects == []


def test_editable_paper_rejects_partial_or_forged_question_layout() -> None:
    selection = PaperBlueprintSelection(
        question_bank=SelectionQuestionBank(
            [
                public_question("q1", stem="函数 f(x)=x+1 的零点是（ ）"),
                public_question("q2", stem="函数 f(x)=x² 的最小值是（ ）"),
            ]
        ),
        personal_question_library=SelectionPersonalLibrary(),
    )
    drafting = PaperEditableDrafting(selection=selection)
    request = command()

    with pytest.raises(PaperEditableDraftingError, match="不能新增、遗漏或替换"):
        drafting.build(
            PaperEditableDraftCommand.model_validate(
                {
                    "selection_request": request.model_dump(mode="json"),
                    "edits": [
                        {
                            "question_id": "forged-question",
                            "position": 1,
                            "section_id": "section-1",
                            "score": 10,
                        }
                    ],
                }
            ),
            owner_id="teacher-a",
        )


def test_editable_paper_http_binds_owner_and_forbids_trust_or_save_fields() -> None:
    selection = PaperBlueprintSelection(
        question_bank=SelectionQuestionBank(
            [
                public_question("q1", stem="函数 f(x)=x+1 的零点是（ ）"),
                public_question("q2", stem="函数 f(x)=x² 的最小值是（ ）"),
            ]
        ),
        personal_question_library=SelectionPersonalLibrary(),
    )
    app.dependency_overrides[get_paper_editable_drafting] = lambda: PaperEditableDrafting(
        selection=selection
    )
    app.dependency_overrides[get_current_teacher] = lambda: CurrentTeacher(
        teacher_id="server-owner",
        source="authenticated_session",
    )
    payload = {
        "selection_request": command().model_dump(mode="json"),
        "edits": [],
    }
    try:
        client = TestClient(app)
        response = client.post("/api/v1/exam-papers/blueprints/edit-draft", json=payload)
        forged = client.post(
            "/api/v1/exam-papers/blueprints/edit-draft",
            json={
                **payload,
                "owner_id": "another-owner",
                "saved": True,
                "verification_status": "passed",
            },
        )
    finally:
        app.dependency_overrides.pop(get_paper_editable_drafting, None)
        app.dependency_overrides.pop(get_current_teacher, None)

    assert response.status_code == 200
    assert response.json()["saved"] is False
    assert response.json()["version_created"] is False
    assert response.json()["export_ready"] is False
    assert forged.status_code == 422


def make_versioning(tmp_path: Path) -> tuple[PaperEditableDrafting, PaperVersioning, PaperSavedExporting]:
    bank = SelectionQuestionBank(
        [
            public_question("q1", stem="函数 f(x)=x+1 的零点是（ ）", difficulty=2),
            public_question("q2", stem="函数 f(x)=x² 的最小值是（ ）", difficulty=4),
        ]
    )
    selection = PaperBlueprintSelection(
        question_bank=bank,
        personal_question_library=SelectionPersonalLibrary(),
    )
    drafting = PaperEditableDrafting(selection=selection)
    studio = ExamPaperStudio(
        database_path=tmp_path / "paper-versions.sqlite3",
        asset_root=tmp_path / "paper-assets",
        question_bank=bank,
    )
    versioning = PaperVersioning(drafting=drafting, studio=studio)
    exporting = PaperSavedExporting(
        studio=studio,
        renderer=ExamPaperDocumentRenderer(
            output_root=tmp_path / "exports",
            asset_root=tmp_path / "paper-assets",
        ),
    )
    return drafting, versioning, exporting


def test_explicit_save_creates_owner_scoped_immutable_version_and_six_exports(
    tmp_path: Path,
) -> None:
    drafting, versioning, exporting = make_versioning(tmp_path)
    draft_command = PaperEditableDraftCommand(
        selection_request=command(),
        edits=[],
    )
    draft = drafting.build(draft_command, owner_id="teacher-a")

    saved = versioning.save(
        PaperVersionSaveCommand(
            draft_command=draft_command,
            expected_draft_fingerprint=draft.draft_fingerprint,
        ),
        owner_id="teacher-a",
    )

    assert saved.saved is True
    assert saved.version_created is True
    assert saved.export_ready is True
    assert saved.version == 1
    assert saved.question_count == 2
    assert len(saved.available_exports) == 6
    assert saved.side_effects == ["created_exam_paper_version"]
    blueprint = exporting.export(
        paper_id=saved.exam_paper_id,
        version=saved.version,
        owner_id="teacher-a",
        export_format="docx",
        edition="blueprint",
    )
    with ZipFile(blueprint.path) as archive:
        xml = archive.read("word/document.xml").decode("utf-8")
    assert "双向细目表" in xml
    assert "教学维度到题目" in xml
    with pytest.raises(PaperSavedExportingError, match="不属于当前教师"):
        exporting.export(
            paper_id=saved.exam_paper_id,
            version=saved.version,
            owner_id="teacher-b",
            export_format="pdf",
            edition="student",
        )


def test_explicit_save_allows_an_incomplete_blueprint_after_teacher_confirmation(
    tmp_path: Path,
) -> None:
    bank = SelectionQuestionBank(
        [public_question("q1", stem="函数 f(x)=x+1 的零点是（ ）")]
    )
    selection = PaperBlueprintSelection(
        question_bank=bank,
        personal_question_library=SelectionPersonalLibrary(),
    )
    drafting = PaperEditableDrafting(selection=selection)
    draft_command = PaperEditableDraftCommand(selection_request=command(), edits=[])
    draft = drafting.build(draft_command, owner_id="teacher-a")
    assert draft.selection_complete is False
    assert draft.draft_consistent is False

    versioning = PaperVersioning(
        drafting=drafting,
        studio=ExamPaperStudio(
            database_path=tmp_path / "incomplete-paper.sqlite3",
            asset_root=tmp_path / "incomplete-paper-assets",
            question_bank=bank,
        ),
    )
    saved = versioning.save(
        PaperVersionSaveCommand(
            draft_command=draft_command,
            expected_draft_fingerprint=draft.draft_fingerprint,
        ),
        owner_id="teacher-a",
    )

    assert saved.saved is True
    assert saved.question_count == 1
    assert saved.total_score == 5


def test_save_rejects_stale_fingerprint_without_creating_version(tmp_path: Path) -> None:
    drafting, versioning, _ = make_versioning(tmp_path)
    draft_command = PaperEditableDraftCommand(selection_request=command(), edits=[])
    draft = drafting.build(draft_command, owner_id="teacher-a")

    with pytest.raises(PaperVersioningConflict, match="草稿已变化"):
        versioning.save(
            PaperVersionSaveCommand(
                draft_command=draft_command,
                expected_draft_fingerprint="0" * 64,
            ),
            owner_id="teacher-a",
        )

    assert versioning.studio.list().total == 0
    assert len(draft.draft_fingerprint) == 64


def test_save_and_exact_version_export_http_bind_owner_server_side(tmp_path: Path) -> None:
    drafting, versioning, exporting = make_versioning(tmp_path)
    draft_command = PaperEditableDraftCommand(selection_request=command(), edits=[])
    draft = drafting.build(draft_command, owner_id="server-owner")
    memory = TeacherMemory(database_path=tmp_path / "teacher-memory.sqlite3")
    memory.apply(
        TeacherMemoryCommand(operation="set_auto_learning", enabled=True),
        owner_id="server-owner",
    )
    app.dependency_overrides[get_paper_versioning] = lambda: versioning
    app.dependency_overrides[get_paper_saved_exporting] = lambda: exporting
    app.dependency_overrides[get_teacher_memory] = lambda: memory
    app.dependency_overrides[get_current_teacher] = lambda: CurrentTeacher(
        teacher_id="server-owner",
        source="authenticated_session",
    )
    try:
        client = TestClient(app)
        payload = {
            "draft_command": draft_command.model_dump(mode="json"),
            "expected_draft_fingerprint": draft.draft_fingerprint,
        }
        response = client.post(
            "/api/v1/exam-papers/blueprints/save-version",
            json=payload,
        )
        for _ in range(2):
            repeated = client.post(
                "/api/v1/exam-papers/blueprints/save-version",
                json=payload,
            )
            assert repeated.status_code == 201
        forged = client.post(
            "/api/v1/exam-papers/blueprints/save-version",
            json={
                **payload,
                "owner_id": "another-owner",
                "saved": True,
                "version": 99,
                "verification_status": "passed",
            },
        )
        saved = response.json()
        download = client.get(
            f"/api/v1/exam-papers/{saved['exam_paper_id']}/versions/1/export",
            params={"format": "pdf", "edition": "student"},
        )
        app.dependency_overrides[get_current_teacher] = lambda: CurrentTeacher(
            teacher_id="other-owner",
            source="authenticated_session",
        )
        denied = client.get(
            f"/api/v1/exam-papers/{saved['exam_paper_id']}/versions/1/export",
            params={"format": "pdf", "edition": "student"},
        )
    finally:
        app.dependency_overrides.pop(get_paper_versioning, None)
        app.dependency_overrides.pop(get_paper_saved_exporting, None)
        app.dependency_overrides.pop(get_teacher_memory, None)
        app.dependency_overrides.pop(get_current_teacher, None)

    assert response.status_code == 201
    assert any(
        proposal.key == "default_difficulty"
        and proposal.evidence.occurrence_count == 3
        for proposal in memory.profile(owner_id="server-owner").proposals
    )
    assert forged.status_code == 422
    assert download.status_code == 200
    assert download.content.startswith(b"%PDF")
    assert denied.status_code == 404
