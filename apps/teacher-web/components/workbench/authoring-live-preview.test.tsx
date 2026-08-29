import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { AuthoringLivePreview } from "./authoring-live-preview";

const statement = {
  question_type: "single_choice" as const,
  stem_plain: "已知函数 f(x)=x²，则 f(2)=（ ）。",
  stem_latex: "已知函数 $f(x)=x^2$，则 $f(2)=$（ ）。",
  options: [
    { key: "A", text: "2" },
    { key: "B", text: "4" },
  ],
  estimated_difficulty: 1,
};

describe("AuthoringLivePreview", () => {
  it("shows an approved statement immediately while the solution continues", () => {
    const html = renderToStaticMarkup(
      <AuthoringLivePreview
        mode="active"
        revision={2}
        stage="solving"
        statement={statement}
        statementState="approved"
      />,
    );

    expect(html).toContain("题面已通过审核 · 解析生成中");
    expect(html).toContain("题面 REV 2");
    expect(html).toContain("f(2)");
    expect(html).toContain("Agent 正在后台生成解析");
  });

  it("marks the displayed statement as adjusting until a reviewed replacement arrives", () => {
    const html = renderToStaticMarkup(
      <AuthoringLivePreview
        mode="active"
        revision={1}
        stage="refining"
        statement={statement}
        statementState="adjusting"
      />,
    );

    expect(html).toContain("题面正在调整");
    expect(html).toContain("新题面重新审核通过后会自动替换当前版本");
  });

  it("clearly labels a stopped statement as having no answer or solution", () => {
    const html = renderToStaticMarkup(
      <AuthoringLivePreview
        mode="preserved"
        onDiscard={() => undefined}
        revision={1}
        stage="solving"
        statement={statement}
        statementState="approved"
      />,
    );

    expect(html).toContain("已停止生成解析 · 题面已保留");
    expect(html).toContain("没有标准答案和解析");
    expect(html).toContain("不再保留题面");
  });
});
