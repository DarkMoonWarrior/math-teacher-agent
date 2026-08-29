import re
from copy import deepcopy
from pathlib import Path
from zipfile import ZipFile

import pytest
from docx import Document
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.core.identity import CurrentTeacher, get_current_teacher
from app.modules.exam_exports import ExamPaperDocumentRenderer
from app.modules.exam_exports.math_text import teacher_readable_math
from app.modules.exam_papers import (
    ExamPaperCreateCommand,
    ExamPaperHistoryRevisionCommand,
    ExamPaperItemInput,
    ExamPaperLifecycleCommand,
    ExamPaperStudio,
    ExamPaperStudioError,
    ExamPaperUpdateCommand,
)
from app.modules.question_bank.schemas import QuestionDetail, QuestionImage
from app.routes import exam_papers as exam_paper_routes
from app.modules.exam_papers.studio import ExamPaperStudioConflict


def question_detail(
    question_id: str,
    *,
    stem: str,
    verification_status: str = "passed",
    review_status: str = "approved",
) -> QuestionDetail:
    raw = {
        "stem": {"plain_text": stem, "latex": None},
        "options": [
            {"key": "A", "plain_text": "1", "latex": None},
            {"key": "B", "plain_text": "2", "latex": None},
        ],
        "solutions": [
            {
                "method": "直接计算",
                "steps_latex": ["根据题设进行计算。", "核对选项得到结论。"],
                "final_answer": "A",
                "review_status": "ready_for_teacher_review",
            }
        ],
    }
    return QuestionDetail(
        question_id=question_id,
        status="verified",
        review_status=review_status,
        visibility="private",
        question_type="single_choice",
        stem_plain=stem,
        answer_value="A",
        volume="必修第一册",
        chapter="第一章 集合与常用逻辑用语",
        section="1.1 集合的概念",
        knowledge_point_ids=["kp_sets"],
        difficulty=2,
        verification_status=verification_status,
        source_document="集合题库.pdf",
        source_page_start=1,
        source_page_end=1,
        license_status="question_content_user_declared_usable",
        publication_blockers=[],
        raw=raw,
        reviews=[],
        images=[],
        revision_count=0,
    )


class FakeQuestionBank:
    def __init__(self) -> None:
        self.media_paths: dict[tuple[str, str], Path] = {}
        self.questions = {
            "q1": question_detail("q1", stem="设集合 A={1,2}，求 A 的子集个数。"),
            "q2": question_detail(
                "q2",
                stem="设全集 U={1,2,3}，A={1}，求 A 的补集。",
                review_status="pending",
            ),
            "bad": question_detail(
                "bad", stem="尚未验算的题目。", verification_status="needs_math_review"
            ),
        }

    def get_question(self, question_id: str) -> QuestionDetail:
        if question_id not in self.questions:
            raise KeyError(question_id)
        return self.questions[question_id]

    def image_path(self, question_id: str, image_id: str):
        if (question_id, image_id) not in self.media_paths:
            raise KeyError((question_id, image_id))
        return self.media_paths[(question_id, image_id)], "image/png"


def make_studio(tmp_path: Path) -> tuple[ExamPaperStudio, FakeQuestionBank]:
    bank = FakeQuestionBank()
    studio = ExamPaperStudio(
        database_path=tmp_path / "exam-papers.sqlite3",
        asset_root=tmp_path / "paper-assets",
        question_bank=bank,  # type: ignore[arg-type]
    )
    return studio, bank


def create_command() -> ExamPaperCreateCommand:
    return ExamPaperCreateCommand(
        title="集合单元检测",
        duration_minutes=45,
        items=[
            ExamPaperItemInput(question_id="q1", score=5),
            ExamPaperItemInput(question_id="q2", score=7),
        ],
    )


def test_studio_creates_versioned_paper_with_breakdown_and_warnings(tmp_path: Path) -> None:
    studio, _ = make_studio(tmp_path)

    paper = studio.create(create_command())

    assert paper.version == 1
    assert paper.total_score == 12
    assert [item.position for item in paper.items] == [1, 2]
    assert paper.chapter_breakdown[0].question_count == 2
    assert paper.difficulty_breakdown[0].score == 12
    assert any("1 道题" in warning and "待教师" in warning for warning in paper.warnings)
    assert studio.list().total == 1


