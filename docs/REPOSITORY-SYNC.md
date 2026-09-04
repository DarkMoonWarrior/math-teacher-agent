# 仓库同步与卫生记录

核对日期：2026-09-05；下列仓库清理表保留 2026-09-04 历史结果，后续基线另列。

## 范围

当前项目为 `math-teacher-agent`，本地目录 `D:/math-teacher-agent`，远端为 `DarkMoonWarrior/math-teacher-agent`。`D:/math ai agent` 对应独立前身项目 `high-school-math-ai`，本轮不修改或删除该独立仓库。

## 清理与文档同步

- 删除旧 UI 的 34 个跟踪文件及旧 UI 信息架构文档；清除该旧目录内可重建的依赖/构建缓存。当前唯一 UI 为 `apps/teacher-web`。
- 移除旧 UI 三个命令、锁文件 workspace 条目和默认 CORS 的旧端口；没有升级依赖，没有改变当前 Teacher Web 的产品行为。
- 根 README、架构、路线、开发边界、贡献指南、应用 README、Tool 契约、数据说明和文档导航与当前实现同步。
- 项目状态页改为当前快照：M0–M11 完成，M12 切片 1–4 已接入，切片 5 和完整 Gate 未完成。没有因仓库清理虚增里程碑完成度。
- 所有保留的 Markdown 纳入链接与状态分类检查。历史里程碑记录保留当时测试数字；迁移/原型材料逐份标注归档与当前事实入口，不把历史待办当作今天的开发计划。
- 保留仍由代码使用的教材基线、来源/权利/许可及审计证据；未发现需要混入主仓库的无关内容。私人环境、数据库、上传、运行状态及导出保持 Git 忽略，不删除用户数据。
- 移除根目录三个过期基线测试日志；这些是被忽略的生成文件，不是测试源码或用户资料。
- 新增 `pnpm check:repo`，只读检查跟踪 Markdown 的本地链接、归档上下文和旧 UI 入口/依赖残留。

## 本轮复验

| 检查 | 结果 |
| --- | --- |
| FastAPI 完整测试 | 474 passed；1 条既有 Starlette/httpx 弃用提示 |
| Teacher Web | 20 个文件、102 项测试通过；类型检查、生产构建通过 |
| Agent | 10 个文件、42 项测试通过；类型检查、构建通过 |
| 锁文件 | 仅移除旧 UI importer，当前依赖版本不变 |
| 文档链接与旧 UI 边界 | `pnpm check:repo` 通过：92 个 Markdown、186 个本地链接；旧 UI 目录/入口/依赖无残留 |

自动测试只使用测试适配器和合成数据，没有调用真实模型或操作教师私人内容。本轮未做新的产品 UI 视觉验收，因为当前 UI 源码未改变。

## 分支收口依据

2026-09-05 M12 后续核对：本轮增加任务 owner/模型会话隔离、旧组卷 Beta 限制、备份路径保护及固定评测入口；完整 API 587 项通过/1 项跳过，固定 M12 入口 138 项通过/1 项跳过，Teacher Web 102 项和 Agent 42 项及双方类型检查/构建通过。新 ADR 和进行中的 Gate 记录已同步到导航、状态、架构和 AGENTS。无新依赖、数据库迁移或真实记录清理；不改变下列历史清理数字。M12 仍进行中。

同日对象边界补充：从检查点 `be8970b` 建立 `codex/m12-object-boundaries`，补齐识别/历史版本处理前的 owner 检查与备份 CLI 错误脱敏，新增 51 项固定回归。完整 API 638 项通过/1 项跳过，固定 M12 189 项通过/1 项跳过；Teacher Web 102 项、Agent 42 项及双方类型检查/构建复验通过。继续合并回 main 并推送后，仅删除已确认合并的工作分支。无新依赖、迁移或真实数据清理，删除/备份保留决策仍未确认，M12 不宣告完成。

长期保留 `main`。下列分支在清理前已由 main 包含：

- `codex/lesson-agent-v1`：`fb37d40`
- `codex/teacher-workbench-v1`：`66eeb40`
- `feat/search-agent-mvp-v1`：`e53873c`
- `feat/teacher-agent-runtime-v1`：`255984b`
- `fix/search-agent-negative-question-type`：`02ee832`（仅本地）
- `stabilize/commercial-baseline-v1`：`3224df1`

`feat/ui-polish-teacher-workspace-v1`（`30138da`）的四个独有提交只涉及已淘汰 UI 和对应旧 UI 说明，不合并回现行界面，按所有者清理要求删除分支。历史提交不改写、不强制覆盖 main；相关代码仍可从既有 Git 历史追溯。清理工作分支 `codex/repository-sync` 验证后合并 main，再删除；最终同步以 main 与 origin/main 相同、工作区无改动和远端分支清单为准。
