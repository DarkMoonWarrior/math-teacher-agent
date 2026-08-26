from __future__ import annotations

from functools import lru_cache
from typing import Literal, NoReturn
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.core.config import get_settings
from app.core.identity import CurrentTeacher, get_current_teacher
from app.modules.personal_question_library import (
    PersonalAuthoringDraftView,
    PersonalAuthoringRevisionCreate,
    PersonalAuthoringRevisionList,
    PersonalAuthoringSolutionRegenerate,
    PersonalCategoryCreate,
    PersonalCategoryList,
    PersonalCategoryUpdate,
    PersonalCategoryView,
    PersonalCollectionCreate,
    PersonalCollectionList,
    PersonalCollectionUpdate,
    PersonalCollectionView,
    PersonalQuestionCopy,
    PersonalQuestionDeletionReceipt,
    PersonalQuestionList,
    PersonalQuestionPermanentDelete,
    PersonalQuestionRevisionCreate,
    PersonalQuestionSave,
    PersonalQuestionUpdate,
    PersonalQuestionVersionCommand,
    PersonalQuestionView,
    PersonalQuestionLibrary,
    PersonalQuestionLibraryConflict,
    PersonalQuestionLibraryError,
)
from app.modules.question_authoring import (
    GeneratedQuestionDraft,
    QuestionAuthoring,
    QuestionAuthoringError,
)


router = APIRouter(
    prefix="/personal-question-library",
    tags=["personal-question-library"],
)


@lru_cache
def get_personal_question_library() -> PersonalQuestionLibrary:
    return PersonalQuestionLibrary(get_settings().personal_question_library_db)


def _raise_library_error(exc: PersonalQuestionLibraryError) -> NoReturn:
    status_code = 409 if isinstance(exc, PersonalQuestionLibraryConflict) else 422
    raise HTTPException(status_code=status_code, detail=str(exc)) from exc


def get_question_authoring_editor() -> QuestionAuthoring:
    # Local import avoids coupling either business module to FastAPI route wiring.
    from app.routes.question_authoring import get_question_authoring

    return get_question_authoring()


@router.get("/collections", response_model=PersonalCollectionList)
def list_personal_collections(
    teacher: CurrentTeacher = Depends(get_current_teacher),
    library: PersonalQuestionLibrary = Depends(get_personal_question_library),
) -> PersonalCollectionList:
    return library.list_collections(owner_id=teacher.teacher_id)


@router.post("/collections", response_model=PersonalCollectionView, status_code=201)
def create_personal_collection(
    command: PersonalCollectionCreate,
    teacher: CurrentTeacher = Depends(get_current_teacher),
    library: PersonalQuestionLibrary = Depends(get_personal_question_library),
) -> PersonalCollectionView:
    try:
        return library.create_collection(command, owner_id=teacher.teacher_id)
    except PersonalQuestionLibraryError as exc:
        _raise_library_error(exc)


@router.get("/collections/{collection_id}", response_model=PersonalCollectionView)
def get_personal_collection(
    collection_id: str,
    teacher: CurrentTeacher = Depends(get_current_teacher),
    library: PersonalQuestionLibrary = Depends(get_personal_question_library),
) -> PersonalCollectionView:
    try:
        return library.get_collection(collection_id, owner_id=teacher.teacher_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="个人题库不存在") from exc


@router.patch("/collections/{collection_id}", response_model=PersonalCollectionView)
def update_personal_collection(
    collection_id: str,
    command: PersonalCollectionUpdate,
    teacher: CurrentTeacher = Depends(get_current_teacher),
    library: PersonalQuestionLibrary = Depends(get_personal_question_library),
) -> PersonalCollectionView:
    try:
        return library.update_collection(
            collection_id,
            command,
            owner_id=teacher.teacher_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="个人题库不存在") from exc
    except PersonalQuestionLibraryError as exc:
        _raise_library_error(exc)


@router.get(
    "/collections/{collection_id}/categories",
    response_model=PersonalCategoryList,
)
def list_personal_categories(
    collection_id: str,
    teacher: CurrentTeacher = Depends(get_current_teacher),
    library: PersonalQuestionLibrary = Depends(get_personal_question_library),
) -> PersonalCategoryList:
    try:
        return library.list_categories(collection_id, owner_id=teacher.teacher_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="个人题库不存在") from exc


