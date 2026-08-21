# Teacher Agent Runtime（apps/agent）

独立 Node / TypeScript Agent Service，负责驱动 DeepSeek Harness 执行 Teacher Agent。

安全边界：

- 本服务**不直接访问任何数据库**；题目/课程数据只能通过 FastAPI Internal Tool Gateway 获取。
- 模型可见工具**恰好只有 6 个受控只读工具**：`search_questions`、`get_question`、
  `solve_question`、`find_similar_questions`、`verify_question`、`get_curriculum_node`。
- 组合不挂载 bash / filesystem / web / subagent / workflow 等任何额外能力。
- Harness 依赖精确锁定 `0.1.0-rc.6`，所有 DeepSeek Harness import 只允许出现在本 app 内。

## 环境要求

- Node >= 24.0.0（DeepSeek Harness 官方要求）
- pnpm（workspace）

## 运行

```bash
# 在仓库根目录
pnpm setup:env      # 首次运行；生成本地 token，并启用 dsh + test-mock
pnpm dev:agent      # 启动 Agent Service（默认 127.0.0.1:4100）
pnpm typecheck:agent # TypeScript 类型检查
pnpm test:agent      # vitest：transport / E2E / cancel / resume / 安全门禁
pnpm build:agent     # 编译到 dist/
```

测试全部使用 deterministic mock model（`test-mock`），绝不调用真实 DeepSeek API。
`pnpm dev:agent` 从仓库根 `.env` 加载配置。真实模型接入需要同时配置 `MATH_AI_DEEPSEEK_API_KEY` 与
`MATH_AI_AGENT_PROVIDER=deepseek-official`（见仓库根 `.env.example`）。

## 当前状态

- 产品自有 Runtime interface 与 DeepSeek Harness adapter 已实现。
- Search Agent 与 Solve Agent Tool seam、取消、恢复、tool-loop 上限和最小权限均有自动测试。
- 目前模型可见能力仍严格限制为 6 个受控只读 Tool；`solve_question` 原样返回 MathVerifier 的 status/capability/scope 分级，不保存或发布；Lesson/Paper 写工具尚未接入。
- 默认 `test-mock` 不调用真实模型；生产密钥只存在于本服务环境。

## HTTP 接口（machine-to-machine）

- `POST /v1/run`、`POST /v1/stream`、`POST /v1/cancel`、`POST /v1/resume`
- `GET /v1/sessions/:id`、`GET /health`、`GET /capabilities`

所有端点要求 `Authorization: Bearer <MATH_AI_AGENT_SERVICE_TOKEN>`，未配置 token 时 fail closed。
