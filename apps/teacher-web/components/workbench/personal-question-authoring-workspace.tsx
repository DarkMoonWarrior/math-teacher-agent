"use client";

import { type FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { MathText } from "@/components/math-text";
import {
  type GeneratedQuestionDraft,
  type PersonalAuthoringDraft,
  type PersonalQuestion,
  type PersonalQuestionCategory,
  type PersonalQuestionCollection,
  type CurriculumSearchItem,
  type QuestionAuthoringEntrySource,
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

type WorkspaceSection = "compose" | "mine" | "trash";
type BusyAction = "loading" | "generating" | "revising" | "regenerating-solution" | "saving" | "managing" | null;

const ENTRY_COPY: Record<QuestionAuthoringEntrySource, string> = {
  new_task: "从新任务进入",
  search: "来自当前搜题条件",
  paper: "由组卷需求明确转入",
};

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
  entrySource,
  initialBrief,
  onExit,
}: {
  entrySource: QuestionAuthoringEntrySource;
  initialBrief: string;
  onExit: () => void;
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
  const feedbackReturnFocusRef = useRef<HTMLElement | null>(null);
  const generationStartedAtRef = useRef(0);
  const sessionRef = useRef(`authoring_${Date.now().toString(36)}`);
  const requestRef = useRef(0);

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

  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      try {
        await Promise.all([loadCollections(controller.signal), loadQuestions("mine", "", controller.signal)]);
      } catch (cause) {
        if (!controller.signal.aborted) setError(errorMessage(cause));
      } finally {
        if (!controller.signal.aborted) setBusy(null);
      }
    })();
    return () => controller.abort();
  }, []);

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
    const sequence = ++requestRef.current;
    clearFeedback();
    generationStartedAtRef.current = Date.now();
    setGenerationElapsed(0);
    setGenerationStage("brief");
    setBusy("generating");
    try {
      const response = await teacherWorkspace.createQuestionAuthoringDraft({
        requestText: requestText.trim(),
        grade: grade || undefined,
        questionType,
        targetDifficulty: difficulty,
        teachingPurpose: teachingPurpose.trim() || "课堂练习",
        expectedMinutes: expectedMinutes ? Number(expectedMinutes) : undefined,
        additionalConstraints: constraints.trim(),
        sessionId: sessionRef.current,
      }, {
        onProgress: setGenerationStage,
      });
      if (sequence !== requestRef.current || !response.draft) return;
      setGenerationStage("staging");
      const staged = await teacherWorkspace.getPersonalAuthoringDraft(response.draft.draft_id);
      if (sequence !== requestRef.current) return;
      setDraftView(staged);
      setDraftEditor(editableContent(staged.current.draft));
      setSaveName(`${staged.current.draft.curriculum?.name ?? "待确认知识点"} · 自主命题`);
      setCurriculumQuery(staged.current.draft.curriculum?.name ?? "");
      setCurriculumMatches([]);
      setNotice(
        staged.current.draft.solution_status === "needs_teacher_verification"
          ? "草稿未通过题面、解析与答案一致性检查，请先校订或重新生成解析。"
          : "草稿已生成，标准答案来自完整解析并已通过交叉审核；保存前仍请教师复核。",
      );
      window.requestAnimationFrame(() => document.querySelector<HTMLElement>("#authoring-draft")?.scrollIntoView({ behavior: "smooth", block: "start" }));
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      if (sequence === requestRef.current) setBusy(null);
    }
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
          : `解析已重新生成并记录为 REV ${regenerated.current_revision}；题面和选项保持不变，标准答案已按新解析更新。`,
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
    if (next !== "compose") {
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
          <button className="authoring-back" type="button" onClick={onExit}><ArrowLeftIcon /> 返回原任务</button>
          <p><SparkIcon /> Question Authoring Agent · {ENTRY_COPY[entrySource]}</p>
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

      {section === "compose" && (
        <>
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
              {busy === "generating" && <AuthoringGenerationStatus elapsedSeconds={generationElapsed} stage={generationStage} />}
            </form>
          </section>

          {draft && draftView && draftEditor && (
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
          )}
        </>
      )}

      {section !== "compose" && (
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
                <ol>{questions.map((question) => <li key={question.question_id}><button aria-pressed={selectedQuestion?.question_id === question.question_id} type="button" onClick={() => openQuestion(question)}><span>{question.name}</span><p>{question.question.stem_plain}</p></button></li>)}</ol>
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
                  <header><div><h3>{selectedQuestion.name}</h3><small>命题 Agent 生成 · 仅自己可见 · 需教师复核</small></div><LockIcon /></header>
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
