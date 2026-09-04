"""Public, identity-bound entry for explicitly consented private retrieval."""

from functools import lru_cache

from fastapi import APIRouter, Depends

from app.core.identity import CurrentTeacher, get_current_teacher
from app.core.agent_sessions import agent_sessions
from app.modules.private_library_agent import (
    PrivateLibraryAgentCommand,
    PrivateLibraryAgentResponse,
    PrivateLibraryAgentWorkflow,
)

router = APIRouter(prefix="/agent/private-library", tags=["private-library-agent"])


@lru_cache
def get_private_library_agent_workflow() -> PrivateLibraryAgentWorkflow:
    return PrivateLibraryAgentWorkflow()


@router.post("/search", response_model=PrivateLibraryAgentResponse)
async def search_private_library(
    command: PrivateLibraryAgentCommand,
    teacher: CurrentTeacher = Depends(get_current_teacher),
) -> PrivateLibraryAgentResponse:
    command = command.model_copy(update={"session_id": agent_sessions.resolve(
        owner_id=teacher.teacher_id, workflow="library", client_session_id=command.session_id,
    )})
    return await get_private_library_agent_workflow().run(command, owner_id=teacher.teacher_id)
