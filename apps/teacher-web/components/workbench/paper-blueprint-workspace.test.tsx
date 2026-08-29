import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { PaperBlueprintSelectionDraft, PaperEditableDraft, PaperSavedVersion } from "@/lib/teacher-workspace/contracts";
import { PaperBlueprintWorkspace, PaperEditableDraftView, PaperHistoryEditor, PaperHistoryPanel, PaperPublicQuestionPicker, PaperSelectionDraftView } from "./paper-blueprint-workspace";


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
    expect(html).toContain("试卷尚未完善，确认保存吗");
    expect(html).toContain("确认保存");
    expect(html).toContain("取消");
    expect(html).toContain("历史组卷");
    expect(html).toContain("仅当前用户可见");
    expect(html).not.toContain("确认蓝图并选题（下一切片）");
  });

  it("renders owner-private paper history with export, recycle and restore controls", () => {
    const item = {
      exam_paper_id: "paper-1",
      title: "函数与导数阶段测验",
      status: "draft",
      version: 1,
      duration_minutes: 60,
      total_score: 100,
      question_count: 8,
      updated_at: "2026-08-29T08:00:00+08:00",
      lifecycle_state: "active" as const,
      trashed_at: null,
    };
    const activeHtml = renderToStaticMarkup(
      <PaperHistoryPanel busyKey="" items={[item]} lifecycle="active" loading={false} onExport={vi.fn()} onLifecycleChange={vi.fn()} onOpen={vi.fn()} onSelectLifecycle={vi.fn()} />,
    );
    const trashHtml = renderToStaticMarkup(
      <PaperHistoryPanel busyKey="" items={[{ ...item, lifecycle_state: "trashed", trashed_at: item.updated_at }]} lifecycle="trashed" loading={false} onExport={vi.fn()} onLifecycleChange={vi.fn()} onOpen={vi.fn()} onSelectLifecycle={vi.fn()} />,
    );

    expect(activeHtml).toContain("函数与导数阶段测验");
    expect(activeHtml).toContain("学生卷");
    expect(activeHtml).toContain("答案卷");
    expect(activeHtml).toContain("细目表");
    expect(activeHtml).toContain("删除");
    expect(activeHtml).toContain("编辑");
    expect(trashHtml).toContain("恢复");
  });

  it("opens a saved paper as an editable new-version draft", () => {
    const html = renderToStaticMarkup(
      <PaperHistoryEditor
        busy={false}
        onClose={vi.fn()}
        onSave={vi.fn()}
        paper={{
          exam_paper_id: "paper-1",
          status: "draft",
          version: 2,
          title: "函数测验",
          duration_minutes: 45,
          instructions: "写出必要过程",
          total_score: 10,
          updated_at: "2026-08-29T08:00:00+08:00",
          lifecycle_state: "active",
          items: [{
            item_id: "item-1",
            position: 1,
            section_id: "fill",
            section_title: "填空题",
            score: 10,
            question: { question_id: "q1", question_type: "fill_blank", stem_plain: "已知 $f(x)=x^2$，则 $f'(1)=$____。", stem_latex: null, options: [], difficulty: 2 },
          }],
        }}
      />,
    );

    expect(html).toContain("历史组卷 · 版本 2");
    expect(html).toContain("编辑后另存新版本");
    expect(html).toContain("另存新版本");
    expect(html).not.toContain("旧版本会保留");
    expect(html).toContain("添加题目");
    expect(html).toContain("试卷总分");
    expect(html).toContain("所属分区");
  });

  it("renders a searchable, explicitly selectable public question catalog", () => {
    const html = renderToStaticMarkup(
      <PaperPublicQuestionPicker
        candidates={[{
          question_id: "public-1",
          question_type: "single_choice",
          stem_plain: "函数 $f(x)=x^2$ 的最小值是（ ）",
          options: [{ key: "A", text: "$0$" }],
          difficulty: 2,
          chapter: "函数",
          knowledge_points: ["函数"],
          source_document: "公共题库",
        }]}
        loading={false}
        onQueryChange={vi.fn()}
        onSearch={vi.fn()}
        onToggle={vi.fn()}
        query="函数"
        selectedIds={["public-1"]}
        total={1}
      />,
    );

    expect(html).toContain("从公共题库中明确选择（可选）");
    expect(html).toContain("搜索公共题库");
    expect(html).toContain("仅展示已通过公开可见性、权利、数学验证、教师审核和在架门禁的题目");
    expect(html).toContain('checked=""');
  });

  it("renders a concise shortage summary and readable questions without internal metadata", () => {
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
        difficulty: 2,
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
      coverage_audit: {
        status: "needs_adjustment",
        coverage_complete: false,
        difficulty_status: "insufficient_supply",
        target_average_difficulty: 3,
        actual_average_difficulty: 2,
        average_difficulty_gap: 1,
        sections: [{
          section_id: "choice",
          section_title: "单项选择题",
          target_question_count: 2,
          actual_question_count: 1,
          target_score: 20,
          actual_score: 10,
          status: "short",
        }],
        knowledge_points: [
          { knowledge_point: "函数", actual_question_count: 1, actual_score: 10, status: "covered" },
          { knowledge_point: "导数", actual_question_count: 0, actual_score: 0, status: "missing" },
        ],
        difficulty_bands: [
          { difficulty: 1, target_question_count: 0, actual_question_count: 0, actual_score: 0 },
          { difficulty: 2, target_question_count: 1, actual_question_count: 1, actual_score: 10 },
          { difficulty: 3, target_question_count: 1, actual_question_count: 0, actual_score: 0 },
          { difficulty: 4, target_question_count: 0, actual_question_count: 0, actual_score: 0 },
          { difficulty: 5, target_question_count: 0, actual_question_count: 0, actual_score: 0 },
        ],
        side_effects: [],
      },
      similarity_exclusions: [],
      unselected_public_question_ids: [],
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

    expect(html).toContain("题目不足");
    expect(html).toContain("我的私题");
    expect(html).toContain("缺 1 题 · 10 分");
    expect(html).toContain("选题结果分析");
    expect(html).toContain("这些分析不限制教师选题");
    expect(html).toContain("导数");
    expect(html).toContain("未覆盖");
    expect(html).toContain("题目不足，暂不能完整判断");
    expect(html).toContain("A");
    expect(html).not.toContain("CONTROLLED SELECTION");
    expect(html).not.toContain("通过门禁的现成题不足");
    expect(html).not.toContain("仅当前教师");
    expect(html).not.toContain("验证：");
    expect(html).not.toContain("审核：");
    expect(html).not.toContain(">保存试卷<");
    expect(html).not.toContain(">导出试卷<");
  });

  it("renders paper editing controls, traceable changes, and both specification directions", () => {
    const item = {
      section_id: "choice",
      section_title: "单项选择题",
      position: 1,
      question_id: "q-1",
      source_kind: "public_question_bank" as const,
      question_type: "single_choice",
      stem_plain: "函数 $f(x)=x^2$ 的最小值是（ ）",
      options: [{ key: "A", text: "$0$" }, { key: "B", text: "$1$" }],
      score: 10,
      difficulty: 3,
      chapter: "函数",
      knowledge_points: ["函数"],
      source_document: "公共题库",
      source_page_start: 1,
      source_page_end: 1,
      license_status: "public_permissive",
      revision_count: 1,
      verification_status: "passed",
      review_status: "approved",
      visibility: "public",
      owner_scope: "public_catalog" as const,
      source_preserved: true as const,
      copied: false as const,
      selection_reason: "受控选题",
    };
    const draft = {
      status: "editable_paper_draft",
      editable: true,
      saved: false,
      version_created: false,
      export_ready: false,
      draft_fingerprint: "a".repeat(64),
      selection_complete: true,
      draft_consistent: true,
      score_status: "matched",
      blueprint: {
        title: "函数测验",
        grade_scope: "高二",
        teaching_usage: "专题测验",
        duration_minutes: 30,
        target_score: 10,
        difficulty_profile: "balanced",
        knowledge_points: ["函数"],
        sections: [{ section_id: "choice", title: "单项选择题", question_type: "single_choice", question_count: 1, target_score: 10 }],
      },
      target_question_count: 1,
      actual_question_count: 1,
      target_score: 10,
      actual_score: 10,
      items: [item],
      gaps: [],
      coverage_audit: {
        status: "matched",
        coverage_complete: true,
        difficulty_status: "matched",
        target_average_difficulty: 3,
        actual_average_difficulty: 3,
        average_difficulty_gap: 0,
        sections: [{ section_id: "choice", section_title: "单项选择题", target_question_count: 1, actual_question_count: 1, target_score: 10, actual_score: 10, status: "met" }],
        knowledge_points: [{ knowledge_point: "函数", actual_question_count: 1, actual_score: 10, status: "covered" }],
        difficulty_bands: [1, 2, 3, 4, 5].map((difficulty) => ({ difficulty, target_question_count: difficulty === 3 ? 1 : 0, actual_question_count: difficulty === 3 ? 1 : 0, actual_score: difficulty === 3 ? 10 : 0 })),
        side_effects: [],
      },
      change_log: [{ question_id: "q-1", kind: "score", before: "8", after: "10", description: "题目分值由 8 分调整为 10 分" }],
      specification: {
        question_to_dimensions: [{ position: 1, question_id: "q-1", section_title: "单项选择题", question_type: "single_choice", chapter: "函数", knowledge_points: ["函数"], difficulty: 3, score: 10, verification_status: "passed", review_status: "approved", source_kind: "public_question_bank" }],
        dimension_to_questions: [{ dimension: "knowledge_point", label: "函数", positions: [1], question_ids: ["q-1"], question_count: 1, score: 10 }],
      },
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
    } satisfies PaperEditableDraft;

    const html = renderToStaticMarkup(<PaperEditableDraftView applying={false} draft={draft} exporting="" onApply={vi.fn()} onExport={vi.fn()} onSave={vi.fn()} savedVersion={null} saving={false} />);

    expect(html).toContain("可编辑试卷与双向细目表");
    expect(html).toContain("上移");
    expect(html).toContain("下移");
    expect(html).toContain("所属分区");
    expect(html).toContain("题目到教学维度");
    expect(html).toContain("教学维度到题目");
    expect(html).toContain("题目分值由 8 分调整为 10 分");
    expect(html).toContain("确认无误后，明确保存为不可变版本");
    expect(html).toContain("保存为正式版本");
    expect(html).toContain("保存与导出");
    expect(html).toContain("保存后可导出学生卷、答案卷和双向细目表");
    expect(html.indexOf("保存为正式版本")).toBeLessThan(html.indexOf("所属分区"));

    const coverageAdjustmentDraft = {
      ...draft,
      draft_consistent: true,
      coverage_audit: {
        ...draft.coverage_audit,
        status: "needs_adjustment" as const,
        coverage_complete: false,
        difficulty_status: "deviated" as const,
        actual_average_difficulty: 5,
        average_difficulty_gap: 2,
        knowledge_points: [
          ...draft.coverage_audit.knowledge_points,
          { knowledge_point: "导数", actual_question_count: 0, actual_score: 0, status: "missing" as const },
        ],
      },
    } satisfies PaperEditableDraft;
    const adjustmentHtml = renderToStaticMarkup(<PaperEditableDraftView applying={false} draft={coverageAdjustmentDraft} exporting="" onApply={vi.fn()} onExport={vi.fn()} onSave={vi.fn()} savedVersion={null} saving={false} />);
    expect(adjustmentHtml).toContain("题量、分区与总分已满足");
    expect(adjustmentHtml).toContain("系统已根据所选题目完成分析");
    expect(adjustmentHtml).toContain("实际知识范围：函数");
    expect(adjustmentHtml).toContain("实际难度均值：5");
    expect(adjustmentHtml).not.toContain("知识与难度分析不会阻止保存");
    expect(adjustmentHtml).toMatch(/class="is-save"[^>]*>保存为正式版本/);
    expect(adjustmentHtml).not.toMatch(/class="is-save"[^>]*disabled/);
    expect(adjustmentHtml).toContain("保存与导出");

    const incompleteDraft = {
      ...draft,
      selection_complete: false,
      draft_consistent: false,
      target_question_count: 2,
      actual_question_count: 1,
      blueprint: {
        ...draft.blueprint,
        sections: [{ ...draft.blueprint.sections[0], question_count: 2 }],
      },
      coverage_audit: {
        ...draft.coverage_audit,
        status: "needs_adjustment" as const,
        coverage_complete: false,
        sections: [{ ...draft.coverage_audit.sections[0], target_question_count: 2, status: "short" as const }],
      },
    } satisfies PaperEditableDraft;
    const incompleteHtml = renderToStaticMarkup(<PaperEditableDraftView applying={false} draft={incompleteDraft} exporting="" onApply={vi.fn()} onExport={vi.fn()} onSave={vi.fn()} savedVersion={null} saving={false} />);
    expect(incompleteHtml).toContain("题量仍有真实缺口");
    expect(incompleteHtml).toContain("仍可由教师确认保存");
    expect(incompleteHtml).toMatch(/class="is-save"[^>]*>保存为正式版本/);
    expect(incompleteHtml).not.toMatch(/class="is-save"[^>]*disabled/);

    const savedVersion = {
      status: "saved_paper_version", saved: true, version_created: true, export_ready: true,
      exam_paper_id: "paper-1", version: 1, title: "函数测验", question_count: 1,
      total_score: 10, draft_fingerprint: draft.draft_fingerprint,
      specification: draft.specification,
      available_exports: [
        ["student", "docx", "学生卷 · DOCX"], ["student", "pdf", "学生卷 · PDF"],
        ["answer", "docx", "答案卷 · DOCX"], ["answer", "pdf", "答案卷 · PDF"],
        ["blueprint", "docx", "双向细目表 · DOCX"], ["blueprint", "pdf", "双向细目表 · PDF"],
      ].map(([edition, format, label]) => ({ edition, format, label })),
      saved_at: "2026-08-29T00:00:00+00:00", side_effects: ["created_exam_paper_version"],
    } as PaperSavedVersion;
    const savedHtml = renderToStaticMarkup(<PaperEditableDraftView applying={false} draft={draft} exporting="" onApply={vi.fn()} onExport={vi.fn()} onSave={vi.fn()} savedVersion={savedVersion} saving={false} />);
    expect(savedHtml).toContain("不可变版本");
    expect(savedHtml).toContain("版本 1");
    expect(savedHtml).toContain("学生卷 · DOCX");
    expect(savedHtml).toContain("双向细目表 · PDF");
    expect(savedHtml.indexOf("学生卷 · DOCX")).toBeLessThan(savedHtml.indexOf("所属分区"));
  });
});
