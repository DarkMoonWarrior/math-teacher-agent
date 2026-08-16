/**
 * Agent Service 配置：全部来自环境变量，任何 secret 不得写入本仓库。
 * 只允许配置好的固定内部地址，模型/用户不得提供 URL。
 */
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";

const require = createRequire(import.meta.url);

export interface AgentServiceConfig {
  /** FastAPI 内部地址（Agent -> FastAPI Tool Gateway 的唯一允许 origin）。 */
  apiInternalUrl: string;
  /** Agent -> FastAPI 的 machine-to-machine token。 */
  toolGatewayToken: string;
  /** FastAPI -> Agent Service 的 machine-to-machine token。 */
  agentServiceToken: string;
  /** 真实 DeepSeek API Key（仅 Agent Service 环境可见；缺省即不启用真实 provider）。 */
  deepseekApiKey: string;
  /** Harness provider route：有 key 时为 deepseek-official，测试为 test-mock。 */
  provider: string;
  /** Provider-owned model id。 */
  model: string;
  /** 默认 session 持久化根目录（绝对路径，gitignored）。 */
  sessionRoot: string;
  /** 每个 Tool 调用的 HTTP 超时（毫秒）。 */
  toolTimeoutMs: number;
  /** 单次 run 的硬性时间上限（毫秒），防止失控 run 永久占用进程。 */
  runHardTimeoutMs: number;
  /** HTTP 服务监听地址。 */
  host: string;
  /** HTTP 服务监听端口（0 = 随机端口，测试用）。 */
  port: number;
  /** 工作目录（agent session 元数据 cwd）。 */
  cwd: string;
  /** DSH 精确锁定版本（用于 health 报告）。 */
  dshVersion: string;
}

const DEFAULT_SESSION_ROOT = path.resolve(
  fileURLToPath(new URL("../../../../", import.meta.url)),
  "data",
  "runtime",
  "agent-sessions",
);

function positiveInt(name: string, fallback: number): number {
  const raw = process.env[name];
  if (raw === undefined || raw === "") return fallback;
  const parsed = Number.parseInt(raw, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

export function loadAgentServiceConfig(env: NodeJS.ProcessEnv = process.env): AgentServiceConfig {
  let dshVersion = "0.1.0-rc.6";
  try {
    dshVersion = require("@deepseek-ai/dsh-tools/package.json").version as string;
  } catch {
    // 保持默认锁定版本；依赖缺失时 boot 会在启动阶段明确失败。
  }
  return {
    apiInternalUrl: (env.MATH_AI_API_INTERNAL_URL ?? "http://127.0.0.1:8000").replace(/\/+$/, ""),
    toolGatewayToken: env.MATH_AI_TOOL_GATEWAY_TOKEN ?? "",
    agentServiceToken: env.MATH_AI_AGENT_SERVICE_TOKEN ?? "",
    deepseekApiKey: env.MATH_AI_DEEPSEEK_API_KEY ?? "",
    provider: env.MATH_AI_AGENT_PROVIDER ?? (env.MATH_AI_DEEPSEEK_API_KEY ? "deepseek-official" : "test-mock"),
    model: env.MATH_AI_AGENT_MODEL ?? (env.MATH_AI_DEEPSEEK_API_KEY ? "deepseek-v4-flash" : "mock-model"),
    sessionRoot: path.resolve(env.MATH_AI_AGENT_SESSION_ROOT ?? DEFAULT_SESSION_ROOT),
    toolTimeoutMs: positiveInt("MATH_AI_AGENT_TOOL_TIMEOUT_MS", 30_000),
    runHardTimeoutMs: positiveInt("MATH_AI_AGENT_RUN_HARD_TIMEOUT_MS", 120_000),
    host: env.MATH_AI_AGENT_HOST ?? "127.0.0.1",
    port: positiveInt("MATH_AI_AGENT_PORT", 4100),
    cwd: path.resolve(env.MATH_AI_AGENT_CWD ?? process.cwd()),
    dshVersion,
  };
}

