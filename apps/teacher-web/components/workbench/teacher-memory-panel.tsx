"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  type TeacherMemoryCommand,
  type TeacherMemoryProfile,
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

  async function apply(command: Omit<TeacherMemoryCommand, "expected_version">, key: string) {
    if (!profile || savingKey) return;
    setSavingKey(key);
    setMessage("");
    try {
      const next = await teacherWorkspace.updateTeacherMemoryProfile({
        ...command,
        expected_version: profile.version,
      });
      setProfile(next);
      setMessage("偏好已更新。后续切片会在任务字段留空时应用这些默认值。");
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
