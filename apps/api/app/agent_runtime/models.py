"""TeacherAgentRuntime 的稳定数据模型。

这些类型属于 math-teacher-agent 产品本身。DeepSeek Harness 的任何类型
都不得出现在本模块中；DSH 类型只允许存在于 apps/agent 的 adapter 内部
以及本仓库的 DeepSeekHarnessRuntime HTTP 客户端边界之外。
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TeacherAgentErrorCode(str, Enum):
    """产品级稳定错误词汇表。"""

    RUNTIME_UNAVAILABLE = "RUNTIME_UNAVAILABLE"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    TOOL_TIMEOUT = "TOOL_TIMEOUT"
    TOOL_UNAUTHORIZED = "TOOL_UNAUTHORIZED"
    TOOL_NOT_FOUND = "TOOL_NOT_FOUND"
    TOOL_VALIDATION_ERROR = "TOOL_VALIDATION_ERROR"
    TOOL_EXECUTION_ERROR = "TOOL_EXECUTION_ERROR"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    VERIFICATION_INCONCLUSIVE = "VERIFICATION_INCONCLUSIVE"
    RUN_CANCELLED = "RUN_CANCELLED"
    UNSUPPORTED_CAPABILITY = "UNSUPPORTED_CAPABILITY"
    SEARCH_PLAN_EXHAUSTED = "SEARCH_PLAN_EXHAUSTED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class TeacherAgentRunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TeacherAgentSessionStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    CANCELLED = "cancelled"
    FAILED = "failed"


class TeacherAgentEventType(str, Enum):
    """产品级事件词汇表；DSH 原始事件只在 adapter 内部映射。"""

    RUN_STARTED = "run_started"
    ASSISTANT_DELTA = "assistant_delta"
    TOOL_STARTED = "tool_started"
    TOOL_FINISHED = "tool_finished"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"
    RUN_CANCELLED = "run_cancelled"


class TeacherAgentError(BaseModel):
    code: TeacherAgentErrorCode
    message: str
    request_id: str = ""
    retryable: bool = False


class TeacherAgentToolCall(BaseModel):
    tool_name: str
    status: str
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] | None = None
    error: TeacherAgentError | None = None
    started_at: float = 0.0
    finished_at: float = 0.0


class TeacherAgentRunRequest(BaseModel):
    """发起一次 Agent run。当前阶段还没有真实教师账号，预留字段仅作占位。"""

    user_message: str = Field(min_length=1, max_length=8000)
    session_id: str | None = Field(default=None, max_length=160)
    request_id: str = Field(default="", max_length=160)
    # 未来 user/tenant 边界预留；当前阶段不得依赖其做权限判断。
    teacher_user_id: str | None = Field(default=None, max_length=160)
    tenant_id: str | None = Field(default=None, max_length=160)


class TeacherAgentRunResult(BaseModel):
    run_id: str
    session_id: str
    request_id: str
    runtime: str
    status: TeacherAgentRunStatus
    final_text: str = ""
    tool_calls: list[TeacherAgentToolCall] = Field(default_factory=list)
    error: TeacherAgentError | None = None


class TeacherAgentEvent(BaseModel):
    type: TeacherAgentEventType
    run_id: str
    session_id: str
    request_id: str
    data: dict[str, Any] = Field(default_factory=dict)
    sequence: int = 0
    created_at: float = Field(default_factory=time.time)


class TeacherAgentSession(BaseModel):
    session_id: str
    runtime: str
    status: TeacherAgentSessionStatus
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    run_ids: list[str] = Field(default_factory=list)
    teacher_user_id: str | None = None
    tenant_id: str | None = None


class TeacherAgentCapabilities(BaseModel):
    run: bool = True
    stream: bool = False
    cancel: bool = False
    resume: bool = False
    get_session: bool = True
    health: bool = True
    model_configured: bool = False
    visible_tool_names: list[str] = Field(default_factory=list)
    runtime_version: str = "0.1.0"


class TeacherAgentHealth(BaseModel):
    status: str
    runtime: str
    initialized: bool
    model_configured: bool
    tool_registry_ready: bool
    visible_tool_count: int
    runtime_version: str
    dsh_version: str | None = None
