"use client";

import {
  Children,
  type CSSProperties,
  type KeyboardEvent,
  type PointerEvent,
  type ReactNode,
  useRef,
  useState,
} from "react";

type ResizableSplitPaneProps = {
  ariaLabel: string;
  children: ReactNode;
  className?: string;
  defaultPrimaryPercent?: number;
  disabled?: boolean;
  maxPrimaryPercent?: number;
  minPrimaryPercent?: number;
  state?: "default" | "loading" | "error" | "success";
};

type SplitPaneStyle = CSSProperties & {
  "--split-primary": string;
  "--split-secondary": string;
};

export function clampSplitPercent(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, value));
}

export function splitPercentForKey(
  current: number,
  key: string,
  shiftKey: boolean,
  minimum: number,
  maximum: number,
): number | null {
  const step = shiftKey ? 10 : 2;
  if (key === "ArrowLeft") return clampSplitPercent(current - step, minimum, maximum);
  if (key === "ArrowRight") return clampSplitPercent(current + step, minimum, maximum);
  if (key === "Home") return minimum;
  if (key === "End") return maximum;
  return null;
}

export function ResizableSplitPane({
  ariaLabel,
  children,
  className = "",
  defaultPrimaryPercent = 40,
  disabled = false,
  maxPrimaryPercent = 65,
  minPrimaryPercent = 30,
  state = "default",
}: ResizableSplitPaneProps) {
  const initialPercent = clampSplitPercent(defaultPrimaryPercent, minPrimaryPercent, maxPrimaryPercent);
  const [primaryPercent, setPrimaryPercent] = useState(initialPercent);
  const [dragging, setDragging] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const draggingPointerRef = useRef<number | null>(null);
  const panes = Children.toArray(children);
  const style: SplitPaneStyle = {
    "--split-primary": `${primaryPercent}fr`,
    "--split-secondary": `${100 - primaryPercent}fr`,
  };

  function updateFromPointer(clientX: number) {
    const bounds = containerRef.current?.getBoundingClientRect();
    if (!bounds || bounds.width <= 0) return;
    const dividerWidth = containerRef.current
      ?.querySelector<HTMLElement>(".resizable-split-pane__divider")
      ?.getBoundingClientRect().width ?? 0;
    const usableWidth = bounds.width - dividerWidth;
    if (usableWidth <= 0) return;
    const next = ((clientX - bounds.left - (dividerWidth / 2)) / usableWidth) * 100;
    setPrimaryPercent(clampSplitPercent(next, minPrimaryPercent, maxPrimaryPercent));
  }

  function startDragging(event: PointerEvent<HTMLDivElement>) {
    if (disabled || (event.pointerType === "mouse" && event.button !== 0)) return;
    event.preventDefault();
    draggingPointerRef.current = event.pointerId;
    event.currentTarget.setPointerCapture(event.pointerId);
    setDragging(true);
    updateFromPointer(event.clientX);
  }

  function moveDivider(event: PointerEvent<HTMLDivElement>) {
    if (disabled || draggingPointerRef.current !== event.pointerId) return;
    updateFromPointer(event.clientX);
  }

  function stopDragging(event: PointerEvent<HTMLDivElement>) {
    if (draggingPointerRef.current !== event.pointerId) return;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    draggingPointerRef.current = null;
    setDragging(false);
  }

  function resizeWithKeyboard(event: KeyboardEvent<HTMLDivElement>) {
    if (disabled) return;
    const next = splitPercentForKey(
      primaryPercent,
      event.key,
      event.shiftKey,
      minPrimaryPercent,
      maxPrimaryPercent,
    );
    if (next === null) return;
    event.preventDefault();
    setPrimaryPercent(next);
  }

  return (
    <div
      className={`resizable-split-pane${className ? ` ${className}` : ""}`}
      data-dragging={dragging ? "true" : "false"}
      ref={containerRef}
      style={style}
    >
      <div className="resizable-split-pane__pane" data-pane="primary">{panes[0]}</div>
      <div
        aria-busy={state === "loading" || undefined}
        aria-disabled={disabled || undefined}
        aria-label={ariaLabel}
        aria-orientation="vertical"
        aria-valuemax={maxPrimaryPercent}
        aria-valuemin={minPrimaryPercent}
        aria-valuenow={Math.round(primaryPercent)}
        aria-valuetext={`左侧区域宽度 ${Math.round(primaryPercent)}%`}
        className="resizable-split-pane__divider"
        data-state={dragging ? "active" : state}
        onDoubleClick={() => !disabled && setPrimaryPercent(initialPercent)}
        onKeyDown={resizeWithKeyboard}
        onLostPointerCapture={() => {
          draggingPointerRef.current = null;
          setDragging(false);
        }}
        onPointerCancel={stopDragging}
        onPointerDown={startDragging}
        onPointerMove={moveDivider}
        onPointerUp={stopDragging}
        role="separator"
        tabIndex={disabled ? -1 : 0}
      >
        <span className="resizable-split-pane__grip" aria-hidden="true"><i /><i /><i /></span>
      </div>
      <div className="resizable-split-pane__pane" data-pane="secondary">{panes[1]}</div>
    </div>
  );
}
