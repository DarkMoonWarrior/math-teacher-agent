import { afterEach, describe, expect, it, vi } from "vitest";
import type {
  SearchTaskProgressStage,
  SearchTaskResult,
  SolveTaskProgressStage,
  SolveTaskResult,
  LibraryItemDetail,
  LibraryItemSummary,
  QuestionInputBundle,
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
      visual_context: null,
    },
    tool_request_id: "req_tool_solve",
    duration_ms: 24,
    tool_call_count: 1,
    error: null,
  };
}

function questionInputBundleFixture(): QuestionInputBundle {
  return {
    asset: {
      asset_id: "qcap_1",
      original_filename: "question.png",
      source: "upload",
      source_sha256: "synthetic-sha256",
      current_revision: 1,
      width: 1200,
      height: 800,
      size_bytes: 2048,
      mime_type: "image/png",
      clarity_status: "clear",
      warnings: [],
      revisions: [{
        revision: 1,
        source_revision: null,
        operation: "original",
        width: 1200,
        height: 800,
        mime_type: "image/png",
        content_endpoint: "/api/v1/question-capture/assets/qcap_1/content?revision=1",
        created_at: "2026-08-22T00:00:00Z",
      }],
      visibility: "private",
      public_search_allowed: false,
      model_training_allowed: false,
      created_at: "2026-08-22T00:00:00Z",
      updated_at: "2026-08-22T00:00:00Z",
    },
    recognition_status: "not_started",
    recognition_revision: null,
    recognition_source_revision: null,
    recognition_mode: null,
    recognition_provider: null,
    recognition_model: null,
    stem_plain: "",
    stem_latex: "",
    options: [],
    requires_visual_reasoning: null,
    low_confidence_regions: [],
    recognition_warnings: [],
    external_processing_consent: false,
    teacher_review_note: "",
    visibility: "private",
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

function libraryItemDetailFixture(): LibraryItemDetail {
  return {
    ...libraryItemFixture(),
    source_sha256: "synthetic-sha256",
    extracted_text: "已提取的函数讲义正文。",
    corrected_text: "已提取的函数讲义正文。",
    rights_statement: "仅在本人的私人教学工作区内使用。",
    adaptation_allowed: false,
    warnings: [],
    review_note: "",
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("HttpTeacherWorkspace", () => {
  it("uploads a private question image without exposing owner or external consent", async () => {
    const bundle = questionInputBundleFixture();
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => new Response(JSON.stringify(bundle), {
      status: 201,
      headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);
    const file = new File([new Uint8Array([1, 2, 3])], "question.png", { type: "image/png" });

    const workspace = new HttpTeacherWorkspace();
    await expect(workspace.uploadQuestionMedia({
      file,
      source: "clipboard",
      privateStorageAcknowledged: true,
    })).resolves.toEqual(bundle);

    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    const body = init.body as FormData;
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/v1/question-capture/assets");
    expect(body.get("source")).toBe("clipboard");
    expect(body.get("private_storage_acknowledged")).toBe("true");
    expect(body.has("owner_id")).toBe(false);
    expect(body.has("external_processing_consent")).toBe(false);
  });

  it("transforms a controlled question asset by id without storage paths", async () => {
    const bundle = questionInputBundleFixture();
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => new Response(JSON.stringify(bundle), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);

    const workspace = new HttpTeacherWorkspace();
    await expect(workspace.transformQuestionMedia("qcap_1", {
      operation: "crop",
      crop: { x: 10, y: 20, width: 900, height: 600 },
    })).resolves.toEqual(bundle);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/question-capture/assets/qcap_1/transform",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          operation: "crop",
          crop: { x: 10, y: 20, width: 900, height: 600 },
        }),
      }),
    );
  });

  it("recognizes a private question with per-action external consent and no owner selector", async () => {
    const bundle = { ...questionInputBundleFixture(), recognition_status: "draft" as const };
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => new Response(JSON.stringify(bundle), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);

    const workspace = new HttpTeacherWorkspace();
    await workspace.recognizeQuestionMedia("qcap_1", {
      mode: "external",
      externalProcessingConsent: true,
    });

    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/v1/question-capture/assets/qcap_1/recognize");
    expect(JSON.parse(String(init.body))).toEqual({
      mode: "external",
      external_processing_consent: true,
    });
    expect(String(init.body)).not.toContain("owner");
  });

  it("saves a teacher recognition review as a controlled revision", async () => {
    const bundle = { ...questionInputBundleFixture(), recognition_status: "confirmed" as const };
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => new Response(JSON.stringify(bundle), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);

    const workspace = new HttpTeacherWorkspace();
    await workspace.reviewQuestionRecognition("qcap_1", {
      stemPlain: "校对题面",
      stemLatex: "$x^2$",
      options: [{ key: "A", text: "1" }],
      note: "已核对",
      confirm: true,
    });

    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/v1/question-capture/assets/qcap_1/recognition");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(String(init.body))).toEqual({
      stem_plain: "校对题面",
      stem_latex: "$x^2$",
      options: [{ key: "A", text: "1" }],
      note: "已核对",
      confirm: true,
    });
  });

  it("requires an explicit one-action consent when searching private excerpts", async () => {
    const result = {
      query: "函数",
      items: [{
        library_item_id: "lib_1",
        title: "函数讲义",
        excerpt: "函数单调性的课堂例题。",
        source_version: 2,
        rights_basis: "original",
        text_review_status: "confirmed",
        visibility: "private",
      }],
      total: 1,
      truncated: false,
      content_scope: "matching_excerpts",
      visibility: "private",
    } as const;
    const fetchMock = vi.fn((_input: RequestInfo | URL, _init?: RequestInit) => Promise.resolve(new Response(JSON.stringify({
      status: "ok",
      result,
    }), { status: 200, headers: { "Content-Type": "application/json" } })));
    vi.stubGlobal("fetch", fetchMock);

    const workspace = new HttpTeacherWorkspace();
    await expect(workspace.searchPrivateLibrary("函数", true)).resolves.toEqual(result);
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/v1/agent/private-library/search");
    expect(JSON.parse(String(init.body))).toEqual({
      query: "函数",
      private_content_consent: true,
      limit: 5,
    });
    expect(String(init.body)).not.toContain("owner_id");
  });

  it("does not turn an aborted private retrieval into a successful result", async () => {
    const fetchMock = vi.fn((_input: RequestInfo | URL, init?: RequestInit) => new Promise<Response>((_resolve, reject) => {
      init?.signal?.addEventListener("abort", () => reject(new DOMException("cancelled", "AbortError")), { once: true });
    }));
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();
    const workspace = new HttpTeacherWorkspace();
    const pending = workspace.searchPrivateLibrary("函数", true, controller.signal);
    controller.abort();
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
  });

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

  it("loads an owner-scoped item and its text revisions", async () => {
    const detail = libraryItemDetailFixture();
    const revisions = {
      library_item_id: detail.library_item_id,
      current_version: 1,
      items: [],
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
      const url = String(input);
      return new Response(JSON.stringify(url.endsWith("/revisions") ? revisions : detail), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    const workspace = new HttpTeacherWorkspace();
    await expect(workspace.getPrivateLibraryItem("lib_1")).resolves.toEqual(detail);
    await expect(workspace.listPrivateLibraryRevisions("lib_1")).resolves.toEqual(revisions);

    expect(fetchMock.mock.calls.map(([url]) => String(url))).toEqual([
      "/api/v1/library/lib_1",
      "/api/v1/library/lib_1/revisions",
    ]);
  });

  it("saves a private text review without accepting browser-supplied actor ids", async () => {
    const detail = { ...libraryItemDetailFixture(), version: 2, review_note: "核对公式" };
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => new Response(JSON.stringify(detail), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);

    const workspace = new HttpTeacherWorkspace();
    await expect(workspace.reviewPrivateLibraryText("lib_1", {
      correctedText: "校对后的函数讲义正文。",
      note: "核对公式",
      confirm: false,
    })).resolves.toEqual(detail);

    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/v1/library/lib_1/review");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(String(init.body))).toEqual({
      corrected_text: "校对后的函数讲义正文。",
      note: "核对公式",
      confirm: false,
    });
    expect(String(init.body)).not.toContain("owner_id");
    expect(String(init.body)).not.toContain("reviewer_id");
  });

  it("hides local OCR job mechanics behind the workspace contract", async () => {
    const detail = { ...libraryItemDetailFixture(), version: 2, corrected_text: "OCR 草稿" };
    const result = { item: detail, provider: "local_math_ocr", warnings: [] };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/local-math-ocr/jobs")) {
        expect(init?.body).toBeUndefined();
        return new Response(JSON.stringify({
          job_id: "job_local",
          status: "running",
          message: "正在识别",
          result: null,
          error: null,
        }), { status: 202, headers: { "Content-Type": "application/json" } });
      }
      return new Response(JSON.stringify({
        job_id: "job_local",
        status: "completed",
        message: "识别完成",
        result,
        error: null,
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    });
    vi.stubGlobal("fetch", fetchMock);
    const progress: string[] = [];

    const workspace = new HttpTeacherWorkspace();
    await expect(workspace.processPrivateLibraryOCR(
      "lib_1",
      { mode: "local", externalProcessingConsent: false },
      { onProgress: (message) => progress.push(message) },
    )).resolves.toEqual(result);

    expect(fetchMock.mock.calls.map(([url]) => String(url))).toEqual([
      "/api/v1/library/lib_1/local-math-ocr/jobs",
      "/api/v1/library/jobs/job_local",
    ]);
    expect(progress).toEqual(["正在准备本地数学 OCR", "正在识别", "识别完成"]);
  });

  it("sends per-action consent and no private actor metadata to external OCR", async () => {
    const result = {
      item: libraryItemDetailFixture(),
      provider: "external_ocr",
      warnings: ["请教师复核"],
    };
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => new Response(JSON.stringify({
      job_id: "job_external",
      status: "completed",
      message: "识别完成",
      result,
      error: null,
    }), { status: 202, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    const workspace = new HttpTeacherWorkspace();
    await expect(workspace.processPrivateLibraryOCR("lib_1", {
      mode: "external",
      externalProcessingConsent: true,
    })).resolves.toEqual(result);

    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/v1/library/lib_1/ocr/jobs");
    expect(JSON.parse(String(init.body))).toEqual({ external_processing_consent: true });
  });

  it("keeps candidate actors and curriculum labels out of browser-controlled payloads", async () => {
    const candidate = {
      candidate_id: "cand_1",
      library_item_id: "lib_1",
      source_version: 2,
      position: 1,
      question_type: "open_response" as const,
      stem_plain: "已知函数 f(x)=x²，求 f(2)。",
      stem_latex: null,
      options: [],
      answer_value: "4",
      solution_method: "代入",
      solution_steps: ["代入 x=2"],
      final_answer: "4",
      difficulty: 2,
      curriculum: null,
      status: "draft" as const,
      warnings: [],
      imported_question_id: null,
      updated_at: "2026-08-22T10:00:00+08:00",
    };
    const listing = { library_item_id: "lib_1", source_version: 2, items: [candidate] };
    const curriculum = {
      query: "函数",
      total: 1,
      items: [{
        node_id: "kp_function",
        code: "3.1.1",
        name: "函数的概念",
        node_type: "knowledge_point" as const,
        volume: "必修第一册",
        chapter: "函数的概念与性质",
        section: "函数的概念",
        description: "函数定义",
        match_score: 1,
      }],
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
      const url = String(input);
      const payload = url.includes("/curriculum/search")
        ? curriculum
        : url.endsWith("/import")
          ? { candidate, question_id: "q_private_1", already_imported: false }
          : url.endsWith("/question-candidates")
            ? listing
            : candidate;
      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    const workspace = new HttpTeacherWorkspace();
    const draft = {
      question_type: candidate.question_type,
      stem_plain: candidate.stem_plain,
      stem_latex: candidate.stem_latex,
      options: candidate.options,
      answer_value: candidate.answer_value,
      solution_method: candidate.solution_method,
      solution_steps: candidate.solution_steps,
      final_answer: candidate.final_answer,
      difficulty: candidate.difficulty,
    };

    await workspace.listPrivateLibraryQuestionCandidates("lib_1");
    await workspace.preparePrivateLibraryQuestionCandidates("lib_1");
    await workspace.updatePrivateLibraryQuestionCandidate("lib_1", "cand_1", draft);
    await workspace.searchCurriculum("函数");
    await workspace.mapPrivateLibraryQuestionCandidateCurriculum("lib_1", "cand_1", "kp_function");
    await workspace.importPrivateLibraryQuestionCandidate("lib_1", "cand_1");

    const calls = fetchMock.mock.calls;
    expect(calls.map(([url]) => String(url))).toEqual([
      "/api/v1/library/lib_1/question-candidates",
      "/api/v1/library/lib_1/question-candidates",
      "/api/v1/library/lib_1/question-candidates/cand_1",
      "/api/v1/curriculum/search?query=%E5%87%BD%E6%95%B0&node_type=knowledge_point&limit=8",
      "/api/v1/library/lib_1/question-candidates/cand_1/curriculum",
      "/api/v1/library/lib_1/question-candidates/cand_1/import",
    ]);
    expect((calls[1]?.[1] as RequestInit).method).toBe("POST");
    expect(JSON.parse(String((calls[2]?.[1] as RequestInit).body))).toEqual(draft);
    expect(JSON.parse(String((calls[4]?.[1] as RequestInit).body))).toEqual({ node_id: "kp_function" });
    expect(String((calls[2]?.[1] as RequestInit).body)).not.toContain("owner_id");
    expect(String((calls[4]?.[1] as RequestInit).body)).not.toContain("volume");
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
          question_capture: null,
        }),
      }),
    );
  });

  it("sends only opaque confirmed revisions and one-run visual consent to Solve", async () => {
    const result = solveResultFixture();
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => streamResponse([{
      type: "run_completed",
      run_id: "run_visual",
      request_id: "req_visual",
      data: { solve_response: result },
    }]));
    vi.stubGlobal("fetch", fetchMock);

    await new HttpTeacherWorkspace().solveQuestion({
      questionText: "如图，在三角形 ABC 中求角 A。",
      sessionId: "tch_visual",
      questionCapture: {
        assetId: "qcap_private_1",
        mediaRevision: 2,
        recognitionRevision: 5,
        visualProcessingConsent: true,
      },
    });

    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    const body = JSON.parse(String(init.body));
    expect(body.question_capture).toEqual({
      asset_id: "qcap_private_1",
      media_revision: 2,
      recognition_revision: 5,
      visual_processing_consent: true,
    });
    expect(JSON.stringify(body)).not.toContain("content_endpoint");
    expect(JSON.stringify(body)).not.toContain("image_bytes");
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
