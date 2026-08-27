"use client";

import { type FormEvent, useMemo, useRef, useState } from "react";
import {
  type PaperBlueprintDraft,
  type PaperBlueprintDifficulty,
  TeacherWorkspaceError,
} from "@/lib/teacher-workspace/contracts";
import { teacherWorkspace } from "@/lib/teacher-workspace/http-adapter";
import { ArrowRightIcon, ArrowUpIcon, CloseIcon, PaperIcon } from "./icons";
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

function numberValue(value: string, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function PaperBlueprintWorkspace({ initialBrief, onBriefChange, onOpenAuthoring }: PaperBlueprintWorkspaceProps) {
  const [brief, setBrief] = useState(initialBrief);
  const [blueprint, setBlueprint] = useState<PaperBlueprintDraft | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const abortRef = useRef<AbortController | null>(null);
  const submitRef = useRef<HTMLButtonElement | null>(null);
  const totalSectionScore = useMemo(
    () => blueprint?.sections.reduce((sum, section) => sum + section.target_score, 0) ?? 0,
    [blueprint],
  );
  const totalQuestions = useMemo(
    () => blueprint?.sections.reduce((sum, section) => sum + section.question_count, 0) ?? 0,
    [blueprint],
  );

  function updateBrief(value: string) {
    setBrief(value);
    onBriefChange(value);
  }

  async function plan(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = brief.trim();
    if (trimmed.length < 5 || running) return;
    const controller = new AbortController();
    abortRef.current = controller;
    setRunning(true);
    setError("");
    try {
      setBlueprint(await teacherWorkspace.planPaperBlueprint(trimmed, controller.signal));
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === "AbortError") return;
      setError(cause instanceof TeacherWorkspaceError ? cause.message : "组卷蓝图没有整理完成，请稍后重试。");
    } finally {
      abortRef.current = null;
      setRunning(false);
    }
  }

  function updateBlueprint(patch: Partial<PaperBlueprintDraft>) {
    setBlueprint((current) => current ? { ...current, ...patch } : current);
  }

  return (
    <main className="paper-blueprint-workspace">
      <section className="paper-blueprint-intent">
        <p className="mode-status"><i className="is-ready" aria-hidden="true" />Paper Agent · 蓝图规划已接入</p>
        <h1>先把组卷要求，<br />整理成可编辑蓝图。</h1>
        <p className="intro-copy">这一阶段只整理范围、结构、题量与配分。不会查题、生成题目、保存试卷或改变任何私题权限。</p>
        <form onSubmit={plan}>
          <label htmlFor="paper-blueprint-brief">描述组卷需求</label>
          <div className={`composer-surface${running ? " is-running" : ""}`}>
            <textarea
              id="paper-blueprint-brief"
              onChange={(event) => updateBrief(event.target.value)}
              placeholder="例如：组一份高二期中卷，120 分钟，总分 150 分，覆盖函数、导数与圆锥曲线"
              readOnly={running}
              rows={5}
              value={brief}
            />
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
            <button key={example} onClick={() => updateBrief(example)} type="button">
              <span>{String(index + 1).padStart(2, "0")}</span><p>{example}</p><ArrowRightIcon />
            </button>
          ))}
        </div>
        <section className="paper-blueprint-authoring-note">
          <p><strong>另有明确命题需求？</strong><span>辅助命题是独立私有工作流，不会自动保存或加入当前蓝图。</span></p>
          <button onClick={() => onOpenAuthoring(brief)} type="button">进入辅助命题 <ArrowRightIcon /></button>
        </section>
      </section>

      <section className="paper-blueprint-desk" aria-live="polite">
        {!blueprint ? (
          <div className="paper-blueprint-empty">
            <PaperIcon />
            <p>PaperBlueprint / 第一切片</p>
            <h2>这里会出现一份可修改的组卷结构。</h2>
            <span>当前没有题目，也没有产生任何保存或权限变更。</span>
          </div>
        ) : (
          <article className="paper-blueprint-sheet">
            <header>
              <div><p>PAPER BLUEPRINT · DRAFT</p><h2>可编辑组卷蓝图</h2></div>
              <ul aria-label="蓝图状态"><li>未确认</li><li>未保存</li><li>未选题</li></ul>
            </header>

            {blueprint.assumptions.length > 0 && (
              <section className="paper-blueprint-assumptions">
                <strong>需要你核对的默认假设</strong>
                <ul>{blueprint.assumptions.map((item) => <li key={item}>{item}</li>)}</ul>
              </section>
            )}

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
                    <label>分区名称<input value={section.title} onChange={(event) => setBlueprint((current) => current ? { ...current, sections: current.sections.map((item, itemIndex) => itemIndex === index ? { ...item, title: event.target.value } : item) } : current)} /></label>
                    <label>题量<input min={0} max={30} type="number" value={section.question_count} onChange={(event) => setBlueprint((current) => current ? { ...current, sections: current.sections.map((item, itemIndex) => itemIndex === index ? { ...item, question_count: numberValue(event.target.value, item.question_count) } : item) } : current)} /></label>
                    <label>分值<input min={0} max={300} step={0.5} type="number" value={section.target_score} onChange={(event) => setBlueprint((current) => current ? { ...current, sections: current.sections.map((item, itemIndex) => itemIndex === index ? { ...item, target_score: numberValue(event.target.value, item.target_score) } : item) } : current)} /></label>
                  </div>
                ))}
              </div>
            </section>

            <footer>
              <p><strong>本切片到此为止。</strong><span>后续只有在你确认蓝图后，才会进入受控选题；题目不足时也不会自动命题。</span></p>
              <button disabled type="button">确认蓝图并选题（下一切片）</button>
            </footer>
          </article>
        )}
      </section>

      <WorkbenchNoticeDialog
        message={error}
        onDismiss={() => setError("")}
        open={Boolean(error)}
        returnFocusRef={submitRef}
        title="蓝图没有整理完成"
        tone="error"
      />
    </main>
  );
}
