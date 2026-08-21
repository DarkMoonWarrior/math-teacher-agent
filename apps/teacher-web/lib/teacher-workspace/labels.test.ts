import { describe, expect, it } from "vitest";
import {
  ERROR_GUIDANCE,
  questionTypeLabel,
  sourceLabel,
  verificationLabel,
  verificationTone,
} from "./labels";

describe("Teacher Workspace labels", () => {
  it("uses the actual QuestionBank vocabulary for trusted Search results", () => {
    expect(questionTypeLabel("single_choice")).toBe("单选题");
    expect(questionTypeLabel("fill_blank")).toBe("填空题");
    expect(verificationLabel("passed")).toBe("程序验证通过");
    expect(verificationTone("passed")).toBe("trusted");
    expect(sourceLabel("commercial_granted")).toBe("已获商业使用授权");
    expect(sourceLabel("question_content_user_declared_usable")).toBe("使用权由上传者声明");
  });

  it("never gives an unverified or conflicting status a trusted tone", () => {
    expect(verificationLabel("needs_math_review")).toBe("需要数学复核");
    expect(verificationLabel("needs_formula_review")).toBe("需要公式复核");
    expect(verificationLabel("teacher_review_required")).toBe("需要教师复核");
    expect(verificationLabel("source_inconsistency_detected")).toBe("来源答案存在冲突");
    expect(verificationTone("needs_math_review")).toBe("review");
    expect(verificationTone("source_inconsistency_detected")).toBe("review");
  });

  it("provides explicit guidance for model, permission, validation and Tool failures", () => {
    expect(ERROR_GUIDANCE.NETWORK_ERROR).toContain("内部地址配置");
    expect(ERROR_GUIDANCE.MODEL_UNAVAILABLE).toContain("不会把未完成任务伪装成成功");
    expect(ERROR_GUIDANCE.TOOL_UNAUTHORIZED).toContain("权限校验失败");
    expect(ERROR_GUIDANCE.TOOL_VALIDATION_ERROR).toContain("拒绝了当前参数");
    expect(ERROR_GUIDANCE.TOOL_EXECUTION_ERROR).toContain("请求编号");
  });
});
