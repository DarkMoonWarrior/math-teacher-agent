"use client";

import { type FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { MathText } from "@/components/math-text";
import {
  type PaperBlueprintDraft,
  type PaperBlueprintDifficulty,
  type PaperBlueprintSection,
  type PaperBlueprintSelectionDraft,
  type PaperDraftItemEdit,
  type PaperEditableDraft,
  type PaperHistoryItem,
  type PaperHistoryPaper,
  type PaperHistoryPaperItem,
  type PaperHistoryRevisionRequest,
  type PaperPublicQuestionCandidate,
  type PaperSavedVersion,
  type PaperSelectionItem,
  type PersonalQuestion,
  TeacherWorkspaceError,
} from "@/lib/teacher-workspace/contracts";
import { teacherWorkspace } from "@/lib/teacher-workspace/http-adapter";
import { ArrowRightIcon, ArrowUpIcon, CheckIcon, CloseIcon, LockIcon, PaperIcon } from "./icons";
import { ResizableSplitPane } from "./resizable-split-pane";
import { WorkbenchNoticeDialog } from "./workbench-notice-dialog";

type PaperBlueprintWorkspaceProps = {
  initialBrief: string;
  onBriefChange: (brief: string) => void;
  onOpenAuthoring: (brief: string) => void;
};

const EXAMPLES = [
  "组一份高二期中卷，120 分钟，总分 150 分，覆盖函数、导数与圆锥曲线，中等偏难",
  "组一份 60 分钟导数专题测验，中等难度，含 3 道解答题",
  "组一份函数性质随堂练习，20 分钟，以基础巩固为主",
];

const DIFFICULTY_LABELS: Record<PaperBlueprintDifficulty, string> = {
  foundation: "基础巩固",
  balanced: "均衡梯度",
  challenge: "能力提升",
};

const QUESTION_TYPE_LABELS: Record<string, string> = {
  single_choice: "单项选择题",
  multiple_choice: "多项选择题",
  fill_blank: "填空题",
  open_response: "解答题",
};

const DIFFICULTY_AUDIT_LABELS = {
  matched: "难度吻合",
  deviated: "难度有偏差",
  insufficient_supply: "题目不足，暂不能完整判断",
} as const;

const SPECIFICATION_DIMENSION_LABELS = {
  section: "分区",
  question_type: "题型",
  knowledge_point: "知识点",
  difficulty: "难度",
} as const;

const PAPER_EXPORT_PREVIEW_LABELS = [
  "学生卷 · DOCX",
  "学生卷 · PDF",
  "答案卷 · DOCX",
  "答案卷 · PDF",
  "双向细目表 · DOCX",
  "双向细目表 · PDF",
] as const;

type PaperHistoryLifecycle = "active" | "trashed";

function numberValue(value: string, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function errorMessage(cause: unknown, fallback: string): string {
  return cause instanceof TeacherWorkspaceError ? cause.message : fallback;
}

function isPrivateQuestionSelectable(question: PersonalQuestion): boolean {
  if (question.question.solution_status === "ready") return true;
  return question.question.solution_status === "needs_teacher_verification"
    && Boolean(question.question.solution_issue?.includes("解析未生成"));
}

function paperHistoryDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

type PaperHistoryPanelProps = {
  busyKey: string;
  items: PaperHistoryItem[];
  lifecycle: PaperHistoryLifecycle;
  loading: boolean;
  onExport: (item: PaperHistoryItem, edition: "student" | "answer" | "blueprint") => void;
  onLifecycleChange: (item: PaperHistoryItem, action: "trash" | "restore") => void;
  onOpen: (item: PaperHistoryItem) => void;
  onSelectLifecycle: (lifecycle: PaperHistoryLifecycle) => void;
};

export function PaperHistoryPanel({
  busyKey,
  items,
  lifecycle,
  loading,
  onExport,
  onLifecycleChange,
  onOpen,
  onSelectLifecycle,
}: PaperHistoryPanelProps) {
  return (
    <section className="paper-history" aria-label="历史组卷">
      <header>
        <div><LockIcon /><span><strong>历史组卷</strong><small>仅当前用户可见</small></span></div>
        <nav aria-label="历史组卷状态">
          <button aria-pressed={lifecycle === "active"} onClick={() => onSelectLifecycle("active")} type="button">已保存</button>
          <button aria-pressed={lifecycle === "trashed"} onClick={() => onSelectLifecycle("trashed")} type="button">回收站</button>
        </nav>
      </header>
      {loading ? <p className="paper-history-state">正在读取你的历史组卷…</p> : items.length === 0 ? (
        <p className="paper-history-state">{lifecycle === "active" ? "还没有已保存的试卷。" : "回收站是空的。"}</p>
      ) : (
        <ul>
          {items.map((item) => (
            <li key={item.exam_paper_id}>
              <div>
                {lifecycle === "active" ? <button className="paper-history-open" onClick={() => onOpen(item)} type="button"><strong>{item.title}</strong></button> : <strong>{item.title}</strong>}
                <span>{item.question_count} 题 · {item.total_score.toLocaleString("zh-CN")} 分 · {paperHistoryDate(item.updated_at)}</span>
              </div>
              {lifecycle === "active" ? (
                <div className="paper-history-actions">
                  <button disabled={Boolean(busyKey)} onClick={() => onOpen(item)} type="button">编辑</button>
                  <button disabled={Boolean(busyKey)} onClick={() => onExport(item, "student")} type="button">学生卷</button>
                  <button disabled={Boolean(busyKey)} onClick={() => onExport(item, "answer")} type="button">答案卷</button>
                  <button disabled={Boolean(busyKey)} onClick={() => onExport(item, "blueprint")} type="button">细目表</button>
                  <button className="is-danger" disabled={Boolean(busyKey)} onClick={() => onLifecycleChange(item, "trash")} type="button">删除</button>
                </div>
              ) : (
                <div className="paper-history-actions">
                  <button disabled={Boolean(busyKey)} onClick={() => onLifecycleChange(item, "restore")} type="button">恢复</button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

type PaperHistoryEditorProps = {
  busy: boolean;
  onClose: () => void;
  onSave: (request: PaperHistoryRevisionRequest) => void;
  paper: PaperHistoryPaper;
  privateQuestions?: PersonalQuestion[];
  publicCandidates?: PaperPublicQuestionCandidate[];
};

export function PaperHistoryEditor({ busy, onClose, onSave, paper, privateQuestions = [], publicCandidates = [] }: PaperHistoryEditorProps) {
  const [title, setTitle] = useState(paper.title);
  const [durationMinutes, setDurationMinutes] = useState(paper.duration_minutes);
  const [items, setItems] = useState<PaperHistoryPaperItem[]>(paper.items);
  const [targetTotalScore, setTargetTotalScore] = useState(paper.total_score);
  const [addingQuestions, setAddingQuestions] = useState(false);

  useEffect(() => {
    setTitle(paper.title);
    setDurationMinutes(paper.duration_minutes);
    setItems(paper.items);
    setTargetTotalScore(paper.total_score);
    setAddingQuestions(false);
  }, [paper]);

  function moveItem(index: number, offset: -1 | 1) {
    const target = index + offset;
    if (target < 0 || target >= items.length) return;
    setItems((current) => {
      const next = [...current];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  }

  function updateItem(index: number, patch: Partial<PaperHistoryPaperItem>) {
    setItems((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item));
  }

  function removeItem(index: number) {
    setItems((current) => {
      const next = current.filter((_, itemIndex) => itemIndex !== index);
      setTargetTotalScore(next.reduce((sum, item) => sum + item.score, 0));
      return next;
    });
  }

  function addPublicQuestion(candidate: PaperPublicQuestionCandidate) {
    if (items.length >= 50 || items.some((item) => item.question.question_id === candidate.question_id)) return;
    setItems((current) => [...current, {
      item_id: `new-${candidate.question_id}`,
      position: current.length + 1,
      section_id: `history-${candidate.question_type}`,
      section_title: QUESTION_TYPE_LABELS[candidate.question_type] ?? "试题",
      score: 5,
      added_source_kind: "public_question_bank",
      question: {
        question_id: candidate.question_id,
        question_type: candidate.question_type,
        stem_plain: candidate.stem_plain,
        stem_latex: null,
        options: candidate.options,
        difficulty: candidate.difficulty,
      },
    }]);
    setTargetTotalScore((current) => current + 5);
  }

  function addPrivateQuestion(candidate: PersonalQuestion) {
    if (items.length >= 50 || items.some((item) => item.question.question_id === candidate.question_id)) return;
    const draft = candidate.question;
    setItems((current) => [...current, {
      item_id: `new-${candidate.question_id}`,
      position: current.length + 1,
      section_id: `history-${draft.question_type}`,
      section_title: QUESTION_TYPE_LABELS[draft.question_type] ?? "试题",
      score: 5,
      added_source_kind: "personal_question_library",
        question: {
          question_id: candidate.question_id,
          question_type: draft.question_type,
          stem_plain: draft.stem_plain,
          stem_latex: draft.stem_latex,
          options: draft.options,
          difficulty: draft.estimated_difficulty,
          answer_value: draft.answer_value,
          solution_method: draft.solution_method,
          solution_steps: draft.solution_steps,
          final_answer: draft.final_answer,
          solution_status: draft.solution_status,
          solution_issue: draft.solution_issue,
        },
    }]);
    setTargetTotalScore((current) => current + 5);
  }

  function distributeTargetTotal() {
    if (items.length === 0) return;
    const totalUnits = Math.round(targetTotalScore * 2);
    const minimumUnits = items.length;
    const maximumUnits = items.length * 100;
    if (totalUnits < minimumUnits || totalUnits > maximumUnits) return;
    const baseUnits = Math.floor(totalUnits / items.length);
    const remainder = totalUnits % items.length;
    setItems((current) => current.map((item, index) => ({
      ...item,
      score: (baseUnits + (index < remainder ? 1 : 0)) / 2,
    })));
    setTargetTotalScore(totalUnits / 2);
  }

  const totalScore = items.reduce((sum, item) => sum + item.score, 0);
  const totalMatches = Math.abs(totalScore - targetTotalScore) < 0.001;
  const canSave = title.trim().length >= 2 && durationMinutes >= 10 && items.length > 0 && items.length <= 50 && targetTotalScore <= 300 && totalMatches && items.every((item) => item.section_title.trim() && item.score > 0 && item.score <= 50);
  const existingIds = new Set(items.map((item) => item.question.question_id));

  return (
    <article className="paper-history-editor">
      <header>
        <div><p>历史组卷 · 版本 {paper.version}</p><h2>编辑后另存新版本</h2></div>
        <button onClick={onClose} type="button">关闭编辑</button>
      </header>
      <div className="paper-history-editor-fields">
        <label>试卷名称<input value={title} onChange={(event) => setTitle(event.target.value)} /></label>
        <label>考试时间（分钟）<input min={10} max={300} type="number" value={durationMinutes} onChange={(event) => setDurationMinutes(numberValue(event.target.value, durationMinutes))} /></label>
        <label>试卷总分<input min={items.length * 0.5} max={Math.min(300, items.length * 50)} step={0.5} type="number" value={targetTotalScore} onChange={(event) => setTargetTotalScore(numberValue(event.target.value, targetTotalScore))} /></label>
        <button className="paper-history-distribute" disabled={busy || items.length === 0 || targetTotalScore < items.length * 0.5 || targetTotalScore > items.length * 50} onClick={distributeTargetTotal} type="button">按总分平均调整题目分值</button>
      </div>
      <div className={`paper-history-editor-summary${totalMatches ? "" : " is-mismatch"}`}><strong>{items.length} 题 · 当前 {totalScore.toLocaleString("zh-CN")} / 目标 {targetTotalScore.toLocaleString("zh-CN")} 分</strong><span>{totalMatches ? `保存会生成版本 ${paper.version + 1} 并重算双向细目表。` : "请调整题目分值，或按目标总分平均分配后再保存。"}</span></div>
      <section className="paper-history-add-questions">
        <header><div><strong>增加题目</strong><span>可从受控公共题库或你的私题中加入；保存时服务端会再次验题。</span></div><button onClick={() => setAddingQuestions((current) => !current)} type="button">{addingQuestions ? "收起题库" : "添加题目"}</button></header>
        {addingQuestions && <div className="paper-history-add-grid">
          <section><h3>公共题库</h3>{publicCandidates.length === 0 ? <p>暂无可用公共题。</p> : <ul>{publicCandidates.map((candidate) => <li key={candidate.question_id}><div><strong>{QUESTION_TYPE_LABELS[candidate.question_type] ?? candidate.question_type}</strong><MathText text={candidate.stem_plain} /></div><button disabled={busy || items.length >= 50 || existingIds.has(candidate.question_id)} onClick={() => addPublicQuestion(candidate)} type="button">{existingIds.has(candidate.question_id) ? "已加入" : items.length >= 50 ? "已达上限" : "加入"}</button></li>)}</ul>}</section>
          <section><h3>我的私题</h3>{privateQuestions.length === 0 ? <p>暂无可用私题。</p> : <ul>{privateQuestions.map((candidate) => {
             const eligible = isPrivateQuestionSelectable(candidate)
               && candidate.question.verification.status !== "checks_failed"
               && !candidate.question.verification.checks.some((check) => check.status === "failed");
             const solutionLabel = candidate.question.solution_status === "needs_teacher_verification" ? "解析：无" : "解析：有";
             return <li key={candidate.question_id}><div><strong>{candidate.name}</strong><MathText text={candidate.question.stem_plain} /><small>{solutionLabel}</small></div><button disabled={busy || items.length >= 50 || !eligible || existingIds.has(candidate.question_id)} onClick={() => addPrivateQuestion(candidate)} type="button">{existingIds.has(candidate.question_id) ? "已加入" : items.length >= 50 ? "已达上限" : eligible ? candidate.question.solution_status === "needs_teacher_verification" ? "加入（无解析）" : "加入" : "尚未通过"}</button></li>;
          })}</ul>}</section>
        </div>}
      </section>
      <ol className="paper-history-editor-items">
        {items.map((item, index) => (
          <li key={item.question.question_id}>
            <header>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <strong>{QUESTION_TYPE_LABELS[item.question.question_type] ?? item.question.question_type}</strong>
              <div>
                <button disabled={busy || index === 0} onClick={() => moveItem(index, -1)} type="button">上移</button>
                <button disabled={busy || index === items.length - 1} onClick={() => moveItem(index, 1)} type="button">下移</button>
                <button className="is-danger" disabled={busy || items.length === 1} onClick={() => removeItem(index)} type="button">移除</button>
              </div>
            </header>
            <div className="paper-history-editor-stem"><MathText text={item.question.stem_plain} /></div>
            {item.question.options.length > 0 && <ol className="paper-history-editor-options">{item.question.options.map((option) => <li key={option.key}><b>{option.key}</b><MathText text={option.text} /></li>)}</ol>}
            {item.question.solution_status === "needs_teacher_verification" && <p className="paper-selection-solution-missing">解析：无（题面已审核，解析尚未生成）</p>}
            <div className="paper-history-editor-item-fields">
              <label>所属分区<input value={item.section_title} onChange={(event) => updateItem(index, { section_title: event.target.value })} /></label>
              <label>分值<input min={0.5} max={50} step={0.5} type="number" value={item.score} onChange={(event) => updateItem(index, { score: numberValue(event.target.value, item.score) })} /></label>
            </div>
          </li>
        ))}
      </ol>
      <footer>
        <button disabled={!canSave || busy} onClick={() => onSave({
          expected_version: paper.version,
          title: title.trim(),
          duration_minutes: durationMinutes,
          instructions: paper.instructions,
          target_total_score: targetTotalScore,
          selected_public_question_ids: items.filter((item) => item.added_source_kind === "public_question_bank").map((item) => item.question.question_id),
          selected_private_question_ids: items.filter((item) => item.added_source_kind === "personal_question_library").map((item) => item.question.question_id),
          items: items.map((item) => ({
            question_id: item.question.question_id,
            section_id: item.section_id,
            section_title: item.section_title.trim(),
            score: item.score,
          })),
        })} type="button">{busy ? "正在保存新版本…" : "另存新版本"}</button>
      </footer>
    </article>
  );
}

function paperDraftAdjustmentReasons(draft: PaperEditableDraft, items = draft.items): string[] {
  const reasons: string[] = [];
  const shortSections = draft.blueprint.sections.filter((section) => {
    const sectionItems = items.filter((item) => item.section_id === section.section_id);
    const sectionScore = sectionItems.reduce((sum, item) => sum + item.score, 0);
    return sectionItems.length !== section.question_count
      || Math.abs(sectionScore - section.target_score) > 0.001;
  });
  const actualScore = items.reduce((sum, item) => sum + item.score, 0);

  if (items.length !== draft.target_question_count) reasons.push("题量仍有真实缺口");
  if (shortSections.length > 0) reasons.push(`分区题量或配分未对齐：${shortSections.map((section) => section.title).join("、")}`);
  if (Math.abs(actualScore - draft.target_score) > 0.001) reasons.push("总分与蓝图不一致");
  return [...new Set(reasons)];
}

function paperDraftStructureComplete(draft: PaperEditableDraft, items = draft.items): boolean {
  return paperDraftAdjustmentReasons(draft, items).length === 0;
}

function paperDraftActualKnowledge(draft: PaperEditableDraft): string {
  const labels = draft.specification.dimension_to_questions
    .filter((row) => row.dimension === "knowledge_point")
    .map((row) => row.label.trim())
    .filter(Boolean);
  return [...new Set(labels)].join("、") || "暂未标注";
}

type PaperPublicQuestionPickerProps = {
  candidates: PaperPublicQuestionCandidate[];
  loading: boolean;
  onQueryChange: (value: string) => void;
  onSearch: () => void;
  onToggle: (questionId: string) => void;
  query: string;
  selectedIds: string[];
  total: number;
};

export function PaperPublicQuestionPicker({ candidates, loading, onQueryChange, onSearch, onToggle, query, selectedIds, total }: PaperPublicQuestionPickerProps) {
  return (
    <section className="paper-private-picker paper-public-picker">
      <header><PaperIcon /><div><strong>从公共题库中明确选择（可选）</strong><span>仅展示已通过公开可见性、权利、数学验证、教师审核和在架门禁的题目。</span></div></header>
      <div className="paper-public-picker__search">
        <input aria-label="搜索公共题库" onChange={(event) => onQueryChange(event.target.value)} placeholder="按题干、章节或知识点搜索" value={query} />
        <button disabled={loading} onClick={onSearch} type="button">{loading ? "正在读取…" : "搜索公共题库"}</button>
      </div>
      {loading ? <p className="paper-private-picker-state">正在读取通过门禁的公共题…</p> : candidates.length === 0 ? (
        <p className="paper-private-picker-state">当前公共题库没有通过全部公开、权利、审核与数学验证门禁的可用题；系统不会把待审核或私人题冒充公共题。</p>
      ) : (
        <><p className="paper-public-picker__count">找到 {total} 道可用公共题，当前显示 {candidates.length} 道。</p><ul>{candidates.map((question) => (
          <li key={question.question_id}><label><input checked={selectedIds.includes(question.question_id)} onChange={() => onToggle(question.question_id)} type="checkbox" /><span><strong><MathText text={question.stem_plain} /></strong><small>{QUESTION_TYPE_LABELS[question.question_type] ?? question.question_type} · 难度 {question.difficulty}/5 · {question.chapter ?? "未分类"}</small></span>{selectedIds.includes(question.question_id) && <CheckIcon />}</label></li>
        ))}</ul></>
      )}
    </section>
  );
}

export function PaperSelectionDraftView({ selection }: { selection: PaperBlueprintSelectionDraft }) {
  return (
    <section className="paper-selection-draft" aria-label="受控选题候选草案">
      <header>
        <div>
          <h2>{selection.selection_complete ? "题目已备齐" : "题目不足"}</h2>
        </div>
        <dl>
          <div><dt>题量</dt><dd>{selection.actual_question_count} / {selection.target_question_count}</dd></div>
          <div><dt>分值</dt><dd>{selection.actual_score.toLocaleString("zh-CN")} / {selection.target_score.toLocaleString("zh-CN")}</dd></div>
        </dl>
      </header>

      {selection.gaps.length > 0 && (
        <section className="paper-selection-gaps" aria-label="选题缺口">
          <ul>
            {selection.gaps.map((gap) => (
              <li key={gap.section_id}>
                <div><b>{gap.section_title}</b><span>缺 {gap.missing_count} 题 · {gap.missing_score.toLocaleString("zh-CN")} 分</span></div>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className={`paper-coverage-audit is-${selection.coverage_audit.status}`} aria-label="覆盖与难度对照">
        <header>
          <div><h3>选题结果分析</h3><p>系统根据教师选定的题目总结实际知识范围和难度；这些分析不限制教师选题。</p></div>
          <strong>{selection.selection_complete ? "分析已完成" : "题目不足"}</strong>
        </header>
        <div className="paper-coverage-grid">
          <section>
            <h4>分区覆盖</h4>
            <ul>{selection.coverage_audit.sections.map((item) => (
              <li key={item.section_id}>
                <div><b>{item.section_title}</b><em className={`is-${item.status}`}>{item.status === "met" ? "已覆盖" : "有缺口"}</em></div>
                <span>{item.actual_question_count} / {item.target_question_count} 题 · {item.actual_score.toLocaleString("zh-CN")} / {item.target_score.toLocaleString("zh-CN")} 分</span>
              </li>
            ))}</ul>
          </section>
          <section>
            <h4>知识范围</h4>
            <ul>{selection.coverage_audit.knowledge_points.map((item) => (
              <li key={item.knowledge_point}>
                <div><b>{item.knowledge_point}</b><em className={`is-${item.status}`}>{item.status === "covered" ? "已出现" : "未覆盖"}</em></div>
                <span>{item.actual_question_count} 题 · {item.actual_score.toLocaleString("zh-CN")} 分</span>
              </li>
            ))}</ul>
          </section>
        </div>
        <section className="paper-difficulty-audit">
          <header><div><h4>难度分布</h4><p>{DIFFICULTY_AUDIT_LABELS[selection.coverage_audit.difficulty_status]}</p></div><span>目标均值 {selection.coverage_audit.target_average_difficulty.toLocaleString("zh-CN")} · 实际 {selection.coverage_audit.actual_average_difficulty?.toLocaleString("zh-CN") ?? "—"}</span></header>
          <ol>{selection.coverage_audit.difficulty_bands.map((band) => (
            <li key={band.difficulty}><b>{band.difficulty} 级</b><span>目标 {band.target_question_count} 题</span><strong>实际 {band.actual_question_count} 题</strong></li>
          ))}</ol>
        </section>
      </section>

      <ol className="paper-selection-items">
        {selection.items.map((item) => (
          <li className={`is-${item.source_kind}`} key={`${item.section_id}-${item.question_id}`}>
            <header>
              <div>
                <span>{String(item.position).padStart(2, "0")}</span>
                <div><strong>{item.section_title}</strong><small>{QUESTION_TYPE_LABELS[item.question_type] ?? item.question_type} · {item.score.toLocaleString("zh-CN")} 分</small></div>
              </div>
              <b>{item.source_kind === "personal_question_library" ? "我的私题" : "公共题库"}</b>
            </header>
            <div className="paper-selection-stem"><MathText text={item.stem_plain} /></div>
            {item.solution_status === "needs_teacher_verification" && <p className="paper-selection-solution-missing">解析：无（题面已审核，解析尚未生成）</p>}
            {item.options.length > 0 && (
              <ol className="paper-selection-options">
                {item.options.map((option) => <li key={option.key}><b>{option.key}</b><MathText text={option.text} /></li>)}
              </ol>
            )}
          </li>
        ))}
      </ol>

      {selection.similarity_exclusions.length > 0 && (
        <p className="paper-selection-similarity-note">已排除 {selection.similarity_exclusions.length} 道重复或高度相似题，未写入候选清单。</p>
      )}
    </section>
  );
}

type PaperEditableDraftViewProps = {
  draft: PaperEditableDraft;
  applying: boolean;
  saving: boolean;
  exporting: string;
  savedVersion: PaperSavedVersion | null;
  onApply: (edits: PaperDraftItemEdit[]) => void;
  onSave: () => void;
  onExport: (option: PaperSavedVersion["available_exports"][number]) => void;
};

export function PaperEditableDraftView({ draft, applying, saving, exporting, savedVersion, onApply, onSave, onExport }: PaperEditableDraftViewProps) {
  const [items, setItems] = useState<PaperSelectionItem[]>(draft.items);
  useEffect(() => setItems(draft.items), [draft]);

  const normalizedEdits = useMemo<PaperDraftItemEdit[]>(() => items.map((item, index) => ({
    question_id: item.question_id,
    position: index + 1,
    section_id: item.section_id,
    score: item.score,
  })), [items]);
  const dirty = useMemo(() => normalizedEdits.some((edit, index) => {
    const original = draft.items[index];
    return !original
      || original.question_id !== edit.question_id
      || original.position !== edit.position
      || original.section_id !== edit.section_id
      || Math.abs(original.score - edit.score) > 0.001;
  }), [draft.items, normalizedEdits]);
  const localScore = useMemo(() => items.reduce((sum, item) => sum + item.score, 0), [items]);
  const adjustmentReasons = paperDraftAdjustmentReasons(draft, items);
  const structureComplete = paperDraftStructureComplete(draft, items);
  const actualKnowledge = paperDraftActualKnowledge(draft);
  const analysisHasDeviation = draft.coverage_audit.status !== "matched";
  const statusDetail = structureComplete
    ? dirty
      ? "题量、分区与总分已满足；当前修改尚未应用，请先重算细目表"
      : "题量、分区与总分已满足；知识与难度分析仅供对照"
    : adjustmentReasons.join("；") || "题量、分区或总分仍未满足";

  function moveItem(index: number, offset: -1 | 1) {
    const target = index + offset;
    if (target < 0 || target >= items.length) return;
    setItems((current) => {
      const next = [...current];
      [next[index], next[target]] = [next[target], next[index]];
      return next.map((item, itemIndex) => ({ ...item, position: itemIndex + 1 }));
    });
  }

  function updateItem(questionId: string, patch: Partial<PaperSelectionItem>) {
    setItems((current) => current.map((item) => item.question_id === questionId ? { ...item, ...patch } : item));
  }

  return (
    <section className="paper-editable-draft" aria-label="可编辑试卷与双向细目表">
      <header>
        <div><p>未保存草稿</p><h2>可编辑试卷与双向细目表</h2><span>调整题目顺序、分区和配分后，由服务器重新核对蓝图并重算细目表。</span></div>
        <dl>
          <div><dt>题量</dt><dd>{items.length} / {draft.target_question_count}</dd></div>
          <div><dt>分值</dt><dd>{localScore.toLocaleString("zh-CN")} / {draft.target_score.toLocaleString("zh-CN")}</dd></div>
        </dl>
      </header>

      <div className={`paper-draft-status${structureComplete ? " is-matched" : " is-adjusting"}`}>
        <strong>{structureComplete ? "题量、分区与总分已满足" : "草稿尚未完善"}</strong>
        <span>{statusDetail}</span>
      </div>

      <section className="paper-draft-analysis" aria-label="所选题目知识与难度分析">
        <header><div><p>系统分析</p><h3>系统已根据所选题目完成分析</h3></div><strong>{analysisHasDeviation ? "仅供对照，不阻止保存" : "与原蓝图相近"}</strong></header>
        <dl>
          <div><dt>实际知识范围</dt><dd>实际知识范围：{actualKnowledge}</dd></div>
          <div><dt>实际难度</dt><dd>实际难度均值：{draft.coverage_audit.actual_average_difficulty?.toLocaleString("zh-CN") ?? "—"}</dd></div>
          <div><dt>原蓝图参考</dt><dd>{draft.blueprint.knowledge_points.join("、")} · 难度均值 {draft.coverage_audit.target_average_difficulty.toLocaleString("zh-CN")}</dd></div>
        </dl>
      </section>

      {draft.gaps.length > 0 && <section className="paper-selection-gaps" aria-label="可编辑试卷题目缺口"><ul>{draft.gaps.map((gap) => <li key={gap.section_id}><div><b>{gap.section_title}</b><span>缺 {gap.missing_count} 题 · {gap.missing_score.toLocaleString("zh-CN")} 分</span></div></li>)}</ul></section>}

      <section className="paper-save-export" aria-label="保存与导出">
        <header><div><p>版本操作</p><h3>保存与导出</h3></div><span>{savedVersion ? `当前为不可变版本 ${savedVersion.version}` : "当前仍是未保存草稿"}</span></header>
        <div className="paper-draft-actions">
          <p><strong>{dirty ? "有尚未应用的调整" : savedVersion ? `版本 ${savedVersion.version} 已保存` : structureComplete ? "当前试卷结构已完成服务器核对" : "试卷尚未完善，仍可由教师确认保存"}</strong><span>{dirty ? "请先应用当前页面调整，避免保存旧版布局。" : savedVersion ? "导出始终读取这个不可变版本，不读取屏幕上的临时状态。" : structureComplete ? "确认无误后，明确保存为不可变版本；知识点与难度以系统分析结果写入细目表。" : `${statusDetail}。点击保存后可选择取消或确认。`}</span></p>
          <div>
            <button disabled={!dirty || applying || saving || items.length === 0} onClick={() => onApply(normalizedEdits)} type="button">{applying ? "正在重新核对…" : "应用调整并重算细目表"}</button>
            <button className="is-save" disabled={dirty || applying || saving || items.length === 0 || Boolean(savedVersion)} onClick={onSave} type="button">{saving ? "正在保存版本…" : savedVersion ? `已保存版本 ${savedVersion.version}` : "保存为正式版本"}</button>
          </div>
        </div>

        {savedVersion ? (
          <section className="paper-saved-version" aria-label={`已保存试卷版本 ${savedVersion.version}`}>
            <header><div><p>不可变版本</p><h3>{savedVersion.title} · 版本 {savedVersion.version}</h3></div><span>{savedVersion.question_count} 道题 · {savedVersion.total_score.toLocaleString("zh-CN")} 分</span></header>
            <p>已绑定当前教师、完整题目快照与双向细目表。下面所有文件均由这一精确版本生成。</p>
            <div>{savedVersion.available_exports.map((option) => {
              const key = `${option.edition}-${option.format}`;
              return <button disabled={Boolean(exporting)} key={key} onClick={() => onExport(option)} type="button">{exporting === key ? "正在导出…" : option.label}</button>;
            })}</div>
          </section>
        ) : (
          <section className="paper-export-preview" aria-label="保存后可用导出格式">
            <p>保存后可导出学生卷、答案卷和双向细目表；导出只读取已保存的不可变版本。</p>
            <div>{PAPER_EXPORT_PREVIEW_LABELS.map((label) => <button disabled key={label} type="button">{label}</button>)}</div>
          </section>
        )}
      </section>

      <ol className="paper-editable-items">
        {items.map((item, index) => {
          const availableSections = draft.blueprint.sections.filter((section) => section.question_type === item.question_type);
          return (
            <li key={item.question_id}>
              <header>
                <div><span>{String(index + 1).padStart(2, "0")}</span><div><strong>{QUESTION_TYPE_LABELS[item.question_type] ?? item.question_type}</strong><small>{item.source_kind === "personal_question_library" ? "我的私题" : "公共题库"}</small></div></div>
                <div className="paper-item-order" aria-label={`调整第 ${index + 1} 题顺序`}>
                  <button disabled={index === 0} onClick={() => moveItem(index, -1)} type="button">上移</button>
                  <button disabled={index === items.length - 1} onClick={() => moveItem(index, 1)} type="button">下移</button>
                </div>
              </header>
              <div className="paper-selection-stem"><MathText text={item.stem_plain} /></div>
              {item.solution_status === "needs_teacher_verification" && <p className="paper-selection-solution-missing">解析：无（题面已审核，解析尚未生成）</p>}
              {item.options.length > 0 && <ol className="paper-selection-options">{item.options.map((option) => <li key={option.key}><b>{option.key}</b><MathText text={option.text} /></li>)}</ol>}
              <div className="paper-item-controls">
                <label>所属分区<select value={item.section_id} onChange={(event) => updateItem(item.question_id, { section_id: event.target.value, section_title: availableSections.find((section) => section.section_id === event.target.value)?.title ?? item.section_title })}>{availableSections.map((section) => <option key={section.section_id} value={section.section_id}>{section.title}</option>)}</select></label>
                <label>分值<input min={0.5} max={50} step={0.5} type="number" value={item.score} onChange={(event) => updateItem(item.question_id, { score: numberValue(event.target.value, item.score) })} /></label>
              </div>
            </li>
          );
        })}
      </ol>

      {draft.change_log.length > 0 && <section className="paper-change-log"><h3>本草稿修改记录</h3><ol>{draft.change_log.map((change, index) => <li key={`${change.question_id}-${change.kind}-${index}`}>{change.description}</li>)}</ol></section>}

      <section className="paper-specification" aria-label="双向细目表">
        <header><div><p>双向细目表</p><h3>题目与教学维度双向核对</h3></div><span>{draft.specification.question_to_dimensions.length} 道题 · {draft.specification.dimension_to_questions.length} 个反向索引</span></header>
        <div className="paper-specification-table-wrap">
          <table>
            <caption>题目到教学维度</caption>
            <thead><tr><th>题号</th><th>分区</th><th>题型</th><th>章节</th><th>知识点</th><th>难度</th><th>分值</th></tr></thead>
            <tbody>{draft.specification.question_to_dimensions.map((row) => <tr key={row.question_id}><td>{row.position}</td><td>{row.section_title}</td><td>{QUESTION_TYPE_LABELS[row.question_type] ?? row.question_type}</td><td>{row.chapter}</td><td>{row.knowledge_points.join("、")}</td><td>{row.difficulty}</td><td>{row.score.toLocaleString("zh-CN")}</td></tr>)}</tbody>
          </table>
        </div>
        <div className="paper-specification-table-wrap">
          <table>
            <caption>教学维度到题目</caption>
            <thead><tr><th>维度</th><th>项目</th><th>对应题号</th><th>题量</th><th>分值</th></tr></thead>
            <tbody>{draft.specification.dimension_to_questions.map((row) => <tr key={`${row.dimension}-${row.label}`}><td>{SPECIFICATION_DIMENSION_LABELS[row.dimension]}</td><td>{row.dimension === "question_type" ? QUESTION_TYPE_LABELS[row.label] ?? row.label : row.label}</td><td>{row.positions.join("、")}</td><td>{row.question_count}</td><td>{row.score.toLocaleString("zh-CN")}</td></tr>)}</tbody>
          </table>
        </div>
      </section>
    </section>
  );
}

export function PaperBlueprintWorkspace({ initialBrief, onBriefChange, onOpenAuthoring }: PaperBlueprintWorkspaceProps) {
  const [brief, setBrief] = useState(initialBrief);
  const [blueprint, setBlueprint] = useState<PaperBlueprintDraft | null>(null);
  const [selection, setSelection] = useState<PaperBlueprintSelectionDraft | null>(null);
  const [editableDraft, setEditableDraft] = useState<PaperEditableDraft | null>(null);
  const [privateQuestions, setPrivateQuestions] = useState<PersonalQuestion[]>([]);
  const [publicQuestions, setPublicQuestions] = useState<PaperPublicQuestionCandidate[]>([]);
  const [publicQuestionTotal, setPublicQuestionTotal] = useState(0);
  const [publicQuery, setPublicQuery] = useState("");
  const [selectedPrivateIds, setSelectedPrivateIds] = useState<string[]>([]);
  const [selectedPublicIds, setSelectedPublicIds] = useState<string[]>([]);
  const [running, setRunning] = useState(false);
  const [selecting, setSelecting] = useState(false);
  const [applyingDraft, setApplyingDraft] = useState(false);
  const [savingDraft, setSavingDraft] = useState(false);
  const [saveConfirmationOpen, setSaveConfirmationOpen] = useState(false);
  const [exportingVersion, setExportingVersion] = useState("");
  const [savedVersion, setSavedVersion] = useState<PaperSavedVersion | null>(null);
  const [paperHistory, setPaperHistory] = useState<PaperHistoryItem[]>([]);
  const [paperHistoryLifecycle, setPaperHistoryLifecycle] = useState<PaperHistoryLifecycle>("active");
  const [paperHistoryLoading, setPaperHistoryLoading] = useState(false);
  const [paperHistoryBusy, setPaperHistoryBusy] = useState("");
  const [paperHistoryDeleteTarget, setPaperHistoryDeleteTarget] = useState<PaperHistoryItem | null>(null);
  const [paperHistoryPaper, setPaperHistoryPaper] = useState<PaperHistoryPaper | null>(null);
  const [paperHistoryRevision, setPaperHistoryRevision] = useState<PaperHistoryRevisionRequest | null>(null);
  const [privateLoading, setPrivateLoading] = useState(false);
  const [publicLoading, setPublicLoading] = useState(false);
  const [error, setError] = useState("");
  const abortRef = useRef<AbortController | null>(null);
  const selectionAbortRef = useRef<AbortController | null>(null);
  const submitRef = useRef<HTMLButtonElement | null>(null);
  const totalSectionScore = useMemo(
    () => blueprint?.sections.reduce((sum, section) => sum + section.target_score, 0) ?? 0,
    [blueprint],
  );
  const totalQuestions = useMemo(
    () => blueprint?.sections.reduce((sum, section) => sum + section.question_count, 0) ?? 0,
    [blueprint],
  );
  const blueprintReady = Boolean(
    blueprint
      && blueprint.title.trim()
      && blueprint.grade_scope.trim()
      && blueprint.teaching_usage.trim()
      && blueprint.knowledge_points.length > 0
      && totalQuestions > 0
      && Math.abs(totalSectionScore - blueprint.target_score) <= 0.001,
  );

  const loadPaperHistory = useCallback(async (
    lifecycle: PaperHistoryLifecycle,
    signal?: AbortSignal,
  ) => {
    setPaperHistoryLoading(true);
    try {
      const result = await teacherWorkspace.listPaperHistory(lifecycle, signal);
      setPaperHistory(result.items);
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === "AbortError") return;
      setPaperHistory([]);
      setError(errorMessage(cause, "你的历史组卷暂时无法读取。"));
    } finally {
      setPaperHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void loadPaperHistory("active", controller.signal);
    return () => controller.abort();
  }, [loadPaperHistory]);

  function updateBrief(value: string) {
    setBrief(value);
    onBriefChange(value);
  }

  async function loadPrivateQuestions() {
    setPrivateLoading(true);
    try {
      const result = await teacherWorkspace.listPersonalQuestions({ lifecycleState: "active" });
      setPrivateQuestions(result.items);
    } catch (cause) {
      setPrivateQuestions([]);
      setError(errorMessage(cause, "你的私题暂时无法读取；公共题库选题仍可继续。"));
    } finally {
      setPrivateLoading(false);
    }
  }

  async function loadPublicQuestions(query = publicQuery) {
    setPublicLoading(true);
    try {
      const result = await teacherWorkspace.listPaperPublicCandidates({ query, limit: 50 });
      setPublicQuestions(result.items);
      setPublicQuestionTotal(result.total);
    } catch (cause) {
      setPublicQuestions([]);
      setPublicQuestionTotal(0);
      setError(errorMessage(cause, "公共题库候选暂时无法读取；你仍可使用自己的私题。"));
    } finally {
      setPublicLoading(false);
    }
  }

  async function plan(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = brief.trim();
    if (trimmed.length < 5 || running) return;
    const controller = new AbortController();
    abortRef.current = controller;
    setRunning(true);
    setError("");
    setSelection(null);
    setEditableDraft(null);
    setSavedVersion(null);
    setPaperHistoryPaper(null);
    setSelectedPrivateIds([]);
    setSelectedPublicIds([]);
    try {
      setBlueprint(await teacherWorkspace.planPaperBlueprint(trimmed, controller.signal));
      void loadPrivateQuestions();
      void loadPublicQuestions("");
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === "AbortError") return;
      setError(errorMessage(cause, "组卷蓝图没有整理完成，请稍后重试。"));
    } finally {
      abortRef.current = null;
      setRunning(false);
    }
  }

  function updateBlueprint(patch: Partial<PaperBlueprintDraft>) {
    setSelection(null);
    setEditableDraft(null);
    setSavedVersion(null);
    setBlueprint((current) => current ? { ...current, ...patch } : current);
  }

  function updateSection(index: number, patch: Partial<PaperBlueprintSection>) {
    setSelection(null);
    setEditableDraft(null);
    setSavedVersion(null);
    setBlueprint((current) => current
      ? { ...current, sections: current.sections.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item) }
      : current);
  }

  function togglePrivateQuestion(questionId: string) {
    setSelection(null);
    setEditableDraft(null);
    setSavedVersion(null);
    setSelectedPrivateIds((current) => current.includes(questionId)
      ? current.filter((item) => item !== questionId)
      : [...current, questionId]);
  }

  function togglePublicQuestion(questionId: string) {
    setSelection(null);
    setEditableDraft(null);
    setSavedVersion(null);
    setSelectedPublicIds((current) => current.includes(questionId)
      ? current.filter((item) => item !== questionId)
      : [...current, questionId]);
  }

  async function confirmAndSelect() {
    if (!blueprint || !blueprintReady || selecting) return;
    const controller = new AbortController();
    selectionAbortRef.current = controller;
    setSelecting(true);
    setError("");
    try {
      const selected = await teacherWorkspace.selectPaperBlueprint(blueprint, selectedPrivateIds, selectedPublicIds, controller.signal);
      setSelection(selected);
      setEditableDraft(await teacherWorkspace.editPaperDraft(blueprint, selectedPrivateIds, selectedPublicIds, [], controller.signal));
      setSavedVersion(null);
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === "AbortError") return;
      setError(errorMessage(cause, "蓝图确认或受控选题没有完成，请稍后重试。"));
    } finally {
      selectionAbortRef.current = null;
      setSelecting(false);
    }
  }

  async function applyDraft(edits: PaperDraftItemEdit[]) {
    if (!blueprint || applyingDraft) return;
    const controller = new AbortController();
    selectionAbortRef.current = controller;
    setApplyingDraft(true);
    setError("");
    try {
      setEditableDraft(await teacherWorkspace.editPaperDraft(blueprint, selectedPrivateIds, selectedPublicIds, edits, controller.signal));
      setSavedVersion(null);
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === "AbortError") return;
      setError(errorMessage(cause, "试卷调整没有完成，请检查题号、分区和配分后重试。"));
    } finally {
      selectionAbortRef.current = null;
      setApplyingDraft(false);
    }
  }

  async function saveVersion() {
    if (!blueprint || !editableDraft || savingDraft || editableDraft.items.length === 0) return;
    const controller = new AbortController();
    selectionAbortRef.current = controller;
    setSavingDraft(true);
    setError("");
    try {
      const edits = editableDraft.items.map((item, index) => ({
        question_id: item.question_id,
        position: index + 1,
        section_id: item.section_id,
        score: item.score,
      }));
      setSavedVersion(await teacherWorkspace.savePaperVersion(
        blueprint,
        selectedPrivateIds,
        selectedPublicIds,
        edits,
        editableDraft.draft_fingerprint,
        controller.signal,
      ));
      setSaveConfirmationOpen(false);
      setPaperHistoryLifecycle("active");
      void loadPaperHistory("active");
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === "AbortError") return;
      setSaveConfirmationOpen(false);
      setError(errorMessage(cause, "当前试卷版本没有保存完成，请重新核对后重试。"));
    } finally {
      selectionAbortRef.current = null;
      setSavingDraft(false);
    }
  }

  async function exportVersion(option: PaperSavedVersion["available_exports"][number]) {
    if (!savedVersion || exportingVersion) return;
    const key = `${option.edition}-${option.format}`;
    setExportingVersion(key);
    setError("");
    try {
      const artifact = await teacherWorkspace.exportPaperVersion(
        savedVersion.exam_paper_id,
        savedVersion.version,
        option.format,
        option.edition,
      );
      const url = URL.createObjectURL(artifact.blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = artifact.filename;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (cause) {
      setError(errorMessage(cause, "这个已保存版本没有导出完成，请稍后重试。"));
    } finally {
      setExportingVersion("");
    }
  }

  async function selectPaperHistoryLifecycle(lifecycle: PaperHistoryLifecycle) {
    if (paperHistoryLoading || paperHistoryBusy) return;
    setPaperHistoryLifecycle(lifecycle);
    await loadPaperHistory(lifecycle);
  }

  async function changePaperHistoryLifecycle(
    item: PaperHistoryItem,
    action: "trash" | "restore",
  ) {
    const key = `${action}-${item.exam_paper_id}`;
    if (paperHistoryBusy) return;
    setPaperHistoryBusy(key);
    setError("");
    try {
      await teacherWorkspace.changePaperHistoryLifecycle(item.exam_paper_id, action);
      setPaperHistoryDeleteTarget(null);
      if (action === "trash" && paperHistoryPaper?.exam_paper_id === item.exam_paper_id) {
        setPaperHistoryPaper(null);
      }
      await loadPaperHistory(paperHistoryLifecycle);
    } catch (cause) {
      setPaperHistoryDeleteTarget(null);
      setError(errorMessage(cause, action === "trash" ? "这份历史组卷没有删除成功。" : "这份历史组卷没有恢复成功。"));
    } finally {
      setPaperHistoryBusy("");
    }
  }

  async function exportPaperHistory(
    item: PaperHistoryItem,
    edition: "student" | "answer" | "blueprint",
  ) {
    const key = `export-${item.exam_paper_id}-${edition}`;
    if (paperHistoryBusy) return;
    setPaperHistoryBusy(key);
    setError("");
    try {
      const artifact = await teacherWorkspace.exportPaperVersion(
        item.exam_paper_id,
        item.version,
        "pdf",
        edition,
      );
      const url = URL.createObjectURL(artifact.blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = artifact.filename;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (cause) {
      setError(errorMessage(cause, "这份历史组卷没有导出成功。"));
    } finally {
      setPaperHistoryBusy("");
    }
  }

  async function openPaperHistory(item: PaperHistoryItem) {
    if (paperHistoryBusy) return;
    setPaperHistoryBusy(`open-${item.exam_paper_id}`);
    setError("");
    try {
      const [paper] = await Promise.all([
        teacherWorkspace.getPaperHistoryPaper(item.exam_paper_id),
        loadPrivateQuestions(),
        loadPublicQuestions(""),
      ]);
      setPaperHistoryPaper(paper);
    } catch (cause) {
      setError(errorMessage(cause, "这份历史组卷没有打开成功。"));
    } finally {
      setPaperHistoryBusy("");
    }
  }

  async function savePaperHistoryRevision() {
    if (!paperHistoryPaper || !paperHistoryRevision || paperHistoryBusy) return;
    setPaperHistoryBusy(`revise-${paperHistoryPaper.exam_paper_id}`);
    setError("");
    try {
      const updated = await teacherWorkspace.revisePaperHistoryPaper(
        paperHistoryPaper.exam_paper_id,
        paperHistoryRevision,
      );
      setPaperHistoryPaper(updated);
      setPaperHistoryRevision(null);
      await loadPaperHistory("active");
    } catch (cause) {
      setPaperHistoryRevision(null);
      setError(errorMessage(cause, "历史试卷的新版本没有保存成功。"));
    } finally {
      setPaperHistoryBusy("");
    }
  }

  return (
    <main className="paper-blueprint-workspace">
      <ResizableSplitPane ariaLabel="调整组卷要求与蓝图区域宽度" className="paper-blueprint-split" defaultPrimaryPercent={40}>
        <section className="paper-blueprint-intent">
          <p className="mode-status"><i className="is-ready" aria-hidden="true" />Paper Agent · 蓝图规划与受控选题已接入</p>
          <h1>先把组卷要求，<br />整理成可编辑蓝图。</h1>
          <p className="intro-copy">先整理范围、结构、题量与配分；经你确认后，只从通过门禁的公共题和你明确选择的私题中建立候选清单。</p>
          <form onSubmit={plan}>
            <label htmlFor="paper-blueprint-brief">描述组卷需求</label>
            <div className={`composer-surface${running ? " is-running" : ""}`}>
              <textarea id="paper-blueprint-brief" onChange={(event) => updateBrief(event.target.value)} placeholder="例如：组一份高二期中卷，120 分钟，总分 150 分，覆盖函数、导数与圆锥曲线" readOnly={running} rows={5} value={brief} />
              <div className="composer-actions">
                <span className="form-help">先生成蓝图，再由你逐项调整。</span>
                {running ? (
                  <button className="cancel-button" onClick={() => abortRef.current?.abort()} type="button"><CloseIcon /><span>取消</span></button>
                ) : (
                  <button className="run-button" disabled={brief.trim().length < 5} ref={submitRef} type="submit"><span>整理组卷蓝图</span><ArrowUpIcon /></button>
                )}
              </div>
            </div>
          </form>
          <div className="paper-blueprint-examples" aria-label="组卷蓝图示例">
            {EXAMPLES.map((example, index) => (
              <button key={example} onClick={() => updateBrief(example)} type="button"><span>{String(index + 1).padStart(2, "0")}</span><p>{example}</p><ArrowRightIcon /></button>
            ))}
          </div>
          <PaperHistoryPanel
            busyKey={paperHistoryBusy}
            items={paperHistory}
            lifecycle={paperHistoryLifecycle}
            loading={paperHistoryLoading}
            onExport={(item, edition) => void exportPaperHistory(item, edition)}
            onLifecycleChange={(item, action) => action === "trash" ? setPaperHistoryDeleteTarget(item) : void changePaperHistoryLifecycle(item, action)}
            onOpen={(item) => void openPaperHistory(item)}
            onSelectLifecycle={(lifecycle) => void selectPaperHistoryLifecycle(lifecycle)}
          />
          <section className="paper-blueprint-authoring-note">
            <p><strong>另有明确命题需求？</strong><span>辅助命题是独立私有工作流，不会自动加入当前蓝图。</span></p>
            <button onClick={() => onOpenAuthoring(brief)} type="button">进入辅助命题 <ArrowRightIcon /></button>
          </section>
        </section>

        <section className="paper-blueprint-desk" aria-live="polite">
          {paperHistoryPaper ? (
            <PaperHistoryEditor busy={paperHistoryBusy.startsWith("revise-")} onClose={() => setPaperHistoryPaper(null)} onSave={setPaperHistoryRevision} paper={paperHistoryPaper} privateQuestions={privateQuestions} publicCandidates={publicQuestions} />
          ) : !blueprint ? (
            <div className="paper-blueprint-empty"><PaperIcon /><p>PaperBlueprint / 规划与选题</p><h2>这里会出现一份可修改的组卷结构。</h2><span>当前没有题目，也没有产生任何保存或权限变更。</span></div>
          ) : (
            <>
              <article className="paper-blueprint-sheet">
                <header>
                  <div><p>PAPER BLUEPRINT · DRAFT</p><h2>可编辑组卷蓝图</h2></div>
                  <ul aria-label="蓝图状态"><li>{selection ? "已确认" : "未确认"}</li><li>未保存</li><li>{selection ? "候选草案" : "未选题"}</li></ul>
                </header>

                {blueprint.assumptions.length > 0 && <section className="paper-blueprint-assumptions"><strong>需要你核对的默认假设</strong><ul>{blueprint.assumptions.map((item) => <li key={item}>{item}</li>)}</ul></section>}

                <div className="paper-blueprint-fields">
                  <label className="wide">试卷名称<input value={blueprint.title} onChange={(event) => updateBlueprint({ title: event.target.value })} /></label>
                  <label>年级范围<input value={blueprint.grade_scope} onChange={(event) => updateBlueprint({ grade_scope: event.target.value })} /></label>
                  <label>教学用途<input value={blueprint.teaching_usage} onChange={(event) => updateBlueprint({ teaching_usage: event.target.value })} /></label>
                  <label>考试时间（分钟）<input min={10} max={300} type="number" value={blueprint.duration_minutes} onChange={(event) => updateBlueprint({ duration_minutes: numberValue(event.target.value, blueprint.duration_minutes) })} /></label>
                  <label>目标总分<input min={5} max={300} step={0.5} type="number" value={blueprint.target_score} onChange={(event) => updateBlueprint({ target_score: numberValue(event.target.value, blueprint.target_score) })} /></label>
                  <label>难度结构<select value={blueprint.difficulty_profile} onChange={(event) => updateBlueprint({ difficulty_profile: event.target.value as PaperBlueprintDifficulty })}>{Object.entries(DIFFICULTY_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
                  <label className="wide">知识范围（用顿号分隔）<input value={blueprint.knowledge_points.join("、")} onChange={(event) => updateBlueprint({ knowledge_points: event.target.value.split(/[、,，]/).map((item) => item.trim()).filter(Boolean) })} /></label>
                </div>

                <section className="paper-blueprint-structure">
                  <header><div><strong>题型与配分</strong><span>{totalQuestions} 道 · {totalSectionScore.toLocaleString("zh-CN")} / {blueprint.target_score.toLocaleString("zh-CN")} 分</span></div>{Math.abs(totalSectionScore - blueprint.target_score) > 0.001 && <b>分区合计与目标总分不一致，请调整。</b>}</header>
                  <div className="paper-blueprint-section-list">
                    {blueprint.sections.map((section, index) => (
                      <div key={section.section_id}>
                        <span>{String(index + 1).padStart(2, "0")}</span>
                        <label>分区名称<input value={section.title} onChange={(event) => updateSection(index, { title: event.target.value })} /></label>
                        <label>题量<input min={0} max={30} type="number" value={section.question_count} onChange={(event) => updateSection(index, { question_count: numberValue(event.target.value, section.question_count) })} /></label>
                        <label>分值<input min={0} max={300} step={0.5} type="number" value={section.target_score} onChange={(event) => updateSection(index, { target_score: numberValue(event.target.value, section.target_score) })} /></label>
                      </div>
                    ))}
                  </div>
                </section>

                <PaperPublicQuestionPicker candidates={publicQuestions} loading={publicLoading} onQueryChange={setPublicQuery} onSearch={() => void loadPublicQuestions()} onToggle={togglePublicQuestion} query={publicQuery} selectedIds={selectedPublicIds} total={publicQuestionTotal} />

                <section className="paper-private-picker">
                  <header><LockIcon /><div><strong>从你的私题中明确选择（可选）</strong><span>只读取当前教师的题目；未勾选的私题不会进入候选池。</span></div></header>
                  {privateLoading ? <p className="paper-private-picker-state">正在读取你的可用私题…</p> : privateQuestions.length === 0 ? <p className="paper-private-picker-state">当前没有可供明确选择的私题，可继续使用公共题库选题。</p> : (
                    <ul>{privateQuestions.map((question) => (
                       <li key={question.question_id}><label><input checked={selectedPrivateIds.includes(question.question_id)} onChange={() => togglePrivateQuestion(question.question_id)} type="checkbox" /><span><strong>{question.name}</strong><small>{QUESTION_TYPE_LABELS[question.question.question_type] ?? question.question.question_type} · 修订 {question.selected_revision} · {question.question.solution_status === "needs_teacher_verification" ? "解析：无" : "解析：有"}</small></span>{selectedPrivateIds.includes(question.question_id) && <CheckIcon />}</label></li>
                    ))}</ul>
                  )}
                </section>

                <footer>
                  {selecting ? <button className="is-selecting" onClick={() => selectionAbortRef.current?.abort()} type="button">取消受控选题</button> : <button disabled={!blueprintReady} onClick={confirmAndSelect} type="button">确认蓝图并受控选题</button>}
                </footer>
              </article>

              {selection && !editableDraft && <PaperSelectionDraftView selection={selection} />}
              {editableDraft && <PaperEditableDraftView applying={applyingDraft} draft={editableDraft} exporting={exportingVersion} onApply={applyDraft} onExport={exportVersion} onSave={() => setSaveConfirmationOpen(true)} savedVersion={savedVersion} saving={savingDraft} />}
            </>
          )}
        </section>
      </ResizableSplitPane>

      <WorkbenchNoticeDialog message={error} onDismiss={() => setError("")} open={Boolean(error)} returnFocusRef={submitRef} title="组卷操作没有完成" tone="error" />
      <WorkbenchNoticeDialog
        actionLabel="确认保存"
        busy={savingDraft}
        closeLabel="取消"
        message={editableDraft && paperDraftStructureComplete(editableDraft)
          ? "将按当前题目、顺序、分区和配分建立不可变版本。确认保存吗？"
          : `试卷尚未完善，确认保存吗？${editableDraft ? ` 当前情况：${paperDraftAdjustmentReasons(editableDraft).join("；") || "未达到原蓝图目标"}。` : ""}`}
        onAction={() => void saveVersion()}
        onDismiss={() => setSaveConfirmationOpen(false)}
        open={saveConfirmationOpen}
        returnFocusRef={submitRef}
        title="试卷尚未完善，确认保存吗"
        tone="warning"
      />
      <WorkbenchNoticeDialog
        actionLabel="保存新版本"
        busy={paperHistoryBusy.startsWith("revise-")}
        closeLabel="取消"
        message={paperHistoryRevision ? `将保留旧版本，并按当前的 ${paperHistoryRevision.items.length} 道题、顺序、分区和配分建立新版本。` : ""}
        onAction={() => void savePaperHistoryRevision()}
        onDismiss={() => setPaperHistoryRevision(null)}
        open={Boolean(paperHistoryRevision)}
        returnFocusRef={submitRef}
        title="确认保存历史试卷的新版本吗"
        tone="warning"
      />
      <WorkbenchNoticeDialog
        actionLabel="确认删除"
        busy={paperHistoryBusy.startsWith("trash-")}
        closeLabel="取消"
        message={paperHistoryDeleteTarget ? `“${paperHistoryDeleteTarget.title}”将移入只有你可见的回收站，之后仍可恢复。` : ""}
        onAction={() => paperHistoryDeleteTarget && void changePaperHistoryLifecycle(paperHistoryDeleteTarget, "trash")}
        onDismiss={() => setPaperHistoryDeleteTarget(null)}
        open={Boolean(paperHistoryDeleteTarget)}
        returnFocusRef={submitRef}
        title="删除这份历史组卷吗"
        tone="warning"
      />
    </main>
  );
}
