from __future__ import annotations

from collections import Counter, defaultdict

from app.modules.exam_papers.composer import ExamPaperComposer
from app.modules.exam_papers.schemas import (
    ConfirmedPaperBlueprint,
    PaperBlueprintCoverageAudit,
    PaperBlueprintSection,
    PaperDifficultyBand,
    PaperKnowledgeCoverage,
    PaperSectionCoverage,
    PaperSelectionItem,
)


class PaperBlueprintCoverage:
    """Compares a gated selection draft with its confirmed blueprint.

    The audit is deterministic and read-only. It does not select, author, save,
    or mutate questions, and it never accepts trust conclusions from a client.
    """

    GENERIC_SCOPE = {"高中", "高中数学", "高中通用"}

    def __init__(self, composer: ExamPaperComposer) -> None:
        self.composer = composer

    def audit(
        self,
        *,
        blueprint: ConfirmedPaperBlueprint,
        items: list[PaperSelectionItem],
    ) -> PaperBlueprintCoverageAudit:
        section_items: dict[str, list[PaperSelectionItem]] = defaultdict(list)
        for item in items:
            section_items[item.section_id].append(item)

        sections = [
            self._section_coverage(section, section_items.get(section.section_id, []))
            for section in blueprint.sections
        ]
        knowledge_points = [
            self._knowledge_coverage(knowledge_point, items)
            for knowledge_point in blueprint.knowledge_points
        ]

        target_slots = self.composer.difficulty_slots(
            sum(section.question_count for section in blueprint.sections),
            blueprint.difficulty_profile,
        )
        target_counts = Counter(target_slots)
        actual_counts = Counter(item.difficulty for item in items)
        actual_scores: dict[int, float] = defaultdict(float)
        for item in items:
            actual_scores[item.difficulty] += item.score

        target_average = sum(
            difficulty * weight
            for difficulty, weight in self.composer.PROFILE_WEIGHTS[
                blueprint.difficulty_profile
            ].items()
        )
        actual_average = (
            sum(item.difficulty for item in items) / len(items) if items else None
        )
        average_gap = (
            abs(actual_average - target_average) if actual_average is not None else None
        )
        coverage_complete = all(item.status == "met" for item in sections) and all(
            item.status == "covered" for item in knowledge_points
        )
        target_question_count = len(target_slots)
        if len(items) < target_question_count:
            difficulty_status = "insufficient_supply"
        elif average_gap is not None and average_gap < 0.75:
            difficulty_status = "matched"
        else:
            difficulty_status = "deviated"

        return PaperBlueprintCoverageAudit(
            status=(
                "matched"
                if coverage_complete and difficulty_status == "matched"
                else "needs_adjustment"
            ),
            coverage_complete=coverage_complete,
            difficulty_status=difficulty_status,
            target_average_difficulty=round(target_average, 2),
            actual_average_difficulty=(
                round(actual_average, 2) if actual_average is not None else None
            ),
            average_difficulty_gap=(
                round(average_gap, 2) if average_gap is not None else None
            ),
            sections=sections,
            knowledge_points=knowledge_points,
            difficulty_bands=[
                PaperDifficultyBand(
                    difficulty=difficulty,
                    target_question_count=target_counts[difficulty],
                    actual_question_count=actual_counts[difficulty],
                    actual_score=round(actual_scores[difficulty], 2),
                )
                for difficulty in range(1, 6)
            ],
        )

    @staticmethod
    def _section_coverage(
        section: PaperBlueprintSection,
        items: list[PaperSelectionItem],
    ) -> PaperSectionCoverage:
        actual_score = round(sum(item.score for item in items), 2)
        met = len(items) == section.question_count and abs(
            actual_score - section.target_score
        ) <= 1e-6
        return PaperSectionCoverage(
            section_id=section.section_id,
            section_title=section.title,
            target_question_count=section.question_count,
            actual_question_count=len(items),
            target_score=section.target_score,
            actual_score=actual_score,
            status="met" if met else "short",
        )

    @classmethod
    def _knowledge_coverage(
        cls,
        knowledge_point: str,
        items: list[PaperSelectionItem],
    ) -> PaperKnowledgeCoverage:
        if knowledge_point in cls.GENERIC_SCOPE:
            matched = items
        else:
            needle = knowledge_point.casefold()
            matched = [
                item
                for item in items
                if needle
                in " ".join(
                    [
                        item.stem_plain,
                        item.chapter or "",
                        *item.knowledge_points,
                    ]
                ).casefold()
            ]
        return PaperKnowledgeCoverage(
            knowledge_point=knowledge_point,
            actual_question_count=len(matched),
            actual_score=round(sum(item.score for item in matched), 2),
            status="covered" if matched else "missing",
        )
