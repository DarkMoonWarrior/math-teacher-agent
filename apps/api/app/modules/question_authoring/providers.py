from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.modules.deepseek import DeepSeekClientError, DeepSeekJsonClient
from app.modules.math_content import MATH_DISPLAY_INSTRUCTIONS
from app.modules.model_operations import ModelRunRecorder, NullModelRunRecorder
from app.modules.question_authoring.schemas import (
    ProviderQuestionDraft,
    ProviderQuestionSolution,
    QuestionDesignBrief,
    QuestionDraftCurriculum,
    QuestionDraftOption,
    QuestionType,
)


PROMPT_REVISION = "question-authoring-v6-resilient-draft"


_DELIBERATION_PATTERNS = (
    r"让我们(?:重新|再|先|仔细)",
    r"我们(?:可能|需要重新|重新审视|重新检查|忘记|算错|犯了|理解错|错误地)",
    r"我(?:可能|需要重新|重新审视|重新检查|算错|犯了|理解错)",
    r"(?:重新|再次)(?:核对|检查|审题|推导|计算)",
    r"(?:前面|之前).{0,30}(?:算错|不对|错误|有误)",
    r"题(?:面|目|干).{0,40}(?:有问题|有误|错误|缺失|矛盾)",
    r"(?:与题设|与初始条件|初始条件).{0,30}(?:不符|不一致|矛盾)",
    r"无法(?:验证|选出|得到).{0,20}(?:答案|结论)",
    r"作为(?:解题|模型|AI)",
    r"final[_ ]?answer",
    r"(?:let us|let's)\s+(?:reconsider|recalculate|check again|start over)",
    r"(?:we|i)\s+(?:may have|might have|need to)\s+(?:made|reconsider|recalculate)",
)


_POLISHED_SOLUTION_INSTRUCTIONS = (
    "输出必须是可直接交给教师和学生阅读的成稿解析。"
    "先在模型内部完成试算、核对和纠错，返回内容只保留最终采用的连贯推导。"
    "严禁出现第一人称独白、思考过程、尝试失败、回退、自我怀疑、提示词讨论、"
    "字段名或诸如‘让我们重新审视’‘我们可能算错了’的元叙述。"
)


class QuestionAuthoringProviderError(RuntimeError):
    pass


class _QuestionAuthoringSolutionConflict(QuestionAuthoringProviderError):
    def __init__(self, *, order: int, issue: str) -> None:
        self.order = order
        self.issue = issue
        super().__init__(
            f"第 {order} 段解析发现数学冲突，已停止展示试算过程：{issue}"
        )


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

    def regenerate_solution(
        self,
        current: ProviderQuestionDraft,
    ) -> ProviderQuestionSolution: ...


class _QuestionCore(BaseModel):
    """Immutable question and answer contract used by every later stage."""

    model_config = ConfigDict(extra="forbid")

    question_type: QuestionType
    stem_plain: str = Field(min_length=5, max_length=20000)
    stem_latex: str | None = Field(default=None, max_length=20000)
    options: list[QuestionDraftOption] = Field(default_factory=list, max_length=20)
    answer_value: str = Field(min_length=1, max_length=4000)
    final_answer: str = Field(min_length=1, max_length=4000)
    estimated_difficulty: int = Field(ge=1, le=5)


class _SolutionPlanSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order: int = Field(ge=1, le=12)
    title: str = Field(min_length=1, max_length=120)
    goal: str = Field(min_length=1, max_length=500)


class _SolutionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    solution_method: str = Field(min_length=1, max_length=500)
    sections: list[_SolutionPlanSection] = Field(min_length=1, max_length=12)
    authoring_intent: str = Field(min_length=1, max_length=2000)
    curriculum_node_id: str | None = Field(default=None, max_length=160)
    knowledge_points: list[str] = Field(default_factory=list, max_length=20)
    assessed_methods: list[str] = Field(default_factory=list, max_length=20)
    common_mistakes: list[str] = Field(default_factory=list, max_length=20)


class _SolutionRegenerationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    solution_method: str = Field(min_length=1, max_length=500)
    sections: list[_SolutionPlanSection] = Field(min_length=1, max_length=12)


class _SolutionSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order: int = Field(ge=1, le=12)
    steps: list[str] = Field(min_length=1, max_length=100)


