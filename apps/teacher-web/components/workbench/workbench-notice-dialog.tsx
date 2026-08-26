"use client";

import { type ReactNode, type RefObject, useEffect, useId, useRef } from "react";
import { CheckIcon, CloseIcon, LockIcon } from "./icons";

export type WorkbenchNoticeTone = "success" | "error" | "warning" | "danger";

type WorkbenchNoticeDialogProps = {
  actionDisabled?: boolean;
  actionLabel?: string;
  busy?: boolean;
  children?: ReactNode;
  closeLabel?: string;
  message: string;
  onAction?: () => void;
  onDismiss: () => void;
  open: boolean;
  returnFocusRef?: RefObject<HTMLElement | null>;
  title: string;
  tone: WorkbenchNoticeTone;
};

function NoticeIcon({ tone }: { tone: WorkbenchNoticeTone }) {
  if (tone === "success") return <CheckIcon />;
  if (tone === "danger") return <LockIcon />;
  return <CloseIcon />;
}

export function WorkbenchNoticeDialog({
  actionDisabled = false,
  actionLabel,
  busy = false,
  children,
  closeLabel = "关闭提示",
  message,
  onAction,
  onDismiss,
  open,
  returnFocusRef,
  title,
  tone,
}: WorkbenchNoticeDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const titleId = useId();
  const messageId = useId();

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      previousFocusRef.current = returnFocusRef?.current
        ?? (document.activeElement instanceof HTMLElement ? document.activeElement : null);
      dialog.showModal();
      window.requestAnimationFrame(() => {
        dialog.querySelector<HTMLElement>("[data-dialog-initial]")?.focus();
      });
    } else if (!open && dialog.open) {
      dialog.close();
      if (previousFocusRef.current?.isConnected && !previousFocusRef.current.matches(":disabled")) {
        previousFocusRef.current.focus({ preventScroll: true });
      } else {
        document.querySelector<HTMLElement>("main button:not(:disabled), main input:not(:disabled), main textarea:not(:disabled)")?.focus({ preventScroll: true });
      }
      previousFocusRef.current = null;
    }
  }, [open, returnFocusRef]);

  useEffect(() => {
    if (!open) return;
    function handleEscape(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      event.preventDefault();
      if (!busy) onDismiss();
    }
    document.addEventListener("keydown", handleEscape, true);
    return () => document.removeEventListener("keydown", handleEscape, true);
  }, [busy, onDismiss, open]);

  function dismiss() {
    if (!busy) onDismiss();
  }

  return (
    <dialog
      aria-describedby={messageId}
      aria-labelledby={titleId}
      className="workbench-notice-dialog"
      data-state={busy ? "loading" : tone}
      data-tone={tone}
      onCancel={(event) => {
        event.preventDefault();
        dismiss();
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) dismiss();
      }}
      ref={dialogRef}
    >
      <div className="workbench-notice-dialog__paper">
        <span className="workbench-notice-dialog__mark" aria-hidden="true"><NoticeIcon tone={tone} /></span>
        <div className="workbench-notice-dialog__copy">
          <h2 id={titleId}>{title}</h2>
          <p id={messageId}>{message}</p>
        </div>
        {children && <div className="workbench-notice-dialog__body">{children}</div>}
        <footer>
          {actionLabel && onAction && (
            <button
              className="workbench-notice-dialog__primary"
              data-dialog-initial
              data-state={busy ? "loading" : tone}
              disabled={actionDisabled || busy}
              onClick={onAction}
              type="button"
            >
              {busy ? "正在处理…" : actionLabel}
            </button>
          )}
          <button
            className="workbench-notice-dialog__secondary"
            data-dialog-initial={!actionLabel ? "true" : undefined}
            disabled={busy}
            onClick={dismiss}
            type="button"
          >
            {closeLabel}
          </button>
        </footer>
      </div>
    </dialog>
  );
}
