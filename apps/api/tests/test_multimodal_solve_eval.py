"""Fixed M7 multimodal Solve evaluation; never reads real teacher media."""

from __future__ import annotations

import asyncio
import json
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from app.agent_runtime import (
    TeacherAgentError,
    TeacherAgentErrorCode,
    TeacherAgentRunResult,
    TeacherAgentRunStatus,
)
from app.modules.question_bank import QuestionBank
from app.modules.question_capture import (
    LowConfidenceRegion,
    QuestionCapture,
    QuestionCaptureCommand,
    QuestionCaptureError,
    QuestionInputBundle,
    QuestionOption,
    QuestionRecognitionCommand,
    QuestionRecognitionError,
    QuestionRecognitionResult,
    QuestionRecognitionReviewCommand,
    QuestionSolveGrantError,
    QuestionSolveGrantRegistry,
    QuestionSolveReference,
)
from app.modules.solution_assistant import (
    GeneratedSolution,
    SolutionAssistant,
    SolutionExplanation,
    SolutionProviderError,
    SolutionRequest,
    SolutionResult,
    SolutionVisualInput,
)
from app.modules.solve_agent import SolveAgentCommand, SolveAgentWorkflow


_CASES = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "test-fixtures"
    / "multimodal-solve"
    / "eval-cases.json"
)


def _image(case_id: str) -> bytes:
    if case_id == "low_contrast_review_warning":
        image = Image.new("RGB", (1000, 700), (250, 250, 250))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, 499, 699), fill=(240, 240, 240))
    else:
        image = Image.new("RGB", (1000, 700), "white")
        draw = ImageDraw.Draw(image)
        draw.line((80, 620, 920, 620), fill="black", width=4)
        draw.line((120, 660, 120, 70), fill="black", width=4)
        if "solid_geometry" in case_id:
            draw.polygon([(250, 500), (620, 520), (480, 250)], outline="black", width=4)
            draw.polygon([(360, 360), (730, 380), (590, 110)], outline="black", width=4)
            draw.line((250, 500, 360, 360), fill="black", width=4)
            draw.line((620, 520, 730, 380), fill="black", width=4)
            draw.line((480, 250, 590, 110), fill="black", width=4)
        elif "statistics" in case_id:
            for index, height in enumerate((160, 300, 240, 420)):
                left = 220 + index * 140
                draw.rectangle((left, 620 - height, left + 75, 620), outline="black", width=4)
        else:
            points = [(150, 560), (300, 430), (450, 300), (600, 210), (820, 160)]
            draw.line(points, fill="black", width=5)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


class _RecognitionProvider:
    name = "synthetic_m7_ocr"
    model = "synthetic-m7-v1"

    def __init__(self, case_id: str, *, fail: bool = False) -> None:
        self.case_id = case_id
        self.fail = fail

    def recognize(self, *, path: Path, mime_type: str, teacher_id: str) -> QuestionRecognitionResult:
        if self.fail:
            raise QuestionRecognitionError("synthetic OCR unavailable")
        visual = self.case_id != "algebra_formula_text_only"
        quality_issue = self.case_id in {
            "truncated_question_review_required",
            "multiple_questions_review_required",
        }
        warning = {
            "truncated_question_review_required": "题面右侧可能被截断，请重新裁剪或人工补全。",
            "multiple_questions_review_required": "图片中可能包含多道题，请裁剪为单题后再确认。",
        }.get(self.case_id)
        return QuestionRecognitionResult(
            stem_plain=(
                "已知函数 f(x)=x²，求 f(2)。"
                if not visual
                else f"项目自建 {self.case_id} 图片题，请结合图形求解。"
            ),
            stem_latex=(
                r"已知函数 $f(x)=x^2$，求 $f(2)$。"
                if not visual
                else f"项目自建 {self.case_id} 图片题，请结合图形求解。"
            ),
            options=[QuestionOption(key="A", text="2"), QuestionOption(key="B", text="4")]
            if not visual
            else [],
            low_confidence_regions=(
                [
                    LowConfidenceRegion(
                        text="图形边缘",
                        reason=warning or "图形标签需教师核对",
                        confidence=0.45,
                    )
                ]
                if quality_issue
                else []
            ),
            warnings=[warning] if warning else [],
            requires_visual_reasoning=visual,
            visual_observations=(
                ["图中存在坐标轴、标注点或数据图形，需与原图共同参与解题。"]
                if visual
                else []
            ),
        )


