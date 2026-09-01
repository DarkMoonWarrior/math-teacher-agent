from __future__ import annotations

from app.modules.lesson_plans.schemas import (
    LessonDraftAssessment,
    LessonDraftCommand,
    LessonDraftObjective,
    LessonDraftQuestionUse,
    LessonDraftSourceRef,
    LessonDraftTeachingPhase,
    LessonEditableDraft,
    LessonSourceDraft,
    LessonSourceSelectionCommand,
)
from app.modules.lesson_plans.source_selection import (
    LessonSourceSelection,
    LessonSourceSelectionError,
)


class LessonDraftingError(ValueError):
    pass


class LessonDraftingConflict(LessonDraftingError):
    pass


def ensure_lesson_high_school_scope(draft: LessonEditableDraft) -> None:
    text = " ".join(
        [
            draft.title,
            *[item.text for item in draft.objectives],
            *draft.key_points,
            *draft.difficulties,
            *[item.teacher_activity for item in draft.teaching_flow],
            *[item.student_activity for item in draft.teaching_flow],
            *[item.assessment for item in draft.teaching_flow],
            *[item.method for item in draft.assessments],
            *[item.success_criteria for item in draft.assessments],
            *draft.homework,
            *draft.board_plan,
            *draft.teacher_notes,
        ]
    )
    if any(marker in text for marker in LessonSourceSelection.UNIVERSITY_MARKERS):
        raise LessonDraftingError("M10 只支持中国普通高中数学教案。")


