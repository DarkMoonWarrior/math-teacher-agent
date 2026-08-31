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
  visual_observations: string[];
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

export type PrivateLibraryQuestionExtractionRequest = {
  externalProcessingConsent: boolean;
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

export type QuestionAuthoringEntrySource = "new_task" | "search" | "paper";

export type QuestionAuthoringBrief = {
  requestText: string;
  grade?: "高一" | "高二" | "高三";
  curriculumNodeId?: string;
  knowledgePointQuery?: string;
  questionType?: "single_choice" | "multiple_choice" | "fill_blank" | "open_response";
  targetDifficulty: number;
  teachingPurpose: string;
  expectedMinutes?: number;
  assessedMethod?: string;
  misconceptionRequirements?: string;
  additionalConstraints?: string;
  referenceQuestionId?: string;
  sessionId?: string;
};

export type QuestionAuthoringProgressStage =
  | "brief"
  | "composing"
  | "reauthoring"
  | "reviewing"
  | "refining"
  | "solving"
  | "reviewing_solution"
  | "regenerating_solution"
  | "staging";

export type QuestionAuthoringGenerationOptions = {
  signal?: AbortSignal;
  onProgress?: (stage: QuestionAuthoringProgressStage) => void;
};

export type QuestionDraftOption = {
  key: string;
  text: string;
};

export type QuestionAuthoringStatementPreview = {
  question_type: "single_choice" | "multiple_choice" | "fill_blank" | "open_response";
  stem_plain: string;
  stem_latex: string | null;
  options: QuestionDraftOption[];
  estimated_difficulty: number;
};

export type QuestionAuthoringProgress = {
  stage: QuestionAuthoringProgressStage;
  elapsed_seconds: number;
  statement: QuestionAuthoringStatementPreview | null;
  statement_revision: number;
  statement_state: "pending" | "approved" | "adjusting";
};

export type QuestionDraftEditableContent = {
  question_type: "single_choice" | "multiple_choice" | "fill_blank" | "open_response";
  stem_plain: string;
  stem_latex: string | null;
  options: QuestionDraftOption[];
  answer_value: string;
  solution_method: string;
  solution_steps: string[];
  final_answer: string;
  authoring_intent: string;
  knowledge_points: string[];
  assessed_methods: string[];
  common_mistakes: string[];
  curriculum_confirmation_node_id?: string | null;
};

export type QuestionDraftTrustCheck = {
  code: "solvability" | "answer_solution_consistency" | "choice_answer_cardinality" | "distractor_quality" | "math_verifier" | "difficulty_disclosure";
  status: "passed" | "failed" | "inconclusive" | "not_applicable";
  capability: "supported" | "unsupported";
  evidence_source: "deterministic_structure" | "math_verifier" | "model_estimate" | "none";
  summary: string;
  details: string[];
};

export type GeneratedQuestionDraft = QuestionDraftEditableContent & {
  draft_id: string;
  request_text: string;
  curriculum: {
    node_id: string;
    name: string;
    volume: string;
    chapter: string;
    section: string;
    mapping_source: "teacher_selected" | "brief_match" | "agent_inferred";
    mapping_status: "teacher_confirmed" | "pending_teacher_confirmation";
    match_confidence: number | null;
    curriculum_status: string;
    reviewed_by: string;
  } | null;
  pedagogy_source: "model_generated" | "teacher_edited";
  solution_status?: "ready" | "needs_teacher_verification";
  solution_issue?: string | null;
  target_difficulty: number;
  estimated_difficulty: number;
  difficulty_source: "model_estimated";
  verification: {
    status: "checks_failed" | "teacher_review_required";
    math_verifier_status: "unsupported" | "passed" | "failed" | "inconclusive";
    math_verifier_checked: boolean;
    teacher_review_required: true;
    verifier_version: string;
    checks: QuestionDraftTrustCheck[];
    details: string[];
  };
  source_type: "ai_generated";
  visibility: "owner_only";
  public_search_allowed: false;
  share_allowed: false;
  commercial_use_allowed: false;
  model_training_allowed: false;
  saved: boolean;
  provider: string;
  model: string;
  prompt_revision: string;
  warnings: string[];
  created_at: string;
};

export type QuestionAuthoringAgentResult = {
  request_id: string;
  session_id: string;
  run_id: string;
  status: "ok" | "error" | "cancelled";
  draft: GeneratedQuestionDraft | null;
  tool_request_id: string;
  tool_call_count: number;
  error: { code?: string; message?: string; request_id?: string } | null;
};

export type QuestionAuthoringJob = {
  job_id: string;
  kind: "question_authoring";
  subject_id: string;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  current: number;
  total: number;
  message: string;
  error: string;
  result: {
    draft_id?: string;
    request_id?: string;
    statement?: QuestionAuthoringStatementPreview;
    statement_revision?: number;
    statement_preserved?: boolean;
    solution_missing?: boolean;
  };
  created_at: string;
  updated_at: string;
};

export type OwnerOnlyPolicy = {
  visibility: "owner_only";
  public_search_allowed: false;
  share_allowed: false;
  commercial_use_allowed: false;
  model_training_allowed: false;
};

export type PersonalQuestionCollection = OwnerOnlyPolicy & {
  collection_id: string;
  name: string;
  description: string;
  category_count: number;
  question_count: number;
  created_at: string;
  updated_at: string;
};

export type PersonalQuestionCollectionList = { items: PersonalQuestionCollection[]; total: number };

export type PersonalQuestionCategory = OwnerOnlyPolicy & {
  category_id: string;
  collection_id: string;
  name: string;
  description: string;
  sort_order: number;
  question_count: number;
  created_at: string;
  updated_at: string;
};

export type PersonalQuestionCategoryList = {
  collection_id: string;
  items: PersonalQuestionCategory[];
  total: number;
};

export type PersonalAuthoringRevision = {
  draft_id: string;
  revision_number: number;
  revision_source: "ai_generated" | "teacher_edit";
  edit_summary: string;
  draft: GeneratedQuestionDraft;
  created_at: string;
};

export type PersonalAuthoringDraft = OwnerOnlyPolicy & {
  draft_id: string;
  current_revision: number;
  saved: boolean;
  saved_question_id: string | null;
  current: PersonalAuthoringRevision;
  created_at: string;
  updated_at: string;
};

export type PersonalAuthoringDraftList = {
  items: PersonalAuthoringDraft[];
  total: number;
  limit: number;
  offset: number;
};

export type PersonalAuthoringHistoryDeletionReceipt = {
  draft_id: string;
  deleted: true;
  saved_question_preserved: boolean;
};

export type PersonalAuthoringRevisionList = {
  draft_id: string;
  current_revision: number;
  items: PersonalAuthoringRevision[];
  total: number;
};

export type PersonalQuestion = OwnerOnlyPolicy & {
  question_id: string;
  collection_id: string;
  category_id: string;
  name: string;
  source_draft_id: string;
  selected_revision: number;
  tags: string[];
  sort_order: number;
  lifecycle_state: "active" | "trashed";
  trashed_at: string | null;
  copied_from_question_id: string | null;
  question: GeneratedQuestionDraft;
  created_at: string;
  updated_at: string;
};

export type PersonalQuestionList = {
  query: string;
  lifecycle_state: "active" | "trashed";
  items: PersonalQuestion[];
  total: number;
  limit: number;
  offset: number;
};

export type PersonalQuestionExport = {
  blob: Blob;
  filename: string;
};

export type LessonBlueprintType = "new_lesson" | "review" | "exercise";

export type LessonBlueprintCurriculumCandidate = {
  node_id: string;
  node_type: "section" | "knowledge_point";
  name: string;
  volume: string;
  chapter: string | null;
  section: string | null;
  description: string;
  competencies: string[];
  common_errors: string[];
  catalog_status: string;
  reviewed_by: string;
  match_score: number;
};

export type LessonBlueprintPhase = {
  phase_id: string;
  title: string;
  minutes: number;
  purpose: string;
};

export type LessonBlueprintDraft = {
  status: "lesson_blueprint_draft";
  editable: true;
  confirmed: false;
  saved: false;
  source_brief: string;
  title: string;
  grade_scope: string;
  lesson_type: LessonBlueprintType;
  lesson_format: string;
  duration_minutes: number;
  student_profile: string;
  focus: string;
  question_count: number;
  curriculum_query: string;
  selected_curriculum_node_id: string | null;
  curriculum_candidates: LessonBlueprintCurriculumCandidate[];
  objectives: string[];
  key_points: string[];
  difficulties: string[];
  phases: LessonBlueprintPhase[];
  required_blocks: Array<
    "objectives" | "key_points" | "difficulties" | "teaching_flow" | "homework" | "board_plan" | "teacher_notes"
  >;
  assumptions: string[];
  trust_policy: {
    curriculum_source: "sealed_pep_a_baseline";
    question_policy: "not_selected_during_planning";
    private_resource_policy: "explicit_owner_selection_only";
    ai_content_status: "draft_requires_teacher_review";
    auto_save_allowed: false;
    preserves_source_traceability: true;
  };
  side_effects: [];
};

export type ConfirmedLessonBlueprint = Omit<LessonBlueprintDraft, "status" | "confirmed"> & {
  status: "lesson_blueprint_confirmed";
  confirmed: true;
};

export type LessonSourceQuestionCandidate = {
  question_id: string;
  source_kind: "public_question_bank" | "personal_question_library";
  name: string;
  question_type: string;
  stem_plain: string;
  options: Array<{ key: string; text: string }>;
  difficulty: number;
  chapter: string | null;
  knowledge_points: string[];
  source_document: string;
  source_revision: number;
  rights_basis: string;
  verification_status: string;
  review_status: string;
  owner_scope: "public_catalog" | "current_owner_only";
};

export type LessonSourceResourceCandidate = {
  library_item_id: string;
  title: string;
  file_kind: "pdf" | "docx" | "image";
  source_version: number;
  rights_basis: "original" | "licensed" | "private_teaching_only";
  text_review_status: "confirmed";
  corrected_char_count: number;
  owner_scope: "current_owner_only";
};

export type LessonSourceOptions = {
  status: "lesson_source_options";
  blueprint: ConfirmedLessonBlueprint;
  public_questions: LessonSourceQuestionCandidate[];
  private_questions: LessonSourceQuestionCandidate[];
  private_resources: LessonSourceResourceCandidate[];
  trust_statement: string;
  side_effects: [];
};

export type LessonSourceDraft = {
  status: "lesson_source_draft";
  editable: true;
  saved: false;
  selection_complete: boolean;
  blueprint: ConfirmedLessonBlueprint;
  curriculum: LessonBlueprintCurriculumCandidate | null;
  questions: LessonSourceQuestionCandidate[];
  private_resources: Array<LessonSourceResourceCandidate & {
    content_excerpt: string;
    rights_statement: string;
  }>;
  gaps: Array<{
    source_kind: "curriculum" | "question";
    required_count: number;
    selected_count: number;
    missing_count: number;
    reason: string;
  }>;
  warnings: string[];
  trust_policy: Record<string, string | boolean>;
  side_effects: [];
};

export type LessonEditableDraft = {
  status: "lesson_editable_draft";
  content_status: "draft_requires_teacher_review";
  editable: true;
  saved: false;
  draft_revision: number;
  title: string;
  source_draft: LessonSourceDraft;
  objectives: Array<{
    objective_id: string;
    text: string;
    observable_evidence: string;
  }>;
  key_points: string[];
  difficulties: string[];
  teaching_flow: Array<{
    phase_id: string;
    title: string;
    minutes: number;
    purpose: string;
    teacher_activity: string;
    student_activity: string;
    assessment: string;
    objective_ids: string[];
    question_ids: string[];
    resource_ids: string[];
  }>;
  questions: Array<{
    question_id: string;
    source_kind: "public_question_bank" | "personal_question_library";
    source_revision: number;
    rights_basis: string;
    verification_status: string;
    review_status: string;
    owner_scope: "public_catalog" | "current_owner_only";
    phase_id: string;
    usage: string;
    stem_plain: string;
    options: Array<{ key: string; text: string }>;
    answer_value: string;
    solution_steps: string[];
    final_answer: string;
  }>;
  assessments: Array<{
    assessment_id: string;
    title: string;
    method: string;
    success_criteria: string;
    objective_ids: string[];
  }>;
  homework: string[];
  board_plan: string[];
  teacher_notes: string[];
  locked_blocks: LessonDraftBlock[];
  rewrite_history: Array<{
    draft_revision: number;
    target_block: LessonDraftBlock;
    instruction: string;
    provider: string;
    model: string;
  }>;
  source_manifest: Array<{
    source_kind: "curriculum" | "public_question" | "private_question" | "private_resource";
    source_id: string;
    source_revision: string;
    rights_basis: string;
    verification_status: string;
    owner_scope: "sealed_catalog" | "public_catalog" | "current_owner_only";
  }>;
  integrity: {
    required_blocks_complete: true;
    time_total_matches: true;
    objective_activity_alignment: true;
    objective_assessment_alignment: true;
    questions_complete: true;
    high_school_scope: true;
    source_traceability_complete: true;
  };
  generation: Record<string, string | boolean>;
  side_effects: [];
};

export type LessonDraftBlock =
  | "objectives"
  | "key_points"
  | "difficulties"
  | "teaching_flow"
  | "questions"
  | "assessments"
  | "homework"
  | "board_plan"
  | "teacher_notes";

export type LessonSavedVersion = {
  status: "saved_lesson_version";
  saved: true;
  lesson_plan_id: string;
  version: number;
  title: string;
  content_status: "draft_requires_teacher_review";
  owner_scope: "current_owner_only";
  lifecycle_state: "active" | "trashed";
  draft_fingerprint: string;
  draft: LessonEditableDraft;
  created_at: string;
  saved_at: string;
  available_exports: Array<{
    format: "docx" | "pdf";
    label: string;
  }>;
  side_effects: ["created_lesson_plan_version"];
};

export type LessonVersionHistoryItem = {
  lesson_plan_id: string;
  title: string;
  version: number;
  duration_minutes: number;
  lesson_type: LessonBlueprintType;
  updated_at: string;
  lifecycle_state: "active" | "trashed";
  trashed_at: string | null;
};

export type LessonVersionHistoryList = {
  items: LessonVersionHistoryItem[];
  total: number;
};

export type PaperBlueprintDifficulty = "foundation" | "balanced" | "challenge";
export type PaperBlueprintQuestionType = "single_choice" | "multiple_choice" | "fill_blank" | "open_response";

export type PaperBlueprintSection = {
  section_id: string;
  title: string;
  question_type: PaperBlueprintQuestionType;
  question_count: number;
  target_score: number;
};

export type PaperBlueprintDraft = {
  status: "draft";
  editable: true;
  confirmed: false;
  saved: false;
  source_brief: string;
  title: string;
  grade_scope: string;
  teaching_usage: string;
  duration_minutes: number;
  target_score: number;
  difficulty_profile: PaperBlueprintDifficulty;
  knowledge_points: string[];
  sections: PaperBlueprintSection[];
  assumptions: string[];
  trust_policy: {
    verification_policy: "passed_only";
    review_policy: "approved_only" | "verified";
    private_question_policy: "explicit_owner_selection_only";
    auto_authoring_allowed: false;
    preserves_source_and_rights: true;
  };
  side_effects: [];
};

export type PaperSelectionOption = { key: string; text: string };

export type PaperPublicQuestionCandidate = {
  question_id: string;
  question_type: string;
  stem_plain: string;
  options: PaperSelectionOption[];
  difficulty: number;
  chapter: string | null;
  knowledge_points: string[];
  source_document: string;
};

export type PaperPublicQuestionCandidateList = {
  items: PaperPublicQuestionCandidate[];
  total: number;
  trust_statement: string;
  side_effects: [];
};

export type PaperSelectionItem = {
  section_id: string;
  section_title: string;
  position: number;
  question_id: string;
  source_kind: "public_question_bank" | "personal_question_library";
  question_type: string;
  stem_plain: string;
  options: PaperSelectionOption[];
  score: number;
  difficulty: number;
  chapter: string | null;
  knowledge_points: string[];
  source_document: string;
  source_page_start: number | null;
  source_page_end: number | null;
  license_status: string;
  revision_count: number;
  verification_status: string;
  review_status: string;
  visibility: string;
  owner_scope: "public_catalog" | "current_owner_only";
  solution_status?: "ready" | "needs_teacher_verification";
  solution_issue?: string | null;
  source_preserved: true;
  copied: false;
  selection_reason: string;
};

export type PaperSelectionGap = {
  section_id: string;
  section_title: string;
  question_type: PaperBlueprintQuestionType;
  required_count: number;
  selected_count: number;
  missing_count: number;
  missing_score: number;
  reason: string;
  suggestions: string[];
};

export type PaperBlueprintCoverageAudit = {
  status: "matched" | "needs_adjustment";
  coverage_complete: boolean;
  difficulty_status: "matched" | "deviated" | "insufficient_supply";
  target_average_difficulty: number;
  actual_average_difficulty: number | null;
  average_difficulty_gap: number | null;
  sections: Array<{
    section_id: string;
    section_title: string;
    target_question_count: number;
    actual_question_count: number;
    target_score: number;
    actual_score: number;
    status: "met" | "short";
  }>;
  knowledge_points: Array<{
    knowledge_point: string;
    actual_question_count: number;
    actual_score: number;
    status: "covered" | "missing";
  }>;
  difficulty_bands: Array<{
    difficulty: number;
    target_question_count: number;
    actual_question_count: number;
    actual_score: number;
  }>;
  side_effects: [];
};

export type PaperBlueprintSelectionDraft = {
  status: "selection_draft";
  blueprint_confirmed: true;
  editable: true;
  saved: false;
  selection_complete: boolean;
  blueprint: Omit<PaperBlueprintDraft, "status" | "editable" | "confirmed" | "saved" | "source_brief" | "assumptions" | "trust_policy" | "side_effects">;
  target_question_count: number;
  actual_question_count: number;
  target_score: number;
  actual_score: number;
  items: PaperSelectionItem[];
  gaps: PaperSelectionGap[];
  coverage_audit: PaperBlueprintCoverageAudit;
  similarity_exclusions: Array<{
    question_id: string;
    matched_question_id: string;
    relation: "exact_duplicate" | "variant";
    confidence: number;
    reason: string;
  }>;
  unselected_public_question_ids: string[];
  unselected_private_question_ids: string[];
  warnings: string[];
  trust_policy: PaperBlueprintDraft["trust_policy"];
  auto_authoring_used: false;
  side_effects: [];
};

export type PaperDraftItemEdit = {
  question_id: string;
  position: number;
  section_id: string;
  score: number;
};

export type PaperDraftChange = {
  question_id: string;
  kind: "position" | "section" | "score";
  before: string;
  after: string;
  description: string;
};

export type PaperEditableDraft = {
  status: "editable_paper_draft";
  editable: true;
  saved: false;
  version_created: false;
  export_ready: false;
  draft_fingerprint: string;
  selection_complete: boolean;
  draft_consistent: boolean;
  score_status: "matched" | "mismatch";
  blueprint: PaperBlueprintSelectionDraft["blueprint"];
  target_question_count: number;
  actual_question_count: number;
  target_score: number;
  actual_score: number;
  items: PaperSelectionItem[];
  gaps: PaperSelectionGap[];
  coverage_audit: PaperBlueprintCoverageAudit;
  change_log: PaperDraftChange[];
  specification: {
    question_to_dimensions: Array<{
      position: number;
      question_id: string;
      section_title: string;
      question_type: string;
      chapter: string;
      knowledge_points: string[];
      difficulty: number;
      score: number;
      verification_status: string;
      review_status: string;
      source_kind: "public_question_bank" | "personal_question_library";
    }>;
    dimension_to_questions: Array<{
      dimension: "section" | "question_type" | "knowledge_point" | "difficulty";
      label: string;
      positions: number[];
      question_ids: string[];
      question_count: number;
      score: number;
    }>;
  };
  warnings: string[];
  trust_policy: PaperBlueprintDraft["trust_policy"];
  auto_authoring_used: false;
  side_effects: [];
};

export type PaperSavedVersion = {
  status: "saved_paper_version";
  saved: true;
  version_created: true;
  export_ready: true;
  exam_paper_id: string;
  version: number;
  title: string;
  question_count: number;
  total_score: number;
  draft_fingerprint: string;
  specification: PaperEditableDraft["specification"];
  available_exports: Array<{
    edition: "student" | "answer" | "blueprint";
    format: "docx" | "pdf";
    label: string;
  }>;
  saved_at: string;
  side_effects: ["created_exam_paper_version"];
};

export type PaperHistoryItem = {
  exam_paper_id: string;
  title: string;
  status: string;
  version: number;
  duration_minutes: number;
  total_score: number;
  question_count: number;
  updated_at: string;
  lifecycle_state: "active" | "trashed";
  trashed_at: string | null;
};

export type PaperHistoryList = {
  items: PaperHistoryItem[];
  total: number;
};

export type PaperHistoryPaperItem = {
  item_id: string;
  position: number;
  section_id: string | null;
  section_title: string;
  score: number;
  added_source_kind?: "public_question_bank" | "personal_question_library";
  question: {
    question_id: string;
    question_type: string;
    stem_plain: string;
    stem_latex: string | null;
    options: Array<{ key: string; text: string }>;
    difficulty: number;
    answer_value?: string | null;
    solution_method?: string | null;
    solution_steps?: string[];
    final_answer?: string | null;
    solution_status?: "ready" | "needs_teacher_verification";
    solution_issue?: string | null;
  };
};

export type PaperHistoryPaper = {
  exam_paper_id: string;
  status: "draft";
  version: number;
  title: string;
  duration_minutes: number;
  instructions: string;
  total_score: number;
  items: PaperHistoryPaperItem[];
  updated_at: string;
  lifecycle_state: "active" | "trashed";
};

export type PaperHistoryRevisionRequest = {
  expected_version: number;
  title: string;
  duration_minutes: number;
  instructions: string;
  target_total_score?: number;
  selected_public_question_ids?: string[];
  selected_private_question_ids?: string[];
  items: Array<{
    question_id: string;
    section_id: string | null;
    section_title: string;
    score: number;
  }>;
};

export type PaperExportArtifact = {
  blob: Blob;
  filename: string;
};

export interface TeacherWorkspace {
  planLessonBlueprint(brief: string, signal?: AbortSignal): Promise<LessonBlueprintDraft>;
  listLessonSourceOptions(
    blueprint: LessonBlueprintDraft,
    signal?: AbortSignal,
  ): Promise<LessonSourceOptions>;
  selectLessonSources(
    blueprint: ConfirmedLessonBlueprint,
    selectedPublicQuestionIds: string[],
    selectedPrivateQuestionIds: string[],
    selectedPrivateResourceIds: string[],
    signal?: AbortSignal,
  ): Promise<LessonSourceDraft>;
  buildLessonDraft(
    sourceDraft: LessonSourceDraft,
    signal?: AbortSignal,
  ): Promise<LessonEditableDraft>;
  rewriteLessonDraftBlock(
    draft: LessonEditableDraft,
    targetBlock: LessonDraftBlock,
    instruction: string,
    signal?: AbortSignal,
  ): Promise<LessonEditableDraft>;
  saveLessonVersion(
    draft: LessonEditableDraft,
    lessonPlanId?: string | null,
    signal?: AbortSignal,
  ): Promise<LessonSavedVersion>;
  listLessonVersionHistory(
    lifecycleState?: "active" | "trashed",
    signal?: AbortSignal,
  ): Promise<LessonVersionHistoryList>;
  getLessonVersion(
    lessonPlanId: string,
    version?: number,
    signal?: AbortSignal,
  ): Promise<LessonSavedVersion>;
  changeLessonVersionLifecycle(
    lessonPlanId: string,
    action: "trash" | "restore",
    signal?: AbortSignal,
  ): Promise<LessonVersionHistoryItem>;
  exportLessonVersion(
    lessonPlanId: string,
    version: number,
    format: "docx" | "pdf",
    signal?: AbortSignal,
  ): Promise<PaperExportArtifact>;
  planPaperBlueprint(brief: string, signal?: AbortSignal): Promise<PaperBlueprintDraft>;
  listPaperPublicCandidates(
    request?: { query?: string; questionType?: PaperBlueprintQuestionType; limit?: number },
    signal?: AbortSignal,
  ): Promise<PaperPublicQuestionCandidateList>;
  selectPaperBlueprint(
    blueprint: PaperBlueprintDraft,
    selectedPrivateQuestionIds: string[],
    selectedPublicQuestionIds: string[],
    signal?: AbortSignal,
  ): Promise<PaperBlueprintSelectionDraft>;
  editPaperDraft(
    blueprint: PaperBlueprintDraft,
    selectedPrivateQuestionIds: string[],
    selectedPublicQuestionIds: string[],
    edits: PaperDraftItemEdit[],
    signal?: AbortSignal,
  ): Promise<PaperEditableDraft>;
  savePaperVersion(
    blueprint: PaperBlueprintDraft,
    selectedPrivateQuestionIds: string[],
    selectedPublicQuestionIds: string[],
    edits: PaperDraftItemEdit[],
    expectedDraftFingerprint: string,
    signal?: AbortSignal,
  ): Promise<PaperSavedVersion>;
  listPaperHistory(
    lifecycleState?: "active" | "trashed",
    signal?: AbortSignal,
  ): Promise<PaperHistoryList>;
  changePaperHistoryLifecycle(
    paperId: string,
    action: "trash" | "restore",
    signal?: AbortSignal,
  ): Promise<PaperHistoryItem>;
  getPaperHistoryPaper(paperId: string, signal?: AbortSignal): Promise<PaperHistoryPaper>;
  revisePaperHistoryPaper(
    paperId: string,
    request: PaperHistoryRevisionRequest,
    signal?: AbortSignal,
  ): Promise<PaperHistoryPaper>;
  exportPaperVersion(
    paperId: string,
    version: number,
    format: "docx" | "pdf",
    edition: "student" | "answer" | "blueprint",
    signal?: AbortSignal,
  ): Promise<PaperExportArtifact>;

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
    request: PrivateLibraryQuestionExtractionRequest,
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

  createQuestionAuthoringDraft(
    request: QuestionAuthoringBrief,
    options?: QuestionAuthoringGenerationOptions,
  ): Promise<QuestionAuthoringAgentResult>;

  startQuestionAuthoringJob(request: QuestionAuthoringBrief, signal?: AbortSignal): Promise<QuestionAuthoringJob>;
  getQuestionAuthoringJob(jobId: string, signal?: AbortSignal): Promise<QuestionAuthoringJob>;
  cancelQuestionAuthoringJob(jobId: string, preserveStatement?: boolean, signal?: AbortSignal, context?: { requestText?: string; targetDifficulty?: number }): Promise<QuestionAuthoringJob>;
  getLatestQuestionAuthoringJob(signal?: AbortSignal): Promise<QuestionAuthoringJob | null>;
  getQuestionAuthoringProgress(progressId: string, signal?: AbortSignal): Promise<QuestionAuthoringProgress>;

  getPersonalAuthoringDraft(draftId: string, signal?: AbortSignal): Promise<PersonalAuthoringDraft>;
  listPersonalAuthoringDrafts(signal?: AbortSignal): Promise<PersonalAuthoringDraftList>;
  deletePersonalAuthoringHistory(draftId: string, signal?: AbortSignal): Promise<PersonalAuthoringHistoryDeletionReceipt>;

  listPersonalAuthoringRevisions(draftId: string, signal?: AbortSignal): Promise<PersonalAuthoringRevisionList>;

  revisePersonalAuthoringDraft(
    draftId: string,
    expectedRevision: number,
    content: QuestionDraftEditableContent,
    editSummary: string,
    signal?: AbortSignal,
  ): Promise<PersonalAuthoringDraft>;

  regeneratePersonalAuthoringSolution(
    draftId: string,
    expectedRevision: number,
    signal?: AbortSignal,
  ): Promise<PersonalAuthoringDraft>;

  savePersonalAuthoringDraft(
    draftId: string,
    request: { expectedRevision: number; collectionId: string; categoryId: string; name: string },
    signal?: AbortSignal,
  ): Promise<PersonalQuestion>;

  listPersonalQuestionCollections(signal?: AbortSignal): Promise<PersonalQuestionCollectionList>;

  createPersonalQuestionCollection(
    name: string,
    description?: string,
    signal?: AbortSignal,
  ): Promise<PersonalQuestionCollection>;

  listPersonalQuestionCategories(collectionId: string, signal?: AbortSignal): Promise<PersonalQuestionCategoryList>;

  createPersonalQuestionCategory(
    collectionId: string,
    name: string,
    description?: string,
    signal?: AbortSignal,
  ): Promise<PersonalQuestionCategory>;

  listPersonalQuestions(
    request: { query?: string; lifecycleState?: "active" | "trashed"; collectionId?: string; categoryId?: string },
    signal?: AbortSignal,
  ): Promise<PersonalQuestionList>;

  revisePersonalQuestion(
    question: PersonalQuestion,
    content: QuestionDraftEditableContent,
    editSummary: string,
    signal?: AbortSignal,
  ): Promise<PersonalQuestion>;

  updatePersonalQuestion(
    question: PersonalQuestion,
    request: { name?: string; collectionId?: string; categoryId?: string; tags?: string[]; sortOrder?: number },
    signal?: AbortSignal,
  ): Promise<PersonalQuestion>;

  copyPersonalQuestion(
    questionId: string,
    request: { collectionId: string; categoryId: string; name?: string },
    signal?: AbortSignal,
  ): Promise<PersonalQuestion>;

  exportPersonalQuestion(
    questionId: string,
    format: "json" | "markdown",
    signal?: AbortSignal,
  ): Promise<PersonalQuestionExport>;

  trashPersonalQuestion(question: PersonalQuestion, signal?: AbortSignal): Promise<PersonalQuestion>;

  restorePersonalQuestion(question: PersonalQuestion, signal?: AbortSignal): Promise<PersonalQuestion>;

  permanentlyDeletePersonalQuestion(
    question: PersonalQuestion,
    confirmation: "永久删除我的私题",
    signal?: AbortSignal,
  ): Promise<{ question_id: string; active_storage_deleted: true; deleted_at: string }>;
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
