from __future__ import annotations

from functools import lru_cache
import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from app.core.config import get_settings
from app.core.identity import CurrentTeacher, get_current_teacher, require_local_legacy_access
from app.modules.lesson_exports import (
    LessonPlanExportError,
    SavedLessonPlanDocumentRenderer,
)
from app.modules.teacher_memory import TeacherMemory, TeacherPreferenceSignal
from app.modules.teacher_memory.dependencies import get_teacher_memory
from app.modules.lesson_plans import (
    LessonBlueprintBrief,
    LessonBlueprintDraft,
    LessonBlueprintPlanning,
    LessonBlueprintPlanningError,
    LessonSourceDraft,
    LessonSourceOptions,
    LessonSourceOptionsCommand,
    LessonSourceSelection,
    LessonSourceSelectionCommand,
    LessonSourceSelectionError,
    LessonDraftCommand,
    LessonDrafting,
    LessonDraftingConflict,
    LessonDraftingError,
    LessonEditableDraft,
    LessonBlockEditing,
    LessonBlockEditingConflict,
    LessonBlockEditingError,
    LessonBlockRewriteCommand,
    LessonSavedVersion,
    LessonSavedExporting,
    LessonSavedExportingError,
    LessonVersionHistoryItem,
    LessonVersionHistoryList,
    LessonVersionLifecycleCommand,
    LessonVersionSaveCommand,
    LessonVersioning,
    LessonVersioningConflict,
    LessonVersioningError,
    LessonPlanBlock,
    DeepSeekLessonPlanProvider,
    LessonPlanBlockLockCommand,
    LessonPlanBlockRewriteCommand,
    LessonPlanBlockRewriteResult,
    LessonPlanGenerationRequest,
    LessonPlanList,
    LessonPlanLifecycleCommand,
    LessonPlanProviderError,
    LessonPlanStudio,
    LessonPlanStudioError,
    LessonPlanUpdateCommand,
    LessonPlanView,
    OpenAIResponsesLessonPlanProvider,
    TemplateLessonPlanProvider,
)
from app.modules.curriculum import CsvCurriculumCatalog, CurriculumBaseline
from app.routes.model_operations import get_model_operations_registry
from app.routes.questions import get_question_bank
from app.routes.library import get_private_library
from app.routes.personal_question_library import get_personal_question_library


router = APIRouter(prefix="/lesson-plans", tags=["lesson-plans"])
logger = logging.getLogger(__name__)


def _observe_saved_lesson_preferences(
    memory: TeacherMemory,
    *,
    owner_id: str,
    saved: LessonSavedVersion,
) -> None:
    blueprint = saved.draft.source_draft.blueprint
    evidence_id = f"lesson_version:{saved.lesson_plan_id}:{saved.version}"
    for key, value in (
        ("default_grade", blueprint.grade_scope),
        ("default_lesson_minutes", blueprint.duration_minutes),
    ):
        try:
            memory.apply(
                TeacherPreferenceSignal(
                    key=key,
                    value=value,
                    evidence_category="confirmed_lesson_version",
                    evidence_id=evidence_id,
                ),
                owner_id=owner_id,
            )
        except Exception:
            logger.exception("teacher memory could not observe a saved lesson preference")


@lru_cache
def get_lesson_blueprint_planning() -> LessonBlueprintPlanning:
    settings = get_settings()
    return LessonBlueprintPlanning(
        curriculum_catalog=CsvCurriculumCatalog(settings.curriculum_csv),
    )


@lru_cache
def get_lesson_source_selection() -> LessonSourceSelection:
    settings = get_settings()
    return LessonSourceSelection(
        curriculum_catalog=CsvCurriculumCatalog(settings.curriculum_csv),
        question_bank=get_question_bank(),
        personal_question_library=get_personal_question_library(),
        private_library=get_private_library(),
    )


def get_lesson_drafting(
    selection: LessonSourceSelection = Depends(get_lesson_source_selection),
) -> LessonDrafting:
    return LessonDrafting(source_selection=selection)


