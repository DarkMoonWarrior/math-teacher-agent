from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.modules.model_operations import ModelRunRecorder, NullModelRunRecorder

from .schemas import LowConfidenceRegion, QuestionOption


class QuestionRecognitionError(RuntimeError):
    pass


@dataclass(frozen=True)
class QuestionRecognitionResult:
    stem_plain: str
    stem_latex: str = ""
    options: list[QuestionOption] = field(default_factory=list)
    low_confidence_regions: list[LowConfidenceRegion] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    requires_visual_reasoning: bool | None = None


class QuestionRecognitionProvider(Protocol):
    name: str
    model: str

    def recognize(
        self,
        *,
        path: Path,
        mime_type: str,
        teacher_id: str,
    ) -> QuestionRecognitionResult: ...


class LocalQuestionRecognitionProvider:
    """Optional, private-only pix2text adapter for a single question image."""

    name = "local_math_ocr"
    model = "pix2text-1.1.6"

    def recognize(
        self,
        *,
        path: Path,
        mime_type: str,
        teacher_id: str,
    ) -> QuestionRecognitionResult:
        del mime_type, teacher_id
        try:
            from PIL import Image
            from app.modules.pdf_imports.math_ocr import _get_engine

            engine = _get_engine()
            with Image.open(path) as opened:
                image = opened.convert("RGB")
                page = engine.recognize_page(
                    image,
                    page_number=0,
                    page_id=f"question-capture-{path.stem}",
                    table_as_image=True,
                )
            elements = sorted(
                (item for item in page.elements if str(getattr(item, "text", "")).strip()),
                key=lambda item: (float(item.box[1]), float(item.box[0])),
            )
        except ImportError as exc:
            raise QuestionRecognitionError(
                "本地数学 OCR 尚未安装。可安装 API 的 math-ocr 可选依赖，或逐次同意使用已配置的外部 OCR。"
            ) from exc
        except Exception as exc:  # pragma: no cover - optional model/runtime boundary
            raise QuestionRecognitionError(f"本地数学 OCR 失败：{exc}") from exc

        lines = [str(item.text).strip() for item in elements]
        if not lines:
            raise QuestionRecognitionError("本地数学 OCR 没有识别到可用题面，请裁剪图片或人工录入")
        options, stem_lines = _split_options(lines)
        return QuestionRecognitionResult(
            stem_plain="\n".join(stem_lines).strip(),
            stem_latex="\n".join(stem_lines).strip(),
            options=options,
            warnings=["本地识别草稿需对照原图校对，尤其是上下标、根号、分式和几何标注。"],
        )


class OpenAIQuestionRecognitionProvider:
    """External vision adapter. The caller must enforce per-action consent."""

    name = "openai"
    MAX_EXTERNAL_BYTES = 15 * 1024 * 1024

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: int = 90,
        recorder: ModelRunRecorder | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("OpenAI API Key 不能为空")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.recorder = recorder or NullModelRunRecorder()

    def recognize(
        self,
        *,
        path: Path,
        mime_type: str,
        teacher_id: str,
    ) -> QuestionRecognitionResult:
        content = path.read_bytes()
        if len(content) > self.MAX_EXTERNAL_BYTES:
            raise QuestionRecognitionError("发送到外部 OCR 的题目图片不能超过 15 MB")
        encoded = base64.b64encode(content).decode("ascii")
        payload = {
            "model": self.model,
            "instructions": (
                "你是高中数学单题 OCR 助手，只忠实转录图片，不解题、不补题。"
                "区分普通题面与 LaTeX 题面，拆出选择题选项。无法辨认处保留原样并列入低置信度区域。"
                "若题目依赖坐标系、几何图、函数图像、表格或其他视觉条件，将 requires_visual_reasoning 设为 true。"
            ),
            "input": [{
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "请识别这张私人题目图片并返回校对草稿。"},
                    {"type": "input_image", "image_url": f"data:{mime_type};base64,{encoded}", "detail": "original"},
                ],
            }],
            "text": {"format": self._output_format(), "verbosity": "low"},
            "safety_identifier": hashlib.sha256(
                f"math-ai-question-ocr:{teacher_id}".encode("utf-8")
            ).hexdigest()[:32],
            "store": False,
        }
        request = Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with self.recorder.track(
            feature="private_question_ocr",
            provider=self.name,
            model=self.model,
            prompt_version="private-question-ocr-v1",
            actor_id=teacher_id,
        ) as run:
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    raw = json.loads(response.read().decode("utf-8"))
            except HTTPError as exc:
                details = exc.read().decode("utf-8", errors="replace")[:500]
                raise QuestionRecognitionError(f"外部 OCR 返回 HTTP {exc.code}：{details}") from exc
            except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
                raise QuestionRecognitionError(f"外部 OCR 调用失败：{exc}") from exc
            run.capture_response(raw)
        try:
            parsed = json.loads(self._output_text(raw))
            return QuestionRecognitionResult(
                stem_plain=str(parsed["stem_plain"]).strip(),
                stem_latex=str(parsed["stem_latex"]).strip(),
                options=[QuestionOption.model_validate(item) for item in parsed["options"]],
                low_confidence_regions=[
                    LowConfidenceRegion.model_validate(item) for item in parsed["low_confidence_regions"]
                ],
                warnings=[str(item) for item in parsed["warnings"]],
                requires_visual_reasoning=bool(parsed["requires_visual_reasoning"]),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise QuestionRecognitionError(f"外部 OCR 返回内容不符合题面结构：{exc}") from exc

    @staticmethod
    def _output_text(payload: dict) -> str:
        for item in payload.get("output", []):
            if item.get("type") == "message":
                for content in item.get("content", []):
                    if content.get("type") == "output_text":
                        return str(content["text"])
        raise KeyError("output_text")

    @staticmethod
    def _output_format() -> dict:
        option = {
            "type": "object",
            "additionalProperties": False,
            "properties": {"key": {"type": "string"}, "text": {"type": "string"}},
            "required": ["key", "text"],
        }
        region = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "text": {"type": "string"},
                "reason": {"type": "string"},
                "confidence": {"type": ["number", "null"], "minimum": 0, "maximum": 1},
                "box": {
                    "type": ["array", "null"],
                    "items": {"type": "number"},
                    "minItems": 4,
                    "maxItems": 4,
                },
            },
            "required": ["text", "reason", "confidence", "box"],
        }
        return {
            "type": "json_schema",
            "name": "private_question_ocr",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "stem_plain": {"type": "string"},
                    "stem_latex": {"type": "string"},
                    "options": {"type": "array", "items": option},
                    "low_confidence_regions": {"type": "array", "items": region},
                    "warnings": {"type": "array", "items": {"type": "string"}},
                    "requires_visual_reasoning": {"type": "boolean"},
                },
                "required": [
                    "stem_plain", "stem_latex", "options", "low_confidence_regions",
                    "warnings", "requires_visual_reasoning",
                ],
            },
        }


def _split_options(lines: list[str]) -> tuple[list[QuestionOption], list[str]]:
    options: list[QuestionOption] = []
    stem: list[str] = []
    for line in lines:
        stripped = line.strip()
        if len(stripped) >= 3 and stripped[0].upper() in "ABCDEFG" and stripped[1] in ".、．)）":
            options.append(QuestionOption(key=stripped[0].upper(), text=stripped[2:].strip()))
        else:
            stem.append(stripped)
    return options, stem
