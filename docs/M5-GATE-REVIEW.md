# M5 Solve Agent Gate 审计

> 状态同步（2026-09-04）：M0–M11 已完成并完成阶段转换，当前为 M12 切片 1–4。本文的切片过程、测试数量和 Gate 结论保留为当时证据；后续行为与当前边界见 [开发状态](PROJECT-STATUS.md) 和 [开发边界](DEVELOPMENT-BOUNDARY.md)。

- 审计日期：2026-08-21
- 审计分支：`codex/teacher-workbench-v1`
- 本轮起始基线：`3d50633dd06a576ee0075efa6bbfa8917de43a83`

## 当前结论

**M5 Gate E 已严格通过。M6 尚未启动，等待项目所有者确认阶段转换。**

可信解题链路、题库解析优先、修订与验证证据、模型生成降级、错误/取消/恢复、Search 转入、三页结果展示、固定 synthetic evaluation、320—1920px 响应式和完整工程回归均已通过。

## M5 完成 Gate 对照

| Gate 项 | 状态 | 审计证据 |
| --- | --- | --- |
| 已验证题优先与追踪 | 通过 | 精确匹配返回 `verified_bank`、题目 ID、修订计数、独立答案、验证明细和 verifier 版本。 |
| 新题/新解法可信等级 | 通过 | 所有 provider 新生成结果保持 `teacher_review_required`；自动测试禁止提升为 `program_verified`。 |
| MathVerifier 分级 | 通过 | `supported/unsupported` 与 `passed/failed/inconclusive` 独立表达；模型文字不能覆盖业务评估。 |
| 教师端完整流程 | 通过 | 支持完整题目输入、Search 一键转入、运行进度、取消、错误、重试、可信标签和三页结果。 |
| 失败体验 | 通过 | 模型不可用、Tool 超时、权限拒绝、无已验证解析、验证失败/不确定均有结构化错误或明确降级标注。 |
| Agent 权限边界 | 通过 | 仅使用 allowlisted 只读 Tool；没有数据库、文件、保存、发布或批准能力。 |
| 响应式与可访问性 | 通过 | 320/375/414/768/1440/1920px 无关键横向溢出；原生键盘控件、焦点反馈和 reduced-motion 分支保留。 |
| 工程验证 | 通过 | FastAPI、Agent、Teacher Web 与 Legacy Web 的测试、类型检查和生产构建全部通过。 |
| Gate E 与后续边界 | 通过 | 固定 synthetic evaluation 六类违规均为 0；Lesson/Paper 仍明确为预览，未启动 M6。 |

## 固定评测

[`M5-SOLVE-EVALUATION.md`](M5-SOLVE-EVALUATION.md) 记录 9 个项目自建合成场景。固定运行结果为：

```text
cases=9
unexpected_outcome=0
generated_promoted=0
verification_overstated=0
evidence_mismatch=0
modified_inherited=0
trace_missing=0
```

## Gate E 工程检查

| 检查面 | 结果 |
| --- | --- |
| FastAPI | 269 项测试通过；1 条 Starlette TestClient 依赖弃用提示，不影响结果。 |
| Agent Runtime | 类型检查、36 项测试、生产构建通过。 |
| Teacher Web | 类型检查、19 项测试、生产构建通过；同源 Search/Solve Route 均生成。 |
| Legacy Web | 类型检查、生产构建通过，旧业务地基未被破坏。 |
| 浏览器验收 | 320—1920px 关键宽度通过；1920px 实测 `scrollWidth=1905`、无横向溢出；真实本地链路已覆盖已验证成功和模型不可用失败。 |
| Agent 权限边界 | 六个 allowlisted 只读工具；M2M 缺失/错误 fail closed；未发现 Agent 直连数据库。 |
| 可信与发布边界 | 未绕过 RightsGate/MathVerifier；未增加自动保存、发布或批准；Lesson/Paper 仍为预览。 |
| 仓库卫生 | 商业题库仅保留说明文件；未发现 API Key、运行数据库、真实私人资料或未审核商业内容进入 Git。 |
| 依赖与迁移 | 本批没有新增依赖、数据库迁移或破坏性操作。 |

## 范围核对

### 已完成

- `solve_question` 受控 Tool 与 `SolutionAssistant` 深模块复用。
- 产品自有 Solve workflow、同步/SSE、取消、终态快照与同 session 恢复。
- 题库已验证解析优先、新解答待教师复核、分级 MathVerifier 证据和 revision 追踪。
- 新工作台文字输入、Search 转入、运行反馈、错误/重试、自动定位和三页结果。
- 固定 synthetic evaluation、关键响应式和完整 Gate E 回归。

### 部分完成

- 无 M5 范围内部分完成事项。

### 未完成

- 无 M5 范围内未完成事项。

### 超范围修改

- 无。Private Library、Paper、Lesson、Memory 及 M6-M15 均未启动。

## 阶段转换

M5 已形成可回滚终态，但不能自动进入 M6。下一步必须由项目所有者确认后，才把当前里程碑切换为 M6 Private Library Agent。
