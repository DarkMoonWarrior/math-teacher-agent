from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

from app.modules.deepseek import DeepSeekClientError, DeepSeekJsonClient
from app.modules.model_operations import ModelRunRecorder, NullModelRunRecorder
from app.modules.question_authoring.schemas import (
    ProviderQuestionDraft,
    QuestionDesignBrief,
    QuestionDraftCurriculum,
    QuestionType,
)


PROMPT_REVISION = "question-authoring-v3-post-generation-grounding"


class QuestionAuthoringProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class QuestionAuthoringContext:
    brief: QuestionDesignBrief
    question_type: QuestionType
    curriculum: QuestionDraftCurriculum | None
    curriculum_options: tuple[QuestionDraftCurriculum, ...]


class QuestionAuthoringProvider(Protocol):
    name: str
    model: str

    def generate(self, context: QuestionAuthoringContext) -> ProviderQuestionDraft: ...


class DeepSeekQuestionAuthoringProvider:
    name = "deepseek"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        timeout_seconds: int = 90,
        recorder: ModelRunRecorder | None = None,
    ) -> None:
        self.model = model
        self.client = DeepSeekJsonClient(
            api_key=api_key,
            model=model,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
        )
        self.recorder = recorder or NullModelRunRecorder()

    def generate(self, context: QuestionAuthoringContext) -> ProviderQuestionDraft:
        provider_input = {
            "design_brief": context.brief.model_dump(
                mode="json",
                exclude_none=True,
                exclude={"reference_question_id"},
            ),
            "resolved_question_type": context.question_type,
            "teacher_curriculum_guidance": (
                context.curriculum.model_dump(mode="json")
                if context.curriculum is not None
                else None
            ),
            "allowed_curriculum_nodes": [
                {
                    "node_id": item.node_id,
                    "name": item.name,
                    "volume": item.volume,
                    "chapter": item.chapter,
                    "section": item.section,
                }
                for item in context.curriculum_options
            ],
        }
        instructions = (
            "你是面向中国高中数学教师的辅助命题模块。根据教师要求命制一道完整、可独立作答的中文数学题草稿。"
            "题干、答案与分步解析必须自洽；选择题必须提供明确选项，但不要声称已通过独立数学验证。"
            "单选题 answer_value 只能包含一个选项编号；多选题用逗号分隔多个编号；"
            "选择题的 final_answer 必须明确对应 answer_value，所有选项文字必须互不重复；"
            "填空题和解答题的 answer_value 与 final_answer 必须返回完全相同的最终答案。"
            "不得虚构学校、考试、年份、教材页码、题库来源或版权信息。"
            "教师可以只描述想要的题，不得因缺少知识点、考查方法或易错点而拒绝命题。"
            "生成题目后，再从 allowed_curriculum_nodes 中选择最贴切的 curriculum_node_id；"
            "只能返回列表内的 ID，无法可靠映射时返回 null。"
            "knowledge_points、assessed_methods 与 common_mistakes 应依据最终题目归纳，"
            "不要照抄空白输入，也不要把模型推断冒充教师确认。"
            "所有数学表达在普通文本中可读，stem_latex 使用 $...$ 或 $$...$$ 包裹公式。"
            "只返回 Schema 要求的题目内容；visibility、来源、验证与保存状态由业务模块写入。"
        )
        try:
            with self.recorder.track(
                feature="question_authoring",
                provider=self.name,
                model=self.model,
                prompt_version=PROMPT_REVISION,
            ) as run:
                raw = self.client.request(
                    instructions=instructions,
                    input_text=json.dumps(provider_input, ensure_ascii=False),
                    action="辅助命题",
                    output_schema=self._output_schema(),
                    max_tokens=5000,
                )
                run.capture_response(raw)
            content = self._extract_output_text(raw)
            payload = json.loads(content)
            if not isinstance(payload, dict):
                raise ValueError("顶层结果必须是 JSON 对象")
            self._normalize_non_choice_answer(payload)
            return ProviderQuestionDraft.model_validate(payload)
        except DeepSeekClientError as exc:
            raise QuestionAuthoringProviderError(str(exc)) from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise QuestionAuthoringProviderError(
                f"DeepSeek 返回内容不符合命题草稿结构：{exc}"
            ) from exc

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
    def _normalize_non_choice_answer(payload: dict) -> None:
        if payload.get("question_type") not in {"fill_blank", "open_response"}:
            return
        final_answer = payload.get("final_answer")
        if isinstance(final_answer, str) and final_answer.strip():
            payload["answer_value"] = final_answer.strip()

    @staticmethod
    def _output_schema() -> dict:
        option = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "key": {"type": "string"},
                "text": {"type": "string"},
            },
            "required": ["key", "text"],
        }
        properties = {
            "question_type": {
                "type": "string",
                "enum": [
                    "single_choice",
                    "multiple_choice",
                    "fill_blank",
                    "open_response",
                ],
            },
            "stem_plain": {"type": "string"},
            "stem_latex": {"type": ["string", "null"]},
            "options": {"type": "array", "items": option},
            "answer_value": {"type": "string", "minLength": 1},
            "solution_method": {"type": "string"},
            "solution_steps": {"type": "array", "items": {"type": "string"}},
            "final_answer": {"type": "string", "minLength": 1},
            "authoring_intent": {"type": "string"},
            "estimated_difficulty": {"type": "integer", "minimum": 1, "maximum": 5},
            "curriculum_node_id": {"type": ["string", "null"]},
            "knowledge_points": {"type": "array", "items": {"type": "string"}},
            "assessed_methods": {"type": "array", "items": {"type": "string"}},
            "common_mistakes": {"type": "array", "items": {"type": "string"}},
        }
        return {
            "type": "json_schema",
            "name": "private_question_authoring_draft",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": properties,
                "required": list(properties),
            },
        }
