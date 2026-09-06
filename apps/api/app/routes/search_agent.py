"""教师可信 Search Agent API（Prompt 3）。

- POST /api/v1/agent/search                发起搜索（同步返回 grounded 结果）
- POST /api/v1/agent/search/stream         单次真实执行的 SSE 主入口
- GET  /api/v1/agent/search/{run_id}       读取 run 记录
- GET  /api/v1/agent/search/{run_id}/stream 读取已保存终态的 SSE 快照（不重新执行）
- POST /api/v1/agent/search/{run_id}/cancel 取消 run

边界：
- MATH_AI_SEARCH_AGENT_ENABLED 默认 false：关闭时返回结构化 FEATURE_DISABLED，
  传统搜索页面不受影响。
- 前端只调用 FastAPI，绝不直接调用 apps/agent。
- 本路由不 import DeepSeek Harness；只依赖 TeacherAgentRuntime 边界。
"""

from __future__ import annotations

import json
import time
import uuid
from functools import lru_cache
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.identity import CurrentTeacher, get_current_teacher
from app.core.agent_sessions import agent_sessions
from app.agent_runtime import TeacherAgentEvent, TeacherAgentEventType
from app.modules.search_agent import SearchAgentPipeline, SearchAgentResponse, SearchAgentRunRecord
from app.modules.beta_validation.dependencies import get_beta_validation_facts
from app.modules.beta_validation.facts import BetaValidationFacts

router = APIRouter(prefix="/agent/search", tags=["search-agent"])

_RUNS: dict[str, SearchAgentRunRecord] = {}


class SearchAgentSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    session_id: str | None = Field(default=None, max_length=160)


class SearchResultSelectionCommand(BaseModel):
    question_id: str = Field(pattern=r"^[A-Za-z0-9_.:-]{1,160}$")


class SearchTaskDecisionCommand(BaseModel):
    decision: Literal["accepted", "rejected"]


class _ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str


class _SearchAgentHttpError(Exception):
    def __init__(self, status_code: int, code: str, message: str, request_id: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.request_id = request_id


async def search_agent_error_handler(
    _request: Request, exc: _SearchAgentHttpError
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": _ErrorBody(
                code=exc.code, message=exc.message, request_id=exc.request_id
            ).model_dump(mode="json")
        },
    )


@lru_cache
def get_search_agent_pipeline() -> SearchAgentPipeline:
    return SearchAgentPipeline()


def _feature_enabled() -> bool:
    return get_settings().search_agent_enabled


def _require_feature() -> None:
    if not _feature_enabled():
        raise _SearchAgentHttpError(
            404,
            "FEATURE_DISABLED",
            "Search Agent 未启用（MATH_AI_SEARCH_AGENT_ENABLED=false）",
            "req_feature_gate",
        )


def _require_run(run_id: str, *, owner_id: str) -> SearchAgentRunRecord:
    _require_feature()
    record = _RUNS.get(run_id)
    if record is None or record.owner_id != owner_id:
        raise _SearchAgentHttpError(404, "RUN_NOT_FOUND", "run 不存在", run_id)
    return record


def _require_completed_run(run_id: str, *, owner_id: str) -> SearchAgentRunRecord:
    record = _require_run(run_id, owner_id=owner_id)
    if record.status != "ok" or record.response is None:
        raise _SearchAgentHttpError(
            409,
            "RUN_NOT_COMPLETED",
            "只有已完成的搜索任务可以记录选择或反馈",
            record.request_id,
        )
    return record


