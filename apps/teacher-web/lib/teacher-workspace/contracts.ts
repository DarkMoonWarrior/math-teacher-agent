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
  visual_context: {
    asset_id: string;
    media_revision: number;
    recognition_revision: number;
    requires_visual_reasoning: boolean;
    visual_processing_consent: boolean;
    image_used: boolean;
    provider: string;
    model: string;
  } | null;
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
  questionCapture?: {
    assetId: string;
    mediaRevision: number;
    recognitionRevision: number;
    visualProcessingConsent: boolean;
  };
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

export type QuestionMediaSource = "upload" | "clipboard" | "camera";

export type QuestionMediaRevision = {
  revision: number;
  source_revision: number | null;
  operation: "original" | "rotate" | "crop";
  width: number;
  height: number;
  mime_type: "image/png" | "image/jpeg" | "image/webp";
  content_endpoint: string;
  created_at: string;
};

export type QuestionMediaAsset = {
  asset_id: string;
  original_filename: string;
  source: QuestionMediaSource;
  source_sha256: string;
  current_revision: number;
  width: number;
  height: number;
  size_bytes: number;
  mime_type: "image/png" | "image/jpeg" | "image/webp";
  clarity_status: "clear" | "review_needed";
  warnings: string[];
  revisions: QuestionMediaRevision[];
  visibility: "private";
  public_search_allowed: false;
  model_training_allowed: false;
  created_at: string;
  updated_at: string;
};

export type QuestionInputBundle = {
  asset: QuestionMediaAsset;
  recognition_status: "not_started" | "draft" | "confirmed" | "stale";
  recognition_revision: number | null;
  recognition_source_revision: number | null;
  recognition_mode: "local" | "external" | null;
  recognition_provider: string | null;
  recognition_model: string | null;
  stem_plain: string;
  stem_latex: string;
  options: Array<{ key: string; text: string }>;
  requires_visual_reasoning: boolean | null;
  low_confidence_regions: Array<{
    text: string;
    reason: string;
    confidence: number | null;
    box: [number, number, number, number] | null;
  }>;
  recognition_warnings: string[];
  external_processing_consent: boolean;
  teacher_review_note: string;
  visibility: "private";
};

export type QuestionMediaUpload = {
  file: File;
  source: QuestionMediaSource;
  privateStorageAcknowledged: true;
};

export type QuestionMediaTransform =
  | { operation: "rotate"; degrees: 90 | 180 | 270 }
  | { operation: "crop"; crop: { x: number; y: number; width: number; height: number } };

export type QuestionRecognitionRequest = {
  mode: "local" | "external";
  externalProcessingConsent: boolean;
};

export type QuestionRecognitionReview = {
  stemPlain: string;
  stemLatex: string;
  options: Array<{ key: string; text: string }>;
  note: string;
  confirm: boolean;
};

export type LibraryRightsBasis =
  | "original"
  | "licensed"
  | "private_teaching_only";

export type LibraryItemSummary = {
  library_item_id: string;
  title: string;
  original_filename: string;
  file_kind: "pdf" | "docx" | "image";
  mime_type: string;
  size_bytes: number;
  page_count: number | null;
  extraction_status: "extracted" | "needs_ocr" | "failed";
  text_review_status: "pending" | "confirmed";
  extracted_char_count: number;
  corrected_char_count: number;
  rights_basis: LibraryRightsBasis;
  lifecycle_state: "active" | "trashed";
  trashed_at: string | null;
  visibility: "private";
  public_search_allowed: false;
  model_training_allowed: false;
  version: number;
  created_at: string;
  updated_at: string;
};

export type PrivateLibraryList = {
  items: LibraryItemSummary[];
  total: number;
};

export type PrivateLibrarySearchItem = {
  library_item_id: string;
  title: string;
  excerpt: string;
  source_version: number;
  rights_basis: LibraryRightsBasis;
  text_review_status: "confirmed";
  visibility: "private";
};

export type PrivateLibrarySearchResult = {
  query: string;
  items: PrivateLibrarySearchItem[];
  total: number;
  truncated: boolean;
  content_scope: "matching_excerpts";
  visibility: "private";
};

export type LibraryItemDetail = LibraryItemSummary & {
  source_sha256: string;
  extracted_text: string;
  corrected_text: string;
  rights_statement: string;
  adaptation_allowed: boolean;
  warnings: string[];
  review_note: string;
};

export type LibraryTextRevision = {
  version: number;
  previous_text: string;
  revised_text: string;
  review_status: "pending" | "confirmed";
  note: string;
  created_at: string;
};

export type LibraryTextRevisionList = {
  library_item_id: string;
  current_version: number;
  items: LibraryTextRevision[];
};

export type PrivateLibraryReview = {
  correctedText: string;
  note: string;
  confirm: boolean;
};

export type PrivateLibraryOCRRequest = {
  mode: "local" | "external";
  externalProcessingConsent: boolean;
};

export type PrivateLibraryOCRResult = {
  item: LibraryItemDetail;
  provider: string;
  warnings: string[];
};

