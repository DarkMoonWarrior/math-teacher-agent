export type MatchReason = {
  code: string;
  label: string;
  strength: string;
};

export type SearchPlanStep = {
  step: number;
  title: string;
  status: "pending" | "completed" | "skipped" | "failed";
  reason: string;
};

export type SearchConstraint = {
  field: string;
  value: unknown;
  strength: "hard" | "soft" | "default";
  reason: string;
};

export type SearchQuestion = {
  question_id: string;
  stem: string;
  stem_preview: string;
  question_type: string;
  knowledge_points: string[];
  difficulty: number;
  verification_status: string;
  source_status: string;
  visibility: string;
  chapter: string | null;
  section: string | null;
  volume: string | null;
  year: number | null;
  region: string | null;
  match_reasons: MatchReason[];
  relaxed_fields: string[];
  grounded: boolean;
};

export type SearchTaskResult = {
  request_id: string;
  session_id: string;
  run_id: string;
  raw_query: string;
  status: string;
  intent: {
    grade: string | null;
    knowledge_points: string[];
    question_types: string[];
    difficulty: number | null;
    regions: string[];
    teaching_usage: string;
    constraints: SearchConstraint[];
    parse_warnings: string[];
  };
  plan_summary: {
    steps: SearchPlanStep[];
    candidate_count: number;
    selected_count: number;
  };
  results: SearchQuestion[];
  requested_count: number;
  returned_count: number;
  exact_match_count: number;
  exact_match: boolean;
  warnings: string[];
  answer_summary: string;
  assistant_explanation: string | null;
  search_confidence: string;
  suggestions: string[];
  duration_ms: number;
  tool_call_count: number;
  candidate_count: number;
  error: { code: string; message: string; request_id: string } | null;
};

export type SearchTaskRequest = {
  query: string;
  sessionId: string;
};

export type SearchTaskProgressStage =
  | "connecting"
  | "understanding"
  | "searching"
  | "checking"
  | "recovering";

export type SearchTaskProgress = {
  stage: SearchTaskProgressStage;
};

export type SearchTaskOptions = {
  signal?: AbortSignal;
  onProgress?: (progress: SearchTaskProgress) => void;
};

export interface TeacherWorkspace {
  searchQuestions(
    request: SearchTaskRequest,
    options?: SearchTaskOptions,
  ): Promise<SearchTaskResult>;
}

export class TeacherWorkspaceError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly requestId = "",
  ) {
    super(message);
    this.name = "TeacherWorkspaceError";
  }
}
