"""教师可信 Search Agent API（Prompt 3）。

- POST /api/v1/agent/search                发起搜索（同步返回 grounded 结果）
- GET  /api/v1/agent/search/{run_id}       读取 run 记录
- GET  /api/v1/agent/search/{run_id}/stream SSE（最终事件携带 SearchAgentResponse）
- POST /api/v1/agent/search/{run_id}/cancel 取消 run

边界：
- MATH_AI_SEARCH_AGENT_ENABLED 默认 false：关闭时返回结构化 FEATURE_DISABLED，
  传统搜索页面不受影响。
- 前端只调用 FastAPI，绝不直接调用 apps/agent。
- 本路由不 import DeepSeek Harness；只依赖 TeacherAgentRuntime 边界。
"""

from __future__ import annotations

import json
import uuid
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.modules.search_agent import SearchAgentPipeline, SearchAgentResponse, SearchAgentRunRecord

router = APIRouter(prefix="/agent/search", tags=["search-agent"])

_RUNS: dict[str, SearchAgentRunRecord] = {}


class SearchAgentSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    session_id: str | None = Field(default=None, max_length=160)


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


def _require_run(run_id: str) -> SearchAgentRunRecord:
    _require_feature()
    record = _RUNS.get(run_id)
    if record is None:
        raise _SearchAgentHttpError(404, "RUN_NOT_FOUND", "run 不存在", run_id)
    return record


@router.post("", response_model=SearchAgentResponse)
async def search(body: SearchAgentSearchRequest) -> SearchAgentResponse:
    _require_feature()
    request_id = f"req_{uuid.uuid4().hex}"
    response = await get_search_agent_pipeline().run(
        body.query, session_id=body.session_id, request_id=request_id
    )
    record = SearchAgentRunRecord(
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
    _RUNS[record.run_id] = record
    return response


@router.get("/{run_id}")
async def get_run(run_id: str) -> dict[str, Any]:
    record = _require_run(run_id)
    return record.model_dump(mode="json")


@router.get("/{run_id}/stream")
async def stream_run(run_id: str) -> StreamingResponse:
    record = _require_run(run_id)
    pipeline = get_search_agent_pipeline()

    async def events():
        async for event in pipeline.stream(
            record.raw_query, session_id=record.session_id, request_id=record.request_id
        ):
            yield f"data: {json.dumps(event.model_dump(mode='json'), ensure_ascii=False)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@router.post("/{run_id}/cancel")
async def cancel_run(run_id: str) -> dict[str, Any]:
    _require_run(run_id)
    return await get_search_agent_pipeline().cancel(run_id)