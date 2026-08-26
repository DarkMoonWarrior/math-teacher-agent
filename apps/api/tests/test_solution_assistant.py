import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.question_bank import QuestionBank
from app.modules.solution_assistant import (
    GeneratedSolution,
    SolutionAssistant,
    SolutionExplanation,
    SolutionRequest,
    SolutionResult,
    SolutionVisualInput,
)
from app.modules.solution_assistant.providers import OpenAISolutionProvider
from app.routes.questions import get_question_bank


client = TestClient(app)


class FakeSolutionProvider:
    name = "fake_model"
    model = "fake-solver-v1"
    vision_model = "fake-vision-v1"

    def __init__(self) -> None:
        self.visual_inputs: list[SolutionVisualInput | None] = []

    def solve(
        self,
        request: SolutionRequest,
        visual_input: SolutionVisualInput | None = None,
    ) -> GeneratedSolution:
        self.visual_inputs.append(visual_input)
        return GeneratedSolution(
            explanation=SolutionExplanation(
                method="代数法",
                steps=["移项并合并同类项。", "解得 $x=2$。"],
                final_answer="$x=2$",
            ),
            knowledge_points=["一元一次方程"],
            common_mistakes=["移项时忘记变号"],
            teaching_notes=["要求学生口述等式性质"],
        )


def test_live_provider_requires_human_readable_math_delimiters() -> None:
    captured: dict = {}
    provider = OpenAISolutionProvider(api_key="test-key", model="test-model")

    def fake_request(payload: dict, _request) -> dict:
        captured.update(payload)
        generated = {
            "explanation": {
                "method": "级数法",
                "steps": [r"由 $S=\sum_{n=1}^{\infty}\frac{1}{n^2}$ 进行计算。"],
                "final_answer": r"$$S=\frac{\pi^2}{6}$$",
            },
            "knowledge_points": ["数列"],
            "common_mistakes": [],
            "teaching_notes": [],
        }
        return {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps(generated, ensure_ascii=False),
                        }
                    ],
                }
            ]
        }

    provider._request = fake_request  # type: ignore[method-assign]
    result = provider.solve(SolutionRequest(question_text="求无穷级数的和。"))

    assert "行内公式用单个 $...$" in captured["instructions"]
    assert "单独成行的公式用 $$...$$" in captured["instructions"]
    assert result.explanation.final_answer.startswith("$$")


