"""Agent -> FastAPI 的内部只读 Tool Gateway。

安全边界（Prompt 2 强制）：
- internal only + versioned：/internal/agent-tools/v1/...
- include_in_schema=False：不进入公开 API 文档。
- machine-to-machine authentication：Authorization: Bearer <MATH_AI_TOOL_GATEWAY_TOKEN>。
- 缺失/错误 token 一律拒绝；token 只来自环境变量。
- Agent 只能通过本 Gateway 访问业务能力，绝不能直接碰数据库。
- 错误响应是结构化产品词汇表，绝不包含 traceback / 本地路径 / secret。
"""

from __future__ import annotations

import asyncio
import hmac
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.modules.math_verifier import MathVerifier
from app.modules.question_bank import QuestionBankError
from app.modules.question_similarity import QuestionSimilarityRegistry
from app.routes.curriculum import _catalog_for_path
from app.routes.questions import get_question_bank, get_question_quality_workflow
from app.routes.question_similarity import get_question_similarity_registry

logger = logging.getLogger("math_ai.internal_agent_tools")

router = APIRouter(
    prefix="/internal/agent-tools/v1",
    tags=["internal-agent-tools"],
    include_in_schema=False,
)

SEARCH_LIMIT_MAX = 20
SIMILAR_LIMIT_MAX = 20


class GatewayErrorResponse(BaseModel):
    code: str
    message: str
    request_id: str


class _GatewayHttpError(Exception):
    def __init__(self, status_code: int, code: str, message: str, request_id: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.request_id = request_id


class _Unauthorized(_GatewayHttpError):
    def __init__(self, message: str) -> None:
        super().__init__(401, "TOOL_UNAUTHORIZED", message, "req_unknown")


def _require_tool_gateway_token(
    authorization: str | None = Header(default=None),
) -> None:
    """M2M 认证：缺失/错误 token 一律拒绝，token 只来自环境。"""
    settings = get_settings()
    expected = settings.tool_gateway_token
    if not expected:
        logger.error("tool_gateway_token_not_configured")
        raise _Unauthorized("internal tool gateway 未配置 service token")
    if not authorization or not authorization.startswith("Bearer "):
        raise _Unauthorized("缺少 service token")
    provided = authorization[len("Bearer ") :].strip()
    if not provided or not hmac.compare_digest(provided, expected):
        raise _Unauthorized("service token 不正确")


def _request_id_from(request: Request) -> str:
    value = request.headers.get("X-Request-Id", "").strip()
    return value[:160] or f"req_{uuid.uuid4().hex}"


async def _run_with_timeout(request: Request, fn: Any, *args: Any, **kwargs: Any) -> Any:
    """同步业务服务在受控超时内执行；超时返回 TOOL_TIMEOUT，不泄漏 traceback。"""
    timeout = get_settings().tool_gateway_timeout_seconds
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(fn, *args, **kwargs), timeout=timeout
        )
    except asyncio.TimeoutError:
        request_id = _request_id_from(request)
        raise _GatewayHttpError(
            504, "TOOL_TIMEOUT", "工具调用超时", request_id
        ) from None





# ---------------------------------------------------------------------------
# Request / response contracts
# ---------------------------------------------------------------------------

class SearchQuestionsRequest(BaseModel):
    query: str = Field(default="", max_length=200)
    chapter: str | None = Field(default=None, max_length=120)
    difficulty: int | None = Field(default=None, ge=1, le=5)
    knowledge_point_id: str | None = Field(default=None, max_length=160)
    limit: int = Field(default=10, ge=1, le=SEARCH_LIMIT_MAX)


class SearchQuestionItem(BaseModel):
    question_id: str
    stem: str
    question_type: str
    knowledge_points: list[str]
    difficulty: int
    verification_status: str
    source_status: str
    visibility: str


class SearchQuestionsResponse(BaseModel):
    items: list[SearchQuestionItem]
    total: int
    truncated: bool
    query_interpretation: dict[str, Any] | None = None
    request_id: str


class GetQuestionRequest(BaseModel):
    question_id: str = Field(min_length=1, max_length=160)


class GetQuestionResponse(BaseModel):
    question_id: str
    stem: str
    question_type: str
    answer: str | None
    solution_steps: list[str]
    verification_status: str
    visibility: str
    source_status: str
    request_id: str


class FindSimilarQuestionsRequest(BaseModel):
    question_id: str = Field(min_length=1, max_length=160)
    limit: int = Field(default=10, ge=1, le=SIMILAR_LIMIT_MAX)


