import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { PersonalQuestionAuthoringWorkspace } from "./personal-question-authoring-workspace";

describe("PersonalQuestionAuthoringWorkspace", () => {
  it("pairs the authoring brief with a resizable result pane before generation", () => {
    const html = renderToStaticMarkup(
      <PersonalQuestionAuthoringWorkspace initialBrief="命一道高二函数题" />,
    );

    expect(html).toContain('aria-label="调整命题要求与题目结果区域宽度"');
    expect(html).toContain('role="separator"');
    expect(html).toContain("告诉我要出一道什么题");
    expect(html).toContain("题目与解析会在这里展开");
    expect(html).toContain("请在左侧填写命题要求并生成私有草稿");
  });
});
