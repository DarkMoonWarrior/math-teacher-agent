"use client";

import { type FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { MathText } from "@/components/math-text";
import {
  type ConfirmedLessonBlueprint,
  type LessonBlueprintDraft,
  type LessonBlueprintType,
  type LessonDraftBlock,
  type LessonEditableDraft,
  type LessonSavedVersion,
  type LessonSourceDraft,
  type LessonSourceOptions,
  type LessonSourceQuestionCandidate,
  type LessonVersionHistoryItem,
  TeacherWorkspaceError,
} from "@/lib/teacher-workspace/contracts";
import { teacherWorkspace } from "@/lib/teacher-workspace/http-adapter";
import { EditableNumberInput } from "./editable-number-input";
import { TeacherPreferenceNotice } from "./teacher-preference-notice";
import { ArrowRightIcon, ArrowUpIcon, BookIcon, CloseIcon, LockIcon } from "./icons";
import { ResizableSplitPane } from "./resizable-split-pane";

type LessonBlueprintWorkspaceProps = {
  initialBrief: string;
  onBriefChange: (brief: string) => void;
};

type LessonBlueprintDraftViewProps = {
  draft: LessonBlueprintDraft;
  onChange: (draft: LessonBlueprintDraft) => void;
  onConfirm?: () => void;
  confirming?: boolean;
  sourceOptions?: LessonSourceOptions | null;
  sourceDraft?: LessonSourceDraft | null;
  selectedPublicQuestionIds?: string[];
  selectedPrivateQuestionIds?: string[];
  selectedPrivateResourceIds?: string[];
  onTogglePublicQuestion?: (questionId: string) => void;
  onTogglePrivateQuestion?: (questionId: string) => void;
  onTogglePrivateResource?: (resourceId: string) => void;
  onSelectSources?: () => void;
  lessonDraft?: LessonEditableDraft | null;
  onBuildLessonDraft?: () => void;
  onChangeLessonDraft?: (draft: LessonEditableDraft) => void;
  onToggleLessonBlockLock?: (block: LessonDraftBlock) => void;
  onRewriteLessonBlock?: (block: LessonDraftBlock, instruction: string) => void;
  rewritingBlock?: LessonDraftBlock | null;
  lessonLocallyEdited?: boolean;
};

const LESSON_DRAFT_BLOCK_LABELS: Record<LessonDraftBlock, string> = {
  objectives: "教学目标",
  key_points: "教学重点",
  difficulties: "教学难点",
  teaching_flow: "教学流程",
  questions: "例题与练习用途",
  assessments: "评价设计",
  homework: "作业",
  board_plan: "板书设计",
  teacher_notes: "教师备注",
};

const LESSON_DRAFT_BLOCKS = Object.keys(LESSON_DRAFT_BLOCK_LABELS) as LessonDraftBlock[];

const EXAMPLES = [
  "为高二椭圆第一课时准备一份 45 分钟新授课教案，班级基础中等",
  "设计一节函数单调性专题复习课，讲练结合，包含 3 道分层练习",
  "整理一节高三导数压轴题讲评课，重点突出构造函数方法，45 分钟",
];

const LESSON_TYPE_LABELS: Record<LessonBlueprintType, string> = {
  new_lesson: "新授课",
  review: "复习课",
  exercise: "习题或讲评课",
};

function lines(value: string): string[] {
  return value.split("\n").map((item) => item.trim()).filter(Boolean);
}

function errorMessage(cause: unknown): string {
  return cause instanceof TeacherWorkspaceError
    ? cause.message
    : "暂时无法继续教案工作流，请稍后重试。";
}

function SourceQuestionCard({
  candidate,
  checked,
  onToggle,
}: {
  candidate: LessonSourceQuestionCandidate;
  checked: boolean;
  onToggle: () => void;
}) {
  return (
    <label className={`lesson-source-card${checked ? " is-selected" : ""}`}>
      <input checked={checked} onChange={onToggle} type="checkbox" />
      <span>
        <strong>{candidate.name}</strong>
        <b>{candidate.source_kind === "public_question_bank" ? "公共题" : "我的私题"} · 难度 {candidate.difficulty}</b>
        <div className="lesson-question-math"><MathText text={candidate.stem_plain} /></div>
        {candidate.options.length > 0 && <ol>{candidate.options.map((option) => <li key={option.key}><b>{option.key}</b><MathText text={option.text} /></li>)}</ol>}
        <small>题面已通过来源与审核检查</small>
      </span>
    </label>
  );
}

export function LessonEditableDraftView({
  draft,
  onChange,
  onToggleLock,
  onRewrite,
  rewritingBlock = null,
  locallyEdited = false,
}: {
  draft: LessonEditableDraft;
  onChange?: (draft: LessonEditableDraft) => void;
  onToggleLock?: (block: LessonDraftBlock) => void;
  onRewrite?: (block: LessonDraftBlock, instruction: string) => void;
  rewritingBlock?: LessonDraftBlock | null;
  locallyEdited?: boolean;
}) {
  const [rewriteInstructions, setRewriteInstructions] = useState<Partial<Record<LessonDraftBlock, string>>>({});
  const locked = (block: LessonDraftBlock) => draft.locked_blocks.includes(block);
  const questionReferences = (questionIds: string[]) => questionIds.map((questionId) => {
    const questionIndex = draft.questions.findIndex((question) => question.question_id === questionId);
    return questionIndex >= 0 ? `第 ${questionIndex + 1} 题` : "已选题目";
  }).join("、");
  const updateStrings = (block: "key_points" | "difficulties" | "homework" | "board_plan" | "teacher_notes", value: string) => {
    onChange?.({ ...draft, [block]: lines(value) });
  };

  return (
    <section className="lesson-complete-draft" aria-label="完整教案草稿">
      <header>
        <div><p>LESSON DRAFT · REV {draft.draft_revision}</p><h2>{draft.title}</h2></div>
        <span>待教师复核 · 未保存</span>
      </header>

      <div className="lesson-integrity-grid" aria-label="完整性检查">
        <span>内容块完整</span><span>时间一致</span><span>目标—活动对应</span>
        <span>目标—评价对应</span><span>题目与解析完整</span><span>来源可追踪</span>
      </div>

      {onChange && (
        <section className="lesson-edit-toolbar" aria-label="教案逐块编辑与锁定">
          <header>
            <div><p>BLOCK EDITING</p><h3>逐块编辑、锁定与定向重写</h3></div>
            <span>服务器 REV {draft.draft_revision} · {locallyEdited ? "有本地未应用修改" : "已同步当前草稿"}</span>
          </header>
          <div>
            {LESSON_DRAFT_BLOCKS.map((block) => {
              const instruction = rewriteInstructions[block] ?? "";
              const isLocked = locked(block);
              return (
                <article className={isLocked ? "is-locked" : ""} key={block}>
                  <strong>{LESSON_DRAFT_BLOCK_LABELS[block]}</strong>
                  <input
                    aria-label={`${LESSON_DRAFT_BLOCK_LABELS[block]}定向重写要求`}
                    disabled={isLocked || rewritingBlock !== null}
                    onChange={(event) => setRewriteInstructions({ ...rewriteInstructions, [block]: event.target.value })}
                    placeholder="只说明这个内容块要怎样调整"
                    value={instruction}
                  />
                  <button disabled={rewritingBlock !== null} onClick={() => onToggleLock?.(block)} type="button">{isLocked ? "解锁" : "锁定"}</button>
                  <button disabled={isLocked || instruction.trim().length < 2 || rewritingBlock !== null} onClick={() => onRewrite?.(block, instruction.trim())} type="button">
                    {rewritingBlock === block ? "正在重写…" : "定向重写"}
                  </button>
                </article>
              );
            })}
          </div>
          <p>锁定块不会被定向重写；重写只替换目标块。题目区只调整课堂用途，题干、选项、答案和解析保持来源原样。</p>
        </section>
      )}

      <section className="lesson-draft-block">
        <h3>教学目标与可观察证据</h3>
        <ol>{draft.objectives.map((objective, index) => <li key={objective.objective_id}><b>{objective.objective_id}</b><div>{onChange ? <><textarea disabled={locked("objectives")} onChange={(event) => onChange({ ...draft, objectives: draft.objectives.map((item, itemIndex) => itemIndex === index ? { ...item, text: event.target.value } : item) })} rows={2} value={objective.text} /><textarea disabled={locked("objectives")} onChange={(event) => onChange({ ...draft, objectives: draft.objectives.map((item, itemIndex) => itemIndex === index ? { ...item, observable_evidence: event.target.value } : item) })} rows={2} value={objective.observable_evidence} /></> : <><strong>{objective.text}</strong><p>{objective.observable_evidence}</p></>}</div></li>)}</ol>
      </section>

      <section className="lesson-draft-two-column">
        <div><h3>教学重点</h3>{onChange ? <textarea disabled={locked("key_points")} onChange={(event) => updateStrings("key_points", event.target.value)} rows={5} value={draft.key_points.join("\n")} /> : <ul>{draft.key_points.map((item) => <li key={item}>{item}</li>)}</ul>}</div>
        <div><h3>教学难点</h3>{onChange ? <textarea disabled={locked("difficulties")} onChange={(event) => updateStrings("difficulties", event.target.value)} rows={5} value={draft.difficulties.join("\n")} /> : <ul>{draft.difficulties.map((item) => <li key={item}>{item}</li>)}</ul>}</div>
      </section>

      <section className="lesson-draft-block lesson-flow-block">
        <h3>教学流程</h3>
        <ol>{draft.teaching_flow.map((phase, index) => (
          <li key={phase.phase_id}>
            <header><b>{String(index + 1).padStart(2, "0")}</b>{onChange ? <input disabled={locked("teaching_flow")} onChange={(event) => onChange({ ...draft, teaching_flow: draft.teaching_flow.map((item, itemIndex) => itemIndex === index ? { ...item, title: event.target.value } : item) })} value={phase.title} /> : <strong>{phase.title}</strong>}{onChange ? <EditableNumberInput disabled={locked("teaching_flow")} min={1} onValueChange={(minutes) => onChange({ ...draft, teaching_flow: draft.teaching_flow.map((item, itemIndex) => itemIndex === index ? { ...item, minutes } : item) })} value={phase.minutes} /> : <span>{phase.minutes} 分钟</span>}</header>
            {onChange ? <>
              <label>阶段目的<textarea disabled={locked("teaching_flow")} onChange={(event) => onChange({ ...draft, teaching_flow: draft.teaching_flow.map((item, itemIndex) => itemIndex === index ? { ...item, purpose: event.target.value } : item) })} rows={2} value={phase.purpose} /></label>
              <label>教师活动<textarea disabled={locked("teaching_flow")} onChange={(event) => onChange({ ...draft, teaching_flow: draft.teaching_flow.map((item, itemIndex) => itemIndex === index ? { ...item, teacher_activity: event.target.value } : item) })} rows={3} value={phase.teacher_activity} /></label>
              <label>学生活动<textarea disabled={locked("teaching_flow")} onChange={(event) => onChange({ ...draft, teaching_flow: draft.teaching_flow.map((item, itemIndex) => itemIndex === index ? { ...item, student_activity: event.target.value } : item) })} rows={3} value={phase.student_activity} /></label>
              <label>评价证据<textarea disabled={locked("teaching_flow")} onChange={(event) => onChange({ ...draft, teaching_flow: draft.teaching_flow.map((item, itemIndex) => itemIndex === index ? { ...item, assessment: event.target.value } : item) })} rows={2} value={phase.assessment} /></label>
            </> : <><p><b>教师活动</b>{phase.teacher_activity}</p><p><b>学生活动</b>{phase.student_activity}</p><p><b>评价证据</b>{phase.assessment}</p></>}
            <small>对应目标：{phase.objective_ids.join("、")}{phase.question_ids.length ? ` · 题目：${questionReferences(phase.question_ids)}` : ""}{phase.resource_ids.length ? ` · 资料：${phase.resource_ids.join("、")}` : ""}</small>
          </li>
        ))}</ol>
      </section>

      <section className="lesson-draft-block lesson-question-block">
        <h3>例题与练习</h3>
        {draft.questions.length > 0 ? draft.questions.map((question, questionIndex) => (
          <article key={question.question_id}>
            <header><strong>第 {questionIndex + 1} 题</strong><span>{question.source_kind === "public_question_bank" ? "公共题" : "我的私题"}</span></header>
            <div className="lesson-question-math"><MathText text={question.stem_plain} /></div>
            {question.options.length > 0 && <ol>{question.options.map((option) => <li key={option.key}><b>{option.key}</b><MathText text={option.text} /></li>)}</ol>}
            <div><b>课堂用途</b>{onChange ? <textarea disabled={locked("questions")} onChange={(event) => onChange({ ...draft, questions: draft.questions.map((item) => item.question_id === question.question_id ? { ...item, usage: event.target.value } : item) })} rows={2} value={question.usage} /> : <p>{question.usage}</p>}</div>
            <div><b>解析</b><ol>{question.solution_steps.map((step, index) => <li key={`${question.question_id}-${index}`}><MathText text={step} /></li>)}</ol><strong>最终答案：<MathText text={question.final_answer} /></strong></div>
            <small>题面、答案与解析均已纳入教案完整性检查</small>
          </article>
        )) : <p className="lesson-blueprint-empty-state">本蓝图计划题量为 0，本教案没有引用题目。</p>}
      </section>

      <section className="lesson-draft-block">
        <h3>评价设计</h3>
        <div className="lesson-assessment-list">{draft.assessments.map((assessment, index) => <article key={assessment.assessment_id}><b>{assessment.assessment_id}</b>{onChange ? <><input disabled={locked("assessments")} onChange={(event) => onChange({ ...draft, assessments: draft.assessments.map((item, itemIndex) => itemIndex === index ? { ...item, title: event.target.value } : item) })} value={assessment.title} /><textarea disabled={locked("assessments")} onChange={(event) => onChange({ ...draft, assessments: draft.assessments.map((item, itemIndex) => itemIndex === index ? { ...item, method: event.target.value } : item) })} rows={3} value={assessment.method} /><textarea disabled={locked("assessments")} onChange={(event) => onChange({ ...draft, assessments: draft.assessments.map((item, itemIndex) => itemIndex === index ? { ...item, success_criteria: event.target.value } : item) })} rows={3} value={assessment.success_criteria} /></> : <><strong>{assessment.title}</strong><p>{assessment.method}</p><small>{assessment.success_criteria}</small></>}</article>)}</div>
      </section>

      <section className="lesson-draft-three-column">
        <div><h3>作业</h3>{onChange ? <textarea disabled={locked("homework")} onChange={(event) => updateStrings("homework", event.target.value)} rows={8} value={draft.homework.join("\n")} /> : <ol>{draft.homework.map((item) => <li key={item}>{item}</li>)}</ol>}</div>
        <div><h3>板书设计</h3>{onChange ? <textarea disabled={locked("board_plan")} onChange={(event) => updateStrings("board_plan", event.target.value)} rows={8} value={draft.board_plan.join("\n")} /> : <ol>{draft.board_plan.map((item) => <li key={item}>{item}</li>)}</ol>}</div>
        <div><h3>教师备注</h3>{onChange ? <textarea disabled={locked("teacher_notes")} onChange={(event) => updateStrings("teacher_notes", event.target.value)} rows={8} value={draft.teacher_notes.join("\n")} /> : <ol>{draft.teacher_notes.map((item) => <li key={item}>{item}</li>)}</ol>}</div>
      </section>

    </section>
  );
}

export function LessonBlueprintDraftView({
  draft,
  onChange,
  onConfirm,
  confirming = false,
  sourceOptions = null,
  sourceDraft = null,
  selectedPublicQuestionIds = [],
  selectedPrivateQuestionIds = [],
  selectedPrivateResourceIds = [],
  onTogglePublicQuestion,
  onTogglePrivateQuestion,
  onTogglePrivateResource,
  onSelectSources,
  lessonDraft = null,
  onBuildLessonDraft,
  onChangeLessonDraft,
  onToggleLessonBlockLock,
  onRewriteLessonBlock,
  rewritingBlock = null,
  lessonLocallyEdited = false,
}: LessonBlueprintDraftViewProps) {
  const phaseMinutes = useMemo(
    () => draft.phases.reduce((sum, phase) => sum + phase.minutes, 0),
    [draft.phases],
  );
  function updatePhase(index: number, patch: Partial<LessonBlueprintDraft["phases"][number]>) {
    onChange({
      ...draft,
      phases: draft.phases.map((phase, phaseIndex) => phaseIndex === index ? { ...phase, ...patch } : phase),
    });
  }

  function overridePreference(
    key: "default_grade" | "default_lesson_minutes",
    patch: Partial<LessonBlueprintDraft>,
  ) {
    const assumptionPrefix = key === "default_grade" ? "未明确年级" : "未明确有效课时";
    onChange({
      ...draft,
      ...patch,
      applied_preferences: draft.applied_preferences.filter((item) => item.key !== key),
      assumptions: draft.assumptions.filter(
        (item) => !item.startsWith(assumptionPrefix) || !item.includes("教师偏好"),
      ),
    });
  }

  return (
    <article className="lesson-blueprint-sheet">
      <header>
        <div>
          <p>LESSON BLUEPRINT · {sourceOptions ? "已确认蓝图" : "未保存草案"}</p>
          <h2>{draft.title}</h2>
        </div>
        <ul aria-label="蓝图状态">
          <li>可编辑</li>
          <li>{sourceOptions ? "已确认" : "未确认"}</li>
          <li>未保存</li>
        </ul>
      </header>

      <TeacherPreferenceNotice preferences={draft.applied_preferences} />

      {draft.assumptions.length > 0 && (
        <section className="lesson-blueprint-assumptions">
          <strong>需要教师核对的默认假设</strong>
          <ul>{draft.assumptions.map((assumption) => <li key={assumption}>{assumption}</li>)}</ul>
        </section>
      )}

      <section className="lesson-blueprint-fields" aria-label="教案蓝图基本信息">
        <label className="wide">教案标题
          <input value={draft.title} onChange={(event) => onChange({ ...draft, title: event.target.value })} />
        </label>
        <label>年级范围
          <input value={draft.grade_scope} onChange={(event) => overridePreference("default_grade", { grade_scope: event.target.value })} />
        </label>
        <label>课型
          <select value={draft.lesson_type} onChange={(event) => onChange({ ...draft, lesson_type: event.target.value as LessonBlueprintType })}>
            {Object.entries(LESSON_TYPE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <label>课型名称
          <input value={draft.lesson_format} onChange={(event) => onChange({ ...draft, lesson_format: event.target.value })} />
        </label>
        <label>课时（分钟）
          <EditableNumberInput min={20} max={120} value={draft.duration_minutes} onValueChange={(duration_minutes) => overridePreference("default_lesson_minutes", { duration_minutes })} />
        </label>
        <label>计划题量
          <EditableNumberInput min={0} max={8} value={draft.question_count} onValueChange={(question_count) => onChange({ ...draft, question_count })} />
        </label>
        <label className="wide">学情
          <textarea rows={3} value={draft.student_profile} onChange={(event) => onChange({ ...draft, student_profile: event.target.value })} />
        </label>
        <label className="wide">教学侧重
          <textarea rows={3} value={draft.focus} onChange={(event) => onChange({ ...draft, focus: event.target.value })} />
        </label>
      </section>

      <section className="lesson-blueprint-curriculum">
        <header><div><strong>教材节点</strong><span>只读取封存的人教 A 版课程基线；候选状态如实显示。</span></div></header>
        {draft.curriculum_candidates.length > 0 ? (
          <label>当前节点
            <select
              value={draft.selected_curriculum_node_id ?? ""}
              onChange={(event) => onChange({ ...draft, selected_curriculum_node_id: event.target.value || null })}
            >
              <option value="">请选择教材节点</option>
              {draft.curriculum_candidates.map((candidate) => (
                <option key={candidate.node_id} value={candidate.node_id}>{candidate.volume} · {candidate.chapter ?? candidate.section ?? candidate.name} · {candidate.name}</option>
              ))}
            </select>
          </label>
        ) : <p className="lesson-blueprint-empty-state">尚未匹配到明确教材节点，生成教案正文前必须由教师补充。</p>}
      </section>

      <section className="lesson-blueprint-requirements">
        <header><strong>目标与重难点</strong><span>每行一项，可直接改写。</span></header>
        <div>
          <label>教学目标<textarea rows={5} value={draft.objectives.join("\n")} onChange={(event) => onChange({ ...draft, objectives: lines(event.target.value) })} /></label>
          <label>教学重点<textarea rows={5} value={draft.key_points.join("\n")} onChange={(event) => onChange({ ...draft, key_points: lines(event.target.value) })} /></label>
          <label>教学难点<textarea rows={5} value={draft.difficulties.join("\n")} onChange={(event) => onChange({ ...draft, difficulties: lines(event.target.value) })} /></label>
        </div>
      </section>

      <section className="lesson-blueprint-phases">
        <header>
          <div><strong>课堂阶段</strong><span>阶段分钟数应与课时一致。</span></div>
          <b data-valid={phaseMinutes === draft.duration_minutes}>{phaseMinutes} / {draft.duration_minutes} 分钟</b>
        </header>
        <ol>
          {draft.phases.map((phase, index) => (
            <li key={phase.phase_id}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <label>阶段名称<input value={phase.title} onChange={(event) => updatePhase(index, { title: event.target.value })} /></label>
              <label>分钟<EditableNumberInput min={1} max={120} value={phase.minutes} onValueChange={(minutes) => updatePhase(index, { minutes })} /></label>
              <label className="wide">阶段目的<textarea rows={2} value={phase.purpose} onChange={(event) => updatePhase(index, { purpose: event.target.value })} /></label>
            </li>
          ))}
        </ol>
      </section>

      <section className="lesson-blueprint-trust">
        <LockIcon />
        <div>
          <strong>{sourceOptions ? "蓝图已确认，来源仍由你控制" : "当前只完成蓝图规划"}</strong>
          <p>{sourceOptions ? "候选只供当前教师勾选；未勾选的私人内容不会进入 Agent 上下文，当前仍未生成正文或写入数据库。" : "尚未选题、未读取私人资料、未生成教案正文，也没有写入数据库。后续来源选择必须由当前教师明确确认。"}</p>
        </div>
      </section>

      {sourceOptions && (
        <section className="lesson-source-selection" aria-label="受控教案来源选择">
          <header>
            <div><strong>明确选择课堂来源</strong><span>{sourceOptions.trust_statement}</span></div>
            <b>蓝图已确认 · 未保存</b>
          </header>

          <div className="lesson-source-group">
            <h3>受控公共题 <span>{sourceOptions.public_questions.length} 道可选</span></h3>
            {sourceOptions.public_questions.length > 0 ? sourceOptions.public_questions.map((candidate) => (
              <SourceQuestionCard
                candidate={candidate}
                checked={selectedPublicQuestionIds.includes(candidate.question_id)}
                key={candidate.question_id}
                onToggle={() => onTogglePublicQuestion?.(candidate.question_id)}
              />
            )) : <p className="lesson-blueprint-empty-state">当前教材范围内没有通过全部公共门禁的题目。</p>}
          </div>

          <div className="lesson-source-group">
            <h3>我的私题 <span>只读取你明确勾选的题目</span></h3>
            {sourceOptions.private_questions.length > 0 ? sourceOptions.private_questions.map((candidate) => (
              <SourceQuestionCard
                candidate={candidate}
                checked={selectedPrivateQuestionIds.includes(candidate.question_id)}
                key={candidate.question_id}
                onToggle={() => onTogglePrivateQuestion?.(candidate.question_id)}
              />
            )) : <p className="lesson-blueprint-empty-state">当前没有符合本蓝图且通过门禁的私题。</p>}
          </div>

          <div className="lesson-source-group">
            <h3>我的私人资料 <span>未勾选资料不会进入 Agent 上下文</span></h3>
            {sourceOptions.private_resources.length > 0 ? sourceOptions.private_resources.map((resource) => (
              <label className={`lesson-source-card compact${selectedPrivateResourceIds.includes(resource.library_item_id) ? " is-selected" : ""}`} key={resource.library_item_id}>
                <input checked={selectedPrivateResourceIds.includes(resource.library_item_id)} onChange={() => onTogglePrivateResource?.(resource.library_item_id)} type="checkbox" />
                <span><strong>{resource.title}</strong><b>{resource.file_kind.toUpperCase()} · version {resource.source_version}</b><small>{resource.rights_basis} · 已确认文本 {resource.corrected_char_count} 字</small></span>
              </label>
            )) : <p className="lesson-blueprint-empty-state">当前没有完成文本校对的私人资料。</p>}
          </div>

          {sourceDraft && (
            <div className={`lesson-source-result${sourceDraft.selection_complete ? " is-complete" : " is-gap"}`}>
              <strong>{sourceDraft.selection_complete ? "受控来源已完整确认" : "来源草案仍有真实缺口"}</strong>
              <p>已选 {sourceDraft.questions.length} 道题、{sourceDraft.private_resources.length} 份私人资料；没有自动编题或保存。</p>
              {sourceDraft.gaps.map((gap) => <p key={gap.source_kind}>{gap.reason}</p>)}
            </div>
          )}

          <button className="lesson-source-confirm" disabled={confirming} onClick={onSelectSources} type="button">
            {confirming ? "正在复核所选来源…" : "确认所选来源"}
          </button>
          {sourceDraft?.selection_complete && !lessonDraft && (
            <button className="lesson-draft-build" disabled={confirming} onClick={onBuildLessonDraft} type="button">
              {confirming ? "正在生成完整教案…" : "生成完整教案草稿"}
            </button>
          )}
        </section>
      )}

      {lessonDraft && <LessonEditableDraftView
        draft={lessonDraft}
        locallyEdited={lessonLocallyEdited}
        onChange={onChangeLessonDraft}
        onRewrite={onRewriteLessonBlock}
        onToggleLock={onToggleLessonBlockLock}
        rewritingBlock={rewritingBlock}
      />}

      <footer>
        <p><strong>本地可编辑草案</strong><span>{lessonDraft ? "完整正文仍待教师复核；只有页面明确确认才会追加私有版本，当前不开放导出。" : sourceOptions ? "确认完整来源后可生成教案正文；生成结果仍不会自动保存。" : "确认蓝图后才能查看受控来源；当前页面不会假装已经保存。"}</span></p>
        {!sourceOptions && onConfirm && <button className="lesson-source-confirm" disabled={confirming || phaseMinutes !== draft.duration_minutes || !draft.selected_curriculum_node_id} onClick={onConfirm} type="button">{confirming ? "正在确认蓝图…" : "确认蓝图并选择来源"}</button>}
      </footer>
    </article>
  );
}

export function LessonBlueprintWorkspace({ initialBrief, onBriefChange }: LessonBlueprintWorkspaceProps) {
  const [brief, setBrief] = useState(initialBrief);
  const [draft, setDraft] = useState<LessonBlueprintDraft | null>(null);
  const [running, setRunning] = useState(false);
  const [sourceRunning, setSourceRunning] = useState(false);
  const [sourceOptions, setSourceOptions] = useState<LessonSourceOptions | null>(null);
  const [sourceDraft, setSourceDraft] = useState<LessonSourceDraft | null>(null);
  const [lessonDraft, setLessonDraft] = useState<LessonEditableDraft | null>(null);
  const [rewritingBlock, setRewritingBlock] = useState<LessonDraftBlock | null>(null);
  const [lessonLocallyEdited, setLessonLocallyEdited] = useState(false);
  const [lessonPlanId, setLessonPlanId] = useState<string | null>(null);
  const [savedVersion, setSavedVersion] = useState<LessonSavedVersion | null>(null);
  const [historyItems, setHistoryItems] = useState<LessonVersionHistoryItem[]>([]);
  const [historyState, setHistoryState] = useState<"active" | "trashed">("active");
  const [historyLoading, setHistoryLoading] = useState(false);
  const [saveRunning, setSaveRunning] = useState(false);
  const [confirmingSave, setConfirmingSave] = useState(false);
  const [exportRunning, setExportRunning] = useState<"docx" | "pdf" | null>(null);
  const [selectedPublicQuestionIds, setSelectedPublicQuestionIds] = useState<string[]>([]);
  const [selectedPrivateQuestionIds, setSelectedPrivateQuestionIds] = useState<string[]>([]);
  const [selectedPrivateResourceIds, setSelectedPrivateResourceIds] = useState<string[]>([]);
  const [error, setError] = useState("");
  const abortRef = useRef<AbortController | null>(null);

  async function refreshHistory(state = historyState) {
    setHistoryLoading(true);
    try {
      const result = await teacherWorkspace.listLessonVersionHistory(state);
      setHistoryItems(result.items);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setHistoryLoading(false);
    }
  }

  useEffect(() => {
    void refreshHistory(historyState);
    // historyState is the only trigger; the adapter is stable.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [historyState]);

  function updateBrief(value: string) {
    setBrief(value);
    onBriefChange(value);
  }

  async function plan(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalized = brief.trim();
    if (normalized.length < 5 || running) return;
    const controller = new AbortController();
    abortRef.current = controller;
    setRunning(true);
    setError("");
    try {
      const nextDraft = await teacherWorkspace.planLessonBlueprint(normalized, controller.signal);
      setDraft(nextDraft);
      setSourceOptions(null);
      setSourceDraft(null);
      setLessonDraft(null);
      setLessonLocallyEdited(false);
      setLessonPlanId(null);
      setSavedVersion(null);
      setRewritingBlock(null);
      setSelectedPublicQuestionIds([]);
      setSelectedPrivateQuestionIds([]);
      setSelectedPrivateResourceIds([]);
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === "AbortError") return;
      setError(errorMessage(cause));
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
      setRunning(false);
    }
  }

  function toggle(values: string[], value: string, update: (next: string[]) => void) {
    update(values.includes(value) ? values.filter((item) => item !== value) : [...values, value]);
    setSourceDraft(null);
    setLessonDraft(null);
    setLessonLocallyEdited(false);
    setLessonPlanId(null);
    setSavedVersion(null);
  }

  async function confirmBlueprint() {
    if (!draft || sourceRunning) return;
    setSourceRunning(true);
    setError("");
    try {
      const nextOptions = await teacherWorkspace.listLessonSourceOptions(draft);
      setSourceOptions(nextOptions);
      setDraft({ ...draft, selected_curriculum_node_id: nextOptions.blueprint.selected_curriculum_node_id });
      setSourceDraft(null);
      setLessonDraft(null);
      setLessonLocallyEdited(false);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setSourceRunning(false);
    }
  }

  async function selectSources() {
    if (!sourceOptions || sourceRunning) return;
    setSourceRunning(true);
    setError("");
    setLessonDraft(null);
    setLessonLocallyEdited(false);
    try {
      const nextDraft = await teacherWorkspace.selectLessonSources(
        sourceOptions.blueprint as ConfirmedLessonBlueprint,
        selectedPublicQuestionIds,
        selectedPrivateQuestionIds,
        selectedPrivateResourceIds,
      );
      setSourceDraft(nextDraft);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setSourceRunning(false);
    }
  }

  async function buildLessonDraft() {
    if (!sourceDraft?.selection_complete || sourceRunning) return;
    setSourceRunning(true);
    setError("");
    try {
      setLessonDraft(await teacherWorkspace.buildLessonDraft(sourceDraft));
      setLessonLocallyEdited(false);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setSourceRunning(false);
    }
  }

  function changeLessonDraft(nextDraft: LessonEditableDraft) {
    setLessonDraft(nextDraft);
    setLessonLocallyEdited(true);
  }

  function toggleLessonBlockLock(block: LessonDraftBlock) {
    if (!lessonDraft || rewritingBlock) return;
    changeLessonDraft({
      ...lessonDraft,
      locked_blocks: lessonDraft.locked_blocks.includes(block)
        ? lessonDraft.locked_blocks.filter((item) => item !== block)
        : [...lessonDraft.locked_blocks, block],
    });
  }

  async function rewriteLessonBlock(block: LessonDraftBlock, instruction: string) {
    if (!lessonDraft || rewritingBlock || lessonDraft.locked_blocks.includes(block)) return;
    setRewritingBlock(block);
    setError("");
    try {
      setLessonDraft(await teacherWorkspace.rewriteLessonDraftBlock(lessonDraft, block, instruction));
      setLessonLocallyEdited(false);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setRewritingBlock(null);
    }
  }

  async function saveLesson() {
    if (!lessonDraft || saveRunning) return;
    setSaveRunning(true);
    setError("");
    try {
      const saved = await teacherWorkspace.saveLessonVersion(lessonDraft, lessonPlanId);
      setSavedVersion(saved);
      setLessonPlanId(saved.lesson_plan_id);
      setLessonDraft(saved.draft);
      setLessonLocallyEdited(false);
      setConfirmingSave(false);
      await refreshHistory("active");
    } catch (cause) {
      setError(errorMessage(cause));
      setConfirmingSave(false);
    } finally {
      setSaveRunning(false);
    }
  }

  async function openHistory(item: LessonVersionHistoryItem) {
    setError("");
    try {
      const saved = await teacherWorkspace.getLessonVersion(item.lesson_plan_id);
      const blueprint = saved.draft.source_draft.blueprint;
      setDraft({ ...blueprint, status: "lesson_blueprint_draft", confirmed: false });
      setSourceOptions(null);
      setSourceDraft(saved.draft.source_draft);
      setLessonDraft(saved.draft);
      setLessonPlanId(saved.lesson_plan_id);
      setSavedVersion(saved);
      setLessonLocallyEdited(false);
    } catch (cause) {
      setError(errorMessage(cause));
    }
  }

  async function changeHistoryLifecycle(item: LessonVersionHistoryItem) {
    try {
      await teacherWorkspace.changeLessonVersionLifecycle(
        item.lesson_plan_id,
        historyState === "active" ? "trash" : "restore",
      );
      if (item.lesson_plan_id === lessonPlanId && historyState === "active") {
        setLessonPlanId(null);
        setSavedVersion(null);
      }
      await refreshHistory(historyState);
    } catch (cause) {
      setError(errorMessage(cause));
    }
  }

  async function exportLesson(format: "docx" | "pdf") {
    if (!savedVersion || exportRunning) return;
    setExportRunning(format);
    setError("");
    try {
      const artifact = await teacherWorkspace.exportLessonVersion(
        savedVersion.lesson_plan_id,
        savedVersion.version,
        format,
      );
      const url = URL.createObjectURL(artifact.blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = artifact.filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setExportRunning(null);
    }
  }

  return (
    <main className="lesson-blueprint-workspace">
      <ResizableSplitPane ariaLabel="调整教案要求与蓝图区域宽度" className="lesson-blueprint-split" defaultPrimaryPercent={40} disabled={running} state={error ? "error" : running ? "loading" : draft ? "success" : "default"}>
        <section className="lesson-blueprint-intent">
          <div>
            <h1>先把一节课，<br />整理成可编辑蓝图。</h1>
            <p className="intro-copy">交代课题、年级、学情和课时。系统先形成目标、重难点与课堂节奏；经你确认后再展示可明确勾选的受控来源，不会自动读取私有正文或保存。</p>
          </div>
          <form onSubmit={plan}>
            <label htmlFor="lesson-blueprint-brief">描述教案需求</label>
            <div className={`composer-surface${running ? " is-running" : ""}${error ? " is-error" : ""}`}>
              <textarea id="lesson-blueprint-brief" onChange={(event) => updateBrief(event.target.value)} placeholder="例如：为高二椭圆第一课时准备一份 45 分钟新授课教案" readOnly={running} rows={6} value={brief} />
              <div className="composer-actions">
                <span className={error ? "form-error" : "form-help"}>{error || "先整理为未保存蓝图，再由你逐项核对。"}</span>
                {running ? (
                  <button className="cancel-button" onClick={() => abortRef.current?.abort()} type="button"><CloseIcon /><span>取消</span></button>
                ) : (
                  <button className="run-button" disabled={brief.trim().length < 5} type="submit"><span>整理教案蓝图</span><ArrowUpIcon /></button>
                )}
              </div>
            </div>
          </form>
          <div className="lesson-blueprint-examples" aria-label="教案蓝图示例">
            {EXAMPLES.map((example, index) => (
              <button disabled={running} key={example} onClick={() => updateBrief(example)} type="button">
                <span>{String(index + 1).padStart(2, "0")}</span><p>{example}</p><ArrowRightIcon />
              </button>
            ))}
          </div>
          <section className="lesson-blueprint-boundary">
            <LockIcon /><p><strong>当前开发边界</strong><span>保存只由当前教师明确确认；历史仅本人可见且采用不可变版本。仍不自动读取未选择的私有内容，也不伪造可信结论。</span></p>
          </section>
          <section className="lesson-version-history" aria-label="我的教案历史">
            <header>
              <div><strong>我的教案历史</strong><span>仅当前教师可见</span></div>
              <nav aria-label="教案历史状态">
                <button className={historyState === "active" ? "is-active" : ""} onClick={() => setHistoryState("active")} type="button">已保存</button>
                <button className={historyState === "trashed" ? "is-active" : ""} onClick={() => setHistoryState("trashed")} type="button">回收站</button>
              </nav>
            </header>
            {historyLoading ? <p>正在读取历史…</p> : historyItems.length === 0 ? <p>当前没有{historyState === "active" ? "已保存" : "已删除"}教案。</p> : (
              <ol>{historyItems.map((item) => <li key={item.lesson_plan_id}>
                <button onClick={() => void openHistory(item)} type="button"><strong>{item.title}</strong><span>v{item.version} · {item.duration_minutes} 分钟 · {new Date(item.updated_at).toLocaleString("zh-CN")}</span></button>
                <button onClick={() => void changeHistoryLifecycle(item)} type="button">{historyState === "active" ? "删除" : "恢复"}</button>
              </li>)}</ol>
            )}
          </section>
        </section>

        <section className="lesson-blueprint-desk" aria-live="polite">
          {running ? (
            <div className="lesson-blueprint-empty lesson-blueprint-loading"><span className="orbit-loader" aria-hidden="true"><i /><i /><i /></span><p>LESSON BLUEPRINT / PLANNING</p><h2>正在整理课堂条件与教学骨架。</h2><span>不会在后台保存，也不会自动读取你的私人资料。</span></div>
          ) : draft ? (
            <>
            <LessonBlueprintDraftView
              confirming={sourceRunning || rewritingBlock !== null}
              draft={draft}
              lessonDraft={lessonDraft}
              lessonLocallyEdited={lessonLocallyEdited}
              onBuildLessonDraft={buildLessonDraft}
              onChangeLessonDraft={changeLessonDraft}
              onChange={(nextDraft) => { setDraft(nextDraft); setSourceOptions(null); setSourceDraft(null); setLessonDraft(null); setLessonLocallyEdited(false); }}
              onConfirm={lessonDraft ? undefined : confirmBlueprint}
              onSelectSources={selectSources}
              onRewriteLessonBlock={rewriteLessonBlock}
              onToggleLessonBlockLock={toggleLessonBlockLock}
              onTogglePrivateQuestion={(questionId) => toggle(selectedPrivateQuestionIds, questionId, setSelectedPrivateQuestionIds)}
              onTogglePrivateResource={(resourceId) => toggle(selectedPrivateResourceIds, resourceId, setSelectedPrivateResourceIds)}
              onTogglePublicQuestion={(questionId) => toggle(selectedPublicQuestionIds, questionId, setSelectedPublicQuestionIds)}
              selectedPrivateQuestionIds={selectedPrivateQuestionIds}
              selectedPrivateResourceIds={selectedPrivateResourceIds}
              selectedPublicQuestionIds={selectedPublicQuestionIds}
              sourceDraft={sourceDraft}
              sourceOptions={sourceOptions}
              rewritingBlock={rewritingBlock}
            />
            {lessonDraft && <section className="lesson-version-actions" aria-label="教案版本保存">
              <div>
                <p>VERSION CONTROL</p>
                <h2>{lessonPlanId ? `编辑后保存为 v${(savedVersion?.version ?? 0) + 1}` : "建立第一个教案版本"}</h2>
                <span>{savedVersion ? `当前打开 v${savedVersion.version}；再次保存会追加新版本，不覆盖旧版本。` : "保存后只进入当前教师的私有历史，内容仍标记为待教师复核。"}</span>
              </div>
              <div className="lesson-version-action-buttons">
                {savedVersion?.available_exports.map((option) => (
                  <button disabled={exportRunning !== null} key={option.format} onClick={() => void exportLesson(option.format)} type="button">
                    {exportRunning === option.format ? "正在导出…" : option.label}
                  </button>
                ))}
                <button disabled={saveRunning || rewritingBlock !== null} onClick={() => setConfirmingSave(true)} type="button">{saveRunning ? "正在保存…" : lessonPlanId ? "另存新版本" : "保存教案"}</button>
              </div>
            </section>}
            </>
          ) : (
            <div className="lesson-blueprint-empty"><BookIcon /><p>LESSON BLUEPRINT / 规划</p><h2>这里会出现一份可修改的教案蓝图。</h2><span>当前没有教案正文、题目或保存记录。</span></div>
          )}
        </section>
      </ResizableSplitPane>
      {confirmingSave && <div className="lesson-save-dialog-backdrop" role="presentation">
        <section aria-labelledby="lesson-save-dialog-title" className="lesson-save-dialog" role="dialog" aria-modal="true">
          <h2 id="lesson-save-dialog-title">确认保存这份教案吗？</h2>
          <p>系统会重新核验课程、题目与私人资料来源，并建立仅你可见的不可变版本。AI 内容仍是“待教师复核”，不会因保存自动升级为已验证。</p>
          <div><button disabled={saveRunning} onClick={() => setConfirmingSave(false)} type="button">取消</button><button disabled={saveRunning} onClick={() => void saveLesson()} type="button">{saveRunning ? "正在核验并保存…" : "确认保存"}</button></div>
        </section>
      </div>}
    </main>
  );
}
