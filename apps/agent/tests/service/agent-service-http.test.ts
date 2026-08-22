/**
 * Agent Service HTTP 层认证门禁（Prompt 2.5 §8）。
 *
 * FastAPI -> Agent Service 方向（MATH_AI_AGENT_SERVICE_TOKEN）：
 *   missing -> fail closed（401）
 *   wrong   -> fail closed（401）
 *   correct -> success
 *   未配置 token 时 -> fail closed（401）
 * 同时覆盖：错误响应不包含 token、payload 校验、未知路由。
 * 测试不启动真实 Harness（fake runtime），只验证 HTTP 边界。
 */
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import type { Server } from "node:http";
import { createAgentService, listenAgentService, type AgentService } from "../../src/index.js";
import type { DeepSeekHarnessRuntime } from "../../src/runtime/dsh-runtime.js";
import type { TeacherAgentHealth, TeacherAgentCapabilities, TeacherAgentRunResult } from "../../src/runtime/types.js";

const SERVICE_TOKEN = "service-token-http-test";

function fakeRuntime(): DeepSeekHarnessRuntime {
  const health: TeacherAgentHealth = {
    status: "ok",
    runtime: "dsh",
    initialized: true,
    model_configured: false,
    tool_registry_ready: true,
    visible_tool_count: 7,
    runtime_version: "0.1.0",
    dsh_version: "0.1.0-rc.6",
  };
  const capabilities: TeacherAgentCapabilities = {
    run: true,
    stream: true,
    cancel: true,
    resume: true,
    get_session: true,
    health: true,
    model_configured: false,
    visible_tool_names: ["search_questions"],
    runtime_version: "0.1.0",
  };
  return {
    runtimeName: "dsh",
    runtimeVersion: "0.1.0",
    run: async () => ({ run_id: "run_1", session_id: "tch_1", request_id: "req_1", runtime: "dsh", status: "completed", final_text: "", tool_calls: [], error: null } satisfies TeacherAgentRunResult),
    stream: async function* () {
      // 测试不消费 stream 事件。
    },
    cancel: async () => ({ run_id: "run_1", session_id: "tch_1", request_id: "req_1", runtime: "dsh", status: "cancelled", final_text: "", tool_calls: [], error: null }),
    resume: async () => ({ run_id: "run_2", session_id: "tch_1", request_id: "req_2", runtime: "dsh", status: "completed", final_text: "", tool_calls: [], error: null }),
    getSession: async (sessionId: string) => ({
      session_id: sessionId,
      runtime: "dsh",
      status: "idle",
      created_at: 0,
      updated_at: 0,
      run_ids: [],
      teacher_user_id: null,
      tenant_id: null,
    }),
    health: async () => health,
    capabilities: async () => capabilities,
    dispose: async () => {},
  } as unknown as DeepSeekHarnessRuntime;
}

