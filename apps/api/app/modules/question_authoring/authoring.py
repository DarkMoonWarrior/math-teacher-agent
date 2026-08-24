from __future__ import annotations

import re
from datetime import datetime, timezone
from uuid import uuid4

from app.modules.curriculum import InMemoryCurriculumCatalog
from app.modules.math_verifier import MathVerifier
from app.modules.question_authoring.providers import (
    PROMPT_REVISION,
    QuestionAuthoringContext,
    QuestionAuthoringProvider,
    QuestionAuthoringProviderError,
)
from app.modules.question_authoring.schemas import (
    GeneratedQuestionDraft,
    ProviderQuestionDraft,
    QuestionDesignBrief,
    QuestionDraftCurriculum,
    QuestionDraftEditableContent,
    QuestionDraftTrustCheck,
    QuestionDraftVerification,
    QuestionType,
)


class QuestionAuthoringError(ValueError):
    pass


class QuestionAuthoringClarificationRequired(QuestionAuthoringError):
    pass


class QuestionAuthoringUnavailableError(QuestionAuthoringError):
    pass


class QuestionAuthoring:
    """Deep module for creating and rechecking owner-only authoring drafts."""

    def __init__(
        self,
        *,
        curriculum: InMemoryCurriculumCatalog,
        provider: QuestionAuthoringProvider | None,
        math_verifier: MathVerifier,
    ) -> None:
        self.curriculum = curriculum
        self.provider = provider
        self.math_verifier = math_verifier

    def create_draft(self, brief: QuestionDesignBrief) -> GeneratedQuestionDraft:
        if brief.reference_question_id:
            raise QuestionAuthoringError(
                "参考母题模式尚未开放；只有母题数学状态与改编权利都可独立验证后才能使用"
            )
        question_type = brief.question_type or self._infer_question_type(brief.request_text)
        curriculum_guidance = self._resolve_curriculum_guidance(brief)
        curriculum_options = self._curriculum_options()
        if self.provider is None:
            raise QuestionAuthoringUnavailableError(
                "当前没有可用的辅助命题模型；请配置 DeepSeek 后重试"
            )
        try:
            content = self.provider.generate(
                QuestionAuthoringContext(
                    brief=brief,
                    question_type=question_type,
                    curriculum=curriculum_guidance,
                    curriculum_options=curriculum_options,
                )
            )
        except QuestionAuthoringProviderError as exc:
            raise QuestionAuthoringUnavailableError(str(exc)) from exc
        self._validate_structure(content, expected_type=question_type)
        curriculum, curriculum_warning = self._ground_generated_curriculum(
            content,
            guidance=curriculum_guidance,
        )
        draft_id = f"qad_{uuid4().hex[:16]}"
        verification = self._evaluate_trust(
            content,
            brief=brief,
            draft_id=draft_id,
        )
        warnings = [
            "本题由 AI 辅助生成；结构检查不等于数学正确，必须由教师复核。",
            "当前草稿尚未保存，仅自己可见；不会进入公共题库或公共搜索。",
            "预计难度来自模型判断，不是统计校准或程序验证结果。",
        ]
        if verification.math_verifier_status == "unsupported":
            warnings.append("当前 MathVerifier 不支持对此任意生成题做独立数学验证。")
        if verification.status == "checks_failed":
            warnings.append("确定性可信检查发现阻断项；修正前不得作为正式题目使用。")
        if brief.question_type is None:
            warnings.append(f"未明确题型，已从要求推断为 {question_type}。")
        if curriculum_warning:
            warnings.append(curriculum_warning)
        return GeneratedQuestionDraft(
            draft_id=draft_id,
            request_text=brief.request_text.strip(),
            question_type=content.question_type,
            stem_plain=content.stem_plain.strip(),
            stem_latex=content.stem_latex.strip() if content.stem_latex else None,
            options=content.options,
            answer_value=content.answer_value.strip(),
            solution_method=content.solution_method.strip(),
            solution_steps=[step.strip() for step in content.solution_steps],
            final_answer=content.final_answer.strip(),
            authoring_intent=content.authoring_intent.strip(),
            curriculum=curriculum,
            knowledge_points=self._clean_list(content.knowledge_points),
            assessed_methods=self._clean_list(content.assessed_methods),
            common_mistakes=self._clean_list(content.common_mistakes),
            target_difficulty=brief.target_difficulty,
            estimated_difficulty=content.estimated_difficulty,
            verification=verification,
            provider=self.provider.name,
            model=self.provider.model,
            prompt_revision=PROMPT_REVISION,
            warnings=warnings,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def revise_draft(
        self,
        current: GeneratedQuestionDraft,
        content: QuestionDraftEditableContent,
    ) -> GeneratedQuestionDraft:
        """Create a teacher-edited snapshot with fresh server-owned trust evidence."""

        revised = ProviderQuestionDraft(
            question_type=content.question_type,
            stem_plain=content.stem_plain,
            stem_latex=content.stem_latex,
            options=content.options,
            answer_value=content.answer_value,
            solution_method=content.solution_method,
            solution_steps=content.solution_steps,
            final_answer=content.final_answer,
            authoring_intent=content.authoring_intent,
            estimated_difficulty=current.estimated_difficulty,
            curriculum_node_id=(
                content.curriculum_confirmation_node_id
                or (current.curriculum.node_id if current.curriculum else None)
            ),
            knowledge_points=content.knowledge_points,
            assessed_methods=content.assessed_methods,
            common_mistakes=content.common_mistakes,
        )
        self._validate_structure(revised, expected_type=content.question_type)
        confirmed_curriculum = current.curriculum
        if content.curriculum_confirmation_node_id:
            confirmed_curriculum = self._teacher_confirmed_curriculum(
                content.curriculum_confirmation_node_id
            )
        brief = QuestionDesignBrief(
            request_text=current.request_text,
            curriculum_node_id=(
                confirmed_curriculum.node_id if confirmed_curriculum else None
            ),
            question_type=content.question_type,
            target_difficulty=current.target_difficulty,
        )
        verification = self._evaluate_trust(
            revised,
            brief=brief,
            draft_id=current.draft_id,
        )
        warnings = [
            "本 revision 已由教师编辑；系统已重跑结构与可信检查，但仍需教师复核数学正确性。",
            "当前内容仍在个人命题工作区；不会进入公共题库或公共搜索。",
            "预计难度沿用原始模型判断，不是统计校准或程序验证结果。",
        ]
        if verification.math_verifier_status == "unsupported":
            warnings.append("当前 MathVerifier 不支持对此任意生成题做独立数学验证。")
        if verification.status == "checks_failed":
            warnings.append("确定性可信检查发现阻断项；修正前不得作为正式题目使用。")
        return current.model_copy(
            update={
                "question_type": revised.question_type,
                "stem_plain": revised.stem_plain.strip(),
                "stem_latex": revised.stem_latex.strip() if revised.stem_latex else None,
                "options": revised.options,
                "answer_value": revised.answer_value.strip(),
                "solution_method": revised.solution_method.strip(),
                "solution_steps": [step.strip() for step in revised.solution_steps],
                "final_answer": revised.final_answer.strip(),
                "authoring_intent": revised.authoring_intent.strip(),
                "curriculum": confirmed_curriculum,
                "knowledge_points": self._clean_list(revised.knowledge_points),
                "assessed_methods": self._clean_list(revised.assessed_methods),
                "common_mistakes": self._clean_list(revised.common_mistakes),
                "pedagogy_source": "teacher_edited",
                "verification": verification,
                "warnings": warnings,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    def _resolve_curriculum_guidance(
        self,
        brief: QuestionDesignBrief,
    ) -> QuestionDraftCurriculum | None:
        if brief.curriculum_node_id:
            try:
                node = self.curriculum.get_node(brief.curriculum_node_id)
            except KeyError as exc:
                raise QuestionAuthoringError("所选教材知识点不存在") from exc
            if node.node_type != "knowledge_point":
                raise QuestionAuthoringError("辅助命题必须选择具体知识点节点")
            return self._curriculum_view(
                node.node_id,
                mapping_source="teacher_selected",
                confidence=1.0,
                mapping_status="teacher_confirmed",
            )

        query = (brief.knowledge_point_query or "").strip()
        normalized_text = self._normalize(f"{query} {brief.request_text}")
        direct = [
            node
            for node in self.curriculum.list_nodes()
            if node.node_type == "knowledge_point"
            and self._normalize(node.name)
            and self._normalize(node.name) in normalized_text
        ]
        if direct:
            selected = max(direct, key=lambda node: len(self._normalize(node.name)))
            return self._curriculum_view(
                selected.node_id,
                mapping_source="brief_match",
                confidence=0.92,
                mapping_status="pending_teacher_confirmation",
            )
        if query:
            matches = self.curriculum.search(
                query,
                node_types={"knowledge_point"},
                limit=2,
            )
            if matches and matches[0].match_score >= 0.65:
                if len(matches) > 1 and matches[0].match_score == matches[1].match_score:
                    return None
                return self._curriculum_view(
                    matches[0].node_id,
                    mapping_source="brief_match",
                    confidence=matches[0].match_score,
                    mapping_status="pending_teacher_confirmation",
                )
        return None

    def _curriculum_options(self) -> tuple[QuestionDraftCurriculum, ...]:
        return tuple(
            self._curriculum_view(
                node.node_id,
                mapping_source="agent_inferred",
                confidence=None,
                mapping_status="pending_teacher_confirmation",
            )
            for node in self.curriculum.list_nodes()
            if node.node_type == "knowledge_point"
        )

    def _ground_generated_curriculum(
        self,
        content: ProviderQuestionDraft,
        *,
        guidance: QuestionDraftCurriculum | None,
    ) -> tuple[QuestionDraftCurriculum | None, str | None]:
        selected_id = (content.curriculum_node_id or "").strip()
        if not selected_id and guidance is not None:
            return guidance, None
        if not selected_id:
            return (
                None,
                "Agent 未能可靠映射教材知识点；草稿仍已生成，请在保存前由教师补充映射。",
            )
        try:
            node = self.curriculum.get_node(selected_id)
        except KeyError:
            return (
                None,
                "Agent 返回的教材节点不在受控目录中，已丢弃该映射；题目内容仍需教师复核。",
            )
        if node.node_type != "knowledge_point":
            return (
                None,
                "Agent 返回的教材节点不是知识点，已丢弃该映射；题目内容仍需教师复核。",
            )
        if guidance is not None and guidance.mapping_source == "teacher_selected":
            if selected_id != guidance.node_id:
                return (
                    guidance,
                    "Agent 建议的教材节点与教师选择不同；已保留教师确认的映射。",
                )
            return guidance, None
        if guidance is not None and selected_id == guidance.node_id:
            return guidance, None
        return (
            self._curriculum_view(
                selected_id,
                mapping_source="agent_inferred",
                confidence=None,
                mapping_status="pending_teacher_confirmation",
            ),
            "教材映射由 Agent 根据生成后的题目推断，尚待教师确认。",
        )

    def _teacher_confirmed_curriculum(self, node_id: str) -> QuestionDraftCurriculum:
        try:
            node = self.curriculum.get_node(node_id)
        except KeyError as exc:
            raise QuestionAuthoringError("所选教材知识点不存在") from exc
        if node.node_type != "knowledge_point":
            raise QuestionAuthoringError("教材映射必须选择具体知识点节点")
        return self._curriculum_view(
            node_id,
            mapping_source="teacher_selected",
            confidence=1.0,
            mapping_status="teacher_confirmed",
        )

    def _curriculum_view(
        self,
        node_id: str,
        *,
        mapping_source: str,
        confidence: float | None,
        mapping_status: str,
    ) -> QuestionDraftCurriculum:
        node = self.curriculum.get_node(node_id)
        path = self.curriculum.path_for(node_id)
        return QuestionDraftCurriculum(
            node_id=node.node_id,
            name=node.name,
            volume=path.get("volume", node.volume),
            chapter=path.get("chapter", ""),
            section=path.get("section", ""),
            mapping_source=mapping_source,
            mapping_status=mapping_status,
            match_confidence=confidence,
            curriculum_status=node.status,
            reviewed_by=node.reviewed_by,
        )

    @staticmethod
    def _infer_question_type(request_text: str) -> QuestionType:
        text = request_text.lower()
        if "多选" in text or "多项选择" in text:
            return "multiple_choice"
        if "单选" in text or "选择题" in text:
            return "single_choice"
        if "填空" in text:
            return "fill_blank"
        return "open_response"

    @staticmethod
    def _validate_structure(
        content: ProviderQuestionDraft,
        *,
        expected_type: QuestionType,
    ) -> None:
        required_text = {
            "题干": content.stem_plain,
            "答案": content.answer_value,
            "解法": content.solution_method,
            "最终答案": content.final_answer,
            "命题意图": content.authoring_intent,
        }
        blank_fields = [label for label, value in required_text.items() if not value.strip()]
        if blank_fields or any(not step.strip() for step in content.solution_steps):
            raise QuestionAuthoringError(
                "题目结构包含空白字段：" + "、".join(blank_fields or ["解析步骤"])
            )
        if content.question_type != expected_type:
            raise QuestionAuthoringError("模型返回的题型与教师要求不一致")
        keys = [option.key.strip() for option in content.options]
        if len(keys) != len(set(keys)):
            raise QuestionAuthoringError("模型返回了重复选项编号")
        if expected_type in {"single_choice", "multiple_choice"}:
            if len(content.options) < 4:
                raise QuestionAuthoringError("选择题必须至少提供四个可读选项")
            answers = QuestionAuthoring._answer_keys(content.answer_value)
            if not answers or not answers.issubset(set(keys)):
                raise QuestionAuthoringError("选择题答案必须引用现有选项编号")
        elif content.options:
            raise QuestionAuthoringError("非选择题不应返回选项")

    def _evaluate_trust(
        self,
        content: ProviderQuestionDraft,
        *,
        brief: QuestionDesignBrief,
        draft_id: str,
    ) -> QuestionDraftVerification:
        checks = [
            self._check_solvability(content),
            self._check_answer_solution_consistency(content),
            self._check_choice_answer_cardinality(content),
            self._check_distractor_quality(content),
            self._check_difficulty_disclosure(content, brief),
        ]
        (
            math_check,
            math_status,
            math_checked,
            verifier_version,
        ) = self._check_math_verifier(content, draft_id=draft_id)
        checks.append(math_check)
        failed = [check for check in checks if check.status == "failed"]
        status = "checks_failed" if failed else "teacher_review_required"
        details = [
            "已完成确定性结构与披露检查；这些检查不等于完整数学验证。",
            "一般数学可解性和干扰项语义仍需教师独立复核。",
        ]
        if failed:
            details.append(
                "阻断项：" + "；".join(check.summary for check in failed)
            )
        return QuestionDraftVerification(
            status=status,
            math_verifier_status=math_status,
            math_verifier_checked=math_checked,
            teacher_review_required=True,
            verifier_version=verifier_version,
            checks=checks,
            details=details,
        )

    @staticmethod
    def _check_solvability(content: ProviderQuestionDraft) -> QuestionDraftTrustCheck:
        combined = " ".join(
            [content.stem_plain, content.answer_value, *content.solution_steps, content.final_answer]
        )
        placeholders = [
            marker
            for marker in ("TODO", "TBD", "待补充", "请补充条件", "条件待定")
            if marker.lower() in combined.lower()
        ]
        if placeholders:
            return QuestionDraftTrustCheck(
                code="solvability",
                status="failed",
                capability="supported",
                evidence_source="deterministic_structure",
                summary="题目仍包含未完成占位内容",
                details=[f"检测到占位标记：{marker}" for marker in placeholders],
            )
        return QuestionDraftTrustCheck(
            code="solvability",
            status="inconclusive",
            capability="unsupported",
            evidence_source="none",
            summary="字段完整，但一般数学可解性尚无独立证据",
            details=["题干、答案和解析字段均非空；这只能证明结构完整。"],
        )

    @classmethod
    def _check_answer_solution_consistency(
        cls,
        content: ProviderQuestionDraft,
    ) -> QuestionDraftTrustCheck:
        if content.question_type in {"single_choice", "multiple_choice"}:
            answer_keys = cls._answer_keys(content.answer_value)
            explicit_keys = cls._explicit_answer_keys(content.final_answer)
            if explicit_keys and explicit_keys != answer_keys:
                return QuestionDraftTrustCheck(
                    code="answer_solution_consistency",
                    status="failed",
                    capability="supported",
                    evidence_source="deterministic_structure",
                    summary="最终答案明确指向了不同选项",
                    details=[
                        f"结构化答案为 {sorted(answer_keys)}，最终答案写为 {sorted(explicit_keys)}。"
                    ],
                )
            option_by_key = {
                option.key.strip(): cls._normalize(option.text)
                for option in content.options
            }
            normalized_final = cls._normalize(content.final_answer)
            selected_texts = [option_by_key[key] for key in answer_keys if key in option_by_key]
            if explicit_keys == answer_keys or (
                selected_texts and all(text and text in normalized_final for text in selected_texts)
            ):
                return QuestionDraftTrustCheck(
                    code="answer_solution_consistency",
                    status="passed",
                    capability="supported",
                    evidence_source="deterministic_structure",
                    summary="结构化答案与最终答案的可见表达一致",
                    details=["该结论只检查表示一致性，不证明选项在数学上正确。"],
                )
            return QuestionDraftTrustCheck(
                code="answer_solution_consistency",
                status="inconclusive",
                capability="supported",
                evidence_source="deterministic_structure",
                summary="无法用确定性文本规则确认答案与最终答案等价",
                details=["可能只是等价表达不同，需教师核对。"],
            )

        answer = cls._normalize(content.answer_value)
        final_answer = cls._normalize(content.final_answer)
        consistent = bool(answer and final_answer and (answer in final_answer or final_answer in answer))
        return QuestionDraftTrustCheck(
            code="answer_solution_consistency",
            status="passed" if consistent else "inconclusive",
            capability="supported",
            evidence_source="deterministic_structure",
            summary=(
                "结构化答案与最终答案的可见表达一致"
                if consistent
                else "无法用确定性文本规则确认答案与最终答案等价"
            ),
            details=["该检查不判断推导过程在数学上是否成立。"],
        )

    @classmethod
    def _check_choice_answer_cardinality(
        cls,
        content: ProviderQuestionDraft,
    ) -> QuestionDraftTrustCheck:
        if content.question_type not in {"single_choice", "multiple_choice"}:
            return QuestionDraftTrustCheck(
                code="choice_answer_cardinality",
                status="not_applicable",
                capability="supported",
                evidence_source="deterministic_structure",
                summary="非选择题不适用选项答案数量检查",
            )
        answers = cls._answer_keys(content.answer_value)
        if content.question_type == "single_choice":
            valid = len(answers) == 1
            expected = "恰好一个答案选项"
        else:
            valid = 2 <= len(answers) < len(content.options)
            expected = "至少两个且不能覆盖全部选项"
        return QuestionDraftTrustCheck(
            code="choice_answer_cardinality",
            status="passed" if valid else "failed",
            capability="supported",
            evidence_source="deterministic_structure",
            summary=(
                "答案选项数量符合题型"
                if valid
                else f"{content.question_type} 的答案必须{expected}"
            ),
            details=[f"当前答案选项：{sorted(answers)}。"],
        )

    @classmethod
    def _check_distractor_quality(
        cls,
        content: ProviderQuestionDraft,
    ) -> QuestionDraftTrustCheck:
        if content.question_type not in {"single_choice", "multiple_choice"}:
            return QuestionDraftTrustCheck(
                code="distractor_quality",
                status="not_applicable",
                capability="unsupported",
                evidence_source="none",
                summary="非选择题不适用干扰项检查",
            )
        normalized = [cls._normalize(option.text) for option in content.options]
        duplicate_text = len(normalized) != len(set(normalized))
        unreadable_text = any(not value for value in normalized)
        answers = cls._answer_keys(content.answer_value)
        distractor_count = sum(option.key.strip() not in answers for option in content.options)
        minimum = 3 if content.question_type == "single_choice" else 1
        if duplicate_text or unreadable_text or distractor_count < minimum:
            reasons = []
            if duplicate_text:
                reasons.append("存在文字完全相同的选项")
            if unreadable_text:
                reasons.append("存在规范化后为空的不可读选项")
            if distractor_count < minimum:
                reasons.append(f"干扰项少于 {minimum} 个")
            return QuestionDraftTrustCheck(
                code="distractor_quality",
                status="failed",
                capability="supported",
                evidence_source="deterministic_structure",
                summary="干扰项结构不合格",
                details=reasons,
            )
        return QuestionDraftTrustCheck(
            code="distractor_quality",
            status="inconclusive",
            capability="unsupported",
            evidence_source="none",
            summary="干扰项数量和文字唯一性合格，诊断价值尚未验证",
            details=["干扰项是否对应真实易错路径仍需教师判断。"],
        )

    @staticmethod
    def _check_difficulty_disclosure(
        content: ProviderQuestionDraft,
        brief: QuestionDesignBrief,
    ) -> QuestionDraftTrustCheck:
        gap = abs(content.estimated_difficulty - brief.target_difficulty)
        return QuestionDraftTrustCheck(
            code="difficulty_disclosure",
            status="passed" if gap <= 1 else "inconclusive",
            capability="supported",
            evidence_source="model_estimate",
            summary=(
                "模型预计难度接近教师目标"
                if gap <= 1
                else "模型预计难度与教师目标偏差较大"
            ),
            details=[
                f"教师目标 {brief.target_difficulty}/5；模型预计 {content.estimated_difficulty}/5。",
                "预计难度不是统计校准或 MathVerifier 结果。",
            ],
        )

    def _check_math_verifier(
        self,
        content: ProviderQuestionDraft,
        *,
        draft_id: str,
    ) -> tuple[QuestionDraftTrustCheck, str, bool, str]:
        candidate = {
            "question_id": draft_id,
            "question_type": content.question_type,
            "stem_plain": content.stem_plain,
            "options": [option.model_dump(mode="json") for option in content.options],
            "source_answer": content.answer_value,
            "solutions": [
                {
                    "steps_latex": content.solution_steps,
                    "final_answer": content.final_answer,
                }
            ],
        }
        version = self.math_verifier.VERSION
        if not self.math_verifier.supports(candidate):
            return (
                QuestionDraftTrustCheck(
                    code="math_verifier",
                    status="inconclusive",
                    capability="unsupported",
                    evidence_source="none",
                    summary="当前 MathVerifier 不支持该生成题",
                    details=[
                        "草稿没有受控 verification_spec；不能使用模型自己的重述冒充独立验证证据。"
                    ],
                ),
                "unsupported",
                False,
                version,
            )
        try:
            report = self.math_verifier.verify(candidate)
        except (KeyError, TypeError, ValueError) as exc:
            return (
                QuestionDraftTrustCheck(
                    code="math_verifier",
                    status="inconclusive",
                    capability="supported",
                    evidence_source="math_verifier",
                    summary="MathVerifier 未能给出确定结论",
                    details=[str(exc)],
                ),
                "inconclusive",
                False,
                version,
            )
        passed = report.status == "passed"
        return (
            QuestionDraftTrustCheck(
                code="math_verifier",
                status="passed" if passed else "failed",
                capability="supported",
                evidence_source="math_verifier",
                summary=(
                    "MathVerifier 独立计算与草稿答案一致"
                    if passed
                    else "MathVerifier 独立计算与草稿答案不一致"
                ),
                details=list(report.details),
            ),
            "passed" if passed else "failed",
            True,
            report.verifier_version,
        )

    @staticmethod
    def _answer_keys(value: str) -> set[str]:
        parts = {
            item.strip()
            for item in re.split(r"[,，、;；\s]+", value)
            if item.strip()
        }
        if len(parts) == 1:
            only = next(iter(parts))
            if re.fullmatch(r"[A-Z]{2,20}", only):
                return set(only)
        return parts

    @staticmethod
    def _explicit_answer_keys(value: str) -> set[str]:
        match = re.search(
            r"(?:答案|选择|选项|选)\s*(?:为|是|:|：)?\s*([A-Z](?:\s*[,，、;；]?\s*[A-Z])*)",
            value.upper(),
        )
        if not match:
            return set()
        return set(re.findall(r"[A-Z]", match.group(1)))

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value.lower())

    @staticmethod
    def _clean_list(values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for value in values:
            item = value.strip()
            if item and item not in cleaned:
                cleaned.append(item)
        return cleaned
