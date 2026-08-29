from __future__ import annotations

from app.modules.exam_exports import ExamPaperDocumentRenderer, RenderedExamPaper
from app.modules.exam_papers.drafting import PaperEditableDrafting
from app.modules.exam_papers.schemas import (
    ExamPaperCreateCommand,
    ExamPaperEdition,
    ExamPaperExportFormat,
    ExamPaperItemInput,
    PaperSavedExportOption,
    PaperSavedVersion,
    PaperSelectionItem,
    PaperVersionSaveCommand,
)
from app.modules.exam_papers.studio import ExamPaperSaveContext, ExamPaperStudio
from app.modules.question_bank.schemas import QuestionDetail


class PaperVersioningError(ValueError):
    pass


class PaperVersioningConflict(PaperVersioningError):
    pass


class PaperSavedExportingError(ValueError):
    pass


class PaperResolvedQuestionSource:
    """Re-resolves public and current-owner private questions for one save attempt."""

    def __init__(self, *, selection, owner_id: str, items: list[PaperSelectionItem]) -> None:
        self.selection = selection
        self.owner_id = owner_id
        self.items = {item.question_id: item for item in items}
        self.details: dict[str, QuestionDetail] = {}

    def validate_all(self) -> None:
        for question_id in self.items:
            self.get_question(question_id)

    def get_question(self, question_id: str) -> QuestionDetail:
        if question_id in self.details:
            return self.details[question_id]
        item = self.items.get(question_id)
        if item is None:
            raise PaperVersioningError("保存清单包含未经受控选题确认的题目。")
        if item.source_kind == "public_question_bank":
            try:
                detail = self.selection.question_bank.get_question(question_id)
            except (AttributeError, KeyError) as exc:
                raise PaperVersioningError(f"公共题目已不可读取：{question_id}") from exc
            if detail.revision_count != item.revision_count:
                raise PaperVersioningConflict(f"题目 {question_id} 已修订，请重新核对试卷后再保存。")
        else:
            try:
                question = self.selection.personal_question_library.get_question(
                    question_id,
                    owner_id=self.owner_id,
                )
            except KeyError as exc:
                raise PaperVersioningError("所选私题不存在或不属于当前教师。") from exc
            if question.selected_revision != item.revision_count:
                raise PaperVersioningConflict(f"私题 {question_id} 已修订，请重新核对试卷后再保存。")
            detail = self._private_detail(question, item)
        self._ensure_complete(detail, item)
        self.details[question_id] = detail
        return detail

    def image_path(self, question_id: str, image_id: str):
        item = self.items.get(question_id)
        if item is None or item.source_kind != "public_question_bank":
            raise KeyError((question_id, image_id))
        return self.selection.question_bank.image_path(question_id, image_id)

    @staticmethod
    def _private_detail(question, item: PaperSelectionItem) -> QuestionDetail:
        draft = question.question
        curriculum = draft.curriculum
        raw = {
            "stem": {"plain_text": draft.stem_plain, "latex": draft.stem_latex},
            "options": [
                {"key": option.key, "plain_text": option.text, "latex": None}
                for option in draft.options
            ],
            "solutions": [
                {
                    "method": draft.solution_method,
                    "steps_latex": list(draft.solution_steps),
                    "final_answer": draft.final_answer,
                    "solution_status": draft.solution_status,
                    "solution_issue": draft.solution_issue,
                    "review_status": "ready_for_teacher_review",
                }
            ],
        }
        return QuestionDetail(
            question_id=question.question_id,
            status="saved_private_complete",
            review_status=item.review_status,
            visibility="owner_only",
            question_type=draft.question_type,
            stem_plain=draft.stem_plain,
            answer_value=draft.answer_value,
            volume=curriculum.volume if curriculum else None,
            chapter=curriculum.chapter if curriculum else None,
            section=curriculum.section if curriculum else None,
            knowledge_point_ids=list(draft.knowledge_points),
            difficulty=draft.estimated_difficulty,
            verification_status=item.verification_status,
            source_document=item.source_document,
            source_page_start=None,
            source_page_end=None,
            license_status="owner_private_use_only",
            publication_blockers=["owner_only_no_publication"],
            raw=raw,
            reviews=[],
            images=[],
            revision_count=question.selected_revision,
        )

    @staticmethod
    def _ensure_complete(detail: QuestionDetail, item: PaperSelectionItem) -> None:
        if detail.status == "rejected" or detail.review_status == "rejected":
            raise PaperVersioningError(f"题目 {detail.question_id} 已被拒绝，不能保存到试卷。")
        if detail.verification_status != item.verification_status:
            raise PaperVersioningConflict(f"题目 {detail.question_id} 的验证状态已变化，请重新核对。")
        solution = (detail.raw.get("solutions") or [{}])[0]
        steps = solution.get("steps_latex") or []
        final_answer = str(solution.get("final_answer") or "").strip()
        statement_only = (
            item.source_kind == "personal_question_library"
            and item.solution_status == "needs_teacher_verification"
            and bool(item.solution_issue)
            and "解析未生成" in item.solution_issue
        )
        if (
            not statement_only
            and (not str(detail.answer_value or "").strip() or not final_answer or not steps)
        ):
            raise PaperVersioningError(
                f"题目 {detail.question_id} 缺少完整答案或解析，不能建立可导出版本。"
            )
        options = detail.raw.get("options") or []
        if detail.question_type in {"single_choice", "multiple_choice"} and len(options) < 2:
            raise PaperVersioningError(f"选择题 {detail.question_id} 的选项不完整，不能保存。")


