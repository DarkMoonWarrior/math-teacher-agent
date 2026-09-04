"""Closed Beta rehearsal: real sessions, isolated synthetic stores, no model calls."""
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from docx import Document
from pypdf import PdfWriter

from app.core.config import Settings, get_settings
from app.main import app
from app.modules.beta_access import ALL_BETA_CAPABILITIES, BetaAccess, BetaParticipant
from app.modules.beta_access.dependencies import get_beta_access
from app.modules.pdf_imports import ImportBatchCommand, PdfImportStudio
from app.modules.private_library import PrivateLibrary, LibraryIngestCommand
from app.modules.lesson_plans.versioning import LessonVersioning
from app.modules.personal_question_library import (
    PersonalQuestionLibrary, PersonalCollectionCreate, PersonalCategoryCreate, PersonalQuestionSave,
)
from app.modules.question_authoring import QuestionAuthoring, QuestionAuthoringStatementPreview
from app.modules.teacher_memory import TeacherMemory
from app.modules.teacher_memory.dependencies import get_teacher_memory
from app.routes import imports as import_routes
from app.routes import library as library_routes
from app.routes import lesson_plans as lesson_routes
from app.routes import questions as question_routes
from app.routes import question_similarity as similarity_routes
from app.routes import solutions as solution_routes
from app.routes import model_operations as model_routes
from app.routes import exam_papers as paper_routes
from app.routes.personal_question_library import get_personal_question_library


@pytest.fixture
def beta_lifecycle(tmp_path, monkeypatch):
    now = [datetime(2026, 9, 4, tzinfo=timezone.utc)]
    settings = Settings(
        beta_access_enabled=True,
        beta_access_roster_json="{}",
        beta_session_cookie_name="rehearsal_session",
        beta_session_secure_cookie=False,
        beta_session_db=tmp_path / "sessions.sqlite3",
        owner_deletion_ledger_db=tmp_path / "owner-deletions.sqlite3",
    )
    access = BetaAccess(
        database_path=settings.beta_session_db,
        participants={
            f"synthetic-{owner}": BetaParticipant(
                teacher_id=owner, display_label=owner,
                capabilities=list(ALL_BETA_CAPABILITIES),
            ) for owner in ("alpha", "beta")
        },
        session_ttl=timedelta(hours=1), clock=lambda: now[0],
    )
    memory = TeacherMemory(database_path=tmp_path / "memory.sqlite3")
    studio = PdfImportStudio(tmp_path / "imports.sqlite3", tmp_path / "imports")
    monkeypatch.setattr(import_routes, "get_pdf_import_studio", lambda: studio)
    monkeypatch.setitem(app.dependency_overrides, get_settings, lambda: settings)
    monkeypatch.setitem(app.dependency_overrides, get_beta_access, lambda: access)
    monkeypatch.setitem(app.dependency_overrides, get_teacher_memory, lambda: memory)
    with ExitStack() as stack:
        clients = {name: stack.enter_context(TestClient(app)) for name in ("alpha", "beta", "anonymous")}
        for owner in ("alpha", "beta"):
            assert clients[owner].post(
                "/api/v1/beta-session", json={"access_code": f"synthetic-{owner}"},
            ).status_code == 200
        yield clients, settings, now, memory, studio


def _synthetic_import(studio):
    pdf = PdfWriter()
    pdf.add_blank_page(width=100, height=100)
    output = BytesIO()
    pdf.write(output)
    return studio.create_batch(
        ImportBatchCommand(
            title="synthetic-alpha-only", owner_id="alpha",
            rights_basis="original", rights_acknowledged=True,
            rights_statement="项目自建空白测试文档",
        ),
        [("synthetic.pdf", output.getvalue())],
    ).batch


@pytest.mark.parametrize("operation", ["status", "login", "logout", "profile", "export", "denied", "invalid"])
def test_private_http_responses_are_not_storable(beta_lifecycle, operation):
    clients = beta_lifecycle[0]
    client = clients["alpha"]
    if operation == "login":
        response = client.post("/api/v1/beta-session", json={"access_code": "synthetic-alpha"})
        assert "httponly" in response.headers["set-cookie"].lower()
    elif operation == "logout":
        response = client.delete("/api/v1/beta-session")
    elif operation == "denied":
        response = clients["anonymous"].get("/api/v1/teacher-memory/profile")
        assert response.status_code == 401
    elif operation == "invalid":
        response = client.post("/api/v1/beta-session", json={})
        assert response.status_code == 422
    else:
        path = "/beta-session" if operation == "status" else f"/teacher-memory/{operation}"
        response = client.get(f"/api/v1{path}")
        assert response.status_code == 200
    directives = response.headers.get("cache-control", "").split(", ")
    assert "private" in directives
    assert "no-store" in directives


