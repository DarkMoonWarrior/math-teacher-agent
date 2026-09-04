from __future__ import annotations

from functools import lru_cache
import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from app.core.config import get_settings
from app.core.identity import CurrentTeacher, get_current_teacher, require_local_legacy_access
from app.modules.exam_exports import ExamPaperDocumentRenderer, ExamPaperExportError
from app.modules.teacher_memory import TeacherMemory, TeacherPreferenceSignal
from app.modules.teacher_memory.dependencies import get_teacher_memory
from app.modules.exam_papers import (
    ExamPaperComposer,
    ExamPaperComposeCommand,
    ExamPaperComposeError,
    ExamPaperCreateCommand,
    ExamPaperEdition,
    ExamPaperExportFormat,
    ExamPaperHistoryRevisionCommand,
    ExamPaperList,
    ExamPaperLifecycleCommand,
    ExamPaperProposal,
    ExamPaperStudio,
    ExamPaperStudioError,
    ExamPaperTemplateCatalog,
    ExamPaperTemplateComposeCommand,
    ExamPaperTemplateError,
    ExamPaperTemplateList,
    ExamPaperUpdateCommand,
    ExamPaperView,
    PaperBlueprintBrief,
    PaperBlueprintDraft,
    PaperBlueprintPlanning,
    PaperBlueprintPlanningError,
    PaperBlueprintSelection,
    PaperBlueprintSelectionCommand,
    PaperBlueprintSelectionDraft,
    PaperBlueprintSelectionError,
    PaperPublicQuestionCandidateList,
    PaperEditableDraft,
    PaperEditableDraftCommand,
    PaperEditableDrafting,
    PaperEditableDraftingError,
    PaperSavedVersion,
    PaperVersionSaveCommand,
)
from app.modules.exam_papers.versioning import (
    PaperResolvedQuestionSource,
    PaperSavedExporting,
    PaperSavedExportingError,
    PaperVersioning,
    PaperVersioningConflict,
    PaperVersioningError,
)
from app.modules.exam_papers.studio import ExamPaperStudioConflict
from app.routes.personal_question_library import get_personal_question_library
from app.routes.questions import get_question_bank


router = APIRouter(prefix="/exam-papers", tags=["exam-papers"])
logger = logging.getLogger(__name__)


def _observe_saved_paper_preferences(
    memory: TeacherMemory,
    *,
    owner_id: str,
    saved: PaperSavedVersion,
    command: PaperVersionSaveCommand,
) -> None:
    blueprint = command.draft_command.selection_request.blueprint
    difficulty = {"foundation": 2, "balanced": 3, "challenge": 5}[blueprint.difficulty_profile]
    evidence_id = f"paper_version:{saved.exam_paper_id}:{saved.version}"
    for key, value in (
        ("default_grade", blueprint.grade_scope),
        ("default_difficulty", difficulty),
    ):
        try:
            memory.apply(
                TeacherPreferenceSignal(
                    key=key,
                    value=value,
                    evidence_category="confirmed_paper_version",
                    evidence_id=evidence_id,
                ),
                owner_id=owner_id,
            )
        except Exception:
            logger.exception("teacher memory could not observe a saved paper preference")


@lru_cache
def get_exam_paper_studio() -> ExamPaperStudio:
    settings = get_settings()
    return ExamPaperStudio(
        database_path=settings.exam_paper_db,
        asset_root=settings.exam_paper_asset_dir,
        question_bank=get_question_bank(),
    )


@lru_cache
def get_exam_paper_composer() -> ExamPaperComposer:
    return ExamPaperComposer(
        question_bank=get_question_bank(),
        template_catalog=get_exam_paper_template_catalog(),
    )


@lru_cache
def get_paper_blueprint_planning() -> PaperBlueprintPlanning:
    return PaperBlueprintPlanning()


@lru_cache
def get_paper_blueprint_selection() -> PaperBlueprintSelection:
    return PaperBlueprintSelection(
        question_bank=get_question_bank(),
        personal_question_library=get_personal_question_library(),
    )


def get_paper_editable_drafting(
    selection: PaperBlueprintSelection = Depends(get_paper_blueprint_selection),
) -> PaperEditableDrafting:
    return PaperEditableDrafting(selection=selection)


def get_paper_versioning(
    drafting: PaperEditableDrafting = Depends(get_paper_editable_drafting),
) -> PaperVersioning:
    return PaperVersioning(drafting=drafting, studio=get_exam_paper_studio())


def get_paper_saved_exporting() -> PaperSavedExporting:
    return PaperSavedExporting(
        studio=get_exam_paper_studio(),
        renderer=get_exam_paper_renderer(),
    )


@lru_cache
def get_exam_paper_template_catalog() -> ExamPaperTemplateCatalog:
    return ExamPaperTemplateCatalog()


