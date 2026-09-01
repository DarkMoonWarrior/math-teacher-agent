import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { BetaAccessScreen } from "./beta-access-gate";

describe("BetaAccessScreen", () => {
  it("asks only for an access code and explains that it is not retained", () => {
    const html = renderToStaticMarkup(
      <BetaAccessScreen
        busy={false}
        error=""
        accessCode=""
        onAccessCodeChange={() => undefined}
        onSubmit={() => undefined}
      />,
    );

    expect(html).toContain("进入教师封闭测试");
    expect(html).toContain("访问码不会保存在浏览器中");
    expect(html).toContain('type="password"');
    expect(html).not.toContain("teacher_id");
  });

  it("shows a generic denial without exposing roster or participant details", () => {
    const html = renderToStaticMarkup(
      <BetaAccessScreen
        busy={false}
        error="访问码无效或已不可用。"
        accessCode="wrong"
        onAccessCodeChange={() => undefined}
        onSubmit={() => undefined}
      />,
    );

    expect(html).toContain("访问码无效或已不可用");
    expect(html).not.toContain("名单");
  });
});
