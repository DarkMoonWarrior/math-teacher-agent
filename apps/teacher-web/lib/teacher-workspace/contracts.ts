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

export type MathVerificationAssessment = {
  status: "passed" | "failed" | "inconclusive";
  capability: "supported" | "unsupported";
  scope: "question_answer" | "matched_question_record" | "generated_solution";
  evidence_source: "math_verifier" | "teacher_evidence" | "stored_status" | "none";
  method: string | null;
  computed_answer: string | null;
  source_answer: string | null;
  details: string[];
  verifier_version: string | null;
};

export type SolveTaskSolution = {
  question_text: string;
  solution_mode: "standard" | "alternative";
  explanation: {
    method: string;
    steps: string[];
    final_answer: string;
  };
  knowledge_points: string[];
  common_mistakes: string[];
  teaching_notes: string[];
  confidence_status: "program_verified" | "model_reviewed" | "teacher_review_required";
  math_verification: MathVerificationAssessment;
  verification_evidence: string[];
  provider: string;
  model: string;
  mode: "verified_bank" | "live_ai";
  matched_question_id: string | null;
  matched_question_revision_count: number | null;
  match_score: number | null;
  alternative_available: boolean;
  warnings: string[];
};

export type SolveTaskResult = {
  request_id: string;
  session_id: string;
  run_id: string;
  status: "pending" | "running" | "ok" | "error" | "cancelled";
  question_text: string;
  solution_mode: "standard" | "alternative";
  solution: SolveTaskSolution | null;
  tool_request_id: string;
  duration_ms: number;
  tool_call_count: number;
  error: { code: string; message: string; request_id: string } | null;
};

export type SolveTaskRequest = {
  questionText: string;
  sessionId: string;
  solutionMode?: "standard" | "alternative";
  teacherInstruction?: string;
};

export type SolveTaskProgressStage =
  | "connecting"
  | "understanding"
  | "solving"
  | "verifying"
  | "recovering";

export type SolveTaskProgress = {
  stage: SolveTaskProgressStage;
};

export type SolveTaskOptions = {
  signal?: AbortSignal;
  onProgress?: (progress: SolveTaskProgress) => void;
};

export interface TeacherWorkspace {
  searchQuestions(
    request: SearchTaskRequest,
    options?: SearchTaskOptions,
  ): Promise<SearchTaskResult>;

  solveQuestion(
    request: SolveTaskRequest,
    options?: SolveTaskOptions,
  ): Promise<SolveTaskResult>;
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
