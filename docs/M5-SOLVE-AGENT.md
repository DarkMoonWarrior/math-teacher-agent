# M5 Solve Agent 实施边界与 Gate

更新日期：2026-08-21

## 产品结果

教师可以输入一道完整高中数学文字题，或从 Search 结果继续解题，并得到结构化、可核对的解析。界面必须把“已有题库已验证解析”和“模型新生成待教师复核”清楚分开。

M5 不处理图片/PDF 导入、题目变式、保存/发布解析、组卷、教案或教师记忆。

## 深模块与 seam

`SolutionAssistant.solve(SolutionRequest) -> SolutionResult` 是业务深模块接口。题库匹配、可信分层、provider 选择和错误语义隐藏在模块实现内；FastAPI 公共路由与 `solve_question` Tool 都复用这个接口。

Harness 不直接调用模型解题 provider，也不接触题库或 MathVerifier 存储。唯一链路是：

`Teacher Web → same-origin route → FastAPI Solve workflow → TeacherAgentRuntime → solve_question Tool → FastAPI SolutionAssistant → QuestionBank / provider / MathVerifier`

M5 第一条 vertical slice 先完成 `solve_question` Tool seam。Tool 接通不等于 M5 完成。

## 可信等级

| 状态 | 含义 | UI 要求 |
| --- | --- | --- |
| `program_verified` | 精确匹配题库题，已有独立数学验证证据 | 展示题目 ID、匹配度和验证证据。 |
| `model_reviewed` | 只代表模型复核，不代表 MathVerifier 通过 | 必须与程序验证视觉区分。 |
| `teacher_review_required` | 模型新生成、验证不支持或证据不足 | 明确提示教师复核，不得使用“已验证”措辞。 |

任何格式校验、第二模型一致或 Agent 自评都不能升级为 `program_verified`。

## 实施顺序

1. 受控 `solve_question` Tool：M2M、超时、结构化错误、可信状态原样透传。
2. Solve workflow：题库解析优先、Runtime 编排、取消/恢复和失败分类。
3. MathVerifier 分级：supported/pass/fail/inconclusive 证据进入结果，不能被模型覆盖。
4. 新 Teacher Web 解题导航、文字输入、Search 结果转入、结构化结果和可信提示。
5. synthetic eval、关键浏览器矩阵和完整 Gate E。

## 完成 Gate

- 已验证题库解析优先且证据可追踪。
- 模型新解答全部保持 `teacher_review_required`。
- 无模型、Tool 超时、权限拒绝、取消、验证失败/inconclusive 均诚实失败或降级标注。
- Agent 无数据库、文件、发布、批准或写工具。
- 新工作台解题流程和 320-1920px 关键响应式通过。
- FastAPI、Agent、Teacher Web 与 legacy 回归按 Gate E 通过。
- 完成/部分/未完成/超范围修改形成 M5 Gate 审计。
