# 商业 V1 · Teacher Agent 架构 v1（设计稿）

> 归档说明（2026-09-04）：本文保留原型/迁移时期的事实与决策。旧 UI、旧路径、分支、待办和验收数字不代表当前实现；请以 [当前开发状态](../PROJECT-STATUS.md) 为准。来源、权利与教材证据继续保留。

- 文档编号：COMMERCIAL-V1 / DOC-03
- 审计日期：2026-08-16
- 状态：**仅设计，不实现**。本阶段不集成 DeepSeek Harness，不改任何现有业务代码与 API。

## 1. 目标与非目标

### 目标

- 新增独立 Teacher Agent 层：`TeacherAgentRuntime` 作为业务系统唯一依赖的 Agent 接口。
- DeepSeek Harness 只作为其中一个 Runtime 实现存在，通过 adapter/plugin/tool 接入，**不修改 Harness core**。
- Agent 只能通过受控 Tool 调用现有 FastAPI 业务服务，永远不能直接访问数据库。
- 所有 AI 产物默认 draft；MathVerifier、RightsGate、Teacher Review 不可绕过。

### 非目标（本设计明确排除）

- 不做 Agent 直接发布、批量合并、自动删数据。
- 不做 Agent 直连 SQLite/PostgreSQL/对象存储。
- 不做学生端/家长端/多学科扩展。
- 不把 Harness 代码 vendoring 进业务仓库并改 core。

## 2. 分层架构

```text
┌──────────────────────────────────────────────────────────┐
│ Next.js Web（教师工作台，现有 UI 不变）                      │
└──────────────────────────┬───────────────────────────────┘
                           │ 现有 REST /api/v1（不变）
┌──────────────────────────▼───────────────────────────────┐
│ FastAPI Business Services（KEEP 模块 + 路由，发布门禁在此）  │
│  search_questions · verify_question · create_paper_draft…  │
│  Rights / Permission / Validation（RightsGate 抽取后在此）   │
└──────────────┬──────────────────────────┬────────────────┘
               │ 受控 Tool HTTP 网关        │ 各模块 SQLite（未来 PG）
┌──────────────▼──────────────┐   ┌───────▼────────────────┐
│ TeacherAgentRuntime（接口）   │   │ 数据库（Agent 无路径）   │
│  LegacyTeacherAgentRuntime   │   └────────────────────────┘
│  DeepSeekHarnessRuntime      │
│   └─ Harness adapter/plugin  │
│      /tool/preset（隔离层）    │
└─────────────────────────────┘
```

不变式：

- Next.js 与 FastAPI 不 import 任何 Harness 代码。
- Harness 进程（Node/TS）只持有 Tool 网关地址与能力令牌，不持有数据库凭证、文件路径或 API Key。
- 业务服务不知道调用方是 UI 还是 Agent；两者走同一组权限/验证/门禁。

## 3. TeacherAgentRuntime 接口（TypeScript 草案）

```ts
type AgentRole = "teacher"; // 仅教师角色；管理员门禁不暴露给 Agent
type Capability = string;   // 如 "read.question_bank" | "draft.paper"

interface AgentContext {
  sessionId: string;
  teacherId: string;
  capabilities: Capability[]; // 会话级最小权限
  budget?: { maxToolCalls: number; maxTokens: number };
}

interface AgentRunSpec {
  intent: string; // 自然语言任务描述
  context: AgentContext;
  toolset: "read_only_v1" | "draft_write_v1";
}

interface AgentEvent {
  type: "message" | "tool_call" | "tool_result" | "status" | "error" | "done";
  // 每个 tool_call 携带 runId、工具名、入参摘要与审计 ID；正文只进业务服务
}

interface TeacherAgentRuntime {
  run(spec: AgentRunSpec): Promise<AgentRunHandle>;
  resume(runId: string, input: AgentResumeInput): Promise<AgentRunHandle>;
  cancel(runId: string, reason: CancelReason): Promise<CancelResult>;
  stream(runId: string): AsyncIterable<AgentEvent>;
  getSession(sessionId: string): Promise<AgentSession>;
}

interface AgentSession {
  sessionId: string;
  teacherId: string;
  capabilities: Capability[];
  history: AgentEvent[];
  state: "idle" | "running" | "waiting_teacher" | "failed" | "cancelled";
}
```

语义约定：

- `run` 幂等返回 run 句柄；同一 run 可重复 `stream`。
- `resume` 仅用于 `waiting_teacher`（需要教师确认/补充信息）状态，不得自动续跑写操作。
- `cancel` 必须传播到后端：中断进行中的 Tool 调用，并在审计中记录原因。
- `getSession` 只返回会话元数据与事件流，不返回任何原始数据行。

## 4. 两种 Runtime 的关系

| | LegacyTeacherAgentRuntime | DeepSeekHarnessRuntime |
| --- | --- | --- |
| 形态 | 确定性"工作流编排器"：按意图模板调用 Tool，无自主多步推理 | Harness 全量 Agent 循环（多步规划、工具迭代） |
| 依赖 | 仅 Tool 网关 HTTP 客户端 | DeepSeek Harness + 网关客户端 |
| 用途 | 默认 Runtime、无 Key 环境、测试、线上降级 | 有 Key/云端环境的主 Runtime |
| 契约 | 实现同一 `TeacherAgentRuntime` 接口，通过同一 conformance 测试套件 | 同左 |

设计决定：

- 两者是**同一接口的两种实现**，按配置切换；Legacy 永久保留为降级与测试路径。
- Harness 通过 `DeepSeekHarnessRuntime` 适配器接入；Harness 内部能力以 plugin/tool/preset 形式注册，
  适配器只做"Harness 事件 ↔ TeacherAgentRuntime 事件"的翻译。
