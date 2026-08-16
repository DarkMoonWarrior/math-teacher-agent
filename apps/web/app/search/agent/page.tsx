"use client";

import Link from "next/link";
import { FormEvent, useRef, useState } from "react";
import { MathText } from "../../components/math-text";
import { longTaskApiUrl } from "../../components/api-url";

const SEARCH_ENDPOINT = "/api/v1/agent/search";

const EXAMPLES = [
  "找 5 道高二椭圆焦点弦，中等偏难，适合课堂例题",
  "只要 2025 江苏圆锥曲线选择题，4 道",
  "给我几道椭圆基础题",
  "找 8 道导数压轴题，最好覆盖构造函数",
  "给我 5 道椭圆题，最好焦点弦，没有的话相近模型也可以",
];

const DIFFICULTY_LABELS: Record<number, string> = {
  1: "基础",
  2: "中等偏易",
  3: "中等",
  4: "中等偏难",
  5: "较难",
};

const QUESTION_TYPE_LABELS: Record<string, string> = {
  single_choice: "选择题",
  multiple_choice: "多选题",
  fill_blank: "填空题",
  true_false: "判断题",
  solution: "解答题",
};

const USAGE_LABELS: Record<string, string> = {
  classroom_example: "课堂例题",
  in_class_practice: "课堂练习",
  homework: "课后作业",
  exam_review: "复习",
  diagnostic: "诊断",
  warm_up: "热身",
  challenge: "挑战题",
  general: "通用",
};

const CONFIDENCE_LABELS: Record<string, string> = {
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
};

const SOURCE_LABELS: Record<string, string> = {
  commercial_granted: "来源已记录",
  public_permissive: "来源公开可核实",
  question_content_user_declared_usable: "来源已记录",
  rights_unclear: "权利待审核",
};

const ERROR_HINTS: Record<string, string> = {
  FEATURE_DISABLED: "该功能未启用。请在 FastAPI 环境开启 MATH_AI_SEARCH_AGENT_ENABLED=true（不影响传统题库检索）。",
  UNSUPPORTED_CAPABILITY: "当前 Agent Runtime 为 legacy，暂不支持自然语言搜索编排。请配置 MATH_AI_AGENT_RUNTIME=dsh 并启动 Agent Service。",
  RUNTIME_UNAVAILABLE: "Agent Service 未启动或不可达。请确认 apps/agent 服务已启动并已配置模型。",
};

type SearchAgentErrorBody = {
  code: string;
  message: string;
  request_id: string;
};

type SearchConstraint = {
  field: string;
  value: unknown;
  strength: "hard" | "soft" | "default";
  origin: "explicit" | "inferred" | "system_default";
  confidence: number;
  reason: string;
};

type CurriculumNodeRef = {
  node_id: string;
  code: string;
  name: string;
  node_type: string;
};

type CurriculumMapping = {
  version: string | null;
  textbook: string | null;
  volume: string | null;
  chapter: string | null;
  section: string | null;
  knowledge_point_ids: string[];
  knowledge_point_names: string[];
  matched_nodes: CurriculumNodeRef[];
};

type SearchIntent = {
  raw_query: string;
  subject: string;
  school_stage: string;
  grade: string | null;
  curriculum_version: string | null;
  book: string | null;
  volume: string | null;
  chapter: string | null;
  knowledge_points: string[];
  sub_knowledge_points: string[];
  question_types: string[];
  difficulty: number | null;
  difficulty_range: number[];
  requested_count: number | null;
  count: number;
  limit_applied: boolean;
  year_from: number | null;
  year_to: number | null;
  regions: string[];
  source_preferences: string[];
  teaching_usage: string;
  exclude_question_ids: string[];
  require_verified: boolean;
  allow_related_fallback: boolean;
  deduplicate: boolean;
  diversify: boolean;
  curriculum: CurriculumMapping;
  constraints: SearchConstraint[];
  parse_warnings: string[];
};

type PlanStep = {
  step: number;
  title: string;
  status: "pending" | "completed" | "skipped" | "failed";
  detail: Record<string, unknown>;
  reason: string;
};

