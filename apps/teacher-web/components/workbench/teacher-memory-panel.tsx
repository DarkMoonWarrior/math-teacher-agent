"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  type TeacherMemoryCommand,
  type TeacherMemoryProfile,
  type TeacherPreferenceFeedback,
  type TeacherPreferenceProposal,
  type TeacherPreferenceKey,
  type TeacherPreferenceValue,
  TeacherWorkspaceError,
} from "@/lib/teacher-workspace/contracts";
import { teacherWorkspace } from "@/lib/teacher-workspace/http-adapter";
import { CloseIcon } from "./icons";


type TeacherMemoryPanelProps = {
  open: boolean;
  onClose: () => void;
};

const QUESTION_TYPES = [
  ["single_choice", "单项选择题"],
  ["multiple_choice", "多项选择题"],
  ["fill_blank", "填空题"],
  ["open_response", "解答题"],
] as const;

const VALUE_LABELS: Record<string, string> = {
  concise: "简洁",
  detailed: "详细",
  fill_blank: "填空题",
  multiple_choice: "多项选择题",
  open_response: "解答题",
  single_choice: "单项选择题",
  standard: "标准",
};

function proposalValue(proposal: TeacherPreferenceProposal) {
  if (Array.isArray(proposal.value)) {
    return proposal.value.map((item) => VALUE_LABELS[item] ?? item).join("、");
  }
  if (proposal.key === "default_difficulty") return `${proposal.value} / 5`;
  if (proposal.key === "default_lesson_minutes") return `${proposal.value} 分钟`;
  return VALUE_LABELS[String(proposal.value)] ?? String(proposal.value);
}

function preferenceDisplayValue(key: TeacherPreferenceKey, value: TeacherPreferenceValue) {
  if (Array.isArray(value)) return value.map((item) => VALUE_LABELS[item] ?? item).join("、");
  if (key === "default_difficulty") return `${value} / 5`;
  if (key === "default_lesson_minutes") return `${value} 分钟`;
  return VALUE_LABELS[String(value)] ?? String(value);
}

export function normalizeProposalCorrection(
  key: TeacherPreferenceKey,
  value: string,
): TeacherPreferenceValue {
  if (key === "default_difficulty" || key === "default_lesson_minutes") {
    return Number(value);
  }
  return value;
}

type TeacherMemoryProposalsProps = {
  disabled: boolean;
  items: TeacherPreferenceProposal[];
  onAccept: (proposal: TeacherPreferenceProposal) => void;
  onCorrect: (proposal: TeacherPreferenceProposal, value: TeacherPreferenceValue) => void;
  onReject: (proposal: TeacherPreferenceProposal) => void;
};

export function TeacherMemoryProposals({
  disabled,
  items,
  onAccept,
  onCorrect,
  onReject,
}: TeacherMemoryProposalsProps) {
  const [corrections, setCorrections] = useState<Record<string, string>>({});
  if (!items.length) return null;
  return (
    <section className="teacher-memory-proposals" aria-labelledby="teacher-memory-proposals-title">
      <header>
        <div>
          <span>可解释推断</span>
          <h3 id="teacher-memory-proposals-title">偏好提议</h3>
        </div>
        <strong>{items.length}</strong>
      </header>
      <p>仅展示重复行为形成的结构化候选；尚未写入偏好，也不会用于任务默认值。</p>
      <ol>
        {items.map((proposal) => (
          <li key={proposal.proposal_id}>
            <div><strong>{proposal.label}</strong><b>{proposalValue(proposal)}</b></div>
            <small>{proposal.evidence.label} · {proposal.evidence.occurrence_count} 次 · 置信度 {Math.round(proposal.confidence * 100)}%</small>
            <div className="teacher-memory-proposal-actions">
              <button disabled={disabled} onClick={() => onAccept(proposal)} type="button">采用建议</button>
              <button disabled={disabled} onClick={() => onReject(proposal)} type="button">不采用</button>
            </div>
            <details className="teacher-memory-proposal-correction">
              <summary>修正后采用</summary>
              <div>
                <ProposalCorrectionControl
                  disabled={disabled}
                  onChange={(value) => setCorrections((current) => ({
                    ...current,
                    [proposal.proposal_id]: value,
                  }))}
                  proposal={proposal}
                  value={corrections[proposal.proposal_id] ?? String(proposal.value)}
                />
                <button
                  disabled={disabled || !(corrections[proposal.proposal_id] ?? String(proposal.value))}
                  onClick={() => onCorrect(
                    proposal,
                    normalizeProposalCorrection(
                      proposal.key,
                      corrections[proposal.proposal_id] ?? String(proposal.value),
                    ),
                  )}
                  type="button"
                >确认修正</button>
              </div>
            </details>
          </li>
        ))}
      </ol>
    </section>
  );
}