describe("Agent Service HTTP 认证门禁（MATH_AI_AGENT_SERVICE_TOKEN）", () => {
  let service: AgentService;
  let url: string;
  let server: Server;

  beforeAll(async () => {
    service = createAgentService({
      env: {
        ...process.env,
        MATH_AI_AGENT_SERVICE_TOKEN: SERVICE_TOKEN,
        MATH_AI_TOOL_GATEWAY_TOKEN: "gateway-token-http-test",
        MATH_AI_AGENT_PROVIDER: "test-mock",
        MATH_AI_AGENT_MODEL: "mock-model",
        MATH_AI_AGENT_PORT: "0",
      },
      runtime: fakeRuntime(),
    });
    server = service.server;
    url = await listenAgentService(service);
  });

  afterAll(async () => {
    await service.close();
  });

  async function get(path: string, token?: string): Promise<{ status: number; text: string }> {
    const headers: Record<string, string> = {};
    if (token !== undefined) headers.authorization = `Bearer ${token}`;
    const res = await fetch(`${url}${path}`, { headers });
    return { status: res.status, text: await res.text() };
  }

  it("missing token -> 401 fail closed（结构化错误，不泄漏配置）", async () => {
    const { status, text } = await get("/health");
    expect(status).toBe(401);
    const payload = JSON.parse(text) as { error?: { code: string } };
    expect(payload.error?.code).toBe("TOOL_UNAUTHORIZED");
    expect(text).not.toContain(SERVICE_TOKEN);
  });

  it("wrong token -> 401 fail closed", async () => {
    const { status, text } = await get("/health", "wrong-token-value");
    expect(status).toBe(401);
    expect(text).not.toContain(SERVICE_TOKEN);
  });

  it("correct token -> success（health 正常返回）", async () => {
    const { status, text } = await get("/health", SERVICE_TOKEN);
    expect(status).toBe(200);
    const payload = JSON.parse(text) as { status: string; visible_tool_count: number };
    expect(payload.status).toBe("ok");
    expect(payload.visible_tool_count).toBe(7);
  });

  it("未配置 token 时一律 fail closed", async () => {
    const unconfigured = createAgentService({
      env: {
        ...process.env,
        MATH_AI_AGENT_SERVICE_TOKEN: "",
        MATH_AI_TOOL_GATEWAY_TOKEN: "gateway-token-http-test",
        MATH_AI_AGENT_PORT: "0",
      },
      runtime: fakeRuntime(),
    });
    const unconfiguredUrl = await listenAgentService(unconfigured);
    try {
      const { status, text } = await getOn(unconfiguredUrl, "/health");
      expect(status).toBe(401);
      expect(text).not.toContain("gateway-token-http-test");
    } finally {
      await unconfigured.close();
    }
    async function getOn(base: string, path: string): Promise<{ status: number; text: string }> {
      const res = await fetch(`${base}${path}`, { headers: { authorization: `Bearer ${SERVICE_TOKEN}` } });
      return { status: res.status, text: await res.text() };
    }
  });

  it("run payload 校验：非法 user_message -> 400，合法 -> 200", async () => {
    const bad = await fetch(`${url}/v1/run`, {
      method: "POST",
      headers: { authorization: `Bearer ${SERVICE_TOKEN}`, "content-type": "application/json" },
      body: JSON.stringify({ user_message: "" }),
    });
    expect(bad.status).toBe(400);
    const badText = await bad.text();
    expect(badText).not.toContain(SERVICE_TOKEN);

    const good = await fetch(`${url}/v1/run`, {
      method: "POST",
      headers: { authorization: `Bearer ${SERVICE_TOKEN}`, "content-type": "application/json" },
      body: JSON.stringify({ user_message: "找题", request_id: "req_http_1" }),
    });
    expect(good.status).toBe(200);
    const payload = (await good.json()) as { status: string };
    expect(payload.status).toBe("completed");
  });

  it("stream 客户端断开会取消同一个在途 run", async () => {
    let release: () => void = () => undefined;
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    const cancelledRuns: string[] = [];
    const runtime = fakeRuntime();
    runtime.stream = async function* () {
      yield {
        type: "run_started",
        run_id: "run_stream_close",
        session_id: "tch_stream_close",
        request_id: "req_stream_close",
        data: {},
        sequence: 0,
        created_at: Date.now(),
      };
      await held;
    };
    runtime.cancel = async (runId: string) => {
      cancelledRuns.push(runId);
      release();
      return {
        run_id: runId,
        session_id: "tch_stream_close",
        request_id: "req_stream_close",
        runtime: "dsh",
        status: "cancelled",
        final_text: "",
        tool_calls: [],
        error: null,
      };
    };
    const cancellable = createAgentService({
      env: {
        ...process.env,
        MATH_AI_AGENT_SERVICE_TOKEN: SERVICE_TOKEN,
        MATH_AI_TOOL_GATEWAY_TOKEN: "gateway-token-http-test",
        MATH_AI_AGENT_PROVIDER: "test-mock",
        MATH_AI_AGENT_MODEL: "mock-model",
        MATH_AI_AGENT_PORT: "0",
      },
      runtime,
    });
    const cancellableUrl = await listenAgentService(cancellable);
    const controller = new AbortController();
    try {
      const response = await fetch(`${cancellableUrl}/v1/stream`, {
        method: "POST",
        headers: {
          authorization: `Bearer ${SERVICE_TOKEN}`,
          "content-type": "application/json",
        },
        body: JSON.stringify({ user_message: "找题", request_id: "req_stream_close" }),
        signal: controller.signal,
      });
      const reader = response.body?.getReader();
      expect(reader).toBeDefined();
      const first = await reader!.read();
      expect(new TextDecoder().decode(first.value)).toContain("run_stream_close");
      controller.abort();
      await reader!.closed.catch(() => undefined);
      await vi.waitFor(() => expect(cancelledRuns).toEqual(["run_stream_close"]));
    } finally {
      controller.abort();
      release();
      await cancellable.close();
    }
  });

  it("未知路由 -> 404 结构化错误", async () => {
    const { status, text } = await get("/v1/nope", SERVICE_TOKEN);
    expect(status).toBe(404);
    expect(text).not.toContain(SERVICE_TOKEN);
  });
});
