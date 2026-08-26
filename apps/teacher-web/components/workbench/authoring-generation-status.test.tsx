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
    expect(html).toContain("生成解析");
    expect(html).not.toContain("长题会先锁定完整题面与选项");
  });

  it("formats long waits without resetting the minute count", () => {
    expect(formatAuthoringElapsed(605)).toBe("10:05");
  });
});
