import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { AuthoringGenerationStatus, formatAuthoringElapsed } from "./authoring-generation-status";

describe("AuthoringGenerationStatus", () => {
  it("shows the actual stage, an activity indicator and elapsed time", () => {
    const html = renderToStaticMarkup(
      <AuthoringGenerationStatus elapsedSeconds={68} stage="reviewing" />,
    );

    expect(html).toContain("Agent 正在审核题面是否合理");
    expect(html).toContain("已处理 01:08");
    expect(html).toContain('class="authoring-progress__spinner"');
    expect(html).toContain('aria-live="polite"');
    expect(html).toContain("命制题面");
    expect(html).toContain("审核题面");
    expect(html).toContain("完善题面（按需）");
    expect(html).toContain("生成解析");
    expect(html).not.toContain("长题会先锁定完整题面与选项");
  });

  it("explains the conditional statement-repair stage", () => {
    const html = renderToStaticMarkup(
      <AuthoringGenerationStatus elapsedSeconds={95} stage="refining" />,
    );

    expect(html).toContain("审核发现问题，Agent 正在完善题面并重新审核");
    expect(html).toContain("已处理 01:35");
  });

  it("formats long waits without resetting the minute count", () => {
    expect(formatAuthoringElapsed(605)).toBe("10:05");
  });
});