type PlanSummary = {
  plan_id: string;
  intent_summary: Record<string, unknown>;
  steps: PlanStep[];
  applied_filters: Record<string, unknown>;
  soft_preferences: string[];
  relaxations: Record<string, unknown>[];
  candidate_count: number;
  selected_count: number;
  generated_at: number;
};

type MatchReason = {
  code: string;
  label: string;
  strength: string;
};

type Relaxation = {
  field: string;
  from_value: unknown;
  to_value: unknown;
  reason: string;
  disclosed: boolean;
};

type UnmetConstraint = {
  field: string;
  requested: unknown;
  matched_count: number;
  reason: string;
};

type SearchAgentResultItem = {
  question_id: string;
  stem: string;
  stem_preview: string;
  question_type: string;
  knowledge_points: string[];
  difficulty: number;
  verification_status: string;
  source_status: string;
  visibility: string;
  chapter: string | null;
  section: string | null;
  volume: string | null;
  year: number | null;
  region: string | null;
  match_reasons: MatchReason[];
  relaxed_fields: string[];
  similarity_group: string | null;
  grounded: boolean;
};

type SearchAgentResponse = {
  request_id: string;
  session_id: string;
  run_id: string;
  raw_query: string;
  status: string;
  intent: SearchIntent;
  plan_summary: PlanSummary;
  results: SearchAgentResultItem[];
  requested_count: number;
  effective_count: number;
  returned_count: number;
  exact_match_count: number;
  exact_match: boolean;
  relaxations: Relaxation[];
  unmet_constraints: UnmetConstraint[];
  warnings: string[];
  answer_summary: string;
  assistant_explanation: string | null;
  search_confidence: string;
  suggestions: string[];
  duration_ms: number;
  tool_call_count: number;
  candidate_count: number;
  error: SearchAgentErrorBody | null;
};

type Phase = "idle" | "loading" | "done";

function difficultyLabel(value: number): string {
  return DIFFICULTY_LABELS[value] ?? `难度 ${value}`;
}

function questionTypeLabel(value: string): string {
  return QUESTION_TYPE_LABELS[value] ?? value;
}

function verificationLabel(value: string): string {
  return VERIFICATION_LABELS[value] ?? (value ? value : "未验证");
}

function verificationTone(value: string): "ok" | "warn" | "none" {
  if (value === "passed" || value === "program_verified" || value === "teacher_review_approved") return "ok";
  if (value === "teacher_review_required" || value === "needs_math_review" || value === "needs_formula_review") return "warn";
  return "none";
}

function sourceLabel(value: string): string {
  return SOURCE_LABELS[value] ?? (value ? value : "来源信息暂缺");
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (Array.isArray(value)) return value.map(String).join("、");
  return String(value);
}

type IntentChip = { label: string; kind: "must" | "prefer" | "default" | "plain" };

