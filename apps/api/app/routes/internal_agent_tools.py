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
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import get_settings
from app.modules.math_verifier import MathVerifier
from app.modules.private_library import (
    PrivateLibraryError,
    PrivateLibrarySearchItem,
    PrivateRetrievalConsentError,
    get_private_retrieval_grants,
)
from app.modules.question_bank import QuestionBankError
from app.modules.question_capture import (
    QuestionCaptureError,
    QuestionSolveGrantError,
    get_question_solve_grants,
)
from app.modules.question_similarity import QuestionSimilarityRegistry
from app.modules.solution_assistant import (
    SolutionAssistantError,
    SolutionAssistantUnavailableError,
    SolutionAssistantVerificationError,
    SolutionProviderError,
    SolutionRequest,
    SolutionResult,
    SolutionVisualInput,
)
from app.routes.curriculum import _catalog_for_path
from app.routes.questions import get_question_bank, get_question_quality_workflow
from app.routes.question_similarity import get_question_similarity_registry
from app.routes.library import get_private_library
from app.routes.solutions import get_solution_assistant
from app.routes.question_capture import get_question_capture

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


async def _run_with_timeout(
    request: Request,
    fn: Any,
    *args: Any,
    timeout_seconds: float | None = None,
    **kwargs: Any,
) -> Any:
    """同步业务服务在受控超时内执行；超时返回 TOOL_TIMEOUT，不泄漏 traceback。"""
    timeout = timeout_seconds or get_settings().tool_gateway_timeout_seconds
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


class SolveQuestionRequest(BaseModel):
    question_text: str = Field(min_length=5, max_length=30000)
    solution_mode: Literal["standard", "alternative"] = "standard"
    teacher_instruction: str = Field(default="", max_length=2000)
    capture_grant: str | None = Field(default=None, min_length=20, max_length=200)


class SolveQuestionResponse(SolutionResult):
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


class InspectPrivateLibraryRequest(BaseModel):
    """No model-supplied owner selector is allowed at this seam."""

    model_config = ConfigDict(extra="forbid")


class InspectPrivateLibraryResponse(BaseModel):
    total: int
    pending_review: int
    confirmed: int
    needs_ocr: int
    trashed: int
    by_file_kind: dict[str, int]
    visibility: Literal["private"] = "private"
    content_included: Literal[False] = False
    request_id: str


