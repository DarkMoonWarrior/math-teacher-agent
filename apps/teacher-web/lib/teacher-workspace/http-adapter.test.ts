import { afterEach, describe, expect, it, vi } from "vitest";
import type {
  SearchTaskProgressStage,
  SearchTaskResult,
  SolveTaskProgressStage,
  SolveTaskResult,
  LibraryItemSummary,
} from "./contracts";
import { HttpTeacherWorkspace } from "./http-adapter";

const encoder = new TextEncoder();

function eventBlock(event: unknown): Uint8Array {
  return encoder.encode(`data: ${JSON.stringify(event)}\n\n`);
}

function streamResponse(events: unknown[], contentType = "text/event-stream"): Response {
  return new Response(new ReadableStream({
    start(controller) {
      for (const event of events) controller.enqueue(eventBlock(event));
      controller.close();
    },
  }), {
    status: 200,
    headers: { "Content-Type": contentType },
  });
}

function resultFixture(): SearchTaskResult {
  return {
    request_id: "req_1",
    session_id: "tch_1",
    run_id: "run_1",
    raw_query: "找椭圆题",
    status: "ok",
    intent: {
      grade: "高二",
      knowledge_points: ["椭圆"],
      question_types: [],
      difficulty: 3,
      regions: [],
      teaching_usage: "classroom_example",
      constraints: [],
      parse_warnings: [],
    },
    plan_summary: { steps: [], candidate_count: 1, selected_count: 1 },
    results: [],
    requested_count: 5,
    returned_count: 0,
    exact_match_count: 0,
    exact_match: false,
    warnings: [],
    answer_summary: "没有真实记录满足当前条件。",
    assistant_explanation: null,
    search_confidence: "low",
    suggestions: [],
    duration_ms: 12,
    tool_call_count: 1,
    candidate_count: 1,
    error: null,
  };
}

function solveResultFixture(): SolveTaskResult {
  return {
    request_id: "req_solve_1",
    session_id: "tch_solve_1",
    run_id: "run_solve_1",
    status: "ok",
    question_text: "解方程 2x-4=0。",
    solution_mode: "standard",
    solution: {
      question_text: "解方程 2x-4=0。",
      solution_mode: "standard",
      explanation: {
        method: "代数法",
        steps: ["移项得 2x=4。", "两边同除以 2，得到 x=2。"],
        final_answer: "x=2",
      },
      knowledge_points: ["一元一次方程"],
      common_mistakes: ["移项忘记变号"],
      teaching_notes: ["提醒学生核验代入结果"],
      confidence_status: "teacher_review_required",
      math_verification: {
        status: "inconclusive",
        capability: "unsupported",
        scope: "generated_solution",
        evidence_source: "none",
        method: null,
        computed_answer: null,
        source_answer: null,
        details: ["当前 MathVerifier 不支持完整推导验证。"],
        verifier_version: null,
      },
      verification_evidence: ["当前 MathVerifier 不支持完整推导验证。"],
      provider: "fake_model",
      model: "fake-solver-v1",
      mode: "live_ai",
      matched_question_id: null,
      matched_question_revision_count: null,
      match_score: null,
      alternative_available: true,
      warnings: ["请由教师复核"],
    },
    tool_request_id: "req_tool_solve",
    duration_ms: 24,
    tool_call_count: 1,
    error: null,
  };
}

