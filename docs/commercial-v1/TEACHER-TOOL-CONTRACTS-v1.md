# Teacher Tool 契约 v1（5 个只读工具）

> 归档说明（2026-09-04）：本文保留原型/迁移时期的事实与决策。旧 UI、旧路径、分支、待办和验收数字不代表当前实现；请以 [当前开发状态](../PROJECT-STATUS.md) 为准。来源、权利与教材证据继续保留。

本文档定义第一版 Teacher Agent 的 model-visible tool allowlist 与每个工具经
FastAPI Internal Tool Gateway（`/internal/agent-tools/v1/*`）的正式契约。
Gateway 实际以 FastAPI Pydantic 模型为准（`apps/api/app/routes/internal_agent_tools.py`）。

## 强制 Allowlist

model-visible tools **恰好等于**（自动测试强制，见 `apps/agent/tests/security/least-capability.test.ts`）：

1. `search_questions`
2. `get_question`
3. `find_similar_questions`
4. `verify_question`
5. `get_curriculum_node`

任何额外工具（bash / filesystem / web / subagent / workflow / terminal 等）出现时测试必须失败。

## 通用协议

- 方法：`POST`；`Content-Type: application/json`。
- 认证：`Authorization: Bearer <MATH_AI_TOOL_GATEWAY_TOKEN>`（M2M，缺失/错误 → 401 `TOOL_UNAUTHORIZED`）。
- 头：`X-Request-Id`（≤160 字符，回显到 `request_id`）。
- 错误信封（HTTP 4xx/5xx 与 domain 错误统一）：`{ "code", "message", "request_id" }`，
  词汇表：`TOOL_UNAUTHORIZED` / `TOOL_NOT_FOUND` / `TOOL_VALIDATION_ERROR` /
  `TOOL_TIMEOUT` / `TOOL_EXECUTION_ERROR`（错误响应不含 traceback / 本地路径 / secret）。
- 网关服务端 timeout：`MATH_AI_TOOL_GATEWAY_TIMEOUT_SECONDS`（默认 30s）→ 504 `TOOL_TIMEOUT`。
- Agent 客户端同样带超时并把取消信号（`exec.signal`）转发到 HTTP 请求。

## 1. search_questions

- 路由：`/internal/agent-tools/v1/search-questions`
- 请求：`query`（≤200）、`chapter`（≤120，可空）、`difficulty`（1–5，可空）、
  `knowledge_point_id`（≤160，可空）、`limit`（默认 10，**hard max 20**）。
- 响应：`items[]`（每项 `question_id/stem/question_type/knowledge_points/difficulty/
  verification_status/source_status/visibility`）、`total`、`truncated`、
  `query_interpretation`（可空）、`request_id`。
- 语义：只走现有 QuestionBank 可见性/权利/发布门禁路径；`limit` 有硬上限，不能一次拉取整个题库。
- 调用方：`app.routes.questions.get_question_bank`。

## 2. get_question

- 路由：`/internal/agent-tools/v1/get-question`
- 请求：`question_id`（1–160）。
- 响应：`question_id/stem/question_type/answer/solution_steps/verification_status/
  visibility/source_status/request_id`。
- 语义：单题完整内容；只返回经现有业务门禁允许的内容；未知 ID 返回结构化 domain 错误
  （HTTP 404 → Agent 侧 `ok:false` 信封，不抛基础设施异常）。

## 3. find_similar_questions

- 路由：`/internal/agent-tools/v1/find-similar-questions`
- 请求：`question_id`、`limit`（默认 10，hard max 20）。
- 响应：`items[]`（`question_id/stem/relation/confidence/status`）、`total`、`truncated`、`request_id`。
- 语义：调用现有 `QuestionSimilarityRegistry`，不在 TypeScript 重实现相似度。

## 4. verify_question

- 路由：`/internal/agent-tools/v1/verify-question`
- 请求：`question_id`。
- 响应：`question_id/stored_status/capability/computed_answer/method/details/
  fresh_verification/request_id`。
- 语义：调用现有 `MathVerifier`；Agent 不得自行判断数学正确性，也不得在 TypeScript 重实现验证。

## 5. get_curriculum_node

- 路由：`/internal/agent-tools/v1/get-curriculum-node`
- 请求：`node_id`（1–160）。
- 响应：`node_id/parent_id/volume/node_type/code/name/description/knowledge_points/request_id`。
- 语义：调用现有 `CurriculumCatalog`，只读课程目录。

## 本阶段明确不存在的能力

`create_question` / `update_question` / `delete_question` / `publish_question` /
`create_variant` / `create_paper` / `create_lesson` / `import_resource` /
`upload_file` / `database_write` 均不存在；第二批写工具只做设计，Prompt 2 不实现。

## Tool 输出原则

- 输出一律 canonical 结构化 JSON，上层 Agent 不需要对 `question_id/status/difficulty/
  verification result` 做 NLP 解析。
- 基础设施失败 throw；domain 结果（含 404/参数错误）以结构化 `ok:false` 信封返回。
- 工具执行遵守 DSH tool contract（args validated、structured output、honor cancellation signal）。