@router.post(
    "/collections/{collection_id}/categories",
    response_model=PersonalCategoryView,
    status_code=201,
)
def create_personal_category(
    collection_id: str,
    command: PersonalCategoryCreate,
    teacher: CurrentTeacher = Depends(get_current_teacher),
    library: PersonalQuestionLibrary = Depends(get_personal_question_library),
) -> PersonalCategoryView:
    try:
        return library.create_category(
            collection_id,
            command,
            owner_id=teacher.teacher_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="个人题库不存在") from exc
    except PersonalQuestionLibraryError as exc:
        _raise_library_error(exc)


@router.get("/categories/{category_id}", response_model=PersonalCategoryView)
def get_personal_category(
    category_id: str,
    teacher: CurrentTeacher = Depends(get_current_teacher),
    library: PersonalQuestionLibrary = Depends(get_personal_question_library),
) -> PersonalCategoryView:
    try:
        return library.get_category(category_id, owner_id=teacher.teacher_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="个人分类不存在") from exc


@router.patch("/categories/{category_id}", response_model=PersonalCategoryView)
def update_personal_category(
    category_id: str,
    command: PersonalCategoryUpdate,
    teacher: CurrentTeacher = Depends(get_current_teacher),
    library: PersonalQuestionLibrary = Depends(get_personal_question_library),
) -> PersonalCategoryView:
    try:
        return library.update_category(
            category_id,
            command,
            owner_id=teacher.teacher_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="个人分类不存在") from exc
    except PersonalQuestionLibraryError as exc:
        _raise_library_error(exc)


@router.get(
    "/authoring-drafts/{draft_id}",
    response_model=PersonalAuthoringDraftView,
)
def get_personal_authoring_draft(
    draft_id: str,
    teacher: CurrentTeacher = Depends(get_current_teacher),
    library: PersonalQuestionLibrary = Depends(get_personal_question_library),
) -> PersonalAuthoringDraftView:
    try:
        return library.get_authoring_draft(draft_id, owner_id=teacher.teacher_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="命题草稿不存在") from exc


@router.get(
    "/authoring-drafts/{draft_id}/revisions",
    response_model=PersonalAuthoringRevisionList,
)
def list_personal_authoring_revisions(
    draft_id: str,
    teacher: CurrentTeacher = Depends(get_current_teacher),
    library: PersonalQuestionLibrary = Depends(get_personal_question_library),
) -> PersonalAuthoringRevisionList:
    try:
        return library.list_authoring_revisions(draft_id, owner_id=teacher.teacher_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="命题草稿不存在") from exc


@router.post(
    "/authoring-drafts/{draft_id}/revisions",
    response_model=PersonalAuthoringDraftView,
    status_code=201,
)
def revise_personal_authoring_draft(
    draft_id: str,
    command: PersonalAuthoringRevisionCreate,
    teacher: CurrentTeacher = Depends(get_current_teacher),
    library: PersonalQuestionLibrary = Depends(get_personal_question_library),
    authoring: QuestionAuthoring = Depends(get_question_authoring_editor),
) -> PersonalAuthoringDraftView:
    try:
        current = library.get_authoring_draft(draft_id, owner_id=teacher.teacher_id)
        if current.current_revision != command.expected_revision:
            raise PersonalQuestionLibraryConflict(
                f"草稿版本已更新，当前版本为 {current.current_revision}"
            )
        revised = authoring.revise_draft(current.current.draft, command.content)
        return library.append_teacher_revision(
            revised,
            owner_id=teacher.teacher_id,
            expected_revision=command.expected_revision,
            edit_summary=command.edit_summary,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="命题草稿不存在") from exc
    except QuestionAuthoringError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PersonalQuestionLibraryError as exc:
        _raise_library_error(exc)


