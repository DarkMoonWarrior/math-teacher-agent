import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import type { QuestionInputBundle } from "@/lib/teacher-workspace/contracts";
import { QuestionMediaComposer } from "./question-media-composer";

function confirmedBundle(requiresVisualReasoning: boolean): QuestionInputBundle {
  return {
    asset: {
      asset_id: "qcap_test",
      original_filename: "题目.png",
      source: "upload",
      source_sha256: "synthetic-sha256",
      current_revision: 1,
      width: 1200,
      height: 800,
      size_bytes: 1024,
      mime_type: "image/png",
      clarity_status: "clear",
      warnings: [],
      revisions: [
        {
          revision: 1,
          source_revision: null,
          operation: "original",
          width: 1200,
          height: 800,
          mime_type: "image/png",
          content_endpoint: "/api/v1/question-media/qcap_test/revisions/1/content",
          created_at: "2026-08-24T00:00:00Z",
        },
      ],
      visibility: "private",
      public_search_allowed: false,
      model_training_allowed: false,
      created_at: "2026-08-24T00:00:00Z",
      updated_at: "2026-08-24T00:00:00Z",
    },
    recognition_status: "confirmed",
    recognition_revision: 1,
    recognition_source_revision: 1,
    recognition_mode: "external",
    recognition_provider: "deepseek",
    recognition_model: "deepseek-v4-flash-vision-exp",
    stem_plain: "测试题面",
    stem_latex: "测试题面",
    options: [],
    requires_visual_reasoning: requiresVisualReasoning,
    visual_observations: [],
    low_confidence_regions: [],
    recognition_warnings: [],
    external_processing_consent: true,
    teacher_review_note: "",
    visibility: "private",
  };
}

function renderComposer(bundle: QuestionInputBundle) {
  return renderToStaticMarkup(
    <QuestionMediaComposer
      bundle={bundle}
      visualProcessingConsent={false}
      onChange={vi.fn()}
      onConfirmed={vi.fn()}
      onVisualProcessingConsentChange={vi.fn()}
    />,
  );
}

describe("QuestionMediaComposer", () => {
  it("omits passive post-confirmation copy when the confirmed text is sufficient", () => {
    const html = renderComposer(confirmedBundle(false));

    expect(html).not.toContain("确认题面足够，本次不发送原图");
    expect(html).not.toContain("Solve 只消费教师确认的文字与公式 revision");
    expect(html).not.toContain("图片与识别 revision 始终属于你的私人工作区");
  });

  it("keeps the actionable one-use visual consent when the problem needs its image", () => {
    const html = renderComposer(confirmedBundle(true));

    expect(html).toContain("本题依赖或可能依赖图形");
    expect(html).toContain("我同意本次解题使用 REV 1 原图；仅本次有效");
  });
});
