"use client";

import Image from "next/image";
import {
  type FormEvent,
  type KeyboardEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { MathText } from "@/components/math-text";
import {
  type BetaFactReceipt,
  type BetaTaskDecision,
  type SearchQuestion,
  type QuestionInputBundle,
  type QuestionAuthoringEntrySource,
  type SearchTaskProgressStage,
  type SearchTaskResult,
  type SolveTaskProgressStage,
  type SolveTaskResult,
  type ProductCapability,
  TeacherWorkspaceError,
} from "@/lib/teacher-workspace/contracts";
import { teacherWorkspace } from "@/lib/teacher-workspace/http-adapter";
import {
  difficultyLabel,
  ERROR_GUIDANCE,
  questionTypeLabel,
  solutionConfidenceLabel,
  sourceLabel,
  verificationLabel,
  verificationTone,
} from "@/lib/teacher-workspace/labels";
import {
  ArrowLeftIcon,
  ArrowRightIcon,
  ArrowUpIcon,
  BookIcon,
  CheckIcon,
  ClockIcon,
  CloseIcon,
  FormulaIcon,
  HistoryIcon,
  LibraryIcon,
  PaperIcon,
  PlusIcon,
  SearchIcon,
  SettingsIcon,
  SignOutIcon,
  SparkIcon,
} from "./icons";
import { SolvePaper, SolveResultBrief } from "./solve-paper";
import { PrivateLibraryWorkspace } from "./private-library-workspace";
import { QuestionMediaComposer } from "./question-media-composer";
import { PersonalQuestionAuthoringWorkspace } from "./personal-question-authoring-workspace";
import { PaperBlueprintWorkspace } from "./paper-blueprint-workspace";
import { LessonBlueprintWorkspace } from "./lesson-blueprint-workspace";
import { ResizableSplitPane } from "./resizable-split-pane";
import { TeacherMemoryPanel } from "./teacher-memory-panel";
import { BetaValidationPanel } from "./beta-validation-panel";
import {
  type BetaSessionContextValue,
  useBetaCapabilities,
  useBetaSession,
} from "./beta-access-gate";

type Phase = "idle" | "running" | "success" | "error" | "cancelled";
type FlipDirection = "next" | "previous";
type CapabilityId = "search" | "solve" | "library" | "lesson" | "paper";
type RunnableCapabilityId = "search" | "solve";
type PersistentWorkspaceId = "authoring" | "library" | "lesson" | "paper";
type TaskFeedbackState = {
  decision: BetaTaskDecision;
  state: BetaFactReceipt["state"];
};

const FEEDBACK_STATE_LABEL: Record<BetaFactReceipt["state"], string> = {
  recorded: "已记录；如果改选，将以最后一次选择为准。",
  disabled: "封闭测试数据采集未开启，本次选择没有写入统计。",
  not_participating: "你尚未加入封闭测试数据采集，本次选择没有写入统计。",
  unavailable: "统计服务暂时不可用，本次选择没有写入统计。",
  invalid: "本次选择不符合统计口径，因此没有写入统计。",
};

type SearchTaskRecord = {
  id: string;
  capability: "search";
  query: string;
  result: SearchTaskResult;
};

type SolveTaskRecord = {
  id: string;
  capability: "solve";
  query: string;
  result: SolveTaskResult;
};

type TaskRecord = SearchTaskRecord | SolveTaskRecord;

type ViewError = {
  code: string;
  message: string;
  requestId: string;
};

type SearchProgressDefinition = {
  stageTitle: string;
  paperTitle: string;
  activeStep: number;
};

type SolveProgressDefinition = {
  stageTitle: string;
  paperTitle: string;
  activeStep: number;
};

type PromptExample = {
  label: string;
  detail: string;
  query: string;
};

type PreviewPage = {
  index: string;
  eyebrow: string;
  title: string;
  body: string;
};

type CapabilityDefinition = {
  id: CapabilityId;
  label: string;
  ready: boolean;
  title: [string, string];
  intro: string;
  inputLabel: string;
  placeholder: string;
  actionLabel: string;
  stageLabel: string;
  stageTitle: string;
  examples: PromptExample[];
  pages: PreviewPage[];
};

const CAPABILITY_ORDER: CapabilityId[] = ["search", "solve", "library", "lesson", "paper"];
const WORKBENCH_NAV_ORDER: Array<CapabilityId | "authoring"> = ["search", "solve", "library", "authoring", "lesson", "paper"];

export function getWorkspaceVisibility(capability: CapabilityId, authoringActive: boolean) {
  return {
    authoring: authoringActive,
    lesson: !authoringActive && capability === "lesson",
    library: !authoringActive && capability === "library",
    paper: !authoringActive && capability === "paper",
    searchSolve: !authoringActive && (capability === "search" || capability === "solve"),
  };
}

const SEARCH_PROGRESS: Record<SearchTaskProgressStage, SearchProgressDefinition> = {
  connecting: {
    stageTitle: "正在建立可信连接",
    paperTitle: "正在连接受控搜索工作流",
    activeStep: 0,
  },
  understanding: {
    stageTitle: "正在理解教学条件",
    paperTitle: "正在把描述整理成可核对条件",
    activeStep: 0,
  },
  searching: {
    stageTitle: "正在查找真实题目",
    paperTitle: "正在通过受控工具翻查题库",
    activeStep: 1,
  },
  checking: {
    stageTitle: "正在核对可信状态",
    paperTitle: "正在核对来源、权利与验证状态",
    activeStep: 2,
  },
  recovering: {
    stageTitle: "正在恢复同一次任务",
    paperTitle: "连接中断，正在取回已保存的运行结果",
    activeStep: 3,
  },
};

const SEARCH_PROGRESS_STEPS = [
  "解析教学描述",
  "调用受控搜索工具",
  "核对来源与验证状态",
];

const SOLVE_PROGRESS: Record<SolveTaskProgressStage, SolveProgressDefinition> = {
  connecting: {
    stageTitle: "正在建立可信连接",
    paperTitle: "正在连接受控解题工作流",
    activeStep: 0,
  },
  understanding: {
    stageTitle: "正在理解题目条件",
    paperTitle: "正在核对题目与解题要求",
    activeStep: 0,
  },
  solving: {
    stageTitle: "正在形成结构化解析",
    paperTitle: "正在通过唯一受控工具解题",
    activeStep: 1,
  },
  verifying: {
    stageTitle: "正在核对数学证据",
    paperTitle: "正在确认验证范围与可信等级",
    activeStep: 2,
  },
  recovering: {
    stageTitle: "正在恢复同一次解题",
    paperTitle: "连接中断，正在取回已保存的解题结果",
    activeStep: 3,
  },
};

const SOLVE_PROGRESS_STEPS = [
  "理解题目条件",
  "调用受控解题工具",
  "核对验证范围与证据",
];

const CAPABILITIES: Record<CapabilityId, CapabilityDefinition> = {
  search: {
    id: "search",
    label: "搜题",
    ready: true,
    title: ["把要找的题，", "直接说出来。"],
    intro: "写下年级、知识点、难度、题量和课堂用途。它负责理解与查找，来源和验证状态会随结果一起返回。",
    inputLabel: "描述搜题需求",
    placeholder: "例如：找 5 道高二椭圆焦点弦题，中等偏难，用作课堂例题",
    actionLabel: "开始查找",
    stageLabel: "搜题工作方式",
    stageTitle: "从一句话，到可核对的题目",
    examples: [
      {
        label: "椭圆焦点弦",
        detail: "高二 · 中等偏难 · 5 道",
        query: "找 5 道高二椭圆焦点弦题，中等偏难，用作课堂例题",
      },
      {
        label: "函数奇偶性",
        detail: "基础 · 随堂练习 · 3 道",
        query: "找 3 道函数奇偶性判断题，基础难度，适合随堂练习",
      },
      {
        label: "导数与构造函数",
        detail: "江苏 · 解答题 · 近年",
        query: "找近年江苏地区导数解答题，优先构造函数方法",
      },
    ],
    pages: [
      {
        index: "01",
        eyebrow: "说出教学意图",
        title: "不用先学会筛选器。",
        body: "年级、知识点、难度、题量和课堂用途，都可以直接写成一句话。",
      },
      {
        index: "02",
        eyebrow: "形成检索意图",
        title: "把口语拆成可核对的条件。",
        body: "Agent 只理解任务和调用工具；题目仍来自受控业务服务。",
      },
      {
        index: "03",
        eyebrow: "返回可信记录",
        title: "来源与验证状态，和题目一起出现。",
        body: "没有满足条件的真实记录时，系统会明确告诉你，而不是临时编一道。",
      },
    ],
  },
  solve: {
    id: "solve",
    label: "解题",
    ready: true,
    title: ["把一道题，", "讲到可以上课。"],
    intro: "输入完整题目，系统优先查找已有可信解析；需要模型生成时会明确标记教师复核，并单独展示 MathVerifier 能力、范围和证据。",
    inputLabel: "输入完整数学题目",
    placeholder: "例如：已知函数 f(x)=x³-3x，求其单调区间与极值",
    actionLabel: "开始解题",
    stageLabel: "解题工作方式",
    stageTitle: "从题目，到分层可信解析",
    examples: [
      {
        label: "函数单调性",
        detail: "导数 · 极值 · 标准解析",
        query: "已知函数 f(x)=x³-3x，求其单调区间与极值。",
      },
      {
        label: "椭圆离心率",
        detail: "圆锥曲线 · 参数范围",
        query: "已知椭圆 x²/a²+y²/b²=1（a>b>0）的焦距为 2c，且 a=2c，求椭圆的离心率。",
      },
      {
        label: "数列求和",
        detail: "等差数列 · 前 n 项和",
        query: "等差数列 {aₙ} 中，a₁=3，公差 d=2，求前 n 项和 Sₙ。",
      },
    ],
    pages: [
      {
        index: "01",
        eyebrow: "提交完整题目",
        title: "先保留题目的全部条件。",
        body: "公式、定义域和问题目标共同进入受控解题工作流，不从一句残缺描述猜题。",
      },
      {
        index: "02",
        eyebrow: "形成结构化解析",
        title: "方法、步骤与答案分开呈现。",
        body: "解析通过业务模块生成；Agent 不能用自由文本替代受控 Tool 的结构化结果。",
      },
      {
        index: "03",
        eyebrow: "核对可信范围",
        title: "验证到哪里，就只说到哪里。",
        body: "程序验证、题库证据和模型新解使用不同标记；不支持验证时明确要求教师复核。",
      },
    ],
  },
  library: {
    id: "library",
    label: "资料库",
    ready: true,
    title: ["我的资料，", "我的工作流。"],
    intro: "上传 PDF、DOCX 和题目图片；来源、权利与私人边界会随资料一起保留。",
    inputLabel: "选择私人教学资料",
    placeholder: "选择 PDF、DOCX 或图片",
    actionLabel: "存入私人资料",
    stageLabel: "私人资料",
    stageTitle: "只属于当前教师的资料空间",
    examples: [],
    pages: [
      {
        index: "01",
        eyebrow: "私人资料",
        title: "文件与来源说明一起保存。",
        body: "私人内容不会自动进入公共题库或模型训练。",
      },
    ],
  },
  lesson: {
    id: "lesson",
    label: "教案",
    ready: true,
    title: ["把一节课，", "整理成可修改的教案。"],
    intro: "从课题、学情和课时出发，组织教学目标、重难点、课堂活动与板书。所有生成内容先是草案，由教师决定是否采用。",
    inputLabel: "描述教案需求",
    placeholder: "例如：为高二椭圆第一课时准备一份 45 分钟新授课教案",
    actionLabel: "整理教案蓝图",
    stageLabel: "教案蓝图规划",
    stageTitle: "从教学目标，到课堂节奏",
    examples: [
      {
        label: "椭圆第一课时",
        detail: "高二 · 新授课 · 45 分钟",
        query: "为高二椭圆第一课时准备一份 45 分钟新授课教案",
      },
      {
        label: "函数单调性复习",
        detail: "专题复习 · 讲练结合",
        query: "设计一节函数单调性专题复习课，包含诊断题与分层练习",
      },
      {
        label: "导数压轴讲评",
        detail: "试卷讲评 · 构造函数",
        query: "整理一节导数压轴题讲评课，重点突出构造函数方法",
      },
    ],
    pages: [
      {
        index: "01",
        eyebrow: "交代课堂条件",
        title: "先说明教谁、教什么、用多久。",
        body: "课题、年级、学情和课时共同决定教案的节奏，不使用万能模板。",
      },
      {
        index: "02",
        eyebrow: "形成教学骨架",
        title: "目标、活动与练习前后相扣。",
        body: "教学目标映射到课堂活动与问题链，避免目标写在一处、课堂走向另一处。",
      },
      {
        index: "03",
        eyebrow: "保留教师决定",
        title: "生成的是草案，不是自动发布的定稿。",
        body: "教师可以逐段修改、补充自己的素材，再决定导出或进入后续工作流。",
      },
    ],
  },
  paper: {
    id: "paper",
    label: "组卷",
    ready: true,
    title: ["把教学目标，", "排成一份有依据的试卷。"],
    intro: "先确定范围、题量、题型、难度和考试时间，再形成试卷草案与双向细目表。题目来源和验证状态不会被隐藏。",
    inputLabel: "描述组卷需求",
    placeholder: "例如：组一份高二期中卷，120 分钟，覆盖函数、导数与圆锥曲线",
    actionLabel: "整理组卷蓝图",
    stageLabel: "组卷蓝图",
    stageTitle: "从命题边界，到试卷草案",
    examples: [
      {
        label: "高二期中卷",
        detail: "120 分钟 · 函数至圆锥曲线",
        query: "组一份高二期中卷，120 分钟，覆盖函数、导数与圆锥曲线",
      },
      {
        label: "导数专题测验",
        detail: "60 分钟 · 中等偏难",
        query: "组一份 60 分钟导数专题测验，中等偏难，含 3 道解答题",
      },
      {
        label: "函数随堂练习",
        detail: "20 分钟 · 基础巩固",
        query: "组一份函数性质随堂练习，20 分钟，以基础巩固为主",
      },
    ],
    pages: [
      {
        index: "01",
        eyebrow: "设定命题边界",
        title: "先约束范围、题量、难度与时间。",
        body: "组卷从明确约束开始，不根据几句模糊描述直接拼出一张试卷。",
      },
      {
        index: "02",
        eyebrow: "形成细目结构",
        title: "知识点、题型和难度分布有据可查。",
        body: "试题草案与双向细目表同步形成，方便教师检查覆盖与梯度。",
      },
      {
        index: "03",
        eyebrow: "经过发布门禁",
        title: "AI 不能替教师直接发布。",
        body: "来源、权利和数学验证状态经过检查后，教师再确认定稿与导出。",
      },
    ],
  },
};

function createSessionId(): string {
  return `tch_${crypto.randomUUID().replaceAll("-", "")}`;
}

function querySummary(query: string): string {
  return query.length > 28 ? `${query.slice(0, 28)}…` : query;
}

function intentLabels(result: SearchTaskResult): string[] {
  const labels = [
    result.intent.grade,
    ...result.intent.knowledge_points,
    ...result.intent.question_types.map(questionTypeLabel),
    result.intent.difficulty === null ? null : difficultyLabel(result.intent.difficulty),
    ...result.intent.regions,
  ];
  return Array.from(new Set(labels.filter((value): value is string => Boolean(value))));
}

function CapabilityIcon({ id }: { id: CapabilityId }) {
  if (id === "solve") return <FormulaIcon />;
  if (id === "library") return <LibraryIcon />;
  if (id === "lesson") return <BookIcon />;
  if (id === "paper") return <PaperIcon />;
  return <SearchIcon />;
}

function QuestionPaper({
  item,
  index,
  onSolve,
  total,
}: {
  item: SearchQuestion;
  index: number;
  onSolve: (item: SearchQuestion) => void;
  total: number;
}) {
  return (
    <article className="question-paper">
      <header className="question-paper__head">
        <div>
          <span className="paper-kicker">题目 {String(index + 1).padStart(2, "0")}</span>
          <h2>{questionTypeLabel(item.question_type)}</h2>
        </div>
        <span className="paper-count">{index + 1} / {total}</span>
      </header>

      <div className="question-paper__stem">
        <MathText text={item.stem || item.stem_preview || "题干暂缺"} />
      </div>

      {item.knowledge_points.length > 0 && (
        <ul className="paper-tags" aria-label="知识点">
          {item.knowledge_points.map((point) => <li key={point}>{point}</li>)}
        </ul>
      )}

      <footer className="question-paper__foot">
        <span className={`trust-label trust-label--${verificationTone(item.verification_status)}`}>
          {verificationTone(item.verification_status) === "trusted" ? <CheckIcon /> : <ClockIcon />}
          {verificationLabel(item.verification_status)}
        </span>
        <span>{sourceLabel(item.source_status)}</span>
        <span>{difficultyLabel(item.difficulty)}</span>
        {item.year !== null && <span>{item.year} 年</span>}
        {item.region && <span>{item.region}</span>}
        <button className="solve-question-button" type="button" onClick={() => onSolve(item)}>
          解这道题 <ArrowRightIcon />
        </button>
      </footer>

      {item.relaxed_fields.length > 0 && (
        <p className="paper-note">相近条件补充 · 已放宽 {item.relaxed_fields.join("、")}</p>
      )}
    </article>
  );
}

function TaskFeedbackControl({
  busy,
  feedback,
  onDecision,
}: {
  busy: boolean;
  feedback: TaskFeedbackState | null;
  onDecision: (decision: BetaTaskDecision) => void;
}) {
  return (
    <section className="task-feedback" aria-label="评价本次结果">
      <div>
        <strong>这次结果是否有帮助？</strong>
        <span>只记录你的明确选择，不上传题目或解析内容。</span>
      </div>
      <div className="task-feedback__actions">
        <button
          aria-pressed={feedback?.decision === "accepted"}
          disabled={busy}
          onClick={() => onDecision("accepted")}
          type="button"
        >有帮助</button>
        <button
          aria-pressed={feedback?.decision === "rejected"}
          disabled={busy}
          onClick={() => onDecision("rejected")}
          type="button"
        >不合适</button>
      </div>
      {feedback && (
        <small role="status">
          {FEEDBACK_STATE_LABEL[feedback.state]}
        </small>
      )}
    </section>
  );
}

function PreviewPaper({ capability, page }: { capability: CapabilityId; page: number }) {
  const definition = CAPABILITIES[capability];
  const content = definition.pages[page];

  return (
    <article className={`preview-paper preview-paper--${capability} preview-paper--page-${page + 1}`}>
      <Image
        alt="由纸张、坐标网格和几何曲线组成的数学图谱"
        className="atlas-image"
        fill
        priority
        sizes="(max-width: 900px) 92vw, 78vw"
        src="/images/math-atlas.png"
      />
      <div className="atlas-wash" aria-hidden="true" />
      <span className={`capability-stamp${definition.ready ? " is-ready" : ""}`}>
        {definition.ready ? "运行时已接入" : "界面预览 · 待接入"}
      </span>
      <div className="preview-paper__copy">
        <span>{content.index} · {content.eyebrow}</span>
        <h2>{content.title}</h2>
        <p>{content.body}</p>
      </div>
      <div className="atlas-coordinate" aria-hidden="true">
        <span>x</span><i /><span>y</span>
      </div>
    </article>
  );
}

export function AccountSettingsPopover({
  error,
  onOpenBetaValidation,
  onOpenTeacherPreferences,
  onSignOut,
  session,
  teacherPreferencesAvailable,
}: {
  error: string;
  onOpenBetaValidation: () => void;
  onOpenTeacherPreferences: () => void;
  onSignOut: () => void;
  session: BetaSessionContextValue;
  teacherPreferencesAvailable: boolean;
}) {
  const avatarLabel = session.displayLabel.trim().slice(0, 1) || "教";
  const sessionLabel = session.mode === "production_identity"
    ? "个人教师账号"
    : session.mode === "closed_beta"
      ? "封闭测试用户"
      : "本地开发用户";

  return (
    <div className="account-settings-popover" id="account-settings-menu" role="menu" aria-label="设置中的用户项目">
      <header>
        <span>设置</span>
        <strong>用户</strong>
      </header>
      <section className="account-settings-profile" aria-label="当前用户信息">
        <span className="account-avatar" aria-hidden="true">{avatarLabel}</span>
        <div>
          <strong>{session.displayLabel}</strong>
          <small>{sessionLabel}</small>
        </div>
      </section>
      <button
        disabled={!teacherPreferencesAvailable}
        onClick={onOpenTeacherPreferences}
        role="menuitem"
        type="button"
      >
        <BookIcon />
        <span>
          <strong>教师偏好</strong>
          <small>{teacherPreferencesAvailable ? "查看、修改与删除偏好" : "本轮测试暂未开放"}</small>
        </span>
      </button>
      <button onClick={onOpenBetaValidation} role="menuitem" type="button">
        <HistoryIcon />
        <span>
          <strong>封闭测试与数据</strong>
          <small>查看告知、导出或退出数据验证</small>
        </span>
      </button>
      <button
        className="account-settings-signout"
        disabled={!session.canSignOut || session.busy}
        onClick={onSignOut}
        role="menuitem"
        type="button"
      >
        <SignOutIcon />
        <span>
          <strong>{session.busy ? "正在退出…" : "退出登录"}</strong>
          <small>{session.canSignOut ? "结束当前测试会话" : "本地开发模式无需退出"}</small>
        </span>
      </button>
      {error ? <p className="account-settings-error" role="alert">{error}</p> : null}
    </div>
  );
}

export function TeacherWorkbench() {
  const betaCapabilities = useBetaCapabilities();
  const betaSession = useBetaSession();
  const [capability, setCapability] = useState<CapabilityId>("search");
  const [drafts, setDrafts] = useState<Record<CapabilityId, string>>({
    search: "",
    solve: "",
    library: "",
    lesson: "",
    paper: "",
  });
  const [phases, setPhases] = useState<Record<CapabilityId, Phase>>({
    search: "idle",
    solve: "idle",
    library: "idle",
    lesson: "idle",
    paper: "idle",
  });
  const [result, setResult] = useState<SearchTaskResult | null>(null);
  const [solveResult, setSolveResult] = useState<SolveTaskResult | null>(null);
  const [questionBundle, setQuestionBundle] = useState<QuestionInputBundle | null>(null);
  const [visualProcessingConsent, setVisualProcessingConsent] = useState(false);
  const [errors, setErrors] = useState<Record<"search" | "solve", ViewError | null>>({
    search: null,
    solve: null,
  });
  const [searchProgress, setSearchProgress] = useState<SearchTaskProgressStage>("connecting");
  const [solveProgress, setSolveProgress] = useState<SolveTaskProgressStage>("connecting");
  const [history, setHistory] = useState<TaskRecord[]>([]);
  const [touched, setTouched] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [newTaskOpen, setNewTaskOpen] = useState(false);
  const [accountSettingsOpen, setAccountSettingsOpen] = useState(false);
  const [accountError, setAccountError] = useState("");
  const [teacherMemoryOpen, setTeacherMemoryOpen] = useState(false);
  const [betaValidationOpen, setBetaValidationOpen] = useState(false);
  const [authoringEntry, setAuthoringEntry] = useState<{
    source: QuestionAuthoringEntrySource;
    brief: string;
  } | null>(null);
  const [authoringActive, setAuthoringActive] = useState(false);
  const [workspaceResetVersions, setWorkspaceResetVersions] = useState<Record<PersistentWorkspaceId, number>>({
    authoring: 0,
    library: 0,
    lesson: 0,
    paper: 0,
  });
  const [previewPage, setPreviewPage] = useState(0);
  const [questionPage, setQuestionPage] = useState(0);
  const [solvePage, setSolvePage] = useState(0);
  const [taskFeedback, setTaskFeedback] = useState<Record<string, TaskFeedbackState>>({});
  const [feedbackBusyKey, setFeedbackBusyKey] = useState("");
  const [turning, setTurning] = useState(false);
  const [flipDirection, setFlipDirection] = useState<FlipDirection>("next");
  const sessionRef = useRef("");
  const abortRefs = useRef<Record<RunnableCapabilityId, AbortController | null>>({ search: null, solve: null });
  const turnTimerRef = useRef<number | null>(null);
  const requestSequenceRefs = useRef<Record<RunnableCapabilityId, number>>({ search: 0, solve: 0 });
  const resultRegionRef = useRef<HTMLElement | null>(null);
  const taskInputRef = useRef<HTMLTextAreaElement | null>(null);
  const historyTriggerRef = useRef<HTMLButtonElement | null>(null);
  const historyDrawerRef = useRef<HTMLElement | null>(null);
  const historyCloseRef = useRef<HTMLButtonElement | null>(null);
  const newTaskMenuRef = useRef<HTMLDivElement | null>(null);
  const accountSettingsRef = useRef<HTMLDivElement | null>(null);

  const definition = CAPABILITIES[capability];
  const query = drafts[capability];
  const phase = phases[capability];
  const workspaceVisibility = getWorkspaceVisibility(capability, authoringActive);
  const authoringVisible = workspaceVisibility.authoring;
  const searchVisible = workspaceVisibility.searchSolve && capability === "search";
  const solveVisible = workspaceVisibility.searchSolve && capability === "solve";
  const libraryVisible = workspaceVisibility.library;
  const lessonVisible = workspaceVisibility.lesson;
  const paperVisible = workspaceVisibility.paper;
  const activeProductCapability: ProductCapability = authoringVisible ? "authoring" : capability;
  const capabilityAvailable = betaCapabilities.has(activeProductCapability);
  const runnable = capabilityAvailable && (searchVisible || solveVisible);
  const error = runnable ? errors[capability as "search" | "solve"] : null;
  const running = runnable && phase === "running";
  const trimmedQuery = query.trim();
  const captureConfirmed = questionBundle?.recognition_status === "confirmed"
    && questionBundle.recognition_revision !== null
    && questionBundle.recognition_source_revision === questionBundle.asset.current_revision;
  const captureRequiresVisual = Boolean(
    captureConfirmed && questionBundle?.requires_visual_reasoning !== false,
  );
  const captureReady = !questionBundle || (
    captureConfirmed && (!captureRequiresVisual || visualProcessingConsent)
  );
  const queryValid = capabilityAvailable && (searchVisible
    ? Boolean(trimmedQuery)
    : solveVisible
      ? trimmedQuery.length >= 5 && captureReady
      : false);
  const validationMessage = runnable && touched && !queryValid
    ? searchVisible
      ? "先写下要找什么题。"
      : questionBundle && !captureConfirmed
        ? "请先完成识别、校对并确认当前题面 revision。"
        : captureRequiresVisual && !visualProcessingConsent
          ? "请确认是否同意本次视觉解题使用当前原图。"
          : "请输入一道完整题目，至少 5 个字符。"
    : "";
  const intent = useMemo(() => (result ? intentLabels(result) : []), [result]);
  const activeQuestion = result?.results[questionPage] ?? null;
  const showingSearchResult = searchVisible && phase === "success" && Boolean(result?.results.length);
  const showingEmptySearchResult = searchVisible && phase === "success" && result?.results.length === 0;
  const showingSolveResult = solveVisible && phase === "success" && Boolean(solveResult?.solution);
  const pageCount = !capabilityAvailable
    ? 1
    : showingSolveResult
    ? 3
    : showingSearchResult && result
    ? result.results.length
    : showingEmptySearchResult
      ? 1
      : definition.pages.length;
  const pageIndex = showingSolveResult ? solvePage : showingSearchResult ? questionPage : previewPage;
  const progressSteps = solveVisible
    ? solveProgress === "recovering"
      ? [...SOLVE_PROGRESS_STEPS, "恢复同一次运行"]
      : SOLVE_PROGRESS_STEPS
    : searchProgress === "recovering"
      ? [...SEARCH_PROGRESS_STEPS, "恢复同一次运行"]
      : SEARCH_PROGRESS_STEPS;

  useEffect(() => {
    if (authoringActive && !betaCapabilities.has("authoring")) {
      setAuthoringActive(false);
    }
    if ((!authoringActive && betaCapabilities.has(capability)) || (authoringActive && betaCapabilities.has("authoring"))) {
      return;
    }
    const next = WORKBENCH_NAV_ORDER.find((item) => betaCapabilities.has(item));
    if (!next) return;
    if (next === "authoring") {
      setAuthoringEntry((current) => current ?? { source: "new_task", brief: "" });
      setAuthoringActive(true);
      return;
    }
    setCapability(next);
    setAuthoringActive(false);
  }, [authoringActive, betaCapabilities, capability]);

  function setPhase(nextPhase: Phase, target: CapabilityId = capability) {
    setPhases((current) => ({ ...current, [target]: nextPhase }));
  }

  function setError(nextError: ViewError | null, target: "search" | "solve" = capability as "search" | "solve") {
    setErrors((current) => ({ ...current, [target]: nextError }));
  }

  function updateQuery(value: string) {
    setDrafts((current) => ({ ...current, [capability]: value }));
  }

  function scrollToResultRegion() {
    window.requestAnimationFrame(() => {
      const target = resultRegionRef.current;
      if (!target) return;

      const navHeight = document.querySelector<HTMLElement>(".app-nav")?.offsetHeight ?? 0;
      const top = window.scrollY + target.getBoundingClientRect().top - navHeight - 16;
      const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

      window.scrollTo({
        behavior: reducedMotion ? "auto" : "smooth",
        top: Math.max(0, top),
      });
    });
  }

  function returnToComposer() {
    window.requestAnimationFrame(() => {
      taskInputRef.current?.focus({ preventScroll: true });
      const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      window.scrollTo({ behavior: reducedMotion ? "auto" : "smooth", top: 0 });
    });
  }

  useEffect(() => {
    return () => {
      if (turnTimerRef.current !== null) window.clearTimeout(turnTimerRef.current);
      abortRefs.current.search?.abort();
      abortRefs.current.solve?.abort();
    };
  }, []);

  useEffect(() => {
    if (!historyOpen) return;
    const previousFocus = document.activeElement;
    historyCloseRef.current?.focus();

    function manageDialogFocus(event: globalThis.KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        setHistoryOpen(false);
        return;
      }
      if (event.key !== "Tab") return;

      const drawer = historyDrawerRef.current;
      if (!drawer) return;
      const focusable = Array.from(drawer.querySelectorAll<HTMLElement>(
        'button:not([disabled]), [href], input:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      )).filter((element) => !element.hasAttribute("hidden"));
      if (focusable.length === 0) {
        event.preventDefault();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    window.addEventListener("keydown", manageDialogFocus);
    return () => {
      window.removeEventListener("keydown", manageDialogFocus);
      if (previousFocus instanceof HTMLElement && document.contains(previousFocus)) {
        previousFocus.focus();
      } else {
        historyTriggerRef.current?.focus();
      }
    };
  }, [historyOpen]);

  useEffect(() => {
    if (!newTaskOpen) return;
    function closeMenu(event: MouseEvent | globalThis.KeyboardEvent) {
      if (event instanceof globalThis.KeyboardEvent) {
        if (event.key === "Escape") setNewTaskOpen(false);
        return;
      }
      if (!newTaskMenuRef.current?.contains(event.target as Node)) setNewTaskOpen(false);
    }
    window.addEventListener("mousedown", closeMenu);
    window.addEventListener("keydown", closeMenu);
    return () => {
      window.removeEventListener("mousedown", closeMenu);
      window.removeEventListener("keydown", closeMenu);
    };
  }, [newTaskOpen]);

  useEffect(() => {
    if (!accountSettingsOpen) return;
    function closeSettings(event: MouseEvent | globalThis.KeyboardEvent) {
      if (event instanceof globalThis.KeyboardEvent) {
        if (event.key === "Escape") setAccountSettingsOpen(false);
        return;
      }
      if (!accountSettingsRef.current?.contains(event.target as Node)) setAccountSettingsOpen(false);
    }
    window.addEventListener("mousedown", closeSettings);
    window.addEventListener("keydown", closeSettings);
    return () => {
      window.removeEventListener("mousedown", closeSettings);
      window.removeEventListener("keydown", closeSettings);
    };
  }, [accountSettingsOpen]);

  async function runTask(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    if (!runnable) return;
    const target = capability as RunnableCapabilityId;
    const trimmed = query.trim();
    setTouched(true);
    if (!queryValid || running) return;

    if (!sessionRef.current) sessionRef.current = createSessionId();
    const requestSequence = ++requestSequenceRefs.current[target];
    const controller = new AbortController();
    abortRefs.current[target] = controller;
    setPhase("running", target);
    if (searchVisible) setSearchProgress("connecting");
    else setSolveProgress("connecting");
    setError(null, target);
    setQuestionPage(0);
    setSolvePage(0);
    scrollToResultRegion();

    try {
      if (searchVisible) {
        const nextResult = await teacherWorkspace.searchQuestions(
          { query: trimmed, sessionId: sessionRef.current },
          {
            signal: controller.signal,
            onProgress: (progress) => {
              if (requestSequence === requestSequenceRefs.current[target]) {
                setSearchProgress(progress.stage);
              }
            },
          },
        );
        if (requestSequence !== requestSequenceRefs.current[target]) return;
        setResult(nextResult);
        setHistory((current) => [
          {
            id: nextResult.run_id || nextResult.request_id,
            capability: "search",
            query: trimmed,
            result: nextResult,
          },
          ...current.filter((item) => item.id !== nextResult.run_id).slice(0, 7),
        ]);
      } else {
        const questionCapture = questionBundle && captureConfirmed ? {
          assetId: questionBundle.asset.asset_id,
          mediaRevision: questionBundle.asset.current_revision,
          recognitionRevision: questionBundle.recognition_revision as number,
          visualProcessingConsent: captureRequiresVisual ? visualProcessingConsent : false,
        } : undefined;
        if (questionCapture?.visualProcessingConsent) setVisualProcessingConsent(false);
        const nextResult = await teacherWorkspace.solveQuestion(
          { questionText: trimmed, sessionId: sessionRef.current, questionCapture },
          {
            signal: controller.signal,
            onProgress: (progress) => {
              if (requestSequence === requestSequenceRefs.current[target]) {
                setSolveProgress(progress.stage);
              }
            },
          },
        );
        if (requestSequence !== requestSequenceRefs.current[target]) return;
        setSolveResult(nextResult);
        setHistory((current) => [
          {
            id: nextResult.run_id || nextResult.request_id,
            capability: "solve",
            query: trimmed,
            result: nextResult,
          },
          ...current.filter((item) => item.id !== nextResult.run_id).slice(0, 7),
        ]);
      }
      setPhase("success", target);
      scrollToResultRegion();
    } catch (cause) {
      if (requestSequence !== requestSequenceRefs.current[target]) return;
      if (cause instanceof DOMException && cause.name === "AbortError") {
        setPhase("cancelled", target);
        return;
      }
      const nextError = cause instanceof TeacherWorkspaceError
        ? { code: cause.code, message: cause.message, requestId: cause.requestId }
        : { code: "UNKNOWN_ERROR", message: "任务未完成。请检查服务状态后重试。", requestId: "" };
      setError(nextError, target);
      setPhase("error", target);
    } finally {
      if (requestSequence === requestSequenceRefs.current[target]) abortRefs.current[target] = null;
    }
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (runnable && (event.ctrlKey || event.metaKey) && event.key === "Enter") {
      event.preventDefault();
      void runTask();
    }
  }

  function selectCapability(nextCapability: CapabilityId) {
    if (turning || !betaCapabilities.has(nextCapability)) return;
    if (nextCapability === capability) {
      setAuthoringActive(false);
      setNewTaskOpen(false);
      setAccountSettingsOpen(false);
      return;
    }

    const currentIndex = CAPABILITY_ORDER.indexOf(capability);
    const nextIndex = CAPABILITY_ORDER.indexOf(nextCapability);
    setFlipDirection(nextIndex > currentIndex ? "next" : "previous");
    setTurning(true);
    setAuthoringActive(false);
    setNewTaskOpen(false);
    setAccountSettingsOpen(false);
    setTouched(false);
    if (turnTimerRef.current !== null) window.clearTimeout(turnTimerRef.current);
    turnTimerRef.current = window.setTimeout(() => {
      setCapability(nextCapability);
      setPreviewPage(0);
      setTurning(false);
    }, 440);
  }

  function resetTask() {
    if (authoringVisible) {
      setWorkspaceResetVersions((current) => ({ ...current, authoring: current.authoring + 1 }));
      setAuthoringEntry({ source: "new_task", brief: "" });
      setNewTaskOpen(false);
      return;
    }
    if (libraryVisible) {
      setWorkspaceResetVersions((current) => ({ ...current, library: current.library + 1 }));
      setNewTaskOpen(false);
      return;
    }
    if (lessonVisible) {
      setDrafts((current) => ({ ...current, lesson: "" }));
      setWorkspaceResetVersions((current) => ({ ...current, lesson: current.lesson + 1 }));
      setNewTaskOpen(false);
      return;
    }
    if (paperVisible) {
      setDrafts((current) => ({ ...current, paper: "" }));
      setWorkspaceResetVersions((current) => ({ ...current, paper: current.paper + 1 }));
      setNewTaskOpen(false);
      return;
    }
    const target = capability as RunnableCapabilityId;
    requestSequenceRefs.current[target] += 1;
    abortRefs.current[target]?.abort();
    abortRefs.current[target] = null;
    setDrafts((current) => ({ ...current, [capability]: "" }));
    setTouched(false);
    setPreviewPage(0);
    if (searchVisible) {
      setResult(null);
      setError(null);
      setPhase("idle");
      setQuestionPage(0);
    }
    if (solveVisible) {
      setSolveResult(null);
      setQuestionBundle(null);
      setVisualProcessingConsent(false);
      setError(null);
      setPhase("idle");
      setSolvePage(0);
    }
    returnToComposer();
  }

  function openAuthoring(source: QuestionAuthoringEntrySource, brief = "") {
    if (turning || !betaCapabilities.has("authoring")) return;
    setNewTaskOpen(false);
    setAccountSettingsOpen(false);
    setAuthoringEntry((current) => current ?? { source, brief: brief.trim() });
    setAuthoringActive(true);
    window.requestAnimationFrame(() => window.scrollTo({ top: 0, behavior: "auto" }));
  }

  async function signOut() {
    setAccountError("");
    try {
      await betaSession.signOut();
      setAccountSettingsOpen(false);
    } catch {
      setAccountError("退出未完成，请检查网络后重试。");
    }
  }

  function openTask(task: TaskRecord) {
    if (!betaCapabilities.has(task.capability)) return;
    requestSequenceRefs.current[task.capability] += 1;
    abortRefs.current[task.capability]?.abort();
    abortRefs.current[task.capability] = null;
    setAuthoringActive(false);
    setCapability(task.capability);
    setDrafts((current) => ({ ...current, [task.capability]: task.query }));
    if (task.capability === "search") {
      setResult(task.result);
      setQuestionPage(0);
    } else {
      setSolveResult(task.result);
      setSolvePage(0);
      setQuestionBundle(null);
      setVisualProcessingConsent(false);
    }
    setError(null, task.capability);
    setPhase("success", task.capability);
    setHistoryOpen(false);
    scrollToResultRegion();
  }

  function continueToSolve(item: SearchQuestion) {
    if (turning || running || !betaCapabilities.has("solve")) return;
    if (result?.run_id) {
      const feedbackKey = `search:${result.run_id}`;
      void teacherWorkspace.selectSearchResult(result.run_id, item.question_id)
        .then((receipt) => {
          setTaskFeedback((current) => ({
            ...current,
            [feedbackKey]: {
              decision: "accepted",
              state: receipt.state,
            },
          }));
        })
        .catch(() => {
          setTaskFeedback((current) => ({
            ...current,
            [feedbackKey]: { decision: "accepted", state: "unavailable" },
          }));
        });
    }
    setDrafts((current) => ({ ...current, solve: item.stem || item.stem_preview }));
    setSolveResult(null);
    setQuestionBundle(null);
    setVisualProcessingConsent(false);
    setError(null, "solve");
    setPhase("idle", "solve");
    setSolvePage(0);
    selectCapability("solve");
    window.setTimeout(returnToComposer, 480);
  }

  async function decideTask(
    workflow: "search" | "solve",
    runId: string,
    decision: BetaTaskDecision,
  ) {
    const feedbackKey = `${workflow}:${runId}`;
    if (feedbackBusyKey) return;
    setFeedbackBusyKey(feedbackKey);
    try {
      const receipt = await teacherWorkspace.recordTaskDecision(workflow, runId, decision);
      setTaskFeedback((current) => ({
        ...current,
        [feedbackKey]: { decision, state: receipt.state },
      }));
    } catch {
      setTaskFeedback((current) => ({
        ...current,
        [feedbackKey]: { decision, state: "unavailable" },
      }));
    } finally {
      setFeedbackBusyKey("");
    }
  }

  function turnPage(direction: FlipDirection) {
    if (turning || pageCount < 2) return;
    const current = showingSolveResult ? solvePage : showingSearchResult ? questionPage : previewPage;
    const next = direction === "next"
      ? (current + 1) % pageCount
      : (current - 1 + pageCount) % pageCount;
    setFlipDirection(direction);
    setTurning(true);
    if (turnTimerRef.current !== null) window.clearTimeout(turnTimerRef.current);
    turnTimerRef.current = window.setTimeout(() => {
      if (showingSolveResult) setSolvePage(next);
      else if (showingSearchResult) setQuestionPage(next);
      else setPreviewPage(next);
      setTurning(false);
    }, 440);
  }

  const stageTitle = !capabilityAvailable
    ? `当前封闭测试尚未开放${definition.label}`
    : searchVisible && phase === "success" && result
    ? `${result.returned_count} 道题已整理成册`
    : solveVisible && phase === "success" && solveResult?.solution
      ? "解析、课堂提示与可信证据已整理"
    : running
      ? solveVisible
        ? SOLVE_PROGRESS[solveProgress].stageTitle
        : SEARCH_PROGRESS[searchProgress].stageTitle
      : runnable && phase === "error"
        ? solveVisible ? "解题暂时中断" : "检索暂时中断"
        : definition.stageTitle;

  return (
    <div className="workbench-shell" data-capability={capability}>
      <header className="app-nav">
        <div className="app-nav__inner">
          <button className="brand-button" type="button" disabled={!betaCapabilities.has("search")} onClick={() => selectCapability("search")} aria-label="返回搜题">
            <span className="brand-mark">数</span>
            <span className="brand-name">备课伙伴</span>
          </button>

          <nav className="capability-tabs" aria-label="Agent 能力">
            {WORKBENCH_NAV_ORDER.map((id) => {
              if (id === "authoring") {
                const available = betaCapabilities.has("authoring");
                return (
                  <button
                    aria-label={available ? "命题，已开放" : "命题，封闭测试暂未开放"}
                    aria-pressed={authoringVisible}
                    className={authoringVisible ? "is-active" : ""}
                    disabled={turning || !available}
                    key={id}
                    onClick={() => openAuthoring("new_task")}
                    type="button"
                  >
                    <SparkIcon />
                    <span>命题</span>
                    <i className="is-ready" aria-hidden="true" />
                  </button>
                );
              }
              const item = CAPABILITIES[id];
              const available = betaCapabilities.has(id);
              return (
                <button
                  aria-label={`${item.label}${available ? "，已开放" : "，封闭测试暂未开放"}`}
                  aria-pressed={!authoringVisible && capability === id}
                  className={!authoringVisible && capability === id ? "is-active" : ""}
                  disabled={turning || !available}
                  key={id}
                  onClick={() => selectCapability(id)}
                  type="button"
                >
                  <CapabilityIcon id={id} />
                  <span>{item.label}</span>
                  <i className={item.ready ? "is-ready" : ""} aria-hidden="true" />
                </button>
              );
            })}
          </nav>

          <div className="nav-actions">
            <button ref={historyTriggerRef} className="icon-button" type="button" onClick={() => setHistoryOpen(true)} aria-label="查看任务记录">
              <HistoryIcon />
              {history.length > 0 && <span>{history.length}</span>}
            </button>
            <div className="new-task-menu" ref={newTaskMenuRef}>
              <button className="new-task-button" type="button" onClick={() => { setAccountSettingsOpen(false); setNewTaskOpen((current) => !current); }} aria-expanded={newTaskOpen} aria-haspopup="menu" aria-label="新任务菜单">
                <PlusIcon />
                <span>新任务</span>
              </button>
              {newTaskOpen && (
                <div className="new-task-popover" role="menu">
                  <button role="menuitem" type="button" onClick={resetTask}><PlusIcon /><span><strong>清空当前任务</strong><small>保留当前 Agent</small></span></button>
                  <button role="menuitem" type="button" disabled={!betaCapabilities.has("authoring")} onClick={() => openAuthoring("new_task")}><SparkIcon /><span><strong>辅助命题</strong><small>{betaCapabilities.has("authoring") ? "生成草稿 · 仅自己可见" : "本轮测试暂未开放"}</small></span></button>
                </div>
              )}
            </div>
            <div className="account-settings" ref={accountSettingsRef}>
              <button
                aria-controls="account-settings-menu"
                aria-expanded={accountSettingsOpen}
                aria-haspopup="menu"
                aria-label={`打开设置，当前用户 ${betaSession.displayLabel}`}
                className="account-settings-button"
                onClick={() => {
                  setNewTaskOpen(false);
                  setAccountError("");
                  setAccountSettingsOpen((current) => !current);
                }}
                type="button"
              >
                <span className="account-avatar" aria-hidden="true">{betaSession.displayLabel.trim().slice(0, 1) || "教"}</span>
                <span className="account-settings-button__label">{betaSession.displayLabel}</span>
                <SettingsIcon />
              </button>
              {accountSettingsOpen ? (
                <AccountSettingsPopover
                  error={accountError}
                  onOpenBetaValidation={() => {
                    setAccountSettingsOpen(false);
                    setBetaValidationOpen(true);
                  }}
                  onOpenTeacherPreferences={() => {
                    setAccountSettingsOpen(false);
                    setTeacherMemoryOpen(true);
                  }}
                  onSignOut={() => { void signOut(); }}
                  session={betaSession}
                  teacherPreferencesAvailable={betaCapabilities.has("teacher_memory")}
                />
              ) : null}
            </div>
          </div>
        </div>
      </header>

      {betaCapabilities.has("teacher_memory") && (
        <TeacherMemoryPanel open={teacherMemoryOpen} onClose={() => setTeacherMemoryOpen(false)} />
      )}
      <BetaValidationPanel open={betaValidationOpen} onClose={() => setBetaValidationOpen(false)} />

      {betaCapabilities.has("authoring") && <div data-workspace-view="authoring" hidden={!authoringVisible}>
        {authoringEntry && (
          <PersonalQuestionAuthoringWorkspace
            initialBrief={authoringEntry.brief}
            key={`authoring-${workspaceResetVersions.authoring}`}
          />
        )}
      </div>}
      {betaCapabilities.has("library") && <div data-workspace-view="library" hidden={!libraryVisible}>
        <PrivateLibraryWorkspace key={`library-${workspaceResetVersions.library}`} />
      </div>}
      {betaCapabilities.has("lesson") && <div data-workspace-view="lesson" hidden={!lessonVisible}>
        <LessonBlueprintWorkspace
          initialBrief={drafts.lesson}
          key={`lesson-${workspaceResetVersions.lesson}`}
          onBriefChange={(brief) => setDrafts((current) => ({ ...current, lesson: brief }))}
        />
      </div>}
      {betaCapabilities.has("paper") && <div data-workspace-view="paper" hidden={!paperVisible}>
        <PaperBlueprintWorkspace
          initialBrief={drafts.paper}
          key={`paper-${workspaceResetVersions.paper}`}
          onBriefChange={(brief) => setDrafts((current) => ({ ...current, paper: brief }))}
          onOpenAuthoring={(brief) => openAuthoring("paper", brief)}
        />
      </div>}
      <div data-workspace-view="search-solve" hidden={authoringVisible || libraryVisible || lessonVisible || paperVisible}>
      <main className="marquee-workspace marquee-workspace--split">
        <ResizableSplitPane
          ariaLabel={`调整${definition.label}要求与结果区域宽度`}
          className="search-solve-split"
          defaultPrimaryPercent={40}
          disabled={running}
          state={phase === "error" ? "error" : running ? "loading" : phase === "success" ? "success" : "default"}
        >
        <section className="task-pane">
          <div className="task-pane__intro">
            <h1>{definition.title[0]}<br />{definition.title[1]}</h1>
            <p className="intro-copy">{definition.intro}</p>
          </div>

          <form className="task-composer" onSubmit={runTask}>
            <label htmlFor="teacher-task">{definition.inputLabel}</label>
            {solveVisible && capabilityAvailable && (
              <QuestionMediaComposer
                bundle={questionBundle}
                disabled={running}
                visualProcessingConsent={visualProcessingConsent}
                onChange={(nextBundle) => {
                  setQuestionBundle(nextBundle);
                  setVisualProcessingConsent(false);
                }}
                onConfirmed={(confirmedBundle) => {
                  const optionText = confirmedBundle.options
                    .map((item) => `${item.key}. ${item.text}`)
                    .join("\n");
                  const confirmedText = optionText
                    ? `${confirmedBundle.stem_plain}\n${optionText}`
                    : confirmedBundle.stem_plain;
                  setDrafts((current) => ({ ...current, solve: confirmedText }));
                  setTouched(false);
                }}
                onVisualProcessingConsentChange={setVisualProcessingConsent}
              />
            )}
            <div className={`composer-surface${validationMessage ? " is-error" : ""}${running ? " is-running" : ""}${definition.ready ? "" : " is-planned"}`}>
              <textarea
                ref={taskInputRef}
                id="teacher-task"
                aria-describedby="teacher-task-help"
                aria-busy={running}
                aria-invalid={Boolean(validationMessage)}
                aria-required={runnable}
                onBlur={() => {
                  if (definition.ready) setTouched(true);
                }}
                onChange={(event) => {
                  updateQuery(event.target.value);
                  if (touched && event.target.value.trim()) setTouched(false);
                }}
                onKeyDown={handleComposerKeyDown}
                placeholder={definition.placeholder}
                disabled={!capabilityAvailable}
                readOnly={running || Boolean(questionBundle && captureConfirmed)}
                rows={4}
                value={query}
              />
              <div className="composer-actions">
                <span id="teacher-task-help" className={validationMessage ? "form-error" : "form-help"}>
                  {validationMessage || (runnable ? "Ctrl ↵ 运行" : "可以先整理需求；该 Agent 尚未接入运行时。")}
                </span>
                {running ? (
                  <button className="cancel-button" type="button" onClick={() => abortRefs.current[capability as RunnableCapabilityId]?.abort()}>
                    <CloseIcon /><span>取消</span>
                  </button>
                ) : (
                  <button className="run-button" type="submit" disabled={!runnable || !queryValid}>
                    <span>{definition.actionLabel}</span><ArrowUpIcon />
                  </button>
                )}
              </div>
            </div>
          </form>

          <section className="quick-prompts" aria-label={`${definition.label}示例`}>
            <p>从一个具体任务开始</p>
            <div>
              {definition.examples.map((example) => (
                <button key={example.query} type="button" disabled={running || !capabilityAvailable} onClick={() => updateQuery(example.query)}>
                  <span>{example.label}</span>
                  <small>{example.detail}</small>
                  <ArrowRightIcon />
                </button>
              ))}
            </div>
          </section>
        </section>

        <section className="visual-pane" aria-live="polite" ref={resultRegionRef}>
          <header className="visual-pane__head">
            <div>
              <span>{searchVisible && phase === "success" ? "检索结果" : solveVisible && phase === "success" ? "解题结果" : definition.stageLabel}</span>
              <h2>{stageTitle}</h2>
            </div>
            <div className="page-controls" aria-label="翻页控制">
              <button type="button" onClick={() => turnPage("previous")} disabled={turning || pageCount < 2} aria-label="上一页"><ArrowLeftIcon /></button>
              <span>{String(pageIndex + 1).padStart(2, "0")} / {String(pageCount).padStart(2, "0")}</span>
              <button type="button" onClick={() => turnPage("next")} disabled={turning || pageCount < 2} aria-label="下一页"><ArrowRightIcon /></button>
            </div>
          </header>

          <div className="paper-theatre">
            <div className="paper-shadow paper-shadow--back" aria-hidden="true" />
            <div className="paper-shadow paper-shadow--middle" aria-hidden="true" />
            <div className={`paper-leaf${turning ? ` is-turning is-turning--${flipDirection}` : ""}`}>
              {!capabilityAvailable && (
                <section className="message-paper" role="status">
                  <ClockIcon /><p>当前封闭测试暂未开放</p>
                  <h2>{definition.label}暂不可用。</h2>
                  <span>开放范围由本次邀请决定；其他已开放模块仍可正常使用。</span>
                </section>
              )}
              {capabilityAvailable && (!runnable || phase === "idle") && <PreviewPaper capability={capability} page={previewPage} />}
              {running && (
                <section className="process-paper">
                  <span className="orbit-loader" aria-hidden="true"><i /><i /><i /></span>
                  <p>{solveVisible ? "SOLVE / CONTROLLED TOOL" : "SEARCH / CONTROLLED TOOLS"}</p>
                  <h2>{solveVisible ? SOLVE_PROGRESS[solveProgress].paperTitle : SEARCH_PROGRESS[searchProgress].paperTitle}</h2>
                  <ol>
                    {progressSteps.map((label, index) => (
                      <li
                        aria-current={index === (solveVisible ? SOLVE_PROGRESS[solveProgress].activeStep : SEARCH_PROGRESS[searchProgress].activeStep) ? "step" : undefined}
                        className={index === (solveVisible ? SOLVE_PROGRESS[solveProgress].activeStep : SEARCH_PROGRESS[searchProgress].activeStep)
                          ? "is-active"
                          : index < (solveVisible ? SOLVE_PROGRESS[solveProgress].activeStep : SEARCH_PROGRESS[searchProgress].activeStep)
                            ? "is-complete"
                            : undefined}
                        key={label}
                      >
                        <span>{String(index + 1).padStart(2, "0")}</span>{label}
                      </li>
                    ))}
                  </ol>
                </section>
              )}
              {runnable && phase === "cancelled" && (
                <section className="message-paper">
                  <ClockIcon /><p>任务已取消</p>
                  <h2>没有保存本次结果。</h2>
                  <span>可以修改描述后重新运行。</span>
                </section>
              )}
              {runnable && phase === "error" && error && (
                <section className="message-paper message-paper--error" role="alert">
                  <span className="error-code">{error.code}</span>
                  <h2>任务没有完成</h2>
                  <p>{error.message}</p>
                  {ERROR_GUIDANCE[error.code] && <span>{ERROR_GUIDANCE[error.code]}</span>}
                  {error.requestId && <small className="request-id">请求编号 · {error.requestId}</small>}
                  <button type="button" onClick={() => void runTask()}>重新尝试 <ArrowRightIcon /></button>
                </section>
              )}
              {searchVisible && phase === "success" && result && activeQuestion && (
                <QuestionPaper item={activeQuestion} index={questionPage} onSolve={continueToSolve} total={result.results.length} />
              )}
              {searchVisible && phase === "success" && result && result.results.length === 0 && (
                <section className="message-paper empty-paper">
                  <SearchIcon /><p>没有真实记录满足当前条件</p>
                  <h2>系统没有为了凑数临时生成题目。</h2>
                  <span>{result.answer_summary || "调整知识点、地区或难度后再试一次。"}</span>
                  {result.suggestions[0] && (
                    <button type="button" onClick={() => updateQuery(result.suggestions[0])}>采用放宽建议 <ArrowRightIcon /></button>
                  )}
                  {betaCapabilities.has("authoring") && <button className="authoring-entry-link" type="button" onClick={() => openAuthoring("search", result.raw_query || query)}>根据当前条件辅助命题 <SparkIcon /></button>}
                </section>
              )}
              {solveVisible && phase === "success" && solveResult?.solution && (
                <SolvePaper page={solvePage} result={solveResult} />
              )}
            </div>
          </div>

          {searchVisible && phase === "success" && result && (
            <section className="result-brief">
              <div className="result-brief__line">
                <span className={`confidence confidence--${result.search_confidence}`}>
                  {result.exact_match ? "条件完全满足" : "包含相近条件"}
                </span>
                <p>{result.exact_match_count} 道完全匹配 · {result.duration_ms} ms · {result.tool_call_count} 次工具调用</p>
              </div>
              {intent.length > 0 && <ul>{intent.map((label) => <li key={label}>{label}</li>)}</ul>}
              {result.warnings.map((warning) => <p className="result-warning" key={warning}>{warning}</p>)}
              {result.assistant_explanation && (
                <details>
                  <summary>检索说明</summary>
                  <MathText text={result.assistant_explanation} />
                </details>
              )}
              {betaCapabilities.has("authoring") && <button className="result-authoring-entry" type="button" onClick={() => openAuthoring("search", result.raw_query || query)}>
                <span>这些题不合适</span><strong>根据当前条件辅助命题</strong><SparkIcon />
              </button>}
            </section>
          )}
          {searchVisible && phase === "success" && result?.run_id && (
            <TaskFeedbackControl
              busy={feedbackBusyKey === `search:${result.run_id}`}
              feedback={taskFeedback[`search:${result.run_id}`] ?? null}
              onDecision={(decision) => void decideTask("search", result.run_id, decision)}
            />
          )}
          {solveVisible && phase === "success" && solveResult?.solution && (
            <SolveResultBrief result={solveResult} />
          )}
          {solveVisible && phase === "success" && solveResult?.solution && solveResult.run_id && (
            <TaskFeedbackControl
              busy={feedbackBusyKey === `solve:${solveResult.run_id}`}
              feedback={taskFeedback[`solve:${solveResult.run_id}`] ?? null}
              onDecision={(decision) => void decideTask("solve", solveResult.run_id, decision)}
            />
          )}
        </section>
        </ResizableSplitPane>
      </main>
      </div>

      <footer className="inline-footer">
        <span>备课伙伴</span>
        <span>{authoringVisible ? "辅助命题 · 已接入" : `${definition.label} · ${definition.ready ? "已接入" : "界面预览"}`}</span>
        <span>高中数学 · 私有工作区</span>
      </footer>

      <button className={`drawer-backdrop${historyOpen ? " is-open" : ""}`} type="button" onClick={() => setHistoryOpen(false)} aria-hidden="true" tabIndex={-1} />
      <aside
        ref={historyDrawerRef}
        className={`history-drawer${historyOpen ? " is-open" : ""}`}
        aria-hidden={!historyOpen}
        aria-labelledby="history-drawer-title"
        aria-modal="true"
        inert={!historyOpen}
        role="dialog"
      >
        <header>
          <div><span>本次会话</span><h2 id="history-drawer-title">任务记录</h2></div>
          <button ref={historyCloseRef} className="icon-button" type="button" onClick={() => setHistoryOpen(false)} aria-label="关闭"><CloseIcon /></button>
        </header>
        {history.length === 0 ? (
          <div className="history-empty"><ClockIcon /><p>完成的搜题与解题会暂存在这里。</p><span>刷新页面后清空。</span></div>
        ) : (
          <ol>
            {history.map((task) => (
              <li key={task.id}>
                <button type="button" onClick={() => openTask(task)}>
                  <span>{querySummary(task.query)}</span>
                  <small>
                    {task.capability === "search"
                      ? `${task.result.returned_count} 道题`
                      : solutionConfidenceLabel(task.result.solution?.confidence_status ?? "")}
                    <ArrowRightIcon />
                  </small>
                </button>
              </li>
            ))}
          </ol>
        )}
      </aside>
    </div>
  );
}
