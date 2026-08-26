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
});
