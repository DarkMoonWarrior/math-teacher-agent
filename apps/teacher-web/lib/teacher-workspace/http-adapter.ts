import {
  TeacherWorkspace,
  TeacherWorkspaceError,
  type LibraryItemDetail,
  type LibraryItemSummary,
  type LibraryTextRevisionList,
  type CurriculumSearchResult,
  type PrivateLibraryCandidateImportResult,
  type PrivateLibraryList,
  type PrivateLibraryOCRRequest,
  type PrivateLibraryOCRResult,
  type PrivateLibraryProcessingOptions,
  type PrivateLibraryQuestionCandidate,
  type PrivateLibraryQuestionCandidateDraft,
  type PrivateLibraryQuestionCandidateList,
  type PrivateLibraryReview,
  type PrivateLibrarySearchResult,
  type PrivateLibraryUpload,
  type PersonalAuthoringDraft,
  type PersonalAuthoringRevisionList,
  type PersonalQuestion,
  type PersonalQuestionCategory,
  type PersonalQuestionCategoryList,
  type PersonalQuestionCollection,
  type PersonalQuestionCollectionList,
  type PersonalQuestionExport,
  type PersonalQuestionList,
  type QuestionAuthoringAgentResult,
  type QuestionAuthoringBrief,
  type QuestionAuthoringGenerationOptions,
  type QuestionAuthoringProgressStage,
  type QuestionDraftEditableContent,
  type QuestionInputBundle,
  type QuestionMediaTransform,
  type QuestionMediaUpload,
  type QuestionRecognitionRequest,
  type QuestionRecognitionReview,
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

function questionAuthoringProgressId(): string {
  const value = typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
    ? crypto.randomUUID().replaceAll("-", "")
    : `${Date.now().toString(36)}${Math.random().toString(36).slice(2)}0000000000`;
  return `qap_${value}`;
}

const QUESTION_AUTHORING_PROGRESS_STAGES = new Set<QuestionAuthoringProgressStage>([
  "brief",
  "composing",
  "reviewing",
  "refining",
  "solving",
  "staging",
]);

type ErrorEnvelope = {
  error?: { code?: string; message?: string; request_id?: string };
  detail?: unknown;
};

type LibraryBackgroundJob = {
  job_id: string;
  status: "queued" | "running" | "succeeded" | "failed";
  message: string;
  error: string;
  result: Record<string, unknown>;
};

function detailMessage(detail: unknown): string | undefined {
  if (typeof detail === "string") return detail;
  if (!Array.isArray(detail)) return undefined;
  const messages = detail
    .map((item) => {
      if (typeof item === "string") return item;
      if (item && typeof item === "object" && "msg" in item && typeof item.msg === "string") {
        return item.msg;
      }
      return "";
    })
    .filter(Boolean);
  return messages.length ? messages.join("；") : undefined;
}

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
    payload.error?.message ?? detailMessage(payload.detail) ?? `任务未完成（HTTP ${response.status}）。`,
    payload.error?.request_id ?? "",
  );
}

function libraryJobDelay(signal?: AbortSignal): Promise<void> {
  if (signal?.aborted) return Promise.reject(abortError());
  return new Promise((resolve, reject) => {
    const timeout = globalThis.setTimeout(resolve, 450);
    signal?.addEventListener("abort", () => {
      globalThis.clearTimeout(timeout);
      reject(abortError());
    }, { once: true });
  });
}