class _SolutionCleanup(_SolutionSection):
    consistent_with_locked_answer: bool
    issue_summary: str | None = Field(default=None, max_length=500)


class _SolutionSubplan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parts: list[_SolutionPlanSection] = Field(min_length=2, max_length=6)


class DeepSeekQuestionAuthoringProvider:
    """Generate a long draft through bounded internal stages behind one provider seam."""

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
        provider_input = self._provider_input(context)
        try:
            core_payload = self._request_stage(
                stage="core",
                instructions=(
                    "你是面向中国高中数学教师的辅助命题模块。先生成完整题面与最终答案骨架。"
                    "教师可能要求综合题、多小问题或长题干；必须完整保留解题所需条件和所有小问，"
                    "不得为了缩短输出删题、合并小问或降低难度。题目必须可独立作答且题干、答案自洽。"
                    "选择题必须给出明确且互不重复的选项；单选 answer_value 只能有一个编号，"
                    "多选用逗号分隔。填空题和解答题的 answer_value 与 final_answer 必须相同。"
                    "不得虚构学校、考试、年份、教材页码、题库来源或版权信息。"
                    f"{MATH_DISPLAY_INSTRUCTIONS}"
                    "stem_plain 应是无需 LaTeX 渲染也能校对的题面；stem_latex 是供页面展示的可读版本。"
                    "本阶段只返回题面、选项、最终答案与难度，不展开解析。"
                ),
                input_value={
                    "design_brief": provider_input["design_brief"],
                    "resolved_question_type": provider_input["resolved_question_type"],
                    "teacher_curriculum_guidance": provider_input[
                        "teacher_curriculum_guidance"
                    ],
                },
                output_schema=self._core_schema(),
                max_tokens=8192,
                recovery_instruction="只修复 JSON 结构并完整返回题面与全部小问；不得截短题目。",
            )
            self._normalize_non_choice_answer(core_payload)
            core = _QuestionCore.model_validate(core_payload)

            plan: _SolutionPlan | None = None
            try:
                plan = _SolutionPlan.model_validate(
                    self._request_stage(
                        stage="solution-plan",
                        instructions=(
                            "根据已经锁定的题面与最终答案，规划一份适合教师审核和讲解的完整解析。"
                            "先把长解析拆成有明确目标的若干段，本阶段不要展开详细计算。"
                            "多小问题必须逐问覆盖；复杂推导应继续拆段，不能因篇幅省略关键论证。"
                            "教师可以只描述想要的题，不得因缺少知识点、考查方法或易错点而拒绝。"
                            "生成题目后，再从 allowed_curriculum_nodes 中选择最贴切的 curriculum_node_id；"
                            "只能返回列表内 ID，无法可靠映射时返回 null。"
                            "knowledge_points、assessed_methods 与 common_mistakes 必须依据最终题目归纳，"
                            "不要把模型推断冒充教师确认。"
                        ),
                        input_value={
                            "design_brief": provider_input["design_brief"],
                            "question_core": core.model_dump(mode="json"),
                            "allowed_curriculum_nodes": provider_input[
                                "allowed_curriculum_nodes"
                            ],
                        },
                        output_schema=self._solution_plan_schema(),
                        max_tokens=3500,
                        recovery_instruction="只修复 JSON 结构；保留覆盖全部小问所需的解析分段。",
                    )
                )
                self._validate_plan_orders(plan)
                sections = self._expand_sections(core, plan)
                steps = [step for section in sections for step in section.steps]
                solution_status = "ready"
                solution_issue = None
            except _QuestionAuthoringSolutionConflict as exc:
                steps = [
                    "解析未通过一致性检查，请教师根据完整题面自行核验，或重新生成解析。"
                ]
                solution_status = "needs_teacher_verification"
                solution_issue = exc.issue
            except (
                QuestionAuthoringProviderError,
                DeepSeekClientError,
                KeyError,
                TypeError,
                ValueError,
            ):
                steps = [
                    "解析生成未完成，请教师根据完整题面自行核验，或重新生成解析。"
                ]
                solution_status = "needs_teacher_verification"
                solution_issue = "解析生成未完成；题面、选项与最终答案已完整保留。"

            return ProviderQuestionDraft(
                question_type=core.question_type,
                stem_plain=core.stem_plain,
                stem_latex=core.stem_latex,
                options=core.options,
                answer_value=core.answer_value,
                solution_method=(plan.solution_method if plan else "解析待教师核验"),
                solution_steps=steps,
                solution_status=solution_status,
                solution_issue=solution_issue,
                final_answer=core.final_answer,
                authoring_intent=(plan.authoring_intent if plan else context.brief.request_text),
                estimated_difficulty=core.estimated_difficulty,
                curriculum_node_id=(
                    plan.curriculum_node_id
                    if plan
                    else (context.curriculum.node_id if context.curriculum else None)
                ),
                knowledge_points=(plan.knowledge_points if plan else []),
                assessed_methods=(plan.assessed_methods if plan else []),
                common_mistakes=(plan.common_mistakes if plan else []),
            )
        except QuestionAuthoringProviderError:
            raise
        except DeepSeekClientError as exc:
            raise QuestionAuthoringProviderError(str(exc)) from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise QuestionAuthoringProviderError(
                f"DeepSeek 返回内容不符合命题草稿结构：{exc}"
            ) from exc

    def regenerate_solution(
        self,
        current: ProviderQuestionDraft,
    ) -> ProviderQuestionSolution:
        """Regenerate only the explanation behind an immutable question contract."""

        core = _QuestionCore(
            question_type=current.question_type,
            stem_plain=current.stem_plain,
            stem_latex=current.stem_latex,
            options=current.options,
            answer_value=current.answer_value,
            final_answer=current.final_answer,
            estimated_difficulty=current.estimated_difficulty,
        )
        try:
            plan = _SolutionRegenerationPlan.model_validate(
                self._request_stage(
                    stage="solution-regeneration-plan",
                    instructions=(
                        "为已经锁定的题面、选项和最终答案重新规划一份全新的解析。"
                        "不得修改或补写题面条件，不得改变答案；多小问必须逐问覆盖。"
                        "本阶段只返回新的解法概述和分段提纲，不展开计算。"
                        f"{_POLISHED_SOLUTION_INSTRUCTIONS}"
                    ),
                    input_value={"locked_question_core": core.model_dump(mode="json")},
                    output_schema=self._solution_regeneration_plan_schema(),
                    max_tokens=2500,
                    recovery_instruction="只修复 JSON 结构；保留覆盖全部小问所需的解析分段。",
                )
            )
            self._validate_plan_orders(plan)
            try:
                sections = self._expand_sections(core, plan)
                return ProviderQuestionSolution(
                    solution_method=plan.solution_method,
                    solution_steps=[step for section in sections for step in section.steps],
                )
            except _QuestionAuthoringSolutionConflict as exc:
                return ProviderQuestionSolution(
                    solution_method=plan.solution_method,
                    solution_steps=[
                        "解析未通过一致性检查，请教师根据完整题面自行核验，或再次重新生成解析。"
                    ],
                    solution_status="needs_teacher_verification",
                    solution_issue=exc.issue,
                )
        except QuestionAuthoringProviderError:
            raise
        except DeepSeekClientError as exc:
            raise QuestionAuthoringProviderError(str(exc)) from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise QuestionAuthoringProviderError(
                f"DeepSeek 返回的重生成解析不符合结构：{exc}"
            ) from exc

    def _expand_sections(
        self,
        core: _QuestionCore,
        plan: _SolutionPlan | _SolutionRegenerationPlan,
    ) -> list[_SolutionSection]:
        workers = min(3, len(plan.sections))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            sections = list(
                executor.map(
                    lambda section: self._expand_solution_section(core, plan, section),
                    plan.sections,
                )
            )
        sections.sort(key=lambda item: item.order)
        expected = list(range(1, len(plan.sections) + 1))
        if [item.order for item in sections] != expected:
            raise QuestionAuthoringProviderError("分段解析序号不完整，未组装为草稿")
        return sections

    def _expand_solution_section(
        self,
        core: _QuestionCore,
        plan: _SolutionPlan | _SolutionRegenerationPlan,
        section: _SolutionPlanSection,
    ) -> _SolutionSection:
        input_value = {
            "question_core": core.model_dump(mode="json"),
            "solution_method": plan.solution_method,
            "solution_outline": [item.model_dump(mode="json") for item in plan.sections],
            "section": section.model_dump(mode="json"),
        }
        instructions = (
            "只展开解析提纲中指定的当前一段，给出教师和学生都能读懂的完整推导步骤。"
            "必须以锁定题面和锁定最终答案为准，不得改题、添加未给条件或改变最终结论。"
            "每一步都写清数学依据；涉及多个小问时保留当前小问的层次。"
            "不要重复整道题，也不要重复其他解析段。"
            f"{_POLISHED_SOLUTION_INSTRUCTIONS}"
            f"{MATH_DISPLAY_INSTRUCTIONS}"
            "不要为了减少字数省略关键等价变形、分类讨论、取值范围或结论核对。"
        )
        try:
            return self._request_solution_section(
                section=section,
                stage=f"solution-section-{section.order}",
                input_value=input_value,
                instructions=instructions,
            )
        except _QuestionAuthoringSolutionConflict:
            raise
        except QuestionAuthoringProviderError as original_error:
            return self._subdivide_and_expand(
                core=core,
                plan=plan,
                section=section,
                original_error=original_error,
            )

    def _request_solution_section(
        self,
        *,
        section: _SolutionPlanSection,
        stage: str,
        input_value: dict,
        instructions: str,
    ) -> _SolutionSection:
        last_error: DeepSeekClientError | ValueError | None = None
        for attempt in range(2):
            try:
                payload = self._request_stage(
                    stage=stage,
                    instructions=instructions,
                    input_value=input_value,
                    output_schema=self._solution_section_schema(),
                    max_tokens=8192,
                    recovery_instruction="只修复当前解析段的 JSON；完整保留该段推导，不要返回其他段。",
                )
                parsed = _SolutionSection.model_validate(payload)
                if parsed.order != section.order:
                    raise ValueError(
                        f"解析段序号应为 {section.order}，实际为 {parsed.order}"
                    )
                if self._contains_deliberation(parsed.steps):
                    parsed = self._cleanup_solution_section(
                        section=section,
                        input_value=input_value,
                        contaminated=parsed,
                    )
                return parsed
            except (DeepSeekClientError, ValueError) as exc:
                last_error = exc
                if attempt == 0:
                    continue
        raise QuestionAuthoringProviderError(
            f"第 {section.order} 段解析生成失败：{last_error}"
        )

    def _cleanup_solution_section(
        self,
        *,
        section: _SolutionPlanSection,
        input_value: dict,
        contaminated: _SolutionSection,
    ) -> _SolutionSection:
        payload = self._request_stage(
            stage=f"solution-section-{section.order}-cleanup",
            instructions=(
                "把当前解析草稿改写为可直接展示的正式解析。删除所有试算、回退、自我纠错、"
                "第一人称独白、提示词或字段讨论，只保留最终采用的严谨推导；不要缩短必要步骤。"
                "题面与最终答案已锁定，不得修改。若你确认二者在数学上无法同时成立，"
                "将 consistent_with_locked_answer 设为 false，并用 issue_summary 简洁说明矛盾；"
                "此时 steps 仍返回一条简短的教师复核提示，不得伪造证明。"
                f"{MATH_DISPLAY_INSTRUCTIONS}"
            ),
            input_value={
                **input_value,
                "contaminated_solution_steps": contaminated.steps,
            },
            output_schema=self._solution_cleanup_schema(),
            max_tokens=8192,
            recovery_instruction="只修复清理后解析的 JSON，不得恢复思考过程。",
        )
        cleaned = _SolutionCleanup.model_validate(payload)
        if cleaned.order != section.order:
            raise ValueError(
                f"清理后解析段序号应为 {section.order}，实际为 {cleaned.order}"
            )
        if not cleaned.consistent_with_locked_answer:
            issue = (cleaned.issue_summary or "题面与锁定答案可能不一致").strip()
            if self._contains_deliberation([issue]):
                issue = "解析与锁定题面或最终答案存在数学冲突。"
            raise _QuestionAuthoringSolutionConflict(order=section.order, issue=issue)
        if self._contains_deliberation(cleaned.steps):
            raise ValueError("清理后的解析仍包含模型思考或自我纠错叙述")
        return _SolutionSection(order=cleaned.order, steps=cleaned.steps)

    @staticmethod
    def _contains_deliberation(steps: list[str]) -> bool:
        combined = "\n".join(steps)
        return any(
            re.search(pattern, combined, flags=re.IGNORECASE | re.DOTALL)
            for pattern in _DELIBERATION_PATTERNS
        )

    def _subdivide_and_expand(
        self,
        *,
        core: _QuestionCore,
        plan: _SolutionPlan | _SolutionRegenerationPlan,
        section: _SolutionPlanSection,
        original_error: QuestionAuthoringProviderError,
    ) -> _SolutionSection:
        try:
            subplan = _SolutionSubplan.model_validate(
                self._request_stage(
                    stage=f"solution-section-{section.order}-subplan",
                    instructions=(
                        "当前解析段对于一次模型输出过长。只把该段拆成 2 到 6 个连续、互不重叠的原子子段。"
                        "子段合并后必须完整实现原段目标，不得删减推导、改变题面或最终答案。"
                        "本阶段只返回子段标题和目标，不展开计算。"
                    ),
                    input_value={
                        "question_core": core.model_dump(mode="json"),
                        "solution_method": plan.solution_method,
                        "parent_section": section.model_dump(mode="json"),
                    },
                    output_schema=self._solution_subplan_schema(),
                    max_tokens=1800,
                    recovery_instruction="只修复子段提纲 JSON；保留全部连续子段。",
                )
            )
            orders = [part.order for part in subplan.parts]
            if orders != list(range(1, len(orders) + 1)):
                raise ValueError("解析子段序号必须从 1 连续递增且不可重复")

            def expand_part(part: _SolutionPlanSection) -> _SolutionSection:
                return self._request_solution_section(
                    section=part,
                    stage=f"solution-section-{section.order}-part-{part.order}",
                    input_value={
                        "question_core": core.model_dump(mode="json"),
                        "solution_method": plan.solution_method,
                        "solution_outline": [
                            item.model_dump(mode="json") for item in plan.sections
                        ],
                        "parent_section": section.model_dump(mode="json"),
                        "section": part.model_dump(mode="json"),
                    },
                    instructions=(
                        "只展开当前原子子段，完整写出教师可读的数学推导；不得重复父段或其他子段。"
                        "必须使用锁定题面和最终答案，不得改题或省略当前目标所需的依据。"
                        f"{_POLISHED_SOLUTION_INSTRUCTIONS}"
                        f"{MATH_DISPLAY_INSTRUCTIONS}"
                    ),
                )

            with ThreadPoolExecutor(max_workers=min(3, len(subplan.parts))) as executor:
                expanded = list(executor.map(expand_part, subplan.parts))
            expanded.sort(key=lambda item: item.order)
            steps = [step for part in expanded for step in part.steps]
            return _SolutionSection(order=section.order, steps=steps)
        except QuestionAuthoringProviderError:
            raise
        except (DeepSeekClientError, KeyError, TypeError, ValueError) as exc:
            raise QuestionAuthoringProviderError(
                f"第 {section.order} 段拆分恢复失败（原错误：{original_error}）：{exc}"
            ) from exc

    def _request_stage(
        self,
        *,
        stage: str,
        instructions: str,
        input_value: dict,
        output_schema: dict,
        max_tokens: int,
        recovery_instruction: str,
    ) -> dict:
        with self.recorder.track(
            feature="question_authoring",
            provider=self.name,
            model=self.model,
            prompt_version=f"{PROMPT_REVISION}:{stage}",
        ) as run:
            raw = self.client.request(
                instructions=instructions,
                input_text=json.dumps(input_value, ensure_ascii=False),
                action=f"辅助命题（{stage}）",
                output_schema=output_schema,
                max_tokens=max_tokens,
                recovery_instruction=recovery_instruction,
            )
            run.capture_response(raw)
        content = self._extract_output_text(raw)
        payload = json.loads(content)
        if not isinstance(payload, dict):
            raise ValueError("顶层结果必须是 JSON 对象")
        return payload

    @staticmethod
    def _provider_input(context: QuestionAuthoringContext) -> dict:
        return {
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

    @staticmethod
    def _validate_plan_orders(
        plan: _SolutionPlan | _SolutionRegenerationPlan,
    ) -> None:
        orders = [item.order for item in plan.sections]
        if orders != list(range(1, len(orders) + 1)):
            raise ValueError("解析提纲序号必须从 1 连续递增且不可重复")

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
    def _option_schema() -> dict:
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "key": {"type": "string", "minLength": 1, "maxLength": 12},
                "text": {"type": "string", "minLength": 1, "maxLength": 4000},
            },
            "required": ["key", "text"],
        }

    @classmethod
    def _core_schema(cls) -> dict:
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
            "stem_plain": {"type": "string", "minLength": 5, "maxLength": 20000},
            "stem_latex": {"type": ["string", "null"], "maxLength": 20000},
            "options": {"type": "array", "maxItems": 20, "items": cls._option_schema()},
            "answer_value": {"type": "string", "maxLength": 4000},
            "final_answer": {"type": "string", "minLength": 1, "maxLength": 4000},
            "estimated_difficulty": {"type": "integer", "minimum": 1, "maximum": 5},
        }
        return cls._schema("private_question_authoring_core", properties)

    @classmethod
    def _solution_plan_schema(cls) -> dict:
        section = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "order": {"type": "integer", "minimum": 1, "maximum": 12},
                "title": {"type": "string", "minLength": 1, "maxLength": 120},
                "goal": {"type": "string", "minLength": 1, "maxLength": 500},
            },
            "required": ["order", "title", "goal"],
        }
        properties = {
            "solution_method": {"type": "string", "minLength": 1, "maxLength": 500},
            "sections": {
                "type": "array",
                "minItems": 1,
                "maxItems": 12,
                "items": section,
            },
            "authoring_intent": {"type": "string", "minLength": 1, "maxLength": 2000},
            "curriculum_node_id": {"type": ["string", "null"], "maxLength": 160},
            "knowledge_points": {
                "type": "array",
                "maxItems": 20,
                "items": {"type": "string", "maxLength": 300},
            },
            "assessed_methods": {
                "type": "array",
                "maxItems": 20,
                "items": {"type": "string", "maxLength": 300},
            },
            "common_mistakes": {
                "type": "array",
                "maxItems": 20,
                "items": {"type": "string", "maxLength": 300},
            },
        }
        return cls._schema("private_question_authoring_solution_plan", properties)

    @classmethod
    def _solution_regeneration_plan_schema(cls) -> dict:
        section = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "order": {"type": "integer", "minimum": 1, "maximum": 12},
                "title": {"type": "string", "minLength": 1, "maxLength": 120},
                "goal": {"type": "string", "minLength": 1, "maxLength": 500},
            },
            "required": ["order", "title", "goal"],
        }
        properties = {
            "solution_method": {"type": "string", "minLength": 1, "maxLength": 500},
            "sections": {
                "type": "array",
                "minItems": 1,
                "maxItems": 12,
                "items": section,
            },
        }
        return cls._schema(
            "private_question_authoring_solution_regeneration_plan",
            properties,
        )

    @classmethod
    def _solution_section_schema(cls) -> dict:
        properties = {
            "order": {"type": "integer", "minimum": 1, "maximum": 12},
            "steps": {
                "type": "array",
                "minItems": 1,
                "maxItems": 100,
                "items": {"type": "string", "minLength": 1, "maxLength": 6000},
            },
        }
        return cls._schema("private_question_authoring_solution_section", properties)

    @classmethod
    def _solution_cleanup_schema(cls) -> dict:
        properties = {
            "order": {"type": "integer", "minimum": 1, "maximum": 12},
            "steps": {
                "type": "array",
                "minItems": 1,
                "maxItems": 100,
                "items": {"type": "string", "minLength": 1, "maxLength": 6000},
            },
            "consistent_with_locked_answer": {"type": "boolean"},
            "issue_summary": {"type": ["string", "null"], "maxLength": 500},
        }
        return cls._schema("private_question_authoring_solution_cleanup", properties)

    @classmethod
    def _solution_subplan_schema(cls) -> dict:
        part = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "order": {"type": "integer", "minimum": 1, "maximum": 6},
                "title": {"type": "string", "minLength": 1, "maxLength": 120},
                "goal": {"type": "string", "minLength": 1, "maxLength": 500},
            },
            "required": ["order", "title", "goal"],
        }
        properties = {
            "parts": {
                "type": "array",
                "minItems": 2,
                "maxItems": 6,
                "items": part,
            }
        }
        return cls._schema("private_question_authoring_solution_subplan", properties)

    @staticmethod
    def _schema(name: str, properties: dict) -> dict:
        return {
            "type": "json_schema",
            "name": name,
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": properties,
                "required": list(properties),
            },
        }
