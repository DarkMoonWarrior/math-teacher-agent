"""Known object IDs cannot bypass real Beta cookies or trigger private work."""
from io import BytesIO
from threading import Lock
from types import SimpleNamespace
from datetime import UTC, datetime, timedelta
import stat
import time

import pytest
from docx import Document

from app.main import app
from app.core.deletion import is_link_or_reparse
from app.modules.data_lifecycle import OwnerDeletionLedger
from app.modules.private_library import LibraryIngestCommand, PrivateLibrary
from app.modules.private_library.exports import LibraryTextRenderer
from app.modules.private_library.schemas import LibraryTextReviewCommand, QuestionCandidateUpdate
from app.modules.background_jobs import BackgroundJobRegistry
from app.modules.exam_papers.versioning import PaperSavedExporting
from app.modules.lesson_plans import LessonVersioning, LessonVersionSaveCommand, LessonSavedExporting
from app.routes import library as library_routes
from app.routes import exam_papers as paper_routes
from app.routes import lesson_plans as lesson_routes
from app.routes.question_capture import get_question_capture
from tests.test_beta_lifecycle import beta_lifecycle
from tests.test_question_capture import (
    FakeRecognitionProvider, command, image_bytes, make_recognition_capture,
)
from tests.test_exam_papers import make_studio, create_command
from tests.test_lesson_drafting import _complete_lesson_draft


def _forbidden_work(*args, **kwargs):
    raise AssertionError("Foreign object IDs must be rejected before source resolution or rendering")


def test_destructive_io_rejects_windows_reparse_points():
    synthetic_path = SimpleNamespace(
        lstat=lambda: SimpleNamespace(st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT),
        is_symlink=lambda: False,
    )
    assert is_link_or_reparse(synthetic_path)


@pytest.fixture
def owned_library(beta_lifecycle, tmp_path, monkeypatch):
    library = PrivateLibrary(tmp_path / "library.sqlite3", tmp_path / "library-files")
    monkeypatch.setattr(library_routes, "get_private_library", lambda: library)
    document = Document()
    document.add_paragraph("synthetic-alpha-only：已知函数 f(x)=x，求 f(1)。")
    output = BytesIO()
    document.save(output)
    item = library.ingest(
        LibraryIngestCommand(title="synthetic-alpha-only", owner_id="alpha"),
        filename="synthetic.docx", content=output.getvalue(),
    )
    return beta_lifecycle[0], library, item, output.getvalue()


@pytest.mark.parametrize("method,suffix,payload", [
    ("GET", "", None),
    ("GET", "/file", None),
    ("GET", "/revisions", None),
    ("GET", "/export?format=docx", None),
    ("PATCH", "/review", {"corrected_text": "foreign edit", "confirm": True}),
    ("POST", "/lifecycle", {"action": "trash", "actor_id": "alpha"}),
    ("POST", "/ocr", {"external_processing_consent": True}),
    ("POST", "/local-math-ocr", None),
    ("POST", "/ocr/jobs", {"external_processing_consent": True}),
    ("POST", "/local-math-ocr/jobs", None),
    ("POST", "/ai-repair", {"draft_text": "synthetic", "external_processing_consent": True}),
    ("POST", "/ai-repair/jobs", {"draft_text": "synthetic", "external_processing_consent": True}),
    ("POST", "/send-to-structured-import", None),
    ("GET", "/question-candidates", None),
    ("POST", "/question-candidates", {"external_processing_consent": True}),
])
def test_foreign_library_id_is_rejected_before_any_provider_or_export(
    owned_library, monkeypatch, method, suffix, payload,
):
    clients, library, item, original = owned_library
    provider_calls = []

    def unavailable():
        provider_calls.append(True)
        raise RuntimeError("synthetic provider unavailable")

    for name in (
        "get_library_ocr_provider", "get_local_math_ocr_provider",
        "get_library_ai_repair_client", "get_library_question_extraction_client",
        "get_library_text_renderer", "get_pdf_import_studio",
    ):
        monkeypatch.setattr(library_routes, name, unavailable)
    path = f"/api/v1/library/{item.library_item_id}"
    response = clients["beta"].request(method, path + suffix, json=payload)
    assert response.status_code == 404, response.text
    assert provider_calls == []
    assert "synthetic-alpha-only" not in response.text
    assert response.headers["cache-control"] == "private, no-store"
    assert library.get(item.library_item_id, owner_id="alpha") == item
    assert clients["alpha"].get(path + "/file").content == original


