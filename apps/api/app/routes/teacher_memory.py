from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.core.identity import CurrentTeacher, get_current_teacher
from app.modules.teacher_memory import (
    TeacherMemory,
    TeacherMemoryCommand,
    TeacherMemoryConflict,
    TeacherMemoryError,
    TeacherMemoryProfile,
)
from app.modules.teacher_memory.dependencies import get_teacher_memory


router = APIRouter(prefix="/teacher-memory", tags=["teacher-memory"])


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