def test_paper_history_list_and_lifecycle_are_owner_scoped(tmp_path: Path) -> None:
    studio, _ = make_studio(tmp_path)
    paper_a = studio.create(create_command().model_copy(update={"teacher_id": "teacher-a"}))
    paper_b = studio.create(
        create_command().model_copy(
            update={"title": "另一位教师的试卷", "teacher_id": "teacher-b"}
        )
    )

    history_a = studio.list_owned(owner_id="teacher-a")
    history_b = studio.list_owned(owner_id="teacher-b")

    assert [item.exam_paper_id for item in history_a.items] == [paper_a.exam_paper_id]
    assert [item.exam_paper_id for item in history_b.items] == [paper_b.exam_paper_id]
    with pytest.raises(KeyError):
        studio.change_owned_lifecycle(
            paper_b.exam_paper_id,
            ExamPaperLifecycleCommand(action="trash"),
            owner_id="teacher-a",
        )

    studio.change_owned_lifecycle(
        paper_a.exam_paper_id,
        ExamPaperLifecycleCommand(action="trash"),
        owner_id="teacher-a",
    )
    assert studio.list_owned(owner_id="teacher-a", lifecycle_state="active").total == 0
    assert studio.list_owned(owner_id="teacher-a", lifecycle_state="trashed").total == 1


def test_owner_can_edit_history_into_a_new_revision_without_overwriting_the_old_one(tmp_path: Path) -> None:
    studio, _ = make_studio(tmp_path)
    original = studio.create(create_command().model_copy(update={"teacher_id": "teacher-a"}))
    command = ExamPaperHistoryRevisionCommand(
        expected_version=1,
        title="集合单元检测（修订）",
        duration_minutes=50,
        instructions="写出必要过程",
        items=[{
            "question_id": "q2",
            "section_id": "open",
            "section_title": "解答题",
            "score": 10,
        }],
    )

    with pytest.raises(KeyError):
        studio.revise_owned_history(original.exam_paper_id, command, owner_id="teacher-b")

    revised = studio.revise_owned_history(
        original.exam_paper_id,
        command,
        owner_id="teacher-a",
    )

    assert revised.version == 2
    assert revised.title.endswith("（修订）")
    assert revised.total_score == 10
    assert len(revised.items) == 1
    assert revised.items[0].section_title == "解答题"
    assert revised.specification is not None
    assert revised.specification.question_to_dimensions[0].position == 1
    preserved = studio.get_owned_version(
        original.exam_paper_id,
        1,
        owner_id="teacher-a",
    )
    assert len(preserved.items) == 2
    assert preserved.total_score == 12
    with pytest.raises(ExamPaperStudioConflict, match="更新版本"):
        studio.revise_owned_history(
            original.exam_paper_id,
            command,
            owner_id="teacher-a",
        )


def test_owner_can_add_a_server_resolved_question_to_history_revision(tmp_path: Path) -> None:
    studio, bank = make_studio(tmp_path)
    bank.questions["q3"] = question_detail(
        "q3", stem="函数 f(x)=x 的定义域是？"
    )
    original = studio.create(create_command().model_copy(update={"teacher_id": "teacher-a"}))
    command = ExamPaperHistoryRevisionCommand(
        expected_version=1,
        title="集合单元检测（加题）",
        duration_minutes=45,
        instructions="写出必要过程",
        target_total_score=17,
        selected_public_question_ids=["q3"],
        items=[
            {"question_id": "q1", "section_id": "choice", "section_title": "选择题", "score": 5},
            {"question_id": "q2", "section_id": "choice", "section_title": "选择题", "score": 7},
            {"question_id": "q3", "section_id": "choice", "section_title": "选择题", "score": 5},
        ],
    )

    revised = studio.revise_owned_history(
        original.exam_paper_id,
        command,
        owner_id="teacher-a",
        added_question_source=bank,
    )

    assert revised.version == 2
    assert len(revised.items) == 3
    assert revised.total_score == 17
    assert revised.items[-1].question.question_id == "q3"


def test_paper_history_http_never_lists_or_changes_another_owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    studio, _ = make_studio(tmp_path)
    own = studio.create(create_command().model_copy(update={"teacher_id": "teacher-a"}))
    other = studio.create(
        create_command().model_copy(
            update={"title": "不可见试卷", "teacher_id": "teacher-b"}
        )
    )
    monkeypatch.setattr(exam_paper_routes, "get_exam_paper_studio", lambda: studio)
    app.dependency_overrides[get_current_teacher] = lambda: CurrentTeacher(
        teacher_id="teacher-a",
        source="authenticated_session",
    )
    try:
        client = TestClient(app)
        listing = client.get("/api/v1/exam-papers")
        forbidden_read = client.get(f"/api/v1/exam-papers/{other.exam_paper_id}")
        forbidden_revision = client.put(
            f"/api/v1/exam-papers/{other.exam_paper_id}/history-revision",
            json={
                "expected_version": 1,
                "title": "不可越权修订",
                "duration_minutes": 45,
                "instructions": "",
                "items": [{
                    "question_id": "q1",
                    "section_id": "single",
                    "section_title": "选择题",
                    "score": 5,
                }],
            },
        )
        forbidden_change = client.post(
            f"/api/v1/exam-papers/{other.exam_paper_id}/lifecycle",
            json={"action": "trash"},
        )
        own_change = client.post(
            f"/api/v1/exam-papers/{own.exam_paper_id}/lifecycle",
            json={"action": "trash"},
        )
    finally:
        app.dependency_overrides.pop(get_current_teacher, None)

    assert listing.status_code == 200
    assert [item["exam_paper_id"] for item in listing.json()["items"]] == [own.exam_paper_id]
    assert forbidden_read.status_code == 404
    assert forbidden_revision.status_code == 404
    assert forbidden_change.status_code == 404
    assert own_change.status_code == 200