def get_lesson_block_editing(
    drafting: LessonDrafting = Depends(get_lesson_drafting),
) -> LessonBlockEditing:
    return LessonBlockEditing(drafting=drafting)


def get_lesson_versioning(
    drafting: LessonDrafting = Depends(get_lesson_drafting),
) -> LessonVersioning:
    return LessonVersioning(
        database_path=get_settings().lesson_plan_db,
        drafting=drafting,
    )


@lru_cache
def get_lesson_plan_studio() -> LessonPlanStudio:
    settings = get_settings()
    baseline = CurriculumBaseline.load(
        settings.curriculum_baseline_manifest, settings.curriculum_csv
    )
    use_deepseek = settings.lesson_plan_provider == "deepseek" or (
        settings.lesson_plan_provider == "auto" and bool(settings.deepseek_api_key)
    )
    use_openai = not use_deepseek and (
        settings.lesson_plan_provider == "openai" or (
            settings.lesson_plan_provider == "auto" and bool(settings.openai_api_key)
        )
    )
    provider = DeepSeekLessonPlanProvider(
        api_key=settings.deepseek_api_key,
        model=settings.deepseek_model,
        base_url=settings.deepseek_base_url,
        timeout_seconds=settings.deepseek_timeout_seconds,
        recorder=get_model_operations_registry(),
    ) if use_deepseek else (
        OpenAIResponsesLessonPlanProvider(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            reasoning_effort=settings.openai_reasoning_effort,
            timeout_seconds=settings.openai_timeout_seconds,
            recorder=get_model_operations_registry(),
        )
        if use_openai
        else TemplateLessonPlanProvider(recorder=get_model_operations_registry())
    )
    return LessonPlanStudio(
        database_path=settings.lesson_plan_db,
        curriculum_catalog=CsvCurriculumCatalog(settings.curriculum_csv),
        curriculum_baseline=baseline,
        question_bank=get_question_bank(),
        provider=provider,
    )


@lru_cache
def get_lesson_plan_renderer() -> SavedLessonPlanDocumentRenderer:
    settings = get_settings()
    return SavedLessonPlanDocumentRenderer(
        output_root=settings.lesson_export_dir,
        cjk_font_regular=settings.cjk_font_regular,
        cjk_font_bold=settings.cjk_font_bold,
    )


def get_lesson_saved_exporting(
    versioning: LessonVersioning = Depends(get_lesson_versioning),
) -> LessonSavedExporting:
    return LessonSavedExporting(
        versioning=versioning,
        renderer=get_lesson_plan_renderer(),
    )


@router.get("", response_model=LessonPlanList, dependencies=[Depends(require_local_legacy_access)])
def list_lesson_plans(limit: int = Query(default=30, ge=1, le=100), lifecycle_state: Literal["active", "trashed"] = Query(default="active")) -> LessonPlanList:
    return get_lesson_plan_studio().list(limit=limit, lifecycle_state=lifecycle_state)


@router.post("/{lesson_plan_id}/lifecycle", response_model=LessonPlanView, dependencies=[Depends(require_local_legacy_access)])
def change_lesson_plan_lifecycle(lesson_plan_id: str, command: LessonPlanLifecycleCommand) -> LessonPlanView:
    try:
        return get_lesson_plan_studio().change_lifecycle(lesson_plan_id, command)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="教案不存在") from exc


@router.post("/generate", response_model=LessonPlanView, status_code=201, dependencies=[Depends(require_local_legacy_access)])
def generate_lesson_plan(command: LessonPlanGenerationRequest) -> LessonPlanView:
    try:
        return get_lesson_plan_studio().create(command)
    except LessonPlanStudioError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LessonPlanProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/blueprints/plan", response_model=LessonBlueprintDraft)
