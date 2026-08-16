import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { ToolGatewayClient } from "../../src/transport/gateway-client.js";
import { createGatewayStub, gatewayJson, waitFor, type GatewayStub } from "../helpers/gateway-stub.js";

const SEARCH_ROUTE = "/internal/agent-tools/v1/search-questions";
const GET_QUESTION_ROUTE = "/internal/agent-tools/v1/get-question";

describe("ToolGatewayClient", () => {
  let stub: GatewayStub;
  let client: ToolGatewayClient;

  beforeAll(async () => {
    stub = await createGatewayStub();
    client = new ToolGatewayClient({ origin: stub.url, token: "gw-secret", timeoutMs: 5000 });
  });

  afterAll(async () => {
    await stub.close();
  });

  it("解析成功响应并回传 request_id / M2M 头", async () => {
    stub.handlers[SEARCH_ROUTE] = () =>
      gatewayJson(200, {
        items: [
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
        ],
        total: 1,
        truncated: false,
        query_interpretation: { query: "x+2=5" },
        request_id: "req_stub_search",
      });
    const result = await client.searchQuestions({ query: "x+2=5", limit: 5 }, { requestId: "req_client_1" });
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.data.total).toBe(1);
    expect(result.data.items[0]?.question_id).toBe("q_1");
    expect(result.request_id).toBe("req_stub_search");
    const call = stub.requests.find((request) => request.route === SEARCH_ROUTE);
    expect(call?.authorization).toBe("Bearer gw-secret");
    expect(call?.requestId).toBe("req_client_1");
  });

  it("把 401 映射为 TOOL_UNAUTHORIZED 结构化错误", async () => {
    stub.handlers[GET_QUESTION_ROUTE] = () =>
      gatewayJson(401, { code: "TOOL_UNAUTHORIZED", message: "缺少 service token", request_id: "req_auth" });
    const result = await client.getQuestion("q_1", { requestId: "req_a" });
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.error.code).toBe("TOOL_UNAUTHORIZED");
    expect(result.error.message).toBe("缺少 service token");
  });

  it("把 404 映射为 TOOL_NOT_FOUND", async () => {
    stub.handlers[GET_QUESTION_ROUTE] = () => gatewayJson(404, { code: "TOOL_NOT_FOUND", message: "题目不存在", request_id: "req_nf" });
    const result = await client.getQuestion("q_1", { requestId: "req_b" });
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.error.code).toBe("TOOL_NOT_FOUND");
  });

  it("把 422 映射为 TOOL_VALIDATION_ERROR", async () => {
    stub.handlers[GET_QUESTION_ROUTE] = () => gatewayJson(422, { code: "TOOL_VALIDATION_ERROR", message: "参数错误", request_id: "req_val" });
    const result = await client.getQuestion("q_1", { requestId: "req_c" });
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.error.code).toBe("TOOL_VALIDATION_ERROR");
  });

  it("把 504 映射为 TOOL_TIMEOUT", async () => {
    stub.handlers[GET_QUESTION_ROUTE] = () => gatewayJson(504, { code: "TOOL_TIMEOUT", message: "工具调用超时", request_id: "req_timeout" });
    const result = await client.getQuestion("q_1", { requestId: "req_d" });
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.error.code).toBe("TOOL_TIMEOUT");
  });

  it("把 500 映射为 TOOL_EXECUTION_ERROR", async () => {
    stub.handlers[GET_QUESTION_ROUTE] = () => gatewayJson(500, { code: "TOOL_EXECUTION_ERROR", message: "内部失败", request_id: "req_boom" });
    const result = await client.getQuestion("q_1", { requestId: "req_e" });
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.error.code).toBe("TOOL_EXECUTION_ERROR");
  });

  it("客户端超时返回 TOOL_TIMEOUT", async () => {
    stub.handlers[GET_QUESTION_ROUTE] = async () => {
      await new Promise((resolve) => setTimeout(resolve, 500));
      return gatewayJson(200, { ok: true });
    };
    const shortClient = new ToolGatewayClient({ origin: stub.url, token: "gw-secret", timeoutMs: 100 });
    const result = await shortClient.getQuestion("q_1", { requestId: "req_f" });
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.error.code).toBe("TOOL_TIMEOUT");
  });

  it("调用方 AbortSignal 能中止在途请求并抛出 AbortError", async () => {
    stub.handlers[GET_QUESTION_ROUTE] = () => new Promise(() => undefined);
    const controller = new AbortController();
    const pending = client.getQuestion("q_1", { requestId: "req_g", signal: controller.signal });
    setTimeout(() => controller.abort(), 30);
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
    await waitFor(() => stub.abortedRequests.includes(GET_QUESTION_ROUTE));
  });
});