@router.post(
    "/authoring-drafts/{draft_id}/regenerate-solution",
    response_model=PersonalAuthoringDraftView,
    status_code=201,
)
def regenerate_personal_authoring_solution(
    draft_id: str,
    command: PersonalAuthoringSolutionRegenerate,
    teacher: CurrentTeacher = Depends(get_current_teacher),
    library: PersonalQuestionLibrary = Depends(get_personal_question_library),
    authoring: QuestionAuthoring = Depends(get_question_authoring_editor),
) -> PersonalAuthoringDraftView:
    try:
        current = library.get_authoring_draft(draft_id, owner_id=teacher.teacher_id)
        if current.current_revision != command.expected_revision:
            raise PersonalQuestionLibraryConflict(
                f"草稿版本已更新，当前版本为 {current.current_revision}"
            )
        regenerated = authoring.regenerate_solution(current.current.draft)
        return library.append_ai_revision(
            regenerated,
            owner_id=teacher.teacher_id,
            expected_revision=command.expected_revision,
            edit_summary="AI 重新生成解析；题面、选项与最终答案保持不变",
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="命题草稿不存在") from exc
    except QuestionAuthoringError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PersonalQuestionLibraryError as exc:
        _raise_library_error(exc)


@router.post(
    "/authoring-drafts/{draft_id}/save",
    response_model=PersonalQuestionView,
    status_code=201,
)
def save_personal_authoring_draft(
    draft_id: str,
    command: PersonalQuestionSave,
    teacher: CurrentTeacher = Depends(get_current_teacher),
    library: PersonalQuestionLibrary = Depends(get_personal_question_library),
) -> PersonalQuestionView:
    try:
        return library.save_authoring_draft(
            draft_id,
            command,
            owner_id=teacher.teacher_id,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail="命题草稿、个人题库或分类不存在",
        ) from exc
    except PersonalQuestionLibraryError as exc:
        _raise_library_error(exc)


@router.get("/questions", response_model=PersonalQuestionList)
def list_personal_questions(
    query: str = Query(default="", max_length=300),
    collection_id: str | None = Query(default=None, max_length=160),
    category_id: str | None = Query(default=None, max_length=160),
    lifecycle_state: Literal["active", "trashed"] = Query(default="active"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    teacher: CurrentTeacher = Depends(get_current_teacher),
    library: PersonalQuestionLibrary = Depends(get_personal_question_library),
) -> PersonalQuestionList:
    try:
        return library.list_questions(
            owner_id=teacher.teacher_id,
            query=query,
            collection_id=collection_id,
            category_id=category_id,
            lifecycle_state=lifecycle_state,
            limit=limit,
            offset=offset,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="个人题库或分类不存在") from exc
    except PersonalQuestionLibraryError as exc:
        _raise_library_error(exc)


@router.get("/questions/{question_id}", response_model=PersonalQuestionView)
def get_personal_question(
    question_id: str,
    teacher: CurrentTeacher = Depends(get_current_teacher),
    library: PersonalQuestionLibrary = Depends(get_personal_question_library),
) -> PersonalQuestionView:
    try:
        return library.get_question(question_id, owner_id=teacher.teacher_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="个人题目不存在") from exc


@router.get(
    "/questions/{question_id}/revisions",
    response_model=PersonalAuthoringRevisionList,
)
def list_personal_question_revisions(
    question_id: str,
    teacher: CurrentTeacher = Depends(get_current_teacher),
    library: PersonalQuestionLibrary = Depends(get_personal_question_library),
) -> PersonalAuthoringRevisionList:
    try:
        question = library.get_question(question_id, owner_id=teacher.teacher_id)
        return library.list_authoring_revisions(
            question.source_draft_id,
            owner_id=teacher.teacher_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="个人题目不存在") from exc


@router.post(
    "/questions/{question_id}/revisions",
    response_model=PersonalQuestionView,
    status_code=201,
)
def revise_saved_personal_question(
    question_id: str,
    command: PersonalQuestionRevisionCreate,
    teacher: CurrentTeacher = Depends(get_current_teacher),
    library: PersonalQuestionLibrary = Depends(get_personal_question_library),
    authoring: QuestionAuthoring = Depends(get_question_authoring_editor),
) -> PersonalQuestionView:
    try:
        current = library.get_question(question_id, owner_id=teacher.teacher_id)
        draft_payload = current.question.model_dump(mode="json")
        draft_payload["saved"] = False
        current_draft = GeneratedQuestionDraft.model_validate(draft_payload)
        revised = authoring.revise_draft(current_draft, command.content)
        return library.append_saved_question_revision(
            question_id,
            revised,
            command,
            owner_id=teacher.teacher_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="个人题目不存在") from exc
    except QuestionAuthoringError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PersonalQuestionLibraryError as exc:
        _raise_library_error(exc)


@router.patch("/questions/{question_id}", response_model=PersonalQuestionView)
def update_personal_question(
    question_id: str,
    command: PersonalQuestionUpdate,
    teacher: CurrentTeacher = Depends(get_current_teacher),
    library: PersonalQuestionLibrary = Depends(get_personal_question_library),
) -> PersonalQuestionView:
    try:
        return library.update_question(question_id, command, owner_id=teacher.teacher_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail="个人题目、题库或分类不存在",
        ) from exc
    except PersonalQuestionLibraryError as exc:
        _raise_library_error(exc)


@router.post(
    "/questions/{question_id}/copy",
    response_model=PersonalQuestionView,
    status_code=201,
)
def copy_personal_question(
    question_id: str,
    command: PersonalQuestionCopy,
    teacher: CurrentTeacher = Depends(get_current_teacher),
    library: PersonalQuestionLibrary = Depends(get_personal_question_library),
) -> PersonalQuestionView:
    try:
        return library.copy_question(question_id, command, owner_id=teacher.teacher_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail="个人题目、题库或分类不存在",
        ) from exc
    except PersonalQuestionLibraryError as exc:
        _raise_library_error(exc)


@router.get("/questions/{question_id}/export")
def export_personal_question(
    question_id: str,
    export_format: Literal["json", "markdown"] = Query(alias="format"),
    teacher: CurrentTeacher = Depends(get_current_teacher),
    library: PersonalQuestionLibrary = Depends(get_personal_question_library),
) -> Response:
    try:
        artifact = library.export_question(
            question_id,
            owner_id=teacher.teacher_id,
            export_format=export_format,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="个人题目不存在") from exc
    except PersonalQuestionLibraryError as exc:
        _raise_library_error(exc)
    return Response(
        content=artifact.content,
        media_type=artifact.media_type,
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": (
                "attachment; filename*=UTF-8''" + quote(artifact.filename)
            ),
        },
    )