@lru_cache
def get_exam_paper_renderer() -> ExamPaperDocumentRenderer:
    settings = get_settings()
    return ExamPaperDocumentRenderer(
        output_root=settings.lesson_export_dir,
        asset_root=settings.exam_paper_asset_dir,
        cjk_font_regular=settings.cjk_font_regular,
        cjk_font_bold=settings.cjk_font_bold,
    )


@router.get("", response_model=ExamPaperList)
def list_exam_papers(
    limit: int = Query(default=30, ge=1, le=100),
    lifecycle_state: Literal["active", "trashed"] = Query(default="active"),
    teacher: CurrentTeacher = Depends(get_current_teacher),
) -> ExamPaperList:
    return get_exam_paper_studio().list_owned(
        owner_id=teacher.teacher_id,
        limit=limit,
        lifecycle_state=lifecycle_state,
    )


@router.post("/{paper_id}/lifecycle", response_model=ExamPaperView)
def change_exam_paper_lifecycle(
    paper_id: str,
    command: ExamPaperLifecycleCommand,
    teacher: CurrentTeacher = Depends(get_current_teacher),
) -> ExamPaperView:
    try:
        return get_exam_paper_studio().change_owned_lifecycle(
            paper_id,
            command,
            owner_id=teacher.teacher_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="试卷不存在") from exc


@router.post("", response_model=ExamPaperView, status_code=201,
             dependencies=[Depends(require_local_legacy_access)])
def create_exam_paper(
    command: ExamPaperCreateCommand,
    teacher: CurrentTeacher = Depends(get_current_teacher),
) -> ExamPaperView:
    try:
        return get_exam_paper_studio().create(
            command.model_copy(update={"teacher_id": teacher.teacher_id})
        )
    except ExamPaperStudioError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/compose", response_model=ExamPaperProposal,
             dependencies=[Depends(require_local_legacy_access)])
def compose_exam_paper(command: ExamPaperComposeCommand) -> ExamPaperProposal:
    try:
        return get_exam_paper_composer().compose(command)
    except ExamPaperComposeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/blueprints/plan", response_model=PaperBlueprintDraft)
def plan_paper_blueprint(
    command: PaperBlueprintBrief,
    teacher: CurrentTeacher = Depends(get_current_teacher),
    memory: TeacherMemory = Depends(get_teacher_memory),
) -> PaperBlueprintDraft:
    try:
        return get_paper_blueprint_planning().plan(
            command,
            defaults=memory.planning_defaults(owner_id=teacher.teacher_id),
        )
    except PaperBlueprintPlanningError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/blueprints/select", response_model=PaperBlueprintSelectionDraft)
def select_paper_blueprint(
    command: PaperBlueprintSelectionCommand,
    teacher: CurrentTeacher = Depends(get_current_teacher),
    selection: PaperBlueprintSelection = Depends(get_paper_blueprint_selection),
) -> PaperBlueprintSelectionDraft:
    try:
        return selection.select(command, owner_id=teacher.teacher_id)
    except PaperBlueprintSelectionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/blueprints/public-candidates", response_model=PaperPublicQuestionCandidateList)
def list_paper_public_candidates(
    query: str | None = Query(default=None, max_length=160),
    question_type: str | None = Query(default=None, max_length=60),
    limit: int = Query(default=50, ge=1, le=100),
    teacher: CurrentTeacher = Depends(get_current_teacher),
    selection: PaperBlueprintSelection = Depends(get_paper_blueprint_selection),
) -> PaperPublicQuestionCandidateList:
    # The browser receives only already-gated public candidates; it cannot
    # supply an owner, visibility, review, or verification override.
    return selection.list_public_candidates(
        owner_id=teacher.teacher_id,
        query=query,
        question_type=question_type,
        limit=limit,
    )


