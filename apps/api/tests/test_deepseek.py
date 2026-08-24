from __future__ import annotations

import json

import pytest

from app.modules.deepseek import DeepSeekJsonClient, DeepSeekJsonResponseError
from app.modules.lesson_plans import DeepSeekLessonPlanProvider
from app.modules.question_variants import DeepSeekQuestionVariantProvider
from app.modules.solution_assistant import (
    DeepSeekSolutionProvider,
    SolutionRequest,
    SolutionVisualInput,
)


def test_deepseek_uses_chat_completions_json_mode(monkeypatch) -> None:
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(
                {"choices": [{"message": {"content": '{"answer":"4"}'}}]}
            ).encode()

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["authorization"] = request.headers["Authorization"]
        captured["payload"] = json.loads(request.data.decode())
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr("app.modules.deepseek.urlopen", fake_urlopen)
    client = DeepSeekJsonClient(
        api_key="test-secret", model="deepseek-v4-flash", timeout_seconds=23
    )
    result = client.request(
        instructions="解题并输出 JSON",
        input_text='{"question":"2+2"}',
        action="解题",
        output_schema={"schema": {"type": "object", "required": ["answer"]}},
    )

    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["authorization"] == "Bearer test-secret"
    assert captured["payload"]["model"] == "deepseek-v4-flash"
    assert captured["payload"]["response_format"] == {"type": "json_object"}
    assert captured["payload"]["thinking"] == {"type": "disabled"}
    assert captured["payload"]["max_tokens"] == 4096
    assert '"required": ["answer"]' in captured["payload"]["messages"][0]["content"]
    assert captured["timeout"] == 23
    assert json.loads(result["output"][0]["content"][0]["text"]) == {"answer": "4"}


def test_deepseek_normalizes_control_characters_fences_and_trailing_text(monkeypatch) -> None:
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            payload = {
                "choices": [{"message": {"content": '```json\n{"answer":"line\none","formula":"\\frac{1}{2}"}\n```\n补充说明'}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
            }
            return json.dumps(payload, ensure_ascii=False).encode()

    monkeypatch.setattr("app.modules.deepseek.urlopen", lambda *_args, **_kwargs: Response())
    result = DeepSeekJsonClient(api_key="test-secret").request(
        instructions="test", input_text="{}", action="test", max_tokens=900,
    )
    parsed = json.loads(result["output"][0]["content"][0]["text"])
    assert parsed == {"answer": "line\none", "formula": "\\frac{1}{2}"}


def test_deepseek_normalizes_unescaped_geometry_latex_commands() -> None:
    content = r'''{"steps":["证明 $AC \perp A_1D$，且 $\angle A=\theta$。","令 $u=\underbrace{a+b}_{2}$，再取 $\vec n$。","由 $\frac{a}{b}=\sqrt{2}$ 得 $x\to 0$，写成 $\left(x\right)$。"],"already_escaped":"$\\underbrace{x}_{1}$"}'''

    normalized = DeepSeekJsonClient._normalize_json(content)

    assert json.loads(normalized) == {
        "steps": [
            r"证明 $AC \perp A_1D$，且 $\angle A=\theta$。",
            r"令 $u=\underbrace{a+b}_{2}$，再取 $\vec n$。",
            r"由 $\frac{a}{b}=\sqrt{2}$ 得 $x\to 0$，写成 $\left(x\right)$。",
        ],
        "already_escaped": r"$\underbrace{x}_{1}$",
    }


def test_deepseek_retries_once_when_json_response_is_truncated(monkeypatch) -> None:
    requests = []

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(self.payload, ensure_ascii=False).encode()

    responses = iter(
        [
            Response(
                {
                    "choices": [
                        {
                            "finish_reason": "length",
                            "message": {
                                "content": '{"explanation":{"method":"解析几何","steps":["设点 Q 的坐标为'
                            },
                        }
                    ]
                }
            ),
            Response(
                {
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {
                                "content": json.dumps(
                                    {
                                        "explanation": {
                                            "method": "解析几何",
                                            "steps": ["建立参数方程并消去参数。"],
                                            "final_answer": "点 Q 在一条定直线上。",
                                        },
                                        "knowledge_points": ["轨迹方程"],
                                        "common_mistakes": [],
                                        "teaching_notes": [],
                                    },
                                    ensure_ascii=False,
                                )
                            },
                        }
                    ]
                }
            ),
        ]
    )

    def fake_urlopen(request, timeout):
        requests.append(json.loads(request.data.decode()))
        return next(responses)

    monkeypatch.setattr("app.modules.deepseek.urlopen", fake_urlopen)
    result = DeepSeekJsonClient(api_key="test-secret").request(
        instructions="test",
        input_text='{"question":"轨迹题"}',
        action="解题",
        max_tokens=4096,
    )

    assert len(requests) == 2
    assert requests[1]["max_tokens"] > requests[0]["max_tokens"]
    assert "上一份回答因长度截断" in requests[1]["messages"][-1]["content"]
    parsed = json.loads(result["output"][0]["content"][0]["text"])
    assert parsed["explanation"]["final_answer"] == "点 Q 在一条定直线上。"


