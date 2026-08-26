from __future__ import annotations

import uuid
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.config import get_settings
from app.core.identity import CurrentTeacher, get_current_teacher
from app.modules.math_verifier import MathVerifier
from app.modules.question_authoring import (
    DeepSeekQuestionAuthoringProvider,
    QuestionAuthoring,
)
from app.modules.question_authoring_agent import (
    QuestionAuthoringAgentCommand,
    QuestionAuthoringAgentResponse,
    QuestionAuthoringAgentWorkflow,
    QuestionAuthoringProgressSnapshot,
    get_question_authoring_progress_registry,
)
from app.modules.personal_question_library import PersonalQuestionLibrary
from app.routes.curriculum import _catalog_for_path
from app.routes.model_operations import get_model_operations_registry
from app.routes.personal_question_library import get_personal_question_library


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
        math_verifier=MathVerifier(),
    )


@lru_cache
def get_question_authoring_agent_workflow() -> QuestionAuthoringAgentWorkflow:
    return QuestionAuthoringAgentWorkflow()


@router.post("/draft", response_model=QuestionAuthoringAgentResponse)
async def create_question_authoring_draft(
    command: QuestionAuthoringAgentCommand,
    request: Request,
    teacher: CurrentTeacher = Depends(get_current_teacher),
    library: PersonalQuestionLibrary = Depends(get_personal_question_library),
) -> QuestionAuthoringAgentResponse:
    settings = get_settings()
    if not settings.question_authoring_agent_enabled:
        raise HTTPException(status_code=503, detail="辅助命题 Agent 当前未启用")
    if not command.progress_id:
        command = command.model_copy(update={"progress_id": f"qap_{uuid.uuid4().hex}"})
    try:
        get_question_authoring_progress_registry().register(
            command.progress_id,
            owner_id=teacher.teacher_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    request_id = request.headers.get("X-Request-Id", "").strip()[:160]
    response = await get_question_authoring_agent_workflow().run(
        command,
        owner_id=teacher.teacher_id,
        request_id=request_id or f"req_{uuid.uuid4().hex}",
    )
    if response.status == "ok" and response.draft is not None:
        get_question_authoring_progress_registry().update(
            command.progress_id,
            "staging",
        )
        library.stage_generated_draft(response.draft, owner_id=teacher.teacher_id)
    return response


@router.get("/progress/{progress_id}", response_model=QuestionAuthoringProgressSnapshot)
async def get_question_authoring_progress(
    progress_id: str,
    teacher: CurrentTeacher = Depends(get_current_teacher),
) -> QuestionAuthoringProgressSnapshot:
    try:
        return get_question_authoring_progress_registry().snapshot(
            progress_id,
            owner_id=teacher.teacher_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="命题进度不存在或已过期") from exc