@router.post("", response_model=SearchAgentResponse)
async def search(
    body: SearchAgentSearchRequest,
    teacher: CurrentTeacher = Depends(get_current_teacher),
    validation_facts: BetaValidationFacts = Depends(get_beta_validation_facts),
) -> SearchAgentResponse:
    _require_feature()
    body = body.model_copy(update={"session_id": agent_sessions.resolve(
        owner_id=teacher.teacher_id, workflow="search", client_session_id=body.session_id,
    )})
    request_id = f"req_{uuid.uuid4().hex}"
    response = await get_search_agent_pipeline().run(
        body.query, session_id=body.session_id, request_id=request_id
    )
    record = SearchAgentRunRecord(
        owner_id=teacher.teacher_id,
        run_id=response.run_id or f"run_{uuid.uuid4().hex}",
        request_id=request_id,
        session_id=response.session_id,
        status=response.status,
        raw_query=body.query,
        intent=response.intent,
        plan_summary=response.plan_summary,
        response=response,
        error=response.error,
        finished_at=None,
    )
    previous = _RUNS.get(record.run_id)
    if previous is not None and previous.owner_id != teacher.teacher_id:
        raise _SearchAgentHttpError(409, "RUN_CONFLICT", "任务编号冲突，请重试", request_id)
    _RUNS[record.run_id] = record
    if response.status == "ok":
        validation_facts.record_checkpoint(
            owner_id=teacher.teacher_id,
            fact="search_completed",
            task_ref=record.run_id,
            duration_ms=response.duration_ms,
            trust_tier="teacher_review_required",
            tool_call_count=response.tool_call_count,
        )
    elif response.tool_call_count:
        validation_facts.record_tool_failure(
            owner_id=teacher.teacher_id,
            workflow="search",
            task_ref=record.run_id,
            tool_call_count=response.tool_call_count,
        )
    return response


def _record_stream_event(
    body: SearchAgentSearchRequest,
    event: TeacherAgentEvent,
    *,
    owner_id: str,
) -> SearchAgentResponse | None:
    """Persist the observable run lifecycle before the event reaches the client."""
    if not event.run_id:
        return None
    record = _RUNS.get(event.run_id)
    if record is not None and record.owner_id != owner_id:
        raise _SearchAgentHttpError(409, "RUN_CONFLICT", "任务编号冲突，请重试", event.request_id)
    if record is None:
        record = SearchAgentRunRecord(
            owner_id=owner_id,
            run_id=event.run_id,
            request_id=event.request_id,
            session_id=event.session_id,
            status="pending",
            raw_query=body.query,
        )
        _RUNS[event.run_id] = record

    if event.type == TeacherAgentEventType.RUN_STARTED:
        record.status = "running"
        return None

    if event.type == TeacherAgentEventType.RUN_COMPLETED:
        raw_response = event.data.get("search_response")
        if isinstance(raw_response, dict):
            response = SearchAgentResponse.model_validate(raw_response)
            record.status = response.status
            record.intent = response.intent
            record.plan_summary = response.plan_summary
            record.response = response
            record.error = response.error
        else:
            record.status = "error"
            record.error = {
                "code": "INTERNAL_ERROR",
                "message": "搜索终态缺少结构化结果",
                "request_id": event.request_id,
            }
        record.finished_at = time.time()
        return record.response

    if event.type in {
        TeacherAgentEventType.RUN_FAILED,
        TeacherAgentEventType.RUN_CANCELLED,
    }:
        record.status = (
            "cancelled"
            if event.type == TeacherAgentEventType.RUN_CANCELLED
            else "error"
        )
        raw_error = event.data.get("error")
        record.error = raw_error if isinstance(raw_error, dict) else None
        record.finished_at = time.time()
    return None


@router.post("/stream")
async def stream_search(
    body: SearchAgentSearchRequest,
    teacher: CurrentTeacher = Depends(get_current_teacher),
    validation_facts: BetaValidationFacts = Depends(get_beta_validation_facts),
) -> StreamingResponse:
    """Run Search once and stream its real lifecycle; disconnect cancels that run."""
    _require_feature()
    body = body.model_copy(update={"session_id": agent_sessions.resolve(
        owner_id=teacher.teacher_id, workflow="search", client_session_id=body.session_id,
    )})
    request_id = f"req_{uuid.uuid4().hex}"
    pipeline = get_search_agent_pipeline()

    async def events():
        async for event in pipeline.stream(
            body.query,
            session_id=body.session_id,
            request_id=request_id,
        ):
            completed = _record_stream_event(
                body, event, owner_id=teacher.teacher_id
            )
            if completed is not None and completed.status == "ok" and completed.run_id:
                validation_facts.record_checkpoint(
                    owner_id=teacher.teacher_id,
                    fact="search_completed",
                    task_ref=completed.run_id,
                    duration_ms=completed.duration_ms,
                    trust_tier="teacher_review_required",
                    tool_call_count=completed.tool_call_count,
                )
            elif completed is not None and completed.run_id and completed.tool_call_count:
                validation_facts.record_tool_failure(
                    owner_id=teacher.teacher_id,
                    workflow="search",
                    task_ref=completed.run_id,
                    tool_call_count=completed.tool_call_count,
                )
            yield f"data: {json.dumps(event.model_dump(mode='json'), ensure_ascii=False)}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{run_id}")
