from __future__ import annotations

import re

from app.modules.lesson_plans.schemas import (
    ConfirmedLessonBlueprint,
    LessonBlueprintCurriculumCandidate,
    LessonBlueprintDraft,
    LessonSelectedPrivateResource,
    LessonSourceDraft,
    LessonSourceGap,
    LessonSourceOptions,
    LessonSourceQuestionCandidate,
    LessonSourceQuestionOption,
    LessonSourceResourceCandidate,
    LessonSourceSelectionCommand,
)


class LessonSourceSelectionError(ValueError):
    pass


class LessonSourceSelection:
    """Resolve teacher-confirmed M10 sources without persistence or auto-authoring.

    Candidate listing exposes only selection metadata. Private source content is
    read only after its ID is explicitly selected by the current owner.
    """

    UNIVERSITY_MARKERS = (
        "高等数学",
        "线性代数",
        "数学分析",
        "实变函数",
        "复变函数",
        "抽象代数",
        "泛函分析",
        "随机过程",
        "马尔可夫链",
        "傅里叶分析",
        "偏微分方程",
        "大学",
        "本科",
    )

    def __init__(
        self,
        *,
        curriculum_catalog,
        question_bank,
        personal_question_library,
        private_library,
    ) -> None:
        self.curriculum_catalog = curriculum_catalog
        self.question_bank = question_bank
        self.personal_question_library = personal_question_library
        self.private_library = private_library

    def options(
        self,
        blueprint: LessonBlueprintDraft,
        *,
        owner_id: str,
    ) -> LessonSourceOptions:
        confirmed = self._confirm_blueprint(blueprint)
        return LessonSourceOptions(
            blueprint=confirmed,
            public_questions=self._public_questions(confirmed, owner_id=owner_id),
            private_questions=self._private_question_options(
                confirmed,
                owner_id=owner_id,
            ),
            private_resources=self._private_resource_options(owner_id=owner_id),
        )

    def select(
        self,
        command: LessonSourceSelectionCommand,
        *,
        owner_id: str,
    ) -> LessonSourceDraft:
        confirmed = self._confirm_blueprint(command.blueprint)
        curriculum = self._curriculum(confirmed)

        public_by_id = {
            item.question_id: item
            for item in self._public_questions(confirmed, owner_id=owner_id)
        }
        questions: list[LessonSourceQuestionCandidate] = []
        for question_id in command.selected_public_question_ids:
            question = public_by_id.get(question_id)
            if question is None:
                raise LessonSourceSelectionError(
                    "所选公共题不存在，或未通过公开、权利、审核、数学验证与高中范围门禁。"
                )
            questions.append(question)

        for question_id in command.selected_private_question_ids:
            try:
                private_question = self.personal_question_library.get_question(
                    question_id,
                    owner_id=owner_id,
                )
            except KeyError as exc:
                raise LessonSourceSelectionError(
                    "所选私题不存在或不属于当前教师。"
                ) from exc
            question = self._private_question_candidate(private_question)
            if question is None:
                raise LessonSourceSelectionError(
                    "所选私题未通过完整性、数学检查或高中范围门禁。"
                )
            questions.append(question)

        private_resources: list[LessonSelectedPrivateResource] = []
        for item_id in command.selected_private_resource_ids:
            try:
                item = self.private_library.get(item_id, owner_id=owner_id)
            except KeyError as exc:
                raise LessonSourceSelectionError(
                    "所选私人资料不存在或不属于当前教师。"
                ) from exc
            if not self._eligible_private_resource(item):
                raise LessonSourceSelectionError(
                    "所选私人资料尚未完成文本校对，不能进入教案来源草案。"
                )
            content = re.sub(r"\s+", " ", item.corrected_text).strip()
            private_resources.append(
                LessonSelectedPrivateResource(
                    **self._resource_candidate(item).model_dump(),
                    content_excerpt=self._bounded_excerpt(content),
                    rights_statement=item.rights_statement,
                )
            )

        gaps: list[LessonSourceGap] = []
        if curriculum is None:
            gaps.append(
                LessonSourceGap(
                    source_kind="curriculum",
                    required_count=1,
                    selected_count=0,
                    missing_count=1,
                    reason="尚未确认封存课程基线中的教材节点。",
                )
            )
        if len(questions) < confirmed.question_count:
            gaps.append(
                LessonSourceGap(
                    source_kind="question",
                    required_count=confirmed.question_count,
                    selected_count=len(questions),
                    missing_count=confirmed.question_count - len(questions),
                    reason=(
                        "教师明确选择且通过门禁的题目数量不足；系统没有临时编题，"
                        "也没有用未审核来源凑数。"
                    ),
                )
            )
        warnings = []
        if gaps:
            warnings.append("存在真实来源缺口；可继续调整蓝图或明确补选来源。")
        return LessonSourceDraft(
            selection_complete=not gaps,
            blueprint=confirmed,
            curriculum=curriculum,
            questions=questions,
            private_resources=private_resources,
            gaps=gaps,
            warnings=warnings,
        )

    def _confirm_blueprint(
        self,
        blueprint: LessonBlueprintDraft | ConfirmedLessonBlueprint,
    ) -> ConfirmedLessonBlueprint:
        if self._contains_university_marker(
            " ".join(
                [
                    blueprint.source_brief,
                    blueprint.title,
                    blueprint.grade_scope,
                    blueprint.curriculum_query,
                    blueprint.focus,
                    *blueprint.objectives,
                    *blueprint.key_points,
                    *blueprint.difficulties,
                ]
            )
        ):
            raise LessonSourceSelectionError("M10 只支持中国普通高中数学教案。")
        curriculum = self._curriculum(blueprint)
        if blueprint.selected_curriculum_node_id and curriculum is None:
            raise LessonSourceSelectionError("所选教材节点不在当前封存课程基线中。")
        payload = blueprint.model_dump(mode="python")
        payload.update(
            status="lesson_blueprint_confirmed",
            confirmed=True,
            saved=False,
            side_effects=[],
        )
        return ConfirmedLessonBlueprint.model_validate(payload)

    def _curriculum(
        self,
        blueprint: LessonBlueprintDraft | ConfirmedLessonBlueprint,
    ) -> LessonBlueprintCurriculumCandidate | None:
        node_id = blueprint.selected_curriculum_node_id
        candidate = next(
            (item for item in blueprint.curriculum_candidates if item.node_id == node_id),
            None,
        )
        if not node_id or candidate is None:
            return None
        try:
            node = self.curriculum_catalog.get_node(node_id)
        except KeyError:
            return None
        if node.status != candidate.catalog_status or node.reviewed_by != candidate.reviewed_by:
            raise LessonSourceSelectionError("教材节点可信状态与封存课程基线不一致。")
        return candidate

    def _public_questions(
        self,
        blueprint: ConfirmedLessonBlueprint,
        *,
        owner_id: str,
    ) -> list[LessonSourceQuestionCandidate]:
        candidates: list[LessonSourceQuestionCandidate] = []
        page = 1
        while True:
            result = self.question_bank.search(
                verification_status="passed",
                review_status="approved",
                library_state="active",
                usage_scope="teacher",
                usage_owner_id=owner_id,
                page=page,
                page_size=100,
            )
            for summary in result.items:
                if not self._eligible_public_question(summary):
                    continue
                candidate = self._public_question_candidate(summary)
                if self._matches_blueprint(candidate, blueprint):
                    candidates.append(candidate)
            if page * result.page_size >= result.total:
                break
            page += 1
        return sorted(candidates, key=lambda item: item.question_id)

    def _public_question_candidate(self, summary) -> LessonSourceQuestionCandidate:
        options: list[LessonSourceQuestionOption] = []
        revision = 0
        try:
            detail = self.question_bank.get_question(summary.question_id)
        except (AttributeError, KeyError):
            detail = None
        if detail is not None:
            revision = detail.revision_count
            options = [
                LessonSourceQuestionOption(
                    key=str(item.get("key") or ""),
                    text=str(
                        item.get("plain_text")
                        or item.get("text")
                        or item.get("latex")
                        or ""
                    ),
                )
                for item in (detail.raw.get("options") or [])
                if isinstance(item, dict) and item.get("key")
            ]
        return LessonSourceQuestionCandidate(
            question_id=summary.question_id,
            source_kind="public_question_bank",
            name=summary.source_document or f"公共题 {summary.question_id}",
            question_type=summary.question_type,
            stem_plain=summary.stem_plain,
            options=options,
            difficulty=summary.difficulty,
            chapter=summary.chapter,
            knowledge_points=summary.knowledge_point_ids,
            source_document=summary.source_document,
            source_revision=revision,
            rights_basis=summary.license_status,
            verification_status=summary.verification_status,
            review_status=summary.review_status,
            owner_scope="public_catalog",
        )

    def _private_question_options(
        self,
        blueprint: ConfirmedLessonBlueprint,
        *,
        owner_id: str,
    ) -> list[LessonSourceQuestionCandidate]:
        result = self.personal_question_library.list_questions(
            owner_id=owner_id,
            lifecycle_state="active",
            limit=200,
            offset=0,
        )
        candidates = [
            candidate
            for item in result.items
            if (candidate := self._private_question_candidate(item)) is not None
            and self._matches_blueprint(candidate, blueprint)
        ]
        return sorted(candidates, key=lambda item: item.question_id)

    def _private_question_candidate(self, item) -> LessonSourceQuestionCandidate | None:
        draft = item.question
        if (
            item.lifecycle_state != "active"
            or draft.solution_status != "ready"
            or draft.verification.status == "checks_failed"
            or any(check.status == "failed" for check in draft.verification.checks)
            or self._contains_university_marker(draft.stem_plain)
        ):
            return None
        curriculum = draft.curriculum
        verification_status = (
            "math_verifier_passed"
            if draft.verification.math_verifier_status == "passed"
            else "authoring_checks_passed_teacher_review_required"
        )
        return LessonSourceQuestionCandidate(
            question_id=item.question_id,
            source_kind="personal_question_library",
            name=item.name,
            question_type=draft.question_type,
            stem_plain=draft.stem_plain,
            options=[
                LessonSourceQuestionOption(key=option.key, text=option.text)
                for option in draft.options
            ],
            difficulty=draft.estimated_difficulty,
            chapter=curriculum.chapter if curriculum else None,
            knowledge_points=draft.knowledge_points,
            source_document=f"个人题库 · {item.name}",
            source_revision=item.selected_revision,
            rights_basis="owner_private_use_only",
            verification_status=verification_status,
            review_status="owner_saved_complete",
            owner_scope="current_owner_only",
        )

    def _private_resource_options(
        self,
        *,
        owner_id: str,
    ) -> list[LessonSourceResourceCandidate]:
        result = self.private_library.list(
            owner_id=owner_id,
            lifecycle_state="active",
            limit=100,
        )
        return [
            self._resource_candidate(item)
            for item in result.items
            if self._eligible_private_resource(item)
        ]

    @staticmethod
    def _resource_candidate(item) -> LessonSourceResourceCandidate:
        return LessonSourceResourceCandidate(
            library_item_id=item.library_item_id,
            title=item.title,
            file_kind=item.file_kind,
            source_version=item.version,
            rights_basis=item.rights_basis,
            corrected_char_count=item.corrected_char_count,
        )

    @staticmethod
    def _eligible_private_resource(item) -> bool:
        return (
            item.lifecycle_state == "active"
            and item.text_review_status == "confirmed"
            and item.corrected_char_count > 0
        )

    @staticmethod
    def _eligible_public_question(summary) -> bool:
        return (
            summary.visibility == "public"
            and summary.status != "rejected"
            and summary.review_status == "approved"
            and summary.verification_status == "passed"
            and summary.library_state == "active"
            and not summary.publication_blockers
            and bool(summary.license_status)
            and not LessonSourceSelection._contains_university_marker(summary.stem_plain)
        )

    @staticmethod
    def _matches_blueprint(
        candidate: LessonSourceQuestionCandidate,
        blueprint: ConfirmedLessonBlueprint,
    ) -> bool:
        selected = next(
            (
                item
                for item in blueprint.curriculum_candidates
                if item.node_id == blueprint.selected_curriculum_node_id
            ),
            None,
        )
        desired = {
            LessonSourceSelection._normalize(value)
            for value in (
                blueprint.curriculum_query,
                selected.name if selected else "",
                selected.chapter if selected else "",
                selected.section if selected else "",
            )
            if value
        }
        searchable = LessonSourceSelection._normalize(
            " ".join(
                [
                    candidate.stem_plain,
                    candidate.chapter or "",
                    *candidate.knowledge_points,
                ]
            )
        )
        return not desired or any(term and term in searchable for term in desired)

    @staticmethod
    def _contains_university_marker(value: str) -> bool:
        return any(marker in value for marker in LessonSourceSelection.UNIVERSITY_MARKERS)

    @staticmethod
    def _bounded_excerpt(value: str, limit: int = 480) -> str:
        if len(value) <= limit:
            return value
        return f"{value[: limit - 1].rstrip()}…"

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value.lower())