@router.post("/blueprints/edit-draft", response_model=PaperEditableDraft)
def edit_paper_blueprint_draft(
    command: PaperEditableDraftCommand,
    teacher: CurrentTeacher = Depends(get_current_teacher),
    drafting: PaperEditableDrafting = Depends(get_paper_editable_drafting),
) -> PaperEditableDraft:
    try:
        return drafting.build(command, owner_id=teacher.teacher_id)
    except (PaperBlueprintSelectionError, PaperEditableDraftingError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/blueprints/save-version", response_model=PaperSavedVersion, status_code=201)
def save_paper_blueprint_version(
    command: PaperVersionSaveCommand,
    teacher: CurrentTeacher = Depends(get_current_teacher),
    versioning: PaperVersioning = Depends(get_paper_versioning),
    memory: TeacherMemory = Depends(get_teacher_memory),
) -> PaperSavedVersion:
    try:
        saved = versioning.save(command, owner_id=teacher.teacher_id)
        _observe_saved_paper_preferences(
            memory,
            owner_id=teacher.teacher_id,
            saved=saved,
            command=command,
        )
        return saved
    except PaperVersioningConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (PaperBlueprintSelectionError, PaperEditableDraftingError, PaperVersioningError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/templates", response_model=ExamPaperTemplateList)
def list_exam_paper_templates() -> ExamPaperTemplateList:
    return get_exam_paper_template_catalog().list()


@router.post("/compose-template", response_model=ExamPaperProposal,
             dependencies=[Depends(require_local_legacy_access)])
def compose_exam_paper_template(
    command: ExamPaperTemplateComposeCommand,
) -> ExamPaperProposal:
    try:
        return get_exam_paper_composer().compose_template(command)
    except (ExamPaperComposeError, ExamPaperTemplateError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{paper_id}", response_model=ExamPaperView)
def get_exam_paper(
    paper_id: str,
    teacher: CurrentTeacher = Depends(get_current_teacher),
) -> ExamPaperView:
    try:
        return get_exam_paper_studio().get_owned(
            paper_id,
            owner_id=teacher.teacher_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="试卷不存在") from exc


@router.put("/{paper_id}", response_model=ExamPaperView,
            dependencies=[Depends(require_local_legacy_access)])
def update_exam_paper(
    paper_id: str,
    command: ExamPaperUpdateCommand,
    teacher: CurrentTeacher = Depends(get_current_teacher),
) -> ExamPaperView:
    try:
        studio = get_exam_paper_studio()
        studio.get_owned(paper_id, owner_id=teacher.teacher_id)
        return studio.update(
            paper_id,
            command.model_copy(update={"teacher_id": teacher.teacher_id}),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="试卷不存在") from exc
    except ExamPaperStudioError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.put("/{paper_id}/history-revision", response_model=ExamPaperView)
def revise_exam_paper_history(
    paper_id: str,
    command: ExamPaperHistoryRevisionCommand,
    teacher: CurrentTeacher = Depends(get_current_teacher),
) -> ExamPaperView:
    try:
        studio = get_exam_paper_studio()
        studio.get_owned(paper_id, owner_id=teacher.teacher_id)
        resolved_items = []
        source = None
        if command.selected_public_question_ids or command.selected_private_question_ids:
            selection = get_paper_blueprint_selection()
            resolved_items = selection.resolve_explicit_candidates(
                owner_id=teacher.teacher_id,
                public_question_ids=command.selected_public_question_ids,
                private_question_ids=command.selected_private_question_ids,
            )
            source = PaperResolvedQuestionSource(
                selection=selection,
                owner_id=teacher.teacher_id,
                items=resolved_items,
            )
            source.validate_all()
        return studio.revise_owned_history(
            paper_id,
            command,
            owner_id=teacher.teacher_id,
            added_question_source=source,
        )
    except ExamPaperStudioConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="试卷不存在") from exc
    except ExamPaperStudioError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (PaperBlueprintSelectionError, PaperVersioningError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{paper_id}/export")
def export_exam_paper(
    paper_id: str,
    format: ExamPaperExportFormat = Query(default="docx"),
    edition: ExamPaperEdition = Query(default="student"),
    teacher: CurrentTeacher = Depends(get_current_teacher),
) -> FileResponse:
    try:
        paper = get_exam_paper_studio().get_owned(
            paper_id,
            owner_id=teacher.teacher_id,
        )
        rendered = get_exam_paper_renderer().render(paper, format, edition)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="试卷不存在") from exc
    except ExamPaperExportError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return FileResponse(
        path=rendered.path,
        media_type=rendered.media_type,
        filename=rendered.download_name,
    )


@router.get("/{paper_id}/versions/{version}/export")
def export_saved_exam_paper_version(
    paper_id: str,
    version: int,
    format: ExamPaperExportFormat = Query(default="docx"),
    edition: ExamPaperEdition = Query(default="student"),
    teacher: CurrentTeacher = Depends(get_current_teacher),
    exporting: PaperSavedExporting = Depends(get_paper_saved_exporting),
) -> FileResponse:
    try:
        rendered = exporting.export(
            paper_id=paper_id,
            version=version,
            owner_id=teacher.teacher_id,
            export_format=format,
            edition=edition,
        )
    except PaperSavedExportingError as exc:
        raise HTTPException(status_code=404, detail="试卷版本不存在或不属于当前教师") from exc
    except ExamPaperExportError as exc:
        raise HTTPException(status_code=500, detail="导出失败，请稍后重试") from exc
    return FileResponse(
        path=rendered.path,
        media_type=rendered.media_type,
        filename=rendered.download_name,
    )
