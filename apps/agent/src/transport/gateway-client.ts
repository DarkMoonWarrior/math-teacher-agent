/**
 * Agent -> FastAPI Internal Tool Gateway 的唯一 HTTP 客户端。
 *
 * 安全边界（Prompt 2 §19）：
 *   - origin 只能来自配置（MATH_AI_API_INTERNAL_URL），绝不由模型/用户提供。
 *   - 只能请求固定 route（/internal/agent-tools/v1/*），不存在任意 URL 能力。
 *   - 请求必须携带 M2M Bearer token 与 X-Request-Id。
 *   - 所有请求转发调用方 AbortSignal；取消必须能中止在途 HTTP 请求。
 *   - 本目录（及整个 apps/agent）禁止任何数据库 import / 文件路径。
 */
import type { TeacherAgentError, TeacherAgentErrorCode } from "../runtime/types.js";

export interface GatewayRequestOptions {
  signal?: AbortSignal;
  requestId: string;
  timeoutMs?: number;
}

export type GatewayResult<T> =
  | { ok: true; data: T; request_id: string }
  | { ok: false; error: TeacherAgentError };

export interface SearchQuestionsInput {
  query?: string;
  chapter?: string | null;
  difficulty?: number | null;
  knowledge_point_id?: string | null;
  limit?: number;
}

export interface SearchQuestionItem {
  question_id: string;
  stem: string;
  question_type: string;
  knowledge_points: string[];
  difficulty: number;
  verification_status: string;
  source_status: string;
  visibility: string;
}

export interface SearchQuestionsResponse {
  items: SearchQuestionItem[];
  total: number;
  truncated: boolean;
  query_interpretation: Record<string, unknown> | null;
  request_id: string;
}

export interface GetQuestionResponse {
  question_id: string;
  stem: string;
  question_type: string;
  answer: string | null;
  solution_steps: string[];
  verification_status: string;
  visibility: string;
  source_status: string;
  request_id: string;
}

export type SolutionMode = "standard" | "alternative";

export interface SolveQuestionInput {
  question_text: string;
  solution_mode?: SolutionMode;
  teacher_instruction?: string;
  capture_grant?: string;
}

export interface SolveQuestionResponse {
  question_text: string;
  solution_mode: SolutionMode;
  explanation: {
    method: string;
    steps: string[];
    final_answer: string;
  };
  knowledge_points: string[];
  common_mistakes: string[];
  teaching_notes: string[];
  confidence_status: "program_verified" | "model_reviewed" | "teacher_review_required";
  math_verification: {
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
  request_id: string;
}

export interface SimilarQuestionItem {
  question_id: string;
  stem: string;
  relation: string;
  confidence: number;
  status: string;
}

export interface FindSimilarQuestionsResponse {
  items: SimilarQuestionItem[];
  total: number;
  truncated: boolean;
  request_id: string;
}

export interface VerifyQuestionResponse {
  question_id: string;
  stored_status: string;
  capability: string;
  computed_answer: string | null;
  method: string | null;
  details: string[];
  fresh_verification: Record<string, unknown> | null;
  request_id: string;
}

export interface GetCurriculumNodeResponse {
  node_id: string;
  parent_id: string | null;
  volume: string;
  node_type: string;
  code: string;
  name: string;
  description: string;
  knowledge_points: string[];
  request_id: string;
}

export interface InspectPrivateLibraryResponse {
  total: number;
  pending_review: number;
  confirmed: number;
  needs_ocr: number;
  trashed: number;
  by_file_kind: Record<string, number>;
  visibility: "private";
  content_included: false;
  request_id: string;
}

export interface SearchPrivateLibraryInput {
  query: string;
  consent_token: string;
  limit?: number;
}

export interface PrivateLibrarySearchItem {
  library_item_id: string;
  title: string;
  excerpt: string;
  source_version: number;
  rights_basis: "original" | "licensed" | "private_teaching_only";
  text_review_status: "confirmed";
  visibility: "private";
}

export interface SearchPrivateLibraryResponse {
  query: string;
  items: PrivateLibrarySearchItem[];
  total: number;
  truncated: boolean;
  content_scope: "matching_excerpts";
  visibility: "private";
  request_id: string;
}

export interface CreateQuestionDraftInput {
  request_text: string;
  grade?: "高一" | "高二" | "高三";
  curriculum_node_id?: string;
  knowledge_point_query?: string;
  question_type?: "single_choice" | "multiple_choice" | "fill_blank" | "open_response";
  target_difficulty?: number;
  teaching_purpose?: string;
  expected_minutes?: number;
  assessed_method?: string;
  misconception_requirements?: string;
  additional_constraints?: string;
  reference_question_id?: string;
}

export interface CreateQuestionDraftResponse {
  draft: Record<string, unknown>;
  request_id: string;
}

const KNOWN_STATUS_ERROR_CODES: Record<number, TeacherAgentErrorCode> = {
  401: "TOOL_UNAUTHORIZED",
  403: "TOOL_UNAUTHORIZED",
  404: "TOOL_NOT_FOUND",
  422: "TOOL_VALIDATION_ERROR",
  503: "MODEL_UNAVAILABLE",
  504: "TOOL_TIMEOUT",
};

export class ToolGatewayError extends Error {
  constructor(
    readonly error: TeacherAgentError,
    options?: ErrorOptions,
  ) {
    super(`tool gateway ${error.code}: ${error.message}`, options);
    this.name = "ToolGatewayError";
  }
}

export class ToolGatewayClient {
  readonly origin: string;
  private readonly token: string;
  private readonly defaultTimeoutMs: number;

