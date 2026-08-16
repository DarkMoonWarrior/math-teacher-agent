# Agent Service（apps/agent）

独立 Node / TypeScript Agent Service，负责驱动 DeepSeek Harness 执行 Teacher Agent。

安全边界（Prompt 2）：

- 本服务**不直接访问任何数据库**；题目/课程数据只能通过 FastAPI Internal Tool Gateway 获取。
- 模型可见工具**恰好只有 5 个只读工具**：`search_questions`、`get_question`、
  `find_similar_questions`、`verify_question`、`get_curriculum_node`。
- 组合不挂载 bash / filesystem / web / subagent / workflow 等任何额外能力。
- Harness 依赖精确锁定 `0.1.0-rc.6`，所有 DeepSeek Harness import 只允许出现在本 app 内。

## 环境要求

- Node >= 24.0.0（DeepSeek Harness 官方要求）
- pnpm（workspace）

## 运行

```bash
# 在仓库根目录
pnpm dev:agent        # 启动 Agent Service（默认 127.0.0.1:4100）
pnpm typecheck:agent  # TypeScript 类型检查
pnpm test:agent       # vitest：transport / E2E / cancel / resume / 安全门禁
pnpm build:agent      # 编译到 dist/
```

测试全部使用 deterministic mock model（`test-mock`），绝不调用真实 DeepSeek API。
真实模型接入需要同时配置 `MATH_AI_DEEPSEEK_API_KEY` 与
`MATH_AI_AGENT_PROVIDER=deepseek-official`（见仓库根 `.env.example`）。

## HTTP 接口（machine-to-machine）

- `POST /v1/run`、`POST /v1/stream`、`POST /v1/cancel`、`POST /v1/resume`
- `GET /v1/sessions/:id`、`GET /health`、`GET /capabilities`

所有端点要求 `Authorization: Bearer <MATH_AI_AGENT_SERVICE_TOKEN>`，未配置 token 时 fail closed。
