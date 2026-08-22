from __future__ import annotations

import hashlib
import json
import base64
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.modules.model_operations import ModelRunRecorder, NullModelRunRecorder
from app.modules.deepseek import (
    DeepSeekClientError,
    DeepSeekJsonClient,
    DeepSeekJsonResponseError,
)
from app.modules.solution_assistant.schemas import (
    GeneratedSolution,
    SolutionRequest,
    SolutionVisualInput,
)


class SolutionProviderError(RuntimeError):
    pass


class SolutionProviderResponseError(SolutionProviderError):
    """The model responded, but the response could not satisfy the contract."""


class SolutionProvider(Protocol):
    name: str
    model: str

    def solve(
        self,
        request: SolutionRequest,
        visual_input: SolutionVisualInput | None = None,
    ) -> GeneratedSolution: ...


class OpenAISolutionProvider:
    name = "openai"
    vision_model: str | None = None

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        reasoning_effort: str = "low",
        timeout_seconds: int = 90,
        recorder: ModelRunRecorder | None = None,
        vision_model: str | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("OpenAI API Key 不能为空")
        self.api_key = api_key
        self.model = model
        self.vision_model = vision_model or model
        self.reasoning_effort = reasoning_effort
        self.timeout_seconds = timeout_seconds
        self.recorder = recorder or NullModelRunRecorder()

    def solve(
        self,
        request_data: SolutionRequest,
        visual_input: SolutionVisualInput | None = None,
    ) -> GeneratedSolution:
        task = (
            "给出一种与常规解法不同但完整严谨的第二种解法。"
            if request_data.solution_mode == "alternative"
            else "给出适合高中教师审核和讲解的标准解法。"
        )
        prompt = {
            "task": task,
            "question": request_data.question_text,
            "teacher_instruction": request_data.teacher_instruction,
        }
        used_model = self.vision_model if visual_input is not None else self.model
        if visual_input is not None:
            if visual_input.image_bytes is None or not visual_input.image_mime_type:
                raise SolutionProviderError("视觉解题输入缺少受控图片内容")
            if not visual_input.visual_processing_consent:
                raise SolutionProviderError("视觉解题缺少本次图片处理同意")
            prompt["visual_grounding_requirements"] = [
                "原图是本题事实输入的一部分，必须核对图中的点、线、面标签与虚实线",
                "不得仅凭 OCR 题面猜测图形关系，也不得把图中未明确给出的关系当作已知",
                "若图形标签或连线无法可靠辨认，必须在步骤和最终答案中明确要求教师复核",
            ]
        prompt_text = json.dumps(prompt, ensure_ascii=False)
        provider_input: str | list[dict[str, object]] = prompt_text
        if visual_input is not None:
            provider_input = [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt_text},
                        {
                            "type": "input_image",
                            "image_url": self._data_url(visual_input),
                            "detail": "original",
                        },
                    ],
                }
            ]
        payload = {
            "model": used_model,
            "instructions": (
                "你是中国高中数学教研员，使用人教A版术语和新高考答题规范解题。"
                "必须检查题目条件是否充分，逐步给出依据，不能虚构题源、数值或验证结论。"
                "如果题目本身有歧义或无解，应在步骤与最终答案中明确指出。"
                "所有数学表达必须使用 KaTeX 兼容的 LaTeX：行内公式用单个 $...$ 包裹，"
                "需要单独成行的公式用 $$...$$ 包裹；中文说明必须放在公式分隔符之外，"
                "不要使用 Markdown 代码块，也不要把 LaTeX 命令作为未分隔的普通文字输出。"
                "输出将交由教师复核，不要声称已经程序验证。"
            ),
            "input": provider_input,
            "reasoning": {"effort": self.reasoning_effort},
            "text": {"format": self._output_format(), "verbosity": "medium"},
            "safety_identifier": hashlib.sha256(
                f"math-ai-solver:{request_data.teacher_id}".encode("utf-8")
            ).hexdigest()[:32],
            "store": False,
        }
        request = Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with self.recorder.track(
            feature="solution_assistant",
            provider=self.name,
            model=used_model,
            prompt_version=(
                "solution-assistant-v3-visual-grounding"
                if visual_input is not None
                else "solution-assistant-v2-math-display"
            ),
            actor_id=request_data.teacher_id,
        ) as run:
            raw = (
                self._request(payload, request, visual_input)
                if visual_input is not None
                else self._request(payload, request)
            )
            run.capture_response(raw)
            if raw.get("status") == "incomplete":
                raise SolutionProviderError("OpenAI 返回未完成结果，请缩短题目或要求后重试")
            try:
                return GeneratedSolution.model_validate(
                    json.loads(self._extract_output_text(raw))
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise SolutionProviderError(f"OpenAI 返回内容不符合解题结构：{exc}") from exc

    def _request(
        self,
        payload: dict,
        request: Request,
        visual_input: SolutionVisualInput | None = None,
    ) -> dict:
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")[:500]
            raise SolutionProviderError(f"OpenAI 返回 HTTP {exc.code}：{details}") from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise SolutionProviderError(f"OpenAI 解题失败：{exc}") from exc

    @staticmethod
    def _data_url(visual_input: SolutionVisualInput) -> str:
        if visual_input.image_bytes is None or not visual_input.image_mime_type:
            raise SolutionProviderError("视觉解题输入缺少受控图片内容")
        encoded = base64.b64encode(visual_input.image_bytes).decode("ascii")
        return f"data:{visual_input.image_mime_type};base64,{encoded}"

    @staticmethod
    def _extract_output_text(payload: dict) -> str:
        for item in payload.get("output", []):
            if item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    return str(content["text"])
        raise KeyError("output_text")

    @staticmethod
    def _output_format() -> dict:
        explanation = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "method": {"type": "string"},
                "steps": {
                    "type": "array",
                    "description": (
                        "中文说明在公式分隔符外；行内公式使用 $...$，独立公式使用 $$...$$"
                    ),
                    "items": {"type": "string"},
                },
                "final_answer": {
                    "type": "string",
                    "description": (
                        "中文说明在公式分隔符外；行内公式使用 $...$，独立公式使用 $$...$$"
                    ),
                },
            },
            "required": ["method", "steps", "final_answer"],
        }
        properties = {
            "explanation": explanation,
            "knowledge_points": {"type": "array", "items": {"type": "string"}},
            "common_mistakes": {"type": "array", "items": {"type": "string"}},
            "teaching_notes": {"type": "array", "items": {"type": "string"}},
        }
        return {
            "type": "json_schema",
            "name": "high_school_math_solution",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": properties,
                "required": list(properties),
            },
        }


