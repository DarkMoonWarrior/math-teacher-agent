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
    PersonalQuestionCopy,
    PersonalQuestionPermanentDelete,
    PersonalQuestionRevisionCreate,
    PersonalQuestionSave,
    PersonalQuestionUpdate,
    PersonalQuestionVersionCommand,
    PersonalQuestionLibrary,
    PersonalQuestionLibraryConflict,
)
from app.modules.curriculum import InMemoryCurriculumCatalog
from app.modules.math_verifier import MathVerifier
from app.modules.question_authoring import (
    GeneratedQuestionDraft,
    ProviderQuestionDraft,
    ProviderQuestionSolution,
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


def create_saved_question(
    library: PersonalQuestionLibrary,
    *,
    owner_id: str = "teacher_a",
    suffix: str = "base",
):
    collection = library.create_collection(
        PersonalCollectionCreate(name=f"个人命题-{suffix}"), owner_id=owner_id
    )
    category = library.create_category(
        collection.collection_id,
        PersonalCategoryCreate(name="函数"),
        owner_id=owner_id,
    )
    draft = generated_draft(f"qad_private_{suffix}")
    library.stage_generated_draft(draft, owner_id=owner_id)
    question = library.save_authoring_draft(
        draft.draft_id,
        PersonalQuestionSave(
            expected_revision=1,
            collection_id=collection.collection_id,
            category_id=category.category_id,
            name="函数单调性诊断题",
        ),
        owner_id=owner_id,
    )
    return collection, category, question


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
    assert any("明确保存" in warning for warning in saved.question.warnings)
    assert all("尚未保存" not in warning for warning in saved.question.warnings)
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


def test_owner_can_list_search_rename_move_tag_sort_and_copy_questions(
    tmp_path: Path,
) -> None:
    library = make_library(tmp_path)
    source_collection, source_category, source = create_saved_question(
        library, suffix="manage"
    )
    target_collection = library.create_collection(
        PersonalCollectionCreate(name="课堂精选"), owner_id="teacher_a"
    )
    target_category = library.create_category(
        target_collection.collection_id,
        PersonalCategoryCreate(name="易错题"),
        owner_id="teacher_a",
    )

    updated = library.update_question(
        source.question_id,
        PersonalQuestionUpdate(
            expected_updated_at=source.updated_at,
            name="函数单调性课堂诊断",
            collection_id=target_collection.collection_id,
            category_id=target_category.category_id,
            tags=[" 高一 ", "课堂诊断", "高一"],
            sort_order=7,
        ),
        owner_id="teacher_a",
    )
    found = library.list_questions(
        owner_id="teacher_a",
        query="单调性",
        collection_id=target_collection.collection_id,
        category_id=target_category.category_id,
    )
    copied = library.copy_question(
        source.question_id,
        PersonalQuestionCopy(
            collection_id=target_collection.collection_id,
            category_id=target_category.category_id,
        ),
        owner_id="teacher_a",
    )

    assert updated.name == "函数单调性课堂诊断"
    assert updated.tags == ["高一", "课堂诊断"]
    assert updated.sort_order == 7
    assert found.total == 1
    assert found.items[0].question_id == source.question_id
    assert copied.question_id != source.question_id
    assert copied.source_draft_id != source.source_draft_id
    assert copied.copied_from_question_id == source.question_id
    assert copied.question.stem_plain == source.question.stem_plain
    assert library.get_collection(source_collection.collection_id, owner_id="teacher_a").question_count == 0
    assert library.get_category(source_category.category_id, owner_id="teacher_a").question_count == 0
    assert library.get_collection(target_collection.collection_id, owner_id="teacher_a").question_count == 2
    assert library.list_questions(owner_id="teacher_b", query="单调性").total == 0
    with pytest.raises(PersonalQuestionLibraryConflict, match="版本已变化"):
        library.update_question(
            source.question_id,
            PersonalQuestionUpdate(
                expected_updated_at=source.updated_at,
                name="使用旧版本覆盖",
            ),
            owner_id="teacher_a",
        )
    with pytest.raises(KeyError):
        library.copy_question(
            source.question_id,
            PersonalQuestionCopy(
                collection_id=target_collection.collection_id,
                category_id=target_category.category_id,
            ),
            owner_id="teacher_b",
        )


def test_owner_can_revise_saved_question_with_new_trust_evidence(
    tmp_path: Path,
) -> None:
    library = make_library(tmp_path)
    _, _, question = create_saved_question(library, suffix="saved-revision")
    editor = QuestionAuthoring(
        curriculum=InMemoryCurriculumCatalog([]),
        provider=None,
        math_verifier=MathVerifier(),
    )
    current_payload = question.question.model_dump(mode="json")
    current_payload["saved"] = False
    current_draft = GeneratedQuestionDraft.model_validate(current_payload)
    command = PersonalQuestionRevisionCreate(
        expected_revision=1,
        expected_updated_at=question.updated_at,
        content=QuestionDraftEditableContent(
            question_type=current_draft.question_type,
            stem_plain="保存后由教师修订的函数单调性题干。",
            stem_latex=current_draft.stem_latex,
            options=current_draft.options,
            answer_value="B",
            solution_method=current_draft.solution_method,
            solution_steps=current_draft.solution_steps,
            final_answer="答案为 A。",
            authoring_intent=current_draft.authoring_intent,
        ),
        edit_summary="保存后修订题干和最终答案",
    )
    revised_draft = editor.revise_draft(current_draft, command.content)
    revised = library.append_saved_question_revision(
        question.question_id,
        revised_draft,
        command,
        owner_id="teacher_a",
    )

    assert revised.selected_revision == 2
    assert revised.question.stem_plain.startswith("保存后由教师修订")
    assert revised.question.verification.status == "checks_failed"
    history = library.list_authoring_revisions(
        revised.source_draft_id,
        owner_id="teacher_a",
    )
    assert [item.revision_number for item in history.items] == [2, 1]
    with pytest.raises(PersonalQuestionLibraryConflict, match="版本已变化"):
        library.append_saved_question_revision(
            question.question_id,
            revised_draft,
            command,
            owner_id="teacher_a",
        )


def test_private_export_contains_no_owner_selector_or_public_transition(
    tmp_path: Path,
) -> None:
    library = make_library(tmp_path)
    _, _, question = create_saved_question(library, suffix="export")
    library.update_question(
        question.question_id,
        PersonalQuestionUpdate(
            expected_updated_at=question.updated_at,
            tags=["函数", "诊断"],
        ),
        owner_id="teacher_a",
    )

    json_export = library.export_question(
        question.question_id,
        owner_id="teacher_a",
        export_format="json",
    )
    markdown_export = library.export_question(
        question.question_id,
        owner_id="teacher_a",
        export_format="markdown",
    )

    assert json_export.filename.endswith(".json")
    assert '"visibility": "owner_only"' in json_export.content
    assert "owner_id" not in json_export.content
    assert markdown_export.filename.endswith(".md")
    assert "仅自己可见" in markdown_export.content
    assert "## 题目" in markdown_export.content
    assert "## 答案" in markdown_export.content
    with pytest.raises(KeyError):
        library.export_question(
            question.question_id,
            owner_id="teacher_b",
            export_format="json",
        )


def test_trash_restore_and_permanent_delete_clear_only_owned_active_storage(
    tmp_path: Path,
) -> None:
    library = make_library(tmp_path)
    collection, category, question = create_saved_question(library, suffix="delete")
    copied = library.copy_question(
        question.question_id,
        PersonalQuestionCopy(
            collection_id=collection.collection_id,
            category_id=category.category_id,
            name="保留的独立副本",
        ),
        owner_id="teacher_a",
    )

    with pytest.raises(PersonalQuestionLibraryConflict, match="回收站"):
        library.permanently_delete_question(
            question.question_id,
            PersonalQuestionPermanentDelete(
                expected_updated_at=question.updated_at,
                confirmation="永久删除我的私题",
            ),
            owner_id="teacher_a",
        )
    trashed = library.trash_question(
        question.question_id,
        PersonalQuestionVersionCommand(expected_updated_at=question.updated_at),
        owner_id="teacher_a",
    )
    assert trashed.lifecycle_state == "trashed"
    assert trashed.trashed_at is not None
    assert library.list_questions(owner_id="teacher_a").total == 1
    assert library.list_questions(owner_id="teacher_a", lifecycle_state="trashed").total == 1
    assert library.get_collection(collection.collection_id, owner_id="teacher_a").question_count == 1

    with pytest.raises(PersonalQuestionLibraryConflict, match="状态或版本"):
        library.restore_question(
            question.question_id,
            PersonalQuestionVersionCommand(expected_updated_at=question.updated_at),
            owner_id="teacher_a",
        )
    restored = library.restore_question(
        question.question_id,
        PersonalQuestionVersionCommand(expected_updated_at=trashed.updated_at),
        owner_id="teacher_a",
    )
    trashed_again = library.trash_question(
        question.question_id,
        PersonalQuestionVersionCommand(expected_updated_at=restored.updated_at),
        owner_id="teacher_a",
    )
    with pytest.raises(KeyError):
        library.permanently_delete_question(
            question.question_id,
            PersonalQuestionPermanentDelete(
                expected_updated_at=trashed_again.updated_at,
                confirmation="永久删除我的私题",
            ),
            owner_id="teacher_b",
        )

    receipt = library.permanently_delete_question(
        question.question_id,
        PersonalQuestionPermanentDelete(
            expected_updated_at=trashed_again.updated_at,
            confirmation="永久删除我的私题",
        ),
        owner_id="teacher_a",
    )

    assert receipt.active_storage_deleted is True
    with pytest.raises(KeyError):
        library.get_question(question.question_id, owner_id="teacher_a")
    assert library.get_question(copied.question_id, owner_id="teacher_a").name == "保留的独立副本"
    with sqlite3.connect(library.database_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM personal_authoring_drafts WHERE draft_id = ?",
            (question.source_draft_id,),
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM personal_authoring_revisions WHERE draft_id = ?",
            (question.source_draft_id,),
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM personal_authoring_drafts WHERE draft_id = ?",
            (copied.source_draft_id,),
        ).fetchone()[0] == 1


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


def test_http_regenerate_solution_appends_ai_revision_without_changing_question(
    tmp_path: Path,
) -> None:
    class RegenerationProvider:
        name = "synthetic_provider"
        model = "synthetic-regenerator-v1"

        def generate(self, _context: object) -> ProviderQuestionDraft:  # pragma: no cover
            raise AssertionError("regeneration must not regenerate the whole question")

        def regenerate_solution(self, current: ProviderQuestionDraft) -> ProviderQuestionSolution:
            assert current.stem_plain == draft.stem_plain
            assert current.answer_value == draft.answer_value
            assert current.final_answer == draft.final_answer
            return ProviderQuestionSolution(
                solution_method="重新生成的定义法",
                solution_steps=["固定题面后重新求解，并据此更新标准答案。"],
                answer_value="A",
                final_answer="A",
            )

    library = make_library(tmp_path)
    draft = generated_draft("qad_regenerate_solution")
    library.stage_generated_draft(draft, owner_id="teacher_a")
    editor = QuestionAuthoring(
        curriculum=InMemoryCurriculumCatalog([]),
        provider=RegenerationProvider(),  # type: ignore[arg-type]
        math_verifier=MathVerifier(),
    )
    app.dependency_overrides[get_personal_question_library] = lambda: library
    app.dependency_overrides[get_question_authoring_editor] = lambda: editor
    app.dependency_overrides[get_current_teacher] = teacher("teacher_a")
    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/v1/personal-question-library/authoring-drafts/{draft.draft_id}/regenerate-solution",
                json={"expected_revision": 1},
            )

            assert response.status_code == 201
            payload = response.json()
            assert payload["current_revision"] == 2
            assert payload["current"]["revision_source"] == "ai_generated"
            regenerated = payload["current"]["draft"]
            assert regenerated["stem_plain"] == draft.stem_plain
            assert regenerated["stem_latex"] == draft.stem_latex
            assert regenerated["options"] == [item.model_dump(mode="json") for item in draft.options]
            assert regenerated["answer_value"] == "A"
            assert regenerated["final_answer"] == "A"
            assert regenerated["solution_method"] == "重新生成的定义法"
            assert regenerated["solution_steps"] == ["固定题面后重新求解，并据此更新标准答案。"]
            assert regenerated["visibility"] == "owner_only"
            assert regenerated["saved"] is False

            app.dependency_overrides[get_current_teacher] = teacher("teacher_b")
            cross_owner = client.post(
                f"/api/v1/personal-question-library/authoring-drafts/{draft.draft_id}/regenerate-solution",
                json={"expected_revision": 2},
            )
            assert cross_owner.status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_teacher, None)
        app.dependency_overrides.pop(get_question_authoring_editor, None)
        app.dependency_overrides.pop(get_personal_question_library, None)


