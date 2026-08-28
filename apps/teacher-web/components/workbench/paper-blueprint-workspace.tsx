"use client";

import { type FormEvent, useMemo, useRef, useState } from "react";
import { MathText } from "@/components/math-text";
import {
  type PaperBlueprintDraft,
  type PaperBlueprintDifficulty,
  type PaperBlueprintSection,
  type PaperBlueprintSelectionDraft,
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

function numberValue(value: string, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function errorMessage(cause: unknown, fallback: string): string {
  return cause instanceof TeacherWorkspaceError ? cause.message : fallback;
}

export function PaperSelectionDraftView({ selection }: { selection: PaperBlueprintSelectionDraft }) {
  return (
    <section className="paper-selection-draft" aria-label="受控选题候选草案">
      <header>
        <div>
          <p>CONTROLLED SELECTION · DRAFT</p>
          <h2>{selection.selection_complete ? "候选题已通过门禁" : "候选题存在真实缺口"}</h2>
          <span>只形成当前蓝图的候选清单；没有保存、复制或改变任何题目的权限。</span>
        </div>
        <dl>
          <div><dt>题量</dt><dd>{selection.actual_question_count} / {selection.target_question_count}</dd></div>
          <div><dt>分值</dt><dd>{selection.actual_score.toLocaleString("zh-CN")} / {selection.target_score.toLocaleString("zh-CN")}</dd></div>
        </dl>
      </header>

      {selection.gaps.length > 0 && (
        <section className="paper-selection-gaps" aria-label="选题缺口">
          <strong>没有用不合格题目填满蓝图</strong>
          <p>以下位置缺少通过验证、审核、范围和相似度门禁的现成题目。系统如实保留缺口，也没有自动命题。</p>
          <ul>
            {selection.gaps.map((gap) => (
              <li key={gap.section_id}>
                <div><b>{gap.section_title}</b><span>缺 {gap.missing_count} 题 · {gap.missing_score.toLocaleString("zh-CN")} 分</span></div>
                <p>{gap.reason}</p>
                {gap.suggestions.length > 0 && <small>{gap.suggestions.join("；")}</small>}
              </li>
            ))}
          </ul>
        </section>
      )}

      {selection.warnings.length > 0 && (
        <ul className="paper-selection-warnings" aria-label="候选题说明">
          {selection.warnings.map((warning) => <li key={warning}>{warning}</li>)}
        </ul>
      )}

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
            {item.options.length > 0 && (
              <ol className="paper-selection-options">
                {item.options.map((option) => <li key={option.key}><b>{option.key}</b><MathText text={option.text} /></li>)}
              </ol>
            )}
            <footer>
              <span>来源：{item.source_document}</span>
              <span>修订：{item.revision_count}</span>
              <span>验证：{item.verification_status}</span>
              <span>审核：{item.review_status}</span>
              <span>权限：{item.owner_scope === "current_owner_only" ? "仅当前教师" : "公共目录"}</span>
            </footer>
          </li>
        ))}
      </ol>

      {selection.similarity_exclusions.length > 0 && (
        <p className="paper-selection-similarity-note">已排除 {selection.similarity_exclusions.length} 道重复或高度相似题，未写入候选清单。</p>
      )}
    </section>
  );
}

export function PaperBlueprintWorkspace({ initialBrief, onBriefChange, onOpenAuthoring }: PaperBlueprintWorkspaceProps) {
  const [brief, setBrief] = useState(initialBrief);
  const [blueprint, setBlueprint] = useState<PaperBlueprintDraft | null>(null);
  const [selection, setSelection] = useState<PaperBlueprintSelectionDraft | null>(null);
  const [privateQuestions, setPrivateQuestions] = useState<PersonalQuestion[]>([]);
  const [selectedPrivateIds, setSelectedPrivateIds] = useState<string[]>([]);
  const [running, setRunning] = useState(false);
  const [selecting, setSelecting] = useState(false);
  const [privateLoading, setPrivateLoading] = useState(false);
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

  async function plan(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = brief.trim();
    if (trimmed.length < 5 || running) return;
    const controller = new AbortController();
    abortRef.current = controller;
    setRunning(true);
    setError("");
    setSelection(null);
    setSelectedPrivateIds([]);
    try {
      setBlueprint(await teacherWorkspace.planPaperBlueprint(trimmed, controller.signal));
      void loadPrivateQuestions();
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
    setBlueprint((current) => current ? { ...current, ...patch } : current);
  }

  function updateSection(index: number, patch: Partial<PaperBlueprintSection>) {
    setSelection(null);
    setBlueprint((current) => current
      ? { ...current, sections: current.sections.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item) }
      : current);
  }

  function togglePrivateQuestion(questionId: string) {
    setSelection(null);
    setSelectedPrivateIds((current) => current.includes(questionId)
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
      setSelection(await teacherWorkspace.selectPaperBlueprint(blueprint, selectedPrivateIds, controller.signal));
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === "AbortError") return;
      setError(errorMessage(cause, "蓝图确认或受控选题没有完成，请稍后重试。"));
    } finally {
      selectionAbortRef.current = null;
      setSelecting(false);
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
          <section className="paper-blueprint-authoring-note">
            <p><strong>另有明确命题需求？</strong><span>辅助命题是独立私有工作流，不会自动加入当前蓝图。</span></p>
            <button onClick={() => onOpenAuthoring(brief)} type="button">进入辅助命题 <ArrowRightIcon /></button>
          </section>
        </section>

        <section className="paper-blueprint-desk" aria-live="polite">
          {!blueprint ? (
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

                <section className="paper-private-picker">
                  <header><LockIcon /><div><strong>从你的私题中明确选择（可选）</strong><span>只读取当前教师的题目；未勾选的私题不会进入候选池。</span></div></header>
                  {privateLoading ? <p className="paper-private-picker-state">正在读取你的可用私题…</p> : privateQuestions.length === 0 ? <p className="paper-private-picker-state">当前没有可供明确选择的私题，可继续使用公共题库选题。</p> : (
                    <ul>{privateQuestions.map((question) => (
                      <li key={question.question_id}><label><input checked={selectedPrivateIds.includes(question.question_id)} onChange={() => togglePrivateQuestion(question.question_id)} type="checkbox" /><span><strong>{question.name}</strong><small>{QUESTION_TYPE_LABELS[question.question.question_type] ?? question.question.question_type} · 修订 {question.selected_revision}</small></span>{selectedPrivateIds.includes(question.question_id) && <CheckIcon />}</label></li>
                    ))}</ul>
                  )}
                </section>

                <footer>
                  <p><strong>确认后仍是可编辑草案。</strong><span>只通过范围、验证、审核、权限与相似度门禁选题；缺题会显示真实缺口，不会自动命题。</span></p>
                  {selecting ? <button className="is-selecting" onClick={() => selectionAbortRef.current?.abort()} type="button">取消受控选题</button> : <button disabled={!blueprintReady} onClick={confirmAndSelect} type="button">确认蓝图并受控选题</button>}
                </footer>
              </article>

              {selection && <PaperSelectionDraftView selection={selection} />}
            </>
          )}
        </section>
      </ResizableSplitPane>

      <WorkbenchNoticeDialog message={error} onDismiss={() => setError("")} open={Boolean(error)} returnFocusRef={submitRef} title="组卷操作没有完成" tone="error" />
    </main>
  );
}