def test_foreign_library_id_is_rejected_even_when_local_ocr_is_busy(owned_library, monkeypatch):
    clients, _, item, _ = owned_library
    lock = Lock()
    monkeypatch.setattr(library_routes, "_local_math_ocr_lock", lock)
    with lock:
        response = clients["beta"].post(f"/api/v1/library/{item.library_item_id}/local-math-ocr")
    assert response.status_code == 404


def test_owner_permanent_delete_library_requires_trash_and_fresh_confirmation(owned_library):
    clients, library, item, _ = owned_library
    path = f"/api/v1/library/{item.library_item_id}"
    payload = {
        "expected_updated_at": item.updated_at,
        "confirmation": "永久删除我选择的内容",
    }
    assert clients["anonymous"].request("DELETE", path, json=payload).status_code == 401
    assert clients["beta"].request("DELETE", path, json=payload).status_code == 404
    assert clients["alpha"].request("DELETE", path, json={
        **payload, "confirmation": "删除",
    }).status_code == 422
    assert clients["alpha"].request("DELETE", path, json=payload).status_code == 409
    ledger = OwnerDeletionLedger(library.database_path.parent / "owner-deletions.sqlite3")
    assert ledger.list() == ()
    trashed = clients["alpha"].post(path + "/lifecycle", json={"action": "trash"}).json()
    assert clients["alpha"].request("DELETE", path, json=payload).status_code == 409
    assert ledger.list() == ()
    deleted = clients["alpha"].request("DELETE", path, json={
        **payload, "expected_updated_at": trashed["updated_at"],
    })
    assert deleted.status_code == 200
    assert deleted.json()["independent_snapshots_preserved"] is True
    with pytest.raises(KeyError):
        library.get(item.library_item_id, owner_id="alpha")
    assert not any(library.file_root.iterdir())


def test_library_export_file_is_removed_after_response_streams(owned_library, tmp_path, monkeypatch):
    clients, library, item, _ = owned_library
    library.review(
        item.library_item_id,
        LibraryTextReviewCommand(corrected_text="合成校对文本：已知 f(x)=x。", confirm=True),
        owner_id="alpha",
        reviewer_id="alpha",
    )
    output_root = tmp_path / "ephemeral-exports"
    monkeypatch.setattr(library_routes, "get_library_text_renderer", lambda: LibraryTextRenderer(output_root))
    monkeypatch.setattr(
        library_routes,
        "get_settings",
        lambda: SimpleNamespace(lesson_export_dir=output_root),
    )
    response = clients["alpha"].get(f"/api/v1/library/{item.library_item_id}/export?format=docx")
    assert response.status_code == 200
    assert response.content.startswith(b"PK")
    assert not list(output_root.rglob("*.docx"))


@pytest.mark.parametrize("operation", ["edit", "discard", "import"])
@pytest.mark.parametrize("parent", ["foreign", "own"])
def test_candidate_id_cannot_be_used_with_foreign_or_substituted_parent(owned_library, monkeypatch, operation, parent):
    clients, library, item, original = owned_library
    library.review(item.library_item_id, LibraryTextReviewCommand(corrected_text="合成题目", confirm=True),
                   owner_id="alpha", reviewer_id="alpha")
    candidate = library.propose_questions(item.library_item_id, owner_id="alpha", structured_questions=[
        (QuestionCandidateUpdate(question_type="fill_blank", stem_plain="合成题目：求 f(1)。"), []),
    ]).items[0]
    own = library.ingest(LibraryIngestCommand(owner_id="beta"), filename="synthetic.docx", content=original)
    item_id = item.library_item_id if parent == "foreign" else own.library_item_id
    path = f"/api/v1/library/{item_id}/question-candidates/{candidate.candidate_id}"
    monkeypatch.setattr(library_routes, "get_library_question_bank", _forbidden_work)
    if operation == "edit":
        response = clients["beta"].patch(path, json={"question_type": "fill_blank", "stem_plain": "foreign edit"})
    elif operation == "discard":
        response = clients["beta"].delete(path)
    else:
        response = clients["beta"].post(path + "/import")
    assert response.status_code == 404, response.text
    assert library.get_question_candidate(item.library_item_id, candidate.candidate_id, owner_id="alpha")[0] == candidate


