import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  normalizeProposalCorrection,
  TeacherMemoryFeedbackHistory,
  TeacherMemoryLifecycle,
  TeacherMemoryProposals,
} from "./teacher-memory-panel";

describe("TeacherMemoryProposals", () => {
  it("shows explainable evidence without presenting a proposal as a saved preference", () => {
    const html = renderToStaticMarkup(
      <TeacherMemoryProposals
        disabled={false}
        items={[{
        proposal_id: "proposal_lesson_minutes",
        key: "default_lesson_minutes",
        label: "默认课时",
        value: 45,
        status: "pending_teacher_review",
        confidence: 0.79,
        evidence: {
          category: "confirmed_lesson_version",
          label: "已确认并保存的教案版本",
          occurrence_count: 3,
        },
        created_at: "2026-09-01T00:00:00Z",
        updated_at: "2026-09-01T00:00:00Z",
        }]}
        onAccept={() => undefined}
        onCorrect={() => undefined}
        onReject={() => undefined}
      />,
    );

    expect(html).toContain("偏好提议");
    expect(html).toContain("45 分钟");
    expect(html).toContain("已确认并保存的教案版本 · 3 次 · 置信度 79%");
    expect(html).toContain("尚未写入偏好，也不会用于任务默认值");
    expect(html).toContain("采用建议");
    expect(html).toContain("不采用");
    expect(html).toContain("修正后采用");
  });

  it("normalizes correction values according to the proposal key", () => {
    expect(normalizeProposalCorrection("default_lesson_minutes", "50")).toBe(50);
    expect(normalizeProposalCorrection("default_difficulty", "4")).toBe(4);
    expect(normalizeProposalCorrection("default_grade", "高三")).toBe("高三");
  });

  it("renders an inspectable structured feedback history without evidence ids", () => {
    const html = renderToStaticMarkup(
      <TeacherMemoryFeedbackHistory items={[{
        feedback_id: "feedback_1",
        proposal_id: "proposal_1",
        key: "default_difficulty",
        label: "默认难度",
        proposed_value: 4,
        resolved_value: null,
        action: "reject",
        confidence: 0.79,
        evidence: {
          category: "confirmed_paper_version",
          label: "已确认并保存的试卷版本",
          occurrence_count: 3,
        },
        created_at: "2026-09-01T00:00:00Z",
      }]} />,
    );

    expect(html).toContain("反馈记录");
    expect(html).toContain("不采用");
    expect(html).toContain("默认难度");
    expect(html).not.toContain("evidence_id");
  });

  it("requires the fixed confirmation before enabling full memory deletion", () => {
    const incomplete = renderToStaticMarkup(
      <TeacherMemoryLifecycle
        confirmation="删除"
        disabled={false}
        onConfirmationChange={() => undefined}
        onDelete={() => undefined}
        onExport={() => undefined}
        retentionNote="保留至教师删除。"
      />,
    );
    const complete = renderToStaticMarkup(
      <TeacherMemoryLifecycle
        confirmation="删除全部教师记忆"
        disabled={false}
        onConfirmationChange={() => undefined}
        onDelete={() => undefined}
        onExport={() => undefined}
        retentionNote="保留至教师删除。"
      />,
    );

    expect(incomplete).toContain("导出 JSON");
    expect(incomplete).toContain("删除全部教师记忆");
    expect(incomplete).toMatch(/button[^>]*disabled=""[^>]*>永久删除全部记忆/);
    expect(complete).not.toMatch(/button[^>]*disabled=""[^>]*>永久删除全部记忆/);
  });
});