class _SolutionProvider:
    name = "synthetic_m7_solver"
    model = "synthetic-m7-text-v1"
    vision_model = "synthetic-m7-vision-v1"

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.visual_inputs: list[SolutionVisualInput | None] = []

    def solve(
        self,
        request: SolutionRequest,
        visual_input: SolutionVisualInput | None = None,
    ) -> GeneratedSolution:
        self.visual_inputs.append(visual_input)
        if self.fail:
            raise SolutionProviderError("synthetic vision model unavailable")
        return GeneratedSolution(
            explanation=SolutionExplanation(
                method="项目自建合成解法",
                steps=["核对教师确认的题面。", "按题面与受控图形信息完成推导。"],
                final_answer="项目自建合成答案，需教师复核。",
            ),
            knowledge_points=["项目自建知识点"],
            common_mistakes=["把视觉理解误当作程序验证"],
            teaching_notes=["仅用于 M7 自动化评测"],
        )


class _CancelledRuntime:
    runtime_name = "dsh"

    async def run(self, request) -> TeacherAgentRunResult:
        return TeacherAgentRunResult(
            run_id="run_m7_cancelled",
            session_id="tch_m7_eval",
            request_id=request.request_id,
            runtime="dsh",
            status=TeacherAgentRunStatus.CANCELLED,
            error=TeacherAgentError(
                code=TeacherAgentErrorCode.RUN_CANCELLED,
                message="synthetic cancellation",
                request_id=request.request_id,
            ),
        )


def _capture(
    tmp_path: Path,
    case_id: str,
    *,
    fail_ocr: bool = False,
) -> tuple[QuestionCapture, QuestionInputBundle]:
    root = tmp_path / case_id
    root.mkdir(parents=True, exist_ok=True)
    provider = _RecognitionProvider(case_id, fail=fail_ocr)
    capture = QuestionCapture(
        root / "capture.sqlite3",
        root / "media",
        recognition_providers={"local": provider, "external": provider},
    )
    bundle = capture.prepare(
        QuestionCaptureCommand(
            owner_id="teacher_m7_eval",
            source="upload",
            private_storage_acknowledged=True,
        ),
        filename=f"{case_id}.png",
        content=_image(case_id),
    )
    return capture, bundle


def _confirmed_input(tmp_path: Path, case_id: str, *, requires_visual: bool):
    capture, created = _capture(tmp_path, case_id)
    draft = capture.recognize(
        created.asset.asset_id,
        QuestionRecognitionCommand(mode="local"),
        owner_id="teacher_m7_eval",
    )
    confirmed = capture.review_recognition(
        created.asset.asset_id,
        QuestionRecognitionReviewCommand(
            stem_plain=draft.stem_plain,
            stem_latex=draft.stem_latex,
            options=draft.options,
            note="M7 synthetic evaluation",
            confirm=True,
        ),
        owner_id="teacher_m7_eval",
    )
    reference = QuestionSolveReference(
        asset_id=created.asset.asset_id,
        media_revision=created.asset.current_revision,
        recognition_revision=confirmed.recognition_revision,
        visual_processing_consent=requires_visual,
    )
    prepared = capture.prepare_for_solve(
        reference,
        owner_id="teacher_m7_eval",
        request_id=f"req_{case_id}",
    )
    return capture, created, confirmed, prepared