def plan_lesson_blueprint(
    command: LessonBlueprintBrief,
    teacher: CurrentTeacher = Depends(get_current_teacher),
    memory: TeacherMemory = Depends(get_teacher_memory),
) -> LessonBlueprintDraft:
    try:
        return get_lesson_blueprint_planning().plan(
            command,
            defaults=memory.planning_defaults(owner_id=teacher.teacher_id),
        )
    except LessonBlueprintPlanningError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/blueprints/source-options", response_model=LessonSourceOptions)
def list_lesson_source_options(
    command: LessonSourceOptionsCommand,
    teacher: CurrentTeacher = Depends(get_current_teacher),
    selection: LessonSourceSelection = Depends(get_lesson_source_selection),
) -> LessonSourceOptions:
    try:
        return selection.options(command.blueprint, owner_id=teacher.teacher_id)
    except LessonSourceSelectionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/blueprints/select-sources", response_model=LessonSourceDraft)
def select_lesson_sources(
    command: LessonSourceSelectionCommand,
    teacher: CurrentTeacher = Depends(get_current_teacher),
    selection: LessonSourceSelection = Depends(get_lesson_source_selection),
) -> LessonSourceDraft:
    try:
        return selection.select(command, owner_id=teacher.teacher_id)
    except LessonSourceSelectionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/blueprints/build-draft", response_model=LessonEditableDraft)
def build_lesson_draft(
    command: LessonDraftCommand,
    teacher: CurrentTeacher = Depends(get_current_teacher),
    drafting: LessonDrafting = Depends(get_lesson_drafting),
) -> LessonEditableDraft:
    try:
        return drafting.build(command, owner_id=teacher.teacher_id)
    except LessonDraftingConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except LessonDraftingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/blueprints/rewrite-block", response_model=LessonEditableDraft)
def rewrite_lesson_draft_block(
    command: LessonBlockRewriteCommand,
    teacher: CurrentTeacher = Depends(get_current_teacher),
    editing: LessonBlockEditing = Depends(get_lesson_block_editing),
) -> LessonEditableDraft:
    try:
        return editing.rewrite(command, owner_id=teacher.teacher_id)
    except LessonBlockEditingConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except LessonBlockEditingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/versions/save", response_model=LessonSavedVersion, status_code=201)
def save_lesson_version(
    command: LessonVersionSaveCommand,
    teacher: CurrentTeacher = Depends(get_current_teacher),
    versioning: LessonVersioning = Depends(get_lesson_versioning),
    memory: TeacherMemory = Depends(get_teacher_memory),
) -> LessonSavedVersion:
    try:
        saved = versioning.save(command, owner_id=teacher.teacher_id)
        _observe_saved_lesson_preferences(
            memory,
            owner_id=teacher.teacher_id,
            saved=saved,
        )
        return saved
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="教案不存在或不属于当前教师") from exc
    except LessonVersioningConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except LessonVersioningError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/versions/history", response_model=LessonVersionHistoryList)
def list_lesson_version_history(
    lifecycle_state: Literal["active", "trashed"] = Query(default="active"),
    limit: int = Query(default=30, ge=1, le=100),
    teacher: CurrentTeacher = Depends(get_current_teacher),
    versioning: LessonVersioning = Depends(get_lesson_versioning),
) -> LessonVersionHistoryList:
    return versioning.list(
        owner_id=teacher.teacher_id,
        lifecycle_state=lifecycle_state,
        limit=limit,
    )


@router.get("/versions/{lesson_plan_id}/export")
def export_saved_lesson_version(
    lesson_plan_id: str,
    version: int = Query(ge=1),
    format: Literal["docx", "pdf"] = Query(default="docx"),
    teacher: CurrentTeacher = Depends(get_current_teacher),
    exporting: LessonSavedExporting = Depends(get_lesson_saved_exporting),
) -> FileResponse:
    try:
        rendered = exporting.export(
            lesson_plan_id=lesson_plan_id,
            version=version,
            owner_id=teacher.teacher_id,
            export_format=format,
        )
    except LessonSavedExportingError as exc:
        raise HTTPException(
            status_code=404,
            detail="教案版本不存在或不属于当前教师",
        ) from exc
    except LessonPlanExportError as exc:
        raise HTTPException(status_code=500, detail="导出失败，请稍后重试") from exc
    return FileResponse(
        path=rendered.path,
        media_type=rendered.media_type,
        filename=rendered.download_name,
    )


