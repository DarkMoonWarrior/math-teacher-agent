"""Fixed synthetic evaluation for the M5 trusted Solve boundary.

The fixture is project-created and never calls a real model. The gate fails if
verified bank evidence is lost, generated content is promoted, a modified
question inherits a verified answer, or failed/inconclusive evidence is hidden.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.core.config import Settings
from app.modules.math_verifier import MathVerifier
from app.modules.question_bank import QuestionBank
from app.modules.solution_assistant import (
    GeneratedSolution,
    SolutionAssistant,
    SolutionAssistantUnavailableError,
    SolutionAssistantVerificationError,
    SolutionExplanation,
    SolutionRequest,
)


_ROOT = Path(__file__).resolve().parents[3]
_EVAL_PATH = _ROOT / "data" / "test-fixtures" / "solve-agent" / "eval-cases.json"


class SyntheticSolutionProvider:
    name = "synthetic_test_provider"
    model = "synthetic-solver-v1"

    def solve(self, _request: SolutionRequest) -> GeneratedSolution:
        return GeneratedSolution(
            explanation=SolutionExplanation(
                method="合成测试解法",
                steps=["整理题目条件。", "形成待教师复核的推导。"],
                final_answer="合成测试答案",
            ),
            knowledge_points=["合成测试知识点"],
            common_mistakes=["忽略条件"],
            teaching_notes=["仅用于自动化评估"],
        )


def _load_payload() -> dict[str, Any]:
    return json.loads(_EVAL_PATH.read_text(encoding="utf-8"))


def _build_bank(tmp_path: Path) -> QuestionBank:
    settings = Settings()
    bank = QuestionBank(tmp_path / "solve-eval.sqlite3")
    for package in [
        settings.pilot_batch_json,
        settings.function_pilot_batch_json,
    ]:
        bank.import_batch(package)
    verifier = MathVerifier()
    for package in [
        settings.set_curation_json,
        settings.probability_curation_json,
        settings.probability_curation_2_json,
        settings.function_curation_json,
    ]:
        bank.apply_curation_package(package, verifier)
    return bank


def _question_text(case: dict[str, Any], bank: QuestionBank) -> str:
    if "question_text" in case:
        return str(case["question_text"])
    selector = case["selector"]
    page = bank.search(
        verification_status=selector["verification_status"], page_size=1
    )
    assert page.items, f"{case['id']}: selector has no synthetic bank record"
    return page.items[0].stem_plain


def _error_code(error: Exception) -> str:
    if isinstance(error, SolutionAssistantVerificationError):
        return (
            "VERIFICATION_FAILED"
            if error.assessment.status == "failed"
            else "VERIFICATION_INCONCLUSIVE"
        )
    if isinstance(error, SolutionAssistantUnavailableError):
        return "MODEL_UNAVAILABLE"
    return type(error).__name__


def test_eval_fixture_is_fixed_synthetic_and_unique() -> None:
    payload = _load_payload()
    cases = payload["cases"]
    assert payload["synthetic"] is True
    assert payload["source"] == "project_created"
    assert len(cases) >= 9
    assert len({case["id"] for case in cases}) == len(cases)
    assert all("expected" in case for case in cases)


def test_solve_trust_gates_all_zero(tmp_path: Path) -> None:
    bank = _build_bank(tmp_path)
    violations = {
        "unexpected_outcome": 0,
        "generated_promoted": 0,
        "verification_overstated": 0,
        "evidence_mismatch": 0,
        "modified_inherited": 0,
        "trace_missing": 0,
    }

    for case in _load_payload()["cases"]:
        expected = case["expected"]
        assistant = SolutionAssistant(
            question_bank=bank,
            provider=SyntheticSolutionProvider() if case["provider"] else None,
        )
        request = SolutionRequest(
            question_text=_question_text(case, bank),
            solution_mode=case["solution_mode"],
        )

        try:
            result = assistant.solve(request)
        except (SolutionAssistantVerificationError, SolutionAssistantUnavailableError) as error:
            if expected["outcome"] != "error" or _error_code(error) != expected["error_code"]:
                violations["unexpected_outcome"] += 1
            continue

        if expected["outcome"] != "success":
            violations["unexpected_outcome"] += 1
            if case["id"] == "verified_text_modified_cannot_inherit":
                violations["modified_inherited"] += 1
            continue

        if result.mode != expected["mode"] or result.confidence_status != expected["confidence_status"]:
            violations["unexpected_outcome"] += 1
        assessment = result.math_verification
        for field, key in [
            (assessment.status, "verification_status"),
            (assessment.capability, "verification_capability"),
            (assessment.scope, "verification_scope"),
        ]:
            if field != expected[key]:
                violations["verification_overstated"] += 1
        if "evidence_source" in expected and assessment.evidence_source != expected["evidence_source"]:
            violations["verification_overstated"] += 1
        if result.mode == "live_ai" and result.confidence_status == "program_verified":
            violations["generated_promoted"] += 1
        if result.verification_evidence != assessment.details:
            violations["evidence_mismatch"] += 1
        if "matched_question_id" in expected and result.matched_question_id != expected["matched_question_id"]:
            violations["trace_missing"] += 1
        if expected.get("revision_required") and result.matched_question_revision_count is None:
            violations["trace_missing"] += 1

    print(f"\n[solve-eval] cases={len(_load_payload()['cases'])} violations={violations}")
    assert violations == {key: 0 for key in violations}, violations
