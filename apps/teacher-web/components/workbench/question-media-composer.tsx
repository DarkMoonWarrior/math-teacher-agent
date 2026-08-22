"use client";

import Image from "next/image";
import { useEffect, useMemo, useRef, useState } from "react";
import type { QuestionInputBundle, QuestionMediaSource } from "@/lib/teacher-workspace/contracts";
import { TeacherWorkspaceError } from "@/lib/teacher-workspace/contracts";
import { teacherWorkspace } from "@/lib/teacher-workspace/http-adapter";
import { CameraIcon, CloseIcon, CropIcon, ImageIcon, RotateIcon, UploadIcon } from "./icons";

type CropMargins = { top: number; right: number; bottom: number; left: number };
type RecognitionOption = { key: string; text: string };

const INITIAL_CROP: CropMargins = { top: 4, right: 4, bottom: 4, left: 4 };

type QuestionMediaComposerProps = {
  bundle: QuestionInputBundle | null;
  disabled?: boolean;
  visualProcessingConsent: boolean;
  onChange: (bundle: QuestionInputBundle | null) => void;
  onConfirmed: (bundle: QuestionInputBundle) => void;
  onVisualProcessingConsentChange: (consent: boolean) => void;
};

export function QuestionMediaComposer({
  bundle,
  disabled = false,
  visualProcessingConsent,
  onChange,
  onConfirmed,
  onVisualProcessingConsentChange,
}: QuestionMediaComposerProps) {
  const uploadInputRef = useRef<HTMLInputElement | null>(null);
  const cameraInputRef = useRef<HTMLInputElement | null>(null);
  const operationRef = useRef<AbortController | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [hint, setHint] = useState("");
  const [cropOpen, setCropOpen] = useState(false);
  const [crop, setCrop] = useState<CropMargins>(INITIAL_CROP);
  const [recognitionMode, setRecognitionMode] = useState<"local" | "external">("local");
  const [externalConsent, setExternalConsent] = useState(false);
  const [stemPlain, setStemPlain] = useState("");
  const [stemLatex, setStemLatex] = useState("");
  const [options, setOptions] = useState<RecognitionOption[]>([]);
  const [reviewNote, setReviewNote] = useState("");

  const currentRevision = useMemo(
    () => bundle?.asset.revisions.find((item) => item.revision === bundle.asset.current_revision) ?? null,
    [bundle],
  );

  useEffect(() => () => operationRef.current?.abort(), []);

  useEffect(() => {
    setStemPlain(bundle?.stem_plain ?? "");
    setStemLatex(bundle?.stem_latex ?? "");
    setOptions(bundle?.options ?? []);
    setReviewNote(bundle?.teacher_review_note ?? "");
  }, [bundle?.recognition_revision]);

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

  async function recognize() {
    if (!bundle) return;
    setError("");
    setHint("");
    operationRef.current?.abort();
    const controller = new AbortController();
    operationRef.current = controller;
    setBusy(true);
    try {
      const consentForAction = recognitionMode === "external" && externalConsent;
      if (recognitionMode === "external") setExternalConsent(false);
      const next = await teacherWorkspace.recognizeQuestionMedia(
        bundle.asset.asset_id,
        { mode: recognitionMode, externalProcessingConsent: consentForAction },
        controller.signal,
      );
      onChange(next);
      setHint("识别草稿已生成。请对照原图校对；只有教师确认的精确 revision 才能进入 Solve。");
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === "AbortError") return;
      setError(cause instanceof TeacherWorkspaceError ? cause.message : "题面识别没有完成，请重试。");
    } finally {
      if (operationRef.current === controller) operationRef.current = null;
      setBusy(false);
    }
  }

  async function saveRecognition(confirm: boolean) {
    if (!bundle || !stemPlain.trim()) {
      setError("题面不能为空，请先校对识别结果。");
      return;
    }
    setError("");
    operationRef.current?.abort();
    const controller = new AbortController();
    operationRef.current = controller;
    setBusy(true);
    try {
      const next = await teacherWorkspace.reviewQuestionRecognition(
        bundle.asset.asset_id,
        { stemPlain, stemLatex, options: options.filter((item) => item.key.trim() && item.text.trim()), note: reviewNote, confirm },
        controller.signal,
      );
      onChange(next);
      if (confirm) onConfirmed(next);
      setHint(confirm ? "题面已确认并锁定到当前图片 revision，可以交给 Solve。" : "校对草稿已保存为新的识别 revision。");
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === "AbortError") return;
      setError(cause instanceof TeacherWorkspaceError ? cause.message : "题面校对没有保存成功，请重试。");
    } finally {
      if (operationRef.current === controller) operationRef.current = null;
      setBusy(false);
    }
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
          <section className="question-recognition" aria-label="题面识别与校对">
            <header>
              <div>
                <span>文字与公式识别</span>
                <strong>{bundle.recognition_status === "not_started" ? "尚未识别" : `OCR REV ${bundle.recognition_revision}`}</strong>
              </div>
              <small className={`question-recognition__status is-${bundle.recognition_status}`}>
                {{ not_started: "待识别", draft: "待校对", confirmed: "教师已确认", stale: "图片已变化" }[bundle.recognition_status]}
              </small>
            </header>

            <div className="question-recognition__mode">
              <label>
                <span>识别方式</span>
                <select value={recognitionMode} onChange={(event) => { setRecognitionMode(event.target.value as "local" | "external"); setExternalConsent(false); }} disabled={busy || disabled}>
                  <option value="local">本地数学 OCR · 图片不离开设备</option>
                  <option value="external">DeepSeek Vision / 外部 OCR · 需本次同意</option>
                </select>
              </label>
              {recognitionMode === "external" && (
                <label className="question-recognition__consent">
                  <input type="checkbox" checked={externalConsent} onChange={(event) => setExternalConsent(event.target.checked)} />
                  <span>我同意仅将这张图片发送给已配置的 DeepSeek Vision 或外部 OCR；本次有效，不改变私人归属。</span>
                </label>
              )}
              <button type="button" disabled={busy || disabled || (recognitionMode === "external" && !externalConsent)} onClick={() => void recognize()}>
                {bundle.recognition_status === "not_started" ? "识别题面" : "重新识别当前图片"}
              </button>
            </div>

            {bundle.recognition_status !== "not_started" && (
              <div className="question-recognition__editor">
                {bundle.recognition_status === "stale" && <p className="question-media__warning">图片 revision 已变化，旧识别只能参考；请重新识别后再校对。</p>}
                <label><span>可读题面</span><textarea value={stemPlain} onChange={(event) => setStemPlain(event.target.value)} disabled={busy || disabled || bundle.recognition_status === "stale"} rows={4} /></label>
                <label><span>LaTeX 题面</span><textarea value={stemLatex} onChange={(event) => setStemLatex(event.target.value)} disabled={busy || disabled || bundle.recognition_status === "stale"} rows={3} /></label>
                {options.length > 0 && (
                  <fieldset>
                    <legend>结构化选项</legend>
                    {options.map((option, index) => (
                      <div key={`${index}-${option.key}`}>
                        <input aria-label={`选项 ${index + 1} 标号`} value={option.key} onChange={(event) => setOptions((items) => items.map((item, itemIndex) => itemIndex === index ? { ...item, key: event.target.value } : item))} disabled={busy || disabled || bundle.recognition_status === "stale"} />
                        <input aria-label={`选项 ${index + 1} 内容`} value={option.text} onChange={(event) => setOptions((items) => items.map((item, itemIndex) => itemIndex === index ? { ...item, text: event.target.value } : item))} disabled={busy || disabled || bundle.recognition_status === "stale"} />
                      </div>
                    ))}
                  </fieldset>
                )}
                {bundle.visual_observations.length > 0 ? (
                  <section className="question-recognition__visual" aria-label="图形识别草稿">
                    <header><strong>图形识别草稿</strong><span>仅记录原图可见结构</span></header>
                    <ul>
                      {bundle.visual_observations.map((observation, index) => (
                        <li key={`${index}-${observation}`}>{observation}</li>
                      ))}
                    </ul>
                    <p>请对照原图核对标签、连线与虚实线；这些观察不会代替原图，也不是 MathVerifier 证据。</p>
                  </section>
                ) : bundle.requires_visual_reasoning ? (
                  <p className="question-media__warning">
                    当前识别版本只判断出“需要图形”，尚未生成可核对的图形观察。请逐次授权后重新识别当前图片。
                  </p>
                ) : null}
                {bundle.low_confidence_regions.length > 0 && (
                  <div className="question-recognition__uncertain">
                    <strong>优先核对 {bundle.low_confidence_regions.length} 处</strong>
                    {bundle.low_confidence_regions.map((region, index) => <p key={`${index}-${region.reason}`}>{region.text || "未辨认内容"} · {region.reason}{region.confidence === null ? "" : ` · ${Math.round(region.confidence * 100)}%`}</p>)}
                  </div>
                )}
                {bundle.recognition_warnings.map((warning) => <p className="question-media__warning" key={warning}>{warning}</p>)}
                <label><span>校对备注</span><input value={reviewNote} onChange={(event) => setReviewNote(event.target.value)} disabled={busy || disabled || bundle.recognition_status === "stale"} placeholder="例如：已核对根号范围与选项 B" /></label>
                <div className="question-recognition__actions">
                  <button type="button" disabled={busy || disabled || bundle.recognition_status === "stale"} onClick={() => void saveRecognition(false)}>保存草稿</button>
                  <button type="button" disabled={busy || disabled || bundle.recognition_status === "stale"} onClick={() => void saveRecognition(true)}>确认题面</button>
                </div>
              </div>
            )}
          </section>
          {bundle.recognition_status === "confirmed" && (
            <section className="question-visual-consent" aria-label="本次视觉解题权限">
              <div>
                <span>图形保真输入</span>
                <strong>
                  {bundle.requires_visual_reasoning === false
                    ? "确认题面足够，本次不发送原图"
                    : "本题依赖或可能依赖图形"}
                </strong>
                <small>
                  {bundle.requires_visual_reasoning === false
                    ? "Solve 只消费教师确认的文字与公式 revision。"
                    : "如开始解题，原图仅发送给已配置的视觉解题模型；这不构成 MathVerifier 证据。"}
                </small>
              </div>
              {bundle.requires_visual_reasoning !== false && (
                <label>
                  <input
                    type="checkbox"
                    checked={visualProcessingConsent}
                    disabled={busy || disabled}
                    onChange={(event) => onVisualProcessingConsentChange(event.target.checked)}
                  />
                  <span>我同意本次解题使用 REV {bundle.asset.current_revision} 原图；仅本次有效。</span>
                </label>
              )}
            </section>
          )}
          <p className="question-media__notice">图片与识别 revision 始终属于你的私人工作区；Agent 只转发本次任务的一次性许可，不能选择资源、读取路径或获得图片字节。</p>
        </div>
      )}

      {busy && !bundle && <p className="question-media__status">正在校验格式、清晰度与私人归属…</p>}
      {hint && <p className="question-media__hint">{hint}</p>}
      {error && <p className="question-media__error" role="alert">{error}</p>}
    </section>
  );
}
