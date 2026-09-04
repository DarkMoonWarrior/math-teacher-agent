# ADR 2026-08-16：Teacher Agent Runtime 与 DeepSeek Harness 隔离

> 归档说明（2026-09-04）：本文保留原型/迁移时期的事实与决策。旧 UI、旧路径、分支、待办和验收数字不代表当前实现；请以 [当前开发状态](../PROJECT-STATUS.md) 为准。来源、权利与教材证据继续保留。

状态：Accepted
决策日期：2026-08-16
阶段：Prompt 2（Teacher Agent Runtime Foundation）

## 背景

产品计划用 DeepSeek Harness 驱动 Teacher Agent，但 DSH 处于 Developer Preview、
存在 breaking-change 风险；同时 Agent 必须遵守可信原则（不绕过 MathVerifier /
RightsGate，不直接访问数据库，AI 内容默认 draft）。

## 决策

1. **DSH 不直接嵌入 FastAPI 业务模块**：业务后端只依赖自有的
   `TeacherAgentRuntime` 接口；DSH 类型与 import 只允许出现在独立
   `apps/agent`（Node Agent Service）。
2. **Node Agent Service 与 Python Business Service 分离**：DSH 官方要求 Node ≥24，
   与现有 Python/Next.js 工具链隔离，避免为 Harness 升级整个产品工具链。
3. **Tool Gateway**：Agent 只能通过 `/internal/agent-tools/v1/*` 调用现有业务 Service；
   Python 业务层保持 source of truth，不在 TypeScript 重实现题库/验证/相似度/课程。
4. **least-capability tool allowlist**：第一版模型可见工具恰好 5 个只读工具，
   无 bash/filesystem/web/subagent/workflow；由自动测试强制而非文档约定。
5. **默认 runtime 仍为 legacy**：`MATH_AI_AGENT_RUNTIME=legacy` 时现有产品行为
   完全不变，DSH 不是应用启动必需依赖。
6. **DSH 版本精确 pin**：`0.1.0-rc.6`（无 `^`，无 latest），升级走锁定文档
   `DSH-INTEGRATION-LOCK.md` 与完整测试门禁。

## 后果

- Harness breaking change 的修改范围被限制在 `apps/agent` + adapter/plugin。
- Agent 权限与数据访问边界可测试、可审计。
- 短期成本：多一个服务进程与 M2M 认证配置；后续 Prompt 再决定部署形态。
