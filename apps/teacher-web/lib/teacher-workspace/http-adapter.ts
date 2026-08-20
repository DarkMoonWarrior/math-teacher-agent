import {
  TeacherWorkspace,
  TeacherWorkspaceError,
  type SearchTaskRequest,
  type SearchTaskResult,
} from "./contracts";

const SEARCH_ENDPOINT = "/api/v1/agent/search";

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

export class HttpTeacherWorkspace implements TeacherWorkspace {
  async searchQuestions(
    request: SearchTaskRequest,
    signal?: AbortSignal,
  ): Promise<SearchTaskResult> {
    let response: Response;

    try {
      response = await fetch(apiUrl(SEARCH_ENDPOINT), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: request.query,
          session_id: request.sessionId,
        }),
        signal,
      });
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === "AbortError") {
        throw cause;
      }
      throw new TeacherWorkspaceError(
        "NETWORK_ERROR",
        "无法连接业务服务。请确认 FastAPI 已启动。",
      );
    }

    let payload: SearchTaskResult | ErrorEnvelope;
    try {
      payload = (await response.json()) as SearchTaskResult | ErrorEnvelope;
    } catch {
      throw new TeacherWorkspaceError(
        `HTTP_${response.status}`,
        `业务服务返回了无法读取的响应（HTTP ${response.status}）。`,
      );
    }

    if (!response.ok || !("results" in payload)) {
      const error = (payload as ErrorEnvelope).error;
      throw new TeacherWorkspaceError(
        error?.code ?? `HTTP_${response.status}`,
        error?.message ?? `任务未完成（HTTP ${response.status}）。`,
        error?.request_id ?? "",
      );
    }

    if (payload.error && payload.status === "error") {
      throw new TeacherWorkspaceError(
        payload.error.code,
        payload.error.message,
        payload.error.request_id,
      );
    }

    return payload;
  }
}

export const teacherWorkspace: TeacherWorkspace = new HttpTeacherWorkspace();
