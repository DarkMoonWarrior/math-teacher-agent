import { afterEach, describe, expect, it, vi } from "vitest";
import type {
  SearchTaskProgressStage,
  SearchTaskResult,
  SolveTaskProgressStage,
  SolveTaskResult,
  LibraryItemDetail,
  LibraryItemSummary,
  GeneratedQuestionDraft,
  PersonalAuthoringDraft,
  PersonalQuestion,
  ConfirmedLessonBlueprint,
  LessonBlueprintDraft,
  LessonEditableDraft,
  LessonSourceDraft,
  PaperBlueprintDraft,
  PaperBlueprintSelectionDraft,
  PaperEditableDraft,
  PaperSavedVersion,
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
    visual_observations: [],
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

function generatedQuestionDraftFixture(saved = false): GeneratedQuestionDraft {
  return {
    draft_id: "qad_1",
    request_text: "命一道高二椭圆离心率单选题，中等难度。",
    question_type: "single_choice",
    stem_plain: "已知椭圆的长半轴长为 2，焦距为 2，求离心率。",
    stem_latex: "已知椭圆的长半轴长为 $2$，焦距为 $2$，求离心率。",
    options: [
      { key: "A", text: "$\\frac{1}{2}$" },
      { key: "B", text: "$1$" },
      { key: "C", text: "$2$" },
      { key: "D", text: "$4$" },
    ],
    answer_value: "A",
    solution_method: "使用椭圆离心率定义",
    solution_steps: ["由焦距 $2c=2$ 得 $c=1$。", "所以 $e=c/a=1/2$。"],
    solution_status: "ready",
    solution_issue: null,
    final_answer: "$\\frac{1}{2}$",
    authoring_intent: "检查学生是否区分焦距与半焦距。",
    knowledge_points: ["椭圆离心率"],
    assessed_methods: ["使用离心率定义建立数量关系"],
    common_mistakes: ["混淆焦距与半焦距"],
    curriculum: {
      node_id: "kp_ellipse_eccentricity",
      name: "椭圆的离心率",
      volume: "选择性必修第一册",
      chapter: "圆锥曲线的方程",
      section: "椭圆",
      mapping_source: "brief_match",
      mapping_status: "pending_teacher_confirmation",
      match_confidence: 0.94,
      curriculum_status: "reviewed",
      reviewed_by: "system",
    },
    pedagogy_source: "model_generated",
    target_difficulty: 3,
    estimated_difficulty: 3,
    difficulty_source: "model_estimated",
    verification: {
      status: "teacher_review_required",
      math_verifier_status: "unsupported",
      math_verifier_checked: false,
      teacher_review_required: true,
      verifier_version: "math-verifier-v1",
      checks: [
        { code: "solvability", status: "passed", capability: "supported", evidence_source: "deterministic_structure", summary: "题目字段完整。", details: [] },
        { code: "answer_solution_consistency", status: "passed", capability: "supported", evidence_source: "deterministic_structure", summary: "答案与解析一致。", details: [] },
        { code: "choice_answer_cardinality", status: "passed", capability: "supported", evidence_source: "deterministic_structure", summary: "单选题只有一个答案。", details: [] },
        { code: "distractor_quality", status: "inconclusive", capability: "supported", evidence_source: "model_estimate", summary: "干扰项需教师复核。", details: [] },
        { code: "math_verifier", status: "inconclusive", capability: "unsupported", evidence_source: "none", summary: "当前验证器不支持。", details: [] },
        { code: "difficulty_disclosure", status: "passed", capability: "supported", evidence_source: "model_estimate", summary: "难度为模型估计。", details: [] },
      ],
      details: ["AI 生成草稿需要教师复核。"],
    },
    source_type: "ai_generated",
    visibility: "owner_only",
    public_search_allowed: false,
    share_allowed: false,
    commercial_use_allowed: false,
    model_training_allowed: false,
    saved,
    provider: "deepseek",
    model: "deepseek-v4-pro",
    prompt_revision: "question-authoring-v1",
    warnings: ["难度仅为模型估计。"],
    created_at: "2026-08-24T10:00:00+08:00",
  };
}

function personalAuthoringDraftFixture(): PersonalAuthoringDraft {
  const draft = generatedQuestionDraftFixture();
  return {
    draft_id: draft.draft_id,
    current_revision: 1,
    saved: false,
    saved_question_id: null,
    current: {
      draft_id: draft.draft_id,
      revision_number: 1,
      revision_source: "ai_generated",
      edit_summary: "AI 初稿",
      draft,
      created_at: draft.created_at,
    },
    created_at: draft.created_at,
    updated_at: draft.created_at,
    visibility: "owner_only",
    public_search_allowed: false,
    share_allowed: false,
    commercial_use_allowed: false,
    model_training_allowed: false,
  };
}

function personalQuestionFixture(): PersonalQuestion {
  const draft = generatedQuestionDraftFixture(true);
  return {
    question_id: "pq_1",
    collection_id: "pc_1",
    category_id: "cat_1",
    name: "椭圆离心率课堂题",
    source_draft_id: draft.draft_id,
    selected_revision: 1,
    tags: ["椭圆"],
    sort_order: 0,
    lifecycle_state: "active",
    trashed_at: null,
    copied_from_question_id: null,
    question: draft,
    created_at: draft.created_at,
    updated_at: "2026-08-24T10:05:00+08:00",
    visibility: "owner_only",
    public_search_allowed: false,
    share_allowed: false,
    commercial_use_allowed: false,
    model_training_allowed: false,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("HttpTeacherWorkspace", () => {
  it("plans a lesson blueprint without submitting owner, trust facts, or persistence commands", async () => {
    const blueprint: LessonBlueprintDraft = {
      status: "lesson_blueprint_draft",
      editable: true,
      confirmed: false,
      saved: false,
      source_brief: "为高二椭圆准备一节 45 分钟新授课",
      title: "高二椭圆新授课教案",
      grade_scope: "高二",
      lesson_type: "new_lesson",
      lesson_format: "新授课",
      duration_minutes: 45,
      student_profile: "基础中等，需要支架",
      focus: "椭圆定义与标准方程",
      question_count: 3,
      curriculum_query: "椭圆",
      selected_curriculum_node_id: "ellipse",
      curriculum_candidates: [{
        node_id: "ellipse", node_type: "section", name: "椭圆", volume: "选择性必修第一册",
        chapter: "圆锥曲线的方程", section: "椭圆", description: "椭圆的定义与方程",
        competencies: ["数学抽象"], common_errors: ["忽略焦点位置"],
        catalog_status: "draft_for_teacher_review", reviewed_by: "pending_owner_teacher", match_score: 1,
      }],
      objectives: ["理解椭圆定义"],
      key_points: ["椭圆定义"],
      difficulties: ["建系与化简"],
      phases: [
        { phase_id: "intro", title: "导入", minutes: 5, purpose: "唤起经验" },
        { phase_id: "build", title: "建构", minutes: 25, purpose: "形成定义" },
        { phase_id: "practice", title: "练习", minutes: 15, purpose: "反馈" },
      ],
      required_blocks: ["objectives", "key_points", "difficulties", "teaching_flow", "homework", "board_plan", "teacher_notes"],
      assumptions: [],
      trust_policy: {
        curriculum_source: "sealed_pep_a_baseline",
        question_policy: "not_selected_during_planning",
        private_resource_policy: "explicit_owner_selection_only",
        ai_content_status: "draft_requires_teacher_review",
        auto_save_allowed: false,
        preserves_source_traceability: true,
      },
      side_effects: [],
    };
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => new Response(JSON.stringify(blueprint), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(new HttpTeacherWorkspace().planLessonBlueprint(blueprint.source_brief)).resolves.toEqual(blueprint);

    const url = fetchMock.mock.calls[0]?.[0];
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(url).toBe("/api/v1/lesson-plans/blueprints/plan");
    expect(init).toEqual(expect.objectContaining({ method: "POST" }));
    expect(JSON.parse(String(init.body))).toEqual({ brief: blueprint.source_brief });
    expect(String(init.body)).not.toMatch(/owner|visibility|auto_save|teacher_id/i);
  });

  it("confirms and selects lesson sources without browser-owned identity or trust selectors", async () => {
    const draft = {
      status: "lesson_blueprint_draft",
      confirmed: false,
      source_brief: "高二椭圆新授课",
      selected_curriculum_node_id: "ellipse",
    } as LessonBlueprintDraft;
    const confirmed = {
      ...draft,
      status: "lesson_blueprint_confirmed",
      confirmed: true,
    } as ConfirmedLessonBlueprint;
    const sourceDraft = {
      status: "lesson_source_draft", blueprint: confirmed, editable: true, saved: false,
      selection_complete: true, curriculum: null, questions: [], private_resources: [], gaps: [],
      warnings: [], trust_policy: {}, side_effects: [],
    } as LessonSourceDraft;
    const lessonDraft = {
      status: "lesson_editable_draft", draft_revision: 1, source_draft: sourceDraft,
      editable: true, saved: false, locked_blocks: [], rewrite_history: [], side_effects: [],
    } as unknown as LessonEditableDraft;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
      const url = String(input);
      const payload = url.endsWith("source-options")
        ? { status: "lesson_source_options", blueprint: confirmed, public_questions: [], private_questions: [], private_resources: [], trust_statement: "", side_effects: [] }
        : url.endsWith("build-draft") || url.endsWith("rewrite-block")
          ? lessonDraft
          : sourceDraft;
      return new Response(JSON.stringify(payload), { status: 200, headers: { "Content-Type": "application/json" } });
    });
    vi.stubGlobal("fetch", fetchMock);

    await new HttpTeacherWorkspace().listLessonSourceOptions(draft);
    await new HttpTeacherWorkspace().selectLessonSources(
      confirmed,
      ["public-1"],
      ["private-1"],
      ["resource-1"],
    );
    await new HttpTeacherWorkspace().buildLessonDraft(sourceDraft);
    await new HttpTeacherWorkspace().rewriteLessonDraftBlock(
      lessonDraft,
      "homework",
      "增加分层迁移任务",
    );

    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/v1/lesson-plans/blueprints/source-options");
    expect(JSON.parse(String((fetchMock.mock.calls[0]?.[1] as RequestInit).body))).toEqual({ blueprint: draft });
    expect(fetchMock.mock.calls[1]?.[0]).toBe("/api/v1/lesson-plans/blueprints/select-sources");
    const selectionBody = JSON.parse(String((fetchMock.mock.calls[1]?.[1] as RequestInit).body));
    expect(selectionBody).toEqual({
      blueprint: confirmed,
      selected_public_question_ids: ["public-1"],
      selected_private_question_ids: ["private-1"],
      selected_private_resource_ids: ["resource-1"],
    });
    expect(JSON.stringify(selectionBody)).not.toMatch(/teacher_id|owner_id|visibility|file_path/i);
    expect(fetchMock.mock.calls[2]?.[0]).toBe("/api/v1/lesson-plans/blueprints/build-draft");
    const draftingBody = JSON.parse(String((fetchMock.mock.calls[2]?.[1] as RequestInit).body));
    expect(draftingBody).toEqual({ source_draft: sourceDraft });
    expect(JSON.stringify(draftingBody)).not.toMatch(/teacher_id|owner_id|visibility|file_path|auto_save/i);
    expect(fetchMock.mock.calls[3]?.[0]).toBe("/api/v1/lesson-plans/blueprints/rewrite-block");
    const rewriteBody = JSON.parse(String((fetchMock.mock.calls[3]?.[1] as RequestInit).body));
    expect(rewriteBody).toEqual({
      draft: lessonDraft,
      target_block: "homework",
      instruction: "增加分层迁移任务",
      expected_draft_revision: 1,
    });
    expect(JSON.stringify(rewriteBody)).not.toMatch(/teacher_id|owner_id|visibility|file_path|auto_save/i);
  });

  it("plans a paper blueprint without submitting owner, trust facts, or persistence commands", async () => {
    const blueprint: PaperBlueprintDraft = {
      status: "draft",
      editable: true,
      confirmed: false,
      saved: false,
      source_brief: "组一份高二期中卷",
      title: "高二函数期中检测",
      grade_scope: "高二",
      teaching_usage: "期中检测",
      duration_minutes: 90,
      target_score: 100,
      difficulty_profile: "balanced",
      knowledge_points: ["函数"],
      sections: [{ section_id: "single", title: "单项选择题", question_type: "single_choice", question_count: 8, target_score: 100 }],
      assumptions: [],
      trust_policy: {
        verification_policy: "passed_only",
        review_policy: "approved_only",
        private_question_policy: "explicit_owner_selection_only",
        auto_authoring_allowed: false,
        preserves_source_and_rights: true,
      },
      side_effects: [],
    };
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => new Response(JSON.stringify(blueprint), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(new HttpTeacherWorkspace().planPaperBlueprint("组一份高二期中卷")).resolves.toEqual(blueprint);

    const url = fetchMock.mock.calls[0]?.[0];
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(url).toBe("/api/v1/exam-papers/blueprints/plan");
    expect(init).toEqual(expect.objectContaining({ method: "POST" }));
    expect(JSON.parse(String(init.body))).toEqual({ brief: "组一份高二期中卷" });
    expect(String(init.body)).not.toMatch(/owner|verification|visibility|save/i);
  });

  it("reads the gated public paper catalog without owner or trust selectors", async () => {
    const catalog = {
      items: [{
        question_id: "public_1", question_type: "single_choice", stem_plain: "函数题",
        options: [{ key: "A", text: "0" }], difficulty: 2, chapter: "函数",
        knowledge_points: ["函数"], source_document: "公共题库",
      }],
      total: 1,
      trust_statement: "仅展示通过公共可见性、权利、数学验证、教师审核和在架门禁的题目",
      side_effects: [],
    };
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => new Response(JSON.stringify(catalog), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);

    await new HttpTeacherWorkspace().listPaperPublicCandidates({ query: "函数", questionType: "single_choice", limit: 20 });

    const url = String(fetchMock.mock.calls[0]?.[0]);
    expect(url).toBe("/api/v1/exam-papers/blueprints/public-candidates?limit=20&query=%E5%87%BD%E6%95%B0&question_type=single_choice");
    expect(url).not.toMatch(/owner|verification|review|visibility/i);
  });

  it("confirms editable blueprint facts and explicit public/private ids without browser-owned trust facts", async () => {
    const blueprint: PaperBlueprintDraft = {
      status: "draft",
      editable: true,
      confirmed: false,
      saved: false,
      source_brief: "组一份函数测验",
      title: "函数测验",
      grade_scope: "高二",
      teaching_usage: "专题测验",
      duration_minutes: 30,
      target_score: 10,
      difficulty_profile: "balanced",
      knowledge_points: ["函数"],
      sections: [{ section_id: "single", title: "单选题", question_type: "single_choice", question_count: 2, target_score: 10 }],
      assumptions: [],
      trust_policy: {
        verification_policy: "passed_only",
        review_policy: "approved_only",
        private_question_policy: "explicit_owner_selection_only",
        auto_authoring_allowed: false,
        preserves_source_and_rights: true,
      },
      side_effects: [],
    };
    const selection = {
      status: "selection_draft",
      blueprint_confirmed: true,
      editable: true,
      saved: false,
      selection_complete: false,
      blueprint: {
        title: blueprint.title,
        grade_scope: blueprint.grade_scope,
        teaching_usage: blueprint.teaching_usage,
        duration_minutes: blueprint.duration_minutes,
        target_score: blueprint.target_score,
        difficulty_profile: blueprint.difficulty_profile,
        knowledge_points: blueprint.knowledge_points,
        sections: blueprint.sections,
      },
      target_question_count: 2,
      actual_question_count: 0,
      target_score: 10,
      actual_score: 0,
      items: [],
      gaps: [],
      coverage_audit: {
        status: "needs_adjustment",
        coverage_complete: false,
        difficulty_status: "insufficient_supply",
        target_average_difficulty: 3,
        actual_average_difficulty: null,
        average_difficulty_gap: null,
        sections: [{
          section_id: "single",
          section_title: "单选题",
          target_question_count: 2,
          actual_question_count: 0,
          target_score: 10,
          actual_score: 0,
          status: "short",
        }],
        knowledge_points: [{
          knowledge_point: "函数",
          actual_question_count: 0,
          actual_score: 0,
          status: "missing",
        }],
        difficulty_bands: [1, 2, 3, 4, 5].map((difficulty) => ({
          difficulty,
          target_question_count: difficulty === 2 || difficulty === 3 ? 1 : 0,
          actual_question_count: 0,
          actual_score: 0,
        })),
        side_effects: [],
      },
      similarity_exclusions: [],
      unselected_public_question_ids: [],
      unselected_private_question_ids: [],
      warnings: [],
      trust_policy: blueprint.trust_policy,
      auto_authoring_used: false,
      side_effects: [],
    } satisfies PaperBlueprintSelectionDraft;
    const fetchMock = vi.fn(async () => new Response(JSON.stringify(selection), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);

    await new HttpTeacherWorkspace().selectPaperBlueprint(blueprint, ["pqq_1"], ["public_1"]);

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    const body = JSON.parse(String(init.body));
    expect(url).toBe("/api/v1/exam-papers/blueprints/select");
    expect(body.selected_public_question_ids).toEqual(["public_1"]);
    expect(body.selected_private_question_ids).toEqual(["pqq_1"]);
    expect(body.blueprint).toEqual(expect.objectContaining({ title: "函数测验", target_score: 10 }));
    expect(body.blueprint).not.toHaveProperty("trust_policy");
    expect(body).not.toHaveProperty("owner_id");
    expect(String(init.body)).not.toMatch(/verification_policy|visibility|save/i);
  });

  it("submits only controlled selection facts and paper layout edits for an editable draft", async () => {
    const blueprint: PaperBlueprintDraft = {
      status: "draft",
      editable: true,
      confirmed: false,
      saved: false,
      source_brief: "组一份函数测验",
      title: "函数测验",
      grade_scope: "高二",
      teaching_usage: "专题测验",
      duration_minutes: 30,
      target_score: 10,
      difficulty_profile: "balanced",
      knowledge_points: ["函数"],
      sections: [{ section_id: "single", title: "单选题", question_type: "single_choice", question_count: 1, target_score: 10 }],
      assumptions: [],
      trust_policy: {
        verification_policy: "passed_only",
        review_policy: "approved_only",
        private_question_policy: "explicit_owner_selection_only",
        auto_authoring_allowed: false,
        preserves_source_and_rights: true,
      },
      side_effects: [],
    };
    const editableDraft = {
      status: "editable_paper_draft",
      editable: true,
      saved: false,
      version_created: false,
      export_ready: false,
      draft_fingerprint: "b".repeat(64),
      selection_complete: false,
      draft_consistent: false,
      score_status: "mismatch",
      blueprint: {
        title: blueprint.title,
        grade_scope: blueprint.grade_scope,
        teaching_usage: blueprint.teaching_usage,
        duration_minutes: blueprint.duration_minutes,
        target_score: blueprint.target_score,
        difficulty_profile: blueprint.difficulty_profile,
        knowledge_points: blueprint.knowledge_points,
        sections: blueprint.sections,
      },
      target_question_count: 1,
      actual_question_count: 0,
      target_score: 10,
      actual_score: 0,
      items: [],
      gaps: [],
      coverage_audit: {
        status: "needs_adjustment",
        coverage_complete: false,
        difficulty_status: "insufficient_supply",
        target_average_difficulty: 3,
        actual_average_difficulty: null,
        average_difficulty_gap: null,
        sections: [],
        knowledge_points: [],
        difficulty_bands: [1, 2, 3, 4, 5].map((difficulty) => ({ difficulty, target_question_count: 0, actual_question_count: 0, actual_score: 0 })),
        side_effects: [],
      },
      change_log: [],
      specification: { question_to_dimensions: [], dimension_to_questions: [] },
      warnings: [],
      trust_policy: blueprint.trust_policy,
      auto_authoring_used: false,
      side_effects: [],
    } satisfies PaperEditableDraft;
    const fetchMock = vi.fn(async () => new Response(JSON.stringify(editableDraft), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);

    await new HttpTeacherWorkspace().editPaperDraft(blueprint, ["pqq_1"], ["public_1"], [{
      question_id: "pqq_1",
      position: 1,
      section_id: "single",
      score: 10,
    }]);

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    const body = JSON.parse(String(init.body));
    expect(url).toBe("/api/v1/exam-papers/blueprints/edit-draft");
    expect(body.selection_request.selected_public_question_ids).toEqual(["public_1"]);
    expect(body.selection_request.selected_private_question_ids).toEqual(["pqq_1"]);
    expect(body.edits).toEqual([{ question_id: "pqq_1", position: 1, section_id: "single", score: 10 }]);
    expect(body).not.toHaveProperty("owner_id");
    expect(String(init.body)).not.toMatch(/verification_status|review_status|visibility|saved|version_created|export_ready/i);
  });

  it("saves an exact paper draft fingerprint without browser-owned owner or version facts", async () => {
    const blueprint: PaperBlueprintDraft = {
      status: "draft", editable: true, confirmed: false, saved: false, source_brief: "函数测验",
      title: "函数测验", grade_scope: "高二", teaching_usage: "专题测验", duration_minutes: 30,
      target_score: 10, difficulty_profile: "balanced", knowledge_points: ["函数"],
      sections: [{ section_id: "single", title: "单选题", question_type: "single_choice", question_count: 1, target_score: 10 }],
      assumptions: [],
      trust_policy: { verification_policy: "passed_only", review_policy: "approved_only", private_question_policy: "explicit_owner_selection_only", auto_authoring_allowed: false, preserves_source_and_rights: true },
      side_effects: [],
    };
    const saved = {
      status: "saved_paper_version", saved: true, version_created: true, export_ready: true,
      exam_paper_id: "paper-1", version: 1, title: "函数测验", question_count: 1, total_score: 10,
      draft_fingerprint: "c".repeat(64),
      specification: { question_to_dimensions: [], dimension_to_questions: [] },
      available_exports: [
        ["student", "docx"], ["student", "pdf"], ["answer", "docx"],
        ["answer", "pdf"], ["blueprint", "docx"], ["blueprint", "pdf"],
      ].map(([edition, format]) => ({ edition, format, label: `${edition}-${format}` })),
      saved_at: "2026-08-29T00:00:00+00:00", side_effects: ["created_exam_paper_version"],
    } as PaperSavedVersion;
    const fetchMock = vi.fn(async () => new Response(JSON.stringify(saved), {
      status: 201,
      headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);

    await new HttpTeacherWorkspace().savePaperVersion(
      blueprint,
      ["pqq-1"],
      ["public-1"],
      [{ question_id: "pqq-1", position: 1, section_id: "single", score: 10 }],
      "c".repeat(64),
    );

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    const body = JSON.parse(String(init.body));
    expect(url).toBe("/api/v1/exam-papers/blueprints/save-version");
    expect(body.expected_draft_fingerprint).toBe("c".repeat(64));
    expect(body.draft_command.selection_request.selected_public_question_ids).toEqual(["public-1"]);
    expect(body.draft_command.selection_request.selected_private_question_ids).toEqual(["pqq-1"]);
    expect(body).not.toHaveProperty("owner_id");
    expect(body).not.toHaveProperty("version");
    expect(JSON.stringify(body)).not.toMatch(/verification_status|review_status|visibility|export_ready/i);
  });

  it("downloads only a named immutable paper version", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => new Response(new Blob(["paper"]), {
      status: 200,
      headers: {
        "Content-Type": "application/pdf",
        "Content-Disposition": "attachment; filename=exam-paper-v2-answer.pdf",
      },
    }));
    vi.stubGlobal("fetch", fetchMock);

    const artifact = await new HttpTeacherWorkspace().exportPaperVersion("paper/unsafe", 2, "pdf", "answer");

    expect(String(fetchMock.mock.calls[0]?.[0])).toBe("/api/v1/exam-papers/paper%2Funsafe/versions/2/export?format=pdf&edition=answer");
    expect(artifact.filename).toBe("exam-paper-v2-answer.pdf");
    expect(await artifact.blob.text()).toBe("paper");
  });

  it("downloads only an exact immutable lesson version without an owner selector", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => new Response(new Blob(["lesson"]), {
      status: 200,
      headers: {
        "Content-Type": "application/pdf",
        "Content-Disposition": "attachment; filename=lesson-plan-v3.pdf",
      },
    }));
    vi.stubGlobal("fetch", fetchMock);

    const artifact = await new HttpTeacherWorkspace().exportLessonVersion("lesson/unsafe", 3, "pdf");

    expect(String(fetchMock.mock.calls[0]?.[0])).toBe(
      "/api/v1/lesson-plans/versions/lesson%2Funsafe/export?version=3&format=pdf",
    );
    expect(String(fetchMock.mock.calls[0]?.[0])).not.toContain("owner");
    expect(artifact.filename).toBe("lesson-plan-v3.pdf");
    expect(await artifact.blob.text()).toBe("lesson");
  });

  it("lists and manages only server-scoped paper history without sending an owner", async () => {
    const history = {
      items: [{
        exam_paper_id: "paper-1", title: "函数测验", status: "draft", version: 1,
        duration_minutes: 45, total_score: 100, question_count: 8,
        updated_at: "2026-08-29T00:00:00+00:00", lifecycle_state: "active", trashed_at: null,
      }],
      total: 1,
    };
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === "POST") {
        return new Response(JSON.stringify({ ...history.items[0], lifecycle_state: "trashed", trashed_at: history.items[0].updated_at }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(JSON.stringify(history), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    const workspace = new HttpTeacherWorkspace();

    await expect(workspace.listPaperHistory("active")).resolves.toEqual(history);
    await workspace.changePaperHistoryLifecycle("paper/unsafe", "trash");

    expect(String(fetchMock.mock.calls[0]?.[0])).toBe("/api/v1/exam-papers?lifecycle_state=active&limit=50");
    expect(String(fetchMock.mock.calls[1]?.[0])).toBe("/api/v1/exam-papers/paper%2Funsafe/lifecycle");
    const lifecycleBody = JSON.parse(String((fetchMock.mock.calls[1]?.[1] as RequestInit).body));
    expect(lifecycleBody).toEqual({ action: "trash" });
    expect(JSON.stringify(lifecycleBody)).not.toMatch(/owner|teacher/i);
  });

  it("opens an owned saved paper and submits only editable revision facts", async () => {
    const paper = {
      exam_paper_id: "paper-1", status: "draft", version: 1, title: "函数测验",
      duration_minutes: 45, instructions: "写出过程", total_score: 10,
      items: [], updated_at: "2026-08-29T00:00:00+00:00", lifecycle_state: "active",
    };
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => new Response(JSON.stringify(paper), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);
    const workspace = new HttpTeacherWorkspace();
    const revision = {
      expected_version: 1,
      title: "函数测验（修订）",
      duration_minutes: 50,
      instructions: "写出过程",
      items: [{ question_id: "q1", section_id: "fill", section_title: "填空题", score: 10 }],
    };

    await workspace.getPaperHistoryPaper("paper/unsafe");
    await workspace.revisePaperHistoryPaper("paper/unsafe", revision);

    expect(String(fetchMock.mock.calls[0]?.[0])).toBe("/api/v1/exam-papers/paper%2Funsafe");
    expect(String(fetchMock.mock.calls[1]?.[0])).toBe("/api/v1/exam-papers/paper%2Funsafe/history-revision");
    expect(JSON.parse(String((fetchMock.mock.calls[1]?.[1] as RequestInit).body))).toEqual(revision);
    expect(JSON.stringify(revision)).not.toMatch(/owner|teacher/i);
  });

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
    expect(progress).toEqual(["正在准备识别", "正在识别", "识别完成"]);
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
    await workspace.preparePrivateLibraryQuestionCandidates("lib_1", {
      externalProcessingConsent: true,
    });
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
    expect(JSON.parse(String((calls[1]?.[1] as RequestInit).body))).toEqual({
      external_processing_consent: true,
    });
    expect(JSON.parse(String((calls[2]?.[1] as RequestInit).body))).toEqual(draft);
    expect(JSON.parse(String((calls[4]?.[1] as RequestInit).body))).toEqual({ node_id: "kp_function" });
    expect(String((calls[2]?.[1] as RequestInit).body)).not.toContain("owner_id");
    expect(String((calls[4]?.[1] as RequestInit).body)).not.toContain("volume");
  });

  it("creates only an unsaved owner-only authoring draft without browser-controlled policy fields", async () => {
    const draft = generatedQuestionDraftFixture();
    const result = {
      request_id: "req_authoring_1",
      session_id: "teacher_session_1",
      run_id: "run_authoring_1",
      status: "ok" as const,
      draft,
      tool_request_id: "req_tool_authoring_1",
      tool_call_count: 1,
      error: null,
    };
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => new Response(JSON.stringify(result), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);

    const workspace = new HttpTeacherWorkspace();
    await expect(workspace.createQuestionAuthoringDraft({
      requestText: "命一道高二椭圆离心率单选题，中等难度。",
      grade: "高二",
      knowledgePointQuery: "椭圆离心率",
      questionType: "single_choice",
      targetDifficulty: 3,
      teachingPurpose: "课堂练习",
      expectedMinutes: 5,
      assessedMethod: "离心率定义",
      misconceptionRequirements: "区分焦距与半焦距",
      additionalConstraints: "四个选项",
      sessionId: "teacher_session_1",
    })).resolves.toEqual(result);

    const [url, init] = fetchMock.mock.calls[0] ?? [];
    const body = JSON.parse(String((init as RequestInit).body));
    expect(url).toBe("/api/v1/agent/question-authoring/draft");
    expect(body).toEqual({
      brief: {
        request_text: "命一道高二椭圆离心率单选题，中等难度。",
        grade: "高二",
        knowledge_point_query: "椭圆离心率",
        question_type: "single_choice",
        target_difficulty: 3,
        teaching_purpose: "课堂练习",
        expected_minutes: 5,
        assessed_method: "离心率定义",
        misconception_requirements: "区分焦距与半焦距",
        additional_constraints: "四个选项",
      },
      session_id: "teacher_session_1",
      progress_id: expect.stringMatching(/^qap_[A-Za-z0-9_-]{20,}$/),
    });
    expect(JSON.stringify(body)).not.toMatch(/owner_id|visibility|public_search|share_allowed|verification|saved/);
    expect(result.draft.saved).toBe(false);
    expect(result.draft.visibility).toBe("owner_only");
  });

  it("starts resumable background authoring and exposes owner history controls", async () => {
    const staged = personalAuthoringDraftFixture();
    const job = {
      job_id: "job_authoring_1", kind: "question_authoring", subject_id: "qap_1",
      status: "running", current: 1, total: 0, message: "正在命制并闭环审核", error: "",
      result: {}, created_at: "2026-08-27T10:00:00Z", updated_at: "2026-08-27T10:00:01Z",
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const payload = url.endsWith("/cancel") ? { ...job, status: "cancelled", message: "任务已取消" }
        : url.endsWith("/jobs") ? job
        : url.includes("authoring-drafts?") ? { items: [staged], total: 1, limit: 100, offset: 0 }
          : { draft_id: staged.draft_id, deleted: true, saved_question_preserved: false };
      return new Response(JSON.stringify(payload), {
        status: url.endsWith("/jobs") ? 202 : 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    const workspace = new HttpTeacherWorkspace();
    await workspace.startQuestionAuthoringJob({
      requestText: "命一道高三导数填空题", questionType: "fill_blank",
      targetDifficulty: 5, teachingPurpose: "考试压轴", sessionId: "session_1",
    });
    await workspace.cancelQuestionAuthoringJob(job.job_id, true);
    await workspace.listPersonalAuthoringDrafts();
    await workspace.deletePersonalAuthoringHistory(staged.draft_id);

    expect(fetchMock.mock.calls.map(([url]) => String(url))).toEqual([
      "/api/v1/agent/question-authoring/jobs",
      "/api/v1/agent/question-authoring/jobs/job_authoring_1/cancel",
      "/api/v1/personal-question-library/authoring-drafts?limit=100&offset=0",
      "/api/v1/personal-question-library/authoring-drafts/qad_1/history",
    ]);
    expect((fetchMock.mock.calls[1]?.[1] as RequestInit).method).toBe("POST");
    expect(JSON.parse(String((fetchMock.mock.calls[1]?.[1] as RequestInit).body))).toEqual({
      preserve_statement: true,
    });
    expect((fetchMock.mock.calls[3]?.[1] as RequestInit).method).toBe("DELETE");
    expect(String((fetchMock.mock.calls[0]?.[1] as RequestInit).body)).not.toContain("owner_id");
  });

  it("keeps explicit save, versioned lifecycle actions and permanent deletion owner-bound", async () => {
    const staged = personalAuthoringDraftFixture();
    const question = personalQuestionFixture();
    const trashed = {
      ...question,
      lifecycle_state: "trashed" as const,
      trashed_at: "2026-08-24T10:10:00+08:00",
      updated_at: "2026-08-24T10:10:00+08:00",
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const payload = url.endsWith(`/authoring-drafts/${staged.draft_id}`)
        ? staged
        : url.endsWith(`/authoring-drafts/${staged.draft_id}/save`)
          ? question
          : init?.method === "DELETE"
            ? { question_id: question.question_id, active_storage_deleted: true, deleted_at: "2026-08-24T10:11:00+08:00" }
            : trashed;
      return new Response(JSON.stringify(payload), {
        status: url.endsWith("/save") ? 201 : 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    const workspace = new HttpTeacherWorkspace();
    await workspace.getPersonalAuthoringDraft(staged.draft_id);
    await workspace.savePersonalAuthoringDraft(staged.draft_id, {
      expectedRevision: staged.current_revision,
      collectionId: "pc_1",
      categoryId: "cat_1",
      name: "椭圆离心率课堂题",
    });
    const movedToTrash = await workspace.trashPersonalQuestion(question);
    await workspace.permanentlyDeletePersonalQuestion(movedToTrash, "永久删除我的私题");

    expect(fetchMock.mock.calls.map(([url]) => String(url))).toEqual([
      "/api/v1/personal-question-library/authoring-drafts/qad_1",
      "/api/v1/personal-question-library/authoring-drafts/qad_1/save",
      "/api/v1/personal-question-library/questions/pq_1/trash",
      "/api/v1/personal-question-library/questions/pq_1",
    ]);
    expect(JSON.parse(String((fetchMock.mock.calls[1]?.[1] as RequestInit).body))).toEqual({
      expected_revision: 1,
      collection_id: "pc_1",
      category_id: "cat_1",
      name: "椭圆离心率课堂题",
    });
    expect(JSON.parse(String((fetchMock.mock.calls[2]?.[1] as RequestInit).body))).toEqual({
      expected_updated_at: question.updated_at,
    });
    expect(JSON.parse(String((fetchMock.mock.calls[3]?.[1] as RequestInit).body))).toEqual({
      expected_updated_at: trashed.updated_at,
      confirmation: "永久删除我的私题",
    });
    expect(fetchMock.mock.calls.map(([, init]) => String((init as RequestInit | undefined)?.body ?? "")).join(""))
      .not.toContain("owner_id");
  });

  it("regenerates only the current authoring solution through the revision-bound endpoint", async () => {
    const staged = personalAuthoringDraftFixture();
    const regenerated = {
      ...staged,
      current_revision: 2,
      current: {
        ...staged.current,
        revision_number: 2,
        revision_source: "ai_generated" as const,
        edit_summary: "AI 重新生成解析；题面和选项保持不变，标准答案按新解析重新推导",
        draft: {
          ...staged.current.draft,
          solution_method: "重新规划的解法",
          solution_steps: ["重新生成后的成稿解析。"],
        },
      },
    };
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => new Response(JSON.stringify(regenerated), {
      status: 201,
      headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);

    const workspace = new HttpTeacherWorkspace();
    await expect(workspace.regeneratePersonalAuthoringSolution(staged.draft_id, 1))
      .resolves.toEqual(regenerated);

    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/api/v1/personal-question-library/authoring-drafts/qad_1/regenerate-solution");
    expect((init as RequestInit).method).toBe("POST");
    expect(JSON.parse(String((init as RequestInit).body))).toEqual({ expected_revision: 1 });
    expect(String((init as RequestInit).body)).not.toMatch(/owner_id|stem|answer|solution/);
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

  it("reads and updates the owner-scoped teacher memory profile", async () => {
    const profile = {
      version: 1,
      auto_learning_enabled: false,
      preferences: [{
        key: "default_grade",
        label: "默认年级",
        value: "高二",
        source: { kind: "teacher_explicit", label: "教师明确设置", confidence: 1 },
        updated_at: "2026-08-31T00:00:00Z",
      }],
      privacy_note: "仅保存结构化教学偏好。",
    } as const;
    const fetchMock = vi.fn((_input: RequestInfo | URL, _init?: RequestInit) => Promise.resolve(new Response(JSON.stringify(profile), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    })));
    vi.stubGlobal("fetch", fetchMock);

    const workspace = new HttpTeacherWorkspace();
    await expect(workspace.getTeacherMemoryProfile()).resolves.toEqual(profile);
    await expect(workspace.updateTeacherMemoryProfile({
      operation: "upsert",
      key: "default_grade",
      value: "高二",
      expected_version: 0,
    })).resolves.toEqual(profile);

    expect(String(fetchMock.mock.calls[0]?.[0])).toBe("/api/v1/teacher-memory/profile");
    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({ method: "GET" });
    const update = fetchMock.mock.calls[1]?.[1] as RequestInit;
    expect(update.method).toBe("POST");
    expect(JSON.parse(String(update.body))).toEqual({
      operation: "upsert",
      key: "default_grade",
      value: "高二",
      expected_version: 0,
    });
    expect(String(update.body)).not.toContain("owner");
    expect(String(update.body)).not.toContain("confidence");
  });
});
