"use client";

import { type FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { MathText } from "@/components/math-text";
import {
  type GeneratedQuestionDraft,
  type PersonalAuthoringDraft,
  type QuestionAuthoringJob,
  type QuestionAuthoringStatementPreview,
  type PersonalQuestion,
  type PersonalQuestionCategory,
  type PersonalQuestionCollection,
  type CurriculumSearchItem,
  type QuestionDraftEditableContent,
  TeacherWorkspaceError,
} from "@/lib/teacher-workspace/contracts";
import { teacherWorkspace } from "@/lib/teacher-workspace/http-adapter";
import {
  ArrowLeftIcon,
  ArrowRightIcon,
  ClockIcon,
  LibraryIcon,
  LockIcon,
  PaperIcon,
  PlusIcon,
  SearchIcon,
  SparkIcon,
} from "./icons";
import { WorkbenchNoticeDialog } from "./workbench-notice-dialog";
import { MathSolutionView } from "./math-solution-view";
import { AuthoringGenerationStatus, type AuthoringGenerationStage } from "./authoring-generation-status";
import { AuthoringLivePreview } from "./authoring-live-preview";
import { ResizableSplitPane } from "./resizable-split-pane";

type WorkspaceSection = "compose" | "history" | "mine" | "trash";
type BusyAction = "loading" | "generating" | "revising" | "regenerating-solution" | "saving" | "managing" | null;

function editableContent(draft: GeneratedQuestionDraft): QuestionDraftEditableContent {
  const choiceQuestion = draft.question_type === "single_choice" || draft.question_type === "multiple_choice";
  return {
    question_type: draft.question_type,
    stem_plain: draft.stem_plain,
    stem_latex: draft.stem_latex,
    options: draft.options.map((option) => ({ ...option })),
    answer_value: choiceQuestion ? draft.answer_value : draft.final_answer,
    solution_method: draft.solution_method,
    solution_steps: [...draft.solution_steps],
    final_answer: draft.final_answer,
    authoring_intent: draft.authoring_intent,
    knowledge_points: [...draft.knowledge_points],
    assessed_methods: [...draft.assessed_methods],
    common_mistakes: [...draft.common_mistakes],
  };
}

function lines(value: string) {
  return value.split("\n").map((item) => item.trim()).filter(Boolean);
}

function parseOptions(value: string) {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line, index) => {
      const match = line.match(/^([A-Za-z0-9]+)[.、．:)）]\s*(.+)$/);
      return match
        ? { key: match[1].toUpperCase(), text: match[2].trim() }
        : { key: String.fromCharCode(65 + index), text: line };
    });
}

function isSolutionMissing(draft: Pick<GeneratedQuestionDraft, "solution_status" | "solution_issue">) {
  return draft.solution_status === "needs_teacher_verification"
    && Boolean(draft.solution_issue?.includes("解析未生成"));
}

function preservedDraftNotice(solutionMissing: boolean) {
  return solutionMissing
    ? "任务已停止；审核通过的题面已保留为未保存私有草稿，解析显示为“无”，可继续补充后保存。"
    : "任务已停止；后台已完成的完整题目已保留为未保存私有草稿，可继续编辑后保存。";
}

function errorMessage(cause: unknown) {
  if (cause instanceof TeacherWorkspaceError) return cause.message;
  if (cause instanceof DOMException && cause.name === "AbortError") return "本次操作已取消。";
  return "操作没有完成。请检查 FastAPI 与 Agent Service 后重试。";
}

function QuestionEditor({
  content,
  idPrefix,
  onChange,
}: {
  content: QuestionDraftEditableContent;
  idPrefix: string;
  onChange: (next: QuestionDraftEditableContent) => void;
}) {
  const choiceQuestion = content.question_type === "single_choice" || content.question_type === "multiple_choice";
  const patch = <K extends keyof QuestionDraftEditableContent>(key: K, value: QuestionDraftEditableContent[K]) => {
    onChange({ ...content, [key]: value });
  };

  return (
    <div className="authoring-editor">
      <label htmlFor={`${idPrefix}-type`}>
        <span>题型</span>
        <select id={`${idPrefix}-type`} value={content.question_type} onChange={(event) => patch("question_type", event.target.value as QuestionDraftEditableContent["question_type"])}>
          <option value="single_choice">单项选择题</option>
          <option value="multiple_choice">多项选择题</option>
          <option value="fill_blank">填空题</option>
          <option value="open_response">解答题</option>
        </select>
      </label>
      <label className="authoring-editor__wide" htmlFor={`${idPrefix}-stem`}>
        <span>可读题面</span>
        <textarea id={`${idPrefix}-stem`} rows={6} value={content.stem_plain} onChange={(event) => patch("stem_plain", event.target.value)} />
      </label>
      <label className="authoring-editor__wide" htmlFor={`${idPrefix}-latex`}>
        <span>LaTeX 题面（可留空）</span>
        <textarea id={`${idPrefix}-latex`} rows={3} value={content.stem_latex ?? ""} onChange={(event) => patch("stem_latex", event.target.value || null)} />
      </label>
      {choiceQuestion && (
        <label className="authoring-editor__wide" htmlFor={`${idPrefix}-options`}>
          <span>选项 · 每行一项，例如 A. 2</span>
          <textarea id={`${idPrefix}-options`} rows={5} value={content.options.map((option) => `${option.key}. ${option.text}`).join("\n")} onChange={(event) => patch("options", parseOptions(event.target.value))} />
        </label>
      )}
      <label className="authoring-editor__wide" htmlFor={`${idPrefix}-final`}>
        <span>最终答案</span>
        <textarea
          id={`${idPrefix}-final`}
          rows={3}
          value={choiceQuestion ? content.answer_value : content.final_answer}
          onChange={(event) => {
            const value = event.target.value;
            onChange({
              ...content,
              answer_value: value,
              final_answer: value,
            });
          }}
        />
      </label>
      <label htmlFor={`${idPrefix}-method`}>
        <span>解题方法</span>
        <input id={`${idPrefix}-method`} value={content.solution_method} onChange={(event) => patch("solution_method", event.target.value)} />
      </label>
      <label htmlFor={`${idPrefix}-intent`}>
        <span>命题意图</span>
        <input id={`${idPrefix}-intent`} value={content.authoring_intent} onChange={(event) => patch("authoring_intent", event.target.value)} />
      </label>
      <label className="authoring-editor__wide" htmlFor={`${idPrefix}-steps`}>
        <span>解析步骤 · 每行一步</span>
        <textarea id={`${idPrefix}-steps`} rows={7} value={content.solution_steps.join("\n")} onChange={(event) => patch("solution_steps", event.target.value.split("\n").map((line) => line.trim()).filter(Boolean))} />
      </label>
      <details className="authoring-editor__wide authoring-pedagogy-editor">
        <summary>校订 Agent 归纳的教学信息</summary>
        <div>
          <label htmlFor={`${idPrefix}-knowledge-points`}>
            <span>细分知识点 · 每行一项</span>
            <textarea id={`${idPrefix}-knowledge-points`} rows={4} value={content.knowledge_points.join("\n")} onChange={(event) => patch("knowledge_points", lines(event.target.value))} />
          </label>
          <label htmlFor={`${idPrefix}-assessed-methods`}>
            <span>考查方法 · 每行一项</span>
            <textarea id={`${idPrefix}-assessed-methods`} rows={4} value={content.assessed_methods.join("\n")} onChange={(event) => patch("assessed_methods", lines(event.target.value))} />
          </label>
          <label htmlFor={`${idPrefix}-common-mistakes`}>
            <span>常见易错点 · 每行一项</span>
            <textarea id={`${idPrefix}-common-mistakes`} rows={4} value={content.common_mistakes.join("\n")} onChange={(event) => patch("common_mistakes", lines(event.target.value))} />
          </label>
        </div>
      </details>
    </div>
  );
}

