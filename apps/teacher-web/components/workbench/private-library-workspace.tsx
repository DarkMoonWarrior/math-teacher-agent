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
  LibraryRightsBasis,
  LibraryTextRevision,
  PrivateLibraryQuestionCandidate,
  PrivateLibraryQuestionCandidateDraft,
  PrivateLibrarySearchItem,
} from "@/lib/teacher-workspace/contracts";
import { TeacherWorkspaceError } from "@/lib/teacher-workspace/contracts";
import { teacherWorkspace } from "@/lib/teacher-workspace/http-adapter";
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
  const [rightsBasis, setRightsBasis] = useState<LibraryRightsBasis>("private_teaching_only");
  const [rightsStatement, setRightsStatement] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);
  const [touched, setTouched] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [formError, setFormError] = useState("");
  const [announcement, setAnnouncement] = useState("");
  const [privateQuery, setPrivateQuery] = useState("");
  const [privateSearchConsent, setPrivateSearchConsent] = useState(false);
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
  const [ocrMode, setOcrMode] = useState<"local" | "external" | "">("");
  const [ocrProgress, setOcrProgress] = useState("");
  const [externalConsent, setExternalConsent] = useState(false);
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
      return;
    }
    const controller = new AbortController();
    setDetailLoading(true);
    setCandidatesLoading(true);
    setDetailError("");
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

  async function searchPrivateContent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const query = privateQuery.trim();
    if (!query || privateSearchBusy) return;
    if (!privateSearchConsent) {
      setPrivateSearchError("请先确认本次检索授权。每次查询都需要重新确认。");
      return;
    }
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
      setPrivateSearchConsent(false);
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

  function replaceCandidate(updated: PrivateLibraryQuestionCandidate) {
    setCandidates((current) => current.map((candidate) => (
      candidate.candidate_id === updated.candidate_id ? updated : candidate
    )));
  }

  async function prepareCandidates() {
    if (!detail || detail.text_review_status !== "confirmed" || candidatesLoading) return;
    setCandidatesLoading(true);
    setCandidateMessage("");
    try {
      const result = await teacherWorkspace.preparePrivateLibraryQuestionCandidates(
        detail.library_item_id,
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

      <section className="library-private-search">
        <header>
          <div>
            <span>私人检索 Agent</span>
            <h2>从你确认过的资料里，找一段证据。</h2>
          </div>
          <p><LockIcon />只读 · 本次授权 · 有界片段</p>
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
          <label className="library-private-search__consent">
            <input
              checked={privateSearchConsent}
              onChange={(event) => setPrivateSearchConsent(event.target.checked)}
              type="checkbox"
            />
            <span>我同意仅为本次查询，将匹配标题、片段、来源版本与权利状态交给已配置的 Agent；不发送原文件、路径或整份正文。</span>
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
                    <footer><span>确认文本 v{item.source_version}</span><span>{rightsLabel(item.rights_basis)}</span></footer>
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
                  <div className="candidate-gate"><span className="button-loader" /><p>正在读取当前文本版本的候选题…</p></div>
                ) : candidates.length === 0 ? (
                  <div className="candidate-gate candidate-gate--ready">
                    <SparkIcon />
                    <div>
                      <strong>文本 v{detail.version} 已确认，可以开始拆题</strong>
                      <p>{reviewChanged ? "校对区还有未保存修改，请先确认或撤回修改。" : "系统先按题号生成可编辑候选，不会自动写入任何题库。"}</p>
                    </div>
                    <button disabled={reviewChanged} onClick={() => void prepareCandidates()} type="button">
                      <PlusIcon />生成拆题候选
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
    </main>
  );
}