@pytest.mark.parametrize("user", ["anonymous", "alpha", "beta"])
def test_beta_old_model_dashboard_denied_before_global_storage(beta_lifecycle, monkeypatch, user):
    def forbidden():
        raise AssertionError("Global operations storage must not be opened in Beta")

    monkeypatch.setattr(model_routes, "get_model_operations_registry", forbidden)
    response = beta_lifecycle[0][user].get("/api/v1/admin/model-operations")
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "LEGACY_WORKFLOW_UNAVAILABLE"


@pytest.mark.parametrize("operation", ["list", "download", "trash"])
def test_beta_legacy_imports_do_not_expose_or_modify_another_owner(beta_lifecycle, operation):
    clients, _, _, _, studio = beta_lifecycle
    batch = _synthetic_import(studio)
    client = clients["beta"]
    if operation == "list":
        response = client.get("/api/v1/imports")
    elif operation == "download":
        response = client.get(f"/api/v1/imports/files/{batch.files[0].file_id}/source")
    else:
        response = client.post(
            f"/api/v1/imports/batches/{batch.batch_id}/lifecycle", json={"action": "trash"},
        )
    assert response.status_code == 403
    assert "synthetic-alpha-only" not in response.text
    assert studio.workspace().batches[0].lifecycle_state == "active"


def test_beta_legacy_paper_composer_cannot_read_unscoped_private_bank(beta_lifecycle, monkeypatch):
    from app.modules.exam_papers import ExamPaperComposer
    from tests.test_exam_paper_composer import ComposerQuestionBank

    bank = ComposerQuestionBank()  # Synthetic private questions, no production stores.
    monkeypatch.setattr(paper_routes, "get_exam_paper_composer", lambda: ExamPaperComposer(bank))
    response = beta_lifecycle[0]["beta"].post("/api/v1/exam-papers/compose", json={
        "target_score": 10, "type_quotas": [{"question_type": "single_choice", "count": 2}],
    })
    assert response.status_code == 403
    assert "教师自有题库" not in response.text


@pytest.mark.parametrize("method,path", [
    ("POST", ""), ("POST", "/compose"), ("POST", "/compose-template"), ("PUT", "/synthetic"),
])
def test_beta_legacy_paper_writes_stop_before_storage(beta_lifecycle, monkeypatch, method, path):
    def forbidden():
        raise AssertionError("Legacy paper stores must not be opened in Beta")
    monkeypatch.setattr(paper_routes, "get_exam_paper_studio", forbidden)
    monkeypatch.setattr(paper_routes, "get_exam_paper_composer", forbidden)
    response = beta_lifecycle[0]["alpha"].request(method, f"/api/v1/exam-papers{path}", json={})
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "LEGACY_WORKFLOW_UNAVAILABLE"


def test_beta_memory_export_delete_is_bound_to_real_session(beta_lifecycle):
    clients, _, _, memory, _ = beta_lifecycle
    for owner, grade in (("alpha", "高一"), ("beta", "高三")):
        assert clients[owner].post("/api/v1/teacher-memory/profile", json={
            "operation": "upsert", "key": "default_grade", "value": grade,
        }).status_code == 200
    alpha = clients["alpha"]
    exported = alpha.get("/api/v1/teacher-memory/export", params={"owner_id": "beta"})
    assert exported.status_code == 200
    assert exported.json()["preferences"][0]["value"] == "高一"
    assert alpha.post("/api/v1/teacher-memory/profile", json={
        "operation": "delete_all", "confirmation": "删除全部教师记忆", "owner_id": "beta",
    }).status_code == 422
    assert alpha.post("/api/v1/teacher-memory/profile", json={
        "operation": "delete_all", "confirmation": "delete",
    }).status_code == 422
    removed = alpha.post("/api/v1/teacher-memory/profile", json={
        "operation": "delete_all", "confirmation": "删除全部教师记忆",
        "expected_version": exported.json()["version"],
    })
    assert removed.status_code == 200
    reopened = TeacherMemory(database_path=memory.database_path)
    assert reopened.profile(owner_id="alpha").preferences == []
    assert reopened.profile(owner_id="alpha").auto_learning_enabled is False
    assert reopened.profile(owner_id="beta").preferences[0].value == "高三"
    assert clients["beta"].get("/api/v1/teacher-memory/export").json()["preferences"][0]["value"] == "高三"


