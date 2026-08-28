from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.identity import CurrentTeacher, get_current_teacher
from app.main import app
from app.modules.exam_papers import (
    PaperBlueprintSelection,
    PaperBlueprintSelectionCommand,
    PaperBlueprintSelectionError,
)
from app.modules.question_bank.schemas import QuestionSearchPage, QuestionSummary
from app.routes.exam_papers import get_paper_blueprint_selection


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


class SelectionPersonalLibrary:
    def __init__(self, questions: dict[str, object] | None = None) -> None:
        self.questions = questions or {}

    def get_question(self, question_id: str, *, owner_id: str):
        value = self.questions.get(f"{owner_id}:{question_id}")
        if value is None:
            raise KeyError(question_id)
        return value


def private_question(question_id: str = "private-1") -> object:
    draft = SimpleNamespace(
        solution_status="ready",
        verification=SimpleNamespace(
            status="teacher_review_required",
            math_verifier_status="unsupported",
            checks=[SimpleNamespace(status="passed")],
        ),
        stem_plain="设函数 f(x)=x²，则 f(1) 的值为（ ）",
        question_type="single_choice",
        answer_value="A",
        curriculum=SimpleNamespace(
            volume="必修第一册",
            chapter="函数",
            section="函数的概念",
        ),
        knowledge_points=["函数"],
        estimated_difficulty=2,
        options=[
            SimpleNamespace(key="A", text="1"),
            SimpleNamespace(key="B", text="2"),
        ],
    )
    return SimpleNamespace(
        question_id=question_id,
        lifecycle_state="active",
        question=draft,
        name="我的函数题",
        selected_revision=3,
    )


def command(*, count: int = 2, score: float = 10, private_ids: list[str] | None = None):
    return PaperBlueprintSelectionCommand.model_validate(
        {
            "blueprint": {
                "title": "高二函数测验",
                "grade_scope": "高二",
                "teaching_usage": "专题测验",
                "duration_minutes": 30,
                "target_score": score,
                "difficulty_profile": "balanced",
                "knowledge_points": ["函数"],
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
    assert forged.status_code == 422