class PaperVersioning:
    """Creates an immutable version only from the exact reviewed gated draft."""

    def __init__(self, *, drafting: PaperEditableDrafting, studio: ExamPaperStudio) -> None:
        self.drafting = drafting
        self.studio = studio

    def save(self, command: PaperVersionSaveCommand, *, owner_id: str) -> PaperSavedVersion:
        draft = self.drafting.build(command.draft_command, owner_id=owner_id)
        if draft.draft_fingerprint != command.expected_draft_fingerprint:
            raise PaperVersioningConflict("试卷草稿已变化，请重新核对最新结果后再保存。")
        if not draft.items:
            raise PaperVersioningError("试卷至少需要一道通过门禁的完整题目才能建立版本。")

        source = PaperResolvedQuestionSource(
            selection=self.drafting.selection,
            owner_id=owner_id,
            items=draft.items,
        )
        source.validate_all()
        paper = self.studio.create(
            ExamPaperCreateCommand(
                title=draft.blueprint.title,
                duration_minutes=draft.blueprint.duration_minutes,
                instructions=command.instructions,
                items=[
                    ExamPaperItemInput(question_id=item.question_id, score=item.score)
                    for item in draft.items
                ],
                teacher_id=owner_id,
            ),
            save_context=ExamPaperSaveContext(
                question_source=source,
                section_by_question={
                    item.question_id: (item.section_id, item.section_title)
                    for item in draft.items
                },
                specification=draft.specification,
            ),
        )
        return PaperSavedVersion(
            exam_paper_id=paper.exam_paper_id,
            version=paper.version,
            title=paper.title,
            question_count=len(paper.items),
            total_score=paper.total_score,
            draft_fingerprint=draft.draft_fingerprint,
            specification=draft.specification,
            available_exports=self._export_options(),
            saved_at=paper.updated_at,
        )

    @staticmethod
    def _export_options() -> list[PaperSavedExportOption]:
        edition_labels = {
            "student": "学生卷",
            "answer": "答案卷",
            "blueprint": "双向细目表",
        }
        return [
            PaperSavedExportOption(
                edition=edition,
                format=export_format,
                label=f"{edition_labels[edition]} · {export_format.upper()}",
            )
            for edition in ("student", "answer", "blueprint")
            for export_format in ("docx", "pdf")
        ]


class PaperSavedExporting:
    """Exports an exact owner-scoped immutable paper version."""

    def __init__(self, *, studio: ExamPaperStudio, renderer: ExamPaperDocumentRenderer) -> None:
        self.studio = studio
        self.renderer = renderer

    def export(
        self,
        *,
        paper_id: str,
        version: int,
        owner_id: str,
        export_format: ExamPaperExportFormat,
        edition: ExamPaperEdition,
    ) -> RenderedExamPaper:
        try:
            paper = self.studio.get_owned_version(paper_id, version, owner_id=owner_id)
        except KeyError as exc:
            raise PaperSavedExportingError("试卷版本不存在或不属于当前教师。") from exc
        if paper.specification is None:
            raise PaperSavedExportingError("该版本不包含完整双向细目表，不能从 Paper Agent 导出。")
        if paper.version != version:
            raise PaperSavedExportingError("试卷版本快照不一致，已停止导出。")
        return self.renderer.render(paper, export_format, edition)
