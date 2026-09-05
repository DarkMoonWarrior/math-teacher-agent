from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.core.identity import CurrentTeacher, get_current_teacher
from app.modules.beta_validation import (
    BetaParticipantDeletion,
    BetaParticipantMetricExport,
    BetaValidationDeleteCommand,
    BetaValidationMetrics,
    BetaValidationNotice,
    BetaValidationParticipation,
)
from app.modules.beta_validation.dependencies import (
    get_beta_validation_metrics,
    get_beta_validation_store,
)


router = APIRouter(prefix="/beta-validation", tags=["beta-validation"])


@router.get("/notice", response_model=BetaValidationNotice)
def validation_notice(
    current_teacher: CurrentTeacher = Depends(get_current_teacher),
    settings: Settings = Depends(get_settings),
) -> BetaValidationNotice:
    del current_teacher
    return BetaValidationNotice(
        collection_enabled=settings.beta_validation_enabled,
    )


@router.post("/participation", response_model=BetaValidationParticipation)
def acknowledge_validation_notice(
    current_teacher: CurrentTeacher = Depends(get_current_teacher),
    metrics: BetaValidationMetrics = Depends(get_beta_validation_metrics),
) -> BetaValidationParticipation:
    return metrics.acknowledge(owner_id=current_teacher.teacher_id)


@router.get("/export", response_model=BetaParticipantMetricExport)
def export_my_validation_metrics(
    current_teacher: CurrentTeacher = Depends(get_current_teacher),
    metrics: BetaValidationMetrics = Depends(get_beta_validation_store),
) -> BetaParticipantMetricExport:
    return metrics.export_participant(owner_id=current_teacher.teacher_id)


@router.delete("/participation", response_model=BetaParticipantDeletion)
def leave_validation_collection(
    command: BetaValidationDeleteCommand,
    current_teacher: CurrentTeacher = Depends(get_current_teacher),
    metrics: BetaValidationMetrics = Depends(get_beta_validation_store),
) -> BetaParticipantDeletion:
    return metrics.delete_participant(
        owner_id=current_teacher.teacher_id,
        confirmed=command.confirm_delete_my_validation_data,
    )
