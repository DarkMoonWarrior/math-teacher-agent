"use client";

import { type FocusEvent, type InputHTMLAttributes, useEffect, useRef, useState } from "react";

export function parseEditableNumber(value: string): number | null {
  if (value.trim() === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

type EditableNumberInputProps = Omit<
  InputHTMLAttributes<HTMLInputElement>,
  "defaultValue" | "onChange" | "type" | "value"
> & {
  value: number;
  onValueChange: (value: number) => void;
};

export function EditableNumberInput({
  value,
  onValueChange,
  onBlur,
  onFocus,
  ...props
}: EditableNumberInputProps) {
  const [draftValue, setDraftValue] = useState(() => String(value));
  const focusedRef = useRef(false);

  useEffect(() => {
    if (!focusedRef.current) setDraftValue(String(value));
  }, [value]);

  function handleFocus(event: FocusEvent<HTMLInputElement>) {
    focusedRef.current = true;
    onFocus?.(event);
  }

  function handleBlur(event: FocusEvent<HTMLInputElement>) {
    focusedRef.current = false;
    const parsed = parseEditableNumber(event.currentTarget.value);
    setDraftValue(parsed === null ? String(value) : String(parsed));
    if (parsed !== null) onValueChange(parsed);
    onBlur?.(event);
  }

  return (
    <input
      {...props}
      onBlur={handleBlur}
      onChange={(event) => {
        const nextDraft = event.target.value;
        setDraftValue(nextDraft);
        const parsed = parseEditableNumber(nextDraft);
        if (parsed !== null) onValueChange(parsed);
      }}
      onFocus={handleFocus}
      type="number"
      value={draftValue}
    />
  );
}
