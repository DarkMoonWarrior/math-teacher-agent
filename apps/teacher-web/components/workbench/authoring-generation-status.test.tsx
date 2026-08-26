import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { AuthoringGenerationStatus, formatAuthoringElapsed } from "./authoring-generation-status";

describe("AuthoringGenerationStatus", () => {
  it("shows the actual stage, an activity indicator and elapsed time", () => {
    const html = renderToStaticMarkup(
      <AuthoringGenerationStatus elapsedSeconds={68} stage="agent" />,
    );

    expect(html).toContain("Agent 正在命制完整题面与解析");
    expect(html).toContain("已处理 01:08");
    expect(html).toContain('class="authoring-progress__spinner"');
    expect(html).toContain('aria-live="polite"');
  });

  it("formats long waits without resetting the minute count", () => {
    expect(formatAuthoringElapsed(605)).toBe("10:05");
  });
});