export function PersonalQuestionAuthoringWorkspace({
  initialBrief,
}: {
  initialBrief: string;
}) {
  const [section, setSection] = useState<WorkspaceSection>("compose");
  const [requestText, setRequestText] = useState(initialBrief);
  const [grade, setGrade] = useState<"" | "高一" | "高二" | "高三">("");
  const [questionType, setQuestionType] = useState<QuestionDraftEditableContent["question_type"]>("open_response");
  const [difficulty, setDifficulty] = useState(3);
  const [teachingPurpose, setTeachingPurpose] = useState("课堂练习");
  const [expectedMinutes, setExpectedMinutes] = useState("");
  const [constraints, setConstraints] = useState("");
  const [curriculumQuery, setCurriculumQuery] = useState("");
  const [curriculumMatches, setCurriculumMatches] = useState<CurriculumSearchItem[]>([]);
  const [curriculumBusy, setCurriculumBusy] = useState(false);
  const [draftView, setDraftView] = useState<PersonalAuthoringDraft | null>(null);
  const [history, setHistory] = useState<PersonalAuthoringDraft[]>([]);
  const [authoringJob, setAuthoringJob] = useState<QuestionAuthoringJob | null>(null);
  const [historyDeleteTarget, setHistoryDeleteTarget] = useState<PersonalAuthoringDraft | null>(null);
  const [draftEditor, setDraftEditor] = useState<QuestionDraftEditableContent | null>(null);
  const [editSummary, setEditSummary] = useState("教师校订题面与解析");
  const [saveName, setSaveName] = useState("");
  const [collections, setCollections] = useState<PersonalQuestionCollection[]>([]);
  const [collectionId, setCollectionId] = useState("");
  const [categories, setCategories] = useState<PersonalQuestionCategory[]>([]);
  const [categoryId, setCategoryId] = useState("");
  const [newCollectionName, setNewCollectionName] = useState("");
  const [newCategoryName, setNewCategoryName] = useState("");
  const [questions, setQuestions] = useState<PersonalQuestion[]>([]);
  const [filter, setFilter] = useState("");
  const [selectedQuestion, setSelectedQuestion] = useState<PersonalQuestion | null>(null);
  const [savedEditor, setSavedEditor] = useState<QuestionDraftEditableContent | null>(null);
  const [manageName, setManageName] = useState("");
  const [manageTags, setManageTags] = useState("");
  const [manageCollectionId, setManageCollectionId] = useState("");
  const [manageCategories, setManageCategories] = useState<PersonalQuestionCategory[]>([]);
  const [manageCategoryId, setManageCategoryId] = useState("");
  const [deleteConfirmation, setDeleteConfirmation] = useState("");
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [lastTrashed, setLastTrashed] = useState<PersonalQuestion | null>(null);
  const [busy, setBusy] = useState<BusyAction>("loading");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [generationStage, setGenerationStage] = useState<AuthoringGenerationStage>("brief");
  const [generationElapsed, setGenerationElapsed] = useState(0);
  const [statementPreview, setStatementPreview] = useState<QuestionAuthoringStatementPreview | null>(null);
  const [statementRevision, setStatementRevision] = useState(0);
  const [statementState, setStatementState] = useState<"pending" | "approved" | "adjusting">("pending");
  const [previewMode, setPreviewMode] = useState<"active" | "preserved" | null>(null);
  const [stopDialogOpen, setStopDialogOpen] = useState(false);
  const feedbackReturnFocusRef = useRef<HTMLElement | null>(null);
  const stopDialogRef = useRef<HTMLElement | null>(null);
  const generationStartedAtRef = useRef(0);
  const sessionRef = useRef(`authoring_${Date.now().toString(36)}`);

  const draft = draftView?.current.draft ?? null;
  const canGenerate = requestText.trim().length >= 5 && busy === null;
  const canSave = Boolean(draftView && !draftView.saved && saveName.trim() && collectionId && categoryId && busy === null);
  const activeCount = section === "mine" ? questions.length : 0;

  async function loadCollections(signal?: AbortSignal) {
    const response = await teacherWorkspace.listPersonalQuestionCollections(signal);
    setCollections(response.items);
    setCollectionId((current) => current || response.items[0]?.collection_id || "");
    return response.items;
  }

  async function loadQuestions(nextSection: "mine" | "trash", query = filter, signal?: AbortSignal) {
    const response = await teacherWorkspace.listPersonalQuestions({
      query,
      lifecycleState: nextSection === "trash" ? "trashed" : "active",
    }, signal);
    setQuestions(response.items);
    return response.items;
  }

  async function loadHistory(signal?: AbortSignal) {
    const response = await teacherWorkspace.listPersonalAuthoringDrafts(signal);
    setHistory(response.items);
    return response.items;
  }

  function presentDraft(staged: PersonalAuthoringDraft, navigate = true) {
    setDraftView(staged);
    setDraftEditor(editableContent(staged.current.draft));
    setSaveName(`${staged.current.draft.curriculum?.name ?? "待确认知识点"} · 自主命题`);
    setCurriculumQuery(staged.current.draft.curriculum?.name ?? "");
    setCurriculumMatches([]);
    if (navigate) setSection("compose");
  }

  function clearLivePreview() {
    setStatementPreview(null);
    setStatementRevision(0);
    setStatementState("pending");
    setPreviewMode(null);
  }

  useEffect(() => {
    if (!stopDialogOpen) return;
    const frame = window.requestAnimationFrame(() => {
      // The dialog is fixed so it is immediately visible; scrolling and
      // focusing the panel also handles browsers that preserve a deep page
      // scroll position when the stop action is triggered.
      stopDialogRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
      stopDialogRef.current?.focus({ preventScroll: true });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [stopDialogOpen]);

  useEffect(() => {
    const controller = new AbortController();
    let resumedGeneration = false;
    void (async () => {
      try {
        const [, , latest, historyItems] = await Promise.all([
          loadCollections(controller.signal),
          loadQuestions("mine", "", controller.signal),
          teacherWorkspace.getLatestQuestionAuthoringJob(controller.signal),
          loadHistory(controller.signal),
        ]);
        if (latest && (latest.status === "queued" || latest.status === "running")) {
          resumedGeneration = true;
          setAuthoringJob(latest);
          generationStartedAtRef.current = Date.parse(latest.created_at);
          setPreviewMode("active");
          setBusy("generating");
          const progress = await teacherWorkspace.getQuestionAuthoringProgress(
            latest.subject_id,
            controller.signal,
          ).catch(() => null);
          if (progress) {
            setGenerationStage(progress.stage);
            setStatementPreview(progress.statement);
            setStatementRevision(progress.statement_revision);
            setStatementState(progress.statement_state);
          }
        } else if (latest?.status === "succeeded" && latest.result.draft_id) {
          const completed = historyItems.find((item) => item.draft_id === latest.result.draft_id);
          if (completed) presentDraft(completed, false);
        } else if (latest?.status === "cancelled" && latest.result.statement_preserved && latest.result.statement) {
          if (latest.result.draft_id) {
            const preservedDraft = historyItems.find((item) => item.draft_id === latest.result.draft_id)
              ?? await teacherWorkspace.getPersonalAuthoringDraft(latest.result.draft_id, controller.signal).catch(() => null);
            if (preservedDraft) {
              presentDraft(preservedDraft, false);
              setNotice(preservedDraftNotice(isSolutionMissing(preservedDraft.current.draft)));
            }
          } else {
            setAuthoringJob(latest);
            setStatementPreview(latest.result.statement);
            setStatementRevision(latest.result.statement_revision ?? 1);
            setStatementState("approved");
            setPreviewMode("preserved");
          }
        }
      } catch (cause) {
        if (!controller.signal.aborted) setError(errorMessage(cause));
      } finally {
        if (!controller.signal.aborted && !resumedGeneration) setBusy(null);
      }
    })();
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!authoringJob || (authoringJob.status !== "queued" && authoringJob.status !== "running")) return;
    setBusy("generating");
    const controller = new AbortController();
    let stopped = false;
    const poll = async () => {
      try {
        const [job, progress] = await Promise.all([
          teacherWorkspace.getQuestionAuthoringJob(authoringJob.job_id, controller.signal),
          teacherWorkspace.getQuestionAuthoringProgress(authoringJob.subject_id, controller.signal).catch(() => null),
        ]);
        if (stopped) return;
        setAuthoringJob(job);
        if (progress) {
          setGenerationStage(progress.stage);
          setStatementPreview(progress.statement);
          setStatementRevision(progress.statement_revision);
          setStatementState(progress.statement_state);
          setPreviewMode("active");
        }
        if (job.status === "succeeded" && job.result.draft_id) {
          const staged = await teacherWorkspace.getPersonalAuthoringDraft(job.result.draft_id, controller.signal);
          if (stopped) return;
          presentDraft(staged, false);
          await loadHistory(controller.signal);
          setNotice("已生成完整题目：题面、解析与解析所得标准答案已通过闭环一致性审核。");
          setStatementPreview(null);
          setStatementRevision(0);
          setStatementState("pending");
          setPreviewMode(null);
          setAuthoringJob(null);
          setBusy(null);
        } else if (job.status === "failed") {
          setError(job.error || "命题内容超出高中数学范围。");
          setStatementPreview(null);
          setStatementRevision(0);
          setStatementState("pending");
          setPreviewMode(null);
          setAuthoringJob(null);
          setBusy(null);
        } else if (job.status === "cancelled") {
          if (job.result.statement_preserved && job.result.statement) {
            if (job.result.draft_id) {
              const preservedDraft = await teacherWorkspace.getPersonalAuthoringDraft(job.result.draft_id, controller.signal).catch(() => null);
              if (stopped) return;
              if (preservedDraft) {
                presentDraft(preservedDraft, false);
                clearLivePreview();
                setNotice(preservedDraftNotice(isSolutionMissing(preservedDraft.current.draft)));
              }
            } else {
              setStatementPreview(job.result.statement);
              setStatementRevision(job.result.statement_revision ?? 1);
              setStatementState("approved");
              setPreviewMode("preserved");
              setNotice("任务已停止；审核通过的题面已保留，当前没有解析和标准答案。");
            }
          } else {
            setStatementPreview(null);
            setStatementRevision(0);
            setStatementState("pending");
            setPreviewMode(null);
            setAuthoringJob(null);
            setNotice("本次命题已停止，未保留题面。");
          }
          setBusy(null);
        }
      } catch (cause) {
        if (!controller.signal.aborted) setError(errorMessage(cause));
      }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 800);
    return () => { stopped = true; controller.abort(); window.clearInterval(timer); };
  }, [authoringJob?.job_id, authoringJob?.status]);

  useEffect(() => {
    if (!collectionId) {
      setCategories([]);
      setCategoryId("");
      return;
    }
    const controller = new AbortController();
    void teacherWorkspace.listPersonalQuestionCategories(collectionId, controller.signal)
      .then((response) => {
        setCategories(response.items);
        setCategoryId((current) => response.items.some((item) => item.category_id === current) ? current : response.items[0]?.category_id || "");
      })
      .catch((cause) => {
        if (!controller.signal.aborted) setError(errorMessage(cause));
      });
    return () => controller.abort();
  }, [collectionId]);

  useEffect(() => {
    if (!manageCollectionId) {
      setManageCategories([]);
      setManageCategoryId("");
      return;
    }
    const controller = new AbortController();
    void teacherWorkspace.listPersonalQuestionCategories(manageCollectionId, controller.signal)
      .then((response) => {
        setManageCategories(response.items);
        setManageCategoryId((current) => response.items.some((item) => item.category_id === current) ? current : response.items[0]?.category_id || "");
      })
      .catch((cause) => {
        if (!controller.signal.aborted) setError(errorMessage(cause));
      });
    return () => controller.abort();
  }, [manageCollectionId]);

  useEffect(() => {
    if (!initialBrief) return;
    setRequestText(initialBrief);
  }, [initialBrief]);

  useEffect(() => {
    if (busy !== "generating") return;
    const updateElapsed = () => {
      setGenerationElapsed(Math.floor((Date.now() - generationStartedAtRef.current) / 1000));
    };
    updateElapsed();
    const timer = window.setInterval(updateElapsed, 1000);
    return () => window.clearInterval(timer);
  }, [busy]);

  const selectedTrust = useMemo(() => selectedQuestion?.question.verification, [selectedQuestion]);

  function clearFeedback() {
    if (document.activeElement instanceof HTMLElement && !document.activeElement.closest(".workbench-notice-dialog")) {
      feedbackReturnFocusRef.current = document.activeElement;
    }
    setError("");
    setNotice("");
  }

  function dismissFeedback() {
    setError("");
    setNotice("");
    setLastTrashed(null);
  }

  async function generateDraft(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canGenerate) return;
    clearFeedback();
    generationStartedAtRef.current = Date.now();
    setGenerationElapsed(0);
    setGenerationStage("brief");
    setStatementPreview(null);
    setStatementRevision(0);
    setStatementState("pending");
    setPreviewMode("active");
    setStopDialogOpen(false);
    setDraftView(null);
    setDraftEditor(null);
    setBusy("generating");
    try {
      const job = await teacherWorkspace.startQuestionAuthoringJob({
        requestText: requestText.trim(),
        grade: grade || undefined,
        questionType,
        targetDifficulty: difficulty,
        teachingPurpose: teachingPurpose.trim() || "课堂练习",
        expectedMinutes: expectedMinutes ? Number(expectedMinutes) : undefined,
        additionalConstraints: constraints.trim(),
        sessionId: sessionRef.current,
      });
      setAuthoringJob(job);
    } catch (cause) {
      setError(errorMessage(cause));
      setBusy(null);
    }
  }

  async function cancelGeneration(preserveStatement: boolean) {
    if (!authoringJob || busy !== "generating") return;
    clearFeedback();
    setStopDialogOpen(false);
    try {
      const cancelled = await teacherWorkspace.cancelQuestionAuthoringJob(
        authoringJob.job_id,
        preserveStatement,
        undefined,
        { requestText: requestText.trim(), targetDifficulty: difficulty },
      );
      if (cancelled.status === "succeeded" && cancelled.result.draft_id) {
        // The worker may finish in the same instant as the stop request. Treat
        // that race as a completed result instead of leaving the progress UI
        // spinning with no visible draft.
        setBusy(null);
        const staged = await teacherWorkspace.getPersonalAuthoringDraft(cancelled.result.draft_id);
        presentDraft(staged, false);
        clearLivePreview();
        await loadHistory();
        setAuthoringJob(null);
        setNotice("题面、解析与解析所得标准答案已完成审核，已保留为未保存私有草稿。 ");
      } else if (cancelled.status === "cancelled") {
        setBusy(null);
        if (cancelled.result.statement_preserved && cancelled.result.statement) {
          setAuthoringJob(cancelled);
          if (cancelled.result.draft_id) {
            const preservedDraft = await teacherWorkspace.getPersonalAuthoringDraft(cancelled.result.draft_id);
            presentDraft(preservedDraft, false);
            clearLivePreview();
            setNotice(preservedDraftNotice(isSolutionMissing(preservedDraft.current.draft)));
          } else {
            setStatementPreview(cancelled.result.statement);
            setStatementRevision(cancelled.result.statement_revision ?? 1);
            setStatementState("approved");
            setPreviewMode("preserved");
            setNotice("任务已停止；审核通过的题面已保留，当前没有解析和标准答案。");
          }
        } else {
          setAuthoringJob(null);
          clearLivePreview();
          setNotice(statementPreview && preserveStatement
            ? "任务已停止，但停止时没有可恢复的审核通过题面。"
            : "本次命题已停止，未保留题面。");
        }
      } else if (cancelled.status === "failed") {
        setAuthoringJob(null);
        setBusy(null);
        setError(cancelled.error || "后台命题未能完成。请重新发起命题。 ");
      } else {
        setAuthoringJob(cancelled);
      }
    } catch (cause) {
      setError(errorMessage(cause));
    }
  }

  async function discardPreservedStatement() {
    if (!authoringJob || authoringJob.status !== "cancelled") return;
    clearFeedback();
    try {
      const discarded = await teacherWorkspace.cancelQuestionAuthoringJob(
        authoringJob.job_id,
        false,
      );
      setAuthoringJob(discarded);
      setStatementPreview(null);
      setStatementRevision(0);
      setStatementState("pending");
      setPreviewMode(null);
      setNotice("已放弃这份无解析题面。");
    } catch (cause) {
      setError(errorMessage(cause));
    }
  }

  async function openLastResult() {
    clearFeedback();
    const items = history.length ? history : await loadHistory();
    if (!items[0]) { setNotice("还没有上一次命题结果。"); return; }
    presentDraft(items[0]);
  }

  async function deleteHistoryItem(item: PersonalAuthoringDraft) {
    clearFeedback();
    setBusy("managing");
    try {
      const receipt = await teacherWorkspace.deletePersonalAuthoringHistory(item.draft_id);
      if (draftView?.draft_id === item.draft_id) {
        setDraftView(null); setDraftEditor(null);
      }
      await loadHistory();
      setNotice(receipt.saved_question_preserved ? "命题历史已删除；已保存的私题仍保留。" : "命题历史已删除。 ");
    } catch (cause) { setError(errorMessage(cause)); }
    finally { setBusy(null); setHistoryDeleteTarget(null); }
  }

  async function searchDraftCurriculum(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (curriculumQuery.trim().length < 2 || curriculumBusy) return;
    setCurriculumBusy(true);
    try {
      const result = await teacherWorkspace.searchCurriculum(curriculumQuery.trim());
      setCurriculumMatches(result.items);
      if (result.items.length === 0) setError("教材目录中没有找到匹配项，可以换一个更宽的关键词。");
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setCurriculumBusy(false);
    }
  }

  async function confirmDraftCurriculum(node: CurriculumSearchItem) {
    if (!draftView || !draftEditor || busy) return;
    clearFeedback();
    setBusy("revising");
    try {
      const revised = await teacherWorkspace.revisePersonalAuthoringDraft(
        draftView.draft_id,
        draftView.current_revision,
        { ...draftEditor, curriculum_confirmation_node_id: node.node_id },
        `教师确认教材映射：${node.name}`,
      );
      setDraftView(revised);
      setDraftEditor(editableContent(revised.current.draft));
      setCurriculumQuery(node.name);
      setCurriculumMatches([]);
      setNotice(`已确认教材映射“${node.name}”，并记录为 REV ${revised.current_revision}。`);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(null);
    }
  }

  async function reviseDraft(summary = editSummary) {
    if (!draftView || !draftEditor || busy) return;
    clearFeedback();
    setBusy("revising");
    try {
      const revised = await teacherWorkspace.revisePersonalAuthoringDraft(
        draftView.draft_id,
        draftView.current_revision,
        draftEditor,
        summary.trim() || "教师校订题面与解析",
      );
      setDraftView(revised);
      setDraftEditor(editableContent(revised.current.draft));
      setNotice(`已记录 REV ${revised.current_revision}，六项可信检查已重新执行。`);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(null);
    }
  }

  async function regenerateSolution() {
    if (!draftView || !draft || !draftEditor || busy) return;
    if (JSON.stringify(draftEditor) !== JSON.stringify(editableContent(draft))) {
      clearFeedback();
      setError("当前还有未记录的题面或解析修改。请先点击“记录校订并重检”，再重新生成解析，避免覆盖你的编辑。");
      return;
    }
    clearFeedback();
    setBusy("regenerating-solution");
    try {
      const regenerated = await teacherWorkspace.regeneratePersonalAuthoringSolution(
        draftView.draft_id,
        draftView.current_revision,
      );
      setDraftView(regenerated);
      setDraftEditor(editableContent(regenerated.current.draft));
      setNotice(
        regenerated.current.draft.solution_status === "needs_teacher_verification"
          ? `题面和选项保持不变；REV ${regenerated.current_revision} 的解析与新推导答案仍未通过一致性检查。`
          : `解析已重新生成并记录为 REV ${regenerated.current_revision}；题面和选项保持不变，新解析与标准答案已通过一致性审核。`,
      );
      window.requestAnimationFrame(() => document.querySelector<HTMLElement>(".authoring-draft__solution")?.scrollIntoView({ behavior: "smooth", block: "start" }));
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(null);
    }
  }

  async function createCollection() {
    if (!newCollectionName.trim() || busy) return;
    clearFeedback();
    setBusy("managing");
    try {
      const created = await teacherWorkspace.createPersonalQuestionCollection(newCollectionName.trim());
      await loadCollections();
      setCollectionId(created.collection_id);
      setNewCollectionName("");
      setNotice("个人题库已建立。下一步为它建立一个分类。 ");
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(null);
    }
  }

  async function createCategory() {
    if (!collectionId || !newCategoryName.trim() || busy) return;
    clearFeedback();
    setBusy("managing");
    try {
      const created = await teacherWorkspace.createPersonalQuestionCategory(collectionId, newCategoryName.trim());
      const response = await teacherWorkspace.listPersonalQuestionCategories(collectionId);
      setCategories(response.items);
      setCategoryId(created.category_id);
      setNewCategoryName("");
      setNotice("个人分类已建立，可以明确保存这份草稿。 ");
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(null);
    }
  }

  async function saveDraft() {
    if (!canSave || !draftView) return;
    clearFeedback();
    setBusy("saving");
    try {
      const saved = await teacherWorkspace.savePersonalAuthoringDraft(draftView.draft_id, {
        expectedRevision: draftView.current_revision,
        collectionId,
        categoryId,
        name: saveName.trim(),
      });
      setSelectedQuestion(saved);
      setSavedEditor(editableContent(saved.question));
      prepareQuestionManagement(saved);
      await loadQuestions("mine", "");
      setSection("mine");
      setNotice("已保存到你的私题库。它不会进入公共搜索、共享或模型训练。 ");
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(null);
    }
  }

  function prepareQuestionManagement(question: PersonalQuestion) {
    setManageName(question.name);
    setManageTags(question.tags.join("、"));
    setManageCollectionId(question.collection_id);
    setManageCategoryId(question.category_id);
    setDeleteConfirmation("");
    setDeleteDialogOpen(false);
  }

  function openQuestion(question: PersonalQuestion) {
    setSelectedQuestion(question);
    setSavedEditor(editableContent(question.question));
    prepareQuestionManagement(question);
    clearFeedback();
  }

  async function switchSection(next: WorkspaceSection) {
    setSection(next);
    setSelectedQuestion(null);
    clearFeedback();
    if (next === "history") {
      setBusy("loading");
      try { await loadHistory(); } catch (cause) { setError(errorMessage(cause)); }
      finally { setBusy(null); }
    } else if (next !== "compose") {
      setBusy("loading");
      try {
        await loadQuestions(next, next === "trash" ? "" : filter);
      } catch (cause) {
        setError(errorMessage(cause));
      } finally {
        setBusy(null);
      }
    }
  }

  async function filterQuestions(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy("loading");
    clearFeedback();
    try {
      await loadQuestions(section === "trash" ? "trash" : "mine", filter.trim());
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(null);
    }
  }

  async function saveQuestionMetadata() {
    if (!selectedQuestion || busy) return;
    clearFeedback();
    setBusy("managing");
    try {
      const move = manageCollectionId !== selectedQuestion.collection_id || manageCategoryId !== selectedQuestion.category_id;
      const updated = await teacherWorkspace.updatePersonalQuestion(selectedQuestion, {
        name: manageName.trim(),
        tags: manageTags.split(/[，,、]/).map((tag) => tag.trim()).filter(Boolean),
        collectionId: move ? manageCollectionId : undefined,
        categoryId: move ? manageCategoryId : undefined,
      });
      setSelectedQuestion(updated);
      prepareQuestionManagement(updated);
      await loadQuestions("mine", filter);
      setNotice("名称、分类与标签已更新。 ");
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(null);
    }
  }

  async function reviseSavedQuestion() {
    if (!selectedQuestion || !savedEditor || busy) return;
    clearFeedback();
    setBusy("revising");
    try {
      const revised = await teacherWorkspace.revisePersonalQuestion(selectedQuestion, savedEditor, "教师校订已保存私题");
      setSelectedQuestion(revised);
      setSavedEditor(editableContent(revised.question));
      await loadQuestions("mine", filter);
      setNotice(`已保存 REV ${revised.selected_revision}，可信检查已重新执行。`);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(null);
    }
  }

  async function copyQuestion() {
    if (!selectedQuestion || busy) return;
    clearFeedback();
    setBusy("managing");
    try {
      const copied = await teacherWorkspace.copyPersonalQuestion(selectedQuestion.question_id, {
        collectionId: selectedQuestion.collection_id,
        categoryId: selectedQuestion.category_id,
        name: `${selectedQuestion.name} · 副本`,
      });
      await loadQuestions("mine", filter);
      openQuestion(copied);
      setNotice("已建立独立副本；后续编辑与删除互不影响。 ");
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(null);
    }
  }

  async function exportQuestion(format: "json" | "markdown") {
    if (!selectedQuestion || busy) return;
    clearFeedback();
    setBusy("managing");
    try {
      const artifact = await teacherWorkspace.exportPersonalQuestion(selectedQuestion.question_id, format);
      const url = URL.createObjectURL(artifact.blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = artifact.filename;
      anchor.click();
      URL.revokeObjectURL(url);
      setNotice(`已准备${format === "json" ? " JSON" : " Markdown"} 私有导出。`);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(null);
    }
  }

  async function trashQuestion() {
    if (!selectedQuestion || busy) return;
    clearFeedback();
    setBusy("managing");
    try {
      const trashed = await teacherWorkspace.trashPersonalQuestion(selectedQuestion);
      setLastTrashed(trashed);
      setSelectedQuestion(null);
      await loadQuestions("mine", filter);
      setNotice("已移入回收站。你可以立即撤销。 ");
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(null);
    }
  }

  async function undoTrash() {
    if (!lastTrashed || busy) return;
    setBusy("managing");
    clearFeedback();
    try {
      await teacherWorkspace.restorePersonalQuestion(lastTrashed);
      setLastTrashed(null);
      await loadQuestions("mine", filter);
      setNotice("已恢复这道私题。 ");
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(null);
    }
  }

  async function restoreQuestion() {
    if (!selectedQuestion || busy) return;
    setBusy("managing");
    clearFeedback();
    try {
      await teacherWorkspace.restorePersonalQuestion(selectedQuestion);
      setSelectedQuestion(null);
      await loadQuestions("trash", filter);
      setNotice("已恢复到我的私题。 ");
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(null);
    }
  }

  async function permanentlyDeleteQuestion() {
    if (!selectedQuestion || deleteConfirmation !== "永久删除我的私题" || busy) return;
    setDeleteDialogOpen(false);
    setBusy("managing");
    clearFeedback();
    try {
      await teacherWorkspace.permanentlyDeletePersonalQuestion(selectedQuestion, "永久删除我的私题");
      setSelectedQuestion(null);
      setDeleteConfirmation("");
      await loadQuestions("trash", filter);
      setNotice("活动存储中的这道私题与其独占 revision 已永久删除。 ");
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(null);
    }
  }

  return (
    <main className="authoring-workspace">
      <header className="authoring-masthead">
        <div>
          <h1>命一道自己的题。</h1>
          <span>生成结果只进入当前教师的私有命题工作区；不会混入真实检索结果，也不会自动保存。</span>
        </div>
        <aside>
          <LockIcon />
          <strong>仅自己可见</strong>
          <span>无公开、共享、商用或训练路径</span>
        </aside>
      </header>

      <nav className="authoring-sections" aria-label="辅助命题工作区">
        <button aria-pressed={section === "compose"} type="button" onClick={() => void switchSection("compose")}><SparkIcon /> 命题书桌</button>
        <button type="button" onClick={() => void openLastResult()}><ClockIcon /> 上一次</button>
        <button aria-pressed={section === "history"} type="button" onClick={() => void switchSection("history")}><PaperIcon /> 命题历史 <span>{history.length || ""}</span></button>
        <button aria-pressed={section === "mine"} type="button" onClick={() => void switchSection("mine")}><LibraryIcon /> 我的私题 <span>{section === "mine" ? activeCount : ""}</span></button>
        <button aria-pressed={section === "trash"} type="button" onClick={() => void switchSection("trash")}><ClockIcon /> 回收站</button>
      </nav>

      <WorkbenchNoticeDialog
        actionLabel={!error && lastTrashed ? "撤销移入回收站" : undefined}
        message={error || notice}
        onAction={!error && lastTrashed ? () => void undoTrash() : undefined}
        onDismiss={dismissFeedback}
        open={Boolean(error || notice)}
        returnFocusRef={feedbackReturnFocusRef}
        title={error ? "操作没有完成" : "操作已完成"}
        tone={error ? "error" : "success"}
      />

      {stopDialogOpen && authoringJob && (
        <div className="authoring-stop-dialog__backdrop" role="presentation">
          <section
            aria-labelledby="authoring-stop-title"
            aria-modal="true"
            className="authoring-stop-dialog"
            ref={stopDialogRef}
            role="dialog"
            tabIndex={-1}
          >
            <span>停止命题任务</span>
            <h2 id="authoring-stop-title">要怎样处理当前题面？</h2>
            <p>
              {statementPreview && statementState === "approved"
                ? "当前题面已经通过审核。你可以停止解析并保留题面，也可以放弃本次结果。"
                : statementPreview
                  ? "当前展示的题面正在返修，尚不能作为审核通过的题面保留。"
                  : "题面尚未通过审核；现在停止只能放弃本次未完成结果。"}
            </p>
            <div>
              <button type="button" onClick={() => setStopDialogOpen(false)}>继续生成</button>
              <button
                disabled={!statementPreview || statementState !== "approved"}
                type="button"
                onClick={() => void cancelGeneration(true)}
              >
                停止并保留题面
              </button>
              <button className="is-danger" type="button" onClick={() => void cancelGeneration(false)}>
                停止并放弃题面
              </button>
            </div>
          </section>
        </div>
      )}

      {section === "compose" && (
        <ResizableSplitPane
          ariaLabel="调整命题要求与题目结果区域宽度"
          className="authoring-compose-split"
          defaultPrimaryPercent={40}
        >
          <section className="authoring-brief">
            <header><div><span>先写命题意图</span><h2>告诉我要出一道什么题</h2></div></header>
            <form onSubmit={generateDraft}>
              <label className="authoring-field authoring-field--wide" htmlFor="authoring-request">
                <span>命题要求</span>
                <textarea id="authoring-request" aria-required="true" rows={5} value={requestText} onChange={(event) => setRequestText(event.target.value)} placeholder="例如：命一道高二椭圆离心率单选题，中等难度，干扰项体现公式混淆" />
              </label>
              <label className="authoring-field" htmlFor="authoring-grade">
                <span>年级（可选）</span>
                <select id="authoring-grade" value={grade} onChange={(event) => setGrade(event.target.value as typeof grade)}><option value="">由要求判断</option><option>高一</option><option>高二</option><option>高三</option></select>
              </label>
              <label className="authoring-field" htmlFor="authoring-type">
                <span>题型</span>
                <select id="authoring-type" value={questionType} onChange={(event) => setQuestionType(event.target.value as typeof questionType)}><option value="single_choice">单项选择题</option><option value="multiple_choice">多项选择题</option><option value="fill_blank">填空题</option><option value="open_response">解答题</option></select>
              </label>
              <label className="authoring-field" htmlFor="authoring-difficulty">
                <span>目标难度 · {difficulty}/5</span>
                <input id="authoring-difficulty" max="5" min="1" type="range" value={difficulty} onChange={(event) => setDifficulty(Number(event.target.value))} />
              </label>
              <label className="authoring-field" htmlFor="authoring-purpose">
                <span>教学用途</span>
                <input id="authoring-purpose" value={teachingPurpose} onChange={(event) => setTeachingPurpose(event.target.value)} />
              </label>
              <label className="authoring-field" htmlFor="authoring-minutes">
                <span>预计用时（分钟，可选）</span>
                <input id="authoring-minutes" min="1" max="120" type="number" value={expectedMinutes} onChange={(event) => setExpectedMinutes(event.target.value)} />
              </label>
              <details className="authoring-advanced">
                <summary>补充必须遵守的限制（可选）</summary>
                <div>
                  <label htmlFor="authoring-constraints"><span>其他限制</span><textarea id="authoring-constraints" rows={3} value={constraints} onChange={(event) => setConstraints(event.target.value)} placeholder="例如：计算量控制在 10 分钟内；不要使用参数方程" /></label>
                </div>
              </details>
              <div className="authoring-submit">
                <button disabled={!canGenerate} type="submit"><span>{busy === "generating" ? "正在分阶段生成…" : "生成私有草稿"}</span><ArrowRightIcon /></button>
              </div>
              {busy === "generating" && <AuthoringGenerationStatus elapsedSeconds={generationElapsed} onCancel={authoringJob ? () => setStopDialogOpen(true) : undefined} stage={generationStage} />}
            </form>
          </section>

          {busy === "generating" || previewMode === "preserved" ? (
            <AuthoringLivePreview
              mode={previewMode === "preserved" ? "preserved" : "active"}
              onDiscard={previewMode === "preserved" ? () => void discardPreservedStatement() : undefined}
              revision={statementRevision}
              stage={generationStage}
              statement={statementPreview}
              statementState={statementState}
            />
          ) : draft && draftView && draftEditor ? (
            <section className="authoring-draft" id="authoring-draft">
              <header>
                <div><h2>已生成属于你的题目</h2></div>
                <div className="authoring-draft__policy"><LockIcon /><strong>仅自己可见</strong><small>命题 Agent 生成 · 尚未保存 · 需教师复核</small><small>{draft.curriculum?.name ?? "教材映射待补充"} · 预计难度 {draft.estimated_difficulty}/5</small></div>
              </header>
              <section className="authoring-inference" aria-label="Agent 归纳的命题信息">
                <header>
                  <div><h3>知识点、方法与易错点</h3></div>
                  <strong data-status={draft.curriculum?.mapping_status ?? "unmapped"}>{draft.curriculum?.mapping_status === "teacher_confirmed" ? "教师已确认" : draft.curriculum ? "待教师确认" : "尚未映射"}</strong>
                </header>
                <div className="authoring-inference__grid">
                  <article><span>教材知识点</span><strong>{draft.curriculum?.name ?? "Agent 未能可靠判断"}</strong><p>{draft.curriculum ? [draft.curriculum.volume, draft.curriculum.chapter, draft.curriculum.section].filter(Boolean).join(" · ") : "不阻断私人草稿生成，可在下方检索教材目录。"}</p></article>
                  <article><span>细分知识点</span><p>{draft.knowledge_points.join("、") || "待教师补充"}</p></article>
                  <article><span>考查方法</span><p>{draft.assessed_methods.join("、") || "待教师补充"}</p></article>
                  <article><span>常见易错点</span><p>{draft.common_mistakes.join("、") || "待教师补充"}</p></article>
                </div>
                {draft.curriculum?.mapping_status !== "teacher_confirmed" && (
                  <form className="authoring-curriculum-review" onSubmit={searchDraftCurriculum}>
                    <label htmlFor="authoring-curriculum-query"><span>确认或修正教材映射</span><input id="authoring-curriculum-query" value={curriculumQuery} onChange={(event) => setCurriculumQuery(event.target.value)} placeholder="搜索教材目录，例如：椭圆" /></label>
                    <button disabled={curriculumQuery.trim().length < 2 || curriculumBusy} type="submit">{curriculumBusy ? "正在查找…" : "查教材目录"}</button>
                    {curriculumMatches.length > 0 && <ol>{curriculumMatches.map((item) => <li key={item.node_id}><button type="button" onClick={() => void confirmDraftCurriculum(item)}><strong>{item.name}</strong><span>{[item.volume, item.chapter, item.section].filter(Boolean).join(" · ")}</span></button></li>)}</ol>}
                  </form>
                )}
              </section>
              <MathSolutionView
                className="authoring-draft__solution"
                finalAnswer={draftEditor.final_answer}
                method={draftEditor.solution_method}
                options={draftEditor.options}
                question={draftEditor.stem_latex || draftEditor.stem_plain}
                steps={draftEditor.solution_steps}
              />
              {draft.solution_status === "needs_teacher_verification" && (
                <section className="authoring-solution-warning" role="status">
                  <strong>题目、解析或标准答案需要你核验</strong>
                  <p>{draft.solution_issue || "解析未通过一致性检查。"}</p>
                  <p>你可以校订题面与解析，或重新生成解析；重新生成后标准答案会随新解析更新。</p>
                </section>
              )}
              <details className="personal-question-edit authoring-draft__editor">
                <summary>编辑题面、答案与解析</summary>
                <QuestionEditor content={draftEditor} idPrefix="draft" onChange={setDraftEditor} />
              </details>
              <div className="authoring-revision-actions">
                <label htmlFor="authoring-edit-summary"><span>本次修改说明</span><input id="authoring-edit-summary" value={editSummary} onChange={(event) => setEditSummary(event.target.value)} /></label>
                <button disabled={busy !== null} type="button" onClick={() => void reviseDraft()}>{busy === "revising" ? "正在重检…" : "记录校订并重检"}</button>
                <button className="is-secondary" disabled={busy !== null} type="button" onClick={() => void regenerateSolution()}>{busy === "regenerating-solution" ? "正在重新生成…" : "重新生成解析"}</button>
              </div>
              {draft.verification.status === "checks_failed" && <p className="personal-question-warning">这道题存在阻断检查，不能把它理解为数学正确或可直接用于正式试卷。</p>}
              <section className="authoring-save">
                <header><div><h3>选择你自己的题库与分类。</h3></div></header>
                <div className="authoring-save__grid">
                  <label htmlFor="authoring-save-name"><span>题目名称</span><input id="authoring-save-name" value={saveName} onChange={(event) => setSaveName(event.target.value)} /></label>
                  <label htmlFor="authoring-collection"><span>个人题库</span><select id="authoring-collection" value={collectionId} onChange={(event) => setCollectionId(event.target.value)}><option value="">请选择</option>{collections.map((item) => <option value={item.collection_id} key={item.collection_id}>{item.name}</option>)}</select></label>
                  <label htmlFor="authoring-category"><span>个人分类</span><select id="authoring-category" value={categoryId} onChange={(event) => setCategoryId(event.target.value)}><option value="">请选择</option>{categories.map((item) => <option value={item.category_id} key={item.category_id}>{item.name}</option>)}</select></label>
                </div>
                <div className="authoring-create-taxonomy">
                  <label htmlFor="new-collection"><span>新建题库</span><input id="new-collection" value={newCollectionName} onChange={(event) => setNewCollectionName(event.target.value)} placeholder="例如：高二课堂例题" /></label>
                  <button type="button" disabled={!newCollectionName.trim() || busy !== null} onClick={() => void createCollection()}><PlusIcon /> 建立题库</button>
                  <label htmlFor="new-category"><span>新建当前题库分类</span><input id="new-category" value={newCategoryName} onChange={(event) => setNewCategoryName(event.target.value)} placeholder="例如：圆锥曲线" /></label>
                  <button type="button" disabled={!collectionId || !newCategoryName.trim() || busy !== null} onClick={() => void createCategory()}><PlusIcon /> 建立分类</button>
                </div>
                <button className="authoring-save__button" type="button" disabled={!canSave} onClick={() => void saveDraft()}>{busy === "saving" ? "正在保存…" : "保存为我的私题"}<ArrowRightIcon /></button>
              </section>
            </section>
          ) : (
            <section className="authoring-draft-empty" aria-live="polite">
              <PaperIcon />
              <p>QUESTION AUTHORING · PRIVATE DRAFT</p>
              <h2>题目与解析会在这里展开。</h2>
              <span>请在左侧填写命题要求并生成私有草稿。</span>
            </section>
          )}
        </ResizableSplitPane>
      )}

      {section === "history" && (
        <section className="personal-question-shelf authoring-history">
          <header><div><span>命题历史</span><h2>返回任意一次完整命制结果。</h2></div></header>
          {history.length === 0 ? <p>还没有命题历史。</p> : (
            <ol className="authoring-history__list">{history.map((item) => (
              <li key={item.draft_id}>
                <div><strong>{item.current.draft.curriculum?.name ?? "自主命题"}</strong><p>{item.current.draft.stem_plain}</p><small>{new Date(item.updated_at).toLocaleString("zh-CN")} · {item.saved ? "已保存" : "未保存"}</small></div>
                <div><button type="button" onClick={() => presentDraft(item)}>打开</button><button className="is-danger" disabled={busy !== null} type="button" onClick={() => setHistoryDeleteTarget(item)}>删除</button></div>
              </li>
            ))}</ol>
          )}
        </section>
      )}

      {(section === "mine" || section === "trash") && (
        <section className="personal-question-shelf">
          <header>
            <div><span>{section === "trash" ? "回收站" : "我的私题"}</span><h2>{section === "trash" ? "只有你可以恢复或永久删除。" : "生成题与公共题库永久分离。"}</h2></div>
            <form onSubmit={filterQuestions}><label htmlFor="personal-question-filter"><SearchIcon /><span className="sr-only">搜索我的私题</span><input id="personal-question-filter" value={filter} onChange={(event) => setFilter(event.target.value)} placeholder="按名称、题面或标签搜索" /></label><button type="submit">筛选</button></form>
          </header>
          <div className="personal-question-shelf__layout">
            <aside className="personal-question-list" aria-live="polite">
              {busy === "loading" ? <p>正在读取你的私题…</p> : questions.length === 0 ? (
                <div className="personal-question-empty"><PaperIcon /><strong>{section === "trash" ? "回收站是空的" : "还没有保存私题"}</strong><span>{section === "trash" ? "移入回收站的题目会出现在这里。" : "回到命题书桌生成并明确保存第一道题。"}</span>{section === "mine" && <button type="button" onClick={() => void switchSection("compose")}>开始命题</button>}</div>
              ) : (
                <ol>{questions.map((question) => <li key={question.question_id}><button aria-pressed={selectedQuestion?.question_id === question.question_id} type="button" onClick={() => openQuestion(question)}><span>{question.name}</span><small className={isSolutionMissing(question.question) ? "personal-question-list__status is-missing" : "personal-question-list__status"}>{isSolutionMissing(question.question) ? "解析：无 · 题面已审核" : "解析：已生成"}</small><p>{question.question.stem_plain}</p></button></li>)}</ol>
              )}
            </aside>
            <article className="personal-question-detail">
              {!selectedQuestion || !savedEditor ? (
                <div className="personal-question-detail__empty"><ArrowLeftIcon /><strong>从左侧选择一道题</strong><span>题面、可信状态与 owner 管理动作会在这里展开。</span></div>
              ) : section === "trash" ? (
                <div className="personal-question-delete">
                  <span>TRASHED · REV {selectedQuestion.selected_revision}</span>
                  <h3>{selectedQuestion.name}</h3>
                  <MathText text={selectedQuestion.question.stem_plain} />
                  <div>
                    <button type="button" disabled={busy !== null} onClick={() => void restoreQuestion()}>恢复到我的私题</button>
                    <button className="is-danger" type="button" disabled={busy !== null} onClick={() => setDeleteDialogOpen(true)}>永久删除</button>
                  </div>
                </div>
              ) : (
                <>
                  <header><div><h3>{selectedQuestion.name}</h3><small>命题 Agent 生成 · 仅自己可见 · 需教师复核</small><small className={isSolutionMissing(selectedQuestion.question) ? "personal-question-list__status is-missing" : "personal-question-list__status"}>{isSolutionMissing(selectedQuestion.question) ? "解析：无 · 题面已审核，等待补充" : "解析：已生成"}</small></div><LockIcon /></header>
                  <div className="personal-question-meta">
                    <label htmlFor="manage-name"><span>名称</span><input id="manage-name" value={manageName} onChange={(event) => setManageName(event.target.value)} /></label>
                    <label htmlFor="manage-tags"><span>标签 · 用顿号或逗号分隔</span><input id="manage-tags" value={manageTags} onChange={(event) => setManageTags(event.target.value)} /></label>
                    <label htmlFor="manage-collection"><span>个人题库</span><select id="manage-collection" value={manageCollectionId} onChange={(event) => setManageCollectionId(event.target.value)}>{collections.map((item) => <option value={item.collection_id} key={item.collection_id}>{item.name}</option>)}</select></label>
                    <label htmlFor="manage-category"><span>个人分类</span><select id="manage-category" value={manageCategoryId} onChange={(event) => setManageCategoryId(event.target.value)}>{manageCategories.map((item) => <option value={item.category_id} key={item.category_id}>{item.name}</option>)}</select></label>
                    <button type="button" disabled={!manageName.trim() || !manageCategoryId || busy !== null} onClick={() => void saveQuestionMetadata()}>保存名称与分类</button>
                  </div>
                  <MathSolutionView
                    className="personal-question-detail__solution"
                    finalAnswer={savedEditor.final_answer}
                    method={savedEditor.solution_method}
                    options={savedEditor.options}
                    question={savedEditor.stem_latex || savedEditor.stem_plain}
                    steps={savedEditor.solution_steps}
                  />
                  <details className="personal-question-edit">
                    <summary>编辑题面、答案与解析</summary>
                    <QuestionEditor content={savedEditor} idPrefix="saved" onChange={setSavedEditor} />
                    <button type="button" disabled={busy !== null} onClick={() => void reviseSavedQuestion()}>{busy === "revising" ? "正在重检…" : "保存新 revision 并重检"}</button>
                  </details>
                  <footer>
                    <button type="button" disabled={busy !== null} onClick={() => void copyQuestion()}>建立独立副本</button>
                    <button type="button" disabled={busy !== null} onClick={() => void exportQuestion("markdown")}>导出 Markdown</button>
                    <button type="button" disabled={busy !== null} onClick={() => void exportQuestion("json")}>导出 JSON</button>
                    <button className="is-danger" type="button" disabled={busy !== null} onClick={() => void trashQuestion()}>移入回收站</button>
                  </footer>
                  {selectedTrust?.status === "checks_failed" && <p className="personal-question-warning">这道题存在阻断检查，不能把它理解为数学正确或可直接用于正式试卷。</p>}
                </>
              )}
            </article>
          </div>
        </section>
      )}
      <WorkbenchNoticeDialog
        actionLabel="删除历史"
        busy={busy === "managing" && Boolean(historyDeleteTarget)}
        closeLabel="保留"
        message={historyDeleteTarget?.saved ? "这条记录会从命题历史中移除；已经保存的私题仍会保留。" : "这会删除这次未保存的题面、答案、解析和全部修订记录。"}
        onAction={() => historyDeleteTarget && void deleteHistoryItem(historyDeleteTarget)}
        onDismiss={() => setHistoryDeleteTarget(null)}
        open={Boolean(historyDeleteTarget)}
        title="删除这条命题历史？"
        tone="danger"
      />
      <WorkbenchNoticeDialog
        actionDisabled={deleteConfirmation !== "永久删除我的私题"}
        actionLabel="永久删除"
        busy={busy === "managing" && deleteDialogOpen}
        closeLabel="保留这道题"
        message="这会删除活动存储中的题面、解析和这道题独占的全部 revision；独立副本不受影响。"
        onAction={() => void permanentlyDeleteQuestion()}
        onDismiss={() => {
          setDeleteDialogOpen(false);
          setDeleteConfirmation("");
        }}
        open={deleteDialogOpen && Boolean(selectedQuestion)}
        title="永久删除这道私题？"
        tone="danger"
      >
        <label className="workbench-notice-dialog__confirmation" htmlFor="permanent-delete-confirmation">
          <span>输入“永久删除我的私题”后才能继续</span>
          <input
            autoComplete="off"
            data-dialog-initial
            id="permanent-delete-confirmation"
            value={deleteConfirmation}
            onChange={(event) => setDeleteConfirmation(event.target.value)}
          />
        </label>
      </WorkbenchNoticeDialog>
    </main>
  );
}
