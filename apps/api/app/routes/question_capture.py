from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from app.core.config import get_settings
from app.core.identity import CurrentTeacher, get_current_teacher
from app.modules.question_capture import (
    QuestionCapture,
    QuestionCaptureCommand,
    QuestionCaptureError,
    QuestionInputBundle,
    QuestionMediaSource,
    QuestionMediaTransformCommand,
)


router = APIRouter(prefix="/question-capture", tags=["question-capture"])


@lru_cache
def get_question_capture() -> QuestionCapture:
    settings = get_settings()
    return QuestionCapture(settings.question_capture_db, settings.question_capture_dir)


@router.post("/assets", response_model=QuestionInputBundle, status_code=201)
async def upload_question_asset(
    file: UploadFile = File(...),
    source: QuestionMediaSource = Form(...),
    private_storage_acknowledged: bool = Form(...),
    current_teacher: CurrentTeacher = Depends(get_current_teacher),
    capture: QuestionCapture = Depends(get_question_capture),
) -> QuestionInputBundle:
    try:
        content = await file.read(QuestionCapture.MAX_FILE_BYTES + 1)
        return capture.prepare(
            QuestionCaptureCommand(
                owner_id=current_teacher.teacher_id,
                source=source,
                private_storage_acknowledged=private_storage_acknowledged,
            ),
            filename=file.filename or "题目图片",
            content=content,
        )
    except QuestionCaptureError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/assets/{asset_id}", response_model=QuestionInputBundle)
def get_question_asset(
    asset_id: str,
    current_teacher: CurrentTeacher = Depends(get_current_teacher),
    capture: QuestionCapture = Depends(get_question_capture),
) -> QuestionInputBundle:
    try:
        return capture.get(asset_id, owner_id=current_teacher.teacher_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="私人题目图片不存在") from exc


@router.post("/assets/{asset_id}/transform", response_model=QuestionInputBundle)
def transform_question_asset(
    asset_id: str,
    command: QuestionMediaTransformCommand,
    current_teacher: CurrentTeacher = Depends(get_current_teacher),
    capture: QuestionCapture = Depends(get_question_capture),
) -> QuestionInputBundle:
    try:
        return capture.transform(asset_id, command, owner_id=current_teacher.teacher_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="私人题目图片不存在") from exc
    except QuestionCaptureError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/assets/{asset_id}/content", response_class=FileResponse)
def question_asset_content(
    asset_id: str,
    revision: int | None = Query(default=None, ge=1),
    current_teacher: CurrentTeacher = Depends(get_current_teacher),
    capture: QuestionCapture = Depends(get_question_capture),
) -> FileResponse:
    try:
        path, mime_type = capture.content(
            asset_id,
            owner_id=current_teacher.teacher_id,
            revision=revision,
        )
        return FileResponse(path, media_type=mime_type)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="私人题目图片不存在") from exc
    except QuestionCaptureError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
