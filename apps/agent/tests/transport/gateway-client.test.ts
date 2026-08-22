import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { ToolGatewayClient } from "../../src/transport/gateway-client.js";
import { createGatewayStub, gatewayJson, waitFor, type GatewayStub } from "../helpers/gateway-stub.js";

const SEARCH_ROUTE = "/internal/agent-tools/v1/search-questions";
const GET_QUESTION_ROUTE = "/internal/agent-tools/v1/get-question";
const SOLVE_QUESTION_ROUTE = "/internal/agent-tools/v1/solve-question";
const INSPECT_PRIVATE_LIBRARY_ROUTE = "/internal/agent-tools/v1/inspect-private-library";

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

  it("只通过固定 solve-question route 返回可信分层结果", async () => {
    stub.handlers[SOLVE_QUESTION_ROUTE] = ({ body }) =>
      gatewayJson(200, {
        question_text: body.question_text,
        solution_mode: "standard",
        explanation: { method: "题库标准解法", steps: ["由等式性质求解。"], final_answer: "x=3" },
        knowledge_points: ["一元一次方程"],
        common_mistakes: [],
        teaching_notes: [],
        confidence_status: "program_verified",
        math_verification: {
          status: "passed",
          capability: "supported",
          scope: "question_answer",
          evidence_source: "math_verifier",
          method: "linear_equation",
          computed_answer: "x=3",
          source_answer: "x=3",
          details: ["独立计算与题库答案一致。"],
          verifier_version: "math-v0.3.0",
        },
        verification_evidence: ["题库记录标记为已通过独立数学验证。"],
        provider: "verified_question_bank",
        model: "independent-math-verifier",
        mode: "verified_bank",
        matched_question_id: "q_1",
        matched_question_revision_count: 2,
        match_score: 1,
        alternative_available: false,
        warnings: [],
        request_id: "req_stub_solve",
      });
    const result = await client.solveQuestion(
      { question_text: "若 x+2=5，求 x。", solution_mode: "standard" },
      { requestId: "req_solve_1" },
    );
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.data.confidence_status).toBe("program_verified");
    expect(result.data.math_verification.status).toBe("passed");
    expect(result.data.math_verification.scope).toBe("question_answer");
    expect(result.data.mode).toBe("verified_bank");
    expect(result.data.matched_question_revision_count).toBe(2);
    const call = stub.requests.find((request) => request.route === SOLVE_QUESTION_ROUTE);
    expect(call?.authorization).toBe("Bearer gw-secret");
    expect(call?.body).toEqual({ question_text: "若 x+2=5，求 x。", solution_mode: "standard" });
  });

  it("只通过固定 route 读取不含私人正文的资料库概览", async () => {
    stub.handlers[INSPECT_PRIVATE_LIBRARY_ROUTE] = ({ body }) =>
      gatewayJson(200, {
        total: 3,
        pending_review: 2,
        confirmed: 1,
        needs_ocr: 1,
        trashed: 1,
        by_file_kind: { pdf: 2, docx: 1 },
        visibility: "private",
        content_included: false,
        request_id: "req_stub_library",
      });

    const result = await client.inspectPrivateLibrary({ requestId: "req_library_1" });

    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.data.total).toBe(3);
    expect(result.data.content_included).toBe(false);
    expect(result.data.visibility).toBe("private");
    const call = stub.requests.find((request) => request.route === INSPECT_PRIVATE_LIBRARY_ROUTE);
    expect(call?.body).toEqual({});
    expect(call?.authorization).toBe("Bearer gw-secret");
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
