/**
 * DeepSeekHarnessRuntime E2E（deterministic mock model）。
 *
 * 这些测试真正穿过 DeepSeek Harness（boot -> Cordis plugin -> agent loop ->
 * mock adapter -> tool -> HTTP gateway stub），不 mock DeepSeekHarnessRuntime.run()。
 * 绝不调用真实 DeepSeek API（Prompt 2 §28）。
 */
import { afterEach, describe, expect, it } from "vitest";
import { ToolGatewayClient } from "../../src/transport/gateway-client.js";
import { DeepSeekHarnessRuntime } from "../../src/runtime/dsh-runtime.js";
import { makeTestConfig } from "../helpers/test-env.js";
import {
  createRuntimeHarness,
  searchResponse,
  SEARCH_ROUTE,
  GET_QUESTION_ROUTE,
  type RuntimeHarness,
} from "../helpers/runtime-harness.js";

describe("DeepSeekHarnessRuntime deterministic E2E", () => {
  let harness: RuntimeHarness;

  afterEach(async () => {
    if (harness) await harness.close();
  });

  it("run() 真正穿过 DSH：mock 模型 -> search_questions -> 网关契约 -> 结构化结果", async () => {
    harness = await createRuntimeHarness({
      handlers: {
        [SEARCH_ROUTE]: () =>
          searchResponse([
            {
              question_id: "q_1",
              stem: "若 x+2=5，求 x。",
              question_type: "fill_in_blank",
              knowledge_points: ["kp_linear"],
              difficulty: 1,
              verification_status: "verified",
              source_status: "commercial_safe",
              visibility: "private",
            },
          ]),
      },
    });

    const result = await harness.runtime.run({
      user_message: "帮我找 x+2=5 的题目",
      request_id: "req_e2e_1",
    });

    expect(result.runtime).toBe("dsh");
    expect(result.status).toBe("completed");
    expect(result.error).toBeNull();
    expect(result.run_id).toMatch(/^run_/);
    expect(result.session_id).toMatch(/^tch_/);

    expect(result.tool_calls).toHaveLength(1);
    const call = result.tool_calls[0];
    expect(call?.tool_name).toBe("search_questions");
    expect(call?.status).toBe("ok");
    expect(call?.input).toEqual({ query: "x+2=5", limit: 5 });
    const searchOutput = call?.output as { ok: boolean; total: number; items: Array<{ question_id: string; verification_status: string; visibility: string }>; request_id: string };
    expect(searchOutput?.ok).toBe(true);
    expect(searchOutput?.total).toBe(1);
    expect(searchOutput?.items[0]?.question_id).toBe("q_1");
    expect(searchOutput?.items[0]?.verification_status).toBe("verified");
    expect(searchOutput?.items[0]?.visibility).toBe("private");
    expect(searchOutput?.request_id).toBe("req_stub_search");
    expect(result.final_text).toContain("已根据工具返回的结构化结果完成查询");

    // 网关 stub 确实收到 M2M Bearer 请求（HTTP 层穿过 FastAPI 契约）。
    const gatewayCall = harness.stub.requests.find((r) => r.route === SEARCH_ROUTE);
    expect(gatewayCall?.authorization).toBe("Bearer test-gateway-token");
    expect(gatewayCall?.requestId).toMatch(/^req_/);

    // session 记录包含本次 run。
    const session = await harness.runtime.getSession(result.session_id);
    expect(session.status).toBe("idle");
    expect(session.run_ids).toContain(result.run_id);
  });

  it("stream() 发出产品自有事件词汇表，不泄漏 DSH 原始事件", async () => {
    harness = await createRuntimeHarness({
      handlers: { [SEARCH_ROUTE]: () => searchResponse() },
    });

    const types: string[] = [];
    for await (const event of harness.runtime.stream({ user_message: "找题", request_id: "req_stream_1" })) {
      types.push(event.type);
      expect(event.run_id).toMatch(/^run_/);
      expect(event.session_id).toMatch(/^tch_/);
      expect(event.request_id).toBe("req_stream_1");
      expect(event.sequence).toBeGreaterThanOrEqual(0);
      expect(event.created_at).toBeTypeOf("number");
    }
    expect(types).toContain("run_started");
    expect(types).toContain("tool_started");
    expect(types).toContain("tool_finished");
    expect(types).toContain("run_completed");
    expect(types).not.toContain("turn/start");
    expect(types).not.toContain("assistant/chunk");
  });

  it("domain 失败以结构化 JSON 返回，不抛异常（get_question 404 映射）", async () => {
    harness = await createRuntimeHarness({
      handlers: {
        [GET_QUESTION_ROUTE]: () => ({
          status: 404,
          body: { code: "TOOL_NOT_FOUND", message: "题目不存在", request_id: "req_nf" },
        }),
      },
      mockScript: {
        steps: [{ kind: "tool", toolName: "get_question", arguments: { question_id: "q_missing" } }],
        finalText: "该题不存在。",
      },
    });

    const result = await harness.runtime.run({ user_message: "读取 q_missing", request_id: "req_domain_1" });
    expect(result.status).toBe("completed");
    expect(result.tool_calls).toHaveLength(1);
    const call = result.tool_calls[0];
    expect(call?.tool_name).toBe("get_question");
    expect(call?.status).toBe("ok");
    expect(call?.output?.ok).toBe(false);
    const domainError = (call?.output as { error: { code: string; message: string } })?.error;
    expect(domainError?.code).toBe("TOOL_NOT_FOUND");
    expect(domainError?.message).toBe("题目不存在");
  });

  it("非 mock provider 且未配置 key 时快速失败 MODEL_UNAVAILABLE，不产生网关请求", async () => {
    harness = await createRuntimeHarness({
      handlers: { [SEARCH_ROUTE]: () => searchResponse() },
    });

    const config = makeTestConfig({ provider: "deepseek-official" });
    const gateway = new ToolGatewayClient({
      origin: harness.stub.url,
      token: config.toolGatewayToken,
      timeoutMs: config.toolTimeoutMs,
    });
    const runtime = new DeepSeekHarnessRuntime({ config, gateway });

    const result = await runtime.run({ user_message: "hi", request_id: "req_model_1" });
    expect(result.status).toBe("failed");
    expect(result.error?.code).toBe("MODEL_UNAVAILABLE");
    expect(harness.stub.requests).toHaveLength(0);
    await runtime.dispose();
  });

  it("health / capabilities 报告 5 个可见工具，且不包含任何凭据字段", async () => {
    harness = await createRuntimeHarness({ handlers: { [SEARCH_ROUTE]: () => searchResponse() } });

    const health = await harness.runtime.health();
    expect(health.status).toBe("ok");
    expect(health.runtime).toBe("dsh");
    expect(health.initialized).toBe(true);
    expect(health.tool_registry_ready).toBe(true);
    expect(health.visible_tool_count).toBe(5);
    expect(health.dsh_version).toBe("0.1.0-rc.6");

    const capabilities = await harness.runtime.capabilities();
    expect(capabilities.run).toBe(true);
    expect(capabilities.stream).toBe(true);
    expect(capabilities.cancel).toBe(true);
    expect(capabilities.resume).toBe(true);
    expect(capabilities.get_session).toBe(true);
    expect(capabilities.visible_tool_names.sort()).toEqual([
      "find_similar_questions",
      "get_curriculum_node",
      "get_question",
      "search_questions",
      "verify_question",
    ]);

    const serialized = JSON.stringify({ health, capabilities });
    expect(serialized).not.toContain("test-gateway-token");
    expect(serialized).not.toContain("test-agent-service-token");
  });
});
