from functools import lru_cache

from app.core.config import get_settings
from app.modules.teacher_memory.memory import TeacherMemory


@lru_cache
def get_teacher_memory() -> TeacherMemory:
    return TeacherMemory(database_path=get_settings().teacher_memory_db)
