from io import BytesIO
from pathlib import Path

import pytest
from docx import Document
from fastapi.testclient import TestClient
from PIL import Image
from reportlab.pdfgen.canvas import Canvas

from app.core.identity import CurrentTeacher, get_current_teacher
from app.main import app
from app.modules.background_jobs import BackgroundJobRegistry
from app.modules.private_library import (
    LibraryIngestCommand,
    LibraryLifecycleCommand,
    LibraryOCRCommand,
    LibraryTextReviewCommand,
    OCRTextResult,
    OpenAIResourceOCRProvider,
    PrivateLibrary,
    PrivateLibraryError,
    QuestionCandidateCurriculum,
    QuestionCandidateUpdate,
)
from app.modules.question_bank import QuestionBank
from app.modules.private_library.exports import LibraryExportError, LibraryTextRenderer


def make_library(tmp_path: Path) -> PrivateLibrary:
    return PrivateLibrary(tmp_path / "library.sqlite3", tmp_path / "files")


def ingest_command(**updates) -> LibraryIngestCommand:
    values = {
        "title": "函数资料",
        "rights_basis": "private_teaching_only",
        "rights_statement": "本人确认该资料仅上传至私人空间用于日常教学。",
        "rights_acknowledged": True,
        "owner_id": "owner_teacher",
    }
    values.update(updates)
    return LibraryIngestCommand(**values)


def docx_bytes(text: str) -> bytes:
    document = Document()
    document.add_heading("高中数学讲义", level=1)
    document.add_paragraph(text)
    output = BytesIO()
    document.save(output)
    return output.getvalue()


def pdf_bytes(text: str) -> bytes:
    output = BytesIO()
    canvas = Canvas(output)
    canvas.drawString(72, 760, text)
    canvas.save()
    return output.getvalue()


def png_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (80, 60), "white").save(output, format="PNG")
    return output.getvalue()


def image_docx_bytes() -> bytes:
    document = Document()
    document.add_picture(BytesIO(png_bytes()))
    output = BytesIO()
    document.save(output)
    return output.getvalue()


def test_docx_is_extracted_but_remains_private(tmp_path: Path) -> None:
    library = make_library(tmp_path)

    item = library.ingest(
        ingest_command(),
        filename="函数讲义.docx",
        content=docx_bytes("函数单调性是本节课的核心内容。"),
    )

    assert item.file_kind == "docx"
    assert item.extraction_status == "extracted"
    assert "函数单调性" in item.extracted_text
    assert item.visibility == "private"
    assert not item.public_search_allowed
    assert not item.model_training_allowed
    assert not item.adaptation_allowed
    assert item.text_review_status == "pending"