def test_solve_exact_verified_bank_question() -> None:
    bank = get_question_bank()
    source = bank.search(verification_status="passed", page_size=1).items[0]

    response = client.post(
        "/api/v1/solutions/solve",
        json={"question_text": source.stem_plain},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["matched_question_id"] == source.question_id
    assert (
        result["matched_question_revision_count"]
        == bank.get_question(source.question_id).revision_count
    )
    assert result["confidence_status"] == "program_verified"
    assert result["math_verification"]["status"] == "passed"
    assert result["math_verification"]["capability"] == "supported"
    assert result["math_verification"]["scope"] == "question_answer"
    assert result["mode"] == "verified_bank"
    assert result["explanation"]["steps"]
    assert result["explanation"]["final_answer"]
    assert result["verification_evidence"]
    assert all(not item.startswith("kp_") for item in result["knowledge_points"])


def test_unmatched_question_without_provider_explains_configuration() -> None:
    response = client.post(
        "/api/v1/solutions/solve",
        json={"question_text": "求一个当前测试题库中绝对不存在的复合虚构数学问题 987654321。"},
    )

    assert response.status_code == 503
    assert "模型解题 Provider" in response.json()["detail"]


def test_short_fragment_cannot_inherit_verified_answer() -> None:
    bank = get_question_bank()
    source = bank.search(verification_status="passed", page_size=1).items[0]

    response = client.post(
        "/api/v1/solutions/solve",
        json={"question_text": source.stem_plain[:12]},
    )

    assert response.status_code == 503


def test_modified_question_cannot_inherit_verified_answer() -> None:
    bank = get_question_bank()
    source = bank.search(verification_status="passed", page_size=1).items[0]

    response = client.post(
        "/api/v1/solutions/solve",
        json={"question_text": f"{source.stem_plain} 另加条件 x>100。"},
    )

    assert response.status_code == 503


def test_provider_solves_question_outside_bank(tmp_path: Path) -> None:
    assistant = SolutionAssistant(
        question_bank=QuestionBank(tmp_path / "empty.sqlite3"),
        provider=FakeSolutionProvider(),
    )

    result = assistant.solve(SolutionRequest(question_text="解方程 $2x-4=0$。"))

    assert result.provider == "fake_model"
    assert result.mode == "live_ai"
    assert result.confidence_status == "teacher_review_required"
    assert result.math_verification.status == "inconclusive"
    assert result.math_verification.capability == "unsupported"
    assert result.math_verification.scope == "generated_solution"
    assert result.explanation.final_answer == "$x=2$"
    assert result.alternative_available

    forged = result.model_dump()
    forged["confidence_status"] = "program_verified"
    with pytest.raises(ValueError, match="program_verified"):
        SolutionResult.model_validate(forged)

    divergent = result.model_dump()
    divergent["verification_evidence"] = ["模型自行声称已验证"]
    with pytest.raises(ValueError, match="必须与"):
        SolutionResult.model_validate(divergent)


def test_visual_solution_uses_vision_model_and_cannot_inherit_verified_status(tmp_path: Path) -> None:
    provider = FakeSolutionProvider()
    assistant = SolutionAssistant(
        question_bank=QuestionBank(tmp_path / "empty.sqlite3"),
        provider=provider,
    )
    visual = SolutionVisualInput(
        asset_id="qcap_visual",
        media_revision=2,
        recognition_revision=3,
        requires_visual_reasoning=True,
        visual_processing_consent=True,
        image_bytes=b"private-image",
        image_mime_type="image/png",
    )

    result = assistant.solve(
        SolutionRequest(question_text="如图，求三角形中角 A 的大小。"),
        visual,
    )

    assert provider.visual_inputs == [visual]
    assert result.mode == "live_ai"
    assert result.model == "fake-vision-v1"
    assert result.confidence_status == "teacher_review_required"
    assert result.visual_context is not None
    assert result.visual_context.image_used is True
    assert result.visual_context.asset_id == "qcap_visual"
    assert result.math_verification.scope == "generated_solution"
    assert any("不是 MathVerifier 证据" in item for item in result.warnings)

    forged = result.model_dump()
    forged["visual_context"]["visual_processing_consent"] = False
    with pytest.raises(ValueError, match="视觉处理同意"):
        SolutionResult.model_validate(forged)


def test_failed_bank_record_is_never_promoted_by_generated_solution() -> None:
    bank = get_question_bank()
    source = bank.search(
        verification_status="source_inconsistency_detected", page_size=1
    ).items[0]
    assistant = SolutionAssistant(question_bank=bank, provider=FakeSolutionProvider())

    result = assistant.solve(SolutionRequest(question_text=source.stem_plain))

    assert result.mode == "live_ai"
    assert result.confidence_status == "teacher_review_required"
    assert result.math_verification.status == "failed"
    assert result.math_verification.capability == "supported"
    assert result.math_verification.scope == "matched_question_record"
    assert result.math_verification.details
    assert any("不因模型重新作答而消失" in item for item in result.warnings)


def test_inconclusive_bank_record_is_never_promoted_by_generated_solution() -> None:
    bank = get_question_bank()
    source = bank.search(verification_status="needs_math_review", page_size=1).items[0]
    assistant = SolutionAssistant(question_bank=bank, provider=FakeSolutionProvider())

    result = assistant.solve(SolutionRequest(question_text=source.stem_plain))

    assert result.confidence_status == "teacher_review_required"
    assert result.math_verification.status == "inconclusive"
    assert result.math_verification.capability == "supported"
    assert result.math_verification.scope == "matched_question_record"


def test_failed_bank_record_without_model_returns_verification_conflict() -> None:
    bank = get_question_bank()
    source = bank.search(
        verification_status="source_inconsistency_detected", page_size=1
    ).items[0]

    response = client.post(
        "/api/v1/solutions/solve",
        json={"question_text": source.stem_plain},
    )

    assert response.status_code == 409
    assert "验证未通过" in response.json()["detail"]


def test_solution_request_rejects_too_short_question() -> None:
    response = client.post(
        "/api/v1/solutions/solve",
        json={"question_text": "求解"},
    )

    assert response.status_code == 422
