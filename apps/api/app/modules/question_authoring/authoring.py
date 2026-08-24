from __future__ import annotations

import re
from datetime import datetime, timezone
from uuid import uuid4

from app.modules.curriculum import InMemoryCurriculumCatalog
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
    """Deep module for one unsaved, owner-only assisted-authored draft."""

    def __init__(
        self,
        *,
        curriculum: InMemoryCurriculumCatalog,
        provider: QuestionAuthoringProvider | None,
    ) -> None:
        self.curriculum = curriculum
        self.provider = provider

    def create_draft(self, brief: QuestionDesignBrief) -> GeneratedQuestionDraft:
        if brief.reference_question_id:
            raise QuestionAuthoringError(
                "参考母题模式尚未开放；必须在后续可信检查切片验证母题数学状态与改编权利后才能使用"
            )
        question_type = brief.question_type or self._infer_question_type(brief.request_text)
        curriculum = self._resolve_curriculum(brief)
        if self.provider is None:
            raise QuestionAuthoringUnavailableError(
                "当前没有可用的辅助命题模型；请配置 DeepSeek 后重试"
            )
        try:
            content = self.provider.generate(
                QuestionAuthoringContext(
                    brief=brief,
                    question_type=question_type,
                    curriculum=curriculum,
                )
            )
        except QuestionAuthoringProviderError as exc:
            raise QuestionAuthoringUnavailableError(str(exc)) from exc
        self._validate_structure(content, expected_type=question_type)
        warnings = [
            "本题由 AI 辅助生成，尚未运行 MathVerifier，必须由教师复核。",
            "当前草稿尚未保存，仅自己可见；不会进入公共题库或公共搜索。",
            "预计难度来自模型判断，不是统计校准或程序验证结果。",
        ]
        if brief.question_type is None:
            warnings.append(f"未明确题型，已从要求推断为 {question_type}。")
        return GeneratedQuestionDraft(
            draft_id=f"qad_{uuid4().hex[:16]}",
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
            target_difficulty=brief.target_difficulty,
            estimated_difficulty=content.estimated_difficulty,
            verification=QuestionDraftVerification(
                details=["结构化草稿已生成；数学可信检查将在 M8 切片 3 执行。"]
            ),
            provider=self.provider.name,
            model=self.provider.model,
            prompt_revision=PROMPT_REVISION,
            warnings=warnings,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def _resolve_curriculum(self, brief: QuestionDesignBrief) -> QuestionDraftCurriculum:
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
            )
        if query:
            matches = self.curriculum.search(
                query,
                node_types={"knowledge_point"},
                limit=2,
            )
            if matches and matches[0].match_score >= 0.65:
                if len(matches) > 1 and matches[0].match_score == matches[1].match_score:
                    raise QuestionAuthoringClarificationRequired(
                        "命题要求匹配到多个知识点，请从教材目录中明确选择一个知识点"
                    )
                return self._curriculum_view(
                    matches[0].node_id,
                    mapping_source="brief_match",
                    confidence=matches[0].match_score,
                )
        raise QuestionAuthoringClarificationRequired(
            "请补充明确的高中数学知识点，或从教材目录中选择一个知识点"
        )

    def _curriculum_view(
        self,
        node_id: str,
        *,
        mapping_source: str,
        confidence: float,
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
        if content.question_type != expected_type:
            raise QuestionAuthoringError("模型返回的题型与教师要求不一致")
        keys = [option.key.strip() for option in content.options]
        if len(keys) != len(set(keys)):
            raise QuestionAuthoringError("模型返回了重复选项编号")
        if expected_type in {"single_choice", "multiple_choice"}:
            if len(content.options) < 4:
                raise QuestionAuthoringError("选择题必须至少提供四个可读选项")
            answers = {
                item.strip()
                for item in re.split(r"[,，、;；\s]+", content.answer_value)
                if item.strip()
            }
            if not answers or not answers.issubset(set(keys)):
                raise QuestionAuthoringError("选择题答案必须引用现有选项编号")
        elif content.options:
            raise QuestionAuthoringError("非选择题不应返回选项")

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value.lower())
