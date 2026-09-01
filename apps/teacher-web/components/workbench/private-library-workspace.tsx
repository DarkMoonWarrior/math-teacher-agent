"use client";

import {
  type ChangeEvent,
  type FormEvent,
  useEffect,
  useRef,
  useState,
} from "react";
import type {
  CurriculumSearchItem,
  LibraryItemDetail,
  LibraryItemSummary,
  LibraryTextRevision,
  PrivateLibraryQuestionCandidate,
  PrivateLibraryQuestionCandidateDraft,
  PrivateLibrarySearchItem,
} from "@/lib/teacher-workspace/contracts";
import { TeacherWorkspaceError } from "@/lib/teacher-workspace/contracts";
import { teacherWorkspace } from "@/lib/teacher-workspace/http-adapter";
import { MathText } from "../math-text";
import {
  ArrowRightIcon,
  BookIcon,
  CheckIcon,
  CloseIcon,
  ClockIcon,
  HistoryIcon,
  LibraryIcon,
  LockIcon,
  PlusIcon,
  SearchIcon,
  SparkIcon,
  UploadIcon,
} from "./icons";
import { ResizableSplitPane } from "./resizable-split-pane";

const MAX_FILE_BYTES = 50 * 1024 * 1024;
const ALLOWED_EXTENSIONS = ["pdf", "docx", "png", "jpg", "jpeg", "webp"];

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

export function privateLibraryRecognitionPreview(
  draft: string,
  running: boolean,
  error: string,
): { kind: "loading" | "error" | "empty" | "content"; text: string } {
  if (running) return { kind: "loading", text: "大模型正在识别并整理原稿…" };
  if (error) return { kind: "error", text: `识别失败：${error}` };
  const text = draft.trim();
  if (!text || text === "无") return { kind: "empty", text: "尚未生成大模型整理稿。" };
  return { kind: "content", text };
}

const QUESTION_TYPE_OPTIONS: Array<{
  value: PrivateLibraryQuestionCandidate["question_type"];
  label: string;
}> = [
  { value: "single_choice", label: "单选题" },
  { value: "multiple_choice", label: "多选题" },
  { value: "fill_blank", label: "填空题" },
  { value: "open_response", label: "解答题" },
];

function candidateDraft(
  candidate: PrivateLibraryQuestionCandidate,
): PrivateLibraryQuestionCandidateDraft {
  return {
    question_type: candidate.question_type,
    stem_plain: candidate.stem_plain,
    stem_latex: candidate.stem_latex,
    options: candidate.options,
    answer_value: candidate.answer_value,
    solution_method: candidate.solution_method,
    solution_steps: candidate.solution_steps,
    final_answer: candidate.final_answer,
    difficulty: candidate.difficulty,
  };
}

export function PrivateLibraryQuestionPreview({
  draft,
}: {
  draft: PrivateLibraryQuestionCandidateDraft;
}) {
  const stem = draft.stem_latex?.trim() || draft.stem_plain.trim();
  return (
    <section className="candidate-readable-preview" aria-label="可读题目预览">
      <header>
        <div><span>题面预览</span><small>数学公式已排版</small></div>
        <strong>{QUESTION_TYPE_OPTIONS.find((item) => item.value === draft.question_type)?.label}</strong>
      </header>
      <div className="candidate-readable-preview__stem"><MathText text={stem || "题面为空"} /></div>
      {draft.options.length > 0 && (
        <ol className="candidate-readable-preview__options">
          {draft.options.map((option) => (
            <li key={option.key}><strong>{option.key}.</strong><MathText text={option.text || "未填写"} /></li>
          ))}
        </ol>
      )}
      <dl>
        <div><dt>答案</dt><dd><MathText text={draft.answer_value?.trim() || "无"} /></dd></div>
        <div><dt>解析</dt><dd>{draft.solution_steps.length > 0
          ? draft.solution_steps.map((step, index) => <p key={index}><MathText text={step} /></p>)
          : <span>无</span>}</dd></div>
      </dl>
    </section>
  );
}

