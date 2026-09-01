const QUESTION_TYPES: Record<string, string> = {
  choice: "选择题",
  single_choice: "单选题",
  multiple_choice: "多选题",
  fill_blank: "填空题",
  solution: "解答题",
  proof: "证明题",
};

const VERIFICATION: Record<string, string> = {
  passed: "程序验证通过",
  verified: "程序验证通过",
  human_verified: "教师审核通过",
  reviewed: "教师已复核",
  pending: "等待数学验证",
  unverified: "需要教师复核",
  teacher_review_required: "需要教师复核",
  needs_math_review: "需要数学复核",
  needs_formula_review: "需要公式复核",
  source_inconsistency_detected: "来源答案存在冲突",
};

const SOURCE_STATUS: Record<string, string> = {
  commercial_granted: "已获商业使用授权",
  public_permissive: "公开来源可核实",
  question_content_user_declared_usable: "使用权由上传者声明",
  rights_unclear: "权利状态待审核",
};

export function questionTypeLabel(value: string): string {
  return QUESTION_TYPES[value] ?? (value || "题型未标注");
}

export function difficultyLabel(value: number): string {
  if (value <= 2) return "基础";
  if (value === 3) return "中等";
  if (value === 4) return "较难";
  return "难";
}

export function verificationLabel(value: string): string {
  return VERIFICATION[value] ?? "验证状态未标注";
}

export function sourceLabel(value: string): string {
  return SOURCE_STATUS[value] ?? "来源状态待确认";
}

export function verificationTone(value: string): "trusted" | "review" {
  return ["passed", "verified", "human_verified", "reviewed"].includes(value)
    ? "trusted"
    : "review";
}

const SOLUTION_CONFIDENCE: Record<string, string> = {
  program_verified: "题库解析 · 程序验证通过",
  model_reviewed: "模型复核 · 不等于程序验证",
  teacher_review_required: "模型新解 · 需要教师复核",
};

const VERIFICATION_SCOPE: Record<string, string> = {
  question_answer: "验证覆盖题目答案",
  matched_question_record: "证据仅覆盖匹配题库记录",
  generated_solution: "证据范围为本次生成解答",
};

const EVIDENCE_SOURCE: Record<string, string> = {
  math_verifier: "MathVerifier 独立证据",
  teacher_evidence: "教师核验记录",
  stored_status: "题库既有状态",
  none: "暂无独立验证证据",
};

export function solutionConfidenceLabel(value: string): string {
  return SOLUTION_CONFIDENCE[value] ?? "解答可信等级未标注";
}

export function solutionConfidenceTone(value: string): "trusted" | "review" {
  return value === "program_verified" ? "trusted" : "review";
}

export function mathVerificationLabel(status: string, capability: string): string {
  if (capability === "unsupported") return "当前 MathVerifier 不支持此范围";
  if (status === "passed") return "独立数学验证通过";
  if (status === "failed") return "独立数学验证未通过";
  return "独立数学验证结果不确定";
}

export function verificationScopeLabel(value: string): string {
  return VERIFICATION_SCOPE[value] ?? "验证范围未标注";
}

export function evidenceSourceLabel(value: string): string {
  return EVIDENCE_SOURCE[value] ?? "证据来源未标注";
}

export const ERROR_GUIDANCE: Record<string, string> = {
  FEATURE_DISABLED: "请在 FastAPI 环境开启相应 Agent 功能后重试。",
  UNSUPPORTED_CAPABILITY: "当前运行环境不支持这条工作流，请切换至可用的大模型运行环境。",
  RUNTIME_UNAVAILABLE: "请确认 Agent Service 已启动，并且模型配置可用。",
  MODEL_UNAVAILABLE: "模型服务当前不可用；系统不会把未完成任务伪装成成功。",
  TOOL_UNAUTHORIZED: "内部工具权限校验失败，请检查 FastAPI 与 Agent Service 的 M2M 配置。",
  TOOL_VALIDATION_ERROR: "受控工具拒绝了当前参数，请调整任务描述后重试。",
  VERIFICATION_FAILED: "独立数学验证发现冲突；系统不会用模型内容覆盖该证据。",
  VERIFICATION_INCONCLUSIVE: "现有证据不足以确认解答；请补充题目条件或由教师复核。",
  TOOL_EXECUTION_ERROR: "受控工具未能完成任务，请保留请求编号后重试。",
  NETWORK_ERROR: "请确认 FastAPI 已启动，并检查 Teacher Web 到业务服务的内部地址配置。",
  STREAM_UNAVAILABLE: "请确认反向代理允许 text/event-stream 响应。",
  STREAM_INVALID: "服务返回的事件格式不完整，请保留错误编号并重试。",
  STREAM_INTERRUPTED: "连接可能短暂中断；重新尝试不会使用未完成的结果。",
  STREAM_RECOVERY_FAILED: "系统没有重复执行原任务；请确认服务恢复后手动重试。",
  TOOL_TIMEOUT: "受控工具或 Agent 运行超过时间限制，请缩小条件后重试。",
};