async function libraryJsonRequest<T>(
  path: string,
  init: RequestInit,
  networkMessage: string,
): Promise<T> {
  try {
    const response = await fetch(apiUrl(path), {
      ...init,
      headers: {
        Accept: "application/json",
        ...init.headers,
      },
    });
    if (!response.ok) throw await responseError(response);
    return await response.json() as T;
  } catch (cause) {
    if (cause instanceof TeacherWorkspaceError) throw cause;
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
    throw new TeacherWorkspaceError("NETWORK_ERROR", networkMessage);
  }
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
  async uploadQuestionMedia(
    request: QuestionMediaUpload,
    signal?: AbortSignal,
  ): Promise<QuestionInputBundle> {
    const body = new FormData();
    body.set("file", request.file);
    body.set("source", request.source);
    body.set("private_storage_acknowledged", String(request.privateStorageAcknowledged));
    try {
      const response = await fetch(apiUrl("/api/v1/question-capture/assets"), {
        method: "POST",
        headers: { Accept: "application/json" },
        body,
        signal,
      });
      if (!response.ok) throw await responseError(response);
      return await response.json() as QuestionInputBundle;
    } catch (cause) {
      if (cause instanceof TeacherWorkspaceError) throw cause;
      if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
      throw new TeacherWorkspaceError(
        "NETWORK_ERROR",
        "无法保存题目图片。请确认 FastAPI 已启动。",
      );
    }
  }

  async transformQuestionMedia(
    assetId: string,
    transform: QuestionMediaTransform,
    signal?: AbortSignal,
  ): Promise<QuestionInputBundle> {
    try {
      const response = await fetch(
        apiUrl(`/api/v1/question-capture/assets/${encodeURIComponent(assetId)}/transform`),
        {
          method: "POST",
          headers: { Accept: "application/json", "Content-Type": "application/json" },
          body: JSON.stringify(transform),
          signal,
        },
      );
      if (!response.ok) throw await responseError(response);
      return await response.json() as QuestionInputBundle;
    } catch (cause) {
      if (cause instanceof TeacherWorkspaceError) throw cause;
      if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
      throw new TeacherWorkspaceError(
        "NETWORK_ERROR",
        "无法调整题目图片。请确认 FastAPI 已启动。",
      );
    }
  }

  async recognizeQuestionMedia(
    assetId: string,
    request: QuestionRecognitionRequest,
    signal?: AbortSignal,
  ): Promise<QuestionInputBundle> {
    try {
      const response = await fetch(
        apiUrl(`/api/v1/question-capture/assets/${encodeURIComponent(assetId)}/recognize`),
        {
          method: "POST",
          headers: { Accept: "application/json", "Content-Type": "application/json" },
          body: JSON.stringify({
            mode: request.mode,
            external_processing_consent: request.externalProcessingConsent,
          }),
          signal,
        },
      );
      if (!response.ok) throw await responseError(response);
      return await response.json() as QuestionInputBundle;
    } catch (cause) {
      if (cause instanceof TeacherWorkspaceError) throw cause;
      if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
      throw new TeacherWorkspaceError("NETWORK_ERROR", "无法识别题目图片。请确认 FastAPI 已启动。");
    }
  }

  async reviewQuestionRecognition(
    assetId: string,
    request: QuestionRecognitionReview,
    signal?: AbortSignal,
  ): Promise<QuestionInputBundle> {
    try {
      const response = await fetch(
        apiUrl(`/api/v1/question-capture/assets/${encodeURIComponent(assetId)}/recognition`),
        {
          method: "PATCH",
          headers: { Accept: "application/json", "Content-Type": "application/json" },
          body: JSON.stringify({
            stem_plain: request.stemPlain,
            stem_latex: request.stemLatex,
            options: request.options,
            note: request.note,
            confirm: request.confirm,
          }),
          signal,
        },
      );
      if (!response.ok) throw await responseError(response);
      return await response.json() as QuestionInputBundle;
    } catch (cause) {
      if (cause instanceof TeacherWorkspaceError) throw cause;
      if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
      throw new TeacherWorkspaceError("NETWORK_ERROR", "无法保存题面校对。请确认 FastAPI 已启动。");
    }
  }

  async searchPrivateLibrary(
    query: string,
    privateContentConsent: true,
    signal?: AbortSignal,
  ): Promise<PrivateLibrarySearchResult> {
    try {
      const response = await fetch(apiUrl("/api/v1/agent/private-library/search"), {
        method: "POST",
        headers: { Accept: "application/json", "Content-Type": "application/json" },
        body: JSON.stringify({ query, private_content_consent: privateContentConsent, limit: 5 }),
        signal,
      });
      if (!response.ok) throw await responseError(response);
      const payload = await response.json() as {
        status: "ok" | "error" | "cancelled";
        result: PrivateLibrarySearchResult | null;
        error?: { code?: string; message?: string; request_id?: string };
      };
      if (payload.status !== "ok" || !payload.result) {
        throw new TeacherWorkspaceError(
          payload.error?.code ?? "PRIVATE_SEARCH_FAILED",
          payload.error?.message ?? "私人检索没有返回可用结果。",
          payload.error?.request_id ?? "",
        );
      }
      return payload.result;
    } catch (cause) {
      if (cause instanceof TeacherWorkspaceError) throw cause;
      if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
      throw new TeacherWorkspaceError("NETWORK_ERROR", "无法完成私人检索。请确认 Agent Service 与 FastAPI 已启动。");
    }
  }

  async listPrivateLibrary(signal?: AbortSignal): Promise<PrivateLibraryList> {
    try {
      const response = await fetch(apiUrl("/api/v1/library"), {
        headers: { Accept: "application/json" },
        signal,
      });
      if (!response.ok) throw await responseError(response);
      return await response.json() as PrivateLibraryList;
    } catch (cause) {
      if (cause instanceof TeacherWorkspaceError) throw cause;
      if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
      throw new TeacherWorkspaceError(
        "NETWORK_ERROR",
        "无法读取私人资料。请确认 FastAPI 已启动。",
      );
    }
  }

  async getPrivateLibraryItem(
    itemId: string,
    signal?: AbortSignal,
  ): Promise<LibraryItemDetail> {
    try {
      const response = await fetch(
        apiUrl(`/api/v1/library/${encodeURIComponent(itemId)}`),
        { headers: { Accept: "application/json" }, signal },
      );
      if (!response.ok) throw await responseError(response);
      return await response.json() as LibraryItemDetail;
    } catch (cause) {
      if (cause instanceof TeacherWorkspaceError) throw cause;
      if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
      throw new TeacherWorkspaceError(
        "NETWORK_ERROR",
        "无法读取这份私人资料。请确认 FastAPI 已启动。",
      );
    }
  }

  async listPrivateLibraryRevisions(
    itemId: string,
    signal?: AbortSignal,
  ): Promise<LibraryTextRevisionList> {
    try {
      const response = await fetch(
        apiUrl(`/api/v1/library/${encodeURIComponent(itemId)}/revisions`),
        { headers: { Accept: "application/json" }, signal },
      );
      if (!response.ok) throw await responseError(response);
      return await response.json() as LibraryTextRevisionList;
    } catch (cause) {
      if (cause instanceof TeacherWorkspaceError) throw cause;
      if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
      throw new TeacherWorkspaceError(
        "NETWORK_ERROR",
        "无法读取资料修订记录。",
      );
    }
  }

  async uploadPrivateLibrary(
    request: PrivateLibraryUpload,
    signal?: AbortSignal,
  ): Promise<LibraryItemSummary> {
    const body = new FormData();
    body.set("file", request.file);
    body.set("title", request.title);
    body.set("rights_basis", request.rightsBasis);
    body.set("rights_statement", request.rightsStatement);
    body.set("rights_acknowledged", String(request.rightsAcknowledged));

    try {
      const response = await fetch(apiUrl("/api/v1/library"), {
        method: "POST",
        headers: { Accept: "application/json" },
        body,
        signal,
      });
      if (!response.ok) throw await responseError(response);
      return await response.json() as LibraryItemSummary;
    } catch (cause) {
      if (cause instanceof TeacherWorkspaceError) throw cause;
      if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
      throw new TeacherWorkspaceError(
        "NETWORK_ERROR",
        "无法上传私人资料。请确认 FastAPI 已启动。",
      );
    }
  }

  async reviewPrivateLibraryText(
    itemId: string,
    request: PrivateLibraryReview,
    signal?: AbortSignal,
  ): Promise<LibraryItemDetail> {
    try {
      const response = await fetch(
        apiUrl(`/api/v1/library/${encodeURIComponent(itemId)}/review`),
        {
          method: "PATCH",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            corrected_text: request.correctedText,
            note: request.note,
            confirm: request.confirm,
          }),
          signal,
        },
      );
      if (!response.ok) throw await responseError(response);
      return await response.json() as LibraryItemDetail;
    } catch (cause) {
      if (cause instanceof TeacherWorkspaceError) throw cause;
      if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
      throw new TeacherWorkspaceError(
        "NETWORK_ERROR",
        "无法保存这次资料校对。",
      );
    }
  }

  async processPrivateLibraryOCR(
    itemId: string,
    request: PrivateLibraryOCRRequest,
    options: PrivateLibraryProcessingOptions = {},
  ): Promise<PrivateLibraryOCRResult> {
    const { signal, onProgress } = options;
    const encodedId = encodeURIComponent(itemId);
    const isExternal = request.mode === "external";
    const endpoint = isExternal
      ? `/api/v1/library/${encodedId}/ocr/jobs`
      : `/api/v1/library/${encodedId}/local-math-ocr/jobs`;
    if (signal?.aborted) throw abortError();
    try {
      onProgress?.(isExternal ? "正在准备外部 OCR" : "正在准备本地数学 OCR");
      const startResponse = await fetch(apiUrl(endpoint), {
        method: "POST",
        headers: isExternal
          ? { Accept: "application/json", "Content-Type": "application/json" }
          : { Accept: "application/json" },
        body: isExternal
          ? JSON.stringify({
            external_processing_consent: request.externalProcessingConsent,
          })
          : undefined,
        signal,
      });
      if (!startResponse.ok) throw await responseError(startResponse);
      let job = await startResponse.json() as LibraryBackgroundJob;
      onProgress?.(job.message || "OCR 任务已开始");

      while (job.status === "queued" || job.status === "running") {
        const jobResponse = await fetch(
          apiUrl(`/api/v1/library/jobs/${encodeURIComponent(job.job_id)}`),
          { headers: { Accept: "application/json" }, signal },
        );
        if (!jobResponse.ok) throw await responseError(jobResponse);
        job = await jobResponse.json() as LibraryBackgroundJob;
        onProgress?.(job.message || "正在识别资料");
        if (job.status === "queued" || job.status === "running") {
          await libraryJobDelay(signal);
        }
      }

      if (job.status === "failed") {
        throw new TeacherWorkspaceError(
          "OCR_FAILED",
          job.error || "OCR 没有生成可用草稿。",
        );
      }
      return job.result as unknown as PrivateLibraryOCRResult;
    } catch (cause) {
      if (cause instanceof TeacherWorkspaceError) throw cause;
      if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
      throw new TeacherWorkspaceError(
        "NETWORK_ERROR",
        "OCR 处理连接中断。请重新打开资料检查是否已经生成草稿。",
      );
    }
  }

  listPrivateLibraryQuestionCandidates(
    itemId: string,
    signal?: AbortSignal,
  ): Promise<PrivateLibraryQuestionCandidateList> {
    return libraryJsonRequest(
      `/api/v1/library/${encodeURIComponent(itemId)}/question-candidates`,
      { signal },
      "无法读取拆题候选。",
    );
  }

  preparePrivateLibraryQuestionCandidates(
    itemId: string,
    signal?: AbortSignal,
  ): Promise<PrivateLibraryQuestionCandidateList> {
    return libraryJsonRequest(
      `/api/v1/library/${encodeURIComponent(itemId)}/question-candidates`,
      { method: "POST", signal },
      "无法从确认文本生成拆题候选。",
    );
  }

  updatePrivateLibraryQuestionCandidate(
    itemId: string,
    candidateId: string,
    draft: PrivateLibraryQuestionCandidateDraft,
    signal?: AbortSignal,
  ): Promise<PrivateLibraryQuestionCandidate> {
    return libraryJsonRequest(
      `/api/v1/library/${encodeURIComponent(itemId)}/question-candidates/${encodeURIComponent(candidateId)}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(draft),
        signal,
      },
      "无法保存拆题候选。",
    );
  }

  searchCurriculum(
    query: string,
    signal?: AbortSignal,
  ): Promise<CurriculumSearchResult> {
    const parameters = new URLSearchParams({
      query: query.trim(),
      node_type: "knowledge_point",
      limit: "8",
    });
    return libraryJsonRequest(
      `/api/v1/curriculum/search?${parameters.toString()}`,
      { signal },
      "无法读取教材知识点。",
    );
  }

  mapPrivateLibraryQuestionCandidateCurriculum(
    itemId: string,
    candidateId: string,
    nodeId: string,
    signal?: AbortSignal,
  ): Promise<PrivateLibraryQuestionCandidate> {
    return libraryJsonRequest(
      `/api/v1/library/${encodeURIComponent(itemId)}/question-candidates/${encodeURIComponent(candidateId)}/curriculum`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ node_id: nodeId }),
        signal,
      },
      "无法保存教材映射。",
    );
  }

  importPrivateLibraryQuestionCandidate(
    itemId: string,
    candidateId: string,
    signal?: AbortSignal,
  ): Promise<PrivateLibraryCandidateImportResult> {
    return libraryJsonRequest(
      `/api/v1/library/${encodeURIComponent(itemId)}/question-candidates/${encodeURIComponent(candidateId)}/import`,
      { method: "POST", signal },
      "无法导入私人题库。",
    );
  }

  async createQuestionAuthoringDraft(
    request: QuestionAuthoringBrief,
    options?: QuestionAuthoringGenerationOptions,
  ): Promise<QuestionAuthoringAgentResult> {
    const progressId = questionAuthoringProgressId();
    let polling = true;
    options?.onProgress?.("brief");
    void (async () => {
      while (polling && !options?.signal?.aborted) {
        await new Promise((resolve) => setTimeout(resolve, 500));
        if (!polling || options?.signal?.aborted) break;
        try {
          const response = await fetch(
            apiUrl(`/api/v1/agent/question-authoring/progress/${encodeURIComponent(progressId)}`),
            { method: "GET", cache: "no-store", signal: options?.signal },
          );
          if (!response.ok) continue;
          const payload = await response.json() as { stage?: unknown };
          if (typeof payload.stage === "string" && QUESTION_AUTHORING_PROGRESS_STAGES.has(payload.stage as QuestionAuthoringProgressStage)) {
            options?.onProgress?.(payload.stage as QuestionAuthoringProgressStage);
          }
        } catch {
          // The POST remains authoritative. A transient progress read must not fail generation.
        }
      }
    })();
    const brief = {
      request_text: request.requestText,
      grade: request.grade,
      curriculum_node_id: request.curriculumNodeId,
      knowledge_point_query: request.knowledgePointQuery,
      question_type: request.questionType,
      target_difficulty: request.targetDifficulty,
      teaching_purpose: request.teachingPurpose,
      expected_minutes: request.expectedMinutes,
      assessed_method: request.assessedMethod ?? "",
      misconception_requirements: request.misconceptionRequirements ?? "",
      additional_constraints: request.additionalConstraints ?? "",
      reference_question_id: request.referenceQuestionId,
    };
    let payload: QuestionAuthoringAgentResult;
    try {
      payload = await libraryJsonRequest<QuestionAuthoringAgentResult>(
        "/api/v1/agent/question-authoring/draft",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ brief, session_id: request.sessionId, progress_id: progressId }),
          signal: options?.signal,
        },
        "无法连接辅助命题 Agent。请确认 Agent Service 与 FastAPI 已启动。",
      );
    } finally {
      polling = false;
    }
    if (payload.status !== "ok" || !payload.draft) {
      throw new TeacherWorkspaceError(
        payload.error?.code ?? "QUESTION_AUTHORING_FAILED",
        payload.error?.message ?? "辅助命题没有返回可编辑草稿。",
        payload.error?.request_id ?? payload.request_id,
      );
    }
    options?.onProgress?.("staging");
    return payload;
  }

  getPersonalAuthoringDraft(
    draftId: string,
    signal?: AbortSignal,
  ): Promise<PersonalAuthoringDraft> {
    return libraryJsonRequest(
      `/api/v1/personal-question-library/authoring-drafts/${encodeURIComponent(draftId)}`,
      { method: "GET", signal },
      "无法读取当前命题草稿。",
    );
  }

  listPersonalAuthoringRevisions(
    draftId: string,
    signal?: AbortSignal,
  ): Promise<PersonalAuthoringRevisionList> {
    return libraryJsonRequest(
      `/api/v1/personal-question-library/authoring-drafts/${encodeURIComponent(draftId)}/revisions`,
      { method: "GET", signal },
      "无法读取命题修订记录。",
    );
  }

  revisePersonalAuthoringDraft(
    draftId: string,
    expectedRevision: number,
    content: QuestionDraftEditableContent,
    editSummary: string,
    signal?: AbortSignal,
  ): Promise<PersonalAuthoringDraft> {
    return libraryJsonRequest(
      `/api/v1/personal-question-library/authoring-drafts/${encodeURIComponent(draftId)}/revisions`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ expected_revision: expectedRevision, content, edit_summary: editSummary }),
        signal,
      },
      "无法保存这次命题校订。",
    );
  }

  regeneratePersonalAuthoringSolution(
    draftId: string,
    expectedRevision: number,
    signal?: AbortSignal,
  ): Promise<PersonalAuthoringDraft> {
    return libraryJsonRequest(
      `/api/v1/personal-question-library/authoring-drafts/${encodeURIComponent(draftId)}/regenerate-solution`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ expected_revision: expectedRevision }),
        signal,
      },
      "无法重新生成这道题的解析。",
    );
  }

  savePersonalAuthoringDraft(
    draftId: string,
    request: { expectedRevision: number; collectionId: string; categoryId: string; name: string },
    signal?: AbortSignal,
  ): Promise<PersonalQuestion> {
    return libraryJsonRequest(
      `/api/v1/personal-question-library/authoring-drafts/${encodeURIComponent(draftId)}/save`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          expected_revision: request.expectedRevision,
          collection_id: request.collectionId,
          category_id: request.categoryId,
          name: request.name,
        }),
        signal,
      },
      "无法把草稿保存到你的私题库。",
    );
  }

  listPersonalQuestionCollections(signal?: AbortSignal): Promise<PersonalQuestionCollectionList> {
    return libraryJsonRequest(
      "/api/v1/personal-question-library/collections",
      { method: "GET", signal },
      "无法读取你的个人题库。",
    );
  }

  createPersonalQuestionCollection(
    name: string,
    description = "",
    signal?: AbortSignal,
  ): Promise<PersonalQuestionCollection> {
    return libraryJsonRequest(
      "/api/v1/personal-question-library/collections",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, description }),
        signal,
      },
      "无法新建个人题库。",
    );
  }

  listPersonalQuestionCategories(
    collectionId: string,
    signal?: AbortSignal,
  ): Promise<PersonalQuestionCategoryList> {
    return libraryJsonRequest(
      `/api/v1/personal-question-library/collections/${encodeURIComponent(collectionId)}/categories`,
      { method: "GET", signal },
      "无法读取个人分类。",
    );
  }

  createPersonalQuestionCategory(
    collectionId: string,
    name: string,
    description = "",
    signal?: AbortSignal,
  ): Promise<PersonalQuestionCategory> {
    return libraryJsonRequest(
      `/api/v1/personal-question-library/collections/${encodeURIComponent(collectionId)}/categories`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, description, sort_order: 0 }),
        signal,
      },
      "无法新建个人分类。",
    );
  }

  listPersonalQuestions(
    request: { query?: string; lifecycleState?: "active" | "trashed"; collectionId?: string; categoryId?: string },
    signal?: AbortSignal,
  ): Promise<PersonalQuestionList> {
    const params = new URLSearchParams({
      query: request.query ?? "",
      lifecycle_state: request.lifecycleState ?? "active",
      limit: "200",
      offset: "0",
    });
    if (request.collectionId) params.set("collection_id", request.collectionId);
    if (request.categoryId) params.set("category_id", request.categoryId);
    return libraryJsonRequest(
      `/api/v1/personal-question-library/questions?${params.toString()}`,
      { method: "GET", signal },
      "无法读取你的私题。",
    );
  }

  revisePersonalQuestion(
    question: PersonalQuestion,
    content: QuestionDraftEditableContent,
    editSummary: string,
    signal?: AbortSignal,
  ): Promise<PersonalQuestion> {
    return libraryJsonRequest(
      `/api/v1/personal-question-library/questions/${encodeURIComponent(question.question_id)}/revisions`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          expected_revision: question.selected_revision,
          expected_updated_at: question.updated_at,
          content,
          edit_summary: editSummary,
        }),
        signal,
      },
      "无法保存这次私题校订。",
    );
  }

  updatePersonalQuestion(
    question: PersonalQuestion,
    request: { name?: string; collectionId?: string; categoryId?: string; tags?: string[]; sortOrder?: number },
    signal?: AbortSignal,
  ): Promise<PersonalQuestion> {
    return libraryJsonRequest(
      `/api/v1/personal-question-library/questions/${encodeURIComponent(question.question_id)}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          expected_updated_at: question.updated_at,
          name: request.name,
          collection_id: request.collectionId,
          category_id: request.categoryId,
          tags: request.tags,
          sort_order: request.sortOrder,
        }),
        signal,
      },
      "无法更新这道私题。",
    );
  }

  copyPersonalQuestion(
    questionId: string,
    request: { collectionId: string; categoryId: string; name?: string },
    signal?: AbortSignal,
  ): Promise<PersonalQuestion> {
    return libraryJsonRequest(
      `/api/v1/personal-question-library/questions/${encodeURIComponent(questionId)}/copy`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          collection_id: request.collectionId,
          category_id: request.categoryId,
          name: request.name,
        }),
        signal,
      },
      "无法复制这道私题。",
    );
  }

  async exportPersonalQuestion(
    questionId: string,
    format: "json" | "markdown",
    signal?: AbortSignal,
  ): Promise<PersonalQuestionExport> {
    try {
      const response = await fetch(apiUrl(
        `/api/v1/personal-question-library/questions/${encodeURIComponent(questionId)}/export?format=${format}`,
      ), { headers: { Accept: format === "json" ? "application/json" : "text/markdown" }, signal });
      if (!response.ok) throw await responseError(response);
      const disposition = response.headers.get("Content-Disposition") ?? "";
      const encodedName = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
      return {
        blob: await response.blob(),
        filename: encodedName ? decodeURIComponent(encodedName) : `private-question.${format === "json" ? "json" : "md"}`,
      };
    } catch (cause) {
      if (cause instanceof TeacherWorkspaceError) throw cause;
      if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
      throw new TeacherWorkspaceError("NETWORK_ERROR", "无法导出这道私题。");
    }
  }

  trashPersonalQuestion(question: PersonalQuestion, signal?: AbortSignal): Promise<PersonalQuestion> {
    return libraryJsonRequest(
      `/api/v1/personal-question-library/questions/${encodeURIComponent(question.question_id)}/trash`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ expected_updated_at: question.updated_at }),
        signal,
      },
      "无法把这道题移入回收站。",
    );
  }

  restorePersonalQuestion(question: PersonalQuestion, signal?: AbortSignal): Promise<PersonalQuestion> {
    return libraryJsonRequest(
      `/api/v1/personal-question-library/questions/${encodeURIComponent(question.question_id)}/restore`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ expected_updated_at: question.updated_at }),
        signal,
      },
      "无法恢复这道私题。",
    );
  }

  permanentlyDeletePersonalQuestion(
    question: PersonalQuestion,
    confirmation: "永久删除我的私题",
    signal?: AbortSignal,
  ): Promise<{ question_id: string; active_storage_deleted: true; deleted_at: string }> {
    return libraryJsonRequest(
      `/api/v1/personal-question-library/questions/${encodeURIComponent(question.question_id)}`,
      {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ expected_updated_at: question.updated_at, confirmation }),
        signal,
      },
      "无法永久删除这道私题。",
    );
  }

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
          question_capture: request.questionCapture ? {
            asset_id: request.questionCapture.assetId,
            media_revision: request.questionCapture.mediaRevision,
            recognition_revision: request.questionCapture.recognitionRevision,
            visual_processing_consent: request.questionCapture.visualProcessingConsent,
          } : null,
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
