"use client";
import Link from "next/link";
import { FormEvent, useRef, useState } from "react";
import { MathText } from "../../components/math-text";
import { longTaskApiUrl } from "../../components/api-url";
import { SearchModeTabs } from "../../components/search-mode-tabs";
import {
  isInternalNodeId,
  TrustBadge,
  MatchBadge,
  difficultyLabel,
  fieldLabel,
  formatFieldValue,
  matchConfidenceLabel,
  questionTypeLabel,
  sourceLabel,
  translateKnowledgePointValues,
  USAGE_LABELS,
} from "./ui";
const SEARCH_ENDPOINT = "/api/v1/agent/search";
const EXAMPLE_SETS = [
  [
    "5 道高二椭圆课堂例题",
    "2025 江苏圆锥曲线选择题",
    "导数压轴题，优先构造函数",
  ],
  ["3 道集合基础题", "概率大题，中等偏难", "函数奇偶性判断题"],
];
const PLAN_STEP_LABELS: Record<string, string> = {
  resolve_curriculum: "对应教材与知识点",
  apply_hard_filters: "应用必须满足的条件",
  search_candidates: "检索候选题目",
  apply_rights_publication_visibility_gate: "核对来源与可见权限",
  verification_enrichment: "补充数学验证信息",
  deduplicate: "去除重复题目",
  similarity_diversity: "平衡相似度与多样性",
  difficulty_knowledge_rerank: "按难度与知识点排序",
  select_top_n: "选取最终结果",
  generate_explanation: "整理结果说明",
};
const STEP_STATUS_LABELS: Record<string, string> = {
  pending: "待执行",
  completed: "已完成",
  skipped: "已跳过",
  failed: "未完成",
};
/** 面向开发者 / 技术支持的提示，仅进入高级详情，不给教师看。 */ const ERROR_HINTS: Record<
  string,
  string
