"use client";

import Image from "next/image";
import { useEffect, useMemo, useRef, useState } from "react";
import type { QuestionInputBundle, QuestionMediaSource } from "@/lib/teacher-workspace/contracts";
import { TeacherWorkspaceError } from "@/lib/teacher-workspace/contracts";
import { teacherWorkspace } from "@/lib/teacher-workspace/http-adapter";
import { CameraIcon, CloseIcon, CropIcon, ImageIcon, RotateIcon, UploadIcon } from "./icons";

type CropMargins = { top: number; right: number; bottom: number; left: number };

const INITIAL_CROP: CropMargins = { top: 4, right: 4, bottom: 4, left: 4 };

type QuestionMediaComposerProps = {
  bundle: QuestionInputBundle | null;
  disabled?: boolean;
  onChange: (bundle: QuestionInputBundle | null) => void;
};

export function QuestionMediaComposer({ bundle, disabled = false, onChange }: QuestionMediaComposerProps) {
  const uploadInputRef = useRef<HTMLInputElement | null>(null);
  const cameraInputRef = useRef<HTMLInputElement | null>(null);
  const operationRef = useRef<AbortController | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [hint, setHint] = useState("");
  const [cropOpen, setCropOpen] = useState(false);
  const [crop, setCrop] = useState<CropMargins>(INITIAL_CROP);

  const currentRevision = useMemo(
    () => bundle?.asset.revisions.find((item) => item.revision === bundle.asset.current_revision) ?? null,
    [bundle],
  );

  useEffect(() => () => operationRef.current?.abort(), []);

  useEffect(() => {
    function receiveClipboardImage(event: globalThis.ClipboardEvent) {
      if (disabled || busy) return;
      const imageItem = Array.from(event.clipboardData?.items ?? []).find((item) => item.type.startsWith("image/"));
      const blob = imageItem?.getAsFile();
      if (!blob) return;
      event.preventDefault();
      const extension = blob.type === "image/jpeg" ? "jpg" : blob.type === "image/webp" ? "webp" : "png";
      const file = new File([blob], `粘贴的题目-${Date.now()}.${extension}`, { type: blob.type });
      void upload(file, "clipboard");
    }
    window.addEventListener("paste", receiveClipboardImage);
    return () => window.removeEventListener("paste", receiveClipboardImage);
  });

  async function upload(file: File, source: QuestionMediaSource) {
    setError("");
    setHint("");
    if (!file.type.startsWith("image/")) {
      setError("请选择 PNG、JPEG 或 WebP 题目图片。");
      return;
    }
    if (file.size > 15 * 1024 * 1024) {
      setError("单张题目图片不能超过 15 MB。");
      return;
    }
    operationRef.current?.abort();
    const controller = new AbortController();
    operationRef.current = controller;
    setBusy(true);
    try {
      const next = await teacherWorkspace.uploadQuestionMedia({
        file,
        source,
        privateStorageAcknowledged: true,
      }, controller.signal);
      onChange(next);
      setCropOpen(false);
      setCrop(INITIAL_CROP);
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === "AbortError") return;
      setError(cause instanceof TeacherWorkspaceError ? cause.message : "题目图片没有保存成功，请重试。");
    } finally {
      if (operationRef.current === controller) operationRef.current = null;
      setBusy(false);
    }
  }

  async function readClipboard() {
    setError("");
    if (!navigator.clipboard?.read) {
      setHint("请按 Ctrl+V 或 ⌘V 粘贴截图。");
      return;
    }
    try {
      const items = await navigator.clipboard.read();
      for (const item of items) {
        const imageType = item.types.find((type) => type.startsWith("image/"));
        if (!imageType) continue;
        const blob = await item.getType(imageType);
        const extension = imageType === "image/jpeg" ? "jpg" : imageType === "image/webp" ? "webp" : "png";
        await upload(new File([blob], `粘贴的题目-${Date.now()}.${extension}`, { type: imageType }), "clipboard");
        return;
      }
      setHint("剪贴板里没有图片；也可以直接按 Ctrl+V 粘贴截图。");
    } catch {
      setHint("浏览器没有授权读取剪贴板；请直接按 Ctrl+V 粘贴截图。");
    }
  }

  async function transform(transform: Parameters<typeof teacherWorkspace.transformQuestionMedia>[1]) {
    if (!bundle) return;
    setError("");
    operationRef.current?.abort();
    const controller = new AbortController();
    operationRef.current = controller;
    setBusy(true);
    try {
      const next = await teacherWorkspace.transformQuestionMedia(
        bundle.asset.asset_id,
        transform,
        controller.signal,
      );
      onChange(next);
      setCropOpen(false);
      setCrop(INITIAL_CROP);
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === "AbortError") return;
      setError(cause instanceof TeacherWorkspaceError ? cause.message : "图片调整没有完成，请重试。");
    } finally {
      if (operationRef.current === controller) operationRef.current = null;
      setBusy(false);
    }
  }

  function applyCrop() {
    if (!bundle) return;
    const x = Math.round(bundle.asset.width * crop.left / 100);
    const y = Math.round(bundle.asset.height * crop.top / 100);
    const width = Math.round(bundle.asset.width * (100 - crop.left - crop.right) / 100);
    const height = Math.round(bundle.asset.height * (100 - crop.top - crop.bottom) / 100);
    void transform({ operation: "crop", crop: { x, y, width, height } });
  }

  function selectFile(event: React.ChangeEvent<HTMLInputElement>, source: QuestionMediaSource) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) void upload(file, source);
  }

  return (
    <section className={`question-media${bundle ? " has-asset" : ""}`} aria-busy={busy} aria-label="题目图片">
      <input ref={uploadInputRef} hidden type="file" accept="image/png,image/jpeg,image/webp" onChange={(event) => selectFile(event, "upload")} />
      <input ref={cameraInputRef} hidden type="file" accept="image/*" capture="environment" onChange={(event) => selectFile(event, "camera")} />

      {!bundle ? (
        <div className="question-media__empty">
          <div className="question-media__copy">
            <ImageIcon />
            <div><strong>也可以给我一道题的图片</strong><span>原图只进入你的私人工作区；本步骤不会发送给外部模型。</span></div>
          </div>
          <div className="question-media__entries">
            <button type="button" disabled={disabled || busy} onClick={() => uploadInputRef.current?.click()}><UploadIcon />上传图片</button>
            <button type="button" disabled={disabled || busy} onClick={() => void readClipboard()}><ImageIcon />粘贴截图</button>
            <button type="button" disabled={disabled || busy} onClick={() => cameraInputRef.current?.click()}><CameraIcon />拍照</button>
          </div>
        </div>
      ) : (
        <div className="question-media__asset">
          <div className="question-media__preview">
            {currentRevision && (
              <Image
                alt="当前私人题目图片"
                fill
                priority
                sizes="(max-width: 900px) 90vw, 720px"
                src={currentRevision.content_endpoint}
                unoptimized
              />
            )}
            {cropOpen && <span className="question-media__crop-frame" style={{ inset: `${crop.top}% ${crop.right}% ${crop.bottom}% ${crop.left}%` }} />}
            {busy && <span className="question-media__busy">正在保护并处理图片…</span>}
          </div>
          <div className="question-media__meta">
            <div>
              <span>PRIVATE · REV {bundle.asset.current_revision}</span>
              <strong>{bundle.asset.original_filename}</strong>
              <small>{bundle.asset.width} × {bundle.asset.height}px · {bundle.asset.clarity_status === "clear" ? "清晰度检查通过" : "建议人工检查"}</small>
            </div>
            <button type="button" disabled={busy || disabled} onClick={() => onChange(null)} aria-label="从本次解题移除图片"><CloseIcon /></button>
          </div>
          <div className="question-media__tools" aria-label="图片调整">
            <button type="button" disabled={busy || disabled} onClick={() => void transform({ operation: "rotate", degrees: 270 })}><RotateIcon />向左转</button>
            <button type="button" disabled={busy || disabled} onClick={() => void transform({ operation: "rotate", degrees: 90 })}><RotateIcon className="is-clockwise" />向右转</button>
            <button type="button" aria-pressed={cropOpen} disabled={busy || disabled} onClick={() => setCropOpen((value) => !value)}><CropIcon />裁剪</button>
            <button type="button" disabled={busy || disabled} onClick={() => uploadInputRef.current?.click()}><UploadIcon />替换</button>
          </div>
          {cropOpen && (
            <div className="question-media__crop-controls">
              {(["top", "right", "bottom", "left"] as const).map((edge) => (
                <label key={edge}>
                  <span>{{ top: "上", right: "右", bottom: "下", left: "左" }[edge]}边</span>
                  <input type="range" min="0" max="30" value={crop[edge]} onChange={(event) => setCrop((value) => ({ ...value, [edge]: Number(event.target.value) }))} />
                  <small>{crop[edge]}%</small>
                </label>
              ))}
              <div><button type="button" onClick={() => { setCrop(INITIAL_CROP); setCropOpen(false); }}>取消</button><button type="button" onClick={applyCrop}>应用裁剪</button></div>
            </div>
          )}
          {bundle.asset.warnings.map((warning) => <p className="question-media__warning" key={warning}>{warning}</p>)}
          <p className="question-media__notice">图片已保留原始版本与修订记录。当前 M7 第一切片尚未运行 OCR，解题前仍需输入文字题面。</p>
        </div>
      )}

      {busy && !bundle && <p className="question-media__status">正在校验格式、清晰度与私人归属…</p>}
      {hint && <p className="question-media__hint">{hint}</p>}
      {error && <p className="question-media__error" role="alert">{error}</p>}
    </section>
  );
}