def test_background_library_job_is_visible_only_to_its_cookie_owner(beta_lifecycle, monkeypatch):
    registry = BackgroundJobRegistry()
    monkeypatch.setattr(library_routes, "_background_jobs", registry)
    job = registry.start(kind="external_ocr", subject_id="synthetic-alpha-only", owner_id="alpha",
                         runner=lambda progress: {"text": "synthetic private result"})
    path = f"/api/v1/library/jobs/{job.job_id}"
    clients = beta_lifecycle[0]
    assert clients["beta"].get(path).status_code == 404
    assert clients["anonymous"].get(path).status_code == 401
    response = clients["alpha"].get(path)
    assert response.status_code == 200
    assert response.json()["subject_id"] == "synthetic-alpha-only"
    assert "owner_id" not in response.json()


def test_completed_background_job_metadata_expires_after_24_hours():
    now = [datetime(2026, 9, 5, tzinfo=UTC)]
    registry = BackgroundJobRegistry(clock=lambda: now[0])
    job = registry.start(
        kind="synthetic",
        subject_id="synthetic-subject",
        owner_id="alpha",
        runner=lambda progress: {"complete": True},
    )
    for _ in range(100):
        current = registry.get(job.job_id, owner_id="alpha")
        if current.status == "succeeded":
            break
        time.sleep(0.01)
    assert current.status == "succeeded"
    now[0] += timedelta(hours=25)
    assert registry.list(owner_id="alpha") == []
    with pytest.raises(KeyError):
        registry.get(job.job_id, owner_id="alpha")


@pytest.mark.parametrize("method,suffix,payload", [
    ("GET", "", None),
    ("GET", "/content", None),
    ("GET", "/content?revision=1", None),
    ("POST", "/transform", {"operation": "rotate", "degrees": 90}),
    ("POST", "/recognize", {"mode": "external", "external_processing_consent": True}),
    ("PATCH", "/recognition", {"stem_plain": "foreign edit", "confirm": True}),
])
def test_foreign_capture_id_cannot_read_change_or_recognize(
    beta_lifecycle, tmp_path, monkeypatch, method, suffix, payload,
):
    clients = beta_lifecycle[0]
    provider = FakeRecognitionProvider()
    capture = make_recognition_capture(tmp_path, external=provider)
    monkeypatch.setitem(app.dependency_overrides, get_question_capture, lambda: capture)
    original = image_bytes()
    bundle = capture.prepare(command(owner_id="alpha"), filename="synthetic.png", content=original)
    path = f"/api/v1/question-capture/assets/{bundle.asset.asset_id}"
    response = clients["beta"].request(method, path + suffix, json=payload)
    assert response.status_code == 404, response.text
    assert provider.calls == []
    assert capture.get(bundle.asset.asset_id, owner_id="alpha") == bundle
    assert clients["alpha"].get(path + "/content?revision=1").content == original


def test_owner_permanent_delete_capture_removes_all_media_revisions(beta_lifecycle, tmp_path, monkeypatch):
    clients = beta_lifecycle[0]
    capture = make_recognition_capture(tmp_path, external=FakeRecognitionProvider())
    monkeypatch.setitem(app.dependency_overrides, get_question_capture, lambda: capture)
    bundle = capture.prepare(command(owner_id="alpha"), filename="synthetic.png", content=image_bytes())
    path = f"/api/v1/question-capture/assets/{bundle.asset.asset_id}"
    transformed = clients["alpha"].post(
        path + "/transform",
        json={"operation": "rotate", "degrees": 90},
    ).json()
    payload = {
        "expected_updated_at": bundle.asset.updated_at,
        "confirmation": "永久删除我选择的内容",
    }
    assert clients["beta"].request("DELETE", path, json=payload).status_code == 404
    assert clients["alpha"].request("DELETE", path, json=payload).status_code == 409
    deleted = clients["alpha"].request("DELETE", path, json={
        **payload, "expected_updated_at": transformed["asset"]["updated_at"],
    })
    assert deleted.status_code == 200
    with pytest.raises(KeyError):
        capture.get(bundle.asset.asset_id, owner_id="alpha")
    assert not any(capture.file_root.iterdir())