  constructor(options: { origin: string; token: string; timeoutMs: number }) {
    this.origin = options.origin.replace(/\/+$/, "");
    this.token = options.token;
    this.defaultTimeoutMs = options.timeoutMs;
  }

  private async post<T>(
    route: string,
    body: unknown,
    options: GatewayRequestOptions,
  ): Promise<GatewayResult<T>> {
    const timeoutMs = options.timeoutMs ?? this.defaultTimeoutMs;
    const signals: AbortSignal[] = [];
    if (options.signal) signals.push(options.signal);
    if (Number.isFinite(timeoutMs) && timeoutMs > 0) {
      signals.push(AbortSignal.timeout(timeoutMs));
    }
    const signal = signals.length > 1 ? AbortSignal.any(signals) : (signals[0] ?? undefined);
    try {
      const response = await fetch(`${this.origin}${route}`, {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-request-id": options.requestId,
          ...(this.token ? { authorization: `Bearer ${this.token}` } : {}),
        },
        body: JSON.stringify(body),
        signal,
      });
      const text = await response.text();
      let payload: unknown = null;
      try {
        payload = text ? JSON.parse(text) : null;
      } catch {
        payload = null;
      }
      if (!response.ok) {
        const error = this.errorFromResponse(response.status, payload, options.requestId);
        return { ok: false, error };
      }
      if (payload === null || typeof payload !== "object") {
        return {
          ok: false,
          error: {
            code: "TOOL_EXECUTION_ERROR",
            message: "网关返回了无法解析的响应",
            request_id: options.requestId,
          },
        };
      }
      const requestId = typeof (payload as { request_id?: unknown }).request_id === "string"
        ? ((payload as { request_id: string }).request_id)
        : options.requestId;
      return { ok: true, data: payload as T, request_id: requestId };
    } catch (cause) {
      if (options.signal?.aborted || (cause instanceof Error && cause.name === "AbortError")) {
        // 调用方取消：原样抛出 AbortError，由 DSH 工具管线将结果归一为 ABORTED。
        // DSH exec.signal 中止时 fetch 的 rejection reason 可能不是标准 AbortError，
        // 因此以调用方 signal.aborted 为准。
        const abortError = new Error("aborted");
        abortError.name = "AbortError";
        throw abortError;
      }
      if (cause instanceof Error && cause.name === "TimeoutError") {
        return {
          ok: false,
          error: { code: "TOOL_TIMEOUT", message: "工具调用超时", request_id: options.requestId },
        };
      }
      throw new ToolGatewayError(
        {
          code: "TOOL_EXECUTION_ERROR",
          message: "内部工具网关不可达",
          request_id: options.requestId,
        },
        { cause },
      );
    }
  }

