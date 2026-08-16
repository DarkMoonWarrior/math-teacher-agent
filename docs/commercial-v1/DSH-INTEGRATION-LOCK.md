# DSH Integration Lock

DeepSeek Harness 集成版本锁定与升级策略。任何升级前必须重读本文件并更新记录。

- 记录日期：2026-08-16（Prompt 2 验收后更新）
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
| @deepseek-ai/dsh-session | 0.1.0-rc.6 | MIT | Session 事件词汇表 / SessionId |
| @deepseek-ai/dsh-session-persistence | 0.1.0-rc.6 | MIT | session 持久化接口 |
| @deepseek-ai/dsh-session-persistence-jsonl | 0.1.0-rc.6 | MIT | 官方 session 持久化（resume 依赖） |
| @deepseek-ai/dsh-tools | 0.1.0-rc.6 | MIT | `ctx.tools.register` / `defineTool` / 执行管线 |
| @deepseek-ai/dsh-llm | 0.1.0-rc.6 | MIT | `LlmAdapter` / StreamChunk / ToolSchema |
| @deepseek-ai/dsh-llm-deepseek | 0.1.0-rc.6 | MIT | 官方 DeepSeek provider adapter（可选 smoke） |
| @deepseek-ai/dsh-system-prompt | 0.1.0-rc.6 | MIT | system prompt 服务 |
| @deepseek-ai/cordis | 4.0.1 | MIT | 插件容器 |
| @deepseek-ai/cordis-plugin-loader | 1.0.2 | MIT | Loader（boot 前置） |
| @deepseek-ai/cordis-plugin-include | 1.0.6 | MIT | entry-list 配置方言（app-boot 已内置实现） |
| @deepseek-ai/schemastery | 3.18.1 | MIT | Tool 参数/output schema |

注：`@deepseek-ai/dsh-tools` 的 npm `latest` dist-tag 是 `0.0.1-rc.1`（BSD-3-Clause），
与 dsh 0.1.0-rc.6 配套的版本挂在 `next` dist-tag 上且版本号为 `0.1.0-rc.6`。
本仓库明确 pin `0.1.0-rc.6`（与其余 dsh 包同一 rc 线），不允许跟随 `latest` 漂移。
**实测修正**：已安装的 rc.6 包 LICENSE 全文为 MIT（2026-08-16 直接读取核对），
此前记录中的 rc.6 BSD-3-Clause 说法不成立，`docs/legal/THIRD-PARTY-LICENSES.md` 已按 MIT 记录。

## Node 要求

- 官方声明：`^22.19.0 || >=24.0.0`（取自 dsh 发行包元数据）。
- 本仓库 `apps/agent/package.json` 声明 `"node": ">=24.0.0"`。
- 本地开发环境实测：Node v24.17.0。
- 现有 `apps/web`（Next.js 16）不因 Harness 升级工具链。

## 精确版本策略

- 所有 `@deepseek-ai/*` 依赖使用精确版本（无 `^`、无 `~`、无 `latest`）。
- 禁止 pnpm/renovate 自动升级 rc 依赖；升级必须人工审查官方 changelog/release 后再改 lock。
- Harness breaking-change 影响面必须保持在 `apps/agent/src/dsh/` 内。

## npm 来源核验（Prompt 2.5，2026-08-16）

全部直接依赖均来自**官方 npm namespace `@deepseek-ai`**（registry.npmjs.org），
无第三方 fork、镜像重打包或非官方 tarball。

| Package | Exact version | npm dist-tag | resolved tarball (registry.npmjs.org) | integrity (sha512) | license | upstream repository |
| --- | --- | --- | --- | --- | --- | --- |
| @deepseek-ai/dsh（CLI，仅版本参照） | 0.1.0-rc.6 | latest, next | .../dsh/-/dsh-0.1.0-rc.6.tgz | 已锁 | MIT | github.com/deepseek-ai/deepseek-harness |
| @deepseek-ai/dsh-app-boot | 0.1.0-rc.6 | latest, next | .../dsh-app-boot/-/dsh-app-boot-0.1.0-rc.6.tgz | 已锁 | MIT | 同上 |
| @deepseek-ai/dsh-agent / dsh-agent-loop | 0.1.0-rc.6 | latest, next | 官方 tarball | 已锁 | MIT | 同上 |
| @deepseek-ai/dsh-llm / dsh-llm-deepseek | 0.1.0-rc.6 | next | 官方 tarball | 已锁 | MIT | 同上 |
| @deepseek-ai/dsh-session / dsh-session-persistence / dsh-session-persistence-jsonl | 0.1.0-rc.6 | next | 官方 tarball | 已锁 | MIT | 同上 |
| @deepseek-ai/dsh-system-prompt / dsh-tools | 0.1.0-rc.6 | next | 官方 tarball | 已锁 | MIT | 同上 |
| @deepseek-ai/cordis | 4.0.1 | latest | 官方 tarball | 已锁 | MIT | 同上 |
| @deepseek-ai/cordis-plugin-include / cordis-plugin-loader | 1.0.6 / 1.0.2 | latest | 官方 tarball | 已锁 | MIT | 同上 |
| @deepseek-ai/schemastery | 3.18.1 | latest | 官方 tarball | 已锁 | MIT | 同上 |

核验方式：`npm view <pkg> dist-tags/versions` + registry 元数据（name/version/dist.tarball/
dist.integrity/license/repository/publish_time）。全部发布时间为 2026-08-13，
maintainers 为 deepseek 官方账号（imccyu / tianyicui-deepseek）。
lockfile 中 71 条 `@deepseek-ai/*` 条目全部精确版本、均含 sha512 integrity，
无 `latest` / `*` / 不受控 git URL / `file:` / `link:` 来源（脚本核验，NO ISSUES）。

