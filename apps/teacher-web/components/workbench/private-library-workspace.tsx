"use client";

import {
  type ChangeEvent,
  type FormEvent,
  useEffect,
  useRef,
  useState,
} from "react";
import type {
  LibraryItemDetail,
  LibraryItemSummary,
  LibraryRightsBasis,
  LibraryTextRevision,
} from "@/lib/teacher-workspace/contracts";
import { TeacherWorkspaceError } from "@/lib/teacher-workspace/contracts";
import { teacherWorkspace } from "@/lib/teacher-workspace/http-adapter";
import {
  ArrowRightIcon,
  CheckIcon,
  CloseIcon,
  ClockIcon,
  HistoryIcon,
  LibraryIcon,
  LockIcon,
  SparkIcon,
  UploadIcon,
} from "./icons";

const MAX_FILE_BYTES = 50 * 1024 * 1024;
const ALLOWED_EXTENSIONS = ["pdf", "docx", "png", "jpg", "jpeg", "webp"];

const RIGHTS_OPTIONS: Array<{
  value: LibraryRightsBasis;
  label: string;
  detail: string;
}> = [
  {
    value: "private_teaching_only",
    label: "仅私人教学",
    detail: "不声明原创，不允许公开检索或改编。",
  },
  {
    value: "original",
    label: "本人原创",
    detail: "由本人创作，仍先保留在私人空间。",
  },
  {
    value: "licensed",
    label: "已获授权",
    detail: "已取得相应使用授权，请写明依据。",
  },
];

function fileExtension(filename: string): string {
  return filename.split(".").pop()?.toLowerCase() ?? "";
}

