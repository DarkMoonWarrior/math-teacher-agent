# Teacher Agent Runtime 实现说明 v1（Prompt 2）

> 历史实现记录：Runtime 基础层仍有效，但其中“现有 UI”指迁移阶段的 `apps/web`。
> 当前主产品 UI 为 `apps/teacher-web`；最新 seam 与能力状态见 `docs/ARCHITECTURE.md` 和
> `docs/PROJECT-STATUS.md`。

## 目标

证明：现有高中数学业务系统可以通过稳定、可替换、安全的 `TeacherAgentRuntime` 驱动
DeepSeek Harness，且 Harness 只能通过受控只读 Tool 使用业务能力。
本阶段**不**新增用户产品功能、不修改现有 UI/API 行为。

## 架构链路

```
Next.js (apps/web, 现有教师界面)
   ↓ HTTP
FastAPI Business Backend (apps/api, 现有模块)
   ├─ TeacherAgentRuntime (Python Protocol, apps/api/app/agent_runtime)
   │     ├─ LegacyTeacherAgentRuntime   ← 默认（行为不变）
   │     └─ DeepSeekHarnessRuntime      ← HTTP 适配器（无 DSH import）
   ↓ HTTP (M2M, MATH_AI_AGENT_SERVICE_TOKEN)
Agent Service (apps/agent, Node/TS)
   └─ DeepSeekHarnessRuntime (product runtime)
         └─ DeepSeek Harness (boot + cordis plugin, DSH 唯一所在)
               └─ 5 Teacher Tools (defineTool)
                     ↓ HTTP (M2M, MATH_AI_TOOL_GATEWAY_TOKEN)
FastAPI Internal Tool Gateway (/internal/agent-tools/v1/*, include_in_schema=False)
   ↓
现有 Business Services：QuestionBank / MathVerifier / QuestionSimilarity / Curriculum
   ↓
Database
```

**Agent 永远不能直接访问数据库。** `apps/agent` 中没有也不允许出现 SQLite / SQL /
PostgreSQL / ORM 代码（有静态测试门禁：`tests/security/least-capability.test.ts`）。

## TeacherAgentRuntime 稳定接口

Python 侧（`apps/api/app/agent_runtime/base.py`，业务系统只依赖该接口）：

- `run(request) -> TeacherAgentRunResult`
- `stream(request) -> AsyncIterator[TeacherAgentEvent]`
- `cancel(run_id) -> TeacherAgentRunResult`
- `resume(session_id, request) -> TeacherAgentRunResult`
- `get_session(session_id) -> TeacherAgentSession`
- `health() -> TeacherAgentHealth`
- `capabilities() -> TeacherAgentCapabilities`

数据结构全部属于 math-teacher-agent（`TeacherAgentRunRequest/RunResult/Event/Session/
Capabilities/Error`，Node 侧 `apps/agent/src/runtime/types.ts` 与之对齐）。
DSH import 只允许出现在 `apps/agent` 内（`src/dsh/`、runtime 适配层与 tools 契约层）；FastAPI 业务模块与 `apps/web` 零 DSH import（已扫描确认）。

## 两个 Runtime

### LegacyTeacherAgentRuntime（默认）

- `MATH_AI_AGENT_RUNTIME=legacy`（默认）→ 现有产品行为完全不变。
- 单轮纯文本补全，无 Tool，不访问数据库；仅供运行时接口占位与 fallback 设计。
- Agent Service 未启动时现有系统（含 184 项后端测试）照常运行。

### DeepSeekHarnessRuntime

- `MATH_AI_AGENT_RUNTIME=dsh` → FastAPI 通过 HTTP 调用独立 Agent Service。
- Agent Service 不可达 → `RUNTIME_UNAVAILABLE`，**不 crash、不静默降级**。
- 显式降级：`MATH_AI_AGENT_ALLOW_LEGACY_FALLBACK=true` 时把 `RUNTIME_UNAVAILABLE`
  降级为 legacy，并记录 fallback happened / original error / runtime used。
  默认 `false`。

## 运行时配置（全部环境变量，见根 `.env.example`）