def test_update_preserves_question_snapshot_when_source_changes(tmp_path: Path) -> None:
    studio, bank = make_studio(tmp_path)
    paper = studio.create(create_command())
    original_stem = paper.items[0].question.stem_plain
    bank.questions["q1"] = question_detail("q1", stem="题库中已经修改的新题干。")

    updated = studio.update(
        paper.exam_paper_id,
        ExamPaperUpdateCommand(
            title="集合单元检测（教师修订）",
            duration_minutes=50,
            items=[
                ExamPaperItemInput(question_id="q2", score=8),
                ExamPaperItemInput(question_id="q1", score=6),
            ],
        ),
    )

    assert updated.version == 2
    assert updated.total_score == 14
    assert updated.items[1].question.stem_plain == original_stem
    assert studio.get(paper.exam_paper_id).title.endswith("教师修订）")


def test_unverified_and_duplicate_questions_are_rejected(tmp_path: Path) -> None:
    studio, _ = make_studio(tmp_path)

    with pytest.raises(ExamPaperStudioError, match="尚未通过"):
        studio.create(
            ExamPaperCreateCommand(
                title="无效试卷",
                items=[ExamPaperItemInput(question_id="bad", score=5)],
            )
        )
    with pytest.raises(ExamPaperStudioError, match="不能重复"):
        studio.create(
            ExamPaperCreateCommand(
                title="重复试卷",
                items=[
                    ExamPaperItemInput(question_id="q1", score=5),
                    ExamPaperItemInput(question_id="q1", score=5),
                ],
            )
        )


def test_renderer_creates_student_answer_and_blueprint_files(tmp_path: Path) -> None:
    studio, _ = make_studio(tmp_path)
    paper = studio.create(create_command())
    renderer = ExamPaperDocumentRenderer(
        output_root=tmp_path / "output", asset_root=tmp_path / "paper-assets"
    )

    student_docx = renderer.render(paper, "docx", "student")
    answer_docx = renderer.render(paper, "docx", "answer")
    blueprint_docx = renderer.render(paper, "docx", "blueprint")
    answer_pdf = renderer.render(paper, "pdf", "answer")

    with ZipFile(student_docx.path) as archive:
        student_xml = archive.read("word/document.xml").decode("utf-8")
    with ZipFile(answer_docx.path) as archive:
        answer_xml = archive.read("word/document.xml").decode("utf-8")
    with ZipFile(blueprint_docx.path) as archive:
        blueprint_xml = archive.read("word/document.xml").decode("utf-8")
    assert "参考答案" not in student_xml
    assert "参考答案" in answer_xml
    assert "双向细目表" in blueprint_xml
    assert "内容来源与审核说明" in student_xml
    assert answer_pdf.path.read_bytes().startswith(b"%PDF")
    assert answer_pdf.path.read_bytes().rstrip().endswith(b"%%EOF")


def test_paper_copies_stem_image_and_export_survives_source_deletion(tmp_path: Path) -> None:
    studio, bank = make_studio(tmp_path)
    source_image = tmp_path / "source-geometry.png"
    Image.new("RGB", (640, 420), "white").save(source_image)
    image = QuestionImage(
        image_id="img_geometry",
        question_id="q1",
        placement="stem",
        original_filename="geometry.png",
        mime_type="image/png",
        width=640,
        height=420,
        alt_text="立体几何示意图",
        caption="几何图形",
        sort_order=0,
        content_url="/content",
        created_at="2026-08-09T00:00:00+00:00",
        updated_at="2026-08-09T00:00:00+00:00",
    )
    bank.questions["q1"] = bank.questions["q1"].model_copy(update={"images": [image]})
    bank.media_paths[("q1", "img_geometry")] = source_image

    paper = studio.create(
        ExamPaperCreateCommand(
            title="含图试卷",
            items=[ExamPaperItemInput(question_id="q1", score=10)],
        )
    )
    source_image.unlink()
    renderer = ExamPaperDocumentRenderer(
        output_root=tmp_path / "output", asset_root=tmp_path / "paper-assets"
    )
    exported = renderer.render(paper, "docx", "student")

    assert len(paper.items[0].question.images) == 1
    with ZipFile(exported.path) as archive:
        assert any(name.startswith("word/media/") for name in archive.namelist())


