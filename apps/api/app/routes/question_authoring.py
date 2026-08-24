from __future__ import annotations

import uuid
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.config import get_settings
from app.core.identity import CurrentTeacher, get_current_teacher
from app.modules.question_authoring import (
    DeepSeekQuestionAuthoringProvider,
    QuestionAuthoring,
)
from app.modules.question_authoring_agent import (
    QuestionAuthoringAgentCommand,
    QuestionAuthoringAgentResponse,
    QuestionAuthoringAgentWorkflow,
)
from app.routes.curriculum import _catalog_for_path
from app.routes.model_operations import get_model_operations_registry


router = APIRouter(prefix="/agent/question-authoring", tags=["question-authoring-agent"])


@lru_cache
def get_question_authoring() -> QuestionAuthoring:
    settings = get_settings()
    use_deepseek = settings.question_authoring_provider == "deepseek" or (
        settings.question_authoring_provider == "auto" and bool(settings.deepseek_api_key)
    )
    provider = (
        DeepSeekQuestionAuthoringProvider(
            api_key=settings.deepseek_api_key,
            model=settings.deepseek_model,
            base_url=settings.deepseek_base_url,
            timeout_seconds=settings.deepseek_timeout_seconds,
            recorder=get_model_operations_registry(),
        )
        if use_deepseek
        else None
    )
    return QuestionAuthoring(
        curriculum=_catalog_for_path(str(settings.curriculum_csv.resolve())),
        provider=provider,
    )


@lru_cache
def get_question_authoring_agent_workflow() -> QuestionAuthoringAgentWorkflow:
    return QuestionAuthoringAgentWorkflow()


@router.post("/draft", response_model=QuestionAuthoringAgentResponse)
async def create_question_authoring_draft(
    command: QuestionAuthoringAgentCommand,
    request: Request,
    teacher: CurrentTeacher = Depends(get_current_teacher),
) -> QuestionAuthoringAgentResponse:
    settings = get_settings()
    if not settings.question_authoring_agent_enabled:
        raise HTTPException(status_code=503, detail="辅助命题 Agent 当前未启用")
    request_id = request.headers.get("X-Request-Id", "").strip()[:160]
    return await get_question_authoring_agent_workflow().run(
        command,
        owner_id=teacher.teacher_id,
        request_id=request_id or f"req_{uuid.uuid4().hex}",
    )
