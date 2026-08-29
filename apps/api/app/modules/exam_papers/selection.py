from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from app.modules.exam_papers.composer import ExamPaperComposer
from app.modules.exam_papers.coverage import PaperBlueprintCoverage
from app.modules.exam_papers.planning import PaperBlueprintPlanning
from app.modules.exam_papers.schemas import (
    ConfirmedPaperBlueprint,
    PaperBlueprintSelectionCommand,
    PaperBlueprintSelectionDraft,
    PaperPublicQuestionCandidate,
    PaperPublicQuestionCandidateList,
    PaperSelectionGap,
    PaperSelectionItem,
    PaperSelectionOption,
    PaperSimilarityExclusion,
)
from app.modules.personal_question_library.schemas import PersonalQuestionView
from app.modules.question_bank.schemas import QuestionSummary
from app.modules.question_similarity import compare_question_similarity


class PaperBlueprintSelectionError(ValueError):
    pass


@dataclass(frozen=True)
class _Candidate:
    summary: QuestionSummary
    options: tuple[PaperSelectionOption, ...]
    source_kind: str
    revision_count: int
    solution_status: str = "ready"
    solution_issue: str | None = None


class PaperBlueprintSelection:
    """Confirms a blueprint and returns a gated, read-only question proposal.

    Identity, rights and trust facts are resolved behind this interface. The
    module never persists a paper, copies a private question, or authors supply.
    """

    def __init__(self, *, question_bank, personal_question_library) -> None:
        self.question_bank = question_bank
        self.personal_question_library = personal_question_library
        self.composer = ExamPaperComposer(question_bank)
        self.coverage = PaperBlueprintCoverage(self.composer)

    def select(
        self,
        command: PaperBlueprintSelectionCommand,
        *,
        owner_id: str,
    ) -> PaperBlueprintSelectionDraft:
        blueprint = command.blueprint
        self._ensure_high_school_scope(blueprint)

        private_candidates: list[_Candidate] = []
        unselected_private: list[str] = []
        for question_id in command.selected_private_question_ids:
            try:
                question = self.personal_question_library.get_question(
                    question_id,
                    owner_id=owner_id,
                )
            except KeyError as exc:
                raise PaperBlueprintSelectionError(
                    "所选私题不存在或不属于当前教师。"
                ) from exc
            candidate = self._private_candidate(question)
            if candidate is None:
                unselected_private.append(question_id)
                continue
            private_candidates.append(candidate)

        all_public_candidates = self._public_candidates(owner_id=owner_id)
        public_by_id = {
            item.summary.question_id: item for item in all_public_candidates
        }
        selected_public_candidates: list[_Candidate] = []
        for question_id in command.selected_public_question_ids:
            candidate = public_by_id.get(question_id)
            if candidate is None:
                raise PaperBlueprintSelectionError(
                    "所选公共题不存在或未通过公共题库门禁。"
                )
            selected_public_candidates.append(candidate)

        selected_public_ids = set(command.selected_public_question_ids)
        public_candidates = sorted(
            (
                item
                for item in all_public_candidates
                if item.summary.question_id not in selected_public_ids
                and self._matches_scope(item, blueprint)
            ),
            key=lambda item: item.summary.question_id,
        )
        private_candidates, private_exclusions = self._deduplicate(private_candidates)
        selected_public_candidates, selected_public_exclusions = self._deduplicate(
            selected_public_candidates,
            against=private_candidates,
        )
        public_candidates, public_exclusions = self._deduplicate(
            public_candidates,
            against=[*private_candidates, *selected_public_candidates],
        )
        similarity_exclusions = [
            *private_exclusions,
            *selected_public_exclusions,
            *public_exclusions,
        ]
        unselected_public = [
            item.question_id
            for item in selected_public_exclusions
            if item.question_id in selected_public_ids
        ]
        unselected_private.extend(
            item.question_id
            for item in similarity_exclusions
            if item.question_id in command.selected_private_question_ids
        )

        items: list[PaperSelectionItem] = []
        gaps: list[PaperSelectionGap] = []
        used_question_ids: set[str] = set()
        chapter_usage: Counter[str] = Counter()
        position = 1

        for section in blueprint.sections:
            if section.question_count == 0:
                continue
            score_plan = self.composer.allocate_scores(
                section.target_score,
                [
                    self.composer.TYPE_SCORE_WEIGHTS.get(
                        self.composer._canonical_type(section.question_type),
                        10,
                    )
                ]
                * section.question_count,
            )
            matching_private = [
                item
                for item in private_candidates
                if item.summary.question_id not in used_question_ids
                and self.composer._canonical_type(item.summary.question_type)
                == self.composer._canonical_type(section.question_type)
            ]
            section_candidates = matching_private[: section.question_count]
            used_question_ids.update(item.summary.question_id for item in section_candidates)

            remaining_count = section.question_count - len(section_candidates)
            matching_selected_public = [
                item
                for item in selected_public_candidates
                if item.summary.question_id not in used_question_ids
                and self.composer._canonical_type(item.summary.question_type)
                == self.composer._canonical_type(section.question_type)
            ]
            section_candidates.extend(matching_selected_public[:remaining_count])
            used_question_ids.update(item.summary.question_id for item in section_candidates)

            remaining_count = section.question_count - len(section_candidates)
            matching_public = [
                item
                for item in public_candidates
                if item.summary.question_id not in used_question_ids
                and self.composer._canonical_type(item.summary.question_type)
                == self.composer._canonical_type(section.question_type)
            ]
            public_count = min(remaining_count, len(matching_public))
            if public_count:
                selected_public = self.composer.select_questions(
                    candidates=[item.summary for item in matching_public],
                    question_type=section.question_type,
                    count=public_count,
                    difficulty_profile=blueprint.difficulty_profile,
                    seed=f"{blueprint.title}:{section.section_id}",
                    chapter_usage=chapter_usage,
                )
                by_id = {item.summary.question_id: item for item in matching_public}
                section_candidates.extend(by_id[question.question_id] for question, _ in selected_public)
                public_targets = {
                    question.question_id: target for question, target in selected_public
                }
            else:
                public_targets = {}
            used_question_ids.update(item.summary.question_id for item in section_candidates)

            for section_position, (candidate, score) in enumerate(
                zip(section_candidates, score_plan, strict=False),
                start=1,
            ):
                summary = candidate.summary
                if candidate.source_kind == "personal_question_library":
                    reason = "教师明确选择的当前 owner 私题 · 未复制、未改变可见性"
                elif summary.question_id in selected_public_ids:
                    reason = "教师从受控公共题库中明确选择 · 来源与可信状态已由服务端复核"
                else:
                    target = public_targets.get(summary.question_id, summary.difficulty)
                    reason = (
                        f"{self.composer.PROFILE_LABELS[blueprint.difficulty_profile]}难度 · "
                        f"目标 {target} 级，实际 {summary.difficulty} 级 · "
                        f"{summary.chapter or '未分类'}"
                    )
                items.append(
                    self._selection_item(
                        candidate,
                        section_id=section.section_id,
                        section_title=section.title,
                        position=position,
                        score=score,
                        reason=reason,
                    )
                )
                position += 1

            if len(section_candidates) < section.question_count:
                missing_count = section.question_count - len(section_candidates)
                gaps.append(
                    PaperSelectionGap(
                        section_id=section.section_id,
                        section_title=section.title,
                        question_type=section.question_type,
                        required_count=section.question_count,
                        selected_count=len(section_candidates),
                        missing_count=missing_count,
                        missing_score=sum(score_plan[len(section_candidates) :]),
                        reason=(
                            "通过数学验证、教师审核、权利、owner 与重复/相似门禁后，"
                            "当前受控题库供给不足。"
                        ),
                        suggestions=[
                            "调整该分区题量或题型后重新确认蓝图",
                            "补充已审核且验证通过的公共题库供给",
                            "从你的个人题库中明确选择一道题后重试",
                        ],
                    )
                )

        unused_private = [
            item.summary.question_id
            for item in private_candidates
            if item.summary.question_id not in used_question_ids
        ]
        unselected_private = list(dict.fromkeys([*unselected_private, *unused_private]))
        unused_public = [
            item.summary.question_id
            for item in selected_public_candidates
            if item.summary.question_id not in used_question_ids
        ]
        unselected_public = list(dict.fromkeys([*unselected_public, *unused_public]))
        warnings: list[str] = []
        if gaps:
            warnings.append("存在真实供给缺口；系统没有自动命题、自动保存或用未通过门禁的题目凑数。")
        if similarity_exclusions:
            warnings.append(
                f"重复/高相似门禁已排除 {len(similarity_exclusions)} 道候选题。"
            )
        if unselected_private:
            warnings.append(
                f"有 {len(unselected_private)} 道明确选择的私题因硬门禁、重复或蓝图题型/容量不匹配而未采用。"
            )
        if unselected_public:
            warnings.append(
                f"有 {len(unselected_public)} 道明确选择的公共题因重复或蓝图题型/容量不匹配而未采用。"
            )

        return PaperBlueprintSelectionDraft(
            selection_complete=not gaps,
            blueprint=blueprint,
            target_question_count=sum(item.question_count for item in blueprint.sections),
            actual_question_count=len(items),
            target_score=blueprint.target_score,
            actual_score=sum(item.score for item in items),
            items=items,
            gaps=gaps,
            similarity_exclusions=similarity_exclusions,
            coverage_audit=self.coverage.audit(blueprint=blueprint, items=items),
            unselected_public_question_ids=unselected_public,
            unselected_private_question_ids=unselected_private,
            warnings=warnings,
        )

    def list_public_candidates(
        self,
        *,
        owner_id: str,
        query: str | None = None,
        question_type: str | None = None,
        limit: int = 50,
    ) -> PaperPublicQuestionCandidateList:
        """Return only public questions that already passed every M9 hard gate."""

        normalized_query = (query or "").strip().lower()
        candidates = sorted(
            self._public_candidates(owner_id=owner_id),
            key=lambda item: item.summary.question_id,
        )
        if question_type:
            canonical_type = self.composer._canonical_type(question_type)
            candidates = [
                item
                for item in candidates
                if self.composer._canonical_type(item.summary.question_type)
                == canonical_type
            ]
        if normalized_query:
            candidates = [
                item
                for item in candidates
                if normalized_query
                in " ".join(
                    [
                        item.summary.stem_plain,
                        item.summary.chapter or "",
                        item.summary.section or "",
                        *item.summary.knowledge_point_ids,
                    ]
                ).lower()
            ]
        total = len(candidates)
        return PaperPublicQuestionCandidateList(
            items=[
                PaperPublicQuestionCandidate(
                    question_id=item.summary.question_id,
                    question_type=item.summary.question_type,
                    stem_plain=item.summary.stem_plain,
                    options=list(item.options),
                    difficulty=item.summary.difficulty,
                    chapter=item.summary.chapter,
                    knowledge_points=item.summary.knowledge_point_ids,
                    source_document=item.summary.source_document,
                )
                for item in candidates[:limit]
            ],
            total=total,
        )

    def resolve_explicit_candidates(
        self,
        *,
        owner_id: str,
        public_question_ids: list[str],
        private_question_ids: list[str],
    ) -> list[PaperSelectionItem]:
        """Re-resolve explicitly added history questions through current hard gates.

        Unlike blueprint selection this does not filter by planned knowledge or
        difficulty: the teacher is editing an existing paper and remains free to
        choose the content. Trust, rights, owner and high-school gates still apply.
        """

        public_by_id = {
            candidate.summary.question_id: candidate
            for candidate in self._public_candidates(owner_id=owner_id)
        }
        candidates: list[_Candidate] = []
        for question_id in public_question_ids:
            candidate = public_by_id.get(question_id)
            if candidate is None:
                raise PaperBlueprintSelectionError(
                    "新增公共题不存在或未通过公共题库门禁。"
                )
            candidates.append(candidate)
        for question_id in private_question_ids:
            try:
                question = self.personal_question_library.get_question(
                    question_id,
                    owner_id=owner_id,
                )
            except KeyError as exc:
                raise PaperBlueprintSelectionError(
                    "新增私题不存在或不属于当前教师。"
                ) from exc
            candidate = self._private_candidate(question)
            if candidate is None:
                raise PaperBlueprintSelectionError(
                    "新增私题尚未通过完整性、数学验证或高中范围门禁。"
                )
            candidates.append(candidate)

        accepted, exclusions = self._deduplicate(candidates)
        if exclusions or len(accepted) != len(candidates):
            raise PaperBlueprintSelectionError("新增题目存在重复或高度相似内容，请重新选择。")
        return [
            self._selection_item(
                candidate,
                section_id=f"history-{index}",
                section_title="新增题目",
                position=index,
                score=1,
                reason="教师在历史试卷编辑器中明确新增，服务端已重新执行门禁",
            )
            for index, candidate in enumerate(accepted, start=1)
        ]

    def _public_candidates(self, *, owner_id: str) -> list[_Candidate]:
        candidates: list[_Candidate] = []
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
                if (
                    summary.visibility == "public"
                    and summary.status != "rejected"
                    and summary.review_status == "approved"
                    and summary.verification_status == "passed"
                    and summary.library_state == "active"
                    and not summary.publication_blockers
                    and not self._contains_university_marker(summary.stem_plain)
                ):
                    candidates.append(self._public_candidate(summary))
            if page * result.page_size >= result.total:
                break
            page += 1
        return candidates

    def _public_candidate(self, summary: QuestionSummary) -> _Candidate:
        options: tuple[PaperSelectionOption, ...] = ()
        revision_count = 0
        try:
            detail = self.question_bank.get_question(summary.question_id)
        except (AttributeError, KeyError):
            detail = None
        if detail is not None:
            revision_count = detail.revision_count
            options = tuple(
                PaperSelectionOption(
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
            )
        return _Candidate(
            summary=summary,
            options=options,
            source_kind="public_question_bank",
            revision_count=revision_count,
        )

    def _private_candidate(self, question: PersonalQuestionView) -> _Candidate | None:
        draft = question.question
        solution_issue = getattr(draft, "solution_issue", None)
        statement_only = (
            draft.solution_status == "needs_teacher_verification"
            and bool(solution_issue)
            and "解析未生成" in solution_issue
        )
        if (
            question.lifecycle_state != "active"
            or (draft.solution_status != "ready" and not statement_only)
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
        return _Candidate(
            summary=QuestionSummary(
                question_id=question.question_id,
                status=("saved_private_statement_only" if statement_only else "saved_private_complete"),
                review_status=("owner_saved_statement_only" if statement_only else "owner_saved_complete"),
                visibility="owner_only",
                question_type=draft.question_type,
                stem_plain=draft.stem_plain,
                answer_value=draft.answer_value,
                volume=curriculum.volume if curriculum else None,
                chapter=curriculum.chapter if curriculum else None,
                section=curriculum.section if curriculum else None,
                knowledge_point_ids=draft.knowledge_points,
                difficulty=draft.estimated_difficulty,
                verification_status=verification_status,
                source_document=f"个人题库 · {question.name}",
                source_page_start=None,
                source_page_end=None,
                license_status="owner_private_use_only",
                publication_blockers=["owner_only_no_publication"],
            ),
            options=tuple(
                PaperSelectionOption(key=item.key, text=item.text)
                for item in draft.options
            ),
            source_kind="personal_question_library",
            revision_count=question.selected_revision,
            solution_status=draft.solution_status,
            solution_issue=solution_issue,
        )

    def _deduplicate(
        self,
        candidates: list[_Candidate],
        *,
        against: list[_Candidate] | None = None,
    ) -> tuple[list[_Candidate], list[PaperSimilarityExclusion]]:
        kept = list(against or [])
        accepted: list[_Candidate] = []
        exclusions: list[PaperSimilarityExclusion] = []
        for candidate in candidates:
            match = next(
                (
                    (existing, evidence)
                    for existing in kept
                    if self.composer._canonical_type(existing.summary.question_type)
                    == self.composer._canonical_type(candidate.summary.question_type)
                    and (
                        evidence := compare_question_similarity(
                            left_stem=existing.summary.stem_plain,
                            right_stem=candidate.summary.stem_plain,
                            left_options=[item.text for item in existing.options],
                            right_options=[item.text for item in candidate.options],
                            left_knowledge_points=existing.summary.knowledge_point_ids,
                            right_knowledge_points=candidate.summary.knowledge_point_ids,
                            left_chapter=existing.summary.chapter,
                            right_chapter=candidate.summary.chapter,
                        )
                    )
                    is not None
                ),
                None,
            )
            if match:
                existing, evidence = match
                relation, confidence, signals = evidence
                exclusions.append(
                    PaperSimilarityExclusion(
                        question_id=candidate.summary.question_id,
                        matched_question_id=existing.summary.question_id,
                        relation=relation,
                        confidence=confidence,
                        reason="；".join(signals),
                    )
                )
                continue
            accepted.append(candidate)
            kept.append(candidate)
        return accepted, exclusions

    @staticmethod
    def _matches_scope(
        candidate: _Candidate,
        blueprint: ConfirmedPaperBlueprint,
    ) -> bool:
        if any(item in {"高中", "高中数学", "高中通用"} for item in blueprint.knowledge_points):
            return True
        searchable = " ".join(
            [
                candidate.summary.stem_plain,
                candidate.summary.chapter or "",
                candidate.summary.section or "",
                *candidate.summary.knowledge_point_ids,
            ]
        ).lower()
        return any(item.lower() in searchable for item in blueprint.knowledge_points)

    @classmethod
    def _ensure_high_school_scope(cls, blueprint: ConfirmedPaperBlueprint) -> None:
        corpus = " ".join(
            [
                blueprint.title,
                blueprint.grade_scope,
                blueprint.teaching_usage,
                *blueprint.knowledge_points,
            ]
        )
        if cls._contains_university_marker(corpus):
            raise PaperBlueprintSelectionError("M9 只支持中国普通高中数学组卷。")

    @staticmethod
    def _contains_university_marker(value: str) -> bool:
        return any(
            marker in value
            for marker in (
                *PaperBlueprintPlanning.UNIVERSITY_MARKERS,
                "大学",
                "本科",
            )
        )

    @staticmethod
    def _selection_item(
        candidate: _Candidate,
        *,
        section_id: str,
        section_title: str,
        position: int,
        score: float,
        reason: str,
    ) -> PaperSelectionItem:
        summary = candidate.summary
        is_private = candidate.source_kind == "personal_question_library"
        return PaperSelectionItem(
            section_id=section_id,
            section_title=section_title,
            position=position,
            question_id=summary.question_id,
            source_kind=candidate.source_kind,
            question_type=summary.question_type,
            stem_plain=summary.stem_plain,
            options=list(candidate.options),
            score=score,
            difficulty=summary.difficulty,
            chapter=summary.chapter,
            knowledge_points=summary.knowledge_point_ids,
            source_document=summary.source_document,
            source_page_start=summary.source_page_start,
            source_page_end=summary.source_page_end,
            license_status=summary.license_status,
            revision_count=candidate.revision_count,
            verification_status=summary.verification_status,
            review_status=summary.review_status,
            visibility=summary.visibility,
            owner_scope="current_owner_only" if is_private else "public_catalog",
            solution_status=(candidate.solution_status if is_private else "ready"),
            solution_issue=(candidate.solution_issue if is_private else None),
            selection_reason=reason,
        )