function validateFile(file: File): string {
  if (!ALLOWED_EXTENSIONS.includes(fileExtension(file.name))) {
    return "文件格式不支持。请选择 PDF、DOCX、PNG、JPEG 或 WebP。";
  }
  if (file.size > MAX_FILE_BYTES) {
    return "文件超过 50 MB。请压缩后重新选择。";
  }
  return "";
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function fileKindLabel(kind: LibraryItemSummary["file_kind"]): string {
  if (kind === "docx") return "DOCX";
  if (kind === "image") return "图片";
  return "PDF";
}

function rightsLabel(basis: LibraryRightsBasis): string {
  return RIGHTS_OPTIONS.find((option) => option.value === basis)?.label ?? basis;
}

function reviewState(item: LibraryItemSummary): {
  label: string;
  tone: "ready" | "pending" | "ocr";
} {
  if (item.text_review_status === "confirmed") {
    return { label: "教师已确认", tone: "ready" };
  }
  if (item.extraction_status === "needs_ocr") {
    return { label: "等待 OCR", tone: "ocr" };
  }
  return { label: "等待校对", tone: "pending" };
}

export function PrivateLibraryWorkspace() {
  const [items, setItems] = useState<LibraryItemSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [rightsBasis, setRightsBasis] = useState<LibraryRightsBasis>("private_teaching_only");
  const [rightsStatement, setRightsStatement] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);
  const [touched, setTouched] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [formError, setFormError] = useState("");
  const [announcement, setAnnouncement] = useState("");
  const [selectedItemId, setSelectedItemId] = useState("");
  const [detail, setDetail] = useState<LibraryItemDetail | null>(null);
  const [revisions, setRevisions] = useState<LibraryTextRevision[]>([]);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [correctedText, setCorrectedText] = useState("");
  const [reviewNote, setReviewNote] = useState("");
  const [savingReview, setSavingReview] = useState<"draft" | "confirm" | "">("");
  const [ocrMode, setOcrMode] = useState<"local" | "external" | "">("");
  const [ocrProgress, setOcrProgress] = useState("");
  const [externalConsent, setExternalConsent] = useState(false);
  const [detailMessage, setDetailMessage] = useState("");
  const inputRef = useRef<HTMLInputElement | null>(null);
  const detailRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    teacherWorkspace.listPrivateLibrary(controller.signal)
      .then((listing) => {
        setItems(listing.items);
        setLoadError("");
      })
      .catch((cause: unknown) => {
        if (cause instanceof DOMException && cause.name === "AbortError") return;
        setLoadError(cause instanceof Error ? cause.message : "私人资料暂时无法读取。请稍后重试。");
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!selectedItemId) {
      setDetail(null);
      setRevisions([]);
      setDetailError("");
      return;
    }
    const controller = new AbortController();
    setDetailLoading(true);
    setDetailError("");
    setDetailMessage("");
    Promise.all([
      teacherWorkspace.getPrivateLibraryItem(selectedItemId, controller.signal),
      teacherWorkspace.listPrivateLibraryRevisions(selectedItemId, controller.signal),
    ])
      .then(([item, history]) => {
        setDetail(item);
        setCorrectedText(item.corrected_text);
        setReviewNote(item.review_note);
        setRevisions(history.items);
        requestAnimationFrame(() => detailRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
      })
      .catch((cause: unknown) => {
        if (cause instanceof DOMException && cause.name === "AbortError") return;
        setDetailError(cause instanceof Error ? cause.message : "无法打开这份私人资料。");
      })
      .finally(() => setDetailLoading(false));
    return () => controller.abort();
  }, [selectedItemId]);

  const fileError = selectedFile ? validateFile(selectedFile) : "";
  const statementError = rightsStatement.trim().length < 6
    ? "请用至少 6 个字说明资料来源或使用依据。"
    : "";
  const canUpload = Boolean(selectedFile)
    && !fileError
    && !statementError
    && acknowledged
    && !uploading;

  function chooseFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null;
    setSelectedFile(file);
    setFormError("");
    setAnnouncement("");
    if (file && !title.trim()) {
      setTitle(file.name.replace(/\.[^.]+$/, ""));
    }
  }

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setTouched(true);
    if (!selectedFile || !canUpload) return;
    setUploading(true);
    setFormError("");
    setAnnouncement("");
    try {
      const uploaded = await teacherWorkspace.uploadPrivateLibrary({
        file: selectedFile,
        title: title.trim(),
        rightsBasis,
        rightsStatement: rightsStatement.trim(),
        rightsAcknowledged: true,
      });
      setItems((current) => [uploaded, ...current.filter((item) => item.library_item_id !== uploaded.library_item_id)]);
      setSelectedFile(null);
      setTitle("");
      setRightsStatement("");
      setAcknowledged(false);
      setTouched(false);
      if (inputRef.current) inputRef.current.value = "";
      setAnnouncement(`“${uploaded.title || uploaded.original_filename}”已加入私人资料库。`);
      setSelectedItemId(uploaded.library_item_id);
    } catch (cause) {
      const message = cause instanceof TeacherWorkspaceError
        ? cause.message
        : "上传未完成。请检查文件后重新尝试。";
      setFormError(message);
    } finally {
      setUploading(false);
    }
  }

  function syncDetail(item: LibraryItemDetail) {
    setDetail(item);
    setCorrectedText(item.corrected_text);
    setReviewNote(item.review_note);
    setItems((current) => current.map((entry) => (
      entry.library_item_id === item.library_item_id ? item : entry
    )));
  }

  async function refreshRevisions(itemId: string) {
    const history = await teacherWorkspace.listPrivateLibraryRevisions(itemId);
    setRevisions(history.items);
  }

  async function saveReview(confirm: boolean) {
    if (!detail || !correctedText.trim() || savingReview || ocrMode) return;
    setSavingReview(confirm ? "confirm" : "draft");
    setDetailError("");
    setDetailMessage("");
    try {
      const saved = await teacherWorkspace.reviewPrivateLibraryText(detail.library_item_id, {
        correctedText,
        note: reviewNote.trim(),
        confirm,
      });
      syncDetail(saved);
      await refreshRevisions(saved.library_item_id);
      setDetailMessage(confirm
        ? "文本已由你确认，仍只保存在私人资料库。"
        : "校对草稿已保存，并留下了一条修订记录。");
    } catch (cause) {
      setDetailError(cause instanceof Error ? cause.message : "校对内容没有保存成功。");
    } finally {
      setSavingReview("");
    }
  }

  async function runOCR(mode: "local" | "external") {
    if (!detail || ocrMode || savingReview) return;
    if (mode === "external" && !externalConsent) {
      setDetailError("请先勾选本次外部 OCR 授权。该授权只对这一次操作有效。");
      return;
    }
    setOcrMode(mode);
    setOcrProgress(mode === "local" ? "正在准备本地识别" : "正在准备外部识别");
    setDetailError("");
    setDetailMessage("");
    try {
      const result = await teacherWorkspace.processPrivateLibraryOCR(
        detail.library_item_id,
        { mode, externalProcessingConsent: mode === "external" && externalConsent },
        { onProgress: setOcrProgress },
      );
      syncDetail(result.item);
      await refreshRevisions(result.item.library_item_id);
      setDetailMessage(`${mode === "local" ? "本地" : "外部"} OCR 已生成可编辑草稿，请对照原文件逐项确认。`);
      setExternalConsent(false);
    } catch (cause) {
      setDetailError(cause instanceof Error ? cause.message : "OCR 没有生成可用草稿。");
    } finally {
      setOcrMode("");
      setOcrProgress("");
    }
  }

  const fileUrl = detail
    ? `/api/v1/library/${encodeURIComponent(detail.library_item_id)}/file`
    : "";
  const reviewChanged = detail
    ? correctedText !== detail.corrected_text || reviewNote !== detail.review_note
    : false;
  const actionsBusy = Boolean(savingReview || ocrMode);

  return (
    <main className="library-workspace">
      <section className="library-intro">
        <div>
          <p className="mode-status"><i className="is-ready" aria-hidden="true" />Private Library 已接入</p>
          <h1>我的资料，<br />我的工作流。</h1>
          <p>上传讲义、试卷和题目图片。系统会保存来源与权利声明；内容不会自动进入公共题库，也不会用于模型训练。</p>
        </div>
        <p className="privacy-promise"><LockIcon /><span>当前教师私人空间</span><small>不公开 · 不训练 · 不自动发布</small></p>
      </section>

      <form className="library-upload" onSubmit={upload} noValidate>
        <header>
          <div>
            <span>添加资料</span>
            <h2>文件和来历，一起留下。</h2>
          </div>
          <span className="file-limit">PDF · DOCX · 图片 · 50 MB 内</span>
        </header>

        <div className={`file-picker${touched && (!selectedFile || fileError) ? " is-error" : ""}`}>
          <input
            ref={inputRef}
            id="private-library-file"
            accept=".pdf,.docx,.png,.jpg,.jpeg,.webp"
            aria-describedby="private-library-file-help"
            aria-invalid={Boolean(touched && (!selectedFile || fileError))}
            onChange={chooseFile}
            type="file"
          />
          <label htmlFor="private-library-file">
            <UploadIcon />
            <span>{selectedFile ? "更换文件" : "选择教学资料"}</span>
          </label>
          <div>
            <strong>{selectedFile?.name ?? "还没有选择文件"}</strong>
            <small id="private-library-file-help">
              {touched && !selectedFile
                ? "请选择一份要放入私人资料库的文件。"
                : fileError || (selectedFile ? formatBytes(selectedFile.size) : "文件只保存在当前教师工作区。")}
            </small>
          </div>
        </div>

        <div className="library-fields">
          <label className="library-field">
            <span>资料名称 <small>可选</small></span>
            <input
              autoComplete="off"
              maxLength={300}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="例如：函数单调性课堂讲义"
              type="text"
              value={title}
            />
            <small>不填写时使用原文件名。</small>
          </label>

          <fieldset className="rights-basis">
            <legend>权利依据</legend>
            <div>
              {RIGHTS_OPTIONS.map((option) => (
                <label key={option.value}>
                  <input
                    checked={rightsBasis === option.value}
                    name="rights-basis"
                    onChange={() => setRightsBasis(option.value)}
                    type="radio"
                    value={option.value}
                  />
                  <span><strong>{option.label}</strong><small>{option.detail}</small></span>
                </label>
              ))}
            </div>
          </fieldset>

          <label className="library-field library-field--statement">
            <span>来源或授权说明</span>
            <textarea
              aria-describedby="rights-statement-help"
              aria-invalid={Boolean(touched && statementError)}
              aria-required="true"
              maxLength={2000}
              onBlur={() => setTouched(true)}
              onChange={(event) => setRightsStatement(event.target.value)}
              placeholder="例如：来自本人 2026 学年校本讲义，仅用于本人的课堂备课。"
              rows={3}
              value={rightsStatement}
            />
            <small id="rights-statement-help" className={touched && statementError ? "is-error" : ""}>
              {touched && statementError ? statementError : "这段说明会随资料保留，不能被 Agent 擦除。"}
            </small>
          </label>
        </div>

        <footer className="library-upload__actions">
          <label className="rights-confirmation">
            <input
              checked={acknowledged}
              onChange={(event) => setAcknowledged(event.target.checked)}
              type="checkbox"
            />
            <span>我确认上述来源说明真实，并同意仅存入当前私人工作区。</span>
          </label>
          <button disabled={!canUpload} type="submit">
            {uploading ? <span className="button-loader" aria-hidden="true" /> : <UploadIcon />}
            <span>{uploading ? "正在保存" : "存入私人资料"}</span>
          </button>
        </footer>

        <div className="library-form-message">
          {formError && <p className="is-error" role="alert">{formError}</p>}
        </div>
        <p className="library-announcement" aria-live="polite">{announcement}</p>
      </form>

      <section className="library-shelf" aria-busy={loading}>
        <header>
          <div>
            <span>私人资料</span>
            <h2>{loading ? "正在读取资料" : `${items.length} 份资料留在当前空间`}</h2>
          </div>
          <p><LockIcon />所有条目默认 private</p>
        </header>

        {loading ? (
          <div className="library-skeleton" aria-label="正在读取私人资料">
            <i /><i /><i />
          </div>
        ) : loadError ? (
          <div className="library-empty library-empty--error" role="alert">
            <ClockIcon /><h3>资料清单没有加载完成</h3><p>{loadError}</p>
          </div>
        ) : items.length === 0 ? (
          <div className="library-empty">
            <LibraryIcon />
            <h3>私人资料库还是空的。</h3>
            <p>从上方选择一份自己的讲义、试卷或题目图片。</p>
            <button type="button" onClick={() => inputRef.current?.click()}>选择第一份资料 <ArrowRightIcon /></button>
          </div>
        ) : (
          <ol className="library-list">
            {items.map((item) => {
              const state = reviewState(item);
              return (
                <li className={selectedItemId === item.library_item_id ? "is-selected" : ""} key={item.library_item_id}>
                  <div className="library-file-mark" aria-hidden="true">{fileKindLabel(item.file_kind)}</div>
                  <button
                    className="library-item__title"
                    onClick={() => setSelectedItemId(item.library_item_id)}
                    type="button"
                  >
                    <strong>{item.title || item.original_filename}</strong>
                    <span>{item.original_filename}</span>
                  </button>
                  <div className="library-item__meta">
                    <span>{formatBytes(item.size_bytes)}</span>
                    {item.page_count && <span>{item.page_count} 页</span>}
                    <span>{formatDate(item.updated_at)}</span>
                  </div>
                  <div className="library-item__trust">
                    <span className={`library-state library-state--${state.tone}`}>
                      {state.tone === "ready" ? <CheckIcon /> : <ClockIcon />}{state.label}
                    </span>
                    <span><LockIcon />{rightsLabel(item.rights_basis)} · 私有</span>
                    <button onClick={() => setSelectedItemId(item.library_item_id)} type="button">
                      打开校对 <ArrowRightIcon />
                    </button>
                  </div>
                </li>
              );
            })}
          </ol>
        )}
      </section>

      {selectedItemId && (
        <section className="library-review" ref={detailRef} aria-busy={detailLoading}>
          <header className="library-review__header">
            <div>
              <span>提取与 OCR 校对</span>
              <h2>{detail?.title || detail?.original_filename || "正在打开资料"}</h2>
              <p><LockIcon />原文件、识别文本和修订记录仅属于当前教师。</p>
            </div>
            <button
              aria-label="关闭资料校对"
              className="library-review__close"
              onClick={() => setSelectedItemId("")}
              type="button"
            ><CloseIcon /></button>
          </header>

          {detailLoading ? (
            <div className="library-review__loading"><span className="button-loader" /><p>正在读取原文件和修订记录…</p></div>
          ) : detailError && !detail ? (
            <div className="library-empty library-empty--error" role="alert">
              <ClockIcon /><h3>这份资料没有打开</h3><p>{detailError}</p>
            </div>
          ) : detail ? (
            <>
              <div className="library-review__meta">
                <span>{fileKindLabel(detail.file_kind)}</span>
                <span>{formatBytes(detail.size_bytes)}</span>
                {detail.page_count && <span>{detail.page_count} 页</span>}
                <span>文本 v{detail.version}</span>
                <span><LockIcon />{rightsLabel(detail.rights_basis)}</span>
              </div>

              {detail.warnings.length > 0 && (
                <aside className="library-warning-list" aria-label="识别与校对提示">
                  <ClockIcon />
                  <div>
                    <strong>识别提示</strong>
                    <ul>{detail.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
                  </div>
                </aside>
              )}

              <div className="library-ocr-console">
                <div>
                  <p className="library-eyebrow">需要重新识别？</p>
                  <h3>先本地，必要时再外部。</h3>
                  <p>OCR 只生成草稿，不会把资料送入题库，也不会替你确认数学内容。</p>
                </div>
                <div className="library-ocr-actions">
                  <button
                    disabled={actionsBusy || detail.file_kind !== "pdf"}
                    onClick={() => void runOCR("local")}
                    type="button"
                  >
                    {ocrMode === "local" ? <span className="button-loader" /> : <SparkIcon />}
                    {ocrMode === "local" ? "本地识别中" : "本地数学 OCR"}
                  </button>
                  <small>{detail.file_kind === "pdf" ? "文件不离开本机。" : "本地 OCR 当前只支持 PDF。"}</small>
                  <label className="library-external-consent">
                    <input
                      checked={externalConsent}
                      disabled={actionsBusy}
                      onChange={(event) => setExternalConsent(event.target.checked)}
                      type="checkbox"
                    />
                    <span>仅本次同意将当前文件发送给已配置的外部 OCR 服务。</span>
                  </label>
                  <button
                    className="is-secondary"
                    disabled={actionsBusy || !externalConsent}
                    onClick={() => void runOCR("external")}
                    type="button"
                  >
                    {ocrMode === "external" ? <span className="button-loader" /> : <ArrowRightIcon />}
                    {ocrMode === "external" ? "外部识别中" : "使用外部 OCR"}
                  </button>
                </div>
                {ocrProgress && <p className="library-ocr-progress" aria-live="polite"><ClockIcon />{ocrProgress}</p>}
              </div>

              <div className="library-review__comparison">
                <article className="library-source">
                  <header><span>01</span><div><h3>原始文件</h3><p>始终保留，用于逐页核对。</p></div></header>
                  <div className="library-source__preview">
                    {detail.file_kind === "image" ? (
                      <img alt={`${detail.title || detail.original_filename} 原始图片`} src={fileUrl} />
                    ) : detail.file_kind === "pdf" ? (
                      <object aria-label={`${detail.title || detail.original_filename} PDF 预览`} data={fileUrl} type="application/pdf">
                        <p>浏览器无法嵌入预览。<a href={fileUrl} rel="noreferrer" target="_blank">在新窗口打开 PDF</a></p>
                      </object>
                    ) : (
                      <div className="library-source__fallback">
                        <LibraryIcon />
                        <p>DOCX 保持原文件不变。请在新窗口下载后对照校对。</p>
                        <a href={fileUrl} rel="noreferrer" target="_blank">打开原文件 <ArrowRightIcon /></a>
                      </div>
                    )}
                  </div>
                  <details className="library-extracted-text">
                    <summary>查看首次提取文本</summary>
                    <pre>{detail.extracted_text || "未提取到嵌入文本，可运行 OCR 或手动录入。"}</pre>
                  </details>
                </article>

                <article className="library-editor">
                  <header><span>02</span><div><h3>教师校对稿</h3><p>OCR 结果未经确认；你可以直接修订。</p></div></header>
                  <label>
                    <span>可编辑文本</span>
                    <textarea
                      aria-label="私人资料校对文本"
                      disabled={actionsBusy}
                      onChange={(event) => setCorrectedText(event.target.value)}
                      placeholder="在这里录入或校对题目、公式与解析…"
                      spellCheck={false}
                      value={correctedText}
                    />
                  </label>
                  <label className="library-review-note">
                    <span>本次修订说明 <small>可选</small></span>
                    <input
                      disabled={actionsBusy}
                      maxLength={500}
                      onChange={(event) => setReviewNote(event.target.value)}
                      placeholder="例如：核对了第 3 题公式"
                      value={reviewNote}
                    />
                  </label>
                  <div className="library-review__actions">
                    <p>{detail.text_review_status === "confirmed" ? <><CheckIcon />当前版本已由教师确认</> : <><ClockIcon />当前版本仍待教师确认</>}</p>
                    <button
                      className="is-secondary"
                      disabled={actionsBusy || !correctedText.trim() || !reviewChanged}
                      onClick={() => void saveReview(false)}
                      type="button"
                    >{savingReview === "draft" ? <span className="button-loader" /> : <HistoryIcon />}保存草稿</button>
                    <button
                      disabled={actionsBusy || !correctedText.trim()}
                      onClick={() => void saveReview(true)}
                      type="button"
                    >{savingReview === "confirm" ? <span className="button-loader" /> : <CheckIcon />}确认本版文本</button>
                  </div>
                </article>
              </div>

              {(detailError || detailMessage) && (
                <p className={`library-detail-message${detailError ? " is-error" : ""}`} role={detailError ? "alert" : "status"}>
                  {detailError || detailMessage}
                </p>
              )}

              <section className="library-revisions">
                <header><div><span>03</span><h3>修订记录</h3></div><p>{revisions.length ? `${revisions.length} 次变更` : "尚无变更"}</p></header>
                {revisions.length ? (
                  <ol>
                    {revisions.map((revision) => (
                      <li key={`${revision.version}-${revision.created_at}`}>
                        <details>
                          <summary>
                            <strong>v{revision.version} · {revision.review_status === "confirmed" ? "教师已确认" : "校对草稿"}</strong>
                            <span>{formatDate(revision.created_at)}{revision.note ? ` · ${revision.note}` : ""}</span>
                          </summary>
                          <pre>{revision.revised_text}</pre>
                        </details>
                      </li>
                    ))}
                  </ol>
                ) : <p className="library-revisions__empty">保存第一次校对后，这里会留下可追溯的版本。</p>}
              </section>
            </>
          ) : null}
        </section>
      )}
    </main>
  );
}
