"""Public FastAPI entry for the M5 Solve workflow.

The route depends only on ``SolveAgentWorkflow`` and product models. It never
imports DeepSeek Harness and never exposes raw Tool input/output to browsers.
"""

from __future__ import annotations

import json
import time
import uuid
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from app.agent_runtime import TeacherAgentEvent, TeacherAgentEventType
from app.core.config import get_settings
from app.core.agent_sessions import agent_sessions
from app.core.identity import CurrentTeacher, get_current_teacher
from app.modules.solve_agent import (
    SolveAgentCommand,
    SolveAgentResponse,
    SolveAgentRunRecord,
    SolveAgentWorkflow,
)
from app.modules.beta_validation.dependencies import get_beta_validation_facts
from app.modules.beta_validation.facts import BetaValidationFacts

router = APIRouter(prefix="/agent/solve", tags=["solve-agent"])

_RUNS: dict[str, SolveAgentRunRecord] = {}


class _ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str


class _SolveAgentHttpError(Exception):
    def __init__(self, status_code: int, code: str, message: str, request_id: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.request_id = request_id


async def solve_agent_error_handler(
    _request: Request, exc: _SolveAgentHttpError
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
def get_solve_agent_workflow() -> SolveAgentWorkflow:
    return SolveAgentWorkflow()


def _require_feature() -> None:
    if not get_settings().solve_agent_enabled:
        raise _SolveAgentHttpError(
            404,
            "FEATURE_DISABLED",
            "Solve Agent 未启用（MATH_AI_SOLVE_AGENT_ENABLED=false）",
            "req_feature_gate",
        )


def _require_run(run_id: str, *, owner_id: str) -> SolveAgentRunRecord:
    _require_feature()
    record = _RUNS.get(run_id)
    if record is None or record.owner_id != owner_id:
        raise _SolveAgentHttpError(404, "RUN_NOT_FOUND", "run 不存在", run_id)
    return record


def _store_response(command: SolveAgentCommand, response: SolveAgentResponse, *, owner_id: str) -> None:
    if not response.run_id:
        response.run_id = f"run_{uuid.uuid4().hex}"
    previous = _RUNS.get(response.run_id)
    if previous is not None and previous.owner_id != owner_id:
        raise _SolveAgentHttpError(409, "RUN_CONFLICT", "任务编号冲突，请重试", response.request_id)
    _RUNS[response.run_id] = SolveAgentRunRecord(
        owner_id=owner_id,
        run_id=response.run_id,
        request_id=response.request_id,
        session_id=response.session_id,
        status=response.status,
        command=command,
        response=response,
        error=response.error,
        finished_at=time.time(),
    )


@router.post("", response_model=SolveAgentResponse)
async def solve(
    command: SolveAgentCommand,
    current_teacher: CurrentTeacher = Depends(get_current_teacher),
    validation_facts: BetaValidationFacts = Depends(get_beta_validation_facts),
) -> SolveAgentResponse:
    _require_feature()
    command = command.model_copy(update={"session_id": agent_sessions.resolve(
        owner_id=current_teacher.teacher_id, workflow="solve", client_session_id=command.session_id,
    )})
    response = await get_solve_agent_workflow().run(
        command,
        owner_id=current_teacher.teacher_id,
        request_id=f"req_{uuid.uuid4().hex}",
    )
    _store_response(command, response, owner_id=current_teacher.teacher_id)
    if response.status == "ok" and response.run_id and response.solution is not None:
        validation_facts.record_checkpoint(
            owner_id=current_teacher.teacher_id,
            fact="solve_completed",
            task_ref=response.run_id,
            duration_ms=response.duration_ms,
            trust_tier=response.solution.confidence_status,
            tool_call_count=response.tool_call_count,
        )
    elif response.run_id and response.tool_call_count:
        validation_facts.record_tool_failure(
            owner_id=current_teacher.teacher_id,
            workflow="solve",
            task_ref=response.run_id,
            tool_call_count=response.tool_call_count,
        )
    return response


def _record_stream_event(
    command: SolveAgentCommand,
    event: TeacherAgentEvent,
    *,
    owner_id: str,
) -> SolveAgentResponse | None:
    if not event.run_id:
        return None
    record = _RUNS.get(event.run_id)
    if record is not None and record.owner_id != owner_id:
        raise _SolveAgentHttpError(409, "RUN_CONFLICT", "任务编号冲突，请重试", event.request_id)
    if record is None:
        record = SolveAgentRunRecord(
            owner_id=owner_id,
            run_id=event.run_id,
            request_id=event.request_id,
            session_id=event.session_id,
            status="pending",
            command=command,
        )
        _RUNS[event.run_id] = record
    if event.type == TeacherAgentEventType.RUN_STARTED:
        record.status = "running"
        return None
    if event.type == TeacherAgentEventType.RUN_COMPLETED:
        raw = event.data.get("solve_response")
        if isinstance(raw, dict):
            response = SolveAgentResponse.model_validate(raw)
            record.status = response.status
            record.response = response
            record.error = response.error
        else:
            record.status = "error"
            record.error = {
                "code": "INTERNAL_ERROR",
                "message": "解题终态缺少结构化结果",
                "request_id": event.request_id,
            }
        record.finished_at = time.time()
        return record.response
    if event.type in {TeacherAgentEventType.RUN_FAILED, TeacherAgentEventType.RUN_CANCELLED}:
        record.status = (
            "cancelled" if event.type == TeacherAgentEventType.RUN_CANCELLED else "error"
        )
        raw_error = event.data.get("error")
        record.error = raw_error if isinstance(raw_error, dict) else None
        record.finished_at = time.time()
    return None


@router.post("/stream")
async def stream_solve(
    command: SolveAgentCommand,
    current_teacher: CurrentTeacher = Depends(get_current_teacher),
    validation_facts: BetaValidationFacts = Depends(get_beta_validation_facts),
) -> StreamingResponse:
    _require_feature()
    command = command.model_copy(update={"session_id": agent_sessions.resolve(
        owner_id=current_teacher.teacher_id, workflow="solve", client_session_id=command.session_id,
    )})
    request_id = f"req_{uuid.uuid4().hex}"
    workflow = get_solve_agent_workflow()

    async def events():
        async for event in workflow.stream(
            command,
            owner_id=current_teacher.teacher_id,
            request_id=request_id,
        ):
            completed = _record_stream_event(
                command, event, owner_id=current_teacher.teacher_id
            )
            if (
                completed is not None
                and completed.status == "ok"
                and completed.run_id
                and completed.solution is not None
            ):
                validation_facts.record_checkpoint(
                    owner_id=current_teacher.teacher_id,
                    fact="solve_completed",
                    task_ref=completed.run_id,
                    duration_ms=completed.duration_ms,
                    trust_tier=completed.solution.confidence_status,
                    tool_call_count=completed.tool_call_count,
                )
            elif completed is not None and completed.run_id and completed.tool_call_count:
                validation_facts.record_tool_failure(
                    owner_id=current_teacher.teacher_id,
                    workflow="solve",
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
    return _require_run(run_id, owner_id=teacher.teacher_id).model_dump(mode="json")


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
        if record.response is not None and record.response.status == "ok":
            terminal = TeacherAgentEvent(
                type=TeacherAgentEventType.RUN_COMPLETED,
                run_id=record.run_id,
                session_id=record.session_id,
                request_id=record.request_id,
                data={"solve_response": record.response.model_dump(mode="json")},
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
        return {"run_id": run_id, "status": record.status, "error": record.error}
    outcome = await get_solve_agent_workflow().cancel(run_id)
    if outcome.get("status") == "cancelled":
        record.status = "cancelled"
        record.error = outcome.get("error")
        record.finished_at = time.time()
    return outcome


@router.post("/{run_id}/resume", response_model=SolveAgentResponse)
async def resume_run(
    run_id: str,
    current_teacher: CurrentTeacher = Depends(get_current_teacher),
) -> SolveAgentResponse:
    record = _require_run(run_id, owner_id=current_teacher.teacher_id)
    if record.status not in {"error", "cancelled"}:
        raise _SolveAgentHttpError(
            409,
            "RUN_NOT_RESUMABLE",
            "只有失败或已取消的 Solve run 可以恢复",
            record.request_id,
        )
    if not record.session_id:
        raise _SolveAgentHttpError(
            409,
            "SESSION_NOT_AVAILABLE",
            "该 run 没有可恢复的 Agent session",
            record.request_id,
        )
    response = await get_solve_agent_workflow().resume(
        record.command,
        session_id=record.session_id,
        owner_id=current_teacher.teacher_id,
        request_id=f"req_{uuid.uuid4().hex}",
    )
    _store_response(record.command, response, owner_id=current_teacher.teacher_id)
    return response