def test_multimodal_solve_fixed_synthetic_evaluation(tmp_path: Path) -> None:
    fixture = json.loads(_CASES.read_text(encoding="utf-8"))
    case_ids = {case["id"] for case in fixture["cases"]}
    assert fixture["evaluation_id"] == "multimodal-solve-synthetic-v1"
    assert fixture["source"] == "project-authored-synthetic"
    assert fixture["synthetic"] is True
    assert len(case_ids) == len(fixture["cases"]) == 15

    violations = {
        "unexpected_outcome": 0,
        "private_state_leak": 0,
        "revision_trace_missing": 0,
        "visual_condition_lost": 0,
        "consent_bypass": 0,
        "cross_owner_leak": 0,
        "failure_masked": 0,
        "verification_overstated": 0,
        "capability_replay": 0,
    }
    executed: set[str] = set()
    visual_results: list[SolutionResult] = []

    for case in fixture["cases"]:
        if case["group"] != "happy_path":
            continue
        case_id = case["id"]
        requires_visual = bool(case["requires_visual_reasoning"])
        capture, created = _capture(tmp_path, case_id)
        draft = capture.recognize(
            created.asset.asset_id,
            QuestionRecognitionCommand(mode="local"),
            owner_id="teacher_m7_eval",
        )
        confirmed = capture.review_recognition(
            created.asset.asset_id,
            QuestionRecognitionReviewCommand(
                stem_plain=draft.stem_plain,
                stem_latex=draft.stem_latex,
                options=draft.options,
                note="M7 synthetic evaluation",
                confirm=True,
            ),
            owner_id="teacher_m7_eval",
        )
        reference = QuestionSolveReference(
            asset_id=created.asset.asset_id,
            media_revision=created.asset.current_revision,
            recognition_revision=confirmed.recognition_revision,
            visual_processing_consent=requires_visual,
        )
        if requires_visual:
            with pytest.raises(QuestionCaptureError, match="逐次确认"):
                capture.prepare_for_solve(
                    reference.model_copy(update={"visual_processing_consent": False}),
                    owner_id="teacher_m7_eval",
                    request_id=f"req_{case_id}_without_consent",
                )
        prepared = capture.prepare_for_solve(
            reference,
            owner_id="teacher_m7_eval",
            request_id=f"req_{case_id}",
        )
        visual_input = (
            SolutionVisualInput(
                asset_id=prepared.asset_id,
                media_revision=prepared.media_revision,
                recognition_revision=prepared.recognition_revision,
                requires_visual_reasoning=prepared.requires_visual_reasoning,
                visual_processing_consent=prepared.visual_processing_consent,
                image_bytes=prepared.image_bytes,
                image_mime_type=prepared.image_mime_type,
            )
            if prepared.image_bytes is not None
            else None
        )
        provider = _SolutionProvider()
        assistant = SolutionAssistant(
            question_bank=QuestionBank(tmp_path / case_id / "questions.sqlite3"),
            provider=provider,
        )
        result = assistant.solve(
            SolutionRequest(question_text=prepared.question_text, teacher_id="teacher_m7_eval"),
            visual_input,
        )
        if created.asset.visibility != "private" or created.asset.public_search_allowed:
            violations["private_state_leak"] += 1
        if confirmed.recognition_source_revision != prepared.media_revision:
            violations["revision_trace_missing"] += 1
        if requires_visual:
            if result.visual_context is None or not result.visual_context.image_used:
                violations["visual_condition_lost"] += 1
            visual_results.append(result)
        elif result.visual_context is not None or provider.visual_inputs != [None]:
            violations["unexpected_outcome"] += 1
        if result.confidence_status != "teacher_review_required":
            violations["verification_overstated"] += 1
        if result.math_verification.scope != "generated_solution":
            violations["verification_overstated"] += 1
        executed.add(case_id)

    capture, low_contrast = _capture(tmp_path, "low_contrast_review_warning")
    if low_contrast.asset.clarity_status != "review_needed" or not low_contrast.asset.warnings:
        violations["unexpected_outcome"] += 1
    executed.add("low_contrast_review_warning")

    for case_id in (
        "truncated_question_review_required",
        "multiple_questions_review_required",
    ):
        capture, created = _capture(tmp_path, case_id)
        draft = capture.recognize(
            created.asset.asset_id,
            QuestionRecognitionCommand(mode="local"),
            owner_id="teacher_m7_eval",
        )
        if not draft.low_confidence_regions or not draft.recognition_warnings:
            violations["unexpected_outcome"] += 1
        with pytest.raises(QuestionCaptureError, match="尚未由教师确认"):
            capture.prepare_for_solve(
                QuestionSolveReference(
                    asset_id=created.asset.asset_id,
                    media_revision=1,
                    recognition_revision=draft.recognition_revision,
                    visual_processing_consent=True,
                ),
                owner_id="teacher_m7_eval",
                request_id=f"req_{case_id}",
            )
        executed.add(case_id)

    capture, created = _capture(tmp_path, "external_ocr_consent_required")
    with pytest.raises(QuestionCaptureError, match="外部 OCR"):
        capture.recognize(
            created.asset.asset_id,
            QuestionRecognitionCommand(mode="external"),
            owner_id="teacher_m7_eval",
        )
    if capture.get(created.asset.asset_id, owner_id="teacher_m7_eval").recognition_status != "not_started":
        violations["consent_bypass"] += 1
    executed.add("external_ocr_consent_required")

    capture, created = _capture(tmp_path, "ocr_service_failure", fail_ocr=True)
    with pytest.raises(QuestionCaptureError, match="unavailable"):
        capture.recognize(
            created.asset.asset_id,
            QuestionRecognitionCommand(mode="local"),
            owner_id="teacher_m7_eval",
        )
    if capture.get(created.asset.asset_id, owner_id="teacher_m7_eval").recognition_status != "not_started":
        violations["failure_masked"] += 1
    executed.add("ocr_service_failure")

    _, _, _, prepared = _confirmed_input(
        tmp_path,
        "vision_service_unavailable",
        requires_visual=True,
    )
    failing_provider = _SolutionProvider(fail=True)
    with pytest.raises(SolutionProviderError, match="unavailable"):
        SolutionAssistant(
            question_bank=QuestionBank(
                tmp_path / "vision_service_unavailable" / "questions.sqlite3"
            ),
            provider=failing_provider,
        ).solve(
            SolutionRequest(question_text=prepared.question_text),
            SolutionVisualInput(
                asset_id=prepared.asset_id,
                media_revision=prepared.media_revision,
                recognition_revision=prepared.recognition_revision,
                requires_visual_reasoning=True,
                visual_processing_consent=True,
                image_bytes=prepared.image_bytes,
                image_mime_type=prepared.image_mime_type,
            ),
        )
    executed.add("vision_service_unavailable")

    cancelled = asyncio.run(
        SolveAgentWorkflow(runtime=_CancelledRuntime()).run(
            SolveAgentCommand(question_text="项目自建取消场景题面。"),
            owner_id="teacher_m7_eval",
            request_id="req_m7_cancelled",
        )
    )
    if cancelled.status != "cancelled" or cancelled.error["code"] != "RUN_CANCELLED":
        violations["failure_masked"] += 1
    executed.add("solve_cancelled")

    grants = QuestionSolveGrantRegistry()
    reference = QuestionSolveReference(
        asset_id="qcap_m7_eval",
        media_revision=2,
        recognition_revision=3,
        visual_processing_consent=True,
    )
    token = grants.issue(
        owner_id="teacher_m7_eval",
        question_text="项目自建视觉题面。",
        solution_mode="standard",
        teacher_instruction="",
        reference=reference,
    )
    grants.consume(token)
    with pytest.raises(QuestionSolveGrantError, match="无效或已使用"):
        grants.consume(token)
    executed.add("solve_permission_replay")

    capture, created = _capture(tmp_path, "cross_owner_isolation")
    with pytest.raises(KeyError):
        capture.get(created.asset.asset_id, owner_id="teacher_other")
    with pytest.raises(KeyError):
        capture.content(created.asset.asset_id, owner_id="teacher_other")
    executed.add("cross_owner_isolation")

    for result in visual_results:
        if result.math_verification.capability != "unsupported":
            violations["verification_overstated"] += 1
        forged = result.model_dump()
        forged["confidence_status"] = "program_verified"
        with pytest.raises(ValueError, match="program_verified"):
            SolutionResult.model_validate(forged)
    executed.add("visual_math_verifier_separation")

    if executed != case_ids:
        violations["unexpected_outcome"] += len(case_ids.symmetric_difference(executed))
    print(f"\n[m7-eval] cases={len(case_ids)} violations={violations}")
    assert violations == {key: 0 for key in violations}, violations