function ProposalCorrectionControl({
  disabled,
  onChange,
  proposal,
  value,
}: {
  disabled: boolean;
  onChange: (value: string) => void;
  proposal: TeacherPreferenceProposal;
  value: string;
}) {
  if (proposal.key === "default_grade") {
    return (
      <select aria-label={`修正${proposal.label}`} disabled={disabled} onChange={(event) => onChange(event.target.value)} value={value}>
        <option>高一</option><option>高二</option><option>高三</option><option>高中通用</option>
      </select>
    );
  }
  if (proposal.key === "default_difficulty") {
    return (
      <select aria-label={`修正${proposal.label}`} disabled={disabled} onChange={(event) => onChange(event.target.value)} value={value}>
        {[1, 2, 3, 4, 5].map((item) => <option key={item} value={item}>{item} / 5</option>)}
      </select>
    );
  }
  return (
    <input
      aria-label={`修正${proposal.label}`}
      disabled={disabled}
      inputMode="numeric"
      max="300"
      min="1"
      onChange={(event) => onChange(event.target.value)}
      type="number"
      value={value}
    />
  );
}

const FEEDBACK_ACTION_LABELS: Record<TeacherPreferenceFeedback["action"], string> = {
  accept: "已采用",
  correct: "修正后采用",
  reject: "不采用",
};

export function TeacherMemoryFeedbackHistory({ items }: { items: TeacherPreferenceFeedback[] }) {
  if (!items.length) return null;
  return (
    <section className="teacher-memory-feedback" aria-labelledby="teacher-memory-feedback-title">
      <header>
        <div>
          <span>可检查记录</span>
          <h3 id="teacher-memory-feedback-title">反馈记录</h3>
        </div>
        <strong>{items.length}</strong>
      </header>
      <ol>
        {items.map((item) => (
          <li key={item.feedback_id}>
            <div>
              <strong>{item.label}</strong>
              <b>{FEEDBACK_ACTION_LABELS[item.action]}</b>
            </div>
            <p>
              建议值：{preferenceDisplayValue(item.key, item.proposed_value)}
              {item.resolved_value !== null && item.action === "correct"
                ? ` → ${preferenceDisplayValue(item.key, item.resolved_value)}`
                : ""}
            </p>
            <small>{item.evidence.label} · {item.evidence.occurrence_count} 次 · 当时置信度 {Math.round(item.confidence * 100)}%</small>
          </li>
        ))}
      </ol>
    </section>
  );
}

type TeacherMemoryLifecycleProps = {
  confirmation: string;
  disabled: boolean;
  onConfirmationChange: (value: string) => void;
  onDelete: () => void;
  onExport: () => void;
  retentionNote: string;
};

export function TeacherMemoryLifecycle({
  confirmation,
  disabled,
  onConfirmationChange,
  onDelete,
  onExport,
  retentionNote,
}: TeacherMemoryLifecycleProps) {
  return (
    <section className="teacher-memory-lifecycle" aria-labelledby="teacher-memory-lifecycle-title">
      <header>
        <span>数据生命周期</span>
        <h3 id="teacher-memory-lifecycle-title">导出与删除</h3>
      </header>
      <p>{retentionNote}</p>
      <button disabled={disabled} onClick={onExport} type="button">导出 JSON</button>
      <div className="teacher-memory-delete-all">
        <strong>永久删除全部教师记忆</strong>
        <span>此操作清除偏好、提议、观察和反馈，且无法恢复；不会删除试卷、教案或私题。</span>
        <label>
          <span>输入“删除全部教师记忆”确认</span>
          <input
            disabled={disabled}
            onChange={(event) => onConfirmationChange(event.target.value)}
            value={confirmation}
          />
        </label>
        <button
          disabled={disabled || confirmation !== "删除全部教师记忆"}
          onClick={onDelete}
          type="button"
        >永久删除全部记忆</button>
      </div>
    </section>
  );
}

