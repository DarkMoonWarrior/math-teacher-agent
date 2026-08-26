import { afterEach, describe, expect, it } from "vitest";
import {
  CREATE_QUESTION_DRAFT_ROUTE,
  createRuntimeHarness,
  type RuntimeHarness,
} from "../helpers/runtime-harness.js";


describe("Private Question Authoring deterministic harness scenario", () => {
  let harness: RuntimeHarness;

  afterEach(async () => {
    if (harness) await harness.close();
  });

  it("calls exactly the unsaved draft tool and preserves owner-only state", async () => {
    harness = await createRuntimeHarness({
      handlers: {
        [CREATE_QUESTION_DRAFT_ROUTE]: ({ body }) => ({
          status: 200,
          body: {
            draft: {
              draft_id: "qad_synthetic_1",
              request_text: (body.brief as Record<string, unknown>).request_text,
              question_type: (body.brief as Record<string, unknown>).question_type,
              stem_plain: "已知函数 f(x)=x²，判断其单调性。",
              stem_latex: "已知函数 $f(x)=x^2$，判断其单调性。",
              options: [
                { key: "A", text: "恒增" },
                { key: "B", text: "先减后增" },
                { key: "C", text: "恒减" },
                { key: "D", text: "不是函数" },
              ],
              answer_value: "B",
              solution_method: "定义法",
              solution_steps: ["分区间判断。"],
              final_answer: "先减后增。",
              authoring_intent: "考查函数单调性。",
              curriculum: {
                node_id: body.curriculum_node_id,
                name: "函数单调性的判断",
                volume: "必修第一册",
                chapter: "函数",
                section: "单调性",
                mapping_source: "teacher_selected",
                match_confidence: 1,
                curriculum_status: "reviewed",
                reviewed_by: "teacher",
              },
              target_difficulty: body.target_difficulty,
              estimated_difficulty: 2,
              difficulty_source: "model_estimated",
              verification: {
                status: "teacher_review_required",
                math_verifier_status: "unsupported",
                math_verifier_checked: false,
                teacher_review_required: true,
                verifier_version: "math-v0.3.0",
                checks: [
                  { code: "solvability", status: "inconclusive", capability: "unsupported", evidence_source: "none", summary: "可解性待复核", details: [] },
                  { code: "answer_solution_consistency", status: "passed", capability: "supported", evidence_source: "deterministic_structure", summary: "答案表达一致", details: [] },
                  { code: "choice_answer_cardinality", status: "passed", capability: "supported", evidence_source: "deterministic_structure", summary: "答案数量合格", details: [] },
                  { code: "distractor_quality", status: "inconclusive", capability: "unsupported", evidence_source: "none", summary: "干扰项待复核", details: [] },
                  { code: "math_verifier", status: "inconclusive", capability: "unsupported", evidence_source: "none", summary: "MathVerifier 不支持", details: [] },
                  { code: "difficulty_disclosure", status: "passed", capability: "supported", evidence_source: "model_estimate", summary: "难度已披露", details: [] },
                ],
                details: ["结构检查不等于完整数学验证。"],
              },
              source_type: "ai_generated",
              visibility: "owner_only",
              public_search_allowed: false,
              share_allowed: false,
              commercial_use_allowed: false,
              model_training_allowed: false,
              saved: false,
              provider: "synthetic_provider",
              model: "synthetic-author-v1",
              prompt_revision: "question-authoring-v1",
              warnings: ["必须由教师复核。"],
              created_at: "2026-08-24T00:00:00+00:00",
            },
            request_id: "req_tool_authoring",
          },
        }),
      },
    });
    const brief = {
      request_text: "围绕函数单调性命制一道单选题。",
      curriculum_node_id: "kp_monotonicity",
      question_type: "single_choice",
      target_difficulty: 2,
      teaching_purpose: "课堂练习",
      assessed_method: "",
      misconception_requirements: "",
      additional_constraints: "",
    };
    const progressId = "qap_authoring_scenario_1234567890";
    const toolInput = { ...brief, progress_id: progressId };
    const result = await harness.runtime.run({
      user_message: [
        "必须且只能调用一次 create_question_draft。",
        `命题请求JSON：${JSON.stringify(toolInput)}`,
      ].join("\n"),
      request_id: "req_authoring_scenario",
    });

    expect(result.status).toBe("completed");
    expect(result.tool_calls.map((call) => call.tool_name)).toEqual(["create_question_draft"]);
    expect(result.tool_calls[0]?.input).toEqual(toolInput);
    const output = result.tool_calls[0]?.output as {
      draft: { visibility: string; saved: boolean; verification: { status: string } };
    };
    expect(output.draft).toMatchObject({
      visibility: "owner_only",
      saved: false,
      verification: { status: "teacher_review_required" },
    });
    const call = harness.stub.requests.find(
      (request) => request.route === CREATE_QUESTION_DRAFT_ROUTE,
    );
    expect(call?.body).toEqual({ brief, progress_id: progressId });
    expect(call?.body).not.toHaveProperty("owner_id");
    expect(call?.body).not.toHaveProperty("publish");
    expect(call?.body).not.toHaveProperty("save");
  });
});
