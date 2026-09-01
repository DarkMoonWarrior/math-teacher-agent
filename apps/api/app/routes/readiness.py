from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.agent_runtime import TeacherAgentRuntime, get_teacher_agent_runtime
from app.core.config import Settings, get_settings
from app.modules.beta_access import BetaAccess
from app.modules.beta_access.dependencies import get_beta_access
from app.modules.beta_operations import ReadinessProbe


router = APIRouter(tags=["system"])


@router.get("/ready")
async def readiness(
    settings: Settings = Depends(get_settings),
    beta_access: BetaAccess = Depends(get_beta_access),
    runtime: TeacherAgentRuntime = Depends(get_teacher_agent_runtime),
):
    snapshot = await ReadinessProbe().check(
        settings=settings,
        beta_access=beta_access,
        runtime=runtime,
    )
    return JSONResponse(
        status_code=200 if snapshot.status == "ready" else 503,
        content=snapshot.model_dump(mode="json"),
    )
