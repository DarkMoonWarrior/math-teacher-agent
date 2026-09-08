# M6 Private Library Agent · Gate E 审计

> 状态同步（2026-09-09）：M0–M12 已完成；M13 工程切片已完成但真实验证延期、Gate 未通过；项目所有者已授权进入 M14，当前进行中。本文的切片过程、测试数量和 Gate 结论保留为当时证据；后续行为与当前边界见 [开发状态](PROJECT-STATUS.md) 和 [开发边界](DEVELOPMENT-BOUNDARY.md)。

审计日期：2026-08-22

审计分支：`codex/teacher-workbench-v1`

审计起点：`c822f5769bfb7d0effa5cc1e564fb02c09ae465b`

## 结论

**M6 Gate E 已严格通过，M6 完成。M7 尚未启动，必须等待项目所有者在本结论之后明确确认阶段转换。**

本结论只覆盖 M6 的本地产品与工程边界。当前固定教师身份不是生产认证，不能据此声称商业多租户、云端隔离或真实教师质量 Gate 已完成。

## Gate 核对

| 维度 | 结论 | 证据摘要 |
| --- | --- | --- |
| 功能 | 通过 | 新工作台形成上传、处理/OCR、校对与 revision、拆题、教材映射、私有导入、逐次授权私人检索的完整流程。 |
| 可信 | 通过 | 空结果、格式/OCR/模型/Tool 失败和取消均有独立语义；取消不再归为普通错误；未确认内容不会成为检索证据。 |
| 隐私与权利 | 通过 | owner 由服务端 seam 绑定；跨 owner、未确认、回收站与许可重放均 fail closed；派生内容始终 private，无 public/shared/commercial-approved 出口。 |
| Agent 权限 | 通过 | Agent 仅调用 allowlisted FastAPI Tool；静态审计未发现数据库、ORM、文件系统或任意 URL 直连。 |
| UI | 通过 | 320/375/768/1440/1920px 无横向溢出；关键导航有可访问名称；未授权阻断、空结果、自动定位、许可自动清除和零控制台告警通过。 |
| 工程 | 通过 | FastAPI、Agent、Teacher Web 和 legacy 回归全部通过；无新依赖、迁移或破坏性操作。 |
| 仓库卫生 | 通过 | 未追踪 `.env`、API Key、运行数据库、上传文件或真实私人资料；commercial-approved 保持空边界。 |
| 后续边界 | 通过 | M7/M8 仅有边界文档，无功能代码；Lesson/Paper 继续明确标记为运行时待接入。 |

## 固定评测

12 个项目自建 synthetic 场景覆盖空库、格式/OCR 失败、模型不可用、Tool 超时、取消、许可重放、跨 owner、未确认/回收站过滤、有界返回、失败后新许可恢复和派生题私有状态；8 类违规均为 0。完整记录见 [`M6-PRIVATE-LIBRARY-EVALUATION.md`](M6-PRIVATE-LIBRARY-EVALUATION.md)。

## Gate E 工程检查

- FastAPI：`291 passed`，另有 1 条 Starlette TestClient 依赖弃用提示。
- Agent Runtime：类型检查、`39 passed`、生产构建通过。
- Teacher Web：类型检查、`28 passed`、生产构建通过。
- Legacy Web：类型检查与生产构建通过。
- 静态边界：未新增依赖；Agent 源码无数据库/ORM/文件系统直连；Private Library 唯一 public 能力字段仍固定为 `public_search_allowed=false`。
- 仓库：tracked files 与本次新增文件的审计未发现 `.env`、运行数据库或 DeepSeek/OpenAI 形式的 API Key；本次没有迁移、永久删除或 destructive operation。

## 浏览器验收

- 320、375、768、1440、1920px 均无关键横向溢出。
- 320px 导航的图标式“新任务”按钮具有独立 `aria-label`；资料库表单保留可访问名称。
- 不勾选本次授权时显示“请先确认本次检索授权”，不会执行 Agent 检索。
- 授权查询完成后勾选自动清空，页面自动定位结果；当前仅有待 OCR 资料时，真实返回“没有找到已由你确认的匹配资料”，不生成假内容。
- 控制台 `error` / `warn` 均为 0；教案和组卷仍标记“运行时待接入”。

## 范围核对

### 已完成

- M6 六条纵向切片及完整 Gate E。
- 聚合、上传/列表、OCR/校对/revision、拆题/映射/私有导入、逐次授权有界检索、固定评测。

### 部分完成

- 无 M6 范围内部分完成项。

### 未完成

- 无 M6 范围内未完成项。

### 明确未启动或超出范围

- M7 多模态题目采集与图片解题。
- M8 私有辅助命题 Agent。
- M9-M11 Paper、Lesson、Memory Agent。
- 生产认证、多租户、云端隔离、Beta、支付与商业发布。

## 阶段转换

M6 已形成可回滚终态，但本次“继续开发”发生在 Gate E 结论之前，不自动视为对 M7 的阶段确认。只有项目所有者在看到本审计结果后明确确认，才可进入 M7。
