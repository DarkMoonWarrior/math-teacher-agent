from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zipfile import BadZipFile, ZipFile

from app.modules.model_operations import ModelRunRecorder, NullModelRunRecorder


class OCRProviderError(RuntimeError):
    pass


def _load_model_json_with_latex(message: str) -> dict:
    """Decode model JSON without turning LaTeX commands into JSON escapes."""
    value = message.strip()
    if value.startswith("```"):
        value = re.sub(
            r"^```(?:json)?\s*|\s*```$",
            "",
            value,
            flags=re.IGNORECASE,
        )

    protected: list[str] = []
    index = 0
    inside_string = False
    while index < len(value):
        character = value[index]
        if character == '"':
            protected.append(character)
            inside_string = not inside_string
            index += 1
            continue
        if inside_string and ord(character) < 0x20:
            protected.append(json.dumps(character)[1:-1])
            index += 1
            continue
        if not inside_string or character != "\\":
            protected.append(character)
            index += 1
            continue
        if index + 1 >= len(value):
            protected.append("\\\\")
            index += 1
            continue

        escaped = value[index + 1]
        if escaped in {'"', "\\", "/"}:
            protected.extend((character, escaped))
            index += 2
            continue
        if escaped == "u" and re.fullmatch(r"[0-9a-fA-F]{4}", value[index + 2:index + 6]):
            protected.append(value[index:index + 6])
            index += 6
            continue
        following = value[index + 2] if index + 2 < len(value) else ""
        looks_like_latex_command = (
            escaped not in "bfnrt"
            or ("A" <= following <= "Z")
            or ("a" <= following <= "z")
        )
        if looks_like_latex_command:
            protected.extend(("\\", character, escaped))
        else:
            protected.extend((character, escaped))
        index += 2

    parsed = json.loads("".join(protected))
    if not isinstance(parsed, dict):
        raise TypeError("顶层结果不是对象")
    return parsed


def _recover_text_from_model_json_envelope(message: str) -> str:
    """Salvage the text field when a long model response damages its JSON quoting."""
    value = message.strip()
    if value.startswith("```"):
        value = re.sub(
            r"^```(?:json)?\s*|\s*```$",
            "",
            value,
            flags=re.IGNORECASE,
        )
    start = re.search(r'"text"\s*:\s*"', value)
    if not start:
        return ""
    endings = list(re.finditer(r'"\s*,\s*"warnings"\s*:', value[start.end():]))
    if not endings:
        return ""
    end = start.end() + endings[-1].start()
    recovered = value[start.end():end].strip()
    recovered = recovered.replace('\\"', '"').replace("\\\\", "\\")
    return recovered.strip()


def _render_pdf_pages_as_jpeg(
    path: Path,
    *,
    dpi: int,
    max_pages: int,
) -> list[bytes]:
    """Render PDF pages with the API's required PDFium dependency."""
    try:
        import pypdfium2 as pdfium

        document = pdfium.PdfDocument(path)
        try:
            if len(document) > max_pages:
                raise OCRProviderError(f"单次最多处理 {max_pages} 页 PDF")
            rendered: list[bytes] = []
            for index in range(len(document)):
                page = document[index]
                try:
                    bitmap = page.render(scale=dpi / 72)
                    try:
                        image = bitmap.to_pil().convert("RGB")
                        output = BytesIO()
                        image.save(output, format="JPEG", quality=90)
                        rendered.append(output.getvalue())
                    finally:
                        bitmap.close()
                finally:
                    page.close()
            return rendered
        finally:
            document.close()
    except OCRProviderError:
        raise
    except Exception as exc:
        raise OCRProviderError(f"PDF 页面渲染失败：{exc}") from exc


@dataclass(frozen=True)
class OCRTextResult:
    text: str
    warnings: list[str] = field(default_factory=list)


