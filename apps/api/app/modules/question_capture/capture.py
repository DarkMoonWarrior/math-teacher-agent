from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageOps, ImageStat, UnidentifiedImageError

from .schemas import (
    QuestionCaptureCommand,
    QuestionInputBundle,
    QuestionMediaAsset,
    QuestionMediaRevision,
    QuestionMediaTransformCommand,
    QuestionRecognitionCommand,
    QuestionRecognitionReviewCommand,
    QuestionSolveReference,
    PreparedQuestionInput,
)
from .recognition import (
    LocalQuestionRecognitionProvider,
    QuestionRecognitionError,
    QuestionRecognitionProvider,
)


class QuestionCaptureError(ValueError):
    pass


class QuestionCapture:
    """Owns validation, private media storage and revision-safe transforms."""

    MAX_FILE_BYTES = 15 * 1024 * 1024
    MAX_IMAGE_PIXELS = 25_000_000
    MIN_SIDE_PIXELS = 80
    MIN_LONG_SIDE_PIXELS = 320
    _FORMATS = {
        "PNG": ("image/png", ".png"),
        "JPEG": ("image/jpeg", ".jpg"),
        "WEBP": ("image/webp", ".webp"),
    }

    def __init__(
        self,
        database_path: Path,
        file_root: Path,
        *,
        recognition_providers: dict[str, QuestionRecognitionProvider] | None = None,
    ) -> None:
        self.database_path = database_path.resolve()
        self.file_root = file_root.resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.file_root.mkdir(parents=True, exist_ok=True)
        self.recognition_providers = recognition_providers or {
            "local": LocalQuestionRecognitionProvider(),
        }
        self._initialize()

    def prepare(
        self,
        command: QuestionCaptureCommand,
        *,
        filename: str,
        content: bytes,
    ) -> QuestionInputBundle:
        if not command.private_storage_acknowledged:
            raise QuestionCaptureError("请先确认题目图片仅存入当前私人工作区")
        if not content:
            raise QuestionCaptureError("题目图片不能为空")
        if len(content) > self.MAX_FILE_BYTES:
            raise QuestionCaptureError("单张题目图片不能超过 15 MB")

        image, image_format = self._open_image(content)
        mime_type, suffix = self._FORMATS[image_format]
        width, height = image.size
        warnings = self._validate_dimensions_and_clarity(image)
        safe_filename = Path(filename or "题目图片").name
        if safe_filename in {"", ".", ".."}:
            safe_filename = "题目图片"
        asset_id = f"qcap_{uuid4().hex[:16]}"
        stored_name = f"{asset_id}-r1{suffix}"
        stored_path = self._confined_path(stored_name)
        stored_path.write_bytes(content)
        now = self._now()
        digest = hashlib.sha256(content).hexdigest()
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO question_capture_assets (
                        asset_id, owner_id, original_filename, source, source_sha256,
                        current_revision, width, height, size_bytes, mime_type,
                        clarity_status, warnings_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        asset_id,
                        command.owner_id,
                        safe_filename,
                        command.source,
                        digest,
                        width,
                        height,
                        len(content),
                        mime_type,
                        "review_needed" if warnings else "clear",
                        json.dumps(warnings, ensure_ascii=False),
                        now,
                        now,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO question_capture_revisions (
                        asset_id, revision, source_revision, operation, operation_json,
                        stored_name, width, height, mime_type, created_at
                    ) VALUES (?, 1, NULL, 'original', '{}', ?, ?, ?, ?, ?)
                    """,
                    (asset_id, stored_name, width, height, mime_type, now),
                )
        except Exception:
            stored_path.unlink(missing_ok=True)
            raise
        return self.get(asset_id, owner_id=command.owner_id)

    def transform(
        self,
        asset_id: str,
        command: QuestionMediaTransformCommand,
        *,
        owner_id: str,
    ) -> QuestionInputBundle:
        with self._connect() as connection:
            asset = connection.execute(
                "SELECT * FROM question_capture_assets WHERE asset_id = ? AND owner_id = ?",
                (asset_id, owner_id),
            ).fetchone()
            if asset is None:
                raise KeyError(asset_id)
            current = connection.execute(
                "SELECT * FROM question_capture_revisions WHERE asset_id = ? AND revision = ?",
                (asset_id, asset["current_revision"]),
            ).fetchone()
        if current is None:
            raise QuestionCaptureError("题目图片当前版本不存在")

        source_path = self._confined_path(current["stored_name"])
        try:
            with Image.open(source_path) as opened:
                image = ImageOps.exif_transpose(opened)
                image.load()
        except (UnidentifiedImageError, OSError) as exc:
            raise QuestionCaptureError("题目图片当前版本无法读取") from exc

        if command.operation == "rotate":
            if command.degrees is None or command.crop is not None:
                raise QuestionCaptureError("旋转操作必须且只能提供旋转角度")
            transformed = image.rotate(-command.degrees, expand=True)
            operation_payload = {"degrees": command.degrees}
        else:
            if command.crop is None or command.degrees is not None:
                raise QuestionCaptureError("裁剪操作必须且只能提供裁剪区域")
            crop = command.crop
            if crop.x + crop.width > image.width or crop.y + crop.height > image.height:
                raise QuestionCaptureError("裁剪区域超出当前图片范围")
            if min(crop.width, crop.height) < self.MIN_SIDE_PIXELS:
                raise QuestionCaptureError("裁剪区域过小，无法可靠识别题目")
            transformed = image.crop((crop.x, crop.y, crop.x + crop.width, crop.y + crop.height))
            operation_payload = crop.model_dump()

        warnings = self._validate_dimensions_and_clarity(transformed)
        next_revision = int(asset["current_revision"]) + 1
        stored_name = f"{asset_id}-r{next_revision}.png"
        stored_path = self._confined_path(stored_name)
        output = BytesIO()
        normalized = transformed.convert("RGBA") if transformed.mode in {"RGBA", "LA"} else transformed.convert("RGB")
        normalized.save(output, format="PNG", optimize=True)
        encoded = output.getvalue()
        stored_path.write_bytes(encoded)
        now = self._now()
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO question_capture_revisions (
                        asset_id, revision, source_revision, operation, operation_json,
                        stored_name, width, height, mime_type, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'image/png', ?)
                    """,
                    (
                        asset_id,
                        next_revision,
                        asset["current_revision"],
                        command.operation,
                        json.dumps(operation_payload, ensure_ascii=False),
                        stored_name,
                        transformed.width,
                        transformed.height,
                        now,
                    ),
                )
                connection.execute(
                    """
                    UPDATE question_capture_assets
                    SET current_revision = ?, width = ?, height = ?, size_bytes = ?,
                        mime_type = 'image/png', clarity_status = ?, warnings_json = ?, updated_at = ?
                    WHERE asset_id = ? AND owner_id = ?
                    """,
                    (
                        next_revision,
                        transformed.width,
                        transformed.height,
                        len(encoded),
                        "review_needed" if warnings else "clear",
                        json.dumps(warnings, ensure_ascii=False),
                        now,
                        asset_id,
                        owner_id,
                    ),
                )
        except Exception:
            stored_path.unlink(missing_ok=True)
            raise
        return self.get(asset_id, owner_id=owner_id)

    def get(self, asset_id: str, *, owner_id: str) -> QuestionInputBundle:
        with self._connect() as connection:
            asset = connection.execute(
                "SELECT * FROM question_capture_assets WHERE asset_id = ? AND owner_id = ?",
                (asset_id, owner_id),
            ).fetchone()
            if asset is None:
                raise KeyError(asset_id)
            rows = connection.execute(
                "SELECT * FROM question_capture_revisions WHERE asset_id = ? ORDER BY revision",
                (asset_id,),
            ).fetchall()
            recognition = connection.execute(
                """
                SELECT * FROM question_capture_recognitions
                WHERE asset_id = ? ORDER BY recognition_revision DESC LIMIT 1
                """,
                (asset_id,),
            ).fetchone()
        revisions = [
            QuestionMediaRevision(
                revision=row["revision"],
                source_revision=row["source_revision"],
                operation=row["operation"],
                width=row["width"],
                height=row["height"],
                mime_type=row["mime_type"],
                content_endpoint=f"/api/v1/question-capture/assets/{asset_id}/content?revision={row['revision']}",
                created_at=row["created_at"],
            )
            for row in rows
        ]
        warnings = json.loads(asset["warnings_json"])
        recognition_payload = {"recognition_warnings": warnings}
        if recognition is not None:
            status = recognition["status"]
            recognition_warnings = json.loads(recognition["warnings_json"])
            if recognition["source_media_revision"] != asset["current_revision"]:
                status = "stale"
                recognition_warnings = [
                    "图片已在本次识别后调整，请重新识别并校对最新版本。",
                    *recognition_warnings,
                ]
            recognition_payload = {
                "recognition_status": status,
                "recognition_revision": recognition["recognition_revision"],
                "recognition_source_revision": recognition["source_media_revision"],
                "recognition_mode": recognition["mode"],
                "recognition_provider": recognition["provider"],
                "recognition_model": recognition["model"],
                "stem_plain": recognition["stem_plain"],
                "stem_latex": recognition["stem_latex"],
                "options": json.loads(recognition["options_json"]),
                "requires_visual_reasoning": (
                    None if recognition["requires_visual_reasoning"] is None
                    else bool(recognition["requires_visual_reasoning"])
                ),
                "low_confidence_regions": json.loads(recognition["low_confidence_json"]),
                "recognition_warnings": recognition_warnings,
                "external_processing_consent": bool(recognition["external_consent"]),
                "teacher_review_note": recognition["teacher_review_note"],
            }
        return QuestionInputBundle(
            asset=QuestionMediaAsset(
                asset_id=asset["asset_id"],
                original_filename=asset["original_filename"],
                source=asset["source"],
                source_sha256=asset["source_sha256"],
                current_revision=asset["current_revision"],
                width=asset["width"],
                height=asset["height"],
                size_bytes=asset["size_bytes"],
                mime_type=asset["mime_type"],
                clarity_status=asset["clarity_status"],
                warnings=warnings,
                revisions=revisions,
                created_at=asset["created_at"],
                updated_at=asset["updated_at"],
            ),
            **recognition_payload,
        )

    def recognize(
        self,
        asset_id: str,
        command: QuestionRecognitionCommand,
        *,
        owner_id: str,
    ) -> QuestionInputBundle:
        if command.mode == "external" and not command.external_processing_consent:
            raise QuestionCaptureError("使用外部 OCR 前必须逐次确认本次图片处理")
        if command.mode == "local" and command.external_processing_consent:
            raise QuestionCaptureError("本地 OCR 不接受外部处理同意标记")
        provider = self.recognition_providers.get(command.mode)
        if provider is None:
            if command.mode == "external":
                raise QuestionCaptureError("外部 OCR 尚未配置 DeepSeek Vision 或 OpenAI 图像模型与 API Key")
            raise QuestionCaptureError("本地数学 OCR 尚未配置")

        with self._connect() as connection:
            asset = connection.execute(
                "SELECT * FROM question_capture_assets WHERE asset_id = ? AND owner_id = ?",
                (asset_id, owner_id),
            ).fetchone()
            if asset is None:
                raise KeyError(asset_id)
            media = connection.execute(
                "SELECT * FROM question_capture_revisions WHERE asset_id = ? AND revision = ?",
                (asset_id, asset["current_revision"]),
            ).fetchone()
            previous = connection.execute(
                "SELECT MAX(recognition_revision) AS value FROM question_capture_recognitions WHERE asset_id = ?",
                (asset_id,),
            ).fetchone()
        if media is None:
            raise QuestionCaptureError("题目图片当前版本不存在")
        try:
            result = provider.recognize(
                path=self._confined_path(media["stored_name"]),
                mime_type=media["mime_type"],
                teacher_id=owner_id,
            )
        except QuestionRecognitionError as exc:
            raise QuestionCaptureError(str(exc)) from exc
        if not result.stem_plain.strip():
            raise QuestionCaptureError("OCR 没有返回可校对的题面")

        next_revision = int(previous["value"] or 0) + 1
        now = self._now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO question_capture_recognitions (
                    asset_id, recognition_revision, source_media_revision, status,
                    mode, provider, model, external_consent, stem_plain, stem_latex,
                    options_json, requires_visual_reasoning, low_confidence_json,
                    warnings_json, teacher_review_note, created_at
                ) VALUES (?, ?, ?, 'draft', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', ?)
                """,
                (
                    asset_id,
                    next_revision,
                    asset["current_revision"],
                    command.mode,
                    provider.name,
                    provider.model,
                    int(command.external_processing_consent),
                    result.stem_plain.strip(),
                    result.stem_latex.strip(),
                    json.dumps([item.model_dump(mode="json") for item in result.options], ensure_ascii=False),
                    None if result.requires_visual_reasoning is None else int(result.requires_visual_reasoning),
                    json.dumps(
                        [item.model_dump(mode="json") for item in result.low_confidence_regions],
                        ensure_ascii=False,
                    ),
                    json.dumps(result.warnings, ensure_ascii=False),
                    now,
                ),
            )
        return self.get(asset_id, owner_id=owner_id)

    def review_recognition(
        self,
        asset_id: str,
        command: QuestionRecognitionReviewCommand,
        *,
        owner_id: str,
    ) -> QuestionInputBundle:
        with self._connect() as connection:
            asset = connection.execute(
                "SELECT * FROM question_capture_assets WHERE asset_id = ? AND owner_id = ?",
                (asset_id, owner_id),
            ).fetchone()
            if asset is None:
                raise KeyError(asset_id)
            previous = connection.execute(
                """
                SELECT * FROM question_capture_recognitions
                WHERE asset_id = ? ORDER BY recognition_revision DESC LIMIT 1
                """,
                (asset_id,),
            ).fetchone()
        if previous is None:
            raise QuestionCaptureError("请先识别题面，再保存校对结果")
        if previous["source_media_revision"] != asset["current_revision"]:
            raise QuestionCaptureError("图片已调整，请先重新识别最新版本")
        next_revision = int(previous["recognition_revision"]) + 1
        warnings = json.loads(previous["warnings_json"])
        if command.confirm:
            warnings = [item for item in warnings if "需对照原图校对" not in item]
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO question_capture_recognitions (
                    asset_id, recognition_revision, source_media_revision, status,
                    mode, provider, model, external_consent, stem_plain, stem_latex,
                    options_json, requires_visual_reasoning, low_confidence_json,
                    warnings_json, teacher_review_note, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    asset_id,
                    next_revision,
                    asset["current_revision"],
                    "confirmed" if command.confirm else "draft",
                    previous["mode"],
                    previous["provider"],
                    previous["model"],
                    previous["external_consent"],
                    command.stem_plain.strip(),
                    command.stem_latex.strip(),
                    json.dumps([item.model_dump(mode="json") for item in command.options], ensure_ascii=False),
                    previous["requires_visual_reasoning"],
                    previous["low_confidence_json"],
                    json.dumps(warnings, ensure_ascii=False),
                    command.note.strip(),
                    self._now(),
                ),
            )
        return self.get(asset_id, owner_id=owner_id)

    def content(
        self,
        asset_id: str,
        *,
        owner_id: str,
        revision: int | None = None,
    ) -> tuple[Path, str]:
        with self._connect() as connection:
            asset = connection.execute(
                "SELECT current_revision FROM question_capture_assets WHERE asset_id = ? AND owner_id = ?",
                (asset_id, owner_id),
            ).fetchone()
            if asset is None:
                raise KeyError(asset_id)
            selected_revision = revision or asset["current_revision"]
            row = connection.execute(
                "SELECT stored_name, mime_type FROM question_capture_revisions WHERE asset_id = ? AND revision = ?",
                (asset_id, selected_revision),
            ).fetchone()
        if row is None:
            raise KeyError(f"{asset_id}:{selected_revision}")
        path = self._confined_path(row["stored_name"])
        if not path.is_file():
            raise QuestionCaptureError("题目图片文件不存在")
        return path, row["mime_type"]

    def prepare_for_solve(
        self,
        reference: QuestionSolveReference,
        *,
        owner_id: str,
        request_id: str,
    ) -> PreparedQuestionInput:
        """Resolve one confirmed private bundle without exposing storage authority."""
        with self._connect() as connection:
            asset = connection.execute(
                "SELECT * FROM question_capture_assets WHERE asset_id = ? AND owner_id = ?",
                (reference.asset_id, owner_id),
            ).fetchone()
            if asset is None:
                raise KeyError(reference.asset_id)
            media = connection.execute(
                """
                SELECT * FROM question_capture_revisions
                WHERE asset_id = ? AND revision = ?
                """,
                (reference.asset_id, reference.media_revision),
            ).fetchone()
            recognition = connection.execute(
                """
                SELECT * FROM question_capture_recognitions
                WHERE asset_id = ? AND recognition_revision = ?
                """,
                (reference.asset_id, reference.recognition_revision),
            ).fetchone()
        if int(asset["current_revision"]) != reference.media_revision:
            raise QuestionCaptureError("题目图片版本已变化，请重新识别并确认后再解题")
        if media is None:
            raise QuestionCaptureError("指定的题目图片版本不存在")
        if recognition is None:
            raise QuestionCaptureError("指定的题面识别版本不存在")
        if recognition["status"] != "confirmed":
            raise QuestionCaptureError("题面尚未由教师确认，不能交给 Solve")
        if int(recognition["source_media_revision"]) != reference.media_revision:
            raise QuestionCaptureError("题面识别与图片版本不一致，请重新识别并确认")

        options = json.loads(recognition["options_json"])
        option_lines = [
            f"{str(item.get('key', '')).strip()}. {str(item.get('text', '')).strip()}"
            for item in options
            if str(item.get("key", "")).strip() and str(item.get("text", "")).strip()
        ]
        question_text = recognition["stem_plain"].strip()
        if option_lines:
            question_text = f"{question_text}\n" + "\n".join(option_lines)
        if not question_text:
            raise QuestionCaptureError("教师确认题面为空，不能交给 Solve")

        # Unknown is treated as visual-dependent: losing a diagram is worse than
        # requiring a fresh, explicit consent.
        requires_visual = recognition["requires_visual_reasoning"] != 0
        if requires_visual and not reference.visual_processing_consent:
            raise QuestionCaptureError("本题依赖原图；发送给视觉解题模型前必须逐次确认本次处理")

        image_content: bytes | None = None
        image_mime_type: str | None = None
        if requires_visual:
            path = self._confined_path(media["stored_name"])
            if not path.is_file():
                raise QuestionCaptureError("题目图片文件不存在")
            image_content = path.read_bytes()
            image_mime_type = media["mime_type"]

        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO question_capture_solve_uses (
                        request_id, owner_id, asset_id, media_revision,
                        recognition_revision, requires_visual_reasoning,
                        visual_processing_consent, image_prepared, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        request_id,
                        owner_id,
                        reference.asset_id,
                        reference.media_revision,
                        reference.recognition_revision,
                        int(requires_visual),
                        int(reference.visual_processing_consent),
                        int(image_content is not None),
                        self._now(),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise QuestionCaptureError("本次题面/视觉处理许可已使用，请重新发起解题") from exc
        return PreparedQuestionInput(
            question_text=question_text,
            asset_id=reference.asset_id,
            media_revision=reference.media_revision,
            recognition_revision=reference.recognition_revision,
            requires_visual_reasoning=requires_visual,
            visual_processing_consent=reference.visual_processing_consent,
            image_bytes=image_content,
            image_mime_type=image_mime_type,
        )

    def _open_image(self, content: bytes) -> tuple[Image.Image, str]:
        try:
            with Image.open(BytesIO(content)) as opened:
                image_format = str(opened.format or "").upper()
                if image_format not in self._FORMATS:
                    raise QuestionCaptureError("仅支持 PNG、JPEG 和 WebP 题目图片")
                if opened.width * opened.height > self.MAX_IMAGE_PIXELS:
                    raise QuestionCaptureError("题目图片像素过大，请裁剪或压缩后重试")
                image = ImageOps.exif_transpose(opened)
                image.load()
        except QuestionCaptureError:
            raise
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise QuestionCaptureError("题目图片格式无效或文件已损坏") from exc
        return image, image_format

    def _validate_dimensions_and_clarity(self, image: Image.Image) -> list[str]:
        width, height = image.size
        if width * height > self.MAX_IMAGE_PIXELS:
            raise QuestionCaptureError("题目图片像素过大，请裁剪或压缩后重试")
        if min(width, height) < self.MIN_SIDE_PIXELS or max(width, height) < self.MIN_LONG_SIDE_PIXELS:
            raise QuestionCaptureError("题目图片尺寸过小，无法可靠识别")
        gray = image.convert("L")
        contrast = float(ImageStat.Stat(gray).stddev[0])
        if contrast < 2.0:
            raise QuestionCaptureError("图片几乎没有可辨内容，请重新拍摄或上传")
        warnings: list[str] = []
        if min(width, height) < 480 or max(width, height) < 900:
            warnings.append("图片分辨率偏低，后续文字与公式识别可能需要人工校对。")
        if contrast < 12.0:
            warnings.append("图片对比度偏低，建议重新拍摄或增强后再识别。")
        return warnings

    def _confined_path(self, stored_name: str) -> Path:
        path = (self.file_root / Path(stored_name).name).resolve()
        if path.parent != self.file_root:
            raise QuestionCaptureError("题目图片路径无效")
        return path

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS question_capture_assets (
                    asset_id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    original_filename TEXT NOT NULL,
                    source TEXT NOT NULL,
                    source_sha256 TEXT NOT NULL,
                    current_revision INTEGER NOT NULL,
                    width INTEGER NOT NULL,
                    height INTEGER NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    mime_type TEXT NOT NULL,
                    clarity_status TEXT NOT NULL,
                    warnings_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_question_capture_owner
                    ON question_capture_assets(owner_id, updated_at DESC);
                CREATE TABLE IF NOT EXISTS question_capture_revisions (
                    asset_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    source_revision INTEGER,
                    operation TEXT NOT NULL,
                    operation_json TEXT NOT NULL,
                    stored_name TEXT NOT NULL,
                    width INTEGER NOT NULL,
                    height INTEGER NOT NULL,
                    mime_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (asset_id, revision),
                    FOREIGN KEY (asset_id) REFERENCES question_capture_assets(asset_id)
                );
                CREATE TABLE IF NOT EXISTS question_capture_recognitions (
                    asset_id TEXT NOT NULL,
                    recognition_revision INTEGER NOT NULL,
                    source_media_revision INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    external_consent INTEGER NOT NULL,
                    stem_plain TEXT NOT NULL,
                    stem_latex TEXT NOT NULL,
                    options_json TEXT NOT NULL,
                    requires_visual_reasoning INTEGER,
                    low_confidence_json TEXT NOT NULL,
                    warnings_json TEXT NOT NULL,
                    teacher_review_note TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (asset_id, recognition_revision),
                    FOREIGN KEY (asset_id) REFERENCES question_capture_assets(asset_id)
                );
                CREATE INDEX IF NOT EXISTS idx_question_capture_recognitions_asset
                    ON question_capture_recognitions(asset_id, recognition_revision DESC);
                CREATE TABLE IF NOT EXISTS question_capture_solve_uses (
                    request_id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    asset_id TEXT NOT NULL,
                    media_revision INTEGER NOT NULL,
                    recognition_revision INTEGER NOT NULL,
                    requires_visual_reasoning INTEGER NOT NULL,
                    visual_processing_consent INTEGER NOT NULL,
                    image_prepared INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (asset_id) REFERENCES question_capture_assets(asset_id)
                );
                CREATE INDEX IF NOT EXISTS idx_question_capture_solve_uses_owner
                    ON question_capture_solve_uses(owner_id, created_at DESC);
                """
            )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
