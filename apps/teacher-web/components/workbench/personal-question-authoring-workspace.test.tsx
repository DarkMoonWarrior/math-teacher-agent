import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import {
  PersonalQuestionAuthoringWorkspace,
  revealAuthoringResult,
} from "./personal-question-authoring-workspace";

describe("PersonalQuestionAuthoringWorkspace", () => {
  it("keeps the full authoring controls and result surface inside the shared split workbench", () => {
    const html = renderToStaticMarkup(
      <PersonalQuestionAuthoringWorkspace initialBrief="命一道高二函数题" />,
    );

    expect(html).toContain('aria-label="调整命题要求与题目结果区域宽度"');
    expect(html).toContain('role="separator"');
    expect(html).toContain("authoring-control-pane");
    expect(html).toContain("authoring-result-pane");
    expect(html).toContain("命一道自己的题");
    expect(html).toContain("命题书桌");
    expect(html).toContain("告诉我要出一道什么题");
    expect(html).toContain("题目与解析会在这里展开");
    expect(html).toContain("请在左侧填写命题要求并生成私有草稿");
  });

  it("reveals the result surface after a generation request is accepted", () => {
    const calls: ScrollIntoViewOptions[] = [];
    const scheduled: FrameRequestCallback[] = [];

    revealAuthoringResult(
      { scrollIntoView: (options) => calls.push(options as ScrollIntoViewOptions) },
      (callback) => {
        scheduled.push(callback);
        return 1;
      },
    );

    expect(calls).toEqual([]);
    expect(scheduled).toHaveLength(1);
    scheduled[0]?.(0);
    expect(calls).toEqual([{ behavior: "smooth", block: "start", inline: "nearest" }]);
  });
});
