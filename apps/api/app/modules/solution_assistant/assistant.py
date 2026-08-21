from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Literal

from app.modules.question_bank import QuestionBank
from app.modules.question_bank.schemas import QuestionDetail
from app.modules.solution_assistant.providers import SolutionProvider
from app.modules.solution_assistant.schemas import (
    MathVerificationAssessment,
    SolutionExplanation,
    SolutionRequest,
    SolutionResult,
)


class SolutionAssistantError(ValueError):
    pass


class SolutionAssistantUnavailableError(SolutionAssistantError):
    """No verified solution or configured model can complete the request."""


class SolutionAssistantVerificationError(SolutionAssistantError):
    """A matching bank record has failed or inconclusive verification evidence."""

    def __init__(self, assessment: MathVerificationAssessment) -> None:
        self.assessment = assessment
        message = (
            "匹配题目的独立数学验证未通过，不能作为可信解析返回。"
            if assessment.status == "failed"
            else "匹配题目的独立数学验证证据不足，不能作为可信解析返回。"
        )
        super().__init__(message)


class SolutionAssistant:
    """Solves through one interface while keeping trust decisions internal."""

    MATCH_THRESHOLD = 0.88
    KNOWLEDGE_POINT_LABELS = {
        "kp_function_extrema": "函数最值",
        "kp_function_inequality": "函数与不等式",
        "kp_function_parity": "函数奇偶性",
        "kp_function_periodicity": "函数周期性",
        "kp_function_symmetry": "函数对称性",
        "kp_graph_transformation": "函数图象变换",
        "kp_probability": "概率",
        "kp_quadratic_function": "二次函数",
        "kp_random_variable_distribution": "随机变量及其分布",
        "kp_sets_and_logic": "集合与常用逻辑用语",
    }

    def __init__(
        self,
        *,
        question_bank: QuestionBank,
        provider: SolutionProvider | None = None,
    ) -> None:
        self.question_bank = question_bank
        self.provider = provider

    def solve(self, request: SolutionRequest) -> SolutionResult:
        match, score = self._best_bank_match(request.question_text)
        exact_match = match is not None and score == 1.0
        exact_verified_match = exact_match and match.verification_status == "passed"
        if exact_verified_match:
            solutions = match.raw.get("solutions") or []
            solution_index = 1 if request.solution_mode == "alternative" else 0
            if len(solutions) > solution_index:
                return self._from_verified_question(
                    request, match, solutions[solution_index], score
                )
        if self.provider is not None:
            generated = self.provider.solve(request)
            assessment = self._generated_assessment(match if exact_match else None)
            warnings = ["请由教师核对条件、推导过程和最终答案后再用于教学。"]
            if assessment.scope == "matched_question_record":
                warnings.insert(
                    0,
                    "题库中的同题记录存在验证冲突或证据不足；该状态不因模型重新作答而消失。",
                )
            return SolutionResult(
                question_text=request.question_text,
                solution_mode=request.solution_mode,
                **generated.model_dump(),
                confidence_status="teacher_review_required",
                math_verification=assessment,
                verification_evidence=assessment.details,
                provider=self.provider.name,
                model=self.provider.model,
                mode="live_ai",
                matched_question_id=match.question_id if match else None,
                matched_question_revision_count=(
                    match.revision_count if match else None
                ),
                match_score=score if match else None,
                alternative_available=True,
                warnings=warnings,
            )
        if exact_match and not exact_verified_match:
            raise SolutionAssistantVerificationError(
                self._stored_assessment(match, scope="matched_question_record")
            )
        if exact_verified_match and request.solution_mode == "alternative":
            raise SolutionAssistantUnavailableError(
                "当前题库只保存了一种已验证解法；配置可用的模型解题 Provider 后可生成第二种解法。"
            )
        raise SolutionAssistantUnavailableError(
            "当前文字题未匹配到已验证题库；配置可用的模型解题 Provider 后才能生成新解答。"
        )

    def _best_bank_match(
        self, question_text: str
    ) -> tuple[QuestionDetail | None, float | None]:
        target = self._normalize(question_text)
        candidates = self.question_bank.search(page=1, page_size=100).items
        best = None
        best_score = 0.0
        for candidate in candidates:
            stem = self._normalize(candidate.stem_plain)
            if not stem:
                continue
            if stem == target:
                score = 1.0
            else:
                score = SequenceMatcher(None, target, stem).ratio()
            if score > best_score:
                best = candidate
                best_score = score
        if best is None or best_score < self.MATCH_THRESHOLD:
            return None, None
        return self.question_bank.get_question(best.question_id), round(best_score, 4)

    def _from_verified_question(
        self,
        request: SolutionRequest,
        question: QuestionDetail,
        solution: dict,
        score: float | None,
    ) -> SolutionResult:
        steps = [
            str(step).strip()
            for step in solution.get("steps_latex", [])
            if str(step).strip()
        ]
        if not steps:
            steps = ["该题已通过独立验证，但题库解析步骤仍需教师补充。"]
        final_answer = str(
            solution.get("final_answer") or question.answer_value or "待教师确认"
        ).strip()
        assessment = self._stored_assessment(question, scope="question_answer")
        if assessment.status != "passed":
            raise SolutionAssistantVerificationError(assessment)
        all_solutions = question.raw.get("solutions") or []
        raw_knowledge_points = question.raw.get("curriculum", {}).get(
            "knowledge_point_ids", question.knowledge_point_ids
        ) or question.knowledge_point_ids
        knowledge_points = [
            self.KNOWLEDGE_POINT_LABELS.get(str(item), str(item))
            for item in raw_knowledge_points
        ]
        return SolutionResult(
            question_text=request.question_text,
            solution_mode=request.solution_mode,
            explanation=SolutionExplanation(
                method=str(solution.get("method") or "题库标准解法"),
                steps=steps,
                final_answer=final_answer,
            ),
            knowledge_points=knowledge_points,
            common_mistakes=self._common_mistakes(question),
            teaching_notes=[
                "建议先让学生说明关键条件，再展示完整推导。",
                "题库解析可以继续在审核台由教师修订。",
            ],
            confidence_status="program_verified",
            math_verification=assessment,
            verification_evidence=assessment.details,
            provider="verified_question_bank",
            model="independent-math-verifier",
            mode="verified_bank",
            matched_question_id=question.question_id,
            matched_question_revision_count=question.revision_count,
            match_score=score,
            alternative_available=len(all_solutions) > 1 or self.provider is not None,
            warnings=["结果来自当前私有题库的已验证题目，请核对输入是否与原题条件完全一致。"],
        )

    @staticmethod
    def _stored_assessment(
        question: QuestionDetail,
        *,
        scope: Literal["question_answer", "matched_question_record"],
    ) -> MathVerificationAssessment:
        verification = question.raw.get("verification") or {}
        raw_status = str(verification.get("status") or question.verification_status)
        status = (
            "passed"
            if raw_status == "passed"
            else "failed"
            if raw_status in {"failed", "inconsistent", "source_inconsistency_detected"}
            else "inconclusive"
        )
        details = [
            str(item).strip()
            for item in verification.get("details", [])
            if str(item).strip()
        ]
        if not details:
            details = {
                "passed": ["题库记录标记为已通过独立数学验证。"],
                "failed": ["题库记录显示独立计算与来源答案存在矛盾。"],
                "inconclusive": ["题库记录尚无足够的独立数学验证证据。"],
            }[status]
        method = verification.get("method")
        methods = verification.get("methods") or []
        if not method and methods:
            method = methods[0]
        verifier_version = verification.get("verifier_version")
        if verifier_version:
            evidence_source = "math_verifier"
        elif method == "teacher_independent_derivation":
            evidence_source = "teacher_evidence"
        else:
            evidence_source = "stored_status"
        return MathVerificationAssessment(
            status=status,
            capability="supported",
            scope=scope,
            evidence_source=evidence_source,
            method=str(method) if method else None,
            computed_answer=(
                str(verification["computed_answer"])
                if verification.get("computed_answer") is not None
                else None
            ),
            source_answer=(
                str(verification["source_answer"])
                if verification.get("source_answer") is not None
                else question.answer_value
            ),
            details=details,
            verifier_version=str(verifier_version) if verifier_version else None,
        )

    @classmethod
    def _generated_assessment(
        cls, exact_match: QuestionDetail | None
    ) -> MathVerificationAssessment:
        if exact_match is not None and exact_match.verification_status != "passed":
            return cls._stored_assessment(
                exact_match, scope="matched_question_record"
            )
        return MathVerificationAssessment(
            status="inconclusive",
            capability="unsupported",
            scope="generated_solution",
            evidence_source="none",
            details=[
                "答案与解析由大模型生成；当前 MathVerifier 不支持对此完整推导做独立验证。"
            ],
        )

    @staticmethod
    def _common_mistakes(question: QuestionDetail) -> list[str]:
        raw_items = question.raw.get("pedagogy", {}).get("common_mistakes", [])
        mistakes = [str(item).strip() for item in raw_items if str(item).strip()]
        if mistakes:
            return mistakes[:8]
        if question.question_type in {"single_choice", "multiple_choice"}:
            return ["只凭局部条件排除选项，未完成全部条件核验。"]
        return ["跳过关键等价变形或遗漏题目中的取值范围。"]

    @staticmethod
    def _normalize(value: str) -> str:
        value = value.lower().replace("$", "")
        value = re.sub(r"\s+", "", value)
        return re.sub(r"[，。；：、,.!?！？（）()\[\]{}]", "", value)
