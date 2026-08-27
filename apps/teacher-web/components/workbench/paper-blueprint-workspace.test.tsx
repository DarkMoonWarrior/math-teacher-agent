import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { PaperBlueprintWorkspace } from "./paper-blueprint-workspace";


describe("PaperBlueprintWorkspace", () => {
  it("states the first-slice boundaries before any blueprint request", () => {
    const html = renderToStaticMarkup(
      <PaperBlueprintWorkspace
        initialBrief="组一份高二期中卷"
        onBriefChange={vi.fn()}
        onOpenAuthoring={vi.fn()}
      />,
    );

    expect(html).toContain("Paper Agent · 蓝图规划已接入");
    expect(html).toContain("不会查题、生成题目、保存试卷或改变任何私题权限");
    expect(html).toContain("当前没有题目，也没有产生任何保存或权限变更");
    expect(html).toContain("辅助命题是独立私有工作流，不会自动保存或加入当前蓝图");
    expect(html).not.toContain("确认蓝图并选题（下一切片）");
  });
});