class LessonDrafting:
    """Build a complete, traceable and unsaved lesson from exact gated sources."""

    UNIVERSITY_MARKERS = LessonSourceSelection.UNIVERSITY_MARKERS

    def __init__(self, *, source_selection: LessonSourceSelection) -> None:
        self.source_selection = source_selection

    def build(
        self,
        command: LessonDraftCommand,
        *,
        owner_id: str,
    ) -> LessonEditableDraft:
        source_draft = self._revalidate_sources(command.source_draft, owner_id=owner_id)
        blueprint = source_draft.blueprint
        if not source_draft.selection_complete or source_draft.gaps:
            raise LessonDraftingError("来源草案仍有真实缺口，不能生成完整教案。")

        objectives = [
            LessonDraftObjective(
                objective_id=f"O{index}",
                text=text,
                observable_evidence=(
                    f"学生能围绕“{text.rstrip('。')}”完成口头解释、书面推理或课堂任务，"
                    "并说明所用条件。"
                ),
            )
            for index, text in enumerate(blueprint.objectives, start=1)
        ]
        objective_ids = [item.objective_id for item in objectives]
        phase_objectives: list[list[str]] = [[] for _ in blueprint.phases]
        for index, objective_id in enumerate(objective_ids):
            phase_objectives[index % len(phase_objectives)].append(objective_id)
        for values in phase_objectives:
            if not values:
                values.append(objective_ids[0])

        practice_index = self._practice_phase_index(blueprint.phases)
        question_ids = [item.question_id for item in source_draft.questions]
        resource_ids = [item.library_item_id for item in source_draft.private_resources]
        teaching_flow = [
            LessonDraftTeachingPhase(
                phase_id=phase.phase_id,
                title=phase.title,
                minutes=phase.minutes,
                purpose=phase.purpose,
                teacher_activity=self._teacher_activity(
                    phase.title,
                    phase.purpose,
                    blueprint.focus,
                    question_ids if index == practice_index else [],
                    resource_ids if index == 1 else [],
                ),
                student_activity=self._student_activity(phase.title, phase.purpose),
                assessment=self._phase_assessment(
                    phase.title,
                    phase_objectives[index],
                ),
                objective_ids=phase_objectives[index],
                question_ids=question_ids if index == practice_index else [],
                resource_ids=resource_ids if index == 1 else [],
            )
            for index, phase in enumerate(blueprint.phases)
        ]

        assessments = [
            LessonDraftAssessment(
                assessment_id=f"A{index}",
                title=f"目标 {objective.objective_id} 学习证据",
                method=(
                    "通过课堂追问、书面过程、同伴解释与出口任务收集证据，"
                    "不以模型自评代替教师判断。"
                ),
                success_criteria=objective.observable_evidence,
                objective_ids=[objective.objective_id],
            )
            for index, objective in enumerate(objectives, start=1)
        ]

        questions = [
            self._resolve_question(
                item,
                phase_id=blueprint.phases[practice_index].phase_id,
                owner_id=owner_id,
            )
            for item in source_draft.questions
        ]
        source_manifest = self._source_manifest(source_draft)
        draft = LessonEditableDraft(
            title=blueprint.title,
            source_draft=source_draft,
            objectives=objectives,
            key_points=list(blueprint.key_points),
            difficulties=list(blueprint.difficulties),
            teaching_flow=teaching_flow,
            questions=questions,
            assessments=assessments,
            homework=self._homework(blueprint.focus, questions),
            board_plan=self._board_plan(blueprint, questions),
            teacher_notes=self._teacher_notes(source_draft),
            source_manifest=source_manifest,
        )
        ensure_lesson_high_school_scope(draft)
        return draft

    def _revalidate_sources(
        self,
        submitted: LessonSourceDraft,
        *,
        owner_id: str,
    ) -> LessonSourceDraft:
        public_ids = [
            item.question_id
            for item in submitted.questions
            if item.source_kind == "public_question_bank"
        ]
        private_ids = [
            item.question_id
            for item in submitted.questions
            if item.source_kind == "personal_question_library"
        ]
        resource_ids = [item.library_item_id for item in submitted.private_resources]
        try:
            current = self.source_selection.select(
                LessonSourceSelectionCommand(
                    blueprint=submitted.blueprint,
                    selected_public_question_ids=public_ids,
                    selected_private_question_ids=private_ids,
                    selected_private_resource_ids=resource_ids,
                ),
                owner_id=owner_id,
            )
        except LessonSourceSelectionError as exc:
            raise LessonDraftingError(str(exc)) from exc
        if not current.selection_complete:
            raise LessonDraftingError("来源草案仍有真实缺口，不能生成完整教案。")

        submitted_questions = {item.question_id: item for item in submitted.questions}
        for item in current.questions:
            previous = submitted_questions.get(item.question_id)
            if previous is None or (
                previous.source_revision != item.source_revision
                or previous.rights_basis != item.rights_basis
                or previous.verification_status != item.verification_status
                or previous.review_status != item.review_status
                or previous.owner_scope != item.owner_scope
            ):
                raise LessonDraftingConflict(
                    f"题目 {item.question_id} 的 revision 或可信状态已变化，请重新确认来源。"
                )
        submitted_resources = {
            item.library_item_id: item for item in submitted.private_resources
        }
        for item in current.private_resources:
            previous = submitted_resources.get(item.library_item_id)
            if previous is None or (
                previous.source_version != item.source_version
                or previous.rights_basis != item.rights_basis
                or previous.text_review_status != item.text_review_status
            ):
                raise LessonDraftingConflict(
                    f"私人资料 {item.library_item_id} 的版本或权利状态已变化，请重新确认来源。"
                )
        return current

    def _resolve_question(
        self,
        item,
        *,
        phase_id: str,
        owner_id: str,
    ) -> LessonDraftQuestionUse:
        if item.source_kind == "public_question_bank":
            try:
                detail = self.source_selection.question_bank.get_question(item.question_id)
            except KeyError as exc:
                raise LessonDraftingConflict(
                    f"公共题 {item.question_id} 已不存在，请重新确认来源。"
                ) from exc
            if detail.revision_count != item.source_revision:
                raise LessonDraftingConflict(
                    f"公共题 {item.question_id} 已修订，请重新确认来源。"
                )
            answer_value = str(detail.answer_value or "").strip()
            solution = (detail.raw.get("solutions") or [{}])[0]
            solution_steps = [
                str(step).strip()
                for step in (solution.get("steps_latex") or solution.get("steps") or [])
                if str(step).strip()
            ]
            final_answer = str(solution.get("final_answer") or "").strip()
        else:
            try:
                question = self.source_selection.personal_question_library.get_question(
                    item.question_id,
                    owner_id=owner_id,
                )
            except KeyError as exc:
                raise LessonDraftingError("所选私题不存在或不属于当前教师。") from exc
            if question.selected_revision != item.source_revision:
                raise LessonDraftingConflict(
                    f"私题 {item.question_id} 已修订，请重新确认来源。"
                )
            answer_value = str(question.question.answer_value or "").strip()
            solution_steps = [
                step.strip() for step in question.question.solution_steps if step.strip()
            ]
            final_answer = str(question.question.final_answer or "").strip()

        if not answer_value or not solution_steps or not final_answer:
            raise LessonDraftingError(
                f"题目 {item.question_id} 缺少完整答案或解析，不能生成完整教案。"
            )
        if item.question_type in {"single_choice", "multiple_choice"} and len(item.options) < 2:
            raise LessonDraftingError(
                f"选择题 {item.question_id} 的选项不完整，不能生成完整教案。"
            )
        return LessonDraftQuestionUse(
            question_id=item.question_id,
            source_kind=item.source_kind,
            source_revision=item.source_revision,
            rights_basis=item.rights_basis,
            verification_status=item.verification_status,
            review_status=item.review_status,
            owner_scope=item.owner_scope,
            phase_id=phase_id,
            usage="作为课堂例题或分层练习，先独立作答，再依据完整解析进行方法比较与纠错。",
            stem_plain=item.stem_plain,
            options=item.options,
            answer_value=answer_value,
            solution_steps=solution_steps,
            final_answer=final_answer,
        )

    @staticmethod
    def _practice_phase_index(phases) -> int:
        for index, phase in enumerate(phases):
            if any(marker in phase.title for marker in ("练习", "例题", "研讨", "讲评", "巩固")):
                return index
        return min(len(phases) - 1, max(1, len(phases) // 2))

    @staticmethod
    def _teacher_activity(
        title: str,
        purpose: str,
        focus: str,
        question_ids: list[str],
        resource_ids: list[str],
    ) -> str:
        parts = [f"围绕“{title}”组织问题链，落实“{purpose}”", f"教学侧重：{focus}"]
        if resource_ids:
            parts.append(f"仅参考已明确选择的私人资料：{'、'.join(resource_ids)}")
        if question_ids:
            parts.append(f"依次组织已确认题目：{'、'.join(question_ids)}，完整呈现题干后再讨论方法")
        return "；".join(parts) + "。"

    @staticmethod
    def _student_activity(title: str, purpose: str) -> str:
        return (
            f"学生在“{title}”阶段先独立思考，再用口头或书面方式说明依据；"
            f"通过同伴互评与订正完成“{purpose}”。"
        )

    @staticmethod
    def _phase_assessment(title: str, objective_ids: list[str]) -> str:
        return (
            f"在“{title}”结束前收集与{'、'.join(objective_ids)}对应的作答、解释或订正证据，"
            "由教师依据成功标准判断是否进入下一阶段。"
        )

    @staticmethod
    def _homework(focus: str, questions: list[LessonDraftQuestionUse]) -> list[str]:
        items = [
            f"基础巩固：整理本课知识结构，并围绕“{focus}”写出一个完整例子。",
            "过程订正：选择课堂中一处易错步骤，写出错误原因、正确依据和检查方法。",
        ]
        if questions:
            items.append(
                f"变式迁移：从题目 {questions[0].question_id} 出发改变一个条件，说明答案或方法如何变化。"
            )
        else:
            items.append("变式迁移：自拟一个符合本课目标的情境，并写出解题依据。")
        return items

    @staticmethod
    def _board_plan(blueprint, questions: list[LessonDraftQuestionUse]) -> list[str]:
        return [
            f"课题：{blueprint.title}",
            f"重点：{'；'.join(blueprint.key_points)}",
            f"难点与检查：{'；'.join(blueprint.difficulties)}",
            "课堂结构：问题情境 → 概念/方法建构 → 例题与练习 → 评价与总结",
            f"受控题目：{'、'.join(item.question_id for item in questions) if questions else '本课未计划题目'}",
        ]

    @staticmethod
    def _teacher_notes(source_draft: LessonSourceDraft) -> list[str]:
        blueprint = source_draft.blueprint
        notes = [
            f"学情：{blueprint.student_profile}",
            "本教案中的组织性文字为 AI 辅助草稿，状态为 draft_requires_teacher_review。",
            "教材、题目和私人资料的可信状态互不升级；教师保存也不能替代数学验证。",
        ]
        if source_draft.private_resources:
            notes.append(
                "私人资料仅限当前教师使用，不公开、不共享，也不改变原资料权利状态。"
            )
        return notes

    @staticmethod
    def _source_manifest(source_draft: LessonSourceDraft) -> list[LessonDraftSourceRef]:
        manifest: list[LessonDraftSourceRef] = []
        if source_draft.curriculum is not None:
            curriculum = source_draft.curriculum
            manifest.append(
                LessonDraftSourceRef(
                    source_kind="curriculum",
                    source_id=curriculum.node_id,
                    source_revision=f"{curriculum.catalog_status}:{curriculum.reviewed_by}",
                    rights_basis="sealed_pep_a_curriculum_baseline",
                    verification_status=curriculum.catalog_status,
                    owner_scope="sealed_catalog",
                )
            )
        manifest.extend(
            LessonDraftSourceRef(
                source_kind=(
                    "public_question"
                    if item.source_kind == "public_question_bank"
                    else "private_question"
                ),
                source_id=item.question_id,
                source_revision=str(item.source_revision),
                rights_basis=item.rights_basis,
                verification_status=f"{item.verification_status}:{item.review_status}",
                owner_scope=item.owner_scope,
            )
            for item in source_draft.questions
        )
        manifest.extend(
            LessonDraftSourceRef(
                source_kind="private_resource",
                source_id=item.library_item_id,
                source_revision=str(item.source_version),
                rights_basis=item.rights_basis,
                verification_status=item.text_review_status,
                owner_scope="current_owner_only",
            )
            for item in source_draft.private_resources
        )
        return manifest