function CandidateEditor({
  candidate,
  onSave,
  onMap,
  onImport,
}: {
  candidate: PrivateLibraryQuestionCandidate;
  onSave: (draft: PrivateLibraryQuestionCandidateDraft) => Promise<void>;
  onMap: (nodeId: string) => Promise<void>;
  onImport: () => Promise<void>;
}) {
  const [draft, setDraft] = useState(() => candidateDraft(candidate));
  const [query, setQuery] = useState(candidate.curriculum?.name ?? "");
  const [matches, setMatches] = useState<CurriculumSearchItem[]>([]);
  const [busy, setBusy] = useState<"save" | "search" | "map" | "import" | "">("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    setDraft(candidateDraft(candidate));
    if (candidate.curriculum) setQuery(candidate.curriculum.name);
  }, [candidate]);

  const locked = candidate.status === "imported";
  const dirty = JSON.stringify(draft) !== JSON.stringify(candidateDraft(candidate));
  const choiceQuestion = draft.question_type === "single_choice"
    || draft.question_type === "multiple_choice";

  function changeDraft<Key extends keyof PrivateLibraryQuestionCandidateDraft>(
    key: Key,
    value: PrivateLibraryQuestionCandidateDraft[Key],
  ) {
    setDraft((current) => ({ ...current, [key]: value }));
    setMessage("");
  }

  async function save() {
    if (!draft.stem_plain.trim() || locked || busy) return;
    setBusy("save");
    setError("");
    try {
      await onSave({ ...draft, stem_plain: draft.stem_plain.trim() });
      setMessage("候选题修改已保存。教材映射仍需单独确认。");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "候选题没有保存成功。");
    } finally {
      setBusy("");
    }
  }

  async function searchCurriculum() {
    if (!query.trim() || busy) return;
    setBusy("search");
    setError("");
    setMessage("");
    try {
      const result = await teacherWorkspace.searchCurriculum(query);
      setMatches(result.items);
      if (!result.items.length) setMessage("没有找到匹配知识点，请换一个教材关键词。");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "教材知识点没有加载成功。");
    } finally {
      setBusy("");
    }
  }

  async function mapCurriculum(node: CurriculumSearchItem) {
    if (busy || locked || dirty) return;
    setBusy("map");
    setError("");
    try {
      await onMap(node.node_id);
      setMatches([]);
      setQuery(node.name);
      setMessage(`已确认映射：${node.volume} · ${node.name}`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "教材映射没有保存成功。");
    } finally {
      setBusy("");
    }
  }

  async function importCandidate() {
    if (busy || locked || dirty || !candidate.curriculum) return;
    setBusy("import");
    setError("");
    try {
      await onImport();
      setMessage("已进入你的私人题库，状态为待审核与待数学验证。");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "候选题没有导入成功。");
    } finally {
      setBusy("");
    }
  }

  return (
    <article className={`candidate-card${locked ? " is-imported" : ""}`}>
      <header>
        <div>
          <span>候选 {String(candidate.position).padStart(2, "0")}</span>
          <strong>{locked ? "已存入私人题库" : "等待教师整理"}</strong>
        </div>
        <p><LockIcon />private · 来源文本 v{candidate.source_version}</p>
      </header>

      <PrivateLibraryQuestionPreview draft={draft} />

      <div className="candidate-fields">
        <label>
          <span>题型</span>
          <select
            disabled={locked || Boolean(busy)}
            onChange={(event) => changeDraft(
              "question_type",
              event.target.value as PrivateLibraryQuestionCandidate["question_type"],
            )}
            value={draft.question_type}
          >
            {QUESTION_TYPE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </label>
        <label>
          <span>难度 <small>{draft.difficulty} / 5</small></span>
          <input
            disabled={locked || Boolean(busy)}
            max={5}
            min={1}
            onChange={(event) => changeDraft("difficulty", Number(event.target.value))}
            type="range"
            value={draft.difficulty}
          />
        </label>
        <label className="candidate-field--wide">
          <span>题干</span>
          <textarea
            disabled={locked || Boolean(busy)}
            onChange={(event) => changeDraft("stem_plain", event.target.value)}
            rows={5}
            value={draft.stem_plain}
          />
        </label>

        {choiceQuestion && (
          <fieldset className="candidate-options candidate-field--wide">
            <legend>选项</legend>
            {draft.options.map((option, index) => (
              <label key={`${option.key}-${index}`}>
                <span>{option.key}</span>
                <input
                  disabled={locked || Boolean(busy)}
                  onChange={(event) => changeDraft("options", draft.options.map((entry, optionIndex) => (
                    optionIndex === index ? { ...entry, text: event.target.value } : entry
                  )))}
                  value={option.text}
                />
                {!locked && draft.options.length > 2 && (
                  <button
                    aria-label={`删除选项 ${option.key}`}
                    disabled={Boolean(busy)}
                    onClick={() => changeDraft(
                      "options",
                      draft.options
                        .filter((_, optionIndex) => optionIndex !== index)
                        .map((entry, optionIndex) => ({
                          ...entry,
                          key: String.fromCharCode(65 + optionIndex),
                        })),
                    )}
                    type="button"
                  ><CloseIcon /></button>
                )}
              </label>
            ))}
            {!locked && draft.options.length < 8 && (
              <button
                className="candidate-option-add"
                disabled={Boolean(busy)}
                onClick={() => changeDraft("options", [
                  ...draft.options,
                  { key: String.fromCharCode(65 + draft.options.length), text: "" },
                ])}
                type="button"
              ><PlusIcon />增加选项</button>
            )}
          </fieldset>
        )}

        <label>
          <span>答案</span>
          <input
            disabled={locked || Boolean(busy)}
            onChange={(event) => changeDraft("answer_value", event.target.value)}
            value={draft.answer_value ?? ""}
          />
        </label>
        <label>
          <span>解法</span>
          <input
            disabled={locked || Boolean(busy)}
            onChange={(event) => changeDraft("solution_method", event.target.value)}
            value={draft.solution_method}
          />
        </label>
        <label>
          <span>最终答案</span>
          <input
            disabled={locked || Boolean(busy)}
            onChange={(event) => changeDraft("final_answer", event.target.value)}
            value={draft.final_answer ?? ""}
          />
        </label>
        <label className="candidate-field--wide">
          <span>解析步骤 <small>每行一步</small></span>
          <textarea
            disabled={locked || Boolean(busy)}
            onChange={(event) => changeDraft("solution_steps", event.target.value.split("\n"))}
            rows={4}
            value={draft.solution_steps.join("\n")}
          />
        </label>
      </div>

      <div className="candidate-save-row">
        <p>{dirty ? "有尚未保存的修改" : "题目内容已保存"}</p>
        <button disabled={locked || Boolean(busy) || !dirty || !draft.stem_plain.trim()} onClick={() => void save()} type="button">
          {busy === "save" ? <span className="button-loader" /> : <CheckIcon />}
          保存候选题
        </button>
      </div>

      <section className="candidate-curriculum">
        <header>
          <div><BookIcon /><span>教材知识点</span></div>
          <p>{dirty ? "先保存题目修改" : candidate.curriculum ? "教师已确认映射" : "导入前必须确认"}</p>
        </header>
        {candidate.curriculum && (
          <div className="candidate-curriculum__current">
            <strong>{candidate.curriculum.name}</strong>
            <span>{[candidate.curriculum.volume, candidate.curriculum.chapter, candidate.curriculum.section].filter(Boolean).join(" · ")}</span>
          </div>
        )}
        {!locked && (
          <>
            <div className="candidate-curriculum__search">
              <input
                aria-label={`候选 ${candidate.position} 的教材关键词`}
                disabled={Boolean(busy)}
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    void searchCurriculum();
                  }
                }}
                placeholder="例如：元素与集合、函数单调性"
                value={query}
              />
              <button disabled={Boolean(busy) || !query.trim()} onClick={() => void searchCurriculum()} type="button">
                {busy === "search" ? <span className="button-loader" /> : <SearchIcon />}搜索教材
              </button>
            </div>
            {matches.length > 0 && (
              <ol className="candidate-curriculum__matches">
                {matches.map((node) => (
                  <li key={node.node_id}>
                    <button disabled={Boolean(busy) || dirty} onClick={() => void mapCurriculum(node)} type="button">
                      <span><strong>{node.name}</strong><small>{node.code} · {node.volume}</small></span>
                      <small>{[node.chapter, node.section].filter(Boolean).join(" / ")}</small>
                      <ArrowRightIcon />
                    </button>
                  </li>
                ))}
              </ol>
            )}
          </>
        )}
      </section>

      {(message || error) && <p className={`candidate-message${error ? " is-error" : ""}`}>{error || message}</p>}
      <footer>
        <p><LockIcon /><span>只进入当前教师的私人题库</span><small>待审核 · 待 MathVerifier</small></p>
        <button
          disabled={locked || Boolean(busy) || dirty || !candidate.curriculum}
          onClick={() => void importCandidate()}
          type="button"
        >
          {busy === "import" ? <span className="button-loader" /> : locked ? <CheckIcon /> : <ArrowRightIcon />}
          {locked ? "已导入" : dirty ? "先保存修改" : !candidate.curriculum ? "先确认教材映射" : "存入私人题库"}
        </button>
      </footer>
    </article>
  );
}