### GitHub master 与 npm 发布差异（如实记录，不当作错误隐藏）

- Published package version：**0.1.0-rc.6**（npm，2026-08-13 发布，latest+next 均为 rc.6）。
- GitHub master（default branch `master`）`apps/cli/package.json` 观察版本：**0.1.0-rc.5**
  （2026-08-16 通过 GitHub API 复核；最近一次触碰该文件的 commit abe560f，2026-08-13）。
- 另外：`0.1.0-rc.5` 从未出现在 npm registry 版本列表中（registry 中只有 0.0.1-rc.5），
  说明 GitHub master 与 npm 发布线当前不同步。
- upstream source commit for rc.6 = **unresolved**（npm 包元数据未嵌入 git SHA，
  无法可靠把 rc.6 映射到具体上游 commit；不猜测）。
- Node engines：rc.6 发布元数据**未声明 engines**（已核验所有直接依赖）；
  此前记录的 `^22.19.0 || >=24.0.0` 来自早期 DSH 发布资料，当前无法从元数据复核，
  本仓库按自有的 `engines: >=24.0.0` 锁定并在 Node v24.17.0 实测通过（状态：REVIEW）。

## 官方扩展机制（我们只使用这些）

- `boot(binName, absoluteConfigPath, patches?, prepare?)`：Cordis Loader 启动；runtime 通过官方 patch 覆盖 session root。
- Cordis plugin：`apply(ctx, config)`、`ctx.plugin(...)`、服务注入。
- `ctx.tools.register(definition)` + `defineTool({name, description, parameters, output, execute})`。
- Tool 执行上下文 `exec.signal`（取消传播到 HTTP 请求）。
- `ctx.llm.registerAdapter(providers, LlmAdapter)`：provider adapter（测试用 deterministic mock）。
- `AgentRegistry.create({sessionId, meta, agentOptions})` → `{agent, dispose}`。
- `AgentRegistry.resume({resumeSessionId, agentOptions})`：官方公开 resume API。
- `agent.followup(message)` / `agent.whenIdle()` / `agent.cancel(cause)`。
- `ctx.tools.schemas()`：model-visible tool schema（allowlist 安全门禁的验证依据）。
- `ctx.on("session/event", ...)`：会话事件映射为产品自有词汇表。

## 不使用 / 禁止

- 不修改 agent loop core；不 patch 内部私有路径。
- 不使用 `dsh-base` bundle（其默认挂载 bash/pwsh/fs/web/subagent 等能力）。
- 不依赖 `@deepseek-ai/dsh-headless`（npm 版本 0.0.1-rc.1 与 rc.6 主线不匹配）。
- 不使用未公开 internal API。

## 实测兼容性要点（Prompt 2 验收，rc.6）

1. 配置 YAML 中 `disabled: !!js "<expr>"` 的表达式必须加引号，否则被 YAML 解析为双重标签而失败。
2. `boot` 的 pnpm 目录缺少 `node-addon-require-builtin`，组合条目指向相对 `./plugins/*.mjs`
   薄封装（`config/plugins/`）即可稳定解析；插件 `name` 字段需与文件路径一致。
3. 工具执行中止时，`fetch` 的 rejection reason 可能是普通对象而非标准 `AbortError`；
   统一以调用方 `signal.aborted` 判定取消（`transport/gateway-client.ts`）。
4. `agent.cancel({kind:'user'})` 能中止在途工具请求；`turn/end` 事件可能晚于
   `agent.whenIdle()` 解析，取消状态由 runtime 自身 `cancelled` 标志定局。
5. Node 24 下服务端 `req.destroyed` 在请求体消费完成后即为 true，测试 stub 以
   `res.destroyed`/`res.writableEnded` 判定响应是否仍可发送。
6. `capabilities.resume` 依赖 `ctx.get("sessionPersistence")` 存在；未挂载持久化时为 false。

## 已知 breaking-change 风险

1. `dsh-tools` 的 latest/next dist-tag 版本线不一致（见上），升级时两线必须整体核验。
2. `SESSION_FORMAT_VERSION` 当前为 0，官方声明 rc 期间不保证日志兼容（见 dsh-session 文档）。
3. rc 版本之间 patch/config 行语义可能变化（例如 base bundle 行 id 重命名）。
4. 官方 CLI `dsh` 依赖面很大（bash/pwsh/subagent 等），我们只依赖最小包集合，
   任一 rc 升级都可能造成我们的最小组合失效，必须全量重跑 Prompt 2 安全门禁。

## 升级政策

- 升级 = 单独 commit：改 `apps/agent/package.json` 精确版本 + `pnpm-lock.yaml` + 本文件 +
  `docs/legal/THIRD-PARTY-LICENSES.md`。
- 升级后必须重跑：`apps/agent` 全部测试（transport / E2E / cancel / resume / allowlist 门禁）、
  backend 全量 pytest、`pnpm typecheck:web`、`pnpm build:web`。
- 任何 allowlist 测试失败 = blocker，不得合并。

## 环境变量（只在 Agent Service 环境内）

- `MATH_AI_DEEPSEEK_API_KEY`：仅 Agent Service 读取（官方 adapter `apiKeyEnv` 指向它）。
- 无 key 时：Agent Service 正常启动，`health` 报告 `model_configured=false`，run 返回 `MODEL_UNAVAILABLE`。
- `MATH_AI_AGENT_PROVIDER` / `MATH_AI_AGENT_MODEL`：provider 路由与模型 ID（默认 test-mock / mock-model）。