def test_export_converts_latex_to_teacher_readable_math(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    studio, bank = make_studio(tmp_path)
    question = bank.questions["q1"]
    raw = deepcopy(question.raw)
    raw["options"][0]["plain_text"] = ""
    raw["options"][0]["latex"] = r"$-\frac{19}{4}$"
    raw["solutions"][0]["steps_latex"] = [
        r"设 $(x_0,y_0)$ 在图象上，且 $x_0\in[-1,0]$、$y_0=x_0^2$。"
    ]
    bank.questions["q1"] = question.model_copy(update={"raw": raw})
    paper = studio.create(
        ExamPaperCreateCommand(
            title="数学排版验收卷",
            items=[ExamPaperItemInput(question_id="q1", score=5)],
        )
    )
    renderer = ExamPaperDocumentRenderer(
        output_root=tmp_path / "output", asset_root=tmp_path / "paper-assets"
    )

    exported = renderer.render(paper, "docx", "answer")
    document = Document(exported.path)
    docx_text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    assert "-19/4" in docx_text
    assert "x₀∈[-1,0]" in docx_text
    assert "y₀=x₀²" in docx_text
    assert "$" not in docx_text
    assert r"\frac" not in docx_text
    source_heading = next(
        paragraph
        for paragraph in document.paragraphs
        if paragraph.text == "内容来源与审核说明"
    )
    assert source_heading.paragraph_format.page_break_before
    with ZipFile(exported.path) as archive:
        document_xml = archive.read("word/document.xml").decode("utf-8")
    assert "Cambria Math" in document_xml

    monkeypatch.setattr(
        "app.modules.exam_exports.renderer.Paragraph",
        lambda content, _style: content,
    )
    pdf_blocks = renderer._pdf_question(paper, paper.items[0], "answer", {  # noqa: SLF001
        name: object()
        for name in ["Question", "Option", "Answer", "Small", "Solution"]
    })
    pdf_text = "\n".join(block for block in pdf_blocks if isinstance(block, str))
    pdf_visible_text = re.sub(r"<[^>]+>", "", pdf_text)
    assert "-19/4" in pdf_visible_text
    assert "x₀∈[-1,0]" in pdf_visible_text
    assert "y₀=x₀²" in pdf_visible_text
    assert "$" not in pdf_visible_text
    assert r"\frac" not in pdf_visible_text


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (r"$-\frac92$", "-9/2"),
        (r"$x_0\in[-1,0],\ y_0=x_0^2$", "x₀∈[-1,0], y₀=x₀²"),
        (r"$A\cap(\complement_U B)$", "A∩(∁ᵤ B)"),
        (r"$P(\text{丙最终获胜})=\frac7{16}$", "P(丙最终获胜)=7/16"),
        (r"$\sum_{n=1}^{2024}f(n)$", "∑ₙ₌₁²⁰²⁴f(n)"),
        ("设集合 A={1,2}。", "设集合 A={1,2}。"),
    ],
)
def test_teacher_readable_math(source: str, expected: str) -> None:
    assert teacher_readable_math(source) == expected


@pytest.mark.parametrize(
    ("export_format", "edition", "content_prefix", "content_type"),
    [
        ("docx", "student", b"PK", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("docx", "answer", b"PK", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("docx", "blueprint", b"PK", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("pdf", "student", b"%PDF", "application/pdf"),
        ("pdf", "answer", b"%PDF", "application/pdf"),
        ("pdf", "blueprint", b"%PDF", "application/pdf"),
    ],
)
def test_exam_paper_http_create_and_export(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    export_format: str,
    edition: str,
    content_prefix: bytes,
    content_type: str,
) -> None:
    studio, _ = make_studio(tmp_path)
    renderer = ExamPaperDocumentRenderer(
        output_root=tmp_path / "output", asset_root=tmp_path / "paper-assets"
    )
    monkeypatch.setattr(exam_paper_routes, "get_exam_paper_studio", lambda: studio)
    monkeypatch.setattr(exam_paper_routes, "get_exam_paper_renderer", lambda: renderer)
    client = TestClient(app)

    response = client.post(
        "/api/v1/exam-papers",
        json={
            "title": "集合单元检测",
            "duration_minutes": 45,
            "items": [{"question_id": "q1", "score": 5}],
        },
    )

    assert response.status_code == 201
    paper = response.json()
    download = client.get(
        f"/api/v1/exam-papers/{paper['exam_paper_id']}/export",
        params={"format": export_format, "edition": edition},
    )
    assert download.status_code == 200
    assert download.content.startswith(content_prefix)
    assert download.headers["content-type"] == content_type
    assert f"-{edition}.{export_format}" in download.headers["content-disposition"]
