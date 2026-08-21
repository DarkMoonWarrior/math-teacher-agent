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

export const ERROR_GUIDANCE: Record<string, string> = {
  FEATURE_DISABLED: "请在 FastAPI 环境开启 Search Agent 功能后重试。",
  UNSUPPORTED_CAPABILITY: "当前 Runtime 不支持这条工作流，请切换至 DeepSeek Harness Runtime。",
  RUNTIME_UNAVAILABLE: "请确认 Agent Service 已启动，并且模型配置可用。",
  MODEL_UNAVAILABLE: "模型服务当前不可用；系统不会把未完成任务伪装成成功。",
  TOOL_UNAUTHORIZED: "内部工具权限校验失败，请检查 FastAPI 与 Agent Service 的 M2M 配置。",
  TOOL_VALIDATION_ERROR: "受控工具拒绝了当前参数，请调整搜题描述后重试。",
  TOOL_EXECUTION_ERROR: "受控工具未能完成任务，请保留请求编号后重试。",
  NETWORK_ERROR: "请确认 FastAPI 已启动，并检查 Teacher Web 到业务服务的内部地址配置。",
  STREAM_UNAVAILABLE: "请确认反向代理允许 text/event-stream 响应。",
  STREAM_INVALID: "服务返回的事件格式不完整，请保留错误编号并重试。",
  STREAM_INTERRUPTED: "连接可能短暂中断；重新尝试不会使用未完成的结果。",
  STREAM_RECOVERY_FAILED: "系统没有重新执行搜索；请确认服务恢复后手动重试。",
  TOOL_TIMEOUT: "受控工具或 Agent 运行超过时间限制，请缩小条件后重试。",
};