class OpenAIResourceOCRProvider:
    """Small Responses API adapter; consent is enforced by PrivateLibrary."""

    name = "openai"
    MAX_EXTERNAL_BYTES = 20 * 1024 * 1024

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

    def extract(
        self, *, path: Path, mime_type: str, filename: str, teacher_id: str
    ) -> OCRTextResult:
        content = path.read_bytes()
        if len(content) > self.MAX_EXTERNAL_BYTES:
            raise OCRProviderError("发送到 OCR 服务的单个文件不能超过 20 MB")
        media = self._media_inputs(content, mime_type=mime_type, filename=filename)
        payload = {
            "model": self.model,
            "instructions": (
                "你是高中数学资料 OCR 助手。忠实转录文件中的中文、数字、公式、题号、选项、答案与解析。"
                "数学公式优先写为可读的 LaTeX；不补题、不改题、不推导答案。无法辨认处使用【无法辨认】。"
            ),
            "input": [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "请逐页转录这份私人教学资料，并返回结构化结果。"},
                        *media,
                    ],
                }
            ],
            "text": {"format": self._output_format(), "verbosity": "low"},
            "safety_identifier": hashlib.sha256(
                f"math-ai-library-ocr:{teacher_id}".encode("utf-8")
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
            feature="private_resource_ocr",
            provider=self.name,
            model=self.model,
            prompt_version="private-resource-ocr-v1",
            actor_id=teacher_id,
        ) as run:
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    raw = json.loads(response.read().decode("utf-8"))
            except HTTPError as exc:
                details = exc.read().decode("utf-8", errors="replace")[:500]
                raise OCRProviderError(f"OpenAI OCR 返回 HTTP {exc.code}：{details}") from exc
            except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
                raise OCRProviderError(f"OpenAI OCR 调用失败：{exc}") from exc
            run.capture_response(raw)
            try:
                parsed = json.loads(self._output_text(raw))
                return OCRTextResult(text=str(parsed["text"]), warnings=list(parsed["warnings"]))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise OCRProviderError(f"OCR 返回内容不符合预期结构：{exc}") from exc

    @staticmethod
    def _media_inputs(content: bytes, *, mime_type: str, filename: str) -> list[dict]:
        if mime_type.startswith("image/"):
            encoded = base64.b64encode(content).decode("ascii")
            return [{
                "type": "input_image",
                "image_url": f"data:{mime_type};base64,{encoded}",
                "detail": "original",
            }]
        if mime_type.endswith("wordprocessingml.document"):
            try:
                with ZipFile(BytesIO(content)) as archive:
                    entries = [
                        name for name in archive.namelist()
                        if name.startswith("word/media/") and Path(name).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
                    ][:12]
                    if not entries:
                        raise OCRProviderError("DOCX 中没有可供 OCR 的 PNG、JPEG 或 WebP 图片")
                    mime_by_suffix = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
                    return [
                        {
                            "type": "input_image",
                            "image_url": f"data:{mime_by_suffix[Path(name).suffix.lower()]};base64,{base64.b64encode(archive.read(name)).decode('ascii')}",
                            "detail": "original",
                        }
                        for name in entries
                    ]
            except BadZipFile as exc:
                raise OCRProviderError("DOCX 压缩结构损坏，无法提取内嵌图片") from exc
        encoded = base64.b64encode(content).decode("ascii")
        return [{
            "type": "input_file",
            "filename": filename,
            "file_data": f"data:{mime_type};base64,{encoded}",
        }]

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
        return {
            "type": "json_schema",
            "name": "private_resource_ocr",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "text": {"type": "string"},
                    "warnings": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["text", "warnings"],
            },
        }