function intentChips(intent: SearchIntent): IntentChip[] {
  const chips: IntentChip[] = [];
  const softFields = new Set(
    intent.constraints.filter((item) => item.strength === "soft").map((item) => item.field)
  );
  if (intent.grade) chips.push({ label: intent.grade, kind: "plain" });
  const kpSoft = softFields.has("knowledge_points");
  for (const term of intent.knowledge_points) {
    chips.push({ label: kpSoft ? `${term}（偏好）` : term, kind: kpSoft ? "prefer" : "must" });
  }
  for (const term of intent.sub_knowledge_points) {
    chips.push({ label: `${term}（偏好）`, kind: "prefer" });
  }
  if (intent.question_types.length > 0) {
    chips.push({ label: intent.question_types.map(questionTypeLabel).join("、"), kind: "plain" });
  }
  if (intent.difficulty !== null) {
    chips.push({ label: `难度 ${difficultyLabel(intent.difficulty)}`, kind: "plain" });
  } else if (intent.difficulty_range.length === 2) {
    chips.push({
      label: `难度 ${difficultyLabel(intent.difficulty_range[0])}–${difficultyLabel(intent.difficulty_range[1])}`,
      kind: "plain",
    });
  }
  if (intent.count > 0) {
    const limited = intent.limit_applied && intent.requested_count !== null && intent.requested_count > intent.count;
    chips.push({
      label: limited ? `单次最多 ${intent.count} 道（原要求 ${intent.requested_count} 道）` : `${intent.count} 道`,
      kind: limited ? "default" : "plain",
    });
  }
  if (intent.year_from !== null || intent.year_to !== null) {
    const from = intent.year_from ?? "";
    const to = intent.year_to ?? "";
    const label = from && to && from !== to ? `${from}–${to} 年` : `${from || to} 年`;
    chips.push({ label, kind: "plain" });
  }
  for (const region of intent.regions) chips.push({ label: region, kind: "plain" });
  if (intent.teaching_usage !== "general") {
    chips.push({ label: USAGE_LABELS[intent.teaching_usage] ?? intent.teaching_usage, kind: "plain" });
  }
  if (intent.require_verified) chips.push({ label: "仅程序验证通过", kind: "must" });
  if (intent.exclude_question_ids.length > 0) {
    chips.push({ label: `排除 ${intent.exclude_question_ids.length} 道已指定题`, kind: "must" });
  }
  return chips;
}

