import {
  TeacherWorkspace,
  TeacherWorkspaceError,
  type SearchTaskOptions,
  type SearchTaskProgressStage,
  type SearchTaskRequest,
  type SearchTaskResult,
  type SolveTaskOptions,
  type SolveTaskProgressStage,
  type SolveTaskRequest,
  type SolveTaskResult,
} from "./contracts";

const SEARCH_STREAM_ENDPOINT = "/api/v1/agent/search/stream";
const SOLVE_STREAM_ENDPOINT = "/api/v1/agent/solve/stream";
const PROGRESS_ORDER: SearchTaskProgressStage[] = [
  "connecting",
  "understanding",
  "searching",
  "checking",
  "recovering",
];
const SOLVE_PROGRESS_ORDER: SolveTaskProgressStage[] = [
  "connecting",
  "understanding",
  "solving",
  "verifying",
  "recovering",
];

function apiUrl(path: string): string {
  const configured = process.env.NEXT_PUBLIC_MATH_AI_API_URL?.replace(/\/$/, "");
  if (configured) return `${configured}${path}`;
  // Keep the browser on the Teacher Web origin. next.config.ts owns the
  // server-side FastAPI rewrite, so local development does not depend on CORS.
  return path;
}

type ErrorEnvelope = {
  error?: { code?: string; message?: string; request_id?: string };
};

type TaskStreamEvent = {
  type: "run_started" | "assistant_delta" | "tool_started" | "tool_finished" | "run_completed" | "run_failed" | "run_cancelled";
  run_id: string;
  request_id: string;
  data: {
    search_response?: SearchTaskResult;
    solve_response?: SolveTaskResult;
    error?: { code?: string; message?: string; request_id?: string };
  };
};

function abortError(): DOMException {
  return new DOMException("Teacher task cancelled", "AbortError");
}

async function cancelRun(capability: "search" | "solve", runId: string): Promise<void> {
  try {
    await fetch(apiUrl(`/api/v1/agent/${capability}/${encodeURIComponent(runId)}/cancel`), {
      method: "POST",
      keepalive: true,
    });
  } catch {
    // Closing the stream is itself a server-side cancellation signal. This
    // request is the explicit best-effort path when the run_id is known.
  }
}

async function responseError(response: Response): Promise<TeacherWorkspaceError> {
  let payload: ErrorEnvelope = {};
  try {
    payload = (await response.json()) as ErrorEnvelope;
  } catch {
    // Fall through to the stable HTTP error below.
  }
  return new TeacherWorkspaceError(
    payload.error?.code ?? `HTTP_${response.status}`,
    payload.error?.message ?? `任务未完成（HTTP ${response.status}）。`,
    payload.error?.request_id ?? "",
  );
}

type SearchStreamContext = {
  runId: string;
  requestId: string;
  reportProgress: (stage: SearchTaskProgressStage) => void;
};

function isRecoverableStreamFailure(cause: unknown): boolean {
  if (cause instanceof TeacherWorkspaceError) {
    return cause.code === "STREAM_INTERRUPTED" || cause.code === "STREAM_INVALID";
  }
  return !(cause instanceof DOMException && cause.name === "AbortError");
}

function isSnapshotTransportFailure(cause: TeacherWorkspaceError): boolean {
  return cause.code.startsWith("STREAM_")
    || cause.code.startsWith("HTTP_")
    || cause.code === "RUN_NOT_FOUND"
    || cause.code === "FEATURE_DISABLED";
}

