import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import {
  clampSplitPercent,
  collapsedSplitPercent,
  ResizableSplitPane,
  splitPercentForKey,
} from "./resizable-split-pane";

describe("ResizableSplitPane", () => {
  it("snaps a pointer dragged to the left edge into a collapsed primary pane", () => {
    expect(collapsedSplitPercent(7, 30, 65)).toBe(0);
    expect(collapsedSplitPercent(18, 30, 65)).toBe(30);
    expect(collapsedSplitPercent(47, 30, 65)).toBe(47);
    expect(collapsedSplitPercent(82, 30, 65)).toBe(65);
    expect(clampSplitPercent(18, 30, 65)).toBe(30);
    expect(clampSplitPercent(47, 30, 65)).toBe(47);
    expect(clampSplitPercent(82, 30, 65)).toBe(65);
  });

  it("supports precise and accelerated keyboard resizing", () => {
    expect(splitPercentForKey(40, "ArrowLeft", false, 30, 65)).toBe(38);
    expect(splitPercentForKey(40, "ArrowRight", true, 30, 65)).toBe(50);
    expect(splitPercentForKey(40, "Home", false, 30, 65)).toBe(0);
    expect(splitPercentForKey(30, "ArrowLeft", false, 30, 65)).toBe(0);
    expect(splitPercentForKey(0, "ArrowRight", false, 30, 65)).toBe(30);
    expect(splitPercentForKey(40, "End", false, 30, 65)).toBe(65);
    expect(splitPercentForKey(40, "Enter", false, 30, 65)).toBeNull();
  });

  it("renders an accessible vertical separator between exactly two panes", () => {
    const html = renderToStaticMarkup(
      <ResizableSplitPane ariaLabel="调整测试区域宽度">
        <section>左侧</section>
        <section>右侧</section>
      </ResizableSplitPane>,
    );

    expect(html).toContain('role="separator"');
    expect(html).toContain('aria-orientation="vertical"');
    expect(html).toContain('aria-valuemin="0"');
    expect(html).toContain('aria-valuenow="40"');
    expect(html).toContain("左侧区域宽度 40%");
    expect(html).toContain('data-pane="primary"');
    expect(html).toContain('data-pane="secondary"');
  });
});