@pytest.mark.parametrize("operation", ["read", "export", "version-export", "trash", "restore", "revise", "add-question"])
def test_foreign_paper_id_cannot_read_export_or_revise(beta_lifecycle, tmp_path, monkeypatch, operation):
    clients = beta_lifecycle[0]
    studio, _ = make_studio(tmp_path)
    original = studio.create(create_command().model_copy(update={"teacher_id": "alpha"}))
    monkeypatch.setattr(paper_routes, "get_exam_paper_studio", lambda: studio)
    monkeypatch.setattr(paper_routes, "get_exam_paper_renderer", _forbidden_work)
    monkeypatch.setattr(paper_routes, "get_paper_blueprint_selection", _forbidden_work)
    exporting = PaperSavedExporting(studio=studio, renderer=SimpleNamespace(render=_forbidden_work))
    monkeypatch.setitem(app.dependency_overrides, paper_routes.get_paper_saved_exporting, lambda: exporting)
    path = f"/api/v1/exam-papers/{original.exam_paper_id}"
    if operation in {"trash", "restore"}:
        response = clients["beta"].post(path + "/lifecycle", json={"action": operation})
    elif operation in {"revise", "add-question"}:
        response = clients["beta"].put(path + "/history-revision", json={
            "expected_version": 1, "title": "foreign edit", "duration_minutes": 45,
            "instructions": "", "items": [{"question_id": "q1", "section_title": "选择题", "score": 5}],
            "selected_private_question_ids": ["synthetic-other"] if operation == "add-question" else [],
        })
    else:
        suffix = {"read": "", "export": "/export", "version-export": "/versions/1/export"}[operation]
        response = clients["beta"].get(path + suffix)
    assert response.status_code == 404, response.text
    assert studio.get_owned(original.exam_paper_id, owner_id="alpha") == original
    assert clients["alpha"].get(path).status_code == 200
    assert clients["beta"].get("/api/v1/exam-papers").json()["total"] == 0


def test_owner_permanent_delete_paper_preserves_other_snapshot(beta_lifecycle, tmp_path, monkeypatch):
    clients = beta_lifecycle[0]
    studio, _ = make_studio(tmp_path)
    target = studio.create(create_command().model_copy(update={"teacher_id": "alpha"}))
    preserved = studio.create(create_command().model_copy(update={"teacher_id": "alpha", "title": "independent"}))
    target_assets = studio.asset_root / target.exam_paper_id
    target_assets.mkdir(exist_ok=True)
    (target_assets / "synthetic.png").write_bytes(b"synthetic asset")
    preserved_assets = studio.asset_root / preserved.exam_paper_id
    preserved_assets.mkdir(exist_ok=True)
    (preserved_assets / "preserved.png").write_bytes(b"preserved asset")
    monkeypatch.setattr(paper_routes, "get_exam_paper_studio", lambda: studio)
    path = f"/api/v1/exam-papers/{target.exam_paper_id}"
    payload = {
        "expected_updated_at": target.updated_at,
        "confirmation": "永久删除我选择的内容",
    }
    assert clients["beta"].request("DELETE", path, json=payload).status_code == 404
    assert clients["alpha"].request("DELETE", path, json=payload).status_code == 409
    trashed = clients["alpha"].post(path + "/lifecycle", json={"action": "trash"}).json()
    deleted = clients["alpha"].request("DELETE", path, json={
        **payload, "expected_updated_at": trashed["updated_at"],
    })
    assert deleted.status_code == 200
    with pytest.raises(KeyError):
        studio.get_owned(target.exam_paper_id, owner_id="alpha")
    assert not target_assets.exists()
    assert (preserved_assets / "preserved.png").read_bytes() == b"preserved asset"
    assert studio.get_owned(preserved.exam_paper_id, owner_id="alpha").title == "independent"