export type QuestionCandidateOption = {
  key: string;
  text: string;
};

export type QuestionCandidateCurriculum = {
  node_id: string;
  name: string;
  volume: string;
  chapter: string;
  section: string;
};

export type PrivateLibraryQuestionCandidate = {
  candidate_id: string;
  library_item_id: string;
  source_version: number;
  position: number;
  question_type: "single_choice" | "multiple_choice" | "fill_blank" | "open_response";
  stem_plain: string;
  stem_latex: string | null;
  options: QuestionCandidateOption[];
  answer_value: string | null;
  solution_method: string;
  solution_steps: string[];
  final_answer: string | null;
  difficulty: number;
  curriculum: QuestionCandidateCurriculum | null;
  status: "draft" | "discarded" | "imported";
  warnings: string[];
  imported_question_id: string | null;
  updated_at: string;
};

export type PrivateLibraryQuestionCandidateList = {
  library_item_id: string;
  source_version: number;
  items: PrivateLibraryQuestionCandidate[];
};

export type PrivateLibraryQuestionCandidateDraft = Pick<
  PrivateLibraryQuestionCandidate,
  | "question_type"
  | "stem_plain"
  | "stem_latex"
  | "options"
  | "answer_value"
  | "solution_method"
  | "solution_steps"
  | "final_answer"
  | "difficulty"
>;

export type CurriculumSearchItem = {
  node_id: string;
  code: string;
  name: string;
  node_type: "knowledge_point";
  volume: string;
  chapter: string | null;
  section: string | null;
  description: string;
  match_score: number;
};

export type CurriculumSearchResult = {
  query: string;
  total: number;
  items: CurriculumSearchItem[];
};

export type PrivateLibraryCandidateImportResult = {
  candidate: PrivateLibraryQuestionCandidate;
  question_id: string;
  already_imported: boolean;
};

export type PrivateLibraryProcessingOptions = {
  signal?: AbortSignal;
  onProgress?: (message: string) => void;
};

export type PrivateLibraryUpload = {
  file: File;
  title: string;
  rightsBasis: LibraryRightsBasis;
  rightsStatement: string;
  rightsAcknowledged: true;
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

  uploadQuestionMedia(
    request: QuestionMediaUpload,
    signal?: AbortSignal,
  ): Promise<QuestionInputBundle>;

  transformQuestionMedia(
    assetId: string,
    transform: QuestionMediaTransform,
    signal?: AbortSignal,
  ): Promise<QuestionInputBundle>;

  recognizeQuestionMedia(
    assetId: string,
    request: QuestionRecognitionRequest,
    signal?: AbortSignal,
  ): Promise<QuestionInputBundle>;

  reviewQuestionRecognition(
    assetId: string,
    request: QuestionRecognitionReview,
    signal?: AbortSignal,
  ): Promise<QuestionInputBundle>;

  listPrivateLibrary(signal?: AbortSignal): Promise<PrivateLibraryList>;

  searchPrivateLibrary(
    query: string,
    privateContentConsent: true,
    signal?: AbortSignal,
  ): Promise<PrivateLibrarySearchResult>;

  getPrivateLibraryItem(
    itemId: string,
    signal?: AbortSignal,
  ): Promise<LibraryItemDetail>;

  listPrivateLibraryRevisions(
    itemId: string,
    signal?: AbortSignal,
  ): Promise<LibraryTextRevisionList>;

  uploadPrivateLibrary(
    request: PrivateLibraryUpload,
    signal?: AbortSignal,
  ): Promise<LibraryItemSummary>;

  reviewPrivateLibraryText(
    itemId: string,
    request: PrivateLibraryReview,
    signal?: AbortSignal,
  ): Promise<LibraryItemDetail>;

  processPrivateLibraryOCR(
    itemId: string,
    request: PrivateLibraryOCRRequest,
    options?: PrivateLibraryProcessingOptions,
  ): Promise<PrivateLibraryOCRResult>;

  listPrivateLibraryQuestionCandidates(
    itemId: string,
    signal?: AbortSignal,
  ): Promise<PrivateLibraryQuestionCandidateList>;

  preparePrivateLibraryQuestionCandidates(
    itemId: string,
    signal?: AbortSignal,
  ): Promise<PrivateLibraryQuestionCandidateList>;

  updatePrivateLibraryQuestionCandidate(
    itemId: string,
    candidateId: string,
    draft: PrivateLibraryQuestionCandidateDraft,
    signal?: AbortSignal,
  ): Promise<PrivateLibraryQuestionCandidate>;

  searchCurriculum(
    query: string,
    signal?: AbortSignal,
  ): Promise<CurriculumSearchResult>;

  mapPrivateLibraryQuestionCandidateCurriculum(
    itemId: string,
    candidateId: string,
    nodeId: string,
    signal?: AbortSignal,
  ): Promise<PrivateLibraryQuestionCandidate>;

  importPrivateLibraryQuestionCandidate(
    itemId: string,
    candidateId: string,
    signal?: AbortSignal,
  ): Promise<PrivateLibraryCandidateImportResult>;
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
