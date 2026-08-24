from __future__ import annotations

from functools import lru_cache
from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException

from app.core.config import get_settings
from app.core.identity import CurrentTeacher, get_current_teacher
from app.modules.personal_question_library import (
    PersonalAuthoringDraftView,
    PersonalAuthoringRevisionCreate,
    PersonalAuthoringRevisionList,
    PersonalCategoryCreate,
    PersonalCategoryList,
    PersonalCategoryUpdate,
    PersonalCategoryView,
    PersonalCollectionCreate,
    PersonalCollectionList,
    PersonalCollectionUpdate,
    PersonalCollectionView,
    PersonalQuestionSave,
    PersonalQuestionView,
    PersonalQuestionLibrary,
    PersonalQuestionLibraryConflict,
    PersonalQuestionLibraryError,
)
from app.modules.question_authoring import QuestionAuthoring, QuestionAuthoringError


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
