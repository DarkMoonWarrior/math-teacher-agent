from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.identity import CurrentTeacher, get_current_teacher
from app.main import app
from app.modules.personal_question_library import (
    PersonalAuthoringRevisionCreate,
    PersonalCategoryCreate,
    PersonalCategoryUpdate,
    PersonalCollectionCreate,
    PersonalCollectionUpdate,
    PersonalQuestionSave,
    PersonalQuestionLibrary,
    PersonalQuestionLibraryConflict,
)
from app.modules.curriculum import InMemoryCurriculumCatalog
from app.modules.math_verifier import MathVerifier
from app.modules.question_authoring import (
    GeneratedQuestionDraft,
    QuestionAuthoring,
    QuestionDraftCurriculum,
    QuestionDraftEditableContent,
    QuestionDraftOption,
    QuestionDraftTrustCheck,
    QuestionDraftVerification,
)
from app.routes.personal_question_library import get_personal_question_library
from app.routes.personal_question_library import get_question_authoring_editor


def make_library(tmp_path: Path) -> PersonalQuestionLibrary:
    return PersonalQuestionLibrary(tmp_path / "personal-question-library.sqlite3")


def teacher(teacher_id: str):
    def dependency() -> CurrentTeacher:
        return CurrentTeacher(
            teacher_id=teacher_id,
            source="authenticated_session",
        )

    return dependency


def generated_draft(draft_id: str = "qad_private_fixture") -> GeneratedQuestionDraft:
    check_specs = [
        ("solvability", "inconclusive", "unsupported", "none"),
        ("answer_solution_consistency", "passed", "supported", "deterministic_structure"),
        ("choice_answer_cardinality", "passed", "supported", "deterministic_structure"),
        ("distractor_quality", "inconclusive", "unsupported", "none"),
        ("math_verifier", "inconclusive", "unsupported", "none"),
        ("difficulty_disclosure", "passed", "supported", "model_estimate"),
    ]
    checks = [
        QuestionDraftTrustCheck(
            code=code,
            status=status,
            capability=capability,
            evidence_source=source,
            summary=f"synthetic {code}",
        )
        for code, status, capability, source in check_specs
    ]
    return GeneratedQuestionDraft(
        draft_id=draft_id,
        request_text="命制一道函数单调性的单选题，用于课堂诊断。",
        question_type="single_choice",
        stem_plain="已知函数 f(x)=x²，判断其在实数范围内的单调性。",
        stem_latex=r"已知函数 $f(x)=x^2$，判断其单调性。",
        options=[
            QuestionDraftOption(key="A", text="恒增"),
            QuestionDraftOption(key="B", text="先减后增"),
            QuestionDraftOption(key="C", text="恒减"),
            QuestionDraftOption(key="D", text="不是函数"),
        ],
        answer_value="B",
        solution_method="定义法",
        solution_steps=["比较自变量大小。", "判断函数值变化。"],
        final_answer="答案为 B。",
        authoring_intent="考查函数单调性的分区判断。",
        curriculum=QuestionDraftCurriculum(
            node_id="kp_monotonicity",
            name="函数单调性的判断",
            volume="必修第一册",
            chapter="函数的概念与性质",
            section="函数单调性",
            mapping_source="teacher_selected",
            match_confidence=1,
            curriculum_status="reviewed",
            reviewed_by="synthetic_teacher",
        ),
        target_difficulty=2,
        estimated_difficulty=2,
        verification=QuestionDraftVerification(
            status="teacher_review_required",
            math_verifier_status="unsupported",
            math_verifier_checked=False,
            teacher_review_required=True,
            verifier_version=MathVerifier.VERSION,
            checks=checks,
            details=["synthetic trust evidence"],
        ),
        provider="synthetic_provider",
        model="synthetic-author-v1",
        prompt_revision="synthetic-v1",
        created_at="2026-08-24T00:00:00+00:00",
    )


