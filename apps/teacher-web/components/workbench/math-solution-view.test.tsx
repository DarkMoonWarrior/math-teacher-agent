import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { MathSolutionView } from "./math-solution-view";


describe("MathSolutionView", () => {
  it("renders question, long solution steps and final answer through the shared math renderer", () => {
    const html = renderToStaticMarkup(
      <MathSolutionView
        finalAnswer={String.raw`$x=\frac{\sqrt{3}}{2}$`}
        method="解析几何法"
        question={String.raw`已知 $x^2+y^2=1$，求 $x$。`}
        steps={[
          String.raw`由题设得到 $$x^2=\frac{3}{4}$$。`,
          String.raw`结合 $x>0$，所以 $x=\frac{\sqrt{3}}{2}$。`,
        ]}
      />,
    );

    expect(html).toContain("结构化解析");
    expect(html).toContain("最终答案");
    expect(html).toContain("01");
    expect(html).toContain("02");
    expect(html.match(/class=\"katex/g)?.length).toBeGreaterThanOrEqual(4);
    expect(html).not.toContain("math-fallback");
  });

  it("renders choice options as a complete ordered block outside the stem", () => {
    const html = renderToStaticMarkup(
      <MathSolutionView
        finalAnswer="C"
        method="递推法"
        options={[
          { key: "A", text: String.raw`$c_n=\frac{1}{2}$` },
          { key: "B", text: String.raw`$c_n=\frac{2}{3}$` },
          { key: "C", text: "不是等比数列" },
          { key: "D", text: "恒为 1" },
        ]}
        question="某游戏满足下列规则，判断数列的性质。"
        steps={["建立递推关系并核验各选项。"]}
      />,
    );

    expect(html).toContain('class="question-options"');
    expect(html).toContain('class="question-option-key">A</span>');
    expect(html).toContain('class="question-option-key">D</span>');
    expect(html.indexOf("某游戏满足下列规则")).toBeLessThan(html.indexOf("question-options"));
    expect(html.match(/class="question-options__item"/g)).toHaveLength(4);
  });
});
