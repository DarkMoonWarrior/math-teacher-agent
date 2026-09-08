from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


METRIC_DEFINITION_VERSION = "m13.v1"
NOTICE_VERSION = "m13.notice.v1"
RETENTION_DAYS = 90

BetaWorkflow = Literal[
    "search",
    "solve",
    "library",
    "authoring",
    "paper",
    "lesson",
    "teacher_memory",
]
BetaTrustTier = Literal[
    "verified_source",
    "program_verified",
    "model_reviewed",
    "teacher_review_required",
]
BetaValidationEventType = Literal[
    "task_completed",
    "task_accepted",
    "task_rejected",
    "search_completed",
    "search_result_selected",
    "paper_generated",
    "paper_exported",
    "lesson_generated",
    "lesson_saved",
    "private_library_import_confirmed",
    "authoring_completed",
    "authoring_saved",
    "agent_tool_succeeded",
    "agent_tool_failed",
    "serious_math_error_confirmed",
    "model_usage",
]


class BetaValidationObservation(BaseModel):
    """Strict, content-free input for one M13 validation fact.

    ``task_ref`` is a server-owned opaque identifier. It is accepted only so the
    module can correlate a journey and is HMAC-digested before persistence.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    task_ref: str = Field(pattern=r"^[A-Za-z0-9_.:-]{1,160}$")
    workflow: BetaWorkflow
    event_type: BetaValidationEventType
    trust_tier: BetaTrustTier | None = None
    duration_ms: int | None = Field(default=None, ge=0, le=86_400_000)
    model_cost_usd: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=14, decimal_places=8
    )

    @model_validator(mode="after")
    def validate_event_contract(self) -> "BetaValidationObservation":
        expected_workflow = {
            "search_completed": "search",
            "search_result_selected": "search",
            "paper_generated": "paper",
            "paper_exported": "paper",
            "lesson_generated": "lesson",
            "lesson_saved": "lesson",
            "private_library_import_confirmed": "library",
            "authoring_completed": "authoring",
            "authoring_saved": "authoring",
        }.get(self.event_type)
        if expected_workflow is not None and self.workflow != expected_workflow:
            raise ValueError(f"{self.event_type} 只能用于 {expected_workflow} 工作流。")
        if self.event_type == "task_completed":
            if self.trust_tier is None or self.duration_ms is None:
                raise ValueError("完成任务必须包含可信等级和耗时。")
        if self.event_type == "serious_math_error_confirmed" and self.trust_tier is None:
            raise ValueError("确认严重数学错误必须包含原任务可信等级。")
        if self.event_type != "model_usage" and self.model_cost_usd != Decimal("0"):
            raise ValueError("模型成本只能由 model_usage 事件记录。")
        if self.event_type != "task_completed" and self.duration_ms is not None:
            raise ValueError("任务耗时只能由 task_completed 事件记录。")
        return self


class BetaValidationReceipt(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: str
    occurred_at: datetime
    definition_version: Literal["m13.v1"] = METRIC_DEFINITION_VERSION


class BetaMetricDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    unit: Literal["count", "rate", "usd", "milliseconds"]
    description: str
    numerator: str
    denominator: str


class BetaMetricValue(BaseModel):
    model_config = ConfigDict(frozen=True)

    value: float | None
    numerator: float
    denominator: float | None = None
    unit: Literal["count", "rate", "usd", "milliseconds"]


class BetaMetricSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    definition_version: Literal["m13.v1"] = METRIC_DEFINITION_VERSION
    window_start: datetime
    window_end: datetime
    generated_at: datetime
    metrics: dict[str, BetaMetricValue]
    trust_tier_error_rates: dict[BetaTrustTier, BetaMetricValue]


class BetaCohortProgress(BaseModel):
    """Weekly activation cohort without participant or task identifiers."""

    model_config = ConfigDict(frozen=True)

    activation_week_start: date
    activated_teachers: int = Field(ge=0)
    week_1_retention: BetaMetricValue
    week_4_retention: BetaMetricValue


class BetaPrivateOperationsReadout(BaseModel):
    """Content-free, aggregate-only readout for the private Beta operator."""

    model_config = ConfigDict(frozen=True)

    definition_version: Literal["m13.v1"] = METRIC_DEFINITION_VERSION
    generated_at: datetime
    window_start: datetime
    window_end: datetime
    event_count: int = Field(ge=0)
    acknowledged_participants: int = Field(ge=0)
    activated_teachers: int = Field(ge=0)
    target_beta_teachers_min: Literal[20] = 20
    target_beta_teachers_max: Literal[30] = 30
    sample_status: Literal["empty", "below_target", "target_range", "above_target"]
    metrics: dict[str, BetaMetricValue]
    trust_tier_error_rates: dict[BetaTrustTier, BetaMetricValue]
    cohorts: tuple[BetaCohortProgress, ...]


class BetaValidationNotice(BaseModel):
    """Stable teacher-facing disclosure for the optional M13 event store."""

    model_config = ConfigDict(frozen=True)

    notice_version: Literal["m13.notice.v1"] = NOTICE_VERSION
    definition_version: Literal["m13.v1"] = METRIC_DEFINITION_VERSION
    collection_enabled: bool
    acknowledgment_required: Literal[True] = True
    retention_days: Literal[90] = RETENTION_DAYS
    collected_categories: tuple[str, ...] = (
        "工作流类型与完成、接受或导出等状态",
        "可信等级、耗时及模型成本数值",
    )
    excluded_categories: tuple[str, ...] = (
        "题目、答案、解析、提示词与教师输入正文",
        "上传文件、网址、学生信息与个人题库名称",
    )
    teacher_rights: tuple[str, ...] = (
        "随时导出本人保留期内的聚合指标",
        "随时退出指标采集并删除本人指标事件",
    )


class BetaValidationParticipation(BaseModel):
    model_config = ConfigDict(frozen=True)

    notice_version: Literal["m13.notice.v1"] = NOTICE_VERSION
    acknowledged_at: datetime
    collection_active: Literal[True] = True


class BetaParticipantMetricExport(BaseModel):
    """Content-free export for the authenticated teacher only."""

    model_config = ConfigDict(frozen=True)

    notice_version: Literal["m13.notice.v1"] = NOTICE_VERSION
    definition_version: Literal["m13.v1"] = METRIC_DEFINITION_VERSION
    retention_days: Literal[90] = RETENTION_DAYS
    generated_at: datetime
    window_start: datetime
    window_end: datetime
    acknowledged_at: datetime | None
    event_count: int = Field(ge=0)
    metrics: dict[str, BetaMetricValue]
    trust_tier_error_rates: dict[BetaTrustTier, BetaMetricValue]


class BetaParticipantDeletion(BaseModel):
    model_config = ConfigDict(frozen=True)

    deleted_at: datetime
    deleted_events: int = Field(ge=0)
    participation_removed: bool
    collection_active: Literal[False] = False


class BetaValidationDeleteCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    confirm_delete_my_validation_data: Literal[True]


class BetaValidationRetentionReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    retention_days: Literal[90] = RETENTION_DAYS
    evaluated_at: datetime
    cutoff_at: datetime
    total_events: int = Field(ge=0)
    retained_events: int = Field(ge=0)
    expired_events: int = Field(ge=0)
    unclassified_events: int = Field(ge=0)
    deleted_events: int = Field(default=0, ge=0)
