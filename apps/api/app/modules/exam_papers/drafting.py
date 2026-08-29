from __future__ import annotations

from collections import defaultdict
import hashlib
import json

from app.modules.exam_papers.coverage import PaperBlueprintCoverage
from app.modules.exam_papers.schemas import (
    PaperBidirectionalSpecification,
    PaperDraftChange,
    PaperDraftItemEdit,
    PaperEditableDraft,
    PaperEditableDraftCommand,
    PaperSelectionItem,
    PaperSpecificationForwardRow,
    PaperSpecificationReverseRow,
)
from app.modules.exam_papers.selection import PaperBlueprintSelection


class PaperEditableDraftingError(ValueError):
    pass


class PaperEditableDrafting:
    """Builds an unsaved editable paper and both specification directions.

    The interface deliberately accepts only the original controlled-selection
    request plus layout edits. Source, owner, rights, verification, review,
    persistence and export facts are rebuilt or derived server-side.
    """

    def __init__(
        self,
        *,
        selection: PaperBlueprintSelection,
        coverage: PaperBlueprintCoverage | None = None,
    ) -> None:
        self.selection = selection
        self.coverage = coverage or selection.coverage

    def build(self, command: PaperEditableDraftCommand, *, owner_id: str) -> PaperEditableDraft:
        selected = self.selection.select(command.selection_request, owner_id=owner_id)
        items = self._apply_edits(selected.items, command.edits, selected.blueprint.sections)
        coverage_audit = self.coverage.audit(blueprint=selected.blueprint, items=items)
        actual_score = round(sum(item.score for item in items), 2)
        score_status = (
            "matched"
            if abs(actual_score - selected.target_score) <= 1e-6
            else "mismatch"
        )
        section_structure_complete = all(
            section.status == "met" for section in coverage_audit.sections
        )
        return PaperEditableDraft(
            draft_fingerprint=self.fingerprint(selected.blueprint, items),
            selection_complete=selected.selection_complete,
            draft_consistent=(
                selected.selection_complete
                and score_status == "matched"
                and section_structure_complete
            ),
            score_status=score_status,
            blueprint=selected.blueprint,
            target_question_count=selected.target_question_count,
            actual_question_count=len(items),
            target_score=selected.target_score,
            actual_score=actual_score,
            items=items,
            gaps=selected.gaps,
            coverage_audit=coverage_audit,
            change_log=self._changes(selected.items, items),
            specification=self._specification(items),
            warnings=selected.warnings,
            trust_policy=selected.trust_policy,
        )

    @staticmethod
    def fingerprint(blueprint, items: list[PaperSelectionItem]) -> str:
        """Bind save intent to the exact server-rebuilt paper the teacher reviewed."""

        payload = {
            "blueprint": blueprint.model_dump(mode="json"),
            "items": [
                {
                    "question_id": item.question_id,
                    "source_kind": item.source_kind,
                    "revision_count": item.revision_count,
                    "position": item.position,
                    "section_id": item.section_id,
                    "score": item.score,
                    "stem_plain": item.stem_plain,
                    "options": [option.model_dump(mode="json") for option in item.options],
                }
                for item in items
            ],
        }
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _apply_edits(
        original: list[PaperSelectionItem],
        edits: list[PaperDraftItemEdit],
        sections,
    ) -> list[PaperSelectionItem]:
        if not edits:
            return [item.model_copy(deep=True) for item in original]

        original_by_id = {item.question_id: item for item in original}
        edit_ids = [item.question_id for item in edits]
        if len(edit_ids) != len(set(edit_ids)):
            raise PaperEditableDraftingError("同一道题只能在可编辑试卷中出现一次")
        if set(edit_ids) != set(original_by_id):
            raise PaperEditableDraftingError(
                "编辑清单必须完整对应服务器重新确认后的候选题，不能新增、遗漏或替换题目"
            )
        positions = [item.position for item in edits]
        if sorted(positions) != list(range(1, len(original) + 1)):
            raise PaperEditableDraftingError("题号必须从 1 开始连续且不能重复")

        section_by_id = {section.section_id: section for section in sections}
        edited_items: list[PaperSelectionItem] = []
        for edit in edits:
            source = original_by_id[edit.question_id]
            section = section_by_id.get(edit.section_id)
            if section is None:
                raise PaperEditableDraftingError(f"分区不存在：{edit.section_id}")
            if section.question_type != source.question_type:
                raise PaperEditableDraftingError(
                    f"题目 {source.question_id} 的题型与目标分区不一致"
                )
            edited_items.append(
                source.model_copy(
                    update={
                        "position": edit.position,
                        "section_id": section.section_id,
                        "section_title": section.title,
                        "score": edit.score,
                    },
                    deep=True,
                )
            )
        return sorted(edited_items, key=lambda item: item.position)

    @staticmethod
    def _changes(
        original: list[PaperSelectionItem], edited: list[PaperSelectionItem]
    ) -> list[PaperDraftChange]:
        original_by_id = {item.question_id: item for item in original}
        changes: list[PaperDraftChange] = []
        for item in edited:
            before = original_by_id[item.question_id]
            if before.position != item.position:
                changes.append(
                    PaperDraftChange(
                        question_id=item.question_id,
                        kind="position",
                        before=str(before.position),
                        after=str(item.position),
                        description=f"题目由第 {before.position} 题调整为第 {item.position} 题",
                    )
                )
            if before.section_id != item.section_id:
                changes.append(
                    PaperDraftChange(
                        question_id=item.question_id,
                        kind="section",
                        before=before.section_title,
                        after=item.section_title,
                        description=f"题目由“{before.section_title}”调整到“{item.section_title}”",
                    )
                )
            if abs(before.score - item.score) > 1e-6:
                changes.append(
                    PaperDraftChange(
                        question_id=item.question_id,
                        kind="score",
                        before=f"{before.score:g}",
                        after=f"{item.score:g}",
                        description=f"题目分值由 {before.score:g} 分调整为 {item.score:g} 分",
                    )
                )
        return changes

    @classmethod
    def _specification(
        cls, items: list[PaperSelectionItem]
    ) -> PaperBidirectionalSpecification:
        forward = [
            PaperSpecificationForwardRow(
                position=item.position,
                question_id=item.question_id,
                section_title=item.section_title,
                question_type=item.question_type,
                chapter=item.chapter or "未分类",
                knowledge_points=item.knowledge_points or ["未标注"],
                difficulty=item.difficulty,
                score=item.score,
                verification_status=item.verification_status,
                review_status=item.review_status,
                source_kind=item.source_kind,
            )
            for item in items
        ]
        grouped: dict[tuple[str, str], list[PaperSelectionItem]] = defaultdict(list)
        for item in items:
            grouped[("section", item.section_title)].append(item)
            grouped[("question_type", item.question_type)].append(item)
            grouped[("difficulty", f"难度 {item.difficulty}")].append(item)
            for point in item.knowledge_points or ["未标注"]:
                grouped[("knowledge_point", point)].append(item)

        dimension_order = {
            "section": 0,
            "question_type": 1,
            "knowledge_point": 2,
            "difficulty": 3,
        }
        reverse = []
        for (dimension, label), grouped_items in sorted(
            grouped.items(),
            key=lambda row: (
                dimension_order[row[0][0]],
                min(item.position for item in row[1]),
                row[0][1],
            ),
        ):
            ordered = sorted(grouped_items, key=lambda item: item.position)
            reverse.append(
                PaperSpecificationReverseRow(
                    dimension=dimension,
                    label=label,
                    positions=[item.position for item in ordered],
                    question_ids=[item.question_id for item in ordered],
                    question_count=len(ordered),
                    score=round(sum(item.score for item in ordered), 2),
                )
            )
        return PaperBidirectionalSpecification(
            question_to_dimensions=forward,
            dimension_to_questions=reverse,
        )