async function readSearchStream(
  response: Response,
  context: SearchStreamContext,
  signal?: AbortSignal,
): Promise<SearchTaskResult> {
  if (!response.ok) throw await responseError(response);
  if (!response.headers.get("content-type")?.toLowerCase().startsWith("text/event-stream")) {
    throw new TeacherWorkspaceError(
      "STREAM_UNAVAILABLE",
      "业务服务没有返回任务事件流。",
      context.requestId,
    );
  }
  if (!response.body) {
    throw new TeacherWorkspaceError(
      "STREAM_UNAVAILABLE",
      "业务服务没有返回可读取的任务流。",
      context.requestId,
    );
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const blocks = buffer.split(/\r?\n\r?\n/);
    buffer = blocks.pop() ?? "";

    for (const block of blocks) {
      const data = block
        .split(/\r?\n/)
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice("data:".length).trim())
        .join("\n");
      if (!data) continue;

      let event: TaskStreamEvent;
      try {
        event = JSON.parse(data) as TaskStreamEvent;
      } catch {
        throw new TeacherWorkspaceError(
          "STREAM_INVALID",
          "业务服务返回了无法读取的任务事件。",
          context.requestId,
        );
      }

      if (event.run_id) context.runId = event.run_id;
      if (event.request_id) context.requestId = event.request_id;
      if (signal?.aborted) throw abortError();

      if (event.type === "run_started") context.reportProgress("understanding");
      if (event.type === "tool_started") context.reportProgress("searching");
      if (event.type === "tool_finished") context.reportProgress("checking");

      if (event.type === "run_completed") {
        const result = event.data.search_response;
        if (!result || !("results" in result)) {
          throw new TeacherWorkspaceError(
            "STREAM_INVALID",
            "任务完成事件缺少结构化搜索结果。",
            event.request_id,
          );
        }
        return result;
      }
      if (event.type === "run_cancelled") throw abortError();
      if (event.type === "run_failed") {
        throw new TeacherWorkspaceError(
          event.data.error?.code ?? "INTERNAL_ERROR",
          event.data.error?.message ?? "Agent 运行失败。",
          event.data.error?.request_id ?? event.request_id,
        );
      }
    }

    if (done) break;
  }

  if (signal?.aborted) throw abortError();
  throw new TeacherWorkspaceError(
    "STREAM_INTERRUPTED",
    "任务连接在返回结果前中断。",
    context.requestId,
  );
}

type SolveStreamContext = {
  runId: string;
  requestId: string;
  reportProgress: (stage: SolveTaskProgressStage) => void;
};

async function readSolveStream(
  response: Response,
  context: SolveStreamContext,
  signal?: AbortSignal,
): Promise<SolveTaskResult> {
  if (!response.ok) throw await responseError(response);
  if (!response.headers.get("content-type")?.toLowerCase().startsWith("text/event-stream")) {
    throw new TeacherWorkspaceError(
      "STREAM_UNAVAILABLE",
      "业务服务没有返回任务事件流。",
      context.requestId,
    );
  }
  if (!response.body) {
    throw new TeacherWorkspaceError(
      "STREAM_UNAVAILABLE",
      "业务服务没有返回可读取的任务流。",
      context.requestId,
    );
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const blocks = buffer.split(/\r?\n\r?\n/);
    buffer = blocks.pop() ?? "";

    for (const block of blocks) {
      const data = block
        .split(/\r?\n/)
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice("data:".length).trim())
        .join("\n");
      if (!data) continue;

      let event: TaskStreamEvent;
      try {
        event = JSON.parse(data) as TaskStreamEvent;
      } catch {
        throw new TeacherWorkspaceError(
          "STREAM_INVALID",
          "业务服务返回了无法读取的任务事件。",
          context.requestId,
        );
      }

      if (event.run_id) context.runId = event.run_id;
      if (event.request_id) context.requestId = event.request_id;
      if (signal?.aborted) throw abortError();

      if (event.type === "run_started") context.reportProgress("understanding");
      if (event.type === "tool_started") context.reportProgress("solving");
      if (event.type === "tool_finished") context.reportProgress("verifying");

      if (event.type === "run_completed") {
        const result = event.data.solve_response;
        if (!result || !result.solution || !("math_verification" in result.solution)) {
          throw new TeacherWorkspaceError(
            "STREAM_INVALID",
            "任务完成事件缺少结构化解题结果。",
            event.request_id,
          );
        }
        return result;
      }
      if (event.type === "run_cancelled") throw abortError();
      if (event.type === "run_failed") {
        throw new TeacherWorkspaceError(
          event.data.error?.code ?? "INTERNAL_ERROR",
          event.data.error?.message ?? "Agent 运行失败。",
          event.data.error?.request_id ?? event.request_id,
        );
      }
    }

    if (done) break;
  }

  if (signal?.aborted) throw abortError();
  throw new TeacherWorkspaceError(
    "STREAM_INTERRUPTED",
    "任务连接在返回结果前中断。",
    context.requestId,
  );
}

