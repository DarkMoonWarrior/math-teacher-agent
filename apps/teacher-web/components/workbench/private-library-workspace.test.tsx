import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import {
  privateLibraryRecognitionPreview,
  PrivateLibraryQuestionPreview,
  PrivateLibraryWorkspace,
} from "./private-library-workspace";

describe("PrivateLibraryQuestionPreview", () => {
  it("renders extracted questions as readable math instead of raw model data", () => {
    const html = renderToStaticMarkup(
      <PrivateLibraryQuestionPreview
        draft={{
          question_type: "single_choice",
          stem_plain: "已知函数 f(x)=x²，求 f(2)。",
          stem_latex: "已知函数 $f(x)=x^2$，求 $f(2)$。",
          options: [
            { key: "A", text: "$2$" },
            { key: "B", text: "$4$" },
          ],
          answer_value: "$4$",
          solution_method: "代入计算",
          solution_steps: ["代入 $x=2$，得到 $f(2)=4$。"],
          final_answer: "$4$",
          difficulty: 2,
        }}
      />,
    );

    expect(html).toContain("题面预览");
    expect(html).toContain("已知函数");
    expect(html).toContain("katex");
    expect(html).toContain("解析");
    expect(html).not.toContain("stem_latex");
    expect(html).not.toContain("question_type");
  });
});

describe("PrivateLibraryWorkspace streamlined import and recognition", () => {
  it("removes rights and one-use gates while keeping an optional source note", () => {
    const html = renderToStaticMarkup(<PrivateLibraryWorkspace />);
    const source = readFileSync(new URL("./private-library-workspace.tsx", import.meta.url), "utf8");

    expect(html).toContain("来源说明");
    expect(html).not.toContain("权利依据");
    expect(html).not.toContain("我确认上述来源说明真实");
    expect(source).not.toContain("本地数学 OCR");
    expect(source).not.toContain("DeepSeek");
    expect(source).not.toContain("仅本次");
    expect(source).not.toContain("查看首次提取文本");
    expect(source).toContain("大模型整理稿");
    expect(source).toContain("可编辑的中文 + LaTeX 校对稿");
  });

  it("adds an independent draggable divider between the source and readable draft", () => {
    const source = readFileSync(new URL("./private-library-workspace.tsx", import.meta.url), "utf8");

    expect(source).toContain('ariaLabel="调整原稿与大模型整理稿宽度"');
    expect(source).toContain('className="library-review-comparison-split"');
  });

  it("never presents the stale placeholder 无 as a successful recognition result", () => {
    expect(privateLibraryRecognitionPreview("无", false, "")).toEqual({
      kind: "empty",
      text: "尚未生成大模型整理稿。",
    });
    expect(privateLibraryRecognitionPreview("无", false, "大模型服务未配置")).toEqual({
      kind: "error",
      text: "识别失败：大模型服务未配置",
    });
    expect(privateLibraryRecognitionPreview("函数 $f(x)=x^2$", false, "")).toEqual({
      kind: "content",
      text: "函数 $f(x)=x^2$",
    });
  });
});
