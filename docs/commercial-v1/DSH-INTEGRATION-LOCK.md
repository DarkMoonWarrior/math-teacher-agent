# DSH Integration Lock

DeepSeek Harness 集成版本锁定与升级策略。任何升级前必须重读本文件并更新记录。

- 记录日期：2026-08-16
- 状态：Developer Preview（`0.1.0-rc.*`），官方明确提示可能发生 breaking changes
- 官方仓库：https://github.com/deepseek-ai/deepseek-harness
- 本仓库定位：只在 `apps/agent/` 内通过官方公开扩展机制使用（`boot`、Cordis plugin、`ctx.tools.register`、`defineTool`、`LlmAdapter`、`AgentRegistry.create/resume`）。不复制、不 vendor、不修改 Harness core。

## 采用版本（2026-08-16 官方 npm registry 实测）

| Package | Version | License | 用途 |
| --- | --- | --- | --- |
| @deepseek-ai/dsh | 0.1.0-rc.6 | MIT | 仅版本参照；不直接依赖 CLI 包 |
| @deepseek-ai/dsh-app-boot | 0.1.0-rc.6 | MIT | Cordis boot（`boot()`） |
| @deepseek-ai/dsh-agent | 0.1.0-rc.6 | MIT | `ctx.agents` 注册表 + Agent 接口 |
| @deepseek-ai/dsh-agent-loop | 0.1.0-rc.6 | MIT | AgentFactory 实现（create/resume） |
| @deepseek-ai/dsh-agent-default-model | 0.1.0-rc.6 | MIT | 默认模型选择 |
| @deepseek-ai/dsh-session | 0.1.0-rc.6 | MIT | Session 事件词汇表 / SessionId |
| @deepseek-ai/dsh-session-persistence-jsonl | 0.1.0-rc.6 | MIT | 官方 session 持久化（resume 依赖） |
| @deepseek-ai/dsh-tools | 0.1.0-rc.6 | MIT | `ctx.tools.register` / `defineTool` / 执行管线 |
| @deepseek-ai/dsh-llm | 0.1.0-rc.6 | MIT | `LlmAdapter` / StreamChunk / ToolSchema |
| @deepseek-ai/dsh-llm-deepseek | 0.1.0-rc.6 | MIT | 官方 DeepSeek provider adapter（可选 smoke） |
| @deepseek-ai/cordis | 4.0.1 | MIT | 插件容器 |
| @deepseek-ai/cordis-plugin-loader | 1.0.2 | MIT | Loader（boot 前置） |
| @deepseek-ai/cordis-plugin-include | 1.0.6 | MIT | entry-list 配置方言（app-boot 已内置实现） |
| @deepseek-ai/schemastery | 3.18.1 | MIT | Tool 参数/output schema |

注：`@deepseek-ai/dsh-tools` 的 npm `latest` dist-tag 是 `0.0.1-rc.1`（BSD-3-Clause），
与 dsh 0.1.0-rc.6 配套的版本挂在 `next` dist-tag 上且版本号为 `0.1.0-rc.6`。
本仓库明确 pin `0.1.0-rc.6`（与其余 dsh 包同一 rc 线），不允许跟随 `latest` 漂移。
该版本 LICENSE 为 BSD-3-Clause，已在 `THIRD_PARTY_NOTICES.md` 记录。

## Node 要求

- 官方声明：`^22.19.0 || >=24.0.0`（取自 dsh 发行包元数据；engines 声明位于 apps/cli 包）。
- 本仓库 `apps/agent/package.json` 声明 `"node": ">=24.0.0"`。
- 本地开发环境实测：Node v24.17.0。
- 现有 `apps/web`（Next.js 16）不因 Harness 升级工具链。

## 精确版本策略

- 所有 `@deepseek-ai/*` 依赖使用精确版本（无 `^`、无 `~`、无 `latest`）。
- 禁止 pnpm/renovate 自动升级 rc 依赖；升级必须人工审查官方 changelog/release 后再改 lock。
- Harness breaking-change 影响面必须保持在 `apps/agent/src/dsh/` 内。

## 官方扩展机制（我们只使用这些）

- `boot(binName, configPath, patches?, prepare?)`：Cordis Loader 启动。
- Cordis plugin：`apply(ctx, config)`、`ctx.plugin(...)`、服务注入。
- `ctx.tools.register(definition)` + `defineTool({name, description, parameters, output, execute})`。
- Tool 执行上下文 `exec.signal: AbortSignal`（取消传播）。
- `ctx.llm.registerAdapter(providers, LlmAdapter)`：provider adapter（测试用 deterministic mock）。
- `AgentRegistry.create({sessionId, meta, agentOptions, setup})` → `{agent, dispose}`。
- `AgentRegistry.resume({resumeSessionId, agentOptions, setup})`：官方公开 resume API。
- `agent.followup(message)` / `agent.whenIdle()` / `agent.cancel(cause)` / `agent.session.events`。
- `ctx.tools.schemas(scope?)`：model-visible tool schema（allowlist 安全门禁的验证依据）。

## 不使用 / 禁止

- 不修改 agent loop core；不 patch 内部私有路径。
- 不使用 `dsh-base` bundle（其默认挂载 bash/pwsh/fs/web/subagent 等能力）。
- 不依赖 `@deepseek-ai/dsh-headless`（一次性 CLI runner，语义与我们需要的可控 session 生命周期不符）。
- 不使用未公开 internal API（`ToolRuntimeScheduler`、`@internal` 符号等）。

## 已知 breaking-change 风险

1. `dsh-tools` 的 latest/next dist-tag 版本线不一致（见上），升级时两线必须整体核验。
2. `SESSION_FORMAT_VERSION` 当前为 0，官方声明 rc 期间不保证日志兼容（见 dsh-session 文档）。
3. rc 版本之间 patch/config 行语义可能变化（例如 base bundle 行 id 重命名）。
4. 官方 CLI `dsh` 依赖面很大（bash/pwsh/subagent 等），我们只依赖上面列出的最小包集合，
   任一 rc 升级都可能造成我们的最小组合失效，必须全量重跑 Prompt 2 安全门禁。

## 升级政策

- 升级 = 单独 commit：改 `apps/agent/package.json` 精确版本 + `pnpm-lock.yaml` + 本文件 + `THIRD_PARTY_NOTICES.md`。
- 升级后必须重跑：`apps/agent` 全部单测、DSH mock E2E、tool allowlist 门禁、cancellation E2E、backend 159+ 测试。
- 任何 allowlist 测试失败 = blocker，不得合并。

## 环境变量（只在 Agent Service 环境内）

- `MATH_AI_DEEPSEEK_API_KEY`：仅 Agent Service 读取（官方 adapter `apiKeyEnv` 指向它）。
- 无 key 时：Agent Service 正常启动，`health` 报告 `model_configured=false`，run 返回 `MODEL_UNAVAILABLE`。