def test_deepseek_stops_after_one_json_recovery_retry(monkeypatch) -> None:
    requests = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(
                {
                    "choices": [
                        {
                            "finish_reason": "length",
                            "message": {"content": '{"answer":"仍然只有半截'},
                        }
                    ]
                },
                ensure_ascii=False,
            ).encode()

    def fake_urlopen(request, timeout):
        requests.append(json.loads(request.data.decode()))
        return Response()

    monkeypatch.setattr("app.modules.deepseek.urlopen", fake_urlopen)

    with pytest.raises(DeepSeekJsonResponseError, match="格式恢复重试仍未成功"):
        DeepSeekJsonClient(api_key="test-secret").request(
            instructions="test",
            input_text='{"question":"轨迹题"}',
            action="解题",
            max_tokens=3000,
        )

    assert len(requests) == 2


def test_deepseek_json_recovery_requires_a_strict_compact_response(monkeypatch) -> None:
    requests = []

    class Response:
        def __init__(self, content: str):
            self.content = content

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(
                {"choices": [{"message": {"content": self.content}}]},
                ensure_ascii=False,
            ).encode()

    responses = iter(
        [
            Response('{"answer":"被截断'),
            Response('{"answer":"已恢复"}'),
        ]
    )

    def fake_urlopen(request, timeout):
        requests.append(json.loads(request.data.decode()))
        return next(responses)

    monkeypatch.setattr("app.modules.deepseek.urlopen", fake_urlopen)

    DeepSeekJsonClient(api_key="test-secret").request(
        instructions="test",
        input_text='{"question":"圆锥曲线压轴题"}',
        action="辅助命题",
        max_tokens=5000,
        recovery_instruction=(
            "总输出不得超过 6000 个中文字符；"
            "每个解析步骤不得超过 220 个中文字符。"
        ),
    )

    recovery_instruction = requests[1]["messages"][-1]["content"]
    assert "总输出不得超过 6000 个中文字符" in recovery_instruction
    assert "每个解析步骤不得超过 220 个中文字符" in recovery_instruction


def test_deepseek_solution_provider_uses_configured_vision_model_and_image_block(monkeypatch) -> None:
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            content = {
                "explanation": {
                    "method": "图形分析",
                    "steps": ["结合原图条件。"],
                    "final_answer": "待教师核对",
                },
                "knowledge_points": [],
                "common_mistakes": [],
                "teaching_notes": [],
            }
            return json.dumps({
                "choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}]
            }, ensure_ascii=False).encode()

    def fake_urlopen(request, timeout):
        captured["payload"] = json.loads(request.data.decode())
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr("app.modules.deepseek.urlopen", fake_urlopen)
    provider = DeepSeekSolutionProvider(
        api_key="test-secret",
        model="deepseek-v4-flash",
        vision_model="deepseek-v4-flash-vision-exp",
        base_url="https://api.deepseek.com",
    )
    provider.solve(
        SolutionRequest(question_text="如图，求角 A 的大小。"),
        SolutionVisualInput(
            asset_id="qcap_1",
            media_revision=1,
            recognition_revision=2,
            requires_visual_reasoning=True,
            visual_processing_consent=True,
            image_bytes=b"private-image",
            image_mime_type="image/png",
        ),
    )

    payload = captured["payload"]
    assert payload["model"] == "deepseek-v4-flash-vision-exp"
    assert payload["messages"][1]["content"][0]["type"] == "text"
    prompt = json.loads(payload["messages"][1]["content"][0]["text"])
    assert "visual_grounding_requirements" in prompt
    assert "不得仅凭 OCR 题面猜测图形关系" in "".join(
        prompt["visual_grounding_requirements"]
    )
    image_block = payload["messages"][1]["content"][1]
    assert image_block["type"] == "image_url"
    assert image_block["image_url"]["url"].startswith("data:image/png;base64,")
    assert image_block["image_url"]["detail"] == "original"


def test_deepseek_providers_initialize_openai_compatible_fields() -> None:
    common = {
        "api_key": "test-secret",
        "model": "deepseek-v4-flash",
        "base_url": "https://api.deepseek.com",
    }

    providers = [
        DeepSeekLessonPlanProvider(**common),
        DeepSeekQuestionVariantProvider(**common),
        DeepSeekSolutionProvider(**common),
    ]

    assert all(provider.reasoning_effort == "low" for provider in providers)
    assert all(provider.api_key == "test-secret" for provider in providers)
    assert all(provider.timeout_seconds == 90 for provider in providers)