def test_pdf_text_is_extracted_and_download_path_is_confined(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    item = library.ingest(
        ingest_command(rights_basis="original"),
        filename="lesson.pdf",
        content=pdf_bytes("Function monotonicity and x^2"),
    )

    assert item.extraction_status == "extracted"
    assert "Function monotonicity" in item.extracted_text
    assert item.page_count == 1
    assert item.adaptation_allowed
    path, downloaded = library.file_for_download(
        item.library_item_id, owner_id="owner_teacher"
    )
    assert path.parent == (tmp_path / "files").resolve()
    assert path.read_bytes().startswith(b"%PDF-")
    assert downloaded.original_filename == "lesson.pdf"


def test_corrected_math_text_exports_to_readable_docx_and_pdf(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    item = library.ingest(ingest_command(), filename="lesson.pdf", content=pdf_bytes("x^2"))
    reviewed = library.review(
        item.library_item_id,
        LibraryTextReviewCommand(
            corrected_text=r"函数 $f(x)=\frac{x^2}{2}$", confirm=True
        ),
        owner_id="owner_teacher",
        reviewer_id="owner_teacher",
    )
    renderer = LibraryTextRenderer(tmp_path / "output")
    docx = renderer.render(reviewed, "docx")
    pdf = renderer.render(reviewed, "pdf")
    assert docx.path.read_bytes().startswith(b"PK")
    assert pdf.path.read_bytes().startswith(b"%PDF")
    document = Document(docx.path)
    assert "x²/2" in "\n".join(p.text for p in document.paragraphs)


def test_unreadable_font_text_cannot_be_exported_before_ocr(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    unreadable = library.ingest(
        ingest_command(rights_basis="original"),
        filename="scan.png",
        content=png_bytes(),
    )

    with pytest.raises(LibraryExportError, match="OCR"):
        LibraryTextRenderer(tmp_path / "output").render(unreadable, "docx")


def test_local_ocr_audit_does_not_claim_external_consent(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    item = library.ingest(ingest_command(), filename="lesson.pdf", content=pdf_bytes("x^2"))

    class FakeLocalProvider:
        name = "local_math_ocr"
        def extract(self, **_kwargs):
            return OCRTextResult(text=r"函数 $f(x)=x^2$", warnings=[])

    library.apply_local_ocr(
        item.library_item_id,
        provider=FakeLocalProvider(),
        owner_id="owner_teacher",
        teacher_id="teacher",
    )
    import sqlite3
    with sqlite3.connect(tmp_path / "library.sqlite3") as connection:
        consent = connection.execute("SELECT external_consent FROM library_ocr_runs").fetchone()[0]
    assert consent == 0


def test_local_ocr_rejects_duplicate_long_running_job() -> None:
    from app.routes.library import _local_math_ocr_lock

    assert _local_math_ocr_lock.acquire(blocking=False)
    try:
        response = TestClient(app).post("/api/v1/library/any-item/local-math-ocr")
    finally:
        _local_math_ocr_lock.release()

    assert response.status_code == 409
    assert "正在处理" in response.json()["detail"]


def test_unreadable_pdf_font_text_cannot_be_falsely_confirmed(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    item = library.ingest(
        ingest_command(rights_basis="original"),
        filename="formula.pdf",
        content=pdf_bytes("Readable source page"),
    )

    with pytest.raises(PrivateLibraryError, match="不能确认"):
        library.review(
            item.library_item_id,
            LibraryTextReviewCommand(
                corrected_text="已知函数 f(\uf021)=\uf022，求 \uf023。", confirm=True
            ),
            owner_id="owner_teacher",
            reviewer_id="owner_teacher",
        )


def test_library_items_move_to_recycle_bin_and_restore(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    item = library.ingest(
        ingest_command(), filename="lesson.docx", content=docx_bytes("函数单调性")
    )

    trashed = library.change_lifecycle(
        item.library_item_id,
        LibraryLifecycleCommand(action="trash", reason="不再需要"),
        owner_id="owner_teacher",
    )
    assert trashed.lifecycle_state == "trashed"
    assert library.list(owner_id="owner_teacher").total == 0
    assert library.list(
        owner_id="owner_teacher", lifecycle_state="trashed"
    ).total == 1
    assert library.stats(owner_id="owner_teacher").trashed == 1

    restored = library.change_lifecycle(
        item.library_item_id,
        LibraryLifecycleCommand(action="restore"),
        owner_id="owner_teacher",
    )
    assert restored.lifecycle_state == "active"
    assert library.list(owner_id="owner_teacher").total == 1


def test_library_stats_are_scoped_to_the_current_owner(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    library.ingest(
        ingest_command(owner_id="owner_teacher"),
        filename="mine.docx",
        content=docx_bytes("函数单调性"),
    )
    library.ingest(
        ingest_command(owner_id="other_teacher"),
        filename="other.docx",
        content=docx_bytes("数列求和"),
    )

    mine = library.stats(owner_id="owner_teacher")
    other = library.stats(owner_id="other_teacher")

    assert mine.total == 1
    assert other.total == 1
    assert mine.by_file_kind == {"docx": 1}


def test_library_list_is_scoped_to_the_current_owner(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    mine = library.ingest(
        ingest_command(owner_id="owner_teacher", title="我的函数讲义"),
        filename="mine.docx",
        content=docx_bytes("函数单调性"),
    )
    library.ingest(
        ingest_command(owner_id="other_teacher", title="其他教师资料"),
        filename="other.docx",
        content=docx_bytes("数列求和"),
    )

    listing = library.list(owner_id="owner_teacher")

    assert listing.total == 1
    assert [item.library_item_id for item in listing.items] == [mine.library_item_id]


def test_library_http_uses_the_server_owner_for_list_upload_and_stats(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = make_library(tmp_path)
    library.ingest(
        ingest_command(owner_id="other_teacher", title="不可见资料"),
        filename="other.docx",
        content=docx_bytes("数列求和"),
    )
    monkeypatch.setattr("app.routes.library.get_private_library", lambda: library)
    client = TestClient(app)

    uploaded = client.post(
        "/api/v1/library",
        files={"file": ("mine.docx", docx_bytes("函数单调性"), "application/octet-stream")},
        data={
            "title": "我的函数讲义",
            "rights_basis": "private_teaching_only",
            "rights_statement": "本人确认该文件仅在私人空间用于教学备课。",
            "rights_acknowledged": "true",
            "owner_id": "other_teacher",
        },
    )
    listing = client.get("/api/v1/library")
    stats = client.get("/api/v1/library/stats")

    assert uploaded.status_code == 201
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["title"] == "我的函数讲义"
    assert stats.json()["total"] == 1
    assert library.list(owner_id="other_teacher").total == 1


def test_library_detail_review_file_and_revisions_fail_closed_across_owners(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = make_library(tmp_path)
    mine = library.ingest(
        ingest_command(title="我的函数资料"),
        filename="mine.docx",
        content=docx_bytes("函数的单调性"),
    )
    other = library.ingest(
        ingest_command(owner_id="other_teacher", title="其他教师资料"),
        filename="other.docx",
        content=docx_bytes("等差数列"),
    )
    monkeypatch.setattr("app.routes.library.get_private_library", lambda: library)
    client = TestClient(app)

    assert client.get(f"/api/v1/library/{mine.library_item_id}").status_code == 200
    assert client.get(f"/api/v1/library/{other.library_item_id}").status_code == 404
    assert client.get(f"/api/v1/library/{other.library_item_id}/file").status_code == 404
    assert client.get(f"/api/v1/library/{other.library_item_id}/revisions").status_code == 404
    assert client.patch(
        f"/api/v1/library/{other.library_item_id}/review",
        json={"corrected_text": "越权修改", "confirm": True},
    ).status_code == 404

    app.dependency_overrides[get_current_teacher] = lambda: CurrentTeacher(
        teacher_id="other_teacher", source="authenticated_session"
    )
    try:
        response = client.get(f"/api/v1/library/{other.library_item_id}")
        assert response.status_code == 200
        assert response.json()["title"] == "其他教师资料"
        assert client.get(f"/api/v1/library/{mine.library_item_id}").status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_teacher, None)


def test_library_public_commands_reject_model_or_browser_supplied_actor_ids() -> None:
    client = TestClient(app)

    review = client.patch(
        "/api/v1/library/any-item/review",
        json={
            "corrected_text": "函数题",
            "confirm": False,
            "reviewer_id": "other_teacher",
        },
    )
    ocr = client.post(
        "/api/v1/library/any-item/ocr",
        json={
            "external_processing_consent": True,
            "teacher_id": "other_teacher",
        },
    )

    assert review.status_code == 422
    assert ocr.status_code == 422


def test_revision_history_returns_only_the_owned_review_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = make_library(tmp_path)
    item = library.ingest(
        ingest_command(title="函数校对"),
        filename="lesson.docx",
        content=docx_bytes("函数 f(x)=x2"),
    )
    library.review(
        item.library_item_id,
        LibraryTextReviewCommand(
            corrected_text="函数 $f(x)=x^2$", note="修复公式", confirm=False
        ),
        owner_id="owner_teacher",
        reviewer_id="owner_teacher",
    )
    confirmed = library.review(
        item.library_item_id,
        LibraryTextReviewCommand(
            corrected_text="函数 $f(x)=x^2$", note="教师确认", confirm=True
        ),
        owner_id="owner_teacher",
        reviewer_id="owner_teacher",
    )
    monkeypatch.setattr("app.routes.library.get_private_library", lambda: library)

    response = TestClient(app).get(
        f"/api/v1/library/{item.library_item_id}/revisions"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["current_version"] == confirmed.version == 3
    assert [revision["version"] for revision in payload["items"]] == [3, 2]
    assert payload["items"][0]["review_status"] == "confirmed"
    assert "reviewer_id" not in payload["items"][0]


def test_background_jobs_are_visible_only_to_the_starting_owner() -> None:
    registry = BackgroundJobRegistry()
    job = registry.start(
        kind="synthetic",
        subject_id="lib_1",
        owner_id="owner_teacher",
        runner=lambda progress: {"ok": True},
    )

    assert registry.get(job.job_id, owner_id="owner_teacher").job_id == job.job_id
    with pytest.raises(KeyError):
        registry.get(job.job_id, owner_id="other_teacher")


def test_image_waits_for_ocr_then_can_be_manually_confirmed(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    item = library.ingest(
        ingest_command(title="立体几何题图"),
        filename="geometry.png",
        content=png_bytes(),
    )

    assert item.file_kind == "image"
    assert item.extraction_status == "needs_ocr"
    assert item.extracted_text == ""
    assert any("人工转录" in warning for warning in item.warnings)

    reviewed = library.review(
        item.library_item_id,
        LibraryTextReviewCommand(
            corrected_text="如图，在正方体 ABCD-A₁B₁C₁D₁ 中，求异面直线所成角。",
            note="教师根据原图完成转录",
            confirm=True,
        ),
        owner_id="owner_teacher",
        reviewer_id="owner_teacher",
    )

    assert reviewed.text_review_status == "confirmed"
    assert reviewed.version == 2
    assert "正方体" in reviewed.corrected_text


def test_rights_acknowledgement_and_duplicate_gate(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    content = docx_bytes("集合与常用逻辑用语")

    with pytest.raises(PrivateLibraryError, match="必须确认"):
        library.ingest(
            ingest_command(rights_acknowledged=False),
            filename="sets.docx",
            content=content,
        )

    first = library.ingest(ingest_command(), filename="sets.docx", content=content)
    with pytest.raises(PrivateLibraryError, match=first.library_item_id):
        library.ingest(ingest_command(), filename="copy.docx", content=content)


def test_invalid_file_is_rejected_without_writing(tmp_path: Path) -> None:
    library = make_library(tmp_path)

    with pytest.raises(PrivateLibraryError, match="不支持的文件格式"):
        library.ingest(
            ingest_command(), filename="payload.exe", content=b"not-a-real-file"
        )

    assert library.stats(owner_id="owner_teacher").total == 0
    assert list((tmp_path / "files").iterdir()) == []


def test_private_library_http_upload_review_and_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = make_library(tmp_path)
    monkeypatch.setattr("app.routes.library.get_private_library", lambda: library)
    client = TestClient(app)

    response = client.post(
        "/api/v1/library",
        files={
            "file": (
                "函数讲义.docx",
                docx_bytes("函数的奇偶性与对称性。"),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
        data={
            "title": "函数奇偶性",
            "rights_basis": "private_teaching_only",
            "rights_statement": "本人确认该文件仅在私人空间用于教学备课。",
            "rights_acknowledged": "true",
        },
    )

    assert response.status_code == 201
    item = response.json()
    assert item["visibility"] == "private"
    assert "函数的奇偶性" in item["extracted_text"]

    review = client.patch(
        f"/api/v1/library/{item['library_item_id']}/review",
        json={
            "corrected_text": "函数的奇偶性可以借助图象对称性理解。",
            "note": "完成首轮校对",
            "confirm": True,
        },
    )
    download = client.get(f"/api/v1/library/{item['library_item_id']}/file")
    listing = client.get("/api/v1/library")

    assert review.status_code == 200
    assert review.json()["text_review_status"] == "confirmed"
    assert download.status_code == 200
    assert download.content.startswith(b"PK")
    assert download.headers["content-disposition"].startswith("inline;")
    assert listing.status_code == 200
    assert listing.json()["total"] == 1


def test_library_ai_repair_requires_explicit_consent() -> None:
    response = TestClient(app).post(
        "/api/v1/library/any-item/ai-repair",
        json={
            "draft_text": "函数 f(x)=x2",
            "external_processing_consent": False,
        },
    )

    assert response.status_code == 422
    assert "DeepSeek" in response.json()["detail"]


def test_library_ai_repair_returns_editable_latex_without_saving(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = make_library(tmp_path)
    item = library.ingest(
        ingest_command(rights_basis="original"),
        filename="lesson.pdf",
        content=pdf_bytes("f(x)=x2"),
    )

    class FakeDeepSeekClient:
        def request(self, **kwargs):
            payload = kwargs["input_text"]
            assert "f(x)=x2" in payload
            return {
                "output": [{"content": [{"text": '{"repaired_text":"函数 $f(x)=x^2$","warnings":[]}'}]}]
            }

    monkeypatch.setattr("app.routes.library.get_private_library", lambda: library)
    monkeypatch.setattr(
        "app.routes.library.get_library_ai_repair_client", lambda: FakeDeepSeekClient()
    )
    client = TestClient(app)
    response = client.post(
        f"/api/v1/library/{item.library_item_id}/ai-repair",
        json={
            "draft_text": "函数 f(x)=x2",
            "external_processing_consent": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["repaired_text"] == "函数 $f(x)=x^2$"
    assert response.json()["provider"] == "deepseek"
    assert library.get(
        item.library_item_id, owner_id="owner_teacher"
    ).corrected_text == item.corrected_text


def test_long_latex_repair_draft_splits_on_page_boundaries() -> None:
    from app.routes.library import _split_latex_repair_draft

    draft = "".join(f"【第 {index} 页】\n" + ("题目内容" * 500) for index in range(1, 9))
    chunks = _split_latex_repair_draft(draft, max_chars=5000)

    assert len(chunks) > 1
    assert "".join(chunks) == draft
    assert all(len(chunk) <= 5000 for chunk in chunks)


def test_http_rejects_short_rights_statement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = make_library(tmp_path)
    monkeypatch.setattr("app.routes.library.get_private_library", lambda: library)
    client = TestClient(app)

    response = client.post(
        "/api/v1/library",
        files={"file": ("lesson.docx", docx_bytes("函数"), "application/octet-stream")},
        data={
            "rights_basis": "private_teaching_only",
            "rights_statement": "太短",
            "rights_acknowledged": "true",
        },
    )

    assert response.status_code == 422
    assert library.stats(owner_id="owner_teacher").total == 0


def confirmed_question_resource(library: PrivateLibrary):
    text = """1. 已知集合 A={1,2}，则下列正确的是（ ）
A. 1∈A B. 3∈A C. A=∅ D. 2∉A
答案：A
解析：由集合元素可知 1∈A。
2. 已知函数 f(x)=x^2，求 f(2)。
答案：4
解析：代入 x=2，得 f(2)=4。"""
    item = library.ingest(
        ingest_command(title="集合与函数例题", rights_basis="original"),
        filename="questions.docx",
        content=docx_bytes(text),
    )
    return library.review(
        item.library_item_id,
        LibraryTextReviewCommand(corrected_text=text, confirm=True),
        owner_id="owner_teacher",
        reviewer_id="owner_teacher",
    )


def map_candidate_to_collection_concepts(
    library: PrivateLibrary, item_id: str, candidate_id: str
):
    return library.map_question_candidate_curriculum(
        item_id,
        candidate_id,
        QuestionCandidateCurriculum(
            node_id="kp_r1_1_1_02",
            name="元素与集合的关系",
            volume="必修第一册",
            chapter="集合与常用逻辑用语",
            section="集合的概念",
        ),
        owner_id="owner_teacher",
        editor_id="owner_teacher",
    )


def test_confirmed_text_becomes_editable_question_candidates(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    item = confirmed_question_resource(library)

    proposed = library.propose_questions(
        item.library_item_id, owner_id="owner_teacher"
    )

    assert len(proposed.items) == 2
    assert proposed.items[0].question_type == "single_choice"
    assert [option.key for option in proposed.items[0].options] == ["A", "B", "C", "D"]
    assert proposed.items[0].answer_value == "A"
    assert proposed.items[1].answer_value == "4"

    updated = library.update_question_candidate(
        item.library_item_id,
        proposed.items[1].candidate_id,
        QuestionCandidateUpdate(**{
            **proposed.items[1].model_dump(include={
                "question_type", "stem_plain", "stem_latex", "options", "answer_value",
                "solution_method", "solution_steps", "final_answer", "difficulty",
            }),
            "stem_plain": "已知函数 f(x)=x²，求 f(3)。",
            "answer_value": "9",
            "final_answer": "9",
            "solution_steps": ["代入 x=3，得 f(3)=9。"],
        }),
        owner_id="owner_teacher",
        editor_id="owner_teacher",
    )
    assert updated.stem_plain.endswith("f(3)。")
    assert updated.answer_value == "9"


def test_question_candidates_require_confirmed_current_text_and_curriculum(
    tmp_path: Path,
) -> None:
    library = make_library(tmp_path)
    pending = library.ingest(
        ingest_command(title="待确认例题", rights_basis="original"),
        filename="pending.docx",
        content=docx_bytes("1. 已知集合 A={1,2}，判断 1∈A。\n答案：正确"),
    )
    with pytest.raises(PrivateLibraryError, match="教师已确认"):
        library.propose_questions(pending.library_item_id, owner_id="owner_teacher")

    item = confirmed_question_resource(library)
    candidate = library.propose_questions(
        item.library_item_id, owner_id="owner_teacher"
    ).items[0]
    with pytest.raises(PrivateLibraryError, match="教材知识点"):
        library.mark_candidate_imported(
            item.library_item_id,
            candidate.candidate_id,
            "q_not_created",
            owner_id="owner_teacher",
        )

    revised = library.review(
        item.library_item_id,
        LibraryTextReviewCommand(
            corrected_text=f"{item.corrected_text}\n3. 新增一道题。\n答案：略",
            confirm=True,
        ),
        owner_id="owner_teacher",
        reviewer_id="owner_teacher",
    )
    assert revised.version > candidate.source_version
    with pytest.raises(PrivateLibraryError, match="旧文本版本"):
        library.map_question_candidate_curriculum(
            item.library_item_id,
            candidate.candidate_id,
            QuestionCandidateCurriculum(
                node_id="kp_r1_1_1_02",
                name="元素与集合的关系",
                volume="必修第一册",
                chapter="集合与常用逻辑用语",
                section="集合的概念",
            ),
            owner_id="owner_teacher",
            editor_id="owner_teacher",
        )


def test_question_candidate_owner_and_server_owned_fields_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = make_library(tmp_path)
    item = confirmed_question_resource(library)
    candidate = library.propose_questions(
        item.library_item_id, owner_id="owner_teacher"
    ).items[0]
    with pytest.raises(KeyError):
        library.map_question_candidate_curriculum(
            item.library_item_id,
            candidate.candidate_id,
            QuestionCandidateCurriculum(
                node_id="kp_r1_1_1_02",
                name="伪造名称",
                volume="伪造册次",
            ),
            owner_id="other_teacher",
            editor_id="other_teacher",
        )

    monkeypatch.setattr("app.routes.library.get_private_library", lambda: library)
    client = TestClient(app)
    curriculum_response = client.post(
        f"/api/v1/library/{item.library_item_id}/question-candidates/{candidate.candidate_id}/curriculum",
        json={"node_id": "kp_r1_1_1_02", "name": "伪造名称", "volume": "伪造册次"},
    )
    update_response = client.patch(
        f"/api/v1/library/{item.library_item_id}/question-candidates/{candidate.candidate_id}",
        json={
            "question_type": candidate.question_type,
            "stem_plain": candidate.stem_plain,
            "options": [option.model_dump() for option in candidate.options],
            "answer_value": candidate.answer_value,
            "solution_method": candidate.solution_method,
            "solution_steps": candidate.solution_steps,
            "final_answer": candidate.final_answer,
            "difficulty": candidate.difficulty,
            "editor_id": "other_teacher",
        },
    )

    assert curriculum_response.status_code == 422
    assert update_response.status_code == 422
    assert library.list_question_candidates(
        item.library_item_id, owner_id="owner_teacher"
    ).items[0].curriculum is None


def test_http_rejects_unmapped_candidate_before_question_bank_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = make_library(tmp_path)
    bank = QuestionBank(tmp_path / "questions.sqlite3", tmp_path / "media")
    item = confirmed_question_resource(library)
    candidate = library.propose_questions(
        item.library_item_id, owner_id="owner_teacher"
    ).items[0]
    monkeypatch.setattr("app.routes.library.get_private_library", lambda: library)
    monkeypatch.setattr("app.routes.library.get_library_question_bank", lambda: bank)
    client = TestClient(app)

    response = client.post(
        f"/api/v1/library/{item.library_item_id}/question-candidates/{candidate.candidate_id}/import"
    )

    assert response.status_code == 409
    assert "教材知识点" in response.json()["detail"]
    with pytest.raises(KeyError):
        bank.get_question(f"q_resource_{candidate.candidate_id.removeprefix('cand_')}")


def test_candidate_import_is_private_auditable_and_idempotent(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    bank = QuestionBank(tmp_path / "questions.sqlite3", tmp_path / "media")
    item = confirmed_question_resource(library)
    candidate = library.propose_questions(
        item.library_item_id, owner_id="owner_teacher"
    ).items[0]
    candidate = map_candidate_to_collection_concepts(
        library, item.library_item_id, candidate.candidate_id
    )

    question = bank.create_private_resource_question(
        candidate.model_dump(), resource=item.model_dump(), owner_id="owner_teacher"
    )
    marked = library.mark_candidate_imported(
        item.library_item_id,
        candidate.candidate_id,
        question.question_id,
        owner_id="owner_teacher",
    )
    same = bank.create_private_resource_question(
        candidate.model_dump(), resource=item.model_dump(), owner_id="owner_teacher"
    )

    assert question.visibility == "private"
    assert question.review_status == "pending"
    assert question.verification_status == "needs_math_review"
    assert "teacher_review_required" in question.publication_blockers
    assert question.raw["provenance"]["resource_candidate_id"] == candidate.candidate_id
    assert question.raw["provenance"]["owner_id"] == "owner_teacher"
    assert question.raw["curriculum"]["knowledge_point_ids"] == ["kp_r1_1_1_02"]
    assert marked.status == "imported"
    assert same.question_id == question.question_id


def test_ocr_requires_per_run_consent_and_returns_pending_review(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    item = library.ingest(
        ingest_command(title="扫描题目"), filename="scan.png", content=png_bytes()
    )

    class FakeOCR:
        name = "fake-ocr"

        def extract(self, **_kwargs):
            return OCRTextResult(text="1. 已知 a>0，求 a+a^{-1} 的最小值。", warnings=["第1页已识别"])

    with pytest.raises(PrivateLibraryError, match="明确同意"):
        library.apply_ocr(
            item.library_item_id,
            provider=FakeOCR(),
            consent=False,
            owner_id="owner_teacher",
            teacher_id="teacher",
        )

    reviewed, provider, warnings = library.apply_ocr(
        item.library_item_id,
        provider=FakeOCR(),
        consent=True,
        owner_id="owner_teacher",
        teacher_id="teacher",
    )
    assert provider == "fake-ocr"
    assert warnings == ["第1页已识别"]
    assert reviewed.extraction_status == "extracted"
    assert reviewed.text_review_status == "pending"
    assert "最小值" in reviewed.corrected_text


def test_openai_ocr_extracts_docx_embedded_images_as_vision_inputs() -> None:
    inputs = OpenAIResourceOCRProvider._media_inputs(
        image_docx_bytes(),
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename="image-only.docx",
    )

    assert len(inputs) == 1
    assert inputs[0]["type"] == "input_image"
    assert inputs[0]["image_url"].startswith("data:image/png;base64,")


def test_question_candidate_http_flow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    library = make_library(tmp_path)
    bank = QuestionBank(tmp_path / "questions.sqlite3", tmp_path / "media")
    item = confirmed_question_resource(library)
    monkeypatch.setattr("app.routes.library.get_private_library", lambda: library)
    monkeypatch.setattr("app.routes.library.get_library_question_bank", lambda: bank)
    client = TestClient(app)

    proposed = client.post(f"/api/v1/library/{item.library_item_id}/question-candidates")
    assert proposed.status_code == 200
    candidate = proposed.json()["items"][0]

    mapped = client.post(
        f"/api/v1/library/{item.library_item_id}/question-candidates/{candidate['candidate_id']}/curriculum",
        json={"node_id": "kp_r1_1_1_02"},
    )
    assert mapped.status_code == 200
    assert mapped.json()["curriculum"]["name"] == "元素与集合的关系"

    imported = client.post(
        f"/api/v1/library/{item.library_item_id}/question-candidates/{candidate['candidate_id']}/import"
    )
    repeated = client.post(
        f"/api/v1/library/{item.library_item_id}/question-candidates/{candidate['candidate_id']}/import"
    )
    assert imported.status_code == 200
    assert imported.json()["candidate"]["status"] == "imported"
    assert repeated.json()["already_imported"] is True


def test_image_resource_is_kept_as_a_bounded_question_image(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = make_library(tmp_path)
    bank = QuestionBank(tmp_path / "questions.sqlite3", tmp_path / "media")
    uploaded = library.ingest(
        ingest_command(title="立体几何原题图", rights_basis="original"),
        filename="solid.png",
        content=png_bytes(),
    )
    item = library.review(
        uploaded.library_item_id,
        LibraryTextReviewCommand(
            corrected_text="1. 如图，在正方体 ABCD-A₁B₁C₁D₁ 中，求异面直线所成角。\n答案：60°",
            confirm=True,
        ),
        owner_id="owner_teacher",
        reviewer_id="owner_teacher",
    )
    candidate = library.propose_questions(
        item.library_item_id, owner_id="owner_teacher"
    ).items[0]
    library.map_question_candidate_curriculum(
        item.library_item_id,
        candidate.candidate_id,
        QuestionCandidateCurriculum(
            node_id="kp_r2_8_4_03",
            name="异面直线",
            volume="必修第二册",
            chapter="立体几何初步",
            section="空间点直线平面之间的位置关系",
        ),
        owner_id="owner_teacher",
        editor_id="owner_teacher",
    )
    monkeypatch.setattr("app.routes.library.get_private_library", lambda: library)
    monkeypatch.setattr("app.routes.library.get_library_question_bank", lambda: bank)
    client = TestClient(app)

    response = client.post(
        f"/api/v1/library/{item.library_item_id}/question-candidates/{candidate.candidate_id}/import"
    )
    question = bank.get_question(response.json()["question_id"])

    assert response.status_code == 200
    assert len(question.images) == 1
    assert question.images[0].placement == "stem"
    assert question.images[0].width == 80
    assert question.images[0].height == 60
