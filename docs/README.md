# 文档导航

本目录分为“当前事实”和“历史记录”两层。开发与评审先读当前文档，只有追溯迁移决策时才进入历史目录。

## 当前事实（优先级最高）

- [`DEVELOPMENT-BOUNDARY.md`](DEVELOPMENT-BOUNDARY.md)：产品范围、不可违反原则、当前阶段的允许与禁止事项。
- [`PROJECT-STATUS.md`](PROJECT-STATUS.md)：每项能力当前究竟是已实现、仅有旧实现、界面预览还是尚未开始。
- [`ARCHITECTURE.md`](ARCHITECTURE.md)：主应用、业务后端、Agent Runtime 与数据之间的 seam 和依赖方向。
- [`ROADMAP.md`](ROADMAP.md)：M0-M17 的当前里程碑顺序、单阶段目标和启动门槛。
- [`PRODUCT-GATES.md`](PRODUCT-GATES.md)：永久可信红线、阶段工程 Gate、Beta 指标和商业发布门禁。
- [`MATH-CONTENT-PRESENTATION.md`](MATH-CONTENT-PRESENTATION.md)：题面、解题步骤和答案的 KaTeX 输出约定、旧结果兼容、失败降级与可读性 Gate。
- [`M5-SOLVE-EVALUATION.md`](M5-SOLVE-EVALUATION.md)：Solve 的固定项目自建合成评测、覆盖范围和结果边界。
- [`M5-GATE-REVIEW.md`](M5-GATE-REVIEW.md)：M5 完成 Gate、工程回归、范围核对和阶段转换结论。
- [`M6-PRIVATE-LIBRARY-AGENT.md`](M6-PRIVATE-LIBRARY-AGENT.md)：已完成 M6 的范围、隐私边界、纵向切片和完成 Gate。
- [`M6-PRIVATE-LIBRARY-EVALUATION.md`](M6-PRIVATE-LIBRARY-EVALUATION.md)：M6 的固定 synthetic evaluation、违规计数和结果边界。
- [`M6-GATE-REVIEW.md`](M6-GATE-REVIEW.md)：M6 完成 Gate、工程回归、浏览器验收和阶段转换结论。
- [`M7-MULTIMODAL-QUESTION-SOLVE.md`](M7-MULTIMODAL-QUESTION-SOLVE.md)：已完成 M7 的单题图片/截图、公式 OCR、图形保真输入、可信 Solve 边界与切片状态。
- [`M8-PRIVATE-QUESTION-AUTHORING.md`](M8-PRIVATE-QUESTION-AUTHORING.md)：辅助命题、owner 独占私题库、个人分类管理和永久公共禁入规则。
- [`M8-PRIVATE-QUESTION-AUTHORING-EVALUATION.md`](M8-PRIVATE-QUESTION-AUTHORING-EVALUATION.md)：M8 的 26 场景固定 synthetic evaluation、违规计数和结果边界。
- [`M8-GATE-REVIEW.md`](M8-GATE-REVIEW.md)：M8 功能 Gate、Gate E/Gate P、工程回归和阶段转换结论。
- [`../AGENTS.md`](../AGENTS.md)：供代码开发 Agent 执行的精简规则。

- [`M9-PAPER-AGENT.md`](M9-PAPER-AGENT.md)、[评测](M9-PAPER-AGENT-EVALUATION.md)、[Gate](M9-GATE-REVIEW.md)：已完成的组卷、历史版本与精确导出。
- [`M10-LESSON-AGENT.md`](M10-LESSON-AGENT.md)、[评测](M10-LESSON-AGENT-EVALUATION.md)、[Gate](M10-GATE-REVIEW.md)：已完成的教案闭环。
- [`M11-TEACHER-MEMORY.md`](M11-TEACHER-MEMORY.md)、[评测](M11-TEACHER-MEMORY-EVALUATION.md)、[Gate](M11-GATE-REVIEW.md)：已完成的教师偏好与生命周期。
- [`M12-CLOSED-BETA-READINESS.md`](M12-CLOSED-BETA-READINESS.md)：唯一活动里程碑，切片 1–4 已接入，切片 5 和完整 Gate 尚未完成。
- [`M12-DATA-LIFECYCLE.md`](M12-DATA-LIFECYCLE.md)：第五切片的旧接口隔离、会话预览/确认清理、HTTP 缓存保护、实际数据保留边界、合成演练和待完成项。
- [`M12-GATE-REVIEW.md`](M12-GATE-REVIEW.md)：固定评测入口、当前 E/P/Q 证据及尚未满足的完成条件；不是 M12 完成声明。
- [`ADR-2026-09-04-OWNER-AGENT-SESSIONS.md`](ADR-2026-09-04-OWNER-AGENT-SESSIONS.md)：教师/模块签名会话、任务 owner 校验及单进程限制。
- [`TEACHER-TOOL-CONTRACTS.md`](TEACHER-TOOL-CONTRACTS.md)：当前九项受控 Tool 契约。
- [`REPOSITORY-SYNC.md`](REPOSITORY-SYNC.md)：仓库清理范围、文档分层与本轮复验记录。

## 治理与历史记录

- `commercial-v1/`：商业仓库迁移、Runtime、Search Agent、测试与验收的历史证据。内容仍有审计价值，但其中的“下一步”“Prompt N”与 `apps/web` 主入口描述不再代表当前计划。
- `high-school-math-ai/`：旧原型的架构、教材、审计与权利证据，其中教材基线仍被当前代码使用。旧 UI 源码与信息架构已删除，不作为当前开发优先级来源。
- `legal/`：第三方许可证与法律相关清单。

## 文档维护规则

1. 产品范围改变时，先更新 `DEVELOPMENT-BOUNDARY.md`。
2. 阶段顺序或验收阈值改变时，更新 `ROADMAP.md` 与 `PRODUCT-GATES.md`。
3. 能力从预览进入可用、或从旧实现完成 Agent 化时，更新 `PROJECT-STATUS.md`。
4. seam、接口或依赖方向改变时，更新 `ARCHITECTURE.md` 并新增 ADR。
5. 只记录历史验收的文档不要反复改写；在顶部注明被哪份当前文档取代即可。
6. README 只提供导航和最短启动路径，不复制整份产品规范。
