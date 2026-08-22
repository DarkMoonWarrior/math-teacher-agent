"use client";

import {
  type ChangeEvent,
  type FormEvent,
  useEffect,
  useRef,
  useState,
} from "react";
import type {
  LibraryItemSummary,
  LibraryRightsBasis,
} from "@/lib/teacher-workspace/contracts";
import { TeacherWorkspaceError } from "@/lib/teacher-workspace/contracts";
import { teacherWorkspace } from "@/lib/teacher-workspace/http-adapter";
import {
  ArrowRightIcon,
  CheckIcon,
  ClockIcon,
  LibraryIcon,
  LockIcon,
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
  const inputRef = useRef<HTMLInputElement | null>(null);

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
    } catch (cause) {
      const message = cause instanceof TeacherWorkspaceError
        ? cause.message
        : "上传未完成。请检查文件后重新尝试。";
      setFormError(message);
    } finally {
      setUploading(false);
    }
  }

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
                <li key={item.library_item_id}>
                  <div className="library-file-mark" aria-hidden="true">{fileKindLabel(item.file_kind)}</div>
                  <div className="library-item__title">
                    <strong>{item.title || item.original_filename}</strong>
                    <span>{item.original_filename}</span>
                  </div>
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
                  </div>
                </li>
              );
            })}
          </ol>
        )}
      </section>
    </main>
  );
}
