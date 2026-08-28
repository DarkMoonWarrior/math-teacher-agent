from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from app.modules.exam_papers.composer import ExamPaperComposer
from app.modules.exam_papers.planning import PaperBlueprintPlanning
from app.modules.exam_papers.schemas import (
    ConfirmedPaperBlueprint,
    PaperBlueprintSelectionCommand,
    PaperBlueprintSelectionDraft,
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


class PaperBlueprintSelection:
    """Confirms a blueprint and returns a gated, read-only question proposal.

    Identity, rights and trust facts are resolved behind this interface. The
    module never persists a paper, copies a private question, or authors supply.
    """

    def __init__(self, *, question_bank, personal_question_library) -> None:
        self.question_bank = question_bank
        self.personal_question_library = personal_question_library
        self.composer = ExamPaperComposer(question_bank)

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
            if candidate is None or not self._matches_scope(candidate, blueprint):
                unselected_private.append(question_id)
                continue
            private_candidates.append(candidate)

        public_candidates = sorted(
            [
            item
            for item in self._public_candidates(owner_id=owner_id)
            if self._matches_scope(item, blueprint)
            ],
            key=lambda item: item.summary.question_id,
        )
        private_candidates, private_exclusions = self._deduplicate(private_candidates)
        public_candidates, public_exclusions = self._deduplicate(
            public_candidates,
            against=private_candidates,
        )
        similarity_exclusions = [*private_exclusions, *public_exclusions]
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
        warnings: list[str] = []
        if gaps:
            warnings.append("存在真实供给缺口；系统没有自动命题、自动保存或用未通过门禁的题目凑数。")
        if similarity_exclusions:
            warnings.append(
                f"重复/高相似门禁已排除 {len(similarity_exclusions)} 道候选题。"
            )
        if unselected_private:
            warnings.append(
                f"有 {len(unselected_private)} 道明确选择的私题因门禁、范围、重复或蓝图题型不匹配而未采用。"
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
            unselected_private_question_ids=unselected_private,
            warnings=warnings,
        )

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
        if (
            question.lifecycle_state != "active"
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
        return _Candidate(
            summary=QuestionSummary(
                question_id=question.question_id,
                status="saved_private_complete",
                review_status="owner_saved_complete",
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
            selection_reason=reason,
        )
