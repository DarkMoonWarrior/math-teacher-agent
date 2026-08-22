from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.core.identity import CurrentTeacher, get_current_teacher
from app.main import app
from app.modules.question_capture import (
    LowConfidenceRegion,
    QuestionCapture,
    QuestionCaptureCommand,
    QuestionCaptureError,
    QuestionMediaCrop,
    QuestionMediaTransformCommand,
    QuestionOption,
    QuestionRecognitionCommand,
    QuestionRecognitionError,
    QuestionRecognitionResult,
    QuestionRecognitionReviewCommand,
)
from app.routes.question_capture import get_question_capture


def image_bytes(
    *,
    width: int = 1000,
    height: int = 700,
    image_format: str = "PNG",
    blank: bool = False,
) -> bytes:
    image = Image.new("RGB", (width, height), "white")
    if not blank:
        draw = ImageDraw.Draw(image)
        margin = max(5, min(width, height) // 10)
        draw.rectangle((margin, margin, width - margin, height - margin), outline="black", width=3)
        draw.line((margin, height // 2, width - margin, height // 2), fill="black", width=3)
    output = BytesIO()
    image.save(output, format=image_format)
    return output.getvalue()


def make_capture(tmp_path: Path) -> QuestionCapture:
    return QuestionCapture(tmp_path / "capture.sqlite3", tmp_path / "media")


class FakeRecognitionProvider:
    name = "synthetic_ocr"
    model = "synthetic-v1"

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[dict[str, object]] = []

    def recognize(self, *, path: Path, mime_type: str, teacher_id: str) -> QuestionRecognitionResult:
        self.calls.append({"path": path, "mime_type": mime_type, "teacher_id": teacher_id})
        if self.fail:
            raise QuestionRecognitionError("synthetic failure")
        return QuestionRecognitionResult(
            stem_plain="已知函数 f(x)=x²，求 f(2)。",
            stem_latex=r"已知函数 $f(x)=x^2$，求 $f(2)$。",
            options=[QuestionOption(key="A", text="2"), QuestionOption(key="B", text="4")],
            low_confidence_regions=[
                LowConfidenceRegion(text="x²", reason="上标较小", confidence=0.72, box=(0.1, 0.2, 0.3, 0.4))
            ],
            warnings=["请核对上标。"],
            requires_visual_reasoning=False,
        )


def make_recognition_capture(
    tmp_path: Path,
    *,
    local: FakeRecognitionProvider | None = None,
    external: FakeRecognitionProvider | None = None,
) -> QuestionCapture:
    providers = {}
    if local is not None:
        providers["local"] = local
    if external is not None:
        providers["external"] = external
    return QuestionCapture(
        tmp_path / "capture.sqlite3",
        tmp_path / "media",
        recognition_providers=providers,
    )


def command(owner_id: str = "teacher_a", source: str = "upload") -> QuestionCaptureCommand:
    return QuestionCaptureCommand(
        owner_id=owner_id,
        source=source,
        private_storage_acknowledged=True,
    )


def test_prepare_returns_private_owner_scoped_bundle_without_storage_paths(tmp_path: Path) -> None:
    capture = make_capture(tmp_path)
    content = image_bytes()

    bundle = capture.prepare(command(source="clipboard"), filename="解析几何.png", content=content)

    assert bundle.asset.source == "clipboard"
    assert bundle.asset.visibility == "private"
    assert not bundle.asset.public_search_allowed
    assert not bundle.asset.model_training_allowed
    assert bundle.asset.current_revision == 1
    assert bundle.asset.clarity_status == "clear"
    assert bundle.recognition_status == "not_started"
    assert bundle.external_processing_consent is False
    assert bundle.requires_visual_reasoning is None
    payload = bundle.model_dump(mode="json")
    serialized = str(payload)
    assert "teacher_a" not in serialized
    assert str(tmp_path) not in serialized
    assert "stored_name" not in serialized
    assert bundle.asset.revisions[0].content_endpoint.endswith("revision=1")
    path, mime_type = capture.content(bundle.asset.asset_id, owner_id="teacher_a")
    assert path.read_bytes() == content
    assert mime_type == "image/png"


def test_prepare_rejects_missing_acknowledgement_invalid_format_and_unreadable_images(tmp_path: Path) -> None:
    capture = make_capture(tmp_path)
    with pytest.raises(QuestionCaptureError, match="确认"):
        capture.prepare(
            QuestionCaptureCommand(
                owner_id="teacher_a",
                source="upload",
                private_storage_acknowledged=False,
            ),
            filename="question.png",
            content=image_bytes(),
        )
    with pytest.raises(QuestionCaptureError, match="格式"):
        capture.prepare(command(), filename="question.png", content=b"not an image")
    with pytest.raises(QuestionCaptureError, match="尺寸过小"):
        capture.prepare(command(), filename="tiny.png", content=image_bytes(width=100, height=70))
    with pytest.raises(QuestionCaptureError, match="没有可辨内容"):
        capture.prepare(command(), filename="blank.png", content=image_bytes(blank=True))


def test_rotate_and_crop_create_traceable_revisions_and_preserve_original(tmp_path: Path) -> None:
    capture = make_capture(tmp_path)
    original = image_bytes(width=1000, height=700)
    created = capture.prepare(command(), filename="question.png", content=original)

    rotated = capture.transform(
        created.asset.asset_id,
        QuestionMediaTransformCommand(operation="rotate", degrees=90),
        owner_id="teacher_a",
    )
    assert (rotated.asset.width, rotated.asset.height) == (700, 1000)
    assert rotated.asset.current_revision == 2
    assert rotated.asset.revisions[-1].operation == "rotate"
    assert rotated.asset.revisions[-1].source_revision == 1

    cropped = capture.transform(
        created.asset.asset_id,
        QuestionMediaTransformCommand(
            operation="crop",
            crop=QuestionMediaCrop(x=50, y=100, width=600, height=800),
        ),
        owner_id="teacher_a",
    )
    assert (cropped.asset.width, cropped.asset.height) == (600, 800)
    assert cropped.asset.current_revision == 3
    assert [item.operation for item in cropped.asset.revisions] == ["original", "rotate", "crop"]
    original_path, original_mime = capture.content(
        created.asset.asset_id,
        owner_id="teacher_a",
        revision=1,
    )
    assert original_path.read_bytes() == original
    assert original_mime == "image/png"


def test_transform_and_content_fail_closed_across_owners(tmp_path: Path) -> None:
    capture = make_capture(tmp_path)
    bundle = capture.prepare(command(), filename="question.png", content=image_bytes())

    with pytest.raises(KeyError):
        capture.get(bundle.asset.asset_id, owner_id="teacher_b")
    with pytest.raises(KeyError):
        capture.content(bundle.asset.asset_id, owner_id="teacher_b")
    with pytest.raises(KeyError):
        capture.transform(
            bundle.asset.asset_id,
            QuestionMediaTransformCommand(operation="rotate", degrees=90),
            owner_id="teacher_b",
        )


def test_crop_rejects_out_of_bounds_or_unreliable_region(tmp_path: Path) -> None:
    capture = make_capture(tmp_path)
    bundle = capture.prepare(command(), filename="question.png", content=image_bytes())
    with pytest.raises(QuestionCaptureError, match="超出"):
        capture.transform(
            bundle.asset.asset_id,
            QuestionMediaTransformCommand(
                operation="crop",
                crop=QuestionMediaCrop(x=900, y=600, width=200, height=200),
            ),
            owner_id="teacher_a",
        )
    with pytest.raises(QuestionCaptureError, match="过小"):
        capture.transform(
            bundle.asset.asset_id,
            QuestionMediaTransformCommand(
                operation="crop",
                crop=QuestionMediaCrop(x=0, y=0, width=79, height=200),
            ),
            owner_id="teacher_a",
        )


def test_public_routes_bind_owner_on_server_and_never_accept_owner_selector(tmp_path: Path) -> None:
    capture = make_recognition_capture(tmp_path, local=FakeRecognitionProvider())
    app.dependency_overrides[get_question_capture] = lambda: capture
    app.dependency_overrides[get_current_teacher] = lambda: CurrentTeacher(
        teacher_id="teacher_route_a",
        source="authenticated_session",
    )
    client = TestClient(app)
    try:
        response = client.post(
            "/api/v1/question-capture/assets",
            files={"file": ("question.png", image_bytes(), "image/png")},
            data={
                "source": "camera",
                "private_storage_acknowledged": "true",
                "owner_id": "teacher_route_b",
            },
        )
        assert response.status_code == 201
        payload = response.json()
        assert "owner_id" not in payload["asset"]
        asset_id = payload["asset"]["asset_id"]
        assert client.get(f"/api/v1/question-capture/assets/{asset_id}").status_code == 200
        assert client.get(
            f"/api/v1/question-capture/assets/{asset_id}/content?revision=1"
        ).status_code == 200
        recognized = client.post(
            f"/api/v1/question-capture/assets/{asset_id}/recognize",
            json={
                "mode": "local",
                "external_processing_consent": False,
                "owner_id": "teacher_route_b",
            },
        )
        assert recognized.status_code == 422
        recognized = client.post(
            f"/api/v1/question-capture/assets/{asset_id}/recognize",
            json={"mode": "local", "external_processing_consent": False},
        )
        assert recognized.status_code == 200
        reviewed = client.patch(
            f"/api/v1/question-capture/assets/{asset_id}/recognition",
            json={
                "stem_plain": "教师校对题面",
                "stem_latex": "",
                "options": [],
                "note": "",
                "confirm": True,
                "reviewer_id": "teacher_route_b",
            },
        )
        assert reviewed.status_code == 422
        reviewed = client.patch(
            f"/api/v1/question-capture/assets/{asset_id}/recognition",
            json={
                "stem_plain": "教师校对题面",
                "stem_latex": "",
                "options": [],
                "note": "",
                "confirm": True,
            },
        )
        assert reviewed.status_code == 200
        assert reviewed.json()["recognition_status"] == "confirmed"

        app.dependency_overrides[get_current_teacher] = lambda: CurrentTeacher(
            teacher_id="teacher_route_b",
            source="authenticated_session",
        )
        assert client.get(f"/api/v1/question-capture/assets/{asset_id}").status_code == 404
        assert client.get(f"/api/v1/question-capture/assets/{asset_id}/content").status_code == 404
        assert client.post(
            f"/api/v1/question-capture/assets/{asset_id}/transform",
            json={"operation": "rotate", "degrees": 90},
        ).status_code == 404
        assert client.post(
            f"/api/v1/question-capture/assets/{asset_id}/recognize",
            json={"mode": "local", "external_processing_consent": False},
        ).status_code == 404
        assert client.patch(
            f"/api/v1/question-capture/assets/{asset_id}/recognition",
            json={"stem_plain": "越权", "confirm": True},
        ).status_code == 404
    finally:
        app.dependency_overrides.pop(get_question_capture, None)
        app.dependency_overrides.pop(get_current_teacher, None)


def test_recognition_creates_private_structured_revision_bound_to_media(tmp_path: Path) -> None:
    provider = FakeRecognitionProvider()
    capture = make_recognition_capture(tmp_path, local=provider)
    created = capture.prepare(command(), filename="question.png", content=image_bytes())

    recognized = capture.recognize(
        created.asset.asset_id,
        QuestionRecognitionCommand(mode="local"),
        owner_id="teacher_a",
    )

    assert recognized.recognition_status == "draft"
    assert recognized.recognition_revision == 1
    assert recognized.recognition_source_revision == 1
    assert recognized.recognition_provider == "synthetic_ocr"
    assert recognized.recognition_model == "synthetic-v1"
    assert recognized.external_processing_consent is False
    assert recognized.options[1].text == "4"
    assert recognized.low_confidence_regions[0].reason == "上标较小"
    assert provider.calls[0]["teacher_id"] == "teacher_a"
    serialized = str(recognized.model_dump(mode="json"))
    assert "teacher_a" not in serialized
    assert str(tmp_path) not in serialized


def test_external_recognition_requires_per_action_consent_and_records_it(tmp_path: Path) -> None:
    provider = FakeRecognitionProvider()
    capture = make_recognition_capture(tmp_path, external=provider)
    created = capture.prepare(command(), filename="question.png", content=image_bytes())

    with pytest.raises(QuestionCaptureError, match="逐次确认"):
        capture.recognize(
            created.asset.asset_id,
            QuestionRecognitionCommand(mode="external", external_processing_consent=False),
            owner_id="teacher_a",
        )
    assert provider.calls == []

    recognized = capture.recognize(
        created.asset.asset_id,
        QuestionRecognitionCommand(mode="external", external_processing_consent=True),
        owner_id="teacher_a",
    )
    assert recognized.external_processing_consent is True
    assert recognized.recognition_mode == "external"


def test_local_recognition_rejects_external_consent_and_provider_failure_is_not_saved(tmp_path: Path) -> None:
    provider = FakeRecognitionProvider(fail=True)
    capture = make_recognition_capture(tmp_path, local=provider)
    created = capture.prepare(command(), filename="question.png", content=image_bytes())

    with pytest.raises(QuestionCaptureError, match="不接受"):
        capture.recognize(
            created.asset.asset_id,
            QuestionRecognitionCommand(mode="local", external_processing_consent=True),
            owner_id="teacher_a",
        )
    with pytest.raises(QuestionCaptureError, match="synthetic failure"):
        capture.recognize(
            created.asset.asset_id,
            QuestionRecognitionCommand(mode="local"),
            owner_id="teacher_a",
        )
    assert capture.get(created.asset.asset_id, owner_id="teacher_a").recognition_status == "not_started"


def test_teacher_review_is_append_only_and_media_change_makes_recognition_stale(tmp_path: Path) -> None:
    capture = make_recognition_capture(tmp_path, local=FakeRecognitionProvider())
    created = capture.prepare(command(), filename="question.png", content=image_bytes())
    capture.recognize(
        created.asset.asset_id,
        QuestionRecognitionCommand(mode="local"),
        owner_id="teacher_a",
    )
    confirmed = capture.review_recognition(
        created.asset.asset_id,
        QuestionRecognitionReviewCommand(
            stem_plain="教师校对后的题面",
            stem_latex=r"教师校对后的 $f(x)$",
            options=[QuestionOption(key="A", text="4")],
            note="已对照原图",
            confirm=True,
        ),
        owner_id="teacher_a",
    )
    assert confirmed.recognition_status == "confirmed"
    assert confirmed.recognition_revision == 2
    assert confirmed.stem_plain == "教师校对后的题面"
    assert confirmed.teacher_review_note == "已对照原图"

    stale = capture.transform(
        created.asset.asset_id,
        QuestionMediaTransformCommand(operation="rotate", degrees=90),
        owner_id="teacher_a",
    )
    assert stale.recognition_status == "stale"
    assert stale.recognition_source_revision == 1
    with pytest.raises(QuestionCaptureError, match="重新识别"):
        capture.review_recognition(
            created.asset.asset_id,
            QuestionRecognitionReviewCommand(stem_plain="不可保存"),
            owner_id="teacher_a",
        )


def test_recognition_and_review_fail_closed_across_owners(tmp_path: Path) -> None:
    capture = make_recognition_capture(tmp_path, local=FakeRecognitionProvider())
    created = capture.prepare(command(), filename="question.png", content=image_bytes())
    with pytest.raises(KeyError):
        capture.recognize(
            created.asset.asset_id,
            QuestionRecognitionCommand(mode="local"),
            owner_id="teacher_b",
        )
    capture.recognize(
        created.asset.asset_id,
        QuestionRecognitionCommand(mode="local"),
        owner_id="teacher_a",
    )
    with pytest.raises(KeyError):
        capture.review_recognition(
            created.asset.asset_id,
            QuestionRecognitionReviewCommand(stem_plain="越权"),
            owner_id="teacher_b",
        )