class SimilarQuestionItem(BaseModel):
    question_id: str
    stem: str
    relation: str
    confidence: float
    status: str


class FindSimilarQuestionsResponse(BaseModel):
    items: list[SimilarQuestionItem]
    total: int
    truncated: bool
    request_id: str


class VerifyQuestionRequest(BaseModel):
    question_id: str = Field(min_length=1, max_length=160)


class VerifyQuestionResponse(BaseModel):
    question_id: str
    stored_status: str
    capability: str
    computed_answer: str | None
    method: str | None
    details: list[str]
    fresh_verification: dict[str, Any] | None = None
    request_id: str


class GetCurriculumNodeRequest(BaseModel):
    node_id: str = Field(min_length=1, max_length=160)


class GetCurriculumNodeResponse(BaseModel):
    node_id: str
    parent_id: str | None
    volume: str
    node_type: str
    code: str
    name: str
    description: str
    knowledge_points: list[str] = Field(default_factory=list)
    request_id: str


# ---------------------------------------------------------------------------
# Endpoints（全部只读）
# ---------------------------------------------------------------------------

@router.post("/search-questions", response_model=SearchQuestionsResponse)
async def search_questions(
    body: SearchQuestionsRequest,
    request: Request,
    _token: None = Depends(_require_tool_gateway_token),
) -> SearchQuestionsResponse:
    request_id = _request_id_from(request)
    try:
        page = await _run_with_timeout(
            request,
            get_question_bank().search,
            query=body.query,
            chapter=body.chapter,
            difficulty=body.difficulty,
            knowledge_point_id=body.knowledge_point_id,
            page=1,
            page_size=body.limit,
            library_state="active",
            usage_scope="teacher",
            usage_owner_id="owner_teacher",
        )
    except QuestionBankError as exc:
        raise _GatewayHttpError(
            422, "TOOL_VALIDATION_ERROR", str(exc), request_id
        ) from exc
    except _GatewayHttpError:
        raise
    except Exception:
        logger.exception("search_questions_failed", extra={"request_id": request_id})
        raise _GatewayHttpError(
            500, "TOOL_EXECUTION_ERROR", "题目搜索失败", request_id
        ) from None
    items = [
        SearchQuestionItem(
            question_id=item.question_id,
            stem=item.stem_plain[:600],
            question_type=item.question_type,
            knowledge_points=item.knowledge_point_ids,
            difficulty=item.difficulty,
            verification_status=item.verification_status,
            source_status=item.license_status,
            visibility=item.visibility,
        )
        for item in page.items
    ]
    return SearchQuestionsResponse(
        items=items,
        total=page.total,
        truncated=page.total > len(items),
        query_interpretation={"query": body.query.strip()} if body.query.strip() else None,
        request_id=request_id,
    )


@router.post("/get-question", response_model=GetQuestionResponse)
async def get_question(
    body: GetQuestionRequest,
    request: Request,
    _token: None = Depends(_require_tool_gateway_token),
) -> GetQuestionResponse:
    request_id = _request_id_from(request)
    try:
        detail = await _run_with_timeout(
            request, get_question_bank().get_question, body.question_id
        )
    except KeyError:
        raise _GatewayHttpError(404, "TOOL_NOT_FOUND", "题目不存在", request_id) from None
    except _GatewayHttpError:
        raise
    except Exception:
        logger.exception("get_question_failed", extra={"request_id": request_id})
        raise _GatewayHttpError(500, "TOOL_EXECUTION_ERROR", "题目读取失败", request_id) from None
    raw = detail.raw or {}
    solution_steps = [str(step) for step in (raw.get("solutions") or [])][:20]
    return GetQuestionResponse(
        question_id=detail.question_id,
        stem=detail.stem_plain[:2000],
        question_type=detail.question_type,
        answer=detail.answer_value,
        solution_steps=solution_steps,
        verification_status=detail.verification_status,
        visibility=detail.visibility,
        source_status=detail.license_status,
        request_id=request_id,
    )