export class HttpTeacherWorkspace implements TeacherWorkspace {
  async searchQuestions(
    request: SearchTaskRequest,
    options: SearchTaskOptions = {},
  ): Promise<SearchTaskResult> {
    const { signal, onProgress } = options;
    if (signal?.aborted) throw abortError();
    let progressIndex = -1;
    const reportProgress = (stage: SearchTaskProgressStage) => {
      const nextIndex = PROGRESS_ORDER.indexOf(stage);
      if (nextIndex <= progressIndex) return;
      progressIndex = nextIndex;
      onProgress?.({ stage });
    };
    reportProgress("connecting");

    const context: SearchStreamContext = { runId: "", requestId: "", reportProgress };
    const onAbort = () => {
      if (context.runId) void cancelRun("search", context.runId);
    };
    signal?.addEventListener("abort", onAbort, { once: true });

    try {
      const response = await fetch(apiUrl(SEARCH_STREAM_ENDPOINT), {
        method: "POST",
        headers: {
          Accept: "text/event-stream",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          query: request.query,
          session_id: request.sessionId,
        }),
        signal,
      });
      return await readSearchStream(response, context, signal);
    } catch (cause) {
      if (signal?.aborted) throw abortError();
      if (context.runId && isRecoverableStreamFailure(cause)) {
        reportProgress("recovering");
        try {
          const snapshot = await fetch(
            apiUrl(`/api/v1/agent/search/${encodeURIComponent(context.runId)}/stream`),
            { headers: { Accept: "text/event-stream" }, signal },
          );
          return await readSearchStream(snapshot, context, signal);
        } catch (recoveryCause) {
          if (signal?.aborted) throw abortError();
          if (
            recoveryCause instanceof TeacherWorkspaceError
            && !isSnapshotTransportFailure(recoveryCause)
          ) {
            throw recoveryCause;
          }
          if (recoveryCause instanceof DOMException && recoveryCause.name === "AbortError") {
            throw recoveryCause;
          }
          throw new TeacherWorkspaceError(
            "STREAM_RECOVERY_FAILED",
            "任务连接中断，且未能取回同一次运行的结果。",
            context.requestId,
          );
        }
      }
      if (cause instanceof TeacherWorkspaceError) throw cause;
      if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
      throw new TeacherWorkspaceError(
        "NETWORK_ERROR",
        "无法连接业务服务。请确认 FastAPI 已启动。",
      );
    } finally {
      signal?.removeEventListener("abort", onAbort);
    }
  }

  async solveQuestion(
    request: SolveTaskRequest,
    options: SolveTaskOptions = {},
  ): Promise<SolveTaskResult> {
    const { signal, onProgress } = options;
    if (signal?.aborted) throw abortError();
    let progressIndex = -1;
    const reportProgress = (stage: SolveTaskProgressStage) => {
      const nextIndex = SOLVE_PROGRESS_ORDER.indexOf(stage);
      if (nextIndex <= progressIndex) return;
      progressIndex = nextIndex;
      onProgress?.({ stage });
    };
    reportProgress("connecting");

    const context: SolveStreamContext = { runId: "", requestId: "", reportProgress };
    const onAbort = () => {
      if (context.runId) void cancelRun("solve", context.runId);
    };
    signal?.addEventListener("abort", onAbort, { once: true });

    try {
      const response = await fetch(apiUrl(SOLVE_STREAM_ENDPOINT), {
        method: "POST",
        headers: {
          Accept: "text/event-stream",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          question_text: request.questionText,
          session_id: request.sessionId,
          solution_mode: request.solutionMode ?? "standard",
          teacher_instruction: request.teacherInstruction ?? "",
        }),
        signal,
      });
      return await readSolveStream(response, context, signal);
    } catch (cause) {
      if (signal?.aborted) throw abortError();
      if (context.runId && isRecoverableStreamFailure(cause)) {
        reportProgress("recovering");
        try {
          const snapshot = await fetch(
            apiUrl(`/api/v1/agent/solve/${encodeURIComponent(context.runId)}/stream`),
            { headers: { Accept: "text/event-stream" }, signal },
          );
          return await readSolveStream(snapshot, context, signal);
        } catch (recoveryCause) {
          if (signal?.aborted) throw abortError();
          if (
            recoveryCause instanceof TeacherWorkspaceError
            && !isSnapshotTransportFailure(recoveryCause)
          ) {
            throw recoveryCause;
          }
          if (recoveryCause instanceof DOMException && recoveryCause.name === "AbortError") {
            throw recoveryCause;
          }
          throw new TeacherWorkspaceError(
            "STREAM_RECOVERY_FAILED",
            "任务连接中断，且未能取回同一次运行的结果。",
            context.requestId,
          );
        }
      }
      if (cause instanceof TeacherWorkspaceError) throw cause;
      if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
      throw new TeacherWorkspaceError(
        "NETWORK_ERROR",
        "无法连接业务服务。请确认 FastAPI 已启动。",
      );
    } finally {
      signal?.removeEventListener("abort", onAbort);
    }
  }
}

export const teacherWorkspace: TeacherWorkspace = new HttpTeacherWorkspace();