- Harness 的 breaking change 只允许影响适配器包，不允许波及业务服务。

## 5. DeepSeek Harness 接入位置（唯一允许位置）

- 新仓库内独立的 `agent/packages/deepseek-harness-runtime`（Node/TS）。
- 接入点：`tool`（业务能力 RPC）、`adapter`（Runtime 翻译）、`preset`（模型/预算配置）、
  必要时 `plugin`（会话持久化钩子）。
- 红线：不修改 Harness core；不在 FastAPI/Next.js 内 import Harness；不在业务模块内出现
  Harness 特有类型或事件名。
- 升级策略：Harness 版本锁定在适配器包的 `package.json`；升级必须过 conformance 套件后放行。

## 6. Harness → FastAPI Tool API 安全边界

1. 专用网关（设计）：`POST /api/v1/agent/tools/{tool_name}`，挂 FastAPI 服务层之上，
   直接调用模块服务对象，不复用浏览器路由（无 HTML/CORS 语义冲突）。
2. 认证与最小权限：会话级能力令牌（`read_only_v1` / `draft_write_v1`），
   令牌绑定 `teacherId + sessionId + capabilities + 有效期`；无令牌或越权即 403。
3. 数据边界：Tool 响应必须是 Pydantic View（现有 schema），禁止返回数据库连接、
   文件绝对路径、原始 SQL、他人私有内容。
4. 私有内容：所有 Tool 在调用者的可见性范围内执行（教师只能看自己的私库与公共题库），
   private → public 在服务层无路径。
5. 写操作全部 draft：`draft_write_v1` 工具产出 `draft` 状态对象；`publish`、审核批准、
   软删除确认等能力**不进入任何 Agent toolset**。
6. 门禁保留：`verify_question` 调用 MathVerifier 纯验证；任何"通过"声明只能由验证报告决定；
   模型答案不得覆盖验证结论。
7. 预算与限流：每次 `run` 有最大 Tool 调用数与 token 预算；超出即 `cancelled` 并审计。
8. 审计：每次 Tool 调用记录 `run_id/session/teacher/tool/入参哈希/出参哈希/耗时/结果`，
   纳入 `model_operations` 记录器扩展，仍不存题目正文、提示词与密钥。
9. 明确禁止：Agent 执行 SQL、读写 SQLite/PostgreSQL 文件、访问文件系统路径、
   使用浏览器路由伪造请求、调用任何未列入 toolset 的端点。

## 7. 第一批只读 Tool（下一阶段最小实现）

| Tool | 对应服务 | 输入 | 输出 | 权限 |
| --- | --- | --- | --- | --- |
| `search_questions` | `QuestionBank.search` | query、章节/难度/质量过滤、分页 | `QuestionSearchPage`（仅 active + 可见性过滤） | `read.question_bank` |
| `get_question` | `QuestionBank.get_question` | question_id | `QuestionDetail`（含验证/审核/来源证据） | `read.question_bank` |
| `find_similar_questions` | `QuestionSimilarityRegistry` | question_id、limit | 候选对 + 关系类型 + 置信度 + 证据 | `read.similarity` |
| `verify_question` | `MathVerifier.verify` | 题干/选项/答案结构 | `VerificationReport`（passed/failed/inconclusive + 证据） | `read.verifier`（纯只读） |
| `get_curriculum_node` | `CurriculumCatalog` | node_id | 节点视图 + 路径 + 子节点 | `read.curriculum` |

约定：这五个 Tool 不产生任何写操作；Agent 输出引用验证报告时必须保留
`program_verified / teacher_review_required` 分级，不得改写结论。

## 8. 第二批写操作 Tool（本阶段仅设计，不实现）

| Tool | 对应服务 | 产物状态 | 强制门禁 |
| --- | --- | --- | --- |
| `create_paper_draft` | `ExamPaperStudio/Composer` | `draft` 试卷 + 版本快照 | 仅从验证通过且权利允许的题库选题；导出前教师确认 |
| `create_lesson_draft` | `LessonPlanStudio` | `draft` 教案 | 关联题必须经过验证；教师复核提示保留 |
| `create_question_variant` | `QuestionVariantService` | `private` 派生题草稿 | 母题验证通过 + 权利允许改编；模型输出 `needs_math_review` |
| `import_private_resource` | `PrivateLibrary.ingest` | `private` 资料条目 | 必须携带 `rights_basis`；默认 private；绝不自动公开 |

统一规则：全部 draft/private；发布、审核批准、权利授予、软删除确认均不在 Agent 权限内；
教师在后端 UI 完成最终确认。

## 9. 与现有 AI 能力的关系

- 现有 provider（教案/变式/解题/OCR）继续作为业务服务内部能力，由业务服务负责
  ProviderRegistry 选择与 ModelRunRecorder 记录；Agent 不直接调模型。
- Agent 层的"智能"只来自 Harness（未来）或意图模板（Legacy）；业务语义与门禁全部留在 FastAPI。
- 现有 `BackgroundJobRegistry` 继续承接 OCR/长任务；Agent 调用的长任务同样返回 job_id 轮询，
  不阻塞 Agent 会话。

## 10. 回滚与降级

- 配置开关：`agent.runtime=legacy|harness|off`；`off` 时前端与现有 API 完全不受影响。
- Legacy Runtime 永远可用；Harness 故障自动降级为 Legacy 或直接拒绝，不产生半成品。
- 所有 Agent 产物在业务层就是普通 draft，随时可经现有 UI 放弃/重做。

## 11. 明确不做的内容（本设计冻结）

- 不实现任何新页面；不改变现有 9 组路由的请求/响应。
- 不给 Agent 增加"自动发布""批量导入""自动合并""自动删数据"能力。
- 不在本阶段把 Harness 接入 CI 或生产运行。
