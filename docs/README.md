# 文档导航

本目录分为“当前事实”和“历史记录”两层。开发与评审先读当前文档，只有追溯迁移决策时才进入历史目录。

## 当前事实（优先级最高）

- [`DEVELOPMENT-BOUNDARY.md`](DEVELOPMENT-BOUNDARY.md)：产品范围、不可违反原则、当前阶段的允许与禁止事项。
- [`PROJECT-STATUS.md`](PROJECT-STATUS.md)：每项能力当前究竟是已实现、仅有旧实现、界面预览还是尚未开始。
- [`ARCHITECTURE.md`](ARCHITECTURE.md)：主应用、业务后端、Agent Runtime 与数据之间的 seam 和依赖方向。
- [`ROADMAP.md`](ROADMAP.md)：从当前里程碑到封闭测试与商业化的顺序和启动门槛。
- [`../AGENTS.md`](../AGENTS.md)：供代码开发 Agent 执行的精简规则。

## 治理与历史记录

- `commercial-v1/`：商业仓库迁移、Runtime、Search Agent、测试与验收的历史证据。内容仍有审计价值，但其中的“下一步”“Prompt N”与 `apps/web` 主入口描述不再代表当前计划。
- `high-school-math-ai/`：旧原型时期的产品、架构、教材、审计与 UI 资料。作为地基和证据保留，不作为新 UI 或当前开发优先级的默认来源。
- `legal/`：第三方许可证与法律相关清单。

## 文档维护规则

1. 产品范围改变时，先更新 `DEVELOPMENT-BOUNDARY.md`。
2. 能力从预览进入可用、或从旧实现完成 Agent 化时，更新 `PROJECT-STATUS.md`。
3. seam、接口或依赖方向改变时，更新 `ARCHITECTURE.md` 并新增 ADR。
4. 只记录历史验收的文档不要反复改写；在顶部注明被哪份当前文档取代即可。
5. README 只提供导航和最短启动路径，不复制整份产品规范。
