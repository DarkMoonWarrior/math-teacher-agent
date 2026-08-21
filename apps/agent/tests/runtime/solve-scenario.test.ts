/**
 * Solve Agent 第一条 vertical slice：mock model -> solve_question -> FastAPI gateway contract.
 * 只验证受控 Tool seam 与可信状态透传，不让 Harness 自行宣称数学验证。
 */
import { afterEach, describe, expect, it } from "vitest";
import {
  createRuntimeHarness,
  SOLVE_QUESTION_ROUTE,
  type RuntimeHarness,
} from "../helpers/runtime-harness.js";

describe("Solve Agent deterministic harness scenario", () => {
  let harness: RuntimeHarness;

  afterEach(async () => {
    if (harness) await harness.close();
  });

  it("runs through the allowlisted solve tool and preserves teacher-review status", async () => {
    harness = await createRuntimeHarness({
      handlers: {
        [SOLVE_QUESTION_ROUTE]: ({ body }) => ({
          status: 200,
          body: {
            question_text: body.question_text,
            solution_mode: "standard",
            explanation: {
              method: "代数法",
              steps: ["移项并合并同类项。", "解得 x=2。"],
              final_answer: "x=2",
            },
            knowledge_points: ["一元一次方程"],
            common_mistakes: ["移项时忘记变号"],
            teaching_notes: ["教师复核后使用"],
            confidence_status: "teacher_review_required",
            verification_evidence: ["答案与解析由大模型生成，尚未经过独立数学程序或第二模型复核。"],
            provider: "fake_model",
            model: "fake-solver-v1",
            mode: "live_ai",
            matched_question_id: null,
            match_score: null,
            alternative_available: true,
            warnings: ["请由教师核对后再用于教学。"],
            request_id: "req_stub_solve",
          },
        }),
      },
      mockScript: {
        steps: [
          {
            kind: "tool",
            toolName: "solve_question",
            arguments: { question_text: "解方程 2x-4=0。", solution_mode: "standard" },
          },
        ],
        finalText: "已返回待教师复核的解题草稿。",
      },
    });

    const result = await harness.runtime.run({
      user_message: "请解方程 2x-4=0。",
      request_id: "req_solve_scenario_1",
    });

    expect(result.status).toBe("completed");
    expect(result.tool_calls.map((call) => call.tool_name)).toEqual(["solve_question"]);
    const output = result.tool_calls[0]?.output as {
      confidence_status: string;
      verification_evidence: string[];
    };
    expect(output.confidence_status).toBe("teacher_review_required");
    expect(output.verification_evidence.join(" ")).toContain("尚未经过独立数学程序");
    expect(result.final_text).not.toContain("程序验证通过");

    const call = harness.stub.requests.find((request) => request.route === SOLVE_QUESTION_ROUTE);
    expect(call?.authorization).toBe("Bearer test-gateway-token");
  });

  it("returns a structured review-required failure when no model is available", async () => {
    harness = await createRuntimeHarness({
      handlers: {
        [SOLVE_QUESTION_ROUTE]: () => ({
          status: 503,
          body: {
            code: "MODEL_UNAVAILABLE",
            message: "当前没有可用的可信题库解析或解题模型。",
            retryable: true,
            request_id: "req_stub_solve_unavailable",
          },
        }),
      },
      mockScript: {
        steps: [
          {
            kind: "tool",
            toolName: "solve_question",
            arguments: { question_text: "求函数 f(x)=x^2 的最小值。" },
          },
        ],
        finalText: "当前无法生成可信解答，请稍后重试或补充已验证题库内容。",
      },
    });

    const result = await harness.runtime.run({
      user_message: "求函数 f(x)=x^2 的最小值。",
      request_id: "req_solve_scenario_unavailable",
    });

    expect(result.status).toBe("completed");
    const output = result.tool_calls[0]?.output as {
      ok: boolean;
      confidence_status: string;
      error: { code: string; message: string };
    };
    expect(output.ok).toBe(false);
    expect(output.confidence_status).toBe("teacher_review_required");
    expect(output.error.code).toBe("MODEL_UNAVAILABLE");
    expect(output.error.message).not.toContain("fake-solver");
  });
});