- FastAPI → Agent Service：`MATH_AI_AGENT_SERVICE_URL` + `MATH_AI_AGENT_SERVICE_TOKEN`。
- Agent Service → FastAPI Gateway：`MATH_AI_API_INTERNAL_URL` + `MATH_AI_TOOL_GATEWAY_TOKEN`。
- 两个信任方向使用**不同** secret；URL 只能来自配置，模型/用户不能提供 URL（防 SSRF）。
- DeepSeek API Key 只存在于 Agent Service 环境（`MATH_AI_DEEPSEEK_API_KEY`），
  绝不下发浏览器 / FastAPI 响应 / 日志 / 仓库。

## Session / Run 身份

- 产品自有 `teacher_agent_session_id`（前缀 `tch_`）与 `run_id`（前缀 `run_`）。
- `teacher_agent_session_id ↔ dsh_session_id` 的映射只存在于 adapter 内部。
- 当前无真实教师用户 ID；`teacher_user_id / tenant_id` 为未来预留字段，不伪造权限设计。
- 会话持久化：DSH 官方 JSONL session persistence，root 固定 `data/runtime/agent-sessions`
  （gitignored）；可替换，不扩散到业务代码。当前不引入 Redis/PostgreSQL session。

## Streaming / Cancellation / Resume

- **Streaming**：DSH 原始事件在 adapter 内映射为产品自有词汇表：
  `run_started / assistant_delta / tool_started / tool_finished / run_completed /
  run_failed / run_cancelled`。DSH 事件结构不直接透传给 FastAPI/Web。
- **Cancellation**：`cancel(run_id)` → run 级取消标志 + `agent.cancel({kind:'user'})` →
  工具 `exec.signal` 中止在途 HTTP 请求 → run 定局为 `cancelled`（`RUN_CANCELLED`）。
  不使用线程强杀 / process kill；测试证明请求 aborted 且无僵尸任务。
- **Resume**：使用官方公开 `ctx.agents.resume` + JSONL persistence；
  `capabilities.resume=true`（挂载 sessionPersistence 时）。跨 runtime 实例恢复已有测试。

## 安全门禁（自动测试强制）

- `tests/security/least-capability.test.ts`：model-visible tools 恰好等于 5 个只读工具；
  组合 YAML 不含 dsh-base / bash / filesystem / web / subagent / workflow / terminal；
  `apps/agent` 源码无任何数据库访问。
- `tests/transport/gateway-client.test.ts`：M2M 头、错误映射、超时、取消。
- `tests/runtime/cancel.test.ts`：取消 E2E。
- `tests/runtime/teacher-agent-runtime.test.ts`：确定性 DSH E2E（mock model → Harness →
  tool → gateway 契约 → 结构化结果）。
- `tests/runtime/resume.test.ts`：跨实例 resume。

## 模型 Provider

- 不重构现有 Python `deepseek.py` / `model_operations` / ProviderRegistry。
- 测试统一 deterministic mock（`test-mock`），CI 绝不调用真实 DeepSeek API。
- 真实 provider：官方 `@deepseek-ai/dsh-llm-deepseek` 插件，仅当存在
  `MATH_AI_DEEPSEEK_API_KEY` 时启用；手动 smoke test 需显式配置，默认不运行。

## 已知限制（Prompt 2 验收边界）

- `resume` 依赖 DSH Developer Preview 官方 API；若未来 breaking change 导致不可用，
  将 `capabilities.resume=false` 而不是侵入 Harness core。
- `get_session` 的 `run_ids` 是进程内记录，跨进程重启后只含新 run（历史由 DSH
  persistence 保存，Prompt 2 不要求跨进程聚合）。
- 尚未实现 UI streaming、Search Agent、写工具、教师账号体系（均属后续 Prompt）。
- DSH 升级风险与政策见 `DSH-INTEGRATION-LOCK.md`。

## Prompt 2.5 合并状态（2026-08-16）

- 已合并到 main：merge commit `ce05c69`（PR #2，merge commit，保留 7 个逻辑 commit）。
- Tag：`teacher-agent-runtime-v1.0`（annotated），作为 Teacher Agent 层正式回滚点。
- 合并后全量复验通过：Backend 184 passed；Agent typecheck / 28 tests / build 全绿；
  Frontend typecheck / build 全绿。
- DSH 来源核验与版本锁定详见 `DSH-INTEGRATION-LOCK.md`（rc.6 精确 pin、npm provenance、
  GitHub master 差异、Node engines REVIEW）。
