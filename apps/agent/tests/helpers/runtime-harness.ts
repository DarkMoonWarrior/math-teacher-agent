/**
 * 测试辅助：一条命令创建 gateway stub + ToolGatewayClient + DeepSeekHarnessRuntime。
 * 每个测试文件自建实例（独立临时 sessionRoot），保证隔离。
 */
import { createGatewayStub, type GatewayStub, type StubHandler } from "./gateway-stub.js";
import { ToolGatewayClient } from "../../src/transport/gateway-client.js";
import { DeepSeekHarnessRuntime } from "../../src/runtime/dsh-runtime.js";
import { makeTestConfig } from "./test-env.js";
import type { AgentServiceConfig } from "../../src/config/env.js";
import type { MockScript } from "../../src/dsh/mock-provider.js";

export interface RuntimeHarness {
  stub: GatewayStub;
  gateway: ToolGatewayClient;
  runtime: DeepSeekHarnessRuntime;
  config: AgentServiceConfig;
  close: () => Promise<void>;
}

export interface RuntimeHarnessOptions {
  handlers?: Partial<Record<string, StubHandler>>;
  mockScript?: MockScript;
  sessionRoot?: string;
  sessionIdPrefix?: string;
}

export async function createRuntimeHarness(options: RuntimeHarnessOptions = {}): Promise<RuntimeHarness> {
  const stub = await createGatewayStub({ handlers: options.handlers });
  const config = makeTestConfig();
  if (options.sessionRoot) config.sessionRoot = options.sessionRoot;
  const gateway = new ToolGatewayClient({
    origin: stub.url,
    token: config.toolGatewayToken,
    timeoutMs: config.toolTimeoutMs,
  });
  const runtime = new DeepSeekHarnessRuntime({
    config,
    gateway,
    mockScript: options.mockScript,
  });
  return {
    stub,
    gateway,
    runtime,
    config,
    close: async () => {
      await runtime.dispose();
      await stub.close();
    },
  };
}

export const SEARCH_ROUTE = "/internal/agent-tools/v1/search-questions";
export const GET_QUESTION_ROUTE = "/internal/agent-tools/v1/get-question";

export function searchResponse(items: unknown[] = [], total: number = items.length): { status: number; body: unknown } {
  return {
    status: 200,
    body: {
      items,
      total,
      truncated: false,
      query_interpretation: null,
      request_id: "req_stub_search",
    },
  };
}
