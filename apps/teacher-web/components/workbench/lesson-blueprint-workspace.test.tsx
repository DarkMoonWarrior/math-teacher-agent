import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { LessonBlueprintDraft, LessonEditableDraft, LessonSourceDraft, LessonSourceOptions } from "@/lib/teacher-workspace/contracts";
import { LessonBlueprintDraftView, LessonBlueprintWorkspace, LessonEditableDraftView } from "./lesson-blueprint-workspace";

function lessonBlueprintFixture(): LessonBlueprintDraft {
  return {
    status: "lesson_blueprint_draft",
    editable: true,
    confirmed: false,
    saved: false,
    source_brief: "为高二椭圆第一课时准备一份 45 分钟新授课教案",
    title: "高二椭圆新授课教案",
    grade_scope: "高二",
    lesson_type: "new_lesson",
    lesson_format: "新授课",
    duration_minutes: 45,
    student_profile: "基础中等，抽象概括能力需要支架",
    focus: "建立椭圆定义与几何表示的联系",
    question_count: 3,
    curriculum_query: "椭圆",
    selected_curriculum_node_id: "kp-ellipse",
    curriculum_candidates: [{
      node_id: "kp-ellipse",
      node_type: "knowledge_point",
      name: "椭圆的定义与标准方程",
      volume: "选择性必修第一册",
      chapter: "圆锥曲线的方程",
      section: "椭圆",
      description: "从轨迹定义建立椭圆标准方程。",
      competencies: ["数学抽象", "直观想象"],
      common_errors: ["忽略定义中的距离条件"],
      catalog_status: "sealed_baseline",
      reviewed_by: "curriculum_baseline_import",
      match_score: 0.96,
    }],
    objectives: ["理解椭圆的定义。", "能由定义推导标准方程。"],
    key_points: ["椭圆的定义与标准方程"],
    difficulties: ["从几何条件过渡到代数表示"],
    phases: [
      { phase_id: "diagnosis", title: "情境与诊断", minutes: 5, purpose: "唤起先备知识" },
      { phase_id: "question", title: "提出问题", minutes: 6, purpose: "形成核心问题" },
      { phase_id: "construction", title: "概念建构", minutes: 16, purpose: "经历推导过程" },
      { phase_id: "practice", title: "例题与练习", minutes: 13, purpose: "完成理解迁移" },
      { phase_id: "summary", title: "总结与作业", minutes: 5, purpose: "回扣目标" },
    ],
    required_blocks: ["objectives", "key_points", "difficulties", "teaching_flow", "homework", "board_plan", "teacher_notes"],
    assumptions: ["未明确例题与练习数量，暂按 3 道受控题目规划。"],
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
}

function lessonSourceOptionsFixture(): LessonSourceOptions {
  const draft = lessonBlueprintFixture();
  return {
    status: "lesson_source_options",
    blueprint: { ...draft, status: "lesson_blueprint_confirmed", confirmed: true },
    public_questions: [{
      question_id: "public-1", source_kind: "public_question_bank", name: "公开题库",
      question_type: "single_choice", stem_plain: "已知椭圆方程，求焦点坐标（ ）", options: [{ key: "A", text: "(3, 0)" }],
      difficulty: 3, chapter: "圆锥曲线", knowledge_points: ["椭圆"], source_document: "公开题库",
      source_revision: 2, rights_basis: "licensed_for_teaching", verification_status: "passed",
      review_status: "approved", owner_scope: "public_catalog",
    }],
    private_questions: [],
    private_resources: [],
    trust_statement: "公共题已通过全部门禁；私人来源仅限当前教师明确选择。",
    side_effects: [],
  };
}

function lessonSourceDraftFixture(): LessonSourceDraft {
  const options = lessonSourceOptionsFixture();
  return {
    status: "lesson_source_draft", editable: true, saved: false, selection_complete: true,
    blueprint: options.blueprint,
    curriculum: options.blueprint.curriculum_candidates[0],
    questions: options.public_questions,
    private_resources: [], gaps: [], warnings: [],
    trust_policy: { ai_content_status: "draft_requires_teacher_review" }, side_effects: [],
  };
}

function lessonEditableDraftFixture(): LessonEditableDraft {
  const sourceDraft = lessonSourceDraftFixture();
  return {
    status: "lesson_editable_draft", content_status: "draft_requires_teacher_review",
    editable: true, saved: false, draft_revision: 1, title: "高二椭圆新授课教案", source_draft: sourceDraft,
    objectives: [{ objective_id: "OBJ-01", text: "理解椭圆定义。", observable_evidence: "能准确复述并判断轨迹。" }],
    key_points: ["椭圆的定义"], difficulties: ["几何条件向代数表示转换"],
    teaching_flow: [{
      phase_id: "diagnosis", title: "情境与诊断", minutes: 45, purpose: "完成概念建构",
      teacher_activity: "组织定义辨析与方程推导。", student_activity: "独立思考后交流推导过程。",
      assessment: "依据课堂作答判断目标达成。", objective_ids: ["OBJ-01"],
      question_ids: ["public-1"], resource_ids: [],
    }],
    questions: [{
      question_id: "public-1", source_kind: "public_question_bank", source_revision: 2,
      rights_basis: "licensed_for_teaching", verification_status: "passed", review_status: "approved",
      owner_scope: "public_catalog", phase_id: "diagnosis", usage: "用于概念辨析。",
      stem_plain: "已知椭圆 $x^2/4+y^2=1$，求焦点坐标（ ）", options: [{ key: "A", text: "$(\\sqrt{3},0)$" }],
      answer_value: "A", solution_steps: ["由 $c^2=a^2-b^2$ 确定焦点位置。"], final_answer: "$(\\sqrt{3},0)$",
    }],
    assessments: [{ assessment_id: "ASM-01", title: "课堂检查", method: "口头说明依据。", success_criteria: "结论与依据均正确。", objective_ids: ["OBJ-01"] }],
    homework: ["完成椭圆定义辨析练习。"], board_plan: ["椭圆定义"], teacher_notes: ["课后记录真实学情。"],
    locked_blocks: [], rewrite_history: [],
    source_manifest: [{
      source_kind: "public_question", source_id: "public-1", source_revision: "2",
      rights_basis: "licensed_for_teaching", verification_status: "passed", owner_scope: "public_catalog",
    }],
    integrity: {
      required_blocks_complete: true, time_total_matches: true, objective_activity_alignment: true,
      objective_assessment_alignment: true, questions_complete: true, high_school_scope: true,
      source_traceability_complete: true,
    },
    generation: { provider: "deterministic_closed_loop" }, side_effects: [],
  };
}

describe("LessonBlueprintWorkspace", () => {
  it("states the blueprint-only boundary before any request", () => {
    const html = renderToStaticMarkup(
      <LessonBlueprintWorkspace
        initialBrief="为高二椭圆第一课时准备一份 45 分钟新授课教案"
        onBriefChange={vi.fn()}
      />,
    );

    expect(html).toContain("Lesson Agent · 私有版本与历史已接入");
    expect(html).toContain("不自动读取未选择的私有内容");
    expect(html).toContain("当前没有教案正文、题目或保存记录");
    expect(html).toContain('aria-label="调整教案要求与蓝图区域宽度"');
    expect(html).toContain('role="separator"');
    expect(html).toContain("我的教案历史");
    expect(html).not.toContain(">保存教案<");
  });

  it("renders an editable, auditable and explicitly unsaved lesson blueprint", () => {
    const html = renderToStaticMarkup(
      <LessonBlueprintDraftView draft={lessonBlueprintFixture()} onChange={vi.fn()} onConfirm={vi.fn()} />,
    );

    expect(html).toContain("LESSON BLUEPRINT · 未保存草案");
    expect(html).toContain("需要教师核对的默认假设");
    expect(html).toContain("教材节点");
    expect(html).toContain("选择性必修第一册 · 圆锥曲线的方程 · 椭圆的定义与标准方程");
    expect(html).not.toContain("基线状态");
    expect(html).not.toContain("匹配度");
    expect(html).toContain("目标与重难点");
    expect(html).toContain("45 / 45 分钟");
    expect(html).toContain("尚未选题、未读取私人资料、未生成教案正文，也没有写入数据库");
    expect(html).toContain("本地可编辑草案");
    expect(html).toContain("确认蓝图并选择来源");
    expect(html).not.toContain("已保存");
  });

  it("renders public, owner-only and private-resource choices only after confirmation", () => {
    const draft = lessonBlueprintFixture();
    const sourceOptions: LessonSourceOptions = {
      ...lessonSourceOptionsFixture(),
      private_questions: [{
        question_id: "private-1", source_kind: "personal_question_library", name: "我的椭圆变式",
        question_type: "open_response", stem_plain: "推导椭圆标准方程。", options: [], difficulty: 3,
        chapter: "圆锥曲线", knowledge_points: ["椭圆"], source_document: "个人题库",
        source_revision: 4, rights_basis: "owner_private_use_only",
        verification_status: "authoring_checks_passed_teacher_review_required", review_status: "owner_saved_complete",
        owner_scope: "current_owner_only",
      }],
      private_resources: [{
        library_item_id: "resource-1", title: "椭圆课堂札记", file_kind: "docx", source_version: 3,
        rights_basis: "original", text_review_status: "confirmed", corrected_char_count: 1200,
        owner_scope: "current_owner_only",
      }],
    };
    const html = renderToStaticMarkup(
      <LessonBlueprintDraftView draft={draft} onChange={vi.fn()} sourceOptions={sourceOptions} />,
    );

    expect(html).toContain("明确选择课堂来源");
    expect(html).toContain("受控公共题");
    expect(html).toContain("我的椭圆变式");
    expect(html).toContain("未勾选资料不会进入 Agent 上下文");
    expect(html).toContain("确认所选来源");
    expect(html).toContain("确认完整来源后可生成教案正文");
    expect(html).not.toContain("保存教案");
  });

  it("offers generation only after a complete source selection", () => {
    const html = renderToStaticMarkup(
      <LessonBlueprintDraftView
        draft={lessonBlueprintFixture()}
        onChange={vi.fn()}
        sourceDraft={lessonSourceDraftFixture()}
        sourceOptions={lessonSourceOptionsFixture()}
      />,
    );

    expect(html).toContain("受控来源已完整确认");
    expect(html).toContain("生成完整教案草稿");
  });

  it("renders a complete, traceable and explicitly unsaved lesson draft", () => {
    const html = renderToStaticMarkup(<LessonEditableDraftView draft={lessonEditableDraftFixture()} />);

    expect(html).toContain("待教师复核 · 未保存");
    expect(html).toContain("目标—活动对应");
    expect(html).toContain("题目与解析完整");
    expect(html).toContain("教学流程");
    expect(html).toContain("katex");
    expect(html).toContain("最终答案：");
    expect(html).not.toContain("精确来源清单");
    expect(html).not.toContain("public-1 · revision 2");
    expect(html).not.toContain("保存教案");
  });

  it("exposes block editing and locking without making source-backed question facts editable", () => {
    const draft = lessonEditableDraftFixture();
    draft.locked_blocks = ["homework"];
    const html = renderToStaticMarkup(
      <LessonEditableDraftView
        draft={draft}
        locallyEdited
        onChange={vi.fn()}
        onRewrite={vi.fn()}
        onToggleLock={vi.fn()}
      />,
    );

    expect(html).toContain("逐块编辑、锁定与定向重写");
    expect(html).toContain("服务器 REV 1 · 有本地未应用修改");
    expect(html).toContain("教学目标定向重写要求");
    expect(html).toContain("解锁");
    expect(html).toContain("锁定块不会被定向重写");
    expect(html).toContain("题干、选项、答案和解析保持来源原样");
    expect(html).toContain("katex");
    expect(html).not.toContain("保存教案");
  });
});