> = {
  FEATURE_DISABLED:
    "该功能未启用。请在 FastAPI 环境开启 MATH_AI_SEARCH_AGENT_ENABLED=true（不影响传统题库检索）。",
  UNSUPPORTED_CAPABILITY:
    "当前 Agent Runtime 为 legacy，暂不支持自然语言搜索编排。请配置 MATH_AI_AGENT_RUNTIME=dsh 并启动 Agent Service。",
  RUNTIME_UNAVAILABLE:
    "Agent Service 未启动或不可达。请确认 apps/agent 服务已启动并已配置模型。",
  TOOL_TIMEOUT:
    "工具调用超时。请检查 Agent Service 与 FastAPI Tool Gateway 的连接状态。",
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
type MatchReason = { code: string; label: string; strength: string };
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
type IntentChip = {
  key: string;
  label: string;
  kind: "must" | "prefer" | "default" | "plain";
};
function strengthOf(
  intent: SearchIntent,
  field: string,
): "hard" | "soft" | "default" | null {
  return (
    intent.constraints.find((item) => item.field === field)?.strength ?? null
  );
}
function intentChips(intent: SearchIntent): IntentChip[] {
  const chips: IntentChip[] = [];
  const push = (key: string, label: string, kind: IntentChip["kind"]) => {
    if (label.trim()) chips.push({ key, label, kind });
  };
  const grade = intent.grade?.trim();
  if (grade)
    push(
      "grade",
      grade,
      strengthOf(intent, "grade") === "hard" ? "must" : "plain",
    );
  const volume = (intent.volume ?? intent.curriculum?.volume)?.trim();
  if (volume)
    push(
      "volume",
      volume,
      strengthOf(intent, "volume") === "hard" ? "must" : "plain",
    );
  const chapter = (intent.chapter ?? intent.curriculum?.chapter)?.trim();
  if (chapter)
    push(
      "chapter",
      chapter,
      strengthOf(intent, "chapter") === "hard" ? "must" : "plain",
    );
  const kpStrength = strengthOf(intent, "knowledge_points");
  for (const term of intent.knowledge_points) {
    const name = term.trim();
    if (!name || /^kp_[0-9a-z_]+$/i.test(name)) continue;
    push(
      `kp-${name}`,
      name,
      kpStrength === "hard"
        ? "must"
        : kpStrength === "soft"
          ? "prefer"
          : "plain",
    );
  }
  for (const term of intent.sub_knowledge_points) {
    const name = term.trim();
    if (!name || /^kp_[0-9a-z_]+$/i.test(name)) continue;
    push(`subkp-${name}`, `${name} · 优先`, "prefer");
  }
  if (intent.question_types.length > 0) {
    push(
      "types",
      intent.question_types.map(questionTypeLabel).join("、"),
      "plain",
    );
  }
  if (intent.difficulty !== null) {
    push(
      "difficulty",
      difficultyLabel(intent.difficulty),
      strengthOf(intent, "difficulty_range") === "hard" ? "must" : "plain",
    );
  } else if (intent.difficulty_range.length === 2) {
    push(
      "difficulty",
      `${difficultyLabel(intent.difficulty_range[0])}～${difficultyLabel(intent.difficulty_range[1])}`,
      strengthOf(intent, "difficulty_range") === "hard" ? "must" : "plain",
    );
  }
  if (intent.count > 0) {
    const limited =
      intent.limit_applied &&
      intent.requested_count !== null &&
      intent.requested_count > intent.count;
    push(
      "count",
      limited ? `最多 ${intent.count} 道` : `${intent.count} 道`,
      limited ? "default" : "plain",
    );
  }
  if (intent.year_from !== null || intent.year_to !== null) {
    const from = intent.year_from ?? "";
    const to = intent.year_to ?? "";
    const label =
      from && to && from !== to ? `${from}–${to} 年` : `${from || to} 年`;
    push("year", label, "plain");
  }
  for (const region of intent.regions)
    push(`region-${region}`, region.trim(), "plain");
  if (intent.teaching_usage && intent.teaching_usage !== "general") {
    const usage = USAGE_LABELS[intent.teaching_usage] ?? intent.teaching_usage;
    push(
      "usage",
      usage,
      strengthOf(intent, "teaching_usage") === "soft" ? "prefer" : "plain",
    );
  }
  if (intent.require_verified) push("verified", "仅程序验证通过", "must");
  return chips;
}
function teacherErrorTitle(code: string): string {
  if (code === "CANCELLED") return "搜索已停止";
  if (code === "SEARCH_PLAN_EXHAUSTED") return "这次搜索没有找到合适结果";
  return "AI 搜题服务暂时不可用";
}
function teacherErrorMessage(code: string, message: string): string {
  if (code === "CANCELLED")
    return "本次搜索已停止，没有返回结果。你可以调整需求后重新搜索。";
  if (code === "SEARCH_PLAN_EXHAUSTED")
    return "这次搜索尝试了多种条件组合，但暂时没有找到合适结果。建议修改条件后重试。";
  if (code === "RUNTIME_UNAVAILABLE")
    return "智能搜题服务暂时无法连接，请稍后重试。你仍然可以使用高级筛选搜题。";
  if (code === "UNSUPPORTED_CAPABILITY")
    return "当前环境暂不支持自然语言搜题，请先使用高级筛选搜题。";
  if (code === "FEATURE_DISABLED")
    return "自然语言搜题尚未开启，你可以先使用高级筛选搜题。";
  if (code === "NETWORK_ERROR") return "无法连接到后端服务，请稍后重试。";
  if (code === "TOOL_TIMEOUT")
    return "搜索耗时过长，已自动停止。请简化条件后重试。";
  if (code === "RUN_NOT_FOUND") return "这次搜索记录已失效，请重新搜索。";
  if (message && message !== code) return message;
  return "服务暂时不可用，请稍后重试。";
}
function SearchResultCard({
  item,
  index,
}: {
  item: SearchAgentResultItem;
  index: number;
}) {
  const relaxed = item.relaxed_fields.length > 0;
  return (
    <li className="search-agent-result">
      <header>
        <div className="search-agent-result-title">
          <span className="search-agent-result-index">
            {String(index + 1).padStart(2, "0")}
          </span>
          <strong>{questionTypeLabel(item.question_type)}</strong>
          <span className="search-agent-difficulty">
            {difficultyLabel(item.difficulty)}
          </span>
        </div>
        <MatchBadge relaxed={relaxed} />
      </header>
      <div className="search-agent-stem">
        <MathText text={item.stem || item.stem_preview || "（题干暂缺）"} />
      </div>
      {item.knowledge_points.length > 0 && (
        <div className="search-agent-kps">
          {item.knowledge_points
            .filter((point) => !isInternalNodeId(point))
            .map((point) => (
              <span key={point}>{point}</span>
            ))}
        </div>
      )}
      {item.match_reasons.length > 0 && (
        <div className="search-agent-reasons">
          <strong>为什么推荐</strong>
          <ul>
            {item.match_reasons.map((reason) => (
              <li key={`${reason.code}-${reason.label}`}>{reason.label}</li>
            ))}
          </ul>
        </div>
      )}
      <div className="search-agent-meta">
        <TrustBadge value={item.verification_status} />
        <span
          className={`search-agent-source ${item.source_status === "rights_unclear" ? "warn" : ""}`}
        >
          {sourceLabel(item.source_status)}
        </span>
        {item.year !== null && <span>{item.year} 年</span>}
        {item.region && <span>{item.region}</span>}
        {item.volume && <span>{item.volume}</span>}
        {item.chapter && (
          <span>
            {item.chapter}
            {item.section ? ` · ${item.section}` : ""}
          </span>
        )}
      </div>
      <footer className="search-agent-result-footer">
        <details className="search-agent-advanced">
          <summary>高级信息（题目编号与状态）</summary>
          <dl>
            <div>
              <dt>题目编号</dt>
              <dd>{item.question_id}</dd>
            </div>
            <div>
              <dt>验证状态（原始值）</dt>
              <dd>{item.verification_status || "—"}</dd>
            </div>
            <div>
              <dt>来源状态（原始值）</dt>
              <dd>{item.source_status || "—"}</dd>
            </div>
            <div>
              <dt>可见范围（原始值）</dt>
              <dd>{item.visibility || "—"}</dd>
            </div>
            {relaxed && (
              <div>
                <dt>放宽条件（原始值）</dt>
                <dd>{item.relaxed_fields.join("、")}</dd>
              </div>
            )}
          </dl>
        </details>
        <Link className="search-agent-detail-link" href="/search">
          在题库中查看详情 →
        </Link>
      </footer>
    </li>
  );
}
function SearchDetails({ response }: { response: SearchAgentResponse }) {
  const empty = response.results.length === 0;
  const kpNames = response.intent.curriculum?.knowledge_point_names ?? [];
  return (
    <details className="search-agent-details">
      <summary>
        {empty
          ? "为什么没有找到？查看检索详情"
          : "为什么得到这些结果？查看检索详情"}
      </summary>
      <div className="search-agent-details-body">
        <section>
          <h4>{empty ? "为什么没有找到？" : "为什么得到这些结果？"}</h4>
          <p>{response.answer_summary || "暂无说明。"}</p>
          {response.assistant_explanation && (
            <p>
              <MathText text={response.assistant_explanation} />
            </p>
          )}
          <span className="search-agent-match-confidence">
            匹配度：{matchConfidenceLabel(response.search_confidence)}
          </span>
        </section>
        {(response.relaxations.length > 0 ||
          response.unmet_constraints.length > 0) && (
          <section>
            <h4>条件调整记录</h4>
            <ul className="search-agent-constraint-list">
              {response.relaxations.map((item, index) => (
                <li key={`relax-${index}`}>
                  {fieldLabel(item.field)}：
                  {formatFieldValue(item.field, item.from_value, kpNames)} →
                  {formatFieldValue(item.field, item.to_value, kpNames)}
                  {item.reason ? `（${item.reason}）` : ""}
                </li>
              ))}
              {response.unmet_constraints.map((item, index) => (
                <li key={`unmet-${index}`}>
                  {fieldLabel(item.field)}要求
                  {formatFieldValue(item.field, item.requested, kpNames)}
                  ，仅匹配 {item.matched_count} 道
                  {item.reason ? `（${item.reason}）` : ""}
                </li>
              ))}
            </ul>
          </section>
        )}
        <section>
          <h4>本次搜索条件</h4>
          <ol className="search-agent-plan-list">
            {response.plan_summary.steps.map((step) => (
              <li key={step.step} className={step.status}>
                <strong>
                  {step.step}. {PLAN_STEP_LABELS[step.title] ?? step.title}
                </strong>
                <span>{STEP_STATUS_LABELS[step.status] ?? step.status}</span>
                {step.reason && <p>{step.reason}</p>}
              </li>
            ))}
          </ol>
        </section>
        <section>
          <h4>技术信息（仅供技术支持参考）</h4>
          <p className="search-agent-run-meta">
            请求编号 {response.request_id} · 会话编号
            {response.session_id || "—"} · 运行编号 {response.run_id || "—"}
            <br /> 候选 {response.candidate_count} 道 · 工具调用
            {response.tool_call_count} 次 · 用时 {response.duration_ms} ms
          </p>
          {response.intent.parse_warnings.length > 0 && (
            <ul className="search-agent-constraint-list">
              {response.intent.parse_warnings.map((warning) => (
                <li key={warning}>⚠ {warning}</li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </details>
  );
}
function AgentResultView({ response }: { response: SearchAgentResponse }) {
  const chips = intentChips(response.intent);
  const mustChips = chips.filter((chip) => chip.kind === "must");
  const preferChips = chips.filter((chip) => chip.kind === "prefer");
  const empty = response.results.length === 0;
  const relatedCount = Math.max(
    0,
    response.returned_count - response.exact_match_count,
  );
  return (
    <>
      <section className="search-agent-understood" aria-label="已理解为">
        <header>
          <strong>已理解为</strong> <span>系统整理出的搜索条件</span>
        </header>
        <div className="search-agent-chips">
          {chips.map((chip) => (
            <span
              className={`search-agent-chip ${chip.kind}`}
              key={chip.key}
              title={chip.label}
            >
              {chip.kind === "prefer" && !chip.label.includes("·")
                ? `${chip.label} · 优先`
                : chip.label}
              {chip.kind === "default" && !chip.label.includes("·")
                ? ` · 系统补充`
                : ""}
            </span>
          ))}
        </div>
        <p className="search-agent-chip-legend" aria-label="条件含义">
          <span>
            <b className="dot must" aria-hidden="true" /> 必须满足
          </span>
          <span>
            <b className="dot prefer" aria-hidden="true" /> 优先满足
          </span>
          <span>
            <b className="dot default" aria-hidden="true" /> 系统补充
          </span>
        </p>
      </section>
      {response.warnings.length > 0 && (
        <section className="search-agent-inline-notice" aria-label="搜索提示">
          {response.warnings.map((warning) => (
            <p key={warning}>⚠ {warning}</p>
          ))}
        </section>
      )}
      <section className="search-agent-results" aria-label="搜索结果">
        {!empty && (
          <header>
            <strong>
              找到 {response.exact_match_count} 道完全匹配
              {relatedCount > 0 ? ` · 另有 ${relatedCount} 道相近条件补充` : ""}
            </strong>
          </header>
        )}
        {empty ? (
          <div className="search-agent-empty">
            <div className="search-agent-empty-copy">
              <h3>暂时没有完全匹配的题目</h3>
              <p>
                题库中暂时没有同时满足全部条件的题目，系统不会为了凑数而生成或伪造题目。
              </p>
            </div>
            {mustChips.length > 0 && (
              <div className="search-agent-empty-group">
                <strong>必须满足</strong>
                <div className="search-agent-chips">
                  {mustChips.map((chip) => (
                    <span className="search-agent-chip must" key={chip.key}>
                      {chip.label}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {preferChips.length > 0 && (
              <div className="search-agent-empty-group">
                <strong>优先满足</strong>
                <div className="search-agent-chips">
                  {preferChips.map((chip) => (
                    <span className="search-agent-chip prefer" key={chip.key}>
                      {chip.label}
                    </span>
                  ))}
                </div>
              </div>
            )}
            <div className="search-agent-empty-stat">
              当前：0 道完全匹配 <span aria-hidden="true">·</span> 匹配度：
              {matchConfidenceLabel(response.search_confidence)}
            </div>
            {response.suggestions.length > 0 && (
              <div className="search-agent-empty-group">
                <strong>可以尝试</strong>
                <ul className="search-agent-suggestion-list">
                  {response.suggestions.map((suggestion) => (
                    <li key={suggestion}>{suggestion}</li>
                  ))}
                </ul>
              </div>
            )}
            <div className="search-agent-empty-actions">
              <a className="primary-button" href="#search-agent-composer">
                修改搜索条件
              </a>
              <Link className="ghost-button" href="/search">
                高级筛选搜题
              </Link>
            </div>
          </div>
        ) : (
          <ol className="search-agent-result-list">
            {response.results.map((item, index) => (
              <SearchResultCard
                item={item}
                index={index}
                key={item.question_id}
              />
            ))}
          </ol>
        )}
      </section>
      <SearchDetails response={response} />
    </>
  );
}
export default function SearchAgentPage() {
  const [query, setQuery] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [response, setResponse] = useState<SearchAgentResponse | null>(null);
  const [error, setError] = useState<SearchAgentErrorBody | null>(null);
  const [exampleSet, setExampleSet] = useState(0);
  const abortRef = useRef<AbortController | null>(null);
  const sessionRef = useRef("");
  const composerRef = useRef<HTMLTextAreaElement | null>(null);
  function ensureSession(): string {
    if (!sessionRef.current) sessionRef.current = `web_${crypto.randomUUID()}`;
    return sessionRef.current;
  }
  function focusComposer() {
    composerRef.current?.focus();
    composerRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
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
        setError({
          code: `HTTP_${result.status}`,
          message: `请求失败（HTTP ${result.status}）`,
          request_id: "",
        });
        return;
      }
      if (!result.ok) {
        const body = (payload as unknown as { error?: SearchAgentErrorBody })
          .error;
        setError(
          body ?? {
            code: `HTTP_${result.status}`,
            message: `请求失败（HTTP ${result.status}）`,
            request_id: "",
          },
        );
        return;
      }
      if (payload.error && payload.status === "error") {
        setError(payload.error);
        return;
      }
      setResponse(payload);
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === "AbortError") {
        setError({
          code: "CANCELLED",
          message: "本次搜索已取消。",
          request_id: "",
        });
      } else {
        setError({
          code: "NETWORK_ERROR",
          message: "无法连接到后端服务，请确认 FastAPI 已启动。",
          request_id: "",
        });
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
  const hint = error ? (ERROR_HINTS[error.code] ?? "") : "";
  const examples = EXAMPLE_SETS[exampleSet % EXAMPLE_SETS.length];
  return (
    <div className="page-content search-agent-page">
      <SearchModeTabs />
      <section className="page-title">
        <div>
          <p className="eyebrow">智能搜题 · 自然语言检索</p>
          <h1>用教学语言描述需求，其余交给可信检索。</h1>
          <p className="subtle">
            系统理解年级、知识点、难度与教学用途，只返回来自题库、通过权限与验证门禁的题目。
          </p>
        </div>
      </section>
      <form
        id="search-agent-composer"
        className="search-agent-composer"
        onSubmit={submit}
      >
        <div className="search-agent-composer-head">
          <label htmlFor="search-agent-query">描述你正在准备什么题</label>
          <span>年级、知识点、难度、题型与用途都可以直接说</span>
        </div>
        <div className="search-agent-composer-box">
          <textarea
            ref={composerRef}
            id="search-agent-query"
            aria-label="自然语言搜题"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="例如：找 5 道高二椭圆焦点弦，中等偏难，适合课堂例题"
            disabled={loading}
            rows={2}
          />
          <div className="search-agent-composer-actions">
            {loading && (
              <button className="ghost-button" type="button" onClick={cancel}>
                停止搜索
              </button>
            )}
            <button
              className="primary-button search-agent-submit"
              type="submit"
              disabled={loading || !query.trim()}
            >
              {loading ? "正在搜索…" : "AI 搜题 →"}
            </button>
          </div>
        </div>
        <div className="search-agent-examples">
          <span>示例：</span>
          {examples.map((example) => (
            <button
              type="button"
              key={example}
              disabled={loading}
              onClick={() => {
                setQuery(example);
                focusComposer();
              }}
              title={example}
            >
              {example}
            </button>
          ))}
          <button
            className="search-agent-example-swap"
            type="button"
            disabled={loading}
            onClick={() => setExampleSet((value) => value + 1)}
          >
            换一批
          </button>
        </div>
      </form>
      {loading && (
        <section className="search-agent-loading" aria-live="polite">
          <span className="search-agent-spinner" aria-hidden="true" />
          <p>正在理解你的教学需求…</p>
        </section>
      )}
      {error && phase !== "loading" && (
        <section className="search-agent-error" role="alert">
          <h3>{teacherErrorTitle(error.code)}</h3>
          <p>{teacherErrorMessage(error.code, error.message)}</p>
          <div className="search-agent-error-actions">
            {error.code !== "CANCELLED" &&
              error.code !== "SEARCH_PLAN_EXHAUSTED" && (
                <button
                  className="primary-button"
                  type="button"
                  onClick={() => submit()}
                >
                  重试
                </button>
              )}
            <button
              className="ghost-button"
              type="button"
              onClick={focusComposer}
            >
              修改搜索条件
            </button>
            <Link className="ghost-button" href="/search">
              高级筛选搜题
            </Link>
          </div>
          <details className="search-agent-error-details">
            <summary>技术详情（仅供技术支持参考）</summary>
            <dl>
              <div>
                <dt>错误代码</dt>
                <dd>{error.code}</dd>
              </div>
              {error.request_id && (
                <div>
                  <dt>请求编号</dt>
                  <dd>{error.request_id}</dd>
                </div>
              )}
            </dl>
            {hint && <p>{hint}</p>}
          </details>
        </section>
      )}
      {response && !error && phase !== "loading" && (
        <AgentResultView response={response} />
      )}
    </div>
  );
}