@router.get("/versions/{lesson_plan_id}", response_model=LessonSavedVersion)
def get_lesson_version(
    lesson_plan_id: str,
    version: int | None = Query(default=None, ge=1),
    teacher: CurrentTeacher = Depends(get_current_teacher),
    versioning: LessonVersioning = Depends(get_lesson_versioning),
) -> LessonSavedVersion:
    try:
        return versioning.get(
            lesson_plan_id,
            owner_id=teacher.teacher_id,
            version=version,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="教案版本不存在或不属于当前教师") from exc


@router.post(
    "/versions/{lesson_plan_id}/lifecycle",
    response_model=LessonVersionHistoryItem,
)
def change_lesson_version_lifecycle(
    lesson_plan_id: str,
    command: LessonVersionLifecycleCommand,
    teacher: CurrentTeacher = Depends(get_current_teacher),
    versioning: LessonVersioning = Depends(get_lesson_versioning),
) -> LessonVersionHistoryItem:
    try:
        return versioning.change_lifecycle(
            lesson_plan_id,
            command,
            owner_id=teacher.teacher_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="教案不存在或不属于当前教师") from exc


@router.get("/{lesson_plan_id}", response_model=LessonPlanView, dependencies=[Depends(require_local_legacy_access)])
def get_lesson_plan(lesson_plan_id: str) -> LessonPlanView:
    try:
        return get_lesson_plan_studio().get(lesson_plan_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="教案不存在") from exc


@router.put("/{lesson_plan_id}/blocks/{block}/lock", response_model=LessonPlanView, dependencies=[Depends(require_local_legacy_access)])
def set_lesson_plan_block_lock(
    lesson_plan_id: str,
    block: LessonPlanBlock,
    command: LessonPlanBlockLockCommand,
) -> LessonPlanView:
    try:
        return get_lesson_plan_studio().set_block_lock(
            lesson_plan_id, block, locked=command.locked
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="教案不存在") from exc


@router.post(
    "/{lesson_plan_id}/blocks/{block}/rewrite",
    response_model=LessonPlanBlockRewriteResult,
    dependencies=[Depends(require_local_legacy_access)],
)
def rewrite_lesson_plan_block(
    lesson_plan_id: str,
    block: LessonPlanBlock,
    command: LessonPlanBlockRewriteCommand,
) -> LessonPlanBlockRewriteResult:
    try:
        return get_lesson_plan_studio().rewrite_block(lesson_plan_id, block, command)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="教案不存在") from exc
    except LessonPlanStudioError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LessonPlanProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/{lesson_plan_id}/export", dependencies=[Depends(require_local_legacy_access)])
def export_lesson_plan(
    lesson_plan_id: str,
    format: Literal["docx", "pdf"] = Query(default="docx"),
) -> FileResponse:
    try:
        plan = get_lesson_plan_studio().get(lesson_plan_id)
        rendered = get_lesson_plan_renderer().render(plan, format)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="教案不存在") from exc
    except LessonPlanExportError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return FileResponse(
        path=rendered.path,
        media_type=rendered.media_type,
        filename=rendered.download_name,
    )


@router.patch("/{lesson_plan_id}", response_model=LessonPlanView, dependencies=[Depends(require_local_legacy_access)])
def update_lesson_plan(
    lesson_plan_id: str, command: LessonPlanUpdateCommand
) -> LessonPlanView:
    try:
        return get_lesson_plan_studio().update(lesson_plan_id, command)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="教案不存在") from exc
    except LessonPlanStudioError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
