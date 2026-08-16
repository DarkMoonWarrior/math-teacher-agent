/**
 * 测试配置工厂：临时 session root + test-mock provider，绝不触碰真实 DeepSeek API。
 */
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { loadAgentServiceConfig } from "../../src/config/env.js";
import type { AgentServiceConfig } from "../../src/config/env.js";

export interface TestConfigOptions {
  toolGatewayToken?: string;
  deepseekApiKey?: string;
  provider?: string;
  model?: string;
  runHardTimeoutMs?: number;
}

export function makeTestConfig(options: TestConfigOptions = {}): AgentServiceConfig {
  const sessionRoot = mkdtempSync(path.join(tmpdir(), "mta-agent-sessions-"));
  return loadAgentServiceConfig({
    ...process.env,
    MATH_AI_API_INTERNAL_URL: "http://127.0.0.1:1",
    MATH_AI_TOOL_GATEWAY_TOKEN: options.toolGatewayToken ?? "test-gateway-token",
    MATH_AI_AGENT_SERVICE_TOKEN: "test-agent-service-token",
    MATH_AI_DEEPSEEK_API_KEY: options.deepseekApiKey ?? "",
    MATH_AI_AGENT_PROVIDER: options.provider ?? "test-mock",
    MATH_AI_AGENT_MODEL: options.model ?? "mock-model",
    MATH_AI_AGENT_SESSION_ROOT: sessionRoot,
    MATH_AI_AGENT_RUN_HARD_TIMEOUT_MS: String(options.runHardTimeoutMs ?? 60_000),
    MATH_AI_AGENT_PORT: "0",
  });
}
