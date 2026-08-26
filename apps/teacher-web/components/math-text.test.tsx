import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { MathText, parseMathText } from "./math-text";

describe("MathText", () => {
  it("parses explicit inline and display math without losing prose", () => {
    expect(parseMathText(String.raw`由 $x=2$ 得到 $$\sum_{n=1}^{\infty}\frac{1}{n^2}=\frac{\pi^2}{6}$$。`)).toEqual([
      { kind: "text", value: "由 " },
      { kind: "inline-math", value: "x=2" },
      { kind: "text", value: " 得到 " },
      {
        kind: "display-math",
        value: String.raw`\sum_{n=1}^{\infty}\frac{1}{n^2}=\frac{\pi^2}{6}`,
      },
      { kind: "text", value: "。" },
    ]);
  });

  it("recognizes legacy undelimited LaTeX embedded in Chinese solution text", () => {
    const parts = parseMathText(
      String.raw`计算傅里叶系数：a_0=(1/\pi)\int_{-\pi}^{\pi}x^2 dx；因此结果为 \pi^2/6。`,
    );

    expect(parts.some((part) => part.kind === "text" && part.value.includes("计算傅里叶系数"))).toBe(true);
    expect(parts.some((part) => part.kind !== "text" && part.value.includes(String.raw`\int`))).toBe(true);
    expect(parts.some((part) => part.kind !== "text" && part.value.includes(String.raw`\pi^2/6`))).toBe(true);
  });

  it("renders math through KaTeX instead of exposing it as visible source text", () => {
    const html = renderToStaticMarkup(
      <MathText text={String.raw`$$\sum_{n=1}^{\infty}\frac{1}{n^2}=\frac{\pi^2}{6}$$`} />,
    );

    expect(html).toContain("katex-display");
    expect(html).toContain("math-display");
  });
});