@pytest.mark.parametrize("operation", ["read", "old-version", "export", "trash", "restore", "save-version"])
def test_foreign_lesson_id_cannot_read_export_or_save(beta_lifecycle, tmp_path, monkeypatch, operation):
    clients = beta_lifecycle[0]
    drafting, draft = _complete_lesson_draft()
    # The reusable synthetic source fixture has a fixed teacher-a assertion;
    # preserve its real source validation while binding this seed to alpha.
    select = drafting.source_selection.select
    monkeypatch.setattr(drafting.source_selection, "select", lambda command, owner_id: select(command, owner_id="teacher-a"))
    versioning = LessonVersioning(database_path=tmp_path / "lessons.sqlite3", drafting=drafting)
    original = versioning.save(LessonVersionSaveCommand(draft=draft, confirmed=True), owner_id="alpha")
    monkeypatch.setattr(drafting, "build", _forbidden_work)
    exporting = LessonSavedExporting(versioning=versioning, renderer=SimpleNamespace(render=_forbidden_work))
    monkeypatch.setitem(app.dependency_overrides, lesson_routes.get_lesson_versioning, lambda: versioning)
    monkeypatch.setitem(app.dependency_overrides, lesson_routes.get_lesson_saved_exporting, lambda: exporting)
    path = f"/api/v1/lesson-plans/versions/{original.lesson_plan_id}"
    if operation in {"trash", "restore"}:
        response = clients["beta"].post(path + "/lifecycle", json={"action": operation})
    elif operation == "save-version":
        response = clients["beta"].post("/api/v1/lesson-plans/versions/save", json={
            "draft": draft.model_dump(mode="json"), "confirmed": True, "lesson_plan_id": original.lesson_plan_id,
        })
    else:
        suffix = {"read": "", "old-version": "?version=1", "export": "/export?version=1&format=docx"}[operation]
        response = clients["beta"].get(path + suffix)
    assert response.status_code == 404, response.text
    assert versioning.get(original.lesson_plan_id, owner_id="alpha") == original
    assert clients["alpha"].get(path).status_code == 200
    assert clients["beta"].get("/api/v1/lesson-plans/versions/history").json()["total"] == 0


def test_owner_permanent_delete_lesson_preserves_other_snapshot(beta_lifecycle, tmp_path, monkeypatch):
    clients = beta_lifecycle[0]
    drafting, draft = _complete_lesson_draft()
    select = drafting.source_selection.select
    monkeypatch.setattr(
        drafting.source_selection,
        "select",
        lambda command, owner_id: select(command, owner_id="teacher-a"),
    )
    versioning = LessonVersioning(database_path=tmp_path / "lessons.sqlite3", drafting=drafting)
    target = versioning.save(LessonVersionSaveCommand(draft=draft, confirmed=True), owner_id="alpha")
    preserved = versioning.save(LessonVersionSaveCommand(draft=draft, confirmed=True), owner_id="alpha")
    monkeypatch.setitem(app.dependency_overrides, lesson_routes.get_lesson_versioning, lambda: versioning)
    path = f"/api/v1/lesson-plans/versions/{target.lesson_plan_id}"
    current = versioning.list(owner_id="alpha").items
    target_updated_at = next(
        item.updated_at for item in current if item.lesson_plan_id == target.lesson_plan_id
    )
    payload = {
        "expected_updated_at": target_updated_at,
        "confirmation": "永久删除我选择的内容",
    }
    assert clients["beta"].request("DELETE", path, json=payload).status_code == 404
    assert clients["alpha"].request("DELETE", path, json=payload).status_code == 409
    trashed = clients["alpha"].post(path + "/lifecycle", json={"action": "trash"}).json()
    deleted = clients["alpha"].request("DELETE", path, json={
        **payload, "expected_updated_at": trashed["updated_at"],
    })
    assert deleted.status_code == 200
    with pytest.raises(KeyError):
        versioning.get(target.lesson_plan_id, owner_id="alpha")
    assert versioning.get(preserved.lesson_plan_id, owner_id="alpha").lesson_plan_id == preserved.lesson_plan_id