export function PrivateLibraryWorkspace() {
  const [items, setItems] = useState<LibraryItemSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [rightsStatement, setRightsStatement] = useState("");
  const [touched, setTouched] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [formError, setFormError] = useState("");
  const [announcement, setAnnouncement] = useState("");
  const [privateQuery, setPrivateQuery] = useState("");
  const [privateSearchBusy, setPrivateSearchBusy] = useState(false);
  const [privateSearchItems, setPrivateSearchItems] = useState<PrivateLibrarySearchItem[]>([]);
  const [privateSearchTotal, setPrivateSearchTotal] = useState<number | null>(null);
  const [privateSearchError, setPrivateSearchError] = useState("");
  const [selectedItemId, setSelectedItemId] = useState("");
  const [detail, setDetail] = useState<LibraryItemDetail | null>(null);
  const [revisions, setRevisions] = useState<LibraryTextRevision[]>([]);
  const [candidates, setCandidates] = useState<PrivateLibraryQuestionCandidate[]>([]);
  const [candidatesLoading, setCandidatesLoading] = useState(false);
  const [candidateMessage, setCandidateMessage] = useState("");
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [correctedText, setCorrectedText] = useState("");
  const [reviewNote, setReviewNote] = useState("");
  const [savingReview, setSavingReview] = useState<"draft" | "confirm" | "">("");
  const [ocrMode, setOcrMode] = useState<"external" | "">("");
  const [ocrProgress, setOcrProgress] = useState("");
  const [recognitionError, setRecognitionError] = useState("");
  const [detailMessage, setDetailMessage] = useState("");
  const inputRef = useRef<HTMLInputElement | null>(null);
  const detailRef = useRef<HTMLElement | null>(null);
  const privateSearchResultRef = useRef<HTMLDivElement | null>(null);

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
      setCandidates([]);
      setDetailError("");
      setRecognitionError("");
      return;
    }
    const controller = new AbortController();
    setDetailLoading(true);
    setCandidatesLoading(true);
    setDetailError("");
    setRecognitionError("");
    setDetailMessage("");
    Promise.all([
      teacherWorkspace.getPrivateLibraryItem(selectedItemId, controller.signal),
      teacherWorkspace.listPrivateLibraryRevisions(selectedItemId, controller.signal),
      teacherWorkspace.listPrivateLibraryQuestionCandidates(selectedItemId, controller.signal),
    ])
      .then(([item, history, candidateList]) => {
        setDetail(item);
        setCorrectedText(item.corrected_text);
        setReviewNote(item.review_note);
        setRevisions(history.items);
        setCandidates(candidateList.items);
        requestAnimationFrame(() => detailRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
      })
      .catch((cause: unknown) => {
        if (cause instanceof DOMException && cause.name === "AbortError") return;
        setDetailError(cause instanceof Error ? cause.message : "无法打开这份私人资料。");
      })
      .finally(() => {
        setDetailLoading(false);
        setCandidatesLoading(false);
      });
    return () => controller.abort();
  }, [selectedItemId]);

  const fileError = selectedFile ? validateFile(selectedFile) : "";
  const canUpload = Boolean(selectedFile)
    && !fileError
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
        rightsBasis: "private_teaching_only",
        rightsStatement: rightsStatement.trim(),
        rightsAcknowledged: true,
      });
      setItems((current) => [uploaded, ...current.filter((item) => item.library_item_id !== uploaded.library_item_id)]);
      setSelectedFile(null);
      setTitle("");
      setRightsStatement("");
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

  async function searchPrivateContent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const query = privateQuery.trim();
    if (!query || privateSearchBusy) return;
    setPrivateSearchBusy(true);
    setPrivateSearchError("");
    setPrivateSearchTotal(null);
    try {
      const result = await teacherWorkspace.searchPrivateLibrary(query, true);
      setPrivateSearchItems(result.items);
      setPrivateSearchTotal(result.total);
      requestAnimationFrame(() => privateSearchResultRef.current?.scrollIntoView({ behavior: "smooth", block: "center" }));
    } catch (cause) {
      setPrivateSearchItems([]);
      setPrivateSearchError(cause instanceof Error ? cause.message : "本次私人检索没有完成。");
    } finally {
      setPrivateSearchBusy(false);
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
      setCandidates([]);
      setCandidateMessage("");
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

  async function runOCR() {
    if (!detail || ocrMode || savingReview) return;
    setOcrMode("external");
    setOcrProgress("正在准备大模型识别");
    setRecognitionError("");
    setDetailError("");
    setDetailMessage("");
    try {
      const result = await teacherWorkspace.processPrivateLibraryOCR(
        detail.library_item_id,
        { mode: "external", externalProcessingConsent: true },
        { onProgress: setOcrProgress },
      );
      syncDetail(result.item);
      await refreshRevisions(result.item.library_item_id);
      setDetailMessage("大模型已生成可读校对稿，可继续修改或确认。");
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "大模型没有生成可用草稿。";
      setRecognitionError(message);
      setDetailError(message);
    } finally {
      setOcrMode("");
      setOcrProgress("");
    }
  }

  function replaceCandidate(updated: PrivateLibraryQuestionCandidate) {
    setCandidates((current) => current.map((candidate) => (
      candidate.candidate_id === updated.candidate_id ? updated : candidate
    )));
  }

  async function prepareCandidates() {
    if (!detail || detail.text_review_status !== "confirmed" || candidatesLoading) return;
    setCandidatesLoading(true);
    setCandidateMessage(detail.file_kind === "pdf" ? "大模型正在逐题识别题面、答案和解析…" : "");
    try {
      const result = await teacherWorkspace.preparePrivateLibraryQuestionCandidates(
        detail.library_item_id,
        { externalProcessingConsent: detail.file_kind === "pdf" },
      );
      setCandidates(result.items);
      setCandidateMessage(result.items.length
        ? `已从教师确认的文本 v${result.source_version} 生成 ${result.items.length} 道候选，请逐题核对。`
        : "当前确认文本中没有识别到可拆分的题目，请先调整题号结构。");
    } catch (cause) {
      setCandidateMessage(cause instanceof Error ? cause.message : "没有生成拆题候选。");
    } finally {
      setCandidatesLoading(false);
    }
  }

  async function saveCandidate(
    candidate: PrivateLibraryQuestionCandidate,
    draft: PrivateLibraryQuestionCandidateDraft,
  ) {
    if (!detail) return;
    const updated = await teacherWorkspace.updatePrivateLibraryQuestionCandidate(
      detail.library_item_id,
      candidate.candidate_id,
      draft,
    );
    replaceCandidate(updated);
  }

  async function mapCandidate(candidate: PrivateLibraryQuestionCandidate, nodeId: string) {
    if (!detail) return;
    const updated = await teacherWorkspace.mapPrivateLibraryQuestionCandidateCurriculum(
      detail.library_item_id,
      candidate.candidate_id,
      nodeId,
    );
    replaceCandidate(updated);
  }

  async function importCandidate(candidate: PrivateLibraryQuestionCandidate) {
    if (!detail) return;
    const result = await teacherWorkspace.importPrivateLibraryQuestionCandidate(
      detail.library_item_id,
      candidate.candidate_id,
    );
    replaceCandidate(result.candidate);
  }

  const fileUrl = detail
    ? `/api/v1/library/${encodeURIComponent(detail.library_item_id)}/file`
    : "";
  const reviewChanged = detail
    ? correctedText !== detail.corrected_text || reviewNote !== detail.review_note
    : false;
  const actionsBusy = Boolean(savingReview || ocrMode);
  const recognitionPreview = privateLibraryRecognitionPreview(
    correctedText,
    ocrMode === "external",
    recognitionError,
  );

  return (
    <main className="library-workspace">
      <ResizableSplitPane
        ariaLabel="调整资料上传与资料详情区域宽度"
        className="library-workbench-split"
        defaultPrimaryPercent={40}
        disabled={uploading}
        state={formError || privateSearchError || loadError || detailError
          ? "error"
          : uploading || privateSearchBusy || loading || detailLoading || actionsBusy
            ? "loading"
            : announcement || detailMessage || candidateMessage
              ? "success"
              : "default"}
      >
      <div className="library-workbench-pane library-workbench-pane--upload">
        <section className="library-intro">
        <div>
          <h1>我的资料，<br />我的工作流。</h1>
          <p>上传讲义、试卷和题目图片。资料默认只保存在当前教师的私人工作区。</p>
        </div>
        <p className="privacy-promise"><LockIcon /><span>当前教师私人空间</span><small>不公开 · 不训练 · 不自动发布</small></p>
        </section>

        <form className="library-upload" onSubmit={upload} noValidate>
        <header>
          <div>
            <span>添加资料</span>
            <h2>把教学资料放进私人工作区。</h2>
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

          <label className="library-field library-field--statement">
            <span>来源说明 <small>可选</small></span>
            <textarea
              onChange={(event) => setRightsStatement(event.target.value)}
              placeholder="可填写资料来源，也可以留空。"
              rows={3}
              value={rightsStatement}
            />
          </label>
        </div>

        <footer className="library-upload__actions">
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
      </div>

      <div className="library-workbench-pane library-workbench-pane--results">
        <section className="library-private-search">
        <header>
          <div>
            <span>私人检索 Agent</span>
            <h2>从你确认过的资料里，找一段证据。</h2>
          </div>
          <p><LockIcon />只读 · 仅检索当前教师资料</p>
        </header>
        <form onSubmit={searchPrivateContent}>
          <label>
            <span>要找什么</span>
            <div className="library-private-search__input">
              <SearchIcon />
              <input
                maxLength={500}
                onChange={(event) => { setPrivateQuery(event.target.value); setPrivateSearchError(""); }}
                placeholder="例如：函数单调性的课堂例题"
                value={privateQuery}
              />
              <button disabled={!privateQuery.trim() || privateSearchBusy} type="submit">
                {privateSearchBusy ? <span className="button-loader" /> : <ArrowRightIcon />}
                {privateSearchBusy ? "检索中" : "查找片段"}
              </button>
            </div>
          </label>
        </form>
        <div className="library-private-search__results" ref={privateSearchResultRef} aria-live="polite">
          {privateSearchError ? <p className="is-error" role="alert">{privateSearchError}</p> : null}
          {privateSearchTotal === 0 ? (
            <div className="library-private-search__empty"><SearchIcon /><span>没有找到已由你确认的匹配资料。待校对内容不会参与检索。</span></div>
          ) : null}
          {privateSearchTotal !== null && privateSearchTotal > 0 ? (
            <>
              <p className="library-private-search__count">找到 {privateSearchTotal} 份匹配资料；这里只展示最小必要片段。</p>
              <ol>
                {privateSearchItems.map((item) => (
                  <li key={item.library_item_id}>
                    <header><strong>{item.title}</strong><span><LockIcon />private</span></header>
                    <p>{item.excerpt}</p>
                    <footer><span>确认文本 v{item.source_version}</span><span>私人资料</span></footer>
                  </li>
                ))}
              </ol>
            </>
          ) : null}
        </div>
        </section>

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
                    <span><LockIcon />仅当前教师可见</span>
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
              <span>大模型识别与校对</span>
              <h2>{detail?.title || detail?.original_filename || "正在打开资料"}</h2>
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
              <div className="library-ocr-console">
                <div>
                  <p className="library-eyebrow">资料识别</p>
                  <h3>使用大模型整理原稿。</h3>
                  <p>识别完成后，右侧直接展示排版后的可读稿。</p>
                </div>
                <div className="library-ocr-actions">
                  <button
                    disabled={actionsBusy}
                    onClick={() => void runOCR()}
                    type="button"
                  >
                    {ocrMode === "external" ? <span className="button-loader" /> : <SparkIcon />}
                    {ocrMode === "external" ? "大模型识别中" : "使用大模型识别"}
                  </button>
                </div>
                {ocrProgress && <p className="library-ocr-progress" aria-live="polite"><ClockIcon />{ocrProgress}</p>}
              </div>

              <ResizableSplitPane
                ariaLabel="调整原稿与大模型整理稿宽度"
                className="library-review-comparison-split"
                defaultPrimaryPercent={50}
                maxPrimaryPercent={70}
                minPrimaryPercent={30}
                state={recognitionError ? "error" : ocrMode ? "loading" : recognitionPreview.kind === "content" ? "success" : "default"}
              >
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
                  <label className="library-editable-latex-draft">
                    <span>可编辑的中文 + LaTeX 校对稿</span>
                    <textarea
                      aria-label="可编辑的中文和 LaTeX 校对稿"
                      disabled={actionsBusy}
                      onChange={(event) => {
                        setCorrectedText(event.target.value);
                        setRecognitionError("");
                      }}
                      placeholder="大模型识别后可在这里继续修改中文、公式、题目与解析…"
                      spellCheck={false}
                      value={correctedText}
                    />
                  </label>
                </article>

                <article className="library-editor">
                  <header><span>02</span><div><h3>大模型整理稿</h3><p>中文与数学公式已排版，可直接阅读。</p></div></header>
                  <div className="library-readable-review" data-state={recognitionPreview.kind} aria-label="大模型识别整理后的可读校对稿">
                    {recognitionPreview.kind === "content"
                      ? <MathText text={recognitionPreview.text} />
                      : <p className="library-readable-review__state" role={recognitionPreview.kind === "error" ? "alert" : "status"}>
                          {recognitionPreview.text}
                        </p>}
                  </div>
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
              </ResizableSplitPane>

              {(detailError || detailMessage) && (
                <p className={`library-detail-message${detailError ? " is-error" : ""}`} role={detailError ? "alert" : "status"}>
                  {detailError || detailMessage}
                </p>
              )}

              <section className="library-candidates">
                <header>
                  <div><span>03</span><div><h3>拆题与教材映射</h3><p>只从你确认过的文本生成；每道题仍需逐项核对。</p></div></div>
                  <p><LockIcon />导入后仍为 private</p>
                </header>

                {detail.text_review_status !== "confirmed" ? (
                  <div className="candidate-gate">
                    <ClockIcon />
                    <div><strong>先确认当前文本</strong><p>待校对文本不会进入拆题流程，OCR 草稿也不能绕过教师确认。</p></div>
                    <button disabled type="button">等待教师确认</button>
                  </div>
                ) : candidatesLoading ? (
                  <div className="candidate-gate"><span className="button-loader" /><p>{detail.file_kind === "pdf" ? "大模型正在从确认文本中逐题提取并整理数学格式…" : "正在读取当前文本版本的候选题…"}</p></div>
                ) : candidates.length === 0 ? (
                  <div className="candidate-gate candidate-gate--ready">
                    <SparkIcon />
                    <div>
                      <strong>文本 v{detail.version} 已确认，可以开始拆题</strong>
                      <p>{reviewChanged
                        ? "校对区还有未保存修改，请先确认或撤回修改。"
                        : detail.file_kind === "pdf"
                          ? "大模型将提取题干、选项、答案与解析，并生成可读数学题卡；不会自动写入题库。"
                          : "系统先按题号生成可编辑候选，不会自动写入任何题库。"}</p>
                    </div>
                    <button disabled={reviewChanged} onClick={() => void prepareCandidates()} type="button">
                      <PlusIcon />{detail.file_kind === "pdf" ? "大模型提取题目" : "生成拆题候选"}
                    </button>
                  </div>
                ) : (
                  <div className="candidate-list">
                    {candidates.map((candidate) => (
                      <CandidateEditor
                        candidate={candidate}
                        key={candidate.candidate_id}
                        onImport={() => importCandidate(candidate)}
                        onMap={(nodeId) => mapCandidate(candidate, nodeId)}
                        onSave={(draft) => saveCandidate(candidate, draft)}
                      />
                    ))}
                  </div>
                )}
                {candidateMessage && <p className="candidate-section-message" aria-live="polite">{candidateMessage}</p>}
              </section>

              <section className="library-revisions">
                <header><div><span>04</span><h3>修订记录</h3></div><p>{revisions.length ? `${revisions.length} 次变更` : "尚无变更"}</p></header>
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
      </div>
      </ResizableSplitPane>
    </main>
  );
}
