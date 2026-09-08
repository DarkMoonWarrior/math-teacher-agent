from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.http_privacy import PrivateApiResponseMiddleware
from app.core.identity import (
    require_any_capability,
    require_capability,
    require_local_legacy_access,
)
from app.modules.beta_operations import PrivacySafeOperations, PrivacySafeOperationsMiddleware
from app.routes.account_session import router as account_session_router
from app.routes.beta_session import router as beta_session_router
from app.routes.beta_validation import router as beta_validation_router
from app.routes.curriculum import router as curriculum_router
from app.routes.exam_papers import router as exam_papers_router
from app.routes.internal_agent_tools import (
    _GatewayHttpError,
    gateway_error_handler,
    router as internal_agent_tools_router,
)
from app.routes.imports import router as imports_router
from app.routes.lesson_plans import router as lesson_plans_router
from app.routes.library import router as library_router
from app.routes.model_operations import router as model_operations_router
from app.routes.questions import router as questions_router
from app.routes.question_similarity import router as question_similarity_router
from app.routes.private_library_agent import router as private_library_agent_router
from app.routes.personal_question_library import router as personal_question_library_router
from app.routes.question_capture import router as question_capture_router
from app.routes.question_authoring import router as question_authoring_router
from app.routes.readiness import router as readiness_router
from app.routes.search_agent import (
    _SearchAgentHttpError,
    router as search_agent_router,
    search_agent_error_handler,
)
from app.routes.solve_agent import (
    _SolveAgentHttpError,
    router as solve_agent_router,
    solve_agent_error_handler,
)
from app.routes.solutions import router as solutions_router
from app.routes.teacher_memory import router as teacher_memory_router


settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")
app.add_exception_handler(_GatewayHttpError, gateway_error_handler)
app.add_exception_handler(_SearchAgentHttpError, search_agent_error_handler)
app.add_exception_handler(_SolveAgentHttpError, solve_agent_error_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    PrivacySafeOperationsMiddleware,
    operations=PrivacySafeOperations(),
)
app.add_middleware(PrivateApiResponseMiddleware)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.environment}


app.include_router(readiness_router)


app.include_router(curriculum_router, prefix="/api/v1")
app.include_router(account_session_router, prefix="/api/v1")
app.include_router(beta_session_router, prefix="/api/v1")
app.include_router(beta_validation_router, prefix="/api/v1")
app.include_router(
    imports_router,
    prefix="/api/v1",
    dependencies=[Depends(require_capability("library"))],
)
app.include_router(
    questions_router,
    prefix="/api/v1",
    dependencies=[Depends(require_local_legacy_access)],
)
app.include_router(
    question_similarity_router,
    prefix="/api/v1",
    dependencies=[Depends(require_local_legacy_access)],
)
app.include_router(
    lesson_plans_router,
    prefix="/api/v1",
    dependencies=[Depends(require_capability("lesson"))],
)
app.include_router(
    exam_papers_router,
    prefix="/api/v1",
    dependencies=[Depends(require_capability("paper"))],
)
app.include_router(
    solutions_router,
    prefix="/api/v1",
    dependencies=[
        Depends(require_capability("solve")),
        Depends(require_local_legacy_access),
    ],
)
app.include_router(
    library_router,
    prefix="/api/v1",
    dependencies=[Depends(require_capability("library"))],
)
app.include_router(
    model_operations_router,
    prefix="/api/v1",
    dependencies=[Depends(require_local_legacy_access)],
)
app.include_router(
    search_agent_router,
    prefix="/api/v1",
    dependencies=[Depends(require_capability("search"))],
)
app.include_router(
    solve_agent_router,
    prefix="/api/v1",
    dependencies=[Depends(require_capability("solve"))],
)
app.include_router(
    private_library_agent_router,
    prefix="/api/v1",
    dependencies=[Depends(require_capability("library"))],
)
app.include_router(
    question_capture_router,
    prefix="/api/v1",
    dependencies=[Depends(require_capability("solve"))],
)
app.include_router(
    personal_question_library_router,
    prefix="/api/v1",
    dependencies=[Depends(require_any_capability("authoring", "lesson", "paper"))],
)
app.include_router(
    question_authoring_router,
    prefix="/api/v1",
    dependencies=[Depends(require_capability("authoring"))],
)
app.include_router(
    teacher_memory_router,
    prefix="/api/v1",
    dependencies=[Depends(require_capability("teacher_memory"))],
)
# Internal-only Agent Tool Gateway（不进入公开 API 文档，M2M token 保护）
app.include_router(internal_agent_tools_router)