@pytest.mark.parametrize("state", ["anonymous", "expired", "revoked"])
@pytest.mark.parametrize("operation", ["export", "delete"])
def test_beta_invalid_sessions_cannot_export_or_delete(beta_lifecycle, state, operation):
    clients, settings, now, memory, _ = beta_lifecycle
    client = clients["anonymous"] if state == "anonymous" else clients["alpha"]
    if state == "expired":
        now[0] += timedelta(hours=2)
    elif state == "revoked":
        token = client.cookies.get(settings.beta_session_cookie_name)
        assert client.delete("/api/v1/beta-session").status_code == 200
        client.cookies.set(settings.beta_session_cookie_name, token)
    before = memory.profile(owner_id="alpha")
    if operation == "export":
        response = client.get("/api/v1/teacher-memory/export")
    else:
        response = client.post("/api/v1/teacher-memory/profile", json={
            "operation": "delete_all", "confirmation": "删除全部教师记忆",
        })
    assert response.status_code == 401
    assert memory.profile(owner_id="alpha") == before


@pytest.mark.parametrize("method,path", [
    ("GET", ""),
    ("GET", "/synthetic-plan"),
    ("GET", "/synthetic-plan/export"),
    ("POST", "/generate"),
    ("POST", "/synthetic-plan/lifecycle"),
    ("PATCH", "/synthetic-plan"),
    ("PUT", "/synthetic-plan/blocks/teaching_flow/lock"),
    ("POST", "/synthetic-plan/blocks/teaching_flow/rewrite"),
])
def test_beta_legacy_lessons_stop_before_storage_or_model(beta_lifecycle, monkeypatch, method, path):
    def forbidden():
        raise AssertionError("Legacy storage/provider must not be opened in Closed Beta")

    monkeypatch.setattr(lesson_routes, "get_lesson_plan_studio", forbidden)
    monkeypatch.setattr(lesson_routes, "get_lesson_plan_renderer", forbidden)
    response = beta_lifecycle[0]["alpha"].request(method, f"/api/v1/lesson-plans{path}", json={})
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "LEGACY_WORKFLOW_UNAVAILABLE"


def test_beta_supported_lesson_history_remains_available(beta_lifecycle, monkeypatch, tmp_path):
    # Reading an empty saved history does not need drafting or any provider.
    versioning = LessonVersioning(database_path=tmp_path / "lesson.sqlite3", drafting=None)  # type: ignore[arg-type]
    monkeypatch.setitem(app.dependency_overrides, lesson_routes.get_lesson_versioning, lambda: versioning)
    response = beta_lifecycle[0]["alpha"].get("/api/v1/lesson-plans/versions/history")
    assert response.status_code == 200
    assert response.json()["items"] == []


@pytest.mark.parametrize("method,path", [
    ("GET", "/questions"),
    ("GET", "/questions/synthetic"),
    ("GET", "/questions/synthetic/images/synthetic/content"),
    ("GET", "/question-bank/stats"),
    ("PATCH", "/questions/synthetic"),
    ("POST", "/questions/synthetic/publish"),
    ("POST", "/questions/synthetic/review"),
    ("DELETE", "/questions/synthetic/images/synthetic"),
    ("GET", "/question-similarity"),
    ("POST", "/question-similarity/scan"),
    ("POST", "/solutions/solve"),
])
def test_beta_other_legacy_entrypoints_stop_before_dependencies(beta_lifecycle, monkeypatch, method, path):
    def forbidden():
        raise AssertionError("Legacy dependency must not access storage or model in Closed Beta")

    monkeypatch.setattr(question_routes, "get_question_bank", forbidden)
    monkeypatch.setattr(solution_routes, "get_solution_assistant", forbidden)
    monkeypatch.setitem(app.dependency_overrides, similarity_routes.get_question_similarity_registry, forbidden)
    response = beta_lifecycle[0]["alpha"].request(method, "/api/v1" + path, json={})
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "LEGACY_WORKFLOW_UNAVAILABLE"


def test_local_legacy_imports_remain_available(beta_lifecycle):
    clients, settings, _, _, studio = beta_lifecycle
    batch = _synthetic_import(studio)
    settings.beta_access_enabled = False
    response = clients["anonymous"].get("/api/v1/imports")
    assert response.status_code == 200
    assert response.json()["batches"][0]["batch_id"] == batch.batch_id


