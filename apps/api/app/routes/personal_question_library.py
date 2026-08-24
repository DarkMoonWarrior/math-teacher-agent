from __future__ import annotations

from functools import lru_cache
from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException

from app.core.config import get_settings
from app.core.identity import CurrentTeacher, get_current_teacher
from app.modules.personal_question_library import (
    PersonalCategoryCreate,
    PersonalCategoryList,
    PersonalCategoryUpdate,
    PersonalCategoryView,
    PersonalCollectionCreate,
    PersonalCollectionList,
    PersonalCollectionUpdate,
    PersonalCollectionView,
    PersonalQuestionLibrary,
    PersonalQuestionLibraryConflict,
    PersonalQuestionLibraryError,
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
