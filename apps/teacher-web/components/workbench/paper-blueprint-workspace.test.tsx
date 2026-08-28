import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { PaperBlueprintSelectionDraft } from "@/lib/teacher-workspace/contracts";
import { PaperBlueprintWorkspace, PaperSelectionDraftView } from "./paper-blueprint-workspace";


describe("PaperBlueprintWorkspace", () => {
  it("states the planning and controlled-selection boundaries before any blueprint request", () => {
    const html = renderToStaticMarkup(
      <PaperBlueprintWorkspace
        initialBrief="组一份高二期中卷"
        onBriefChange={vi.fn()}
        onOpenAuthoring={vi.fn()}
      />,
    );

    expect(html).toContain("Paper Agent · 蓝图规划与受控选题已接入");
    expect(html).toContain("经你确认后，只从通过门禁的公共题和你明确选择的私题中建立候选清单");
    expect(html).toContain("当前没有题目，也没有产生任何保存或权限变更");
    expect(html).toContain("辅助命题是独立私有工作流，不会自动加入当前蓝图");
    expect(html).toContain('aria-label="调整组卷要求与蓝图区域宽度"');
    expect(html).toContain('role="separator"');
    expect(html).not.toContain("确认蓝图并选题（下一切片）");
  });

  it("renders source facts, options, and honest gaps without offering persistence", () => {
    const selection = {
      status: "selection_draft",
      blueprint_confirmed: true,
      editable: true,
      saved: false,
      selection_complete: false,
      blueprint: {
        title: "高二函数测验",
        grade_scope: "高二",
        teaching_usage: "课堂练习",
        duration_minutes: 45,
        target_score: 20,
        difficulty_profile: "balanced",
        knowledge_points: ["函数"],
        sections: [{ section_id: "choice", title: "单项选择题", question_type: "single_choice", question_count: 2, target_score: 20 }],
      },
      target_question_count: 2,
      actual_question_count: 1,
      target_score: 20,
      actual_score: 10,
      items: [{
        section_id: "choice",
        section_title: "单项选择题",
        position: 1,
        question_id: "private-1",
        source_kind: "personal_question_library",
        question_type: "single_choice",
        stem_plain: "函数 $f(x)=x^2$ 的最小值是（ ）",
        options: [{ key: "A", text: "$0$" }, { key: "B", text: "$1$" }],
        score: 10,
        difficulty: 0.55,
        chapter: "函数",
        knowledge_points: ["函数"],
        source_document: "我的私题",
        source_page_start: null,
        source_page_end: null,
        license_status: "owner_created",
        revision_count: 2,
        verification_status: "passed",
        review_status: "verified",
        visibility: "private",
        owner_scope: "current_owner_only",
        source_preserved: true,
        copied: false,
        selection_reason: "教师明确选择",
      }],
      gaps: [{
        section_id: "choice",
        section_title: "单项选择题",
        question_type: "single_choice",
        required_count: 2,
        selected_count: 1,
        missing_count: 1,
        missing_score: 10,
        reason: "通过门禁的现成题不足",
        suggestions: ["调整知识范围"],
      }],
      similarity_exclusions: [],
      unselected_private_question_ids: [],
      warnings: [],
      trust_policy: {
        verification_policy: "passed_only",
        review_policy: "approved_only",
        private_question_policy: "explicit_owner_selection_only",
        auto_authoring_allowed: false,
        preserves_source_and_rights: true,
      },
      auto_authoring_used: false,
      side_effects: [],
    } satisfies PaperBlueprintSelectionDraft;

    const html = renderToStaticMarkup(<PaperSelectionDraftView selection={selection} />);

    expect(html).toContain("候选题存在真实缺口");
    expect(html).toContain("我的私题");
    expect(html).toContain("仅当前教师");
    expect(html).toContain("通过门禁的现成题不足");
    expect(html).toContain("A");
    expect(html).not.toContain("保存试卷");
    expect(html).not.toContain("导出试卷");
  });
});