def test_http_personal_management_export_and_delete_are_owner_bound(
    tmp_path: Path,
) -> None:
    library = make_library(tmp_path)
    _, _, question = create_saved_question(library, suffix="http-manage")
    editor = QuestionAuthoring(
        curriculum=InMemoryCurriculumCatalog([]),
        provider=None,
        math_verifier=MathVerifier(),
    )
    app.dependency_overrides[get_personal_question_library] = lambda: library
    app.dependency_overrides[get_question_authoring_editor] = lambda: editor
    app.dependency_overrides[get_current_teacher] = teacher("teacher_a")
    try:
        with TestClient(app) as client:
            forged = client.patch(
                f"/api/v1/personal-question-library/questions/{question.question_id}",
                json={"name": "伪造", "owner_id": "teacher_b"},
            )
            revised = client.post(
                f"/api/v1/personal-question-library/questions/{question.question_id}/revisions",
                json={
                    "expected_revision": 1,
                    "expected_updated_at": question.updated_at,
                    "content": editable_content(
                        question.question,
                        stem="HTTP 保存后修订的函数题。",
                    ).model_dump(mode="json"),
                    "edit_summary": "HTTP 修订",
                },
            )
            updated = client.patch(
                f"/api/v1/personal-question-library/questions/{question.question_id}",
                json={
                    "expected_updated_at": revised.json()["updated_at"],
                    "name": "HTTP 管理题",
                    "tags": ["函数", "课堂"],
                },
            )
            listed = client.get(
                "/api/v1/personal-question-library/questions",
                params={"query": "HTTP 管理"},
            )
            exported = client.get(
                f"/api/v1/personal-question-library/questions/{question.question_id}/export",
                params={"format": "markdown"},
            )
            trashed = client.post(
                f"/api/v1/personal-question-library/questions/{question.question_id}/trash",
                json={"expected_updated_at": updated.json()["updated_at"]},
            )
            wrong_confirmation = client.request(
                "DELETE",
                f"/api/v1/personal-question-library/questions/{question.question_id}",
                json={
                    "expected_updated_at": trashed.json()["updated_at"],
                    "confirmation": "delete",
                },
            )

            assert forged.status_code == 422
            assert revised.status_code == 201
            assert revised.json()["selected_revision"] == 2
            assert updated.status_code == 200
            assert listed.json()["total"] == 1
            assert exported.status_code == 200
            assert exported.headers["cache-control"] == "private, no-store"
            assert "attachment" in exported.headers["content-disposition"]
            assert "仅自己可见" in exported.text
            assert trashed.status_code == 200
            assert wrong_confirmation.status_code == 422

            app.dependency_overrides[get_current_teacher] = teacher("teacher_b")
            cross_owner = client.request(
                "DELETE",
                f"/api/v1/personal-question-library/questions/{question.question_id}",
                json={
                    "expected_updated_at": trashed.json()["updated_at"],
                    "confirmation": "永久删除我的私题",
                },
            )
            assert cross_owner.status_code == 404

            app.dependency_overrides[get_current_teacher] = teacher("teacher_a")
            deleted = client.request(
                "DELETE",
                f"/api/v1/personal-question-library/questions/{question.question_id}",
                json={
                    "expected_updated_at": trashed.json()["updated_at"],
                    "confirmation": "永久删除我的私题",
                },
            )
            assert deleted.status_code == 200
            assert deleted.json()["active_storage_deleted"] is True
    finally:
        app.dependency_overrides.pop(get_current_teacher, None)
        app.dependency_overrides.pop(get_question_authoring_editor, None)
        app.dependency_overrides.pop(get_personal_question_library, None)


def test_public_routes_have_no_publish_share_or_admin_interface() -> None:
    personal_paths = {
        path: operations
        for path, operations in app.openapi()["paths"].items()
        if path.startswith("/api/v1/personal-question-library")
    }
    serialized = str(personal_paths).lower()

    assert personal_paths
    delete_paths = {
        path for path, operations in personal_paths.items() if "delete" in operations
    }
    assert delete_paths == {"/api/v1/personal-question-library/questions/{question_id}"}
    assert "publish" not in serialized
    assert "share" not in serialized
    assert "admin" not in serialized