def editable_content(draft: GeneratedQuestionDraft, *, stem: str) -> QuestionDraftEditableContent:
    return QuestionDraftEditableContent(
        question_type=draft.question_type,
        stem_plain=stem,
        stem_latex=draft.stem_latex,
        options=draft.options,
        answer_value=draft.answer_value,
        solution_method=draft.solution_method,
        solution_steps=draft.solution_steps,
        final_answer=draft.final_answer,
        authoring_intent=draft.authoring_intent,
    )


def test_collections_are_owner_only_and_never_expose_owner_or_public_transitions(
    tmp_path: Path,
) -> None:
    library = make_library(tmp_path)
    mine = library.create_collection(
        PersonalCollectionCreate(name="  高二 圆锥曲线  ", description="月考备用题"),
        owner_id="teacher_a",
    )
    other = library.create_collection(
        PersonalCollectionCreate(name="高二 圆锥曲线"),
        owner_id="teacher_b",
    )

    assert mine.collection_id != other.collection_id
    assert mine.name == "高二 圆锥曲线"
    assert library.list_collections(owner_id="teacher_a").total == 1
    assert (
        library.list_collections(owner_id="teacher_b").items[0].collection_id
        == other.collection_id
    )
    with pytest.raises(KeyError):
        library.get_collection(mine.collection_id, owner_id="teacher_b")

    payload = mine.model_dump(mode="json")
    assert payload["visibility"] == "owner_only"
    assert payload["public_search_allowed"] is False
    assert payload["share_allowed"] is False
    assert payload["commercial_use_allowed"] is False
    assert payload["model_training_allowed"] is False
    assert "owner_id" not in payload
    assert "publish" not in str(payload).lower()