function AgentResultView({ response }: { response: SearchAgentResponse }) {
  const chips = intentChips(response.intent);
  const hasKinds = chips.some((item) => item.kind === "prefer" || item.kind === "default");
  return (
    <>
      <section className="search-agent-understood" aria-label="已理解为">
        <header>
          <strong>已理解为</strong>
          <span>来自结构化 SearchIntent，不是模型自由发挥</span>
        </header>
        <div className="search-agent-chips">
          {chips.map((chip) => (
            <span className={`search-agent-chip ${chip.kind}`} key={`${chip.kind}-${chip.label}`}>{chip.label}</span>
          ))}
        </div>
        {hasKinds && (
          <p className="search-agent-chip-legend">
            <span><b className="dot must" /> 必须满足</span>
            <span><b className="dot prefer" /> 软偏好（可以补充相近题）</span>
            <span><b className="dot default" /> 系统默认</span>
          </p>
        )}
        {response.intent.parse_warnings.length > 0 && (
          <div className="search-agent-warnings">
            {response.intent.parse_warnings.map((warning) => <p key={warning}>⚠ {warning}</p>)}
          </div>
        )}
      </section>

      {response.relaxations.length > 0 && (
        <section className="notice warning search-agent-relaxation" aria-label="相近条件补充说明">
          <strong>有 {response.relaxations.length} 处软偏好使用了相近条件补充。</strong>
          <ul>
            {response.relaxations.map((item, index) => (
              <li key={`${item.field}-${index}`}>
                放宽了「{item.field}」：{formatValue(item.from_value)} → {formatValue(item.to_value)}
                {item.reason ? `（${item.reason}）` : ""}
              </li>
            ))}
          </ul>
          <p>下面带「相近条件补充」标记的题目并不完全满足你的全部偏好。</p>
        </section>
      )}

      {response.unmet_constraints.length > 0 && (
        <section className="notice search-agent-unmet" aria-label="硬性条件未完全满足说明">
          <strong>没有足够完全匹配的题目：要求 {response.requested_count} 道，完全匹配 {response.exact_match_count} 道。</strong>
          <ul>
            {response.unmet_constraints.map((item, index) => (
              <li key={`${item.field}-${index}`}>
                「{item.field}」要求 {formatValue(item.requested)}，仅匹配 {item.matched_count} 道
                {item.reason ? `（${item.reason}）` : ""}
              </li>
            ))}
          </ul>
          <p>硬性条件没有被静默放宽；如需要，你可以放宽条件后重新搜索。</p>
        </section>
      )}

      {response.warnings.length > 0 && (
        <section className="notice search-agent-warnings">
          {response.warnings.map((warning) => <p key={warning}>⚠ {warning}</p>)}
        </section>
      )}

      {response.answer_summary && (
        <section className="search-agent-summary">
          <strong>检索结论</strong>
          <p>{response.answer_summary}</p>
          <span className="search-agent-confidence">
            可信度：{CONFIDENCE_LABELS[response.search_confidence] ?? response.search_confidence}
          </span>
        </section>
      )}

      <section className="search-agent-results" aria-label="搜索结果">
        <header>
          <strong>结果（{response.returned_count} 道，完全匹配 {response.exact_match_count} 道）</strong>
          <span>
            候选 {response.candidate_count} · 工具调用 {response.tool_call_count} 次 · 用时 {response.duration_ms} ms
          </span>
        </header>

        {response.results.length === 0 ? (
          <div className="empty-state">
            <h3>没有找到完全满足条件的题目</h3>
            <p>{response.answer_summary || "当前题库中暂无满足条件的题目，系统不会为了凑数而生成或伪造题目。"}</p>
            {response.suggestions.length > 0 && (
              <div className="search-agent-suggestions">
                <strong>你可以尝试：</strong>
                <ul>
                  {response.suggestions.map((suggestion) => <li key={suggestion}>{suggestion}</li>)}
                </ul>
              </div>
            )}
          </div>
        ) : (
          <ol className="search-agent-result-list">
            {response.results.map((item, index) => (
              <li className="search-agent-result" key={item.question_id}>
                <header>
                  <div>
                    <strong>{index + 1}. {questionTypeLabel(item.question_type)}</strong>
                    <span className="search-agent-id">{item.question_id}</span>
                    {item.relaxed_fields.length > 0 && (
                      <span className="search-agent-relaxed-badge">相近条件补充</span>
                    )}
                  </div>
                  <span className="search-agent-difficulty">{difficultyLabel(item.difficulty)}</span>
                </header>
                <div className="search-agent-stem">
                  <MathText text={item.stem || item.stem_preview || "（题干暂缺）"} />
                </div>
                {item.knowledge_points.length > 0 && (
                  <div className="search-agent-kps">
                    {item.knowledge_points.map((point) => <span key={point}>{point}</span>)}
                  </div>
                )}
                <div className="search-agent-meta">
                  <span className={`search-agent-trust ${verificationTone(item.verification_status)}`}>
                    {verificationLabel(item.verification_status)}
                  </span>
                  <span className="search-agent-source">{sourceLabel(item.source_status)}</span>
                  {item.year !== null && <span>{item.year} 年</span>}
                  {item.region && <span>{item.region}</span>}
                  {item.volume && <span>{item.volume}</span>}
                  {item.chapter && <span>{item.chapter}{item.section ? ` · ${item.section}` : ""}</span>}
                </div>
                {item.match_reasons.length > 0 && (
                  <ul className="search-agent-reasons">
                    {item.match_reasons.map((reason) => (
                      <li key={`${reason.code}-${reason.label}`}>
                        {reason.strength === "soft" ? "偏好：" : ""}{reason.label}
                      </li>
                    ))}
                  </ul>
                )}
                <Link className="search-agent-detail-link" href="/search">在题库中查看详情 →</Link>
              </li>
            ))}
          </ol>
        )}
      </section>

      {response.assistant_explanation && (
        <details className="search-agent-explanation">
          <summary>检索说明（模型基于结构化结果生成）</summary>
          <p><MathText text={response.assistant_explanation} /></p>
        </details>
      )}

      <details className="search-agent-plan">
        <summary>查看检索过程（结构化 SearchPlan）</summary>
        <ol>
          {response.plan_summary.steps.map((step) => (
            <li key={step.step} className={step.status}>
              <strong>{step.step}. {step.title}</strong>
              <span>{step.status === "completed" ? "已完成" : step.status === "skipped" ? "已跳过" : step.status}</span>
              {step.reason && <p>{step.reason}</p>}
            </li>
          ))}
        </ol>
        <p className="search-agent-run-meta">
          request_id {response.request_id} · run_id {response.run_id || "—"} · 候选 {response.candidate_count} · 已选 {response.returned_count}
        </p>
      </details>
    </>
  );
}

