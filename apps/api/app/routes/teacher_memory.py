from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException

from app.core.config import get_settings
from app.core.identity import CurrentTeacher, get_current_teacher
from app.modules.teacher_memory import (
    TeacherMemory,
    TeacherMemoryCommand,
    TeacherMemoryConflict,
    TeacherMemoryError,
    TeacherMemoryProfile,
)


router = APIRouter(prefix="/teacher-memory", tags=["teacher-memory"])


@lru_cache
def get_teacher_memory() -> TeacherMemory:
    return TeacherMemory(database_path=get_settings().teacher_memory_db)


@router.get("/profile", response_model=TeacherMemoryProfile)
def get_profile(
    teacher: CurrentTeacher = Depends(get_current_teacher),
    memory: TeacherMemory = Depends(get_teacher_memory),
) -> TeacherMemoryProfile:
    return memory.profile(owner_id=teacher.teacher_id)


@router.post("/profile", response_model=TeacherMemoryProfile)
def apply_profile_command(
    command: TeacherMemoryCommand,
    teacher: CurrentTeacher = Depends(get_current_teacher),
    memory: TeacherMemory = Depends(get_teacher_memory),
) -> TeacherMemoryProfile:
    try:
        return memory.apply(command, owner_id=teacher.teacher_id)
    except TeacherMemoryConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except TeacherMemoryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
