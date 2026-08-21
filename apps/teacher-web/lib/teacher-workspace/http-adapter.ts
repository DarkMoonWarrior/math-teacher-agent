import {
  TeacherWorkspace,
  TeacherWorkspaceError,
  type SearchTaskRequest,
  type SearchTaskResult,
} from "./contracts";

const SEARCH_STREAM_ENDPOINT = "/api/v1/agent/search/stream";

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

type SearchStreamEvent = {
  type: "run_started" | "assistant_delta" | "tool_started" | "tool_finished" | "run_completed" | "run_failed" | "run_cancelled";
  run_id: string;
  request_id: string;
  data: {
    search_response?: SearchTaskResult;
    error?: { code?: string; message?: string; request_id?: string };
  };
};

function abortError(): DOMException {
  return new DOMException("Search task cancelled", "AbortError");
}

async function cancelRun(runId: string): Promise<void> {
  try {
    await fetch(apiUrl(`/api/v1/agent/search/${encodeURIComponent(runId)}/cancel`), {
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

export class HttpTeacherWorkspace implements TeacherWorkspace {
  async searchQuestions(
    request: SearchTaskRequest,
    signal?: AbortSignal,
  ): Promise<SearchTaskResult> {
    if (signal?.aborted) throw abortError();

    let response: Response;
    let runId = "";
    const onAbort = () => {
      if (runId) void cancelRun(runId);
    };
    signal?.addEventListener("abort", onAbort, { once: true });

    try {
      response = await fetch(apiUrl(SEARCH_STREAM_ENDPOINT), {
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

      if (!response.ok) throw await responseError(response);
      if (!response.body) {
        throw new TeacherWorkspaceError(
          "STREAM_UNAVAILABLE",
          "业务服务没有返回可读取的任务流。",
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

          let event: SearchStreamEvent;
          try {
            event = JSON.parse(data) as SearchStreamEvent;
          } catch {
            throw new TeacherWorkspaceError(
              "STREAM_INVALID",
              "业务服务返回了无法读取的任务事件。",
            );
          }

          if (event.run_id) runId = event.run_id;
          if (signal?.aborted) throw abortError();

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
        "任务连接在返回结果前中断。请重试。",
      );
    } catch (cause) {
      if (signal?.aborted) throw abortError();
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