async def get_run(run_id: str, teacher: CurrentTeacher = Depends(get_current_teacher)) -> dict[str, Any]:
    record = _require_run(run_id, owner_id=teacher.teacher_id)
    return record.model_dump(mode="json")


@router.post("/{run_id}/selection")
def select_search_result(
    run_id: str,
    command: SearchResultSelectionCommand,
    teacher: CurrentTeacher = Depends(get_current_teacher),
    validation_facts: BetaValidationFacts = Depends(get_beta_validation_facts),
) -> dict[str, str | int]:
    record = _require_completed_run(run_id, owner_id=teacher.teacher_id)
    if not any(
        item.question_id == command.question_id
        for item in record.response.results
    ):
        raise _SearchAgentHttpError(
            404,
            "SEARCH_RESULT_NOT_FOUND",
            "所选题目不属于本次搜索结果",
            record.request_id,
        )
    result = validation_facts.record_search_selection(
        owner_id=teacher.teacher_id,
        task_ref=record.run_id,
    )
    return {"state": result.state, "recorded_events": result.recorded_events}


@router.post("/{run_id}/decision")
def decide_search_task(
    run_id: str,
    command: SearchTaskDecisionCommand,
    teacher: CurrentTeacher = Depends(get_current_teacher),
    validation_facts: BetaValidationFacts = Depends(get_beta_validation_facts),
) -> dict[str, str | int]:
    record = _require_completed_run(run_id, owner_id=teacher.teacher_id)
    result = validation_facts.record_task_decision(
        owner_id=teacher.teacher_id,
        workflow="search",
        task_ref=record.run_id,
        decision=command.decision,
    )
    return {"state": result.state, "recorded_events": result.recorded_events}


@router.get("/{run_id}/stream")
async def stream_run(run_id: str, teacher: CurrentTeacher = Depends(get_current_teacher)) -> StreamingResponse:
    record = _require_run(run_id, owner_id=teacher.teacher_id)

    async def events():
        started = TeacherAgentEvent(
            type=TeacherAgentEventType.RUN_STARTED,
            run_id=record.run_id,
            session_id=record.session_id,
            request_id=record.request_id,
        )
        yield f"data: {json.dumps(started.model_dump(mode='json'), ensure_ascii=False)}\n\n"
        if record.response is not None:
            terminal = TeacherAgentEvent(
                type=TeacherAgentEventType.RUN_COMPLETED,
                run_id=record.run_id,
                session_id=record.session_id,
                request_id=record.request_id,
                data={"search_response": record.response.model_dump(mode="json")},
                sequence=1,
            )
            yield f"data: {json.dumps(terminal.model_dump(mode='json'), ensure_ascii=False)}\n\n"
        elif record.status in {"error", "cancelled"}:
            terminal = TeacherAgentEvent(
                type=(
                    TeacherAgentEventType.RUN_CANCELLED
                    if record.status == "cancelled"
                    else TeacherAgentEventType.RUN_FAILED
                ),
                run_id=record.run_id,
                session_id=record.session_id,
                request_id=record.request_id,
                data={"error": record.error},
                sequence=1,
            )
            yield f"data: {json.dumps(terminal.model_dump(mode='json'), ensure_ascii=False)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@router.post("/{run_id}/cancel")
async def cancel_run(run_id: str, teacher: CurrentTeacher = Depends(get_current_teacher)) -> dict[str, Any]:
    record = _require_run(run_id, owner_id=teacher.teacher_id)
    if record.status in {"ok", "error", "cancelled"}:
        return {
            "run_id": run_id,
            "status": record.status,
            "error": record.error,
        }
    outcome = await get_search_agent_pipeline().cancel(run_id)
    status = outcome.get("status")
    if status == "cancelled":
        record.status = "cancelled"
        record.error = outcome.get("error")
        record.finished_at = time.time()
    return outcome