class DeepSeekResourceOCRProvider:
    """Render private resources into bounded images for DeepSeek Vision transcription."""

    name = "deepseek"
    MAX_EXTERNAL_BYTES = 50 * 1024 * 1024
    MAX_PDF_PAGES = 100

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "deepseek-v4-flash-vision-exp",
        base_url: str = "https://api.deepseek.com",
        timeout_seconds: int = 90,
        recorder: ModelRunRecorder | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("大模型 API Key 不能为空")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.recorder = recorder or NullModelRunRecorder()

    def extract(
        self, *, path: Path, mime_type: str, filename: str, teacher_id: str
    ) -> OCRTextResult:
        content = path.read_bytes()
        if len(content) > self.MAX_EXTERNAL_BYTES:
            raise OCRProviderError("发送到大模型的单个文件不能超过 50 MB")
        images = self._page_images(
            content,
            path=path,
            mime_type=mime_type,
        )
        pages: list[str] = []
        warnings: list[str] = []
        for index, (page_mime, page_content) in enumerate(images, start=1):
            parsed = self._recognize_page(
                content=page_content,
                mime_type=page_mime,
                page_number=index,
                page_count=len(images),
                teacher_id=teacher_id,
            )
            page_text = str(parsed.get("text", "")).strip()
            if page_text:
                pages.append(f"【第 {index} 页】\n{page_text}")
            page_warnings = parsed.get("warnings", [])
            if not isinstance(page_warnings, list):
                raise OCRProviderError(f"大模型第 {index} 页 warnings 不是数组")
            warnings.extend(
                f"第 {index} 页：{value}"
                for value in page_warnings
                if str(value).strip()
            )
        if not pages:
            raise OCRProviderError("大模型没有从文件中提取到可读题目")
        return OCRTextResult(
            text="\n\n".join(pages),
            warnings=list(dict.fromkeys([
                *warnings,
                "大模型已生成中文 + LaTeX 校对稿；请对照原 PDF 确认题面、答案和解析。",
            ])),
        )

    def _recognize_page(
        self,
        *,
        content: bytes,
        mime_type: str,
        page_number: int,
        page_count: int,
        teacher_id: str,
    ) -> dict:
        encoded = base64.b64encode(content).decode("ascii")
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是高中数学 PDF 题目识别助手。忠实提取页面中的题号、完整题干、选项、"
                        "答案和解析，忽略页眉、页脚、目录与无关说明。中文必须正常可读；数学公式"
                        "统一写成 $LaTeX$。不得解题、补题或猜测看不清的内容；无法辨认处写入 warnings。"
                        "只返回包含 text 和 warnings 的 JSON；JSON 字符串中的 LaTeX 反斜杠必须写成双反斜杠。"
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                f"这是私人 PDF 的第 {page_number}/{page_count} 页。"
                                "请提取本页可读的高中数学题目内容并保持原顺序。"
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{encoded}",
                                "detail": "original",
                            },
                        },
                    ],
                },
            ],
            "response_format": {"type": "json_object"},
            "thinking": {"type": "disabled"},
            "max_tokens": 8192,
            "stream": False,
        }
        request = Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with self.recorder.track(
            feature="private_resource_ocr",
            provider=self.name,
            model=self.model,
            prompt_version="private-resource-deepseek-ocr-v1",
            actor_id=teacher_id,
        ) as run:
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    raw = json.loads(response.read().decode("utf-8"))
            except HTTPError as exc:
                details = exc.read().decode("utf-8", errors="replace")[:500]
                raise OCRProviderError(
                    f"大模型视觉识别返回 HTTP {exc.code}：{details}"
                ) from exc
            except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
                raise OCRProviderError(f"大模型视觉识别调用失败：{exc}") from exc
            run.capture_response(raw)
        try:
            message = str(raw["choices"][0]["message"]["content"]).strip()
            try:
                return _load_model_json_with_latex(message)
            except (TypeError, ValueError, json.JSONDecodeError):
                recovered = _recover_text_from_model_json_envelope(message)
                if recovered:
                    return {
                        "text": recovered,
                        "warnings": [
                            "大模型返回格式不完整，已保留可读正文；请重点核对本页。"
                        ],
                    }
                raise
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise OCRProviderError(
                f"大模型视觉识别返回内容不符合预期结构：{exc}"
            ) from exc

    @classmethod
    def _page_images(
        cls,
        content: bytes,
        *,
        path: Path,
        mime_type: str,
    ) -> list[tuple[str, bytes]]:
        if mime_type.startswith("image/"):
            return [(mime_type, content)]
        if mime_type == "application/pdf":
            return [
                ("image/jpeg", page)
                for page in _render_pdf_pages_as_jpeg(
                    path,
                    dpi=180,
                    max_pages=cls.MAX_PDF_PAGES,
                )
            ]
        if mime_type.endswith("wordprocessingml.document"):
            try:
                with ZipFile(BytesIO(content)) as archive:
                    entries = [
                        name for name in archive.namelist()
                        if name.startswith("word/media/")
                        and Path(name).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
                    ][: cls.MAX_PDF_PAGES]
                    if not entries:
                        raise OCRProviderError("DOCX 中没有可供大模型识别的图片")
                    mime_by_suffix = {
                        ".png": "image/png",
                        ".jpg": "image/jpeg",
                        ".jpeg": "image/jpeg",
                        ".webp": "image/webp",
                    }
                    return [
                        (mime_by_suffix[Path(name).suffix.lower()], archive.read(name))
                        for name in entries
                    ]
            except BadZipFile as exc:
                raise OCRProviderError("DOCX 压缩结构损坏，无法提取图片") from exc
        raise OCRProviderError("大模型识别当前只支持 PDF、图片和含图片的 DOCX")


class LocalMathOCRProvider:
    """Rebuild readable Chinese and LaTeX from rendered pages without uploading files."""

    name = "local_math_ocr"

    def __init__(self, progress=None) -> None:
        self.progress = progress

    def extract(
        self, *, path: Path, mime_type: str, filename: str, teacher_id: str
    ) -> OCRTextResult:
        if mime_type != "application/pdf":
            raise OCRProviderError("本地数学 OCR 当前只支持 PDF")
        try:
            import io
            from PIL import Image
            from app.modules.pdf_imports.math_ocr import _get_engine

            engine = _get_engine()
            pages: list[str] = []
            rendered_pages = _render_pdf_pages_as_jpeg(
                path,
                dpi=220,
                max_pages=DeepSeekResourceOCRProvider.MAX_PDF_PAGES,
            )
            total_pages = len(rendered_pages)
            for index, page_content in enumerate(rendered_pages):
                if self.progress:
                    self.progress(index, total_pages, f"正在识别第 {index + 1}/{total_pages} 页")
                image = Image.open(io.BytesIO(page_content)).convert("RGB")
                recognized = engine.recognize_page(
                    image,
                    page_number=index,
                    page_id=f"library-{path.stem}-{index + 1}",
                    table_as_image=True,
                )
                elements = sorted(
                    (item for item in recognized.elements if str(getattr(item, "text", "")).strip()),
                    key=lambda item: (float(item.box[1]), float(item.box[0])),
                )
                text = "\n".join(str(item.text).strip() for item in elements)
                pages.append(f"【第 {index + 1} 页】\n{text}")
            if self.progress:
                self.progress(total_pages, total_pages, "正在保存 OCR 草稿")
        except OCRProviderError:
            raise
        except Exception as exc:  # pragma: no cover - model/runtime boundary
            raise OCRProviderError(f"本地数学 OCR 失败：{exc}") from exc
        return OCRTextResult(
            text="\n\n".join(pages),
            warnings=[
                "本地数学 OCR 已生成含 LaTeX 的可读草稿；公式、选项和图表仍须对照原页确认。"
            ],
        )
