"use client";

/** 教师面向的字段标签映射：内部 domain 字段名一律不直接展示。 */
export const FIELD_LABELS: Record<string, string> = {
  grade: "年级",
  volume: "教材",
  chapter: "章节",
  section: "小节",
  knowledge_points: "知识点",
  sub_knowledge_points: "子知识点",
  question_types: "题型",
  difficulty: "难度",
  difficulty_range: "难度",
  year: "年份",
  regions: "地区",
  teaching_usage: "教学用途",
  source_preferences: "来源偏好",
  require_verified: "验证要求",
  exclude_question_ids: "排除题目",
  count: "题量",
};

export const DIFFICULTY_LABELS: Record<number, string> = {
  1: "基础",
  2: "中等偏易",
  3: "中等",
  4: "中等偏难",
  5: "较难",
};

export const QUESTION_TYPE_LABELS: Record<string, string> = {
  single_choice: "选择题",
  multiple_choice: "多选题",
  fill_blank: "填空题",
  true_false: "判断题",
  solution: "解答题",
};

export const USAGE_LABELS: Record<string, string> = {
  classroom_example: "课堂例题",
  in_class_practice: "课堂练习",
  homework: "课后作业",
  exam_review: "复习",
  diagnostic: "诊断",
  warm_up: "热身",
  challenge: "挑战题",
  general: "通用",
};

export const CONFIDENCE_LABELS: Record<string, string> = {
  high: "高",
  medium: "中",
  low: "低",
};

const VERIFICATION_LABELS: Record<string, string> = {
  passed: "程序验证通过",
  program_verified: "程序验证通过",
  teacher_review_approved: "教师复核通过",
  teacher_review_required: "需要教师复核",
  needs_math_review: "待数学验算",
  needs_formula_review: "待公式校正",
  source_inconsistency_detected: "来源待核查",
};

export type TrustTone = "ok" | "warn" | "alert" | "none";

export function trustTone(value: string): TrustTone {
  if (value === "passed" || value === "program_verified" || value === "teacher_review_approved") return "ok";
  if (value === "teacher_review_required" || value === "needs_math_review" || value === "needs_formula_review") return "warn";
  if (value === "source_inconsistency_detected") return "alert";
  return "none";
}

export function verificationLabel(value: string): string {
  return VERIFICATION_LABELS[value] ?? (value ? value : "尚未验证");
}

export function TrustBadge({ value }: { value: string }) {
  const tone = trustTone(value);
  const label = verificationLabel(value);
  const mark = tone === "ok" ? "✓" : tone === "warn" ? "◐" : tone === "alert" ? "!" : "○";
  return <span className={`search-agent-trust ${tone}`} title={`验证状态：${value || "unverified"}`}><b aria-hidden="true">{mark}</b>{label}</span>;
}

export function MatchBadge({ relaxed }: { relaxed: boolean }) {
  return relaxed
    ? <span className="search-agent-match relaxed">≈ 相近条件补充</span>
    : <span className="search-agent-match exact">✓ 完全匹配</span>;
}

const SOURCE_LABELS: Record<string, string> = {
  commercial_granted: "来源已记录",
  public_permissive: "来源公开可核实",
  question_content_user_declared_usable: "来源已记录",
  rights_unclear: "权利待审核",
};

export function sourceLabel(value: string): string {
  return SOURCE_LABELS[value] ?? (value ? value : "来源信息暂缺");
}

export function difficultyLabel(value: number): string {
  return DIFFICULTY_LABELS[value] ?? `难度 ${value}`;
}

export function questionTypeLabel(value: string): string {
  return QUESTION_TYPE_LABELS[value] ?? value;
}

/** 内部节点 id（kp_xxx 等）不能作为教师主文本；返回 true 表示该值不应直接展示。 */
export function isInternalNodeId(value: unknown): boolean {
  return typeof value === "string" && /^kp_[0-9a-z_]+$/i.test(value);
}

/** 把知识点约束中的内部 id 换成教材名称；无名称对应的 id 直接剔除。 */
export function translateKnowledgePointValues(values: unknown, names: string[]): string[] {
  const list = Array.isArray(values) ? values.map(String) : typeof values === "string" ? [values] : [];
  const namePool = new Set(names.map((name) => name.trim()).filter(Boolean));
  const out: string[] = [];
  for (const item of list) {
    if (isInternalNodeId(item)) {
      for (const name of names) if (namePool.has(name) && !out.includes(name)) out.push(name);
      continue;
    }
    if (item.trim() && !out.includes(item.trim())) out.push(item.trim());
  }
  return out;
}

export function formatFieldValue(field: string, value: unknown, knowledgePointNames: string[] = []): string {
  if (value === null || value === undefined || value === "") return "—";
  if (field === "knowledge_points") {
    const translated = translateKnowledgePointValues(value, knowledgePointNames);
    return translated.length ? translated.join("、") : "—";
  }
  if (field === "difficulty_range" && Array.isArray(value) && value.length === 2) {
    return `${difficultyLabel(Number(value[0]))}～${difficultyLabel(Number(value[1]))}`;
  }
  if (field === "teaching_usage") return USAGE_LABELS[String(value)] ?? String(value);
  if (Array.isArray(value)) return value.map(String).join("、");
  return String(value);
}

export function fieldLabel(field: string): string {
  return FIELD_LABELS[field] ?? field;
}

export function matchConfidenceLabel(value: string): string {
  return CONFIDENCE_LABELS[value] ?? (value ? value : "—");
}