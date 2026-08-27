from __future__ import annotations

import asyncio
import time
import uuid
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.config import get_settings
from app.core.identity import CurrentTeacher, get_current_teacher
from app.modules.math_verifier import MathVerifier
from app.modules.background_jobs import BackgroundJobRegistry, BackgroundJobView
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
AUTHORING_JOB_KIND = "question_authoring"


def _agent_error_message(error: object) -> str:
    """Normalize the Agent boundary without leaking Python representation errors."""
    if isinstance(error, dict):
        value = error.get("message") or error.get("detail")
        return value.strip() if isinstance(value, str) and value.strip() else "候选题未通过闭环审核"
    value = getattr(error, "message", None)
    return value.strip() if isinstance(value, str) and value.strip() else "候选题未通过闭环审核"


@lru_cache
def get_question_authoring_job_registry() -> BackgroundJobRegistry:
    return BackgroundJobRegistry()


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


@router.post(
    "/jobs",
    response_model=BackgroundJobView,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_question_authoring_job(
    command: QuestionAuthoringAgentCommand,
    request: Request,
    teacher: CurrentTeacher = Depends(get_current_teacher),
    library: PersonalQuestionLibrary = Depends(get_personal_question_library),
) -> BackgroundJobView:
    """Start an owner-scoped authoring loop that survives page navigation.

    Content-quality failures are not a user-facing terminal state: the loop asks
    the workflow for a wholly new candidate. Only an explicit out-of-high-school
    scope result is allowed to stop without a deliverable.
    """
    settings = get_settings()
    if not settings.question_authoring_agent_enabled:
        raise HTTPException(status_code=503, detail="辅助命题 Agent 当前未启用")
    progress_id = command.progress_id or f"qap_{uuid.uuid4().hex}"
    command = command.model_copy(update={"progress_id": progress_id})
    try:
        get_question_authoring_progress_registry().register(
            progress_id, owner_id=teacher.teacher_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    request_id_prefix = request.headers.get("X-Request-Id", "").strip()[:120]
    workflow = get_question_authoring_agent_workflow()
    owner_id = teacher.teacher_id

    def runner(report) -> dict:
        attempt = 0
        while True:
            attempt += 1
            report(attempt, 0, "正在命制并闭环审核" if attempt == 1 else f"第 {attempt} 轮重新命题中")
            try:
                response = asyncio.run(
                    workflow.run(
                        command,
                        owner_id=owner_id,
                        request_id=(request_id_prefix or "req") + f"_{uuid.uuid4().hex}",
                    )
                )
            except Exception as exc:  # transient/provider faults stay inside the job loop
                message = str(exc)
                if "超出高中数学范围" in message or "大学" in message:
                    raise RuntimeError(message) from exc
                report(attempt, 0, "本轮未完成，正在自动重新命题")
                time.sleep(min(2 ** min(attempt - 1, 4), 15))
                continue
            if response.status == "ok" and response.draft is not None:
                # This checkpoint is the cancellation boundary before the durable
                # private-library write. A cancelled model call never stages a draft.
                report(attempt, attempt, "正在建立私有草稿")
                get_question_authoring_progress_registry().update(progress_id, "staging")
                library.stage_generated_draft(response.draft, owner_id=owner_id)
                report(attempt, attempt, "完整题目与解析已生成")
                return {
                    "draft_id": response.draft.draft_id,
                    "request_id": response.request_id,
                }
            message = _agent_error_message(response.error)
            if "超出高中数学范围" in message or "大学" in message:
                raise RuntimeError(message)
            report(attempt, 0, "候选题未通过闭环审核，正在重新出题")
            time.sleep(min(2 ** min(attempt - 1, 4), 15))

    return get_question_authoring_job_registry().start(
        kind=AUTHORING_JOB_KIND,
        subject_id=progress_id,
        owner_id=teacher.teacher_id,
        runner=runner,
    )


@router.get("/jobs/latest", response_model=BackgroundJobView)
async def get_latest_question_authoring_job(
    teacher: CurrentTeacher = Depends(get_current_teacher),
) -> BackgroundJobView:
    try:
        return get_question_authoring_job_registry().latest(
            owner_id=teacher.teacher_id, kind=AUTHORING_JOB_KIND
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="没有可恢复的命题任务") from exc


@router.get("/jobs/{job_id}", response_model=BackgroundJobView)
async def get_question_authoring_job(
    job_id: str,
    teacher: CurrentTeacher = Depends(get_current_teacher),
) -> BackgroundJobView:
    try:
        return get_question_authoring_job_registry().get(
            job_id, owner_id=teacher.teacher_id
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="命题任务不存在或已过期") from exc


@router.post("/jobs/{job_id}/cancel", response_model=BackgroundJobView)
async def cancel_question_authoring_job(
    job_id: str,
    teacher: CurrentTeacher = Depends(get_current_teacher),
) -> BackgroundJobView:
    try:
        return get_question_authoring_job_registry().cancel(
            job_id, owner_id=teacher.teacher_id
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="命题任务不存在或已过期") from exc


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
