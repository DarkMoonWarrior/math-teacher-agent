/**
 * Search Agent 场景的 deterministic DSH E2E（Prompt 3）。
 *
 * 真正穿过 DeepSeek Harness：mock 模型 -> search_questions -> get_question ->
 * 网关 stub -> 结构化结果。绝不调用真实 DeepSeek API。
 * 同时验证 M5 开始后 model-visible tool allowlist 仍为精确受控集合。
 */
import { afterEach, describe, expect, it } from "vitest";
import { TEACHER_TOOL_ALLOWLIST } from "../../src/tools/teacher-tools.js";
import {
  createRuntimeHarness,
  searchResponse,
  SEARCH_ROUTE,
  GET_QUESTION_ROUTE,
  type RuntimeHarness,
} from "../helpers/runtime-harness.js";

const SEARCH_ITEM = {
  question_id: "q_sa_focus_01",
  stem: "已知椭圆 x²/25+y²/16=1，过右焦点 F 且斜率为 1 的直线与椭圆交于 A、B 两点，求焦点弦 AB 的长度。",
  question_type: "single_choice",
  knowledge_points: ["kp_s1_3_1_01"],
  difficulty: 3,
  verification_status: "passed",
  source_status: "question_content_user_declared_usable",
  visibility: "private",
};

describe("Search Agent deterministic harness scenario", () => {
  let harness: RuntimeHarness;

  afterEach(async () => {
    if (harness) await harness.close();
  });

  it("teacher search flow runs through DSH with only allowlisted tools", async () => {
    harness = await createRuntimeHarness({
      handlers: {
        [SEARCH_ROUTE]: () => searchResponse([SEARCH_ITEM]),
        [GET_QUESTION_ROUTE]: () => ({
          status: 200,
          body: {
            question_id: "q_sa_focus_01",
            stem: SEARCH_ITEM.stem,
            question_type: "single_choice",
            answer: "A",
            solution_steps: [],
            verification_status: "passed",
            visibility: "private",
            source_status: "question_content_user_declared_usable",
            request_id: "req_stub_get",
          },
        }),
      },
      mockScript: {
        steps: [
          { kind: "tool", toolName: "search_questions", arguments: { query: "椭圆 焦点弦", limit: 5 } },
          { kind: "tool", toolName: "get_question", arguments: { question_id: "q_sa_focus_01" } },
        ],
        finalText: "已根据工具返回的结构化结果找到题目 q_sa_focus_01。",
      },
    });

    const result = await harness.runtime.run({
      user_message: "给我找5道高二椭圆焦点弦，中等偏难，适合课堂例题",
      request_id: "req_search_scenario_1",
    });

    expect(result.status).toBe("completed");
    expect(result.error).toBeNull();
    expect(result.tool_calls.map((call) => call.tool_name)).toEqual([
      "search_questions",
      "get_question",
    ]);
    expect(result.tool_calls.every((call) => call.status === "ok")).toBe(true);

    const searchCall = result.tool_calls[0];
    expect(searchCall?.input).toEqual({ query: "椭圆 焦点弦", limit: 5 });
    const output = searchCall?.output as { items: Array<{ question_id: string }>; total: number };
    expect(output.items[0]?.question_id).toBe("q_sa_focus_01");
    expect(result.final_text).toContain("q_sa_focus_01");

    // 网关 stub 实际收到 M2M 请求（跨 HTTP 边界）。
    const gatewayCalls = harness.stub.requests.filter(
      (request) => request.route === SEARCH_ROUTE || request.route === GET_QUESTION_ROUTE,
    );
    expect(gatewayCalls).toHaveLength(2);
    for (const call of gatewayCalls) {
      expect(call.authorization).toBe("Bearer test-gateway-token");
    }

    // M5 新增 Solve Tool 后可见工具仍必须是精确受控集合。
    expect(TEACHER_TOOL_ALLOWLIST).toEqual([
      "search_questions",
      "get_question",
      "solve_question",
      "find_similar_questions",
      "verify_question",
      "get_curriculum_node",
      "inspect_private_library",
      "search_private_library",
      "create_question_draft",
    ]);
  });
});