class DeepSeekSolutionProvider(OpenAISolutionProvider):
    name = "deepseek"

    def __init__(
        self, *, api_key: str, model: str, base_url: str,
        vision_model: str | None = None,
        timeout_seconds: int = 90, recorder=None, **_kwargs,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.vision_model = vision_model
        self.reasoning_effort = "low"
        self.timeout_seconds = timeout_seconds
        self.recorder = recorder or NullModelRunRecorder()
        self.client = DeepSeekJsonClient(
            api_key=api_key, model=model, base_url=base_url,
            timeout_seconds=timeout_seconds,
        )
        self.vision_client = (
            DeepSeekJsonClient(
                api_key=api_key,
                model=vision_model,
                base_url=base_url,
                timeout_seconds=timeout_seconds,
            )
            if vision_model
            else None
        )

    def _request(
        self,
        payload: dict,
        request: Request,
        visual_input: SolutionVisualInput | None = None,
    ) -> dict:
        try:
            client = self.vision_client if visual_input is not None else self.client
            if client is None:
                raise SolutionProviderError("DeepSeek 视觉解题模型尚未配置")
            input_value = payload["input"]
            input_text = (
                str(input_value)
                if isinstance(input_value, str)
                else str(input_value[0]["content"][0]["text"])
            )
            return client.request(
                instructions=payload["instructions"],
                input_text=input_text,
                action="视觉解题" if visual_input is not None else "解题",
                output_schema=payload.get("text", {}).get("format"),
                max_tokens=3000,
                image_data_url=(
                    self._data_url(visual_input)
                    if visual_input is not None
                    else None
                ),
            )
        except DeepSeekJsonResponseError as exc:
            raise SolutionProviderResponseError(str(exc)) from exc
        except DeepSeekClientError as exc:
            raise SolutionProviderError(str(exc)) from exc
