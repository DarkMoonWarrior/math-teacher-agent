/**
 * Tool Loop / Cost Gate（Prompt 3.5 §16）。
 *
 * Mock 模型反复请求 search_questions：
 *   - 达到 searchToolCallLimit 硬上限 -> run 终止，返回 SEARCH_PLAN_EXHAUSTED；
 *   - 不产生无限调用（不会出现无限循环 / 无界费用）。
 * 绝不调用真实 DeepSeek API；网关 stub 固定返回空结果。
 */
import { afterEach, describe, expect, it } from "vitest";
import { createRuntimeHarness, searchResponse, SEARCH_ROUTE, type RuntimeHarness } from "../helpers/runtime-harness.js";

describe("Search tool loop / cost gate", () => {
  let harness: RuntimeHarness;

  afterEach(async () => {
    if (harness) await harness.close();
  });

  it("repeated search_questions calls are capped with SEARCH_PLAN_EXHAUSTED", async () => {
    const steps = Array.from({ length: 20 }, (_, index) => ({
      kind: "tool" as const,
      toolName: "search_questions",
      arguments: { query: `椭圆 ${index}`, limit: 5 },
    }));
    harness = await createRuntimeHarness({
      handlers: { [SEARCH_ROUTE]: () => searchResponse([]) },
      mockScript: { steps, finalText: "搜索完成。" },
      searchToolCallLimit: 6,
    });

    const result = await harness.runtime.run({
      user_message: "给我找椭圆题",
      request_id: "req_loop_1",
    });

    expect(result.status).toBe("failed");
    expect(result.error?.code).toBe("SEARCH_PLAN_EXHAUSTED");
    const searches = result.tool_calls.filter((call) => call.tool_name === "search_questions");
    expect(searches.length).toBeGreaterThan(0);
    expect(searches.length).toBeLessThanOrEqual(6);
    expect(result.tool_calls.every((call) => call.tool_name === "search_questions")).toBe(true);
    // 网关收到的 search 请求数同样受上限约束。
    const gatewayHits = harness.stub.requests.filter((request) => request.route === SEARCH_ROUTE);
    expect(gatewayHits.length).toBeLessThanOrEqual(6);
  });
});