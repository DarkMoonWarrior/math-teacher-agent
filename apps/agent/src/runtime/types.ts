/**
 * 产品级 TeacherAgentRuntime 词汇表（math-teacher-agent 自有）。
 * 与 FastAPI 侧 apps/api/app/agent_runtime/models.py 保持结构一致。
 * DeepSeek Harness 类型只允许存在于 src/dsh/ 内部。
 */

export const ERROR_CODES = [
  "RUNTIME_UNAVAILABLE",
  "MODEL_UNAVAILABLE",
  "TOOL_TIMEOUT",
  "TOOL_UNAUTHORIZED",
  "PRIVATE_CONSENT_REQUIRED",
  "TOOL_NOT_FOUND",
  "TOOL_VALIDATION_ERROR",
  "TOOL_EXECUTION_ERROR",
  "VERIFICATION_FAILED",
  "VERIFICATION_INCONCLUSIVE",
  "RUN_CANCELLED",
  "UNSUPPORTED_CAPABILITY",
  "SEARCH_PLAN_EXHAUSTED",
  "INTERNAL_ERROR",
] as const;

export type TeacherAgentErrorCode = (typeof ERROR_CODES)[number];

export interface TeacherAgentError {
  code: TeacherAgentErrorCode;
  message: string;
  request_id: string;
  retryable?: boolean;
}

export type TeacherAgentRunStatus = "pending" | "running" | "completed" | "failed" | "cancelled";
export type TeacherAgentSessionStatus = "idle" | "running" | "cancelled" | "failed";

export type TeacherAgentEventType =
  | "run_started"
  | "assistant_delta"
  | "tool_started"
  | "tool_finished"
  | "run_completed"
  | "run_failed"
  | "run_cancelled";

export interface TeacherAgentToolCall {
  tool_name: string;
  status: string;
  input: Record<string, unknown>;
  output?: Record<string, unknown> | null;
  error?: TeacherAgentError | null;
  started_at: number;
  finished_at: number;
}

export interface TeacherAgentRunRequest {
  user_message: string;
  session_id?: string | null;
  request_id?: string;
  teacher_user_id?: string | null;
  tenant_id?: string | null;
}

export interface TeacherAgentRunResult {
  run_id: string;
  session_id: string;
  request_id: string;
  runtime: string;
  status: TeacherAgentRunStatus;
  final_text: string;
  tool_calls: TeacherAgentToolCall[];
  error?: TeacherAgentError | null;
}

export interface TeacherAgentEvent {
  type: TeacherAgentEventType;
  run_id: string;
  session_id: string;
  request_id: string;
  data?: Record<string, unknown>;
  sequence: number;
  created_at: number;
}

export interface TeacherAgentSession {
  session_id: string;
  runtime: string;
  status: TeacherAgentSessionStatus;
  created_at: number;
  updated_at: number;
  run_ids: string[];
  teacher_user_id?: string | null;
  tenant_id?: string | null;
}

export interface TeacherAgentCapabilities {
  run: boolean;
  stream: boolean;
  cancel: boolean;
  resume: boolean;
  get_session: boolean;
  health: boolean;
  model_configured: boolean;
  visible_tool_names: string[];
  runtime_version: string;
}

export interface TeacherAgentHealth {
  status: string;
  runtime: string;
  initialized: boolean;
  model_configured: boolean;
  tool_registry_ready: boolean;
  visible_tool_count: number;
  runtime_version: string;
  dsh_version?: string | null;
}

export interface TeacherAgentRuntime {
  readonly runtimeName: string;
  readonly runtimeVersion: string;
  run(request: TeacherAgentRunRequest): Promise<TeacherAgentRunResult>;
  stream(request: TeacherAgentRunRequest): AsyncIterable<TeacherAgentEvent>;
  cancel(runId: string): Promise<TeacherAgentRunResult>;
  resume(sessionId: string, request: TeacherAgentRunRequest): Promise<TeacherAgentRunResult>;
  getSession(sessionId: string): Promise<TeacherAgentSession>;
  health(): Promise<TeacherAgentHealth>;
  capabilities(): Promise<TeacherAgentCapabilities>;
}

export function isTeacherAgentErrorCode(value: string): value is TeacherAgentErrorCode {
  return (ERROR_CODES as readonly string[]).includes(value);
}

export function errorResult(
  code: TeacherAgentErrorCode,
  message: string,
  requestId: string,
  sessionId = "",
): TeacherAgentRunResult {
  return {
    run_id: `run_${crypto.randomUUID().replaceAll("-", "")}`,
    session_id: sessionId,
    request_id: requestId,
    runtime: "dsh",
    status: code === "RUN_CANCELLED" ? "cancelled" : "failed",
    final_text: "",
    tool_calls: [],
    error: { code, message, request_id: requestId },
  };
}