def test_collection_names_are_unique_per_owner_and_can_be_renamed(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    first = library.create_collection(
        PersonalCollectionCreate(name="函数专题"),
        owner_id="teacher_a",
    )
    with pytest.raises(PersonalQuestionLibraryConflict, match="同名"):
        library.create_collection(
            PersonalCollectionCreate(name="  函数专题  "),
            owner_id="teacher_a",
        )

    updated = library.update_collection(
        first.collection_id,
        PersonalCollectionUpdate(name="导数专题", description="一轮复习"),
        owner_id="teacher_a",
    )
    assert updated.name == "导数专题"
    assert updated.description == "一轮复习"


def test_categories_are_scoped_to_owner_and_collection(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    mine = library.create_collection(
        PersonalCollectionCreate(name="我的私题"),
        owner_id="teacher_a",
    )
    category = library.create_category(
        mine.collection_id,
        PersonalCategoryCreate(name="易错题", description="课堂诊断", sort_order=20),
        owner_id="teacher_a",
    )

    assert library.get_collection(mine.collection_id, owner_id="teacher_a").category_count == 1
    assert library.list_categories(mine.collection_id, owner_id="teacher_a").items == [category]
    with pytest.raises(KeyError):
        library.list_categories(mine.collection_id, owner_id="teacher_b")
    with pytest.raises(KeyError):
        library.get_category(category.category_id, owner_id="teacher_b")
    with pytest.raises(KeyError):
        library.update_category(
            category.category_id,
            PersonalCategoryUpdate(name="越权分类"),
            owner_id="teacher_b",
        )

    updated = library.update_category(
        category.category_id,
        PersonalCategoryUpdate(name="压轴题", sort_order=5),
        owner_id="teacher_a",
    )
    assert updated.name == "压轴题"
    assert updated.description == "课堂诊断"
    assert updated.sort_order == 5


def test_storage_namespace_has_no_publication_or_question_bank_tables(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    with sqlite3.connect(library.database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        columns = {
            row[1]
            for table in tables
            for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }

    assert tables == {
        "personal_authoring_drafts",
        "personal_authoring_revisions",
        "personal_question_collections",
        "personal_question_categories",
        "personal_questions",
    }
    assert "visibility" not in columns
    assert "publish_status" not in columns
    assert "share_status" not in columns
    assert "commercial_status" not in columns


def test_authoring_revisions_are_owner_only_append_only_and_version_checked(
    tmp_path: Path,
) -> None:
    library = make_library(tmp_path)
    original = generated_draft()
    staged = library.stage_generated_draft(original, owner_id="teacher_a")

    assert staged.current_revision == 1
    assert staged.saved is False
    assert staged.current.revision_source == "ai_generated"
    with pytest.raises(KeyError):
        library.get_authoring_draft(original.draft_id, owner_id="teacher_b")

    revised_draft = original.model_copy(
        update={"stem_plain": "教师修改后的函数单调性题干。"}
    )
    revised = library.append_teacher_revision(
        revised_draft,
        owner_id="teacher_a",
        expected_revision=1,
        edit_summary="精简题干",
    )
    history = library.list_authoring_revisions(original.draft_id, owner_id="teacher_a")

    assert revised.current_revision == 2
    assert revised.current.revision_source == "teacher_edit"
    assert history.total == 2
    assert [item.revision_number for item in history.items] == [2, 1]
    with pytest.raises(PersonalQuestionLibraryConflict, match="当前版本为 2"):
        library.append_teacher_revision(
            revised_draft,
            owner_id="teacher_a",
            expected_revision=1,
            edit_summary="使用过期版本覆盖",
        )


def test_teacher_explicitly_saves_selected_revision_to_owned_category(
    tmp_path: Path,
) -> None:
    library = make_library(tmp_path)
    collection = library.create_collection(
        PersonalCollectionCreate(name="我的命题"), owner_id="teacher_a"
    )
    category = library.create_category(
        collection.collection_id,
        PersonalCategoryCreate(name="函数"),
        owner_id="teacher_a",
    )
    other_collection = library.create_collection(
        PersonalCollectionCreate(name="别人的题库"), owner_id="teacher_b"
    )
    other_category = library.create_category(
        other_collection.collection_id,
        PersonalCategoryCreate(name="不可写"),
        owner_id="teacher_b",
    )
    draft = generated_draft()
    library.stage_generated_draft(draft, owner_id="teacher_a")

    with pytest.raises(KeyError):
        library.save_authoring_draft(
            draft.draft_id,
            PersonalQuestionSave(
                expected_revision=1,
                collection_id=other_collection.collection_id,
                category_id=other_category.category_id,
                name="越权保存",
            ),
            owner_id="teacher_a",
        )

    saved = library.save_authoring_draft(
        draft.draft_id,
        PersonalQuestionSave(
            expected_revision=1,
            collection_id=collection.collection_id,
            category_id=category.category_id,
            name="函数单调性诊断题",
        ),
        owner_id="teacher_a",
    )

    assert saved.question.saved is True
    assert saved.visibility == "owner_only"
    assert saved.public_search_allowed is False
    assert library.get_collection(collection.collection_id, owner_id="teacher_a").question_count == 1
    assert library.get_category(category.category_id, owner_id="teacher_a").question_count == 1
    with pytest.raises(KeyError):
        library.get_question(saved.question_id, owner_id="teacher_b")
    with pytest.raises(PersonalQuestionLibraryConflict, match="已经保存"):
        library.save_authoring_draft(
            draft.draft_id,
            PersonalQuestionSave(
                expected_revision=1,
                collection_id=collection.collection_id,
                category_id=category.category_id,
                name="重复保存",
            ),
            owner_id="teacher_a",
        )


def test_http_identity_binding_rejects_owner_selection_and_cross_owner_access(
    tmp_path: Path,
) -> None:
    library = make_library(tmp_path)
    app.dependency_overrides[get_personal_question_library] = lambda: library
    app.dependency_overrides[get_current_teacher] = teacher("teacher_a")
    try:
        with TestClient(app) as client:
            created = client.post(
                "/api/v1/personal-question-library/collections",
                json={"name": "解析几何", "description": "个人整理"},
            )
            assert created.status_code == 201
            collection = created.json()
            assert "owner_id" not in collection

            forged = client.post(
                "/api/v1/personal-question-library/collections",
                json={"name": "伪造归属", "owner_id": "teacher_b"},
            )
            assert forged.status_code == 422

            category = client.post(
                "/api/v1/personal-question-library/collections/"
                f"{collection['collection_id']}/categories",
                json={"name": "课堂例题", "sort_order": 1},
            )
            assert category.status_code == 201
            category_id = category.json()["category_id"]

            app.dependency_overrides[get_current_teacher] = teacher("teacher_b")
            assert client.get(
                f"/api/v1/personal-question-library/collections/{collection['collection_id']}"
            ).status_code == 404
            assert client.get(
                f"/api/v1/personal-question-library/categories/{category_id}"
            ).status_code == 404
            assert client.get(
                "/api/v1/personal-question-library/collections"
            ).json() == {"items": [], "total": 0}
    finally:
        app.dependency_overrides.pop(get_current_teacher, None)
        app.dependency_overrides.pop(get_personal_question_library, None)


def test_http_authoring_revision_and_explicit_save_are_teacher_bound(
    tmp_path: Path,
) -> None:
    library = make_library(tmp_path)
    draft = generated_draft()
    library.stage_generated_draft(draft, owner_id="teacher_a")
    collection = library.create_collection(
        PersonalCollectionCreate(name="个人命题"), owner_id="teacher_a"
    )
    category = library.create_category(
        collection.collection_id,
        PersonalCategoryCreate(name="函数"),
        owner_id="teacher_a",
    )
    editor = QuestionAuthoring(
        curriculum=InMemoryCurriculumCatalog([]),
        provider=None,
        math_verifier=MathVerifier(),
    )
    app.dependency_overrides[get_personal_question_library] = lambda: library
    app.dependency_overrides[get_question_authoring_editor] = lambda: editor
    app.dependency_overrides[get_current_teacher] = teacher("teacher_a")
    try:
        revision_command = PersonalAuthoringRevisionCreate(
            expected_revision=1,
            content=editable_content(draft, stem="教师确认后的函数单调性题干。"),
            edit_summary="教师校订题干",
        )
        with TestClient(app) as client:
            revised = client.post(
                f"/api/v1/personal-question-library/authoring-drafts/{draft.draft_id}/revisions",
                json=revision_command.model_dump(mode="json"),
            )
            forged = client.post(
                f"/api/v1/personal-question-library/authoring-drafts/{draft.draft_id}/revisions",
                json={**revision_command.model_dump(mode="json"), "owner_id": "teacher_b"},
            )
            forged_trust = client.post(
                f"/api/v1/personal-question-library/authoring-drafts/{draft.draft_id}/revisions",
                json={
                    **revision_command.model_dump(mode="json"),
                    "content": {
                        **revision_command.content.model_dump(mode="json"),
                        "verification": {"status": "passed"},
                    },
                },
            )
            saved = client.post(
                f"/api/v1/personal-question-library/authoring-drafts/{draft.draft_id}/save",
                json={
                    "expected_revision": 2,
                    "collection_id": collection.collection_id,
                    "category_id": category.category_id,
                    "name": "函数单调性校订题",
                },
            )

            assert revised.status_code == 201
            assert revised.json()["current_revision"] == 2
            assert revised.json()["current"]["revision_source"] == "teacher_edit"
            assert forged.status_code == 422
            assert forged_trust.status_code == 422
            assert saved.status_code == 201
            assert saved.json()["question"]["saved"] is True
            assert "owner_id" not in str(saved.json())

            question_id = saved.json()["question_id"]
            app.dependency_overrides[get_current_teacher] = teacher("teacher_b")
            assert client.get(
                f"/api/v1/personal-question-library/authoring-drafts/{draft.draft_id}"
            ).status_code == 404
            assert client.get(
                f"/api/v1/personal-question-library/questions/{question_id}"
            ).status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_teacher, None)
        app.dependency_overrides.pop(get_question_authoring_editor, None)
        app.dependency_overrides.pop(get_personal_question_library, None)


def test_public_routes_have_no_publish_share_admin_or_delete_interface() -> None:
    personal_paths = {
        path: operations
        for path, operations in app.openapi()["paths"].items()
        if path.startswith("/api/v1/personal-question-library")
    }
    serialized = str(personal_paths).lower()

    assert personal_paths
    methods = {
        method for operations in personal_paths.values() for method in operations
    }
    assert "delete" not in methods
    assert "publish" not in serialized
    assert "share" not in serialized
    assert "admin" not in serialized
