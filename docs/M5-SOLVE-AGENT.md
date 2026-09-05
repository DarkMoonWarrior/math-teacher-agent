# M5 Solve Agent 实施边界与 Gate

> 状态同步（2026-09-05）：M0–M12 已完成，项目所有者已确认进入 M13，当前进行中。本文的切片过程、测试数量和 Gate 结论保留为当时证据；后续行为与当前边界见 [开发状态](PROJECT-STATUS.md) 和 [开发边界](DEVELOPMENT-BOUNDARY.md)。

更新日期：2026-08-21

## 产品结果

教师可以输入一道完整高中数学文字题，或从 Search 结果继续解题，并得到结构化、可核对的解析。界面必须把“已有题库已验证解析”和“模型新生成待教师复核”清楚分开。

M5 不处理图片/PDF 导入、题目变式、保存/发布解析、组卷、教案或教师记忆。

## 深模块与 seam

`SolutionAssistant.solve(SolutionRequest) -> SolutionResult` 是业务深模块接口。题库匹配、可信分层、provider 选择和错误语义隐藏在模块实现内；FastAPI 公共路由与 `solve_question` Tool 都复用这个接口。

Harness 不直接调用模型解题 provider，也不接触题库或 MathVerifier 存储。唯一链路是：

`Teacher Web → same-origin route → FastAPI Solve workflow → TeacherAgentRuntime → solve_question Tool → FastAPI SolutionAssistant → QuestionBank / provider / MathVerifier`

M5 第一条 vertical slice 完成 `solve_question` Tool seam。
第二条 vertical slice 将题库中已有的 MathVerifier/教师独立核验证据归一为显式分级。
第三条 vertical slice 已完成产品自有 Solve workflow、公开 FastAPI 生命周期和错误分类；只有唯一成功的 `solve_question` 结构化结果能成为最终解答，原始 Tool payload 与模型自由文本不进入浏览器。
第四条 vertical slice 已完成新 Teacher Web 接入：文字输入、Search 转入、同一 run 恢复、取消、结构化三页结果和 MathVerifier 证据页均已接通。第五条完成固定 synthetic evaluation、revision 追踪、320—1920px 验收和完整 Gate E；M5 已完成，后续阶段转换已确认。当前里程碑见 [项目状态](PROJECT-STATUS.md)。

## 可信等级

| 状态 | 含义 | UI 要求 |
| --- | --- | --- |
| `program_verified` | 精确匹配题库题，已有独立数学验证证据 | 展示题目 ID、匹配度和验证证据。 |
| `model_reviewed` | 只代表模型复核，不代表 MathVerifier 通过 | 必须与程序验证视觉区分。 |
| `teacher_review_required` | 模型新生成、验证不支持或证据不足 | 明确提示教师复核，不得使用“已验证”措辞。 |

任何格式校验、第二模型一致或 Agent 自评都不能升级为 `program_verified`。

每次成功结果还必须携带 `math_verification`：

- `status`：`passed | failed | inconclusive`；
- `capability`：`supported | unsupported`；
- `scope`：明确证据只覆盖题库题答案、匹配到的题库记录，还是模型生成的完整解答；
- `evidence_source`、方法、独立答案、来源答案、证据步骤和 verifier 版本。

题库中已有的答案矛盾不能被模型输出覆盖；任意模型新解答在现有 MathVerifier 无对应能力时必须保持 `unsupported/inconclusive`。

## 实施顺序

1. 受控 `solve_question` Tool：M2M、超时、结构化错误、可信状态原样透传。
2. Solve workflow：题库解析优先、Runtime 编排、取消/恢复和失败分类。（已完成）
3. MathVerifier 分级：supported/pass/fail/inconclusive 证据进入结果，不能被模型覆盖。（已完成现有证据分级与 Tool 透传；任意新题通用验证能力仍不虚构）
4. 新 Teacher Web 解题导航、文字输入、Search 结果转入、结构化结果和可信提示。（已完成）
5. synthetic eval 与完整 Gate E。（已完成；9 个固定场景六类可信违规为 0）

## 当前公开接口

全部接口受 `MATH_AI_SOLVE_AGENT_ENABLED` 独立开关保护，默认关闭：

- `POST /api/v1/agent/solve`：同步执行并保存终态；
- `POST /api/v1/agent/solve/stream`：单次真实执行的 SSE；
- `GET /api/v1/agent/solve/{run_id}`：读取进程内 run 记录；
- `GET /api/v1/agent/solve/{run_id}/stream`：读取已保存快照，不重复解题；
- `POST /api/v1/agent/solve/{run_id}/cancel`：取消同一在途 Runtime run；
- `POST /api/v1/agent/solve/{run_id}/resume`：仅恢复失败/取消且存在 session 的 run。

run 记录仍是当前开发阶段的进程内状态，不代表云端持久化、教师身份或多租户能力。

## 完成 Gate

- 已验证题库解析优先且证据可追踪。
- 模型新解答全部保持 `teacher_review_required`。
- 无模型、Tool 超时、权限拒绝、取消、验证失败/inconclusive 均诚实失败或降级标注。
- Agent 无数据库、文件、发布、批准或写工具。
- 新工作台解题流程和 320-1920px 关键响应式通过。
- FastAPI、Agent、Teacher Web 与 legacy 回归按 Gate E 通过。
- 完成/部分/未完成/超范围修改形成 M5 Gate 审计。

完整评测见 [`M5-SOLVE-EVALUATION.md`](M5-SOLVE-EVALUATION.md)，逐项 Gate 证据见 [`M5-GATE-REVIEW.md`](M5-GATE-REVIEW.md)。M6 在项目所有者确认前保持未启动。