  private errorFromResponse(status: number, payload: unknown, requestId: string): TeacherAgentError {
    if (payload !== null && typeof payload === "object") {
      const code = (payload as { code?: unknown }).code;
      const message = (payload as { message?: unknown }).message;
      const payloadRequestId = (payload as { request_id?: unknown }).request_id;
      if (typeof code === "string" && typeof message === "string") {
        return {
          code: code as TeacherAgentErrorCode,
          message: String(message).slice(0, 500),
          request_id: typeof payloadRequestId === "string" ? payloadRequestId : requestId,
        };
      }
      const error = (payload as { error?: { code?: unknown; message?: unknown; request_id?: unknown } }).error;
      if (error && typeof error === "object" && typeof error.code === "string") {
        return {
          code: error.code as TeacherAgentErrorCode,
          message: String(error.message ?? "网关错误").slice(0, 500),
          request_id: typeof error.request_id === "string" ? error.request_id : requestId,
        };
      }
    }
    const code = KNOWN_STATUS_ERROR_CODES[status] ?? "TOOL_EXECUTION_ERROR";
    const message = status === 401 || status === 403
      ? "内部工具网关认证失败"
      : status === 404
        ? "内部工具网关路由不存在"
        : status === 422
          ? "工具参数校验失败"
          : `内部工具网关返回 ${status}`;
    return { code, message, request_id: requestId };
  }

  searchQuestions(input: SearchQuestionsInput, options: GatewayRequestOptions): Promise<GatewayResult<SearchQuestionsResponse>> {
    return this.post("/internal/agent-tools/v1/search-questions", input, options);
  }

  getQuestion(questionId: string, options: GatewayRequestOptions): Promise<GatewayResult<GetQuestionResponse>> {
    return this.post("/internal/agent-tools/v1/get-question", { question_id: questionId }, options);
  }

  solveQuestion(input: SolveQuestionInput, options: GatewayRequestOptions): Promise<GatewayResult<SolveQuestionResponse>> {
    return this.post("/internal/agent-tools/v1/solve-question", input, options);
  }

  findSimilarQuestions(input: { question_id: string; limit?: number }, options: GatewayRequestOptions): Promise<GatewayResult<FindSimilarQuestionsResponse>> {
    return this.post("/internal/agent-tools/v1/find-similar-questions", input, options);
  }

  verifyQuestion(questionId: string, options: GatewayRequestOptions): Promise<GatewayResult<VerifyQuestionResponse>> {
    return this.post("/internal/agent-tools/v1/verify-question", { question_id: questionId }, options);
  }

  getCurriculumNode(nodeId: string, options: GatewayRequestOptions): Promise<GatewayResult<GetCurriculumNodeResponse>> {
    return this.post("/internal/agent-tools/v1/get-curriculum-node", { node_id: nodeId }, options);
  }

  inspectPrivateLibrary(options: GatewayRequestOptions): Promise<GatewayResult<InspectPrivateLibraryResponse>> {
    return this.post("/internal/agent-tools/v1/inspect-private-library", {}, options);
  }

  searchPrivateLibrary(input: SearchPrivateLibraryInput, options: GatewayRequestOptions): Promise<GatewayResult<SearchPrivateLibraryResponse>> {
    return this.post("/internal/agent-tools/v1/search-private-library", input, options);
  }

  createQuestionDraft(input: CreateQuestionDraftInput, options: GatewayRequestOptions): Promise<GatewayResult<CreateQuestionDraftResponse>> {
    return this.post("/internal/agent-tools/v1/create-question-draft", input, options);
  }
}