def test_beta_library_recycle_is_owner_scoped_and_not_permanent_erasure(beta_lifecycle, monkeypatch, tmp_path):
    clients = beta_lifecycle[0]
    library = PrivateLibrary(tmp_path / "library.sqlite3", tmp_path / "library-files")
    monkeypatch.setattr(library_routes, "get_private_library", lambda: library)
    document = Document()
    document.add_paragraph("项目自建测试：求函数 f(x)=x 的值。")
    output = BytesIO()
    document.save(output)
    item = library.ingest(
        LibraryIngestCommand(title="synthetic-alpha-document", owner_id="alpha"),
        filename="synthetic.docx", content=output.getvalue(),
    )
    path = f"/api/v1/library/{item.library_item_id}"
    for suffix in ("", "/file", "/revisions"):
        assert clients["beta"].get(path + suffix).status_code == 404
    assert clients["beta"].post(path + "/lifecycle", json={"action": "trash"}).status_code == 404
    assert clients["alpha"].get(path + "/file").content == output.getvalue()
    trashed = clients["alpha"].post(path + "/lifecycle", json={"action": "trash"})
    assert trashed.status_code == 200
    assert trashed.json()["lifecycle_state"] == "trashed"
    reopened = PrivateLibrary(library.database_path, library.file_root)
    stored_path, retained = reopened.file_for_download(item.library_item_id, owner_id="alpha")
    assert retained.lifecycle_state == "trashed"
    assert stored_path.read_bytes() == output.getvalue()
    assert clients["beta"].post(path + "/lifecycle", json={"action": "restore"}).status_code == 404
    restored = clients["alpha"].post(path + "/lifecycle", json={"action": "restore"})
    assert restored.status_code == 200
    assert restored.json()["lifecycle_state"] == "active"


def test_beta_private_question_export_and_permanent_deletion(beta_lifecycle, monkeypatch, tmp_path):
    clients = beta_lifecycle[0]
    library = PersonalQuestionLibrary(tmp_path / "personal.sqlite3")
    monkeypatch.setitem(app.dependency_overrides, get_personal_question_library, lambda: library)
    questions = {}
    for owner in ("alpha", "beta"):
        collection = library.create_collection(PersonalCollectionCreate(name="合成测试题库"), owner_id=owner)
        category = library.create_category(
            collection.collection_id, PersonalCategoryCreate(name="合成测试"), owner_id=owner,
        )
        draft = QuestionAuthoring.preserve_approved_statement(
            QuestionAuthoringStatementPreview(
                question_type="fill_blank", stem_plain=f"合成测试 {owner}：求函数 f(x)=x 在 x=1 的值。",
                estimated_difficulty=1,
            ),
            request_text="项目自建的删除演练题面", target_difficulty=1,
        )
        library.stage_generated_draft(draft, owner_id=owner)
        questions[owner] = library.save_authoring_draft(
            draft.draft_id,
            PersonalQuestionSave(
                expected_revision=1, collection_id=collection.collection_id,
                category_id=category.category_id, name=f"synthetic-{owner}-question",
            ), owner_id=owner,
        )
    question = questions["alpha"]
    path = f"/api/v1/personal-question-library/questions/{question.question_id}"
    exported = clients["alpha"].get(path + "/export?format=json")
    assert exported.status_code == 200
    assert exported.headers["cache-control"] == "private, no-store"
    assert exported.json()["question"]["answer_value"] == "无"
    assert clients["beta"].get(path + "/export?format=json").status_code == 404
    assert clients["beta"].post(path + "/trash", json={"expected_updated_at": question.updated_at}).status_code == 404
    trashed = clients["alpha"].post(path + "/trash", json={"expected_updated_at": question.updated_at})
    assert trashed.status_code == 200
    command = {"expected_updated_at": trashed.json()["updated_at"], "confirmation": "永久删除我的私题"}
    assert clients["beta"].request("DELETE", path, json=command).status_code == 404
    assert clients["anonymous"].request("DELETE", path, json=command).status_code == 401
    assert clients["alpha"].request("DELETE", path, json={**command, "expected_updated_at": "stale"}).status_code == 409
    removed = clients["alpha"].request("DELETE", path, json=command)
    assert removed.status_code == 200
    assert removed.json()["active_storage_deleted"] is True
    reopened = PersonalQuestionLibrary(library.database_path)
    with pytest.raises(KeyError):
        reopened.get_question(question.question_id, owner_id="alpha")
    with pytest.raises(KeyError):
        reopened.get_authoring_draft(question.source_draft_id, owner_id="alpha")
    assert reopened.get_question(questions["beta"].question_id, owner_id="beta") == questions["beta"]
    assert clients["alpha"].get(path + "/export?format=json").status_code == 404
    assert clients["alpha"].post(path + "/restore", json={"expected_updated_at": command["expected_updated_at"]}).status_code == 404