function preferenceValue(
  profile: TeacherMemoryProfile | null,
  key: TeacherPreferenceKey,
): TeacherPreferenceValue | undefined {
  return profile?.preferences.find((item) => item.key === key)?.value;
}

export function TeacherMemoryPanel({ open, onClose }: TeacherMemoryPanelProps) {
  const [profile, setProfile] = useState<TeacherMemoryProfile | null>(null);
  const [grade, setGrade] = useState("");
  const [difficulty, setDifficulty] = useState("");
  const [minutes, setMinutes] = useState("");
  const [detail, setDetail] = useState("");
  const [questionTypes, setQuestionTypes] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [savingKey, setSavingKey] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [deleteConfirmation, setDeleteConfirmation] = useState("");
  const [message, setMessage] = useState("");
  const closeRef = useRef<HTMLButtonElement | null>(null);

  const savedByKey = useMemo(
    () => new Map(profile?.preferences.map((item) => [item.key, item]) ?? []),
    [profile],
  );

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    setLoading(true);
    setMessage("");
    void teacherWorkspace.getTeacherMemoryProfile(controller.signal)
      .then((next) => {
        setProfile(next);
        setGrade(String(preferenceValue(next, "default_grade") ?? ""));
        setDifficulty(String(preferenceValue(next, "default_difficulty") ?? ""));
        setMinutes(String(preferenceValue(next, "default_lesson_minutes") ?? ""));
        setDetail(String(preferenceValue(next, "solution_detail_level") ?? ""));
        const types = preferenceValue(next, "preferred_question_types");
        setQuestionTypes(Array.isArray(types) ? types : []);
        window.requestAnimationFrame(() => closeRef.current?.focus());
      })
      .catch((cause) => {
        if (cause instanceof DOMException && cause.name === "AbortError") return;
        setMessage(cause instanceof TeacherWorkspaceError ? cause.message : "无法读取教师偏好。");
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function closeOnEscape(event: globalThis.KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose, open]);

  async function apply(
    command: Omit<TeacherMemoryCommand, "expected_version">,
    key: string,
    successMessage = "偏好已更新。后续任务字段留空时会使用已确认的默认值。",
    onSuccess?: (next: TeacherMemoryProfile) => void,
  ) {
    if (!profile || savingKey) return;
    setSavingKey(key);
    setMessage("");
    try {
      const next = await teacherWorkspace.updateTeacherMemoryProfile({
        ...command,
        expected_version: profile.version,
      });
      setProfile(next);
      onSuccess?.(next);
      setMessage(successMessage);
    } catch (cause) {
      setMessage(cause instanceof TeacherWorkspaceError ? cause.message : "偏好未能更新，请重试。");
    } finally {
      setSavingKey(null);
    }
  }

  function saveScalar(key: TeacherPreferenceKey, value: string, numeric = false) {
    if (!value) return;
    void apply({ operation: "upsert", key, value: numeric ? Number(value) : value }, key);
  }

  function remove(key: TeacherPreferenceKey) {
    void apply({ operation: "remove", key }, key);
  }

  function syncPreferenceInput(key: TeacherPreferenceKey, next: TeacherMemoryProfile) {
    const value = preferenceValue(next, key);
    if (key === "default_grade") setGrade(String(value ?? ""));
    if (key === "default_difficulty") setDifficulty(String(value ?? ""));
    if (key === "default_lesson_minutes") setMinutes(String(value ?? ""));
    if (key === "solution_detail_level") setDetail(String(value ?? ""));
    if (key === "preferred_question_types") setQuestionTypes(Array.isArray(value) ? value : []);
  }

  function reviewProposal(
    operation: "accept_proposal" | "reject_proposal" | "correct_proposal",
    proposal: TeacherPreferenceProposal,
    value?: TeacherPreferenceValue,
  ) {
    const successMessage = operation === "reject_proposal"
      ? "已记录不采用。至少再出现 3 个新的相同行为证据前，系统不会重复提出这个建议。"
      : operation === "correct_proposal"
        ? "已按修正后的值保存为明确偏好。"
        : "已采用建议并保存为明确偏好。";
    void apply(
      { operation, proposal_id: proposal.proposal_id, value },
      `proposal:${proposal.proposal_id}`,
      successMessage,
      operation === "reject_proposal"
        ? undefined
        : (next) => syncPreferenceInput(proposal.key, next),
    );
  }

  async function exportMemory() {
    if (exporting || savingKey) return;
    setExporting(true);
    setMessage("");
    try {
      const artifact = await teacherWorkspace.exportTeacherMemory();
      const url = URL.createObjectURL(artifact.blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = artifact.filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      setMessage("教师记忆已导出为 JSON。文件不包含任务正文或底层证据标识。");
    } catch (cause) {
      setMessage(cause instanceof TeacherWorkspaceError ? cause.message : "教师记忆未能导出，请重试。");
    } finally {
      setExporting(false);
    }
  }

  function deleteAllMemory() {
    void apply(
      { operation: "delete_all", confirmation: deleteConfirmation },
      "delete-all",
      "全部教师记忆已删除，自动学习已关闭。试卷、教案和私题未受影响。",
      (next) => {
        setGrade("");
        setDifficulty("");
        setMinutes("");
        setDetail("");
        setQuestionTypes([]);
        setDeleteConfirmation("");
        setProfile(next);
      },
    );
  }

  return (
    <>
      <button
        aria-hidden="true"
        className={`teacher-memory-backdrop${open ? " is-open" : ""}`}
        onClick={onClose}
        tabIndex={-1}
        type="button"
      />
      <aside
        aria-hidden={!open}
        aria-labelledby="teacher-memory-title"
        className={`teacher-memory-panel${open ? " is-open" : ""}`}
        inert={!open}
      >
        <header>
          <div>
            <span>仅当前教师可见</span>
            <h2 id="teacher-memory-title">教师偏好</h2>
          </div>
          <button aria-label="关闭教师偏好" className="icon-button" onClick={onClose} ref={closeRef} type="button">
            <CloseIcon />
          </button>
        </header>

        <div className="teacher-memory-panel__body">
          <p className="teacher-memory-privacy">{profile?.privacy_note ?? "仅保存结构化教学偏好，不保存任务正文。"}</p>
          {loading && <p className="teacher-memory-state">正在读取偏好…</p>}
          {!loading && profile && (
            <>
              <section className="teacher-memory-auto">
                <div>
                  <strong>自动学习偏好</strong>
                  <span>默认关闭；开启后也只允许形成可解释、可删除的偏好提议。</span>
                </div>
                <label>
                  <input
                    checked={profile.auto_learning_enabled}
                    disabled={Boolean(savingKey)}
                    onChange={(event) => void apply({ operation: "set_auto_learning", enabled: event.target.checked }, "auto")}
                    type="checkbox"
                  />
                  <span>{profile.auto_learning_enabled ? "已开启" : "已关闭"}</span>
                </label>
              </section>

              <TeacherMemoryProposals
                disabled={Boolean(savingKey)}
                items={profile.proposals ?? []}
                onAccept={(proposal) => reviewProposal("accept_proposal", proposal)}
                onCorrect={(proposal, value) => reviewProposal("correct_proposal", proposal, value)}
                onReject={(proposal) => reviewProposal("reject_proposal", proposal)}
              />

              <TeacherMemoryFeedbackHistory items={profile.feedback ?? []} />

              <PreferenceRow item={savedByKey.get("default_grade")} label="默认年级" onRemove={() => remove("default_grade")} saving={savingKey === "default_grade"}>
                <select onChange={(event) => setGrade(event.target.value)} value={grade}>
                  <option value="">请选择</option>
                  <option>高一</option><option>高二</option><option>高三</option><option>高中通用</option>
                </select>
                <button disabled={!grade || Boolean(savingKey)} onClick={() => saveScalar("default_grade", grade)} type="button">保存</button>
              </PreferenceRow>

              <PreferenceRow item={savedByKey.get("default_difficulty")} label="默认难度" onRemove={() => remove("default_difficulty")} saving={savingKey === "default_difficulty"}>
                <select onChange={(event) => setDifficulty(event.target.value)} value={difficulty}>
                  <option value="">请选择</option>
                  {[1, 2, 3, 4, 5].map((value) => <option key={value} value={value}>{value} / 5</option>)}
                </select>
                <button disabled={!difficulty || Boolean(savingKey)} onClick={() => saveScalar("default_difficulty", difficulty, true)} type="button">保存</button>
              </PreferenceRow>

              <PreferenceRow item={savedByKey.get("default_lesson_minutes")} label="默认课时" onRemove={() => remove("default_lesson_minutes")} saving={savingKey === "default_lesson_minutes"}>
                <input inputMode="numeric" max="300" min="1" onChange={(event) => setMinutes(event.target.value)} placeholder="例如 45" type="number" value={minutes} />
                <button disabled={!minutes || Boolean(savingKey)} onClick={() => saveScalar("default_lesson_minutes", minutes, true)} type="button">保存</button>
              </PreferenceRow>

              <PreferenceRow item={savedByKey.get("solution_detail_level")} label="解析详略" onRemove={() => remove("solution_detail_level")} saving={savingKey === "solution_detail_level"}>
                <select onChange={(event) => setDetail(event.target.value)} value={detail}>
                  <option value="">请选择</option>
                  <option value="concise">简洁</option><option value="standard">标准</option><option value="detailed">详细</option>
                </select>
                <button disabled={!detail || Boolean(savingKey)} onClick={() => saveScalar("solution_detail_level", detail)} type="button">保存</button>
              </PreferenceRow>

              <PreferenceRow item={savedByKey.get("preferred_question_types")} label="常用题型" onRemove={() => remove("preferred_question_types")} saving={savingKey === "preferred_question_types"}>
                <div className="teacher-memory-checks">
                  {QUESTION_TYPES.map(([value, label]) => (
                    <label key={value}>
                      <input
                        checked={questionTypes.includes(value)}
                        onChange={(event) => setQuestionTypes((current) => event.target.checked ? [...current, value] : current.filter((item) => item !== value))}
                        type="checkbox"
                      />
                      <span>{label}</span>
                    </label>
                  ))}
                </div>
                <button disabled={!questionTypes.length || Boolean(savingKey)} onClick={() => void apply({ operation: "upsert", key: "preferred_question_types", value: questionTypes }, "preferred_question_types")} type="button">保存</button>
              </PreferenceRow>

              <TeacherMemoryLifecycle
                confirmation={deleteConfirmation}
                disabled={Boolean(savingKey) || exporting}
                onConfirmationChange={setDeleteConfirmation}
                onDelete={deleteAllMemory}
                onExport={() => void exportMemory()}
                retentionNote={profile.retention_note ?? "结构化教师记忆保留至你明确删除。"}
              />
            </>
          )}
          {message && <p aria-live="polite" className="teacher-memory-message">{message}</p>}
        </div>
      </aside>
    </>
  );
}

type PreferenceRowProps = {
  children: React.ReactNode;
  item?: TeacherMemoryProfile["preferences"][number];
  label: string;
  onRemove: () => void;
  saving: boolean;
};

function PreferenceRow({ children, item, label, onRemove, saving }: PreferenceRowProps) {
  return (
    <section className="teacher-memory-row">
      <header>
        <strong>{label}</strong>
        {item && <button disabled={saving} onClick={onRemove} type="button">删除偏好</button>}
      </header>
      <div className="teacher-memory-row__controls">{children}</div>
      {item && (
        <small>
          来源：{item.source.label} · 置信度 {Math.round(item.source.confidence * 100)}%
        </small>
      )}
    </section>
  );
}
