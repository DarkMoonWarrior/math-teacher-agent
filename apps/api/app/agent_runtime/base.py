"""TeacherAgentRuntime 稳定接口（ABC）。

业务系统只依赖这个接口，不依赖任何具体 Runtime 实现，
更不依赖 DeepSeek Harness 内部 API。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import ClassVar

from app.agent_runtime.models import (
    TeacherAgentCapabilities,
    TeacherAgentEvent,
    TeacherAgentHealth,
    TeacherAgentRunRequest,
    TeacherAgentRunResult,
    TeacherAgentSession,
)


class TeacherAgentRuntime(ABC):
    """我们的产品级 Agent Runtime 边界。

    实现要求：
    - 输入/输出只使用 app.agent_runtime.models 中的类型。
    - 任何 Harness 类型不得泄漏到本接口。
    - 任何实现都不得直接访问数据库。
    """

    runtime_name: ClassVar[str] = "abstract"
    runtime_version: ClassVar[str] = "0.1.0"

    @abstractmethod
    async def run(self, request: TeacherAgentRunRequest) -> TeacherAgentRunResult:
        """执行一次完整 run，直到 completed / failed / cancelled。"""

    @abstractmethod
    def stream(
        self, request: TeacherAgentRunRequest
    ) -> AsyncIterator[TeacherAgentEvent]:
        """流式执行并产出产品级事件；结束时必须产出终态事件。"""

    @abstractmethod
    async def cancel(self, run_id: str) -> TeacherAgentRunResult:
        """取消进行中的 run；未知 run_id 返回明确错误结果。"""

    @abstractmethod
    async def resume(
        self, session_id: str, request: TeacherAgentRunRequest
    ) -> TeacherAgentRunResult:
        """在既有 session 上继续。不支持时必须返回 UNSUPPORTED_CAPABILITY。"""

    @abstractmethod
    async def get_session(self, session_id: str) -> TeacherAgentSession:
        """读取我们自己的 session 视图。"""

    @abstractmethod
    async def health(self) -> TeacherAgentHealth:
        """健康信息；不得暴露任何 secret / key / token。"""

    @abstractmethod
    async def capabilities(self) -> TeacherAgentCapabilities:
        """能力声明；必须与实际行为一致（宁可 false，不可假报）。"""