function libraryItemFixture(): LibraryItemSummary {
  return {
    library_item_id: "lib_1",
    title: "函数单调性讲义",
    original_filename: "函数讲义.docx",
    file_kind: "docx",
    mime_type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    size_bytes: 1024,
    page_count: null,
    extraction_status: "extracted",
    text_review_status: "pending",
    extracted_char_count: 128,
    corrected_char_count: 128,
    rights_basis: "private_teaching_only",
    lifecycle_state: "active",
    trashed_at: null,
    visibility: "private",
    public_search_allowed: false,
    model_training_allowed: false,
    version: 1,
    created_at: "2026-08-22T08:00:00+00:00",
    updated_at: "2026-08-22T08:00:00+00:00",
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("HttpTeacherWorkspace", () => {
  it("loads only the server-scoped private library list", async () => {
    const item = libraryItemFixture();
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ items: [item], total: 1 }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);

    const workspace = new HttpTeacherWorkspace();
    await expect(workspace.listPrivateLibrary()).resolves.toEqual({ items: [item], total: 1 });
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/library", expect.objectContaining({
      headers: { Accept: "application/json" },
    }));
  });

  it("uploads rights metadata without exposing an owner selector", async () => {
    const item = libraryItemFixture();
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => new Response(JSON.stringify(item), {
      status: 201,
      headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);
    const file = new File(["synthetic lesson"], "lesson.docx", {
      type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    });

    const workspace = new HttpTeacherWorkspace();
    await expect(workspace.uploadPrivateLibrary({
      file,
      title: "函数单调性讲义",
      rightsBasis: "private_teaching_only",
      rightsStatement: "仅在本人的私人教学工作区内使用。",
      rightsAcknowledged: true,
    })).resolves.toEqual(item);

    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    const body = init.body as FormData;
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/v1/library");
    expect(init.method).toBe("POST");
    expect(body.get("rights_basis")).toBe("private_teaching_only");
    expect(body.get("rights_acknowledged")).toBe("true");
    expect(body.has("owner_id")).toBe(false);
  });

  it("returns the structured result from the terminal stream event", async () => {
    const result = resultFixture();
    vi.stubGlobal("fetch", vi.fn(async () => streamResponse([
      { type: "run_started", run_id: "run_1", request_id: "req_1", data: {} },
      {
        type: "run_completed",
        run_id: "run_1",
        request_id: "req_1",
        data: { search_response: result },
      },
    ])));

    const workspace = new HttpTeacherWorkspace();
    await expect(workspace.searchQuestions({ query: "找椭圆题", sessionId: "tch_1" }))
      .resolves.toEqual(result);
  });

  it("reports only the safe task stages exposed by the stream contract", async () => {
    const result = resultFixture();
    vi.stubGlobal("fetch", vi.fn(async () => streamResponse([
      { type: "run_started", run_id: "run_1", request_id: "req_1", data: {} },
      {
        type: "assistant_delta",
        run_id: "run_1",
        request_id: "req_1",
        data: { text: "raw model text must stay private" },
      },
      {
        type: "tool_started",
        run_id: "run_1",
        request_id: "req_1",
        data: { tool_name: "search_questions", input: { query: "private payload" } },
      },
      {
        type: "tool_finished",
        run_id: "run_1",
        request_id: "req_1",
        data: { tool_name: "search_questions", output: { questions: ["private payload"] } },
      },
      {
        type: "tool_started",
        run_id: "run_1",
        request_id: "req_1",
        data: { tool_name: "get_question" },
      },
      {
        type: "run_completed",
        run_id: "run_1",
        request_id: "req_1",
        data: { search_response: result },
      },
    ])));
    const stages: SearchTaskProgressStage[] = [];

    const workspace = new HttpTeacherWorkspace();
    await workspace.searchQuestions(
      { query: "找椭圆题", sessionId: "tch_1" },
      { onProgress: ({ stage }) => stages.push(stage) },
    );

    expect(stages).toEqual(["connecting", "understanding", "searching", "checking"]);
  });

  it("rejects a successful non-SSE response before attempting to parse it", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("<html>proxy error</html>", {
      status: 200,
      headers: { "Content-Type": "text/html" },
    })));

    const workspace = new HttpTeacherWorkspace();
    const failure = workspace.searchQuestions({ query: "找题", sessionId: "tch_proxy" });
    await expect(failure).rejects.toMatchObject({
      code: "STREAM_UNAVAILABLE",
      message: "业务服务没有返回任务事件流。",
    });
  });

  it("preserves the product error code from a failed run", async () => {
    const fetchMock = vi.fn(async () => streamResponse([
      { type: "run_started", run_id: "run_2", request_id: "req_2", data: {} },
      {
        type: "run_failed",
        run_id: "run_2",
        request_id: "req_2",
        data: {
          error: {
            code: "TOOL_TIMEOUT",
            message: "工具调用超时",
            request_id: "req_2",
          },
        },
      },
    ]));
    vi.stubGlobal("fetch", fetchMock);

    const workspace = new HttpTeacherWorkspace();
    const failure = workspace.searchQuestions({ query: "找题", sessionId: "tch_2" });
    await expect(failure).rejects.toMatchObject({
      code: "TOOL_TIMEOUT",
      message: "工具调用超时",
      requestId: "req_2",
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("recovers a saved terminal result by run id without executing Search again", async () => {
    const result = resultFixture();
    const fetchMock = vi.fn((input: RequestInfo | URL, _init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/run_1/stream")) {
        return Promise.resolve(streamResponse([
          { type: "run_started", run_id: "run_1", request_id: "req_1", data: {} },
          {
            type: "run_completed",
            run_id: "run_1",
            request_id: "req_1",
            data: { search_response: result },
          },
        ]));
      }
      return Promise.resolve(streamResponse([
        { type: "run_started", run_id: "run_1", request_id: "req_1", data: {} },
      ]));
    });
    vi.stubGlobal("fetch", fetchMock);
    const stages: SearchTaskProgressStage[] = [];

    const workspace = new HttpTeacherWorkspace();
    await expect(workspace.searchQuestions(
      { query: "找椭圆题", sessionId: "tch_1" },
      { onProgress: ({ stage }) => stages.push(stage) },
    )).resolves.toEqual(result);

    expect(stages).toEqual(["connecting", "understanding", "recovering"]);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({ method: "POST" });
    expect(String(fetchMock.mock.calls[1]?.[0])).toBe("/api/v1/agent/search/run_1/stream");
  });

  it("reports a stable error when the saved run has no terminal result", async () => {
    const fetchMock = vi.fn(async () => streamResponse([
      { type: "run_started", run_id: "run_pending", request_id: "req_pending", data: {} },
    ]));
    vi.stubGlobal("fetch", fetchMock);

    const workspace = new HttpTeacherWorkspace();
    const failure = workspace.searchQuestions({ query: "找题", sessionId: "tch_pending" });
    await expect(failure).rejects.toMatchObject({
      code: "STREAM_RECOVERY_FAILED",
      message: "任务连接中断，且未能取回同一次运行的结果。",
      requestId: "req_pending",
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("preserves a saved terminal failure instead of hiding it as a recovery error", async () => {
    let requestCount = 0;
    const fetchMock = vi.fn(async () => {
      requestCount += 1;
      if (requestCount === 1) {
        return streamResponse([
          { type: "run_started", run_id: "run_failed", request_id: "req_failed", data: {} },
        ]);
      }
      return streamResponse([
        { type: "run_started", run_id: "run_failed", request_id: "req_failed", data: {} },
        {
          type: "run_failed",
          run_id: "run_failed",
          request_id: "req_failed",
          data: {
            error: {
              code: "TOOL_TIMEOUT",
              message: "工具调用超时",
              request_id: "req_failed",
            },
          },
        },
      ]);
    });
    vi.stubGlobal("fetch", fetchMock);

    const workspace = new HttpTeacherWorkspace();
    const failure = workspace.searchQuestions({ query: "找题", sessionId: "tch_failed" });
    await expect(failure).rejects.toMatchObject({
      code: "TOOL_TIMEOUT",
      message: "工具调用超时",
      requestId: "req_failed",
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("maps AbortSignal to the explicit server-side cancel endpoint", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/run_live/cancel")) {
        return Promise.resolve(new Response(JSON.stringify({ status: "cancelled" }), { status: 200 }));
      }
      const stream = new ReadableStream({
        start(controller) {
          controller.enqueue(eventBlock({
            type: "run_started",
            run_id: "run_live",
            request_id: "req_live",
            data: {},
          }));
          init?.signal?.addEventListener("abort", () => {
            controller.error(new DOMException("cancelled", "AbortError"));
          }, { once: true });
        },
      });
      return Promise.resolve(new Response(stream, {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      }));
    });
    vi.stubGlobal("fetch", fetchMock);

    const controller = new AbortController();
    const workspace = new HttpTeacherWorkspace();
    const pending = workspace.searchQuestions(
      { query: "找题", sessionId: "tch_live" },
      { signal: controller.signal },
    );
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    await new Promise((resolve) => setTimeout(resolve, 0));
    controller.abort();

    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
    await vi.waitFor(() => {
      expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/run_live/cancel"))).toBe(true);
    });
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/run_live/stream"))).toBe(false);
  });

  it("returns a structured Solve result and reports trusted progress stages", async () => {
    const result = solveResultFixture();
    vi.stubGlobal("fetch", vi.fn(async () => streamResponse([
      { type: "run_started", run_id: "run_solve_1", request_id: "req_solve_1", data: {} },
      { type: "tool_started", run_id: "run_solve_1", request_id: "req_solve_1", data: { tool_name: "solve_question" } },
      { type: "tool_finished", run_id: "run_solve_1", request_id: "req_solve_1", data: { tool_name: "solve_question", status: "ok" } },
      {
        type: "run_completed",
        run_id: "run_solve_1",
        request_id: "req_solve_1",
        data: { solve_response: result },
      },
    ])));
    const stages: SolveTaskProgressStage[] = [];

    const workspace = new HttpTeacherWorkspace();
    await expect(workspace.solveQuestion(
      { questionText: "解方程 2x-4=0。", sessionId: "tch_solve_1" },
      { onProgress: ({ stage }) => stages.push(stage) },
    )).resolves.toEqual(result);

    expect(stages).toEqual(["connecting", "understanding", "solving", "verifying"]);
    expect(fetch).toHaveBeenCalledWith(
      "/api/v1/agent/solve/stream",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          question_text: "解方程 2x-4=0。",
          session_id: "tch_solve_1",
          solution_mode: "standard",
          teacher_instruction: "",
        }),
      }),
    );
  });

  it("recovers the same Solve run snapshot without repeating execution", async () => {
    const result = solveResultFixture();
    const fetchMock = vi.fn((input: RequestInfo | URL, _init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/run_solve_1/stream")) {
        return Promise.resolve(streamResponse([
          { type: "run_started", run_id: "run_solve_1", request_id: "req_solve_1", data: {} },
          {
            type: "run_completed",
            run_id: "run_solve_1",
            request_id: "req_solve_1",
            data: { solve_response: result },
          },
        ]));
      }
      return Promise.resolve(streamResponse([
        { type: "run_started", run_id: "run_solve_1", request_id: "req_solve_1", data: {} },
      ]));
    });
    vi.stubGlobal("fetch", fetchMock);

    const workspace = new HttpTeacherWorkspace();
    await expect(workspace.solveQuestion({
      questionText: "解方程 2x-4=0。",
      sessionId: "tch_solve_1",
    })).resolves.toEqual(result);

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({ method: "POST" });
    expect(String(fetchMock.mock.calls[1]?.[0])).toBe("/api/v1/agent/solve/run_solve_1/stream");
  });

  it("maps Solve AbortSignal to the Solve cancel endpoint", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/run_solve_live/cancel")) {
        return Promise.resolve(new Response(JSON.stringify({ status: "cancelled" }), { status: 200 }));
      }
      const stream = new ReadableStream({
        start(controller) {
          controller.enqueue(eventBlock({
            type: "run_started",
            run_id: "run_solve_live",
            request_id: "req_solve_live",
            data: {},
          }));
          init?.signal?.addEventListener("abort", () => {
            controller.error(new DOMException("cancelled", "AbortError"));
          }, { once: true });
        },
      });
      return Promise.resolve(new Response(stream, {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      }));
    });
    vi.stubGlobal("fetch", fetchMock);

    const controller = new AbortController();
    const workspace = new HttpTeacherWorkspace();
    const pending = workspace.solveQuestion(
      { questionText: "解方程 2x-4=0。", sessionId: "tch_solve_live" },
      { signal: controller.signal },
    );
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    await new Promise((resolve) => setTimeout(resolve, 0));
    controller.abort();

    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
    await vi.waitFor(() => {
      expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/run_solve_live/cancel"))).toBe(true);
    });
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/run_solve_live/stream"))).toBe(false);
  });
});
