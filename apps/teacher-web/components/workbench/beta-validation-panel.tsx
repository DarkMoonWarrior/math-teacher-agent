"use client";

import { useEffect, useRef, useState } from "react";
import {
  type BetaParticipantMetricExport,
  type BetaValidationNotice,
  TeacherWorkspaceError,
} from "@/lib/teacher-workspace/contracts";
import { teacherWorkspace } from "@/lib/teacher-workspace/http-adapter";
import { CloseIcon } from "./icons";

type BetaValidationPanelProps = {
  open: boolean;
  onClose: () => void;
};

function readableError(cause: unknown, fallback: string) {
  return cause instanceof TeacherWorkspaceError ? cause.message : fallback;
}

export function BetaValidationPanel({ open, onClose }: BetaValidationPanelProps) {
  const [notice, setNotice] = useState<BetaValidationNotice | null>(null);
  const [metricExport, setMetricExport] = useState<BetaParticipantMetricExport | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState<"join" | "export" | "leave" | null>(null);
  const [confirmingLeave, setConfirmingLeave] = useState(false);
  const [message, setMessage] = useState("");
  const closeRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    setLoading(true);
    setConfirmingLeave(false);
    setMessage("");
    void teacherWorkspace.getBetaValidationNotice(controller.signal)
      .then(async (nextNotice) => {
        setNotice(nextNotice);
        try {
          const nextExport = await teacherWorkspace.getBetaValidationExport(controller.signal);
          setMetricExport(nextExport);
        } catch (cause) {
          if (cause instanceof DOMException && cause.name === "AbortError") return;
          setMetricExport(null);
        }
        window.requestAnimationFrame(() => closeRef.current?.focus());
      })
      .catch((cause) => {
        if (cause instanceof DOMException && cause.name === "AbortError") return;
        setMessage(readableError(cause, "无法读取封闭测试数据说明。"));
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

  async function joinValidation() {
    if (busy || !notice?.collection_enabled) return;
    setBusy("join");
    setMessage("");
    try {
      const participation = await teacherWorkspace.acknowledgeBetaValidation();
      const nextExport = await teacherWorkspace.getBetaValidationExport();
      setMetricExport({ ...nextExport, acknowledged_at: participation.acknowledged_at });
      setMessage("你已主动加入数据验证。只会记录下方列出的无正文指标。");
    } catch (cause) {
      setMessage(readableError(cause, "暂时无法加入数据验证，请重试。"));
    } finally {
      setBusy(null);
    }
  }

  async function downloadMetrics() {
    if (busy) return;
    setBusy("export");
    setMessage("");
    try {
      const nextExport = await teacherWorkspace.getBetaValidationExport();
      setMetricExport(nextExport);
      const blob = new Blob([JSON.stringify(nextExport, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "closed-beta-metrics.json";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      setMessage("你的保留期内聚合指标已导出。文件不含任务正文。" );
    } catch (cause) {
      setMessage(readableError(cause, "暂时无法导出指标，请重试。"));
    } finally {
      setBusy(null);
    }
  }

  async function leaveValidation() {
    if (busy) return;
    setBusy("leave");
    setMessage("");
    try {
      const deletion = await teacherWorkspace.leaveBetaValidation();
      setMetricExport((current) => current ? {
        ...current,
        acknowledged_at: null,
        event_count: 0,
        metrics: {},
        trust_tier_error_rates: {},
      } : null);
      setConfirmingLeave(false);
      setMessage(`已退出数据验证，并删除 ${deletion.deleted_events} 条本人指标事件。`);
    } catch (cause) {
      setMessage(readableError(cause, "暂时无法退出数据验证，请重试。"));
    } finally {
      setBusy(null);
    }
  }

  const participating = Boolean(metricExport?.acknowledged_at);

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
        aria-labelledby="beta-validation-title"
        className={`teacher-memory-panel beta-validation-panel${open ? " is-open" : ""}`}
        inert={!open}
      >
        <header>
          <div>
            <span>由你决定是否参与</span>
            <h2 id="beta-validation-title">封闭测试与数据</h2>
          </div>
          <button aria-label="关闭封闭测试与数据" className="icon-button" onClick={onClose} ref={closeRef} type="button">
            <CloseIcon />
          </button>
        </header>

        <div className="teacher-memory-panel__body beta-validation-panel__body">
          <p className="teacher-memory-privacy">
            数据验证默认关闭。只有你阅读说明并主动加入后，系统才会记录不含题面、答案、解析或教师输入正文的汇总事件。
          </p>
          {loading && <p className="teacher-memory-state">正在读取数据说明…</p>}
          {notice && (
            <>
              <section className="beta-validation-summary" aria-label="参与状态">
                <div>
                  <span>当前状态</span>
                  <strong>{participating ? "已加入" : notice.collection_enabled ? "未加入" : "本轮未开放"}</strong>
                </div>
                <div>
                  <span>保留期限</span>
                  <strong>{notice.retention_days} 天</strong>
                </div>
                <div>
                  <span>本人事件</span>
                  <strong>{metricExport?.event_count ?? 0} 条</strong>
                </div>
              </section>

              <section className="beta-validation-list is-collected">
                <h3>会记录什么</h3>
                <ul>{notice.collected_categories.map((item) => <li key={item}>{item}</li>)}</ul>
              </section>
              <section className="beta-validation-list is-excluded">
                <h3>绝不会记录什么</h3>
                <ul>{notice.excluded_categories.map((item) => <li key={item}>{item}</li>)}</ul>
              </section>
              <section className="beta-validation-list">
                <h3>你的权利</h3>
                <ul>{notice.teacher_rights.map((item) => <li key={item}>{item}</li>)}</ul>
              </section>

              {!participating && notice.collection_enabled && (
                <button className="beta-validation-primary" disabled={Boolean(busy)} onClick={() => void joinValidation()} type="button">
                  {busy === "join" ? "正在加入…" : "同意加入数据验证"}
                </button>
              )}
              {participating && (
                <section className="beta-validation-actions">
                  <button disabled={Boolean(busy)} onClick={() => void downloadMetrics()} type="button">
                    {busy === "export" ? "正在导出…" : "导出我的指标"}
                  </button>
                  {!confirmingLeave ? (
                    <button className="is-danger" disabled={Boolean(busy)} onClick={() => setConfirmingLeave(true)} type="button">
                      退出并删除指标数据
                    </button>
                  ) : (
                    <div className="beta-validation-leave-confirm" role="alert">
                      <strong>确认退出并删除？</strong>
                      <p>只删除你的数据验证事件和参与记录，不影响试卷、教案、私题或教师偏好。</p>
                      <div>
                        <button disabled={Boolean(busy)} onClick={() => setConfirmingLeave(false)} type="button">取消</button>
                        <button className="is-danger" disabled={Boolean(busy)} onClick={() => void leaveValidation()} type="button">
                          {busy === "leave" ? "正在删除…" : "确认退出并删除"}
                        </button>
                      </div>
                    </div>
                  )}
                </section>
              )}
            </>
          )}
          {message && <p className="teacher-memory-message" role="status">{message}</p>}
        </div>
      </aside>
    </>
  );
}
