from __future__ import annotations

import re
from typing import Protocol

from pydantic import ValidationError

from app.modules.lesson_plans.drafting import (
    LessonDrafting,
    LessonDraftingConflict,
    LessonDraftingError,
    ensure_lesson_high_school_scope,
)
from app.modules.lesson_plans.schemas import (
    LessonBlockRewriteCommand,
    LessonDraftBlock,
    LessonDraftCommand,
    LessonDraftRewriteRecord,
    LessonEditableDraft,
)


class LessonBlockEditingError(ValueError):
    pass


class LessonBlockEditingConflict(LessonBlockEditingError):
    pass


def ensure_lesson_source_facts_unchanged(
    submitted: LessonEditableDraft,
    current: LessonEditableDraft,
) -> None:
    """Rejects browser-supplied changes to server-owned source facts."""
    if submitted.source_draft != current.source_draft:
        raise LessonBlockEditingConflict("课程、题目或私人资料来源已经变化，请重新生成教案草稿。")
    if submitted.source_manifest != current.source_manifest:
        raise LessonBlockEditingConflict("来源清单已经变化，请重新生成教案草稿。")
    submitted_questions = {item.question_id: item for item in submitted.questions}
    current_questions = {item.question_id: item for item in current.questions}
    if submitted_questions.keys() != current_questions.keys():
        raise LessonBlockEditingConflict("题目来源已经变化，请重新生成教案草稿。")
    for question_id, question in submitted_questions.items():
        source_facts = question.model_dump(exclude={"phase_id", "usage"})
        current_facts = current_questions[question_id].model_dump(
            exclude={"phase_id", "usage"}
        )
        if source_facts != current_facts:
            raise LessonBlockEditingConflict(
                f"题目 {question_id} 的题面、选项、答案或解析已变化，请重新生成教案草稿。"
            )


class LessonDraftBlockRewriter(Protocol):
    name: str
    model: str

    def rewrite(
        self,
        draft: LessonEditableDraft,
        *,
        target_block: LessonDraftBlock,
        instruction: str,
    ) -> object: ...


class StructuredLessonDraftBlockRewriter:
    """Deterministic adapter that changes only the requested editable lesson block."""

    name = "structured_lesson_block_rewriter"
    model = "closed_loop_block_rewrite_v1"

    _SUFFIX = re.compile(r"[；，]?定向要求：.*?。?$", re.DOTALL)

    def rewrite(
        self,
        draft: LessonEditableDraft,
        *,
        target_block: LessonDraftBlock,
        instruction: str,
    ) -> object:
        focus = instruction.strip().rstrip("。；")
        if target_block == "objectives":
            return [
                item.model_copy(
                    update={
                        "text": self._with_focus(item.text, focus),
                        "observable_evidence": self._with_focus(
                            item.observable_evidence,
                            f"以“{focus}”作为补充观察点",
                        ),
                    }
                )
                for item in draft.objectives
            ]
        if target_block in {"key_points", "difficulties", "homework", "board_plan"}:
            return [self._with_focus(item, focus) for item in getattr(draft, target_block)]
        if target_block == "teacher_notes":
            retained = [
                item for item in draft.teacher_notes
                if not item.startswith("本轮定向重写要求：")
            ]
            return [*retained[:7], f"本轮定向重写要求：{focus}。"]
        if target_block == "teaching_flow":
            return [
                phase.model_copy(
                    update={
                        "teacher_activity": self._with_focus(
                            phase.teacher_activity,
                            f"围绕“{focus}”补充追问与示范",
                        ),
                        "student_activity": self._with_focus(
                            phase.student_activity,
                            f"围绕“{focus}”形成可观察产出",
                        ),
                        "assessment": self._with_focus(
                            phase.assessment,
                            f"增加“{focus}”对应的课堂证据",
                        ),
                    }
                )
                for phase in draft.teaching_flow
            ]
        if target_block == "questions":
            return [
                question.model_copy(
                    update={"usage": self._with_focus(question.usage, focus)}
                )
                for question in draft.questions
            ]
        if target_block == "assessments":
            return [
                assessment.model_copy(
                    update={
                        "method": self._with_focus(assessment.method, focus),
                        "success_criteria": self._with_focus(
                            assessment.success_criteria,
                            f"同时核对“{focus}”",
                        ),
                    }
                )
                for assessment in draft.assessments
            ]
        raise LessonBlockEditingError(f"不支持改写内容块：{target_block}")

    @classmethod
    def _with_focus(cls, value: str, focus: str) -> str:
        base = cls._SUFFIX.sub("", value.strip()).rstrip("。；，")
        return f"{base}；定向要求：{focus}。"


class LessonBlockEditing:
    """Rewrite one block while preserving exact sources and every non-target block."""

    def __init__(
        self,
        *,
        drafting: LessonDrafting,
        rewriter: LessonDraftBlockRewriter | None = None,
    ) -> None:
        self.drafting = drafting
        self.rewriter = rewriter or StructuredLessonDraftBlockRewriter()

    def rewrite(
        self,
        command: LessonBlockRewriteCommand,
        *,
        owner_id: str,
    ) -> LessonEditableDraft:
        draft = command.draft
        if command.target_block in draft.locked_blocks:
            raise LessonBlockEditingConflict(
                f"内容块 {command.target_block} 已锁定，请先解锁再改写。"
            )

        try:
            current = self.drafting.build(
                LessonDraftCommand(source_draft=draft.source_draft),
                owner_id=owner_id,
            )
        except LessonDraftingConflict as exc:
            raise LessonBlockEditingConflict(str(exc)) from exc
        except LessonDraftingError as exc:
            raise LessonBlockEditingError(str(exc)) from exc
        ensure_lesson_source_facts_unchanged(draft, current)

        replacement = self.rewriter.rewrite(
            draft,
            target_block=command.target_block,
            instruction=command.instruction,
        )
        revision = draft.draft_revision + 1
        payload = draft.model_dump(mode="python")
        payload[command.target_block] = replacement
        payload["draft_revision"] = revision
        payload["rewrite_history"] = [
            *draft.rewrite_history,
            LessonDraftRewriteRecord(
                draft_revision=revision,
                target_block=command.target_block,
                instruction=command.instruction.strip(),
                provider=self.rewriter.name,
                model=self.rewriter.model,
            ),
        ]
        payload["generation"] = {
            **draft.generation,
            "last_rewrite_provider": self.rewriter.name,
            "last_rewrite_model": self.rewriter.model,
        }
        try:
            result = LessonEditableDraft.model_validate(payload)
        except ValidationError as exc:
            raise LessonBlockEditingError(
                "定向重写未通过教案结构、时间或目标对应检查。"
            ) from exc
        try:
            ensure_lesson_high_school_scope(result)
        except LessonDraftingError as exc:
            raise LessonBlockEditingError(str(exc)) from exc
        return result
