import { afterEach, describe, expect, it, vi } from "vitest";
import type { SearchTaskProgressStage, SearchTaskResult } from "./contracts";
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

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("HttpTeacherWorkspace", () => {
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
    vi.stubGlobal("fetch", vi.fn(async () => streamResponse([
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
    ])));

    const workspace = new HttpTeacherWorkspace();
    const failure = workspace.searchQuestions({ query: "找题", sessionId: "tch_2" });
    await expect(failure).rejects.toMatchObject({
      code: "TOOL_TIMEOUT",
      message: "工具调用超时",
      requestId: "req_2",
    });
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
  });
});