export default function SearchAgentPage() {
  const [query, setQuery] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [response, setResponse] = useState<SearchAgentResponse | null>(null);
  const [error, setError] = useState<SearchAgentErrorBody | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const sessionRef = useRef("");

  function ensureSession(): string {
    if (!sessionRef.current) sessionRef.current = `web_${crypto.randomUUID()}`;
    return sessionRef.current;
  }

  async function submit(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    const trimmed = query.trim();
    if (!trimmed || phase === "loading") return;
    setPhase("loading");
    setError(null);
    setResponse(null);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const result = await fetch(longTaskApiUrl(SEARCH_ENDPOINT), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: trimmed, session_id: ensureSession() }),
        signal: controller.signal,
      });
      let payload: SearchAgentResponse;
      try {
        payload = (await result.json()) as SearchAgentResponse;
      } catch {
        setError({ code: `HTTP_${result.status}`, message: `请求失败（HTTP ${result.status}）`, request_id: "" });
        return;
      }
      if (!result.ok) {
        const body = (payload as unknown as { error?: SearchAgentErrorBody }).error;
        setError(body ?? { code: `HTTP_${result.status}`, message: `请求失败（HTTP ${result.status}）`, request_id: "" });
        return;
      }
      if (payload.error && payload.status === "error") {
        setError(payload.error);
        return;
      }
      setResponse(payload);
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === "AbortError") {
        setError({ code: "CANCELLED", message: "本次搜索已取消。", request_id: "" });
      } else {
        setError({ code: "NETWORK_ERROR", message: "无法连接到后端服务，请确认 FastAPI 已启动。", request_id: "" });
      }
    } finally {
      abortRef.current = null;
      setPhase("done");
    }
  }

  function cancel() {
    abortRef.current?.abort();
  }

  const loading = phase === "loading";
  const hint = error ? ERROR_HINTS[error.code] : "";

  return (
    <div className="page-content search-agent-page">
      <section className="page-title">
        <div>
          <p className="eyebrow">Search Agent · 自然语言搜题</p>
          <h1>用教学语言描述需求，其余交给可信检索。</h1>
          <p className="subtle">
            系统理解年级、知识点、难度与教学用途，只返回来自真实题库、通过权限与验证门禁的题目；AI 负责理解与解释，不编题、不伪造来源。
          </p>
        </div>
        <Link className="primary-button" href="/search">返回题库筛选</Link>
      </section>

      <form className="search-agent-input" onSubmit={submit}>
        <label>
          <span>描述你想找的题</span>
          <input
            aria-label="自然语言搜题"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="例如：找 5 道高二椭圆焦点弦，中等偏难，适合课堂例题"
            disabled={loading}
          />
        </label>
        <div className="search-agent-input-actions">
          <button className="primary-button" type="submit" disabled={loading || !query.trim()}>
            {loading ? "检索中…" : "搜索"}
          </button>
          {loading && <button className="ghost-button" type="button" onClick={cancel}>取消</button>}
        </div>
        <div className="search-agent-examples">
          <span>试试：</span>
          {EXAMPLES.map((example) => (
            <button
              type="button"
              key={example}
              disabled={loading}
              onClick={() => setQuery(example)}
              title={example}
            >
              {example.length > 20 ? `${example.slice(0, 20)}…` : example}
            </button>
          ))}
        </div>
      </form>

      {loading && (
        <section className="search-agent-loading" aria-live="polite">
          <span className="search-agent-spinner" aria-hidden="true" />
          <p>正在理解教学意图、检索题库并核对可信状态…（长任务可能需要一些时间）</p>
        </section>
      )}

      {error && phase !== "loading" && (
        <section className="search-agent-error" role="alert">
          <strong>搜索未完成（{error.code}）</strong>
          <p>{error.message}</p>
          {hint && <p className="search-agent-error-hint">{hint}</p>}
          <div>
            <button className="primary-button" type="button" onClick={() => submit()}>重试</button>
          </div>
        </section>
      )}

      {response && !error && phase !== "loading" && <AgentResultView response={response} />}
    </div>
  );
}