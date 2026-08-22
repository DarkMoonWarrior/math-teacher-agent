# 文档导航

本目录分为“当前事实”和“历史记录”两层。开发与评审先读当前文档，只有追溯迁移决策时才进入历史目录。

## 当前事实（优先级最高）

- [`DEVELOPMENT-BOUNDARY.md`](DEVELOPMENT-BOUNDARY.md)：产品范围、不可违反原则、当前阶段的允许与禁止事项。
- [`PROJECT-STATUS.md`](PROJECT-STATUS.md)：每项能力当前究竟是已实现、仅有旧实现、界面预览还是尚未开始。
- [`ARCHITECTURE.md`](ARCHITECTURE.md)：主应用、业务后端、Agent Runtime 与数据之间的 seam 和依赖方向。
- [`ROADMAP.md`](ROADMAP.md)：M0-M17 的当前里程碑顺序、单阶段目标和启动门槛。
- [`PRODUCT-GATES.md`](PRODUCT-GATES.md)：永久可信红线、阶段工程 Gate、Beta 指标和商业发布门禁。
- [`M5-SOLVE-EVALUATION.md`](M5-SOLVE-EVALUATION.md)：Solve 的固定项目自建合成评测、覆盖范围和结果边界。
- [`M5-GATE-REVIEW.md`](M5-GATE-REVIEW.md)：M5 完成 Gate、工程回归、范围核对和阶段转换结论。
- [`M6-PRIVATE-LIBRARY-AGENT.md`](M6-PRIVATE-LIBRARY-AGENT.md)：已完成 M6 的范围、隐私边界、纵向切片和完成 Gate。
- [`M6-PRIVATE-LIBRARY-EVALUATION.md`](M6-PRIVATE-LIBRARY-EVALUATION.md)：M6 的固定 synthetic evaluation、违规计数和结果边界。
- [`M6-GATE-REVIEW.md`](M6-GATE-REVIEW.md)：M6 完成 Gate、工程回归、浏览器验收和阶段转换结论。
- [`M7-MULTIMODAL-QUESTION-SOLVE.md`](M7-MULTIMODAL-QUESTION-SOLVE.md)：当前 M7 的单题图片/截图、公式 OCR、图形保真输入、可信 Solve 边界与切片状态。
- [`M8-PRIVATE-QUESTION-AUTHORING.md`](M8-PRIVATE-QUESTION-AUTHORING.md)：辅助命题、owner 独占私题库、个人分类管理和永久公共禁入规则。
- [`../AGENTS.md`](../AGENTS.md)：供代码开发 Agent 执行的精简规则。

## 治理与历史记录

- `commercial-v1/`：商业仓库迁移、Runtime、Search Agent、测试与验收的历史证据。内容仍有审计价值，但其中的“下一步”“Prompt N”与 `apps/web` 主入口描述不再代表当前计划。
- `high-school-math-ai/`：旧原型时期的产品、架构、教材、审计与 UI 资料。作为地基和证据保留，不作为新 UI 或当前开发优先级的默认来源。
- `legal/`：第三方许可证与法律相关清单。

## 文档维护规则

1. 产品范围改变时，先更新 `DEVELOPMENT-BOUNDARY.md`。
2. 阶段顺序或验收阈值改变时，更新 `ROADMAP.md` 与 `PRODUCT-GATES.md`。
3. 能力从预览进入可用、或从旧实现完成 Agent 化时，更新 `PROJECT-STATUS.md`。
4. seam、接口或依赖方向改变时，更新 `ARCHITECTURE.md` 并新增 ADR。
5. 只记录历史验收的文档不要反复改写；在顶部注明被哪份当前文档取代即可。
6. README 只提供导航和最短启动路径，不复制整份产品规范。