@router.post("/questions/{question_id}/trash", response_model=PersonalQuestionView)
def trash_personal_question(
    question_id: str,
    command: PersonalQuestionVersionCommand,
    teacher: CurrentTeacher = Depends(get_current_teacher),
    library: PersonalQuestionLibrary = Depends(get_personal_question_library),
) -> PersonalQuestionView:
    try:
        return library.trash_question(question_id, command, owner_id=teacher.teacher_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="个人题目不存在") from exc
    except PersonalQuestionLibraryError as exc:
        _raise_library_error(exc)


@router.post("/questions/{question_id}/restore", response_model=PersonalQuestionView)
def restore_personal_question(
    question_id: str,
    command: PersonalQuestionVersionCommand,
    teacher: CurrentTeacher = Depends(get_current_teacher),
    library: PersonalQuestionLibrary = Depends(get_personal_question_library),
) -> PersonalQuestionView:
    try:
        return library.restore_question(question_id, command, owner_id=teacher.teacher_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="个人题目不存在") from exc
    except PersonalQuestionLibraryError as exc:
        _raise_library_error(exc)


@router.delete(
    "/questions/{question_id}",
    response_model=PersonalQuestionDeletionReceipt,
)
def permanently_delete_personal_question(
    question_id: str,
    command: PersonalQuestionPermanentDelete,
    teacher: CurrentTeacher = Depends(get_current_teacher),
    library: PersonalQuestionLibrary = Depends(get_personal_question_library),
) -> PersonalQuestionDeletionReceipt:
    try:
        return library.permanently_delete_question(
            question_id,
            command,
            owner_id=teacher.teacher_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="个人题目不存在") from exc
    except PersonalQuestionLibraryError as exc:
        _raise_library_error(exc)