class SearchPrivateLibraryRequest(BaseModel):
    """Consent receipt selects owner server-side; model cannot submit an owner."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=500)
    consent_token: str = Field(min_length=20, max_length=200)
    limit: int = Field(default=5, ge=1, le=8)


class SearchPrivateLibraryResponse(BaseModel):
    query: str
    items: list[PrivateLibrarySearchItem]
    total: int
    truncated: bool
    content_scope: Literal["matching_excerpts"] = "matching_excerpts"
    visibility: Literal["private"] = "private"
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
    solutions = raw.get("solutions") or []
    first_solution = solutions[0] if solutions and isinstance(solutions[0], dict) else {}
    solution_steps = [
        str(step).strip()
        for step in first_solution.get("steps_latex", [])
        if str(step).strip()
    ][:20]
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


@router.post("/solve-question", response_model=SolveQuestionResponse)
async def solve_question(
    body: SolveQuestionRequest,
    request: Request,
    _token: None = Depends(_require_tool_gateway_token),
) -> SolveQuestionResponse:
    """Read-only Solve Tool: all trust decisions remain in SolutionAssistant."""
    request_id = _request_id_from(request)
    question_text = body.question_text.strip()
    solution_mode = body.solution_mode
    teacher_instruction = body.teacher_instruction
    visual_input = None
    if body.capture_grant is not None:
        try:
            binding = get_question_solve_grants().consume(body.capture_grant)
            question_text = binding.question_text
            solution_mode = binding.solution_mode
            teacher_instruction = binding.teacher_instruction
            reference = binding.reference
            prepared = await _run_with_timeout(
                request,
                get_question_capture().prepare_for_solve,
                reference,
                owner_id=binding.owner_id,
                request_id=request_id,
            )
        except QuestionSolveGrantError as exc:
            raise _GatewayHttpError(
                403, "PRIVATE_CONSENT_REQUIRED", str(exc), request_id
            ) from exc
        except KeyError:
            raise _GatewayHttpError(
                404, "TOOL_NOT_FOUND", "私人题目图片不存在", request_id
            ) from None
        except QuestionCaptureError as exc:
            raise _GatewayHttpError(
                422, "TOOL_VALIDATION_ERROR", str(exc), request_id
            ) from exc
        if prepared.question_text != question_text:
            raise _GatewayHttpError(
                422,
                "TOOL_VALIDATION_ERROR",
                "解题文本与教师确认的题面 revision 不一致",
                request_id,
            )
        visual_input = SolutionVisualInput(
            asset_id=prepared.asset_id,
            media_revision=prepared.media_revision,
            recognition_revision=prepared.recognition_revision,
            requires_visual_reasoning=prepared.requires_visual_reasoning,
            visual_processing_consent=prepared.visual_processing_consent,
            image_bytes=prepared.image_bytes,
            image_mime_type=prepared.image_mime_type,
        )
    command = SolutionRequest(
        question_text=question_text,
        solution_mode=solution_mode,
        teacher_instruction=teacher_instruction,
        teacher_id="owner_teacher",
    )
    try:
        result = await _run_with_timeout(
            request,
            get_solution_assistant().solve,
            command,
            visual_input,
            timeout_seconds=get_settings().solve_tool_timeout_seconds,
        )
    except SolutionAssistantVerificationError as exc:
        code = (
            "VERIFICATION_FAILED"
            if exc.assessment.status == "failed"
            else "VERIFICATION_INCONCLUSIVE"
        )
        raise _GatewayHttpError(409, code, str(exc), request_id) from None
    except (SolutionAssistantUnavailableError, SolutionProviderError):
        raise _GatewayHttpError(
            503,
            "MODEL_UNAVAILABLE",
            "当前没有可用的已验证解析或模型解题能力",
            request_id,
        ) from None
    except SolutionAssistantError as exc:
        raise _GatewayHttpError(
            422,
            "TOOL_VALIDATION_ERROR",
            str(exc),
            request_id,
        ) from exc
    except _GatewayHttpError:
        raise
    except Exception:
        logger.exception("solve_question_failed", extra={"request_id": request_id})
        raise _GatewayHttpError(
            500,
            "TOOL_EXECUTION_ERROR",
            "解题工具执行失败",
            request_id,
        ) from None
    return SolveQuestionResponse(**result.model_dump(), request_id=request_id)


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


@router.post(
    "/inspect-private-library",
    response_model=InspectPrivateLibraryResponse,
)
async def inspect_private_library(
    _body: InspectPrivateLibraryRequest,
    request: Request,
    _token: None = Depends(_require_tool_gateway_token),
) -> InspectPrivateLibraryResponse:
    """Return aggregate private-library state without exposing private content."""
    request_id = _request_id_from(request)
    try:
        stats = await _run_with_timeout(
            request,
            get_private_library().stats,
            owner_id="owner_teacher",
        )
    except _GatewayHttpError:
        raise
    except Exception:
        logger.exception(
            "inspect_private_library_failed",
            extra={"request_id": request_id},
        )
        raise _GatewayHttpError(
            500,
            "TOOL_EXECUTION_ERROR",
            "私人资料库概览读取失败",
            request_id,
        ) from None
    return InspectPrivateLibraryResponse(
        **stats.model_dump(),
        request_id=request_id,
    )


@router.post("/search-private-library", response_model=SearchPrivateLibraryResponse)
async def search_private_library(
    body: SearchPrivateLibraryRequest,
    request: Request,
    _token: None = Depends(_require_tool_gateway_token),
) -> SearchPrivateLibraryResponse:
    """Consume one explicit consent receipt and return only bounded confirmed excerpts."""
    request_id = _request_id_from(request)
    try:
        owner_id = get_private_retrieval_grants().consume(
            body.consent_token,
            query=body.query,
            limit=body.limit,
        )
        result = await _run_with_timeout(
            request,
            get_private_library().search_confirmed_text,
            body.query,
            limit=body.limit,
            owner_id=owner_id,
        )
    except PrivateRetrievalConsentError as exc:
        raise _GatewayHttpError(403, "PRIVATE_CONSENT_REQUIRED", str(exc), request_id) from exc
    except PrivateLibraryError as exc:
        raise _GatewayHttpError(422, "TOOL_VALIDATION_ERROR", str(exc), request_id) from exc
    except _GatewayHttpError:
        raise
    except Exception:
        logger.exception("search_private_library_failed", extra={"request_id": request_id})
        raise _GatewayHttpError(500, "TOOL_EXECUTION_ERROR", "私人资料检索失败", request_id) from None
    return SearchPrivateLibraryResponse(**result.model_dump(), request_id=request_id)

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