@router.post("/find-similar-questions", response_model=FindSimilarQuestionsResponse)
async def find_similar_questions(
    body: FindSimilarQuestionsRequest,
    request: Request,
    _token: None = Depends(_require_tool_gateway_token),
) -> FindSimilarQuestionsResponse:
    request_id = _request_id_from(request)
    try:
        registry: QuestionSimilarityRegistry = await _run_with_timeout(
            request, get_question_similarity_registry
        )
        workspace = await _run_with_timeout(request, registry.workspace, limit=1000)
        await _run_with_timeout(
            request, get_question_bank().get_question, body.question_id
        )
    except KeyError:
        raise _GatewayHttpError(404, "TOOL_NOT_FOUND", "题目不存在", request_id) from None
    except _GatewayHttpError:
        raise
    except Exception:
        logger.exception("find_similar_failed", extra={"request_id": request_id})
        raise _GatewayHttpError(500, "TOOL_EXECUTION_ERROR", "相似题查询失败", request_id) from None

    items: list[SimilarQuestionItem] = []
    for candidate in workspace.items:
        member_ids = {member.question_id for member in candidate.members}
        if body.question_id not in member_ids:
            continue
        relation = candidate.teacher_relation or candidate.suggested_relation
        for member in candidate.members:
            if member.question_id == body.question_id:
                continue
            items.append(
                SimilarQuestionItem(
                    question_id=member.question_id,
                    stem=member.stem_plain[:600],
                    relation=relation,
                    confidence=candidate.confidence,
                    status=candidate.status,
                )
            )
    total = len(items)
    return FindSimilarQuestionsResponse(
        items=items[: body.limit],
        total=total,
        truncated=total > body.limit,
        request_id=request_id,
    )


@router.post("/verify-question", response_model=VerifyQuestionResponse)
async def verify_question(
    body: VerifyQuestionRequest,
    request: Request,
    _token: None = Depends(_require_tool_gateway_token),
) -> VerifyQuestionResponse:
    request_id = _request_id_from(request)
    try:
        workspace = await _run_with_timeout(
            request, get_question_quality_workflow().inspect, body.question_id
        )
        detail = await _run_with_timeout(
            request, get_question_bank().get_question, body.question_id
        )
    except KeyError:
        raise _GatewayHttpError(404, "TOOL_NOT_FOUND", "题目不存在", request_id) from None
    except _GatewayHttpError:
        raise
    except Exception:
        logger.exception("verify_question_failed", extra={"request_id": request_id})
        raise _GatewayHttpError(500, "TOOL_EXECUTION_ERROR", "数学验证失败", request_id) from None

    verification = workspace.verification
    fresh: dict[str, Any] | None = None
    raw = detail.raw or {}
    spec = raw.get("verification_spec")
    if isinstance(spec, dict) and spec.get("rule"):
        try:
            candidate = {
                "question_id": body.question_id,
                "verification_spec": spec,
                "options": raw.get("options") or [],
                "source_answer": detail.answer_value,
            }
            fresh = MathVerifier().verify(candidate).model_dump(mode="json")
        except Exception:
            logger.exception(
                "verify_question_recompute_failed", extra={"request_id": request_id}
            )
    return VerifyQuestionResponse(
        question_id=body.question_id,
        stored_status=verification.status,
        capability=verification.capability,
        computed_answer=verification.computed_answer,
        method=verification.method,
        details=verification.details,
        fresh_verification=fresh,
        request_id=request_id,
    )


@router.post("/get-curriculum-node", response_model=GetCurriculumNodeResponse)
async def get_curriculum_node(
    body: GetCurriculumNodeRequest,
    request: Request,
    _token: None = Depends(_require_tool_gateway_token),
) -> GetCurriculumNodeResponse:
    request_id = _request_id_from(request)
    settings = get_settings()
    try:
        catalog = await _run_with_timeout(
            request, _catalog_for_path, str(settings.curriculum_csv.resolve())
        )
        node = await _run_with_timeout(request, catalog.get_node, body.node_id)
    except KeyError:
        raise _GatewayHttpError(
            404, "TOOL_NOT_FOUND", "教材知识点不存在", request_id
        ) from None
    except _GatewayHttpError:
        raise
    except Exception:
        logger.exception("get_curriculum_node_failed", extra={"request_id": request_id})
        raise _GatewayHttpError(500, "TOOL_EXECUTION_ERROR", "知识点读取失败", request_id) from None
    return GetCurriculumNodeResponse(
        node_id=node.node_id,
        parent_id=node.parent_id,
        volume=node.volume,
        node_type=node.node_type,
        code=node.code,
        name=node.name,
        description=node.description,
        knowledge_points=node.prerequisite_node_ids,
        request_id=request_id,
    )

async def gateway_error_handler(
    _request: Request, exc: _GatewayHttpError
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": GatewayErrorResponse(
                code=exc.code, message=exc.message, request_id=exc.request_id
            ).model_dump(mode="json")
        },
    )
