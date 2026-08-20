# Post-Baseline Backlog（仅记录，不在基线阶段实现）

> 历史 backlog：当前阶段顺序以 `docs/ROADMAP.md` 为准；已完成项会继续在本表留存审计记录。

以下机会在审计中发现，但按 Prompt 1 边界**不得在本阶段实现**。每一项在开始前都需要项目所有者确认。

| ID | 主题 | 说明 | 建议阶段 |
| --- | --- | --- | --- |
| B-01 | RightsGate 抽取 | 把 `question_bank` 内嵌的权利判定抽取为独立服务，供变式/相似度/发布一致调用；先用现有测试锁定行为 | TeacherAgentRuntime 之前 |
| B-02 | ProviderRegistry | 路由层 `lru_cache` 工厂抽成统一 provider 装配，供 REST 与 Agent 共用 | 与 B-01 同阶段 |
| B-03 | AIOrchestrator 落地 | 按 `module-interfaces-v0.1.md` 设计实现，或由 TeacherAgentRuntime 承担编排 | Agent 阶段 |
| B-04 | TeacherAgentRuntime 接口 | `run/resume/cancel/stream/get_session` + Legacy Runtime + 首批只读 Tool（DOC-03）。**已于 Prompt 2 落地基础层**（`apps/api/app/agent_runtime` + `apps/agent`） | 已完成（Prompt 2） |
| B-05 | DeepSeek Harness 适配器 | 仅通过 adapter/plugin/tool/preset 接入，不改 Harness core（DOC-03）。**已于 Prompt 2 以 rc.6 + plugin/tool 接入完成基础层** | 已完成（Prompt 2） |
| B-06 | 数据库云端化 | 每模块 SQLite → PostgreSQL/pgvector/对象存储；模块接口不变 | 商业化前 |
| B-07 | 后台任务持久化 | `BackgroundJobRegistry` 进程内实现替换为持久化队列 | 多 worker 部署前 |
| B-08 | 认证与教师身份 | 当前教师/管理员只是 UI 模式；需要真实账号、会话与会话级能力令牌 | 封闭 Beta 前 |
| B-09 | 计费与额度 | UsageBilling 设计已有（module-interfaces）；订单/支付不提前开发 | 商业上线前 |
| B-10 | Takedown 流程 | 权利下架与投诉处理代码（ERD 已设计） | 与 B-01 同阶段 |
| B-11 | Search / Solve / Paper / Lesson Agent | 按路线图顺序逐个实现，不并行铺开；Search Agent MVP 为 Prompt 3 候选 | Agent 阶段后期 |
| B-12 | Teacher Memory | 教师长期偏好记忆 | 真实教师验证之后 |
| B-13 | KMI-01 修复 | 课程封存哈希 CRLF/LF 归一化（见 KNOWN-MIGRATION-ISSUES） | 已完成（Prompt 1.5，commit 942c2dc） |
| B-14 | KMI-02 测试数据策略 | 数据依赖测试的 synthetic fixture / 跳过策略（见 KNOWN-MIGRATION-ISSUES） | 已完成（Prompt 1.5，d769021） |
| B-15 | 大文件模块渐进拆分 | `pdf_imports/studio.py`、`question_bank/bank.py` 接口内聚拆分，不重写 | 视维护成本决定 |


## Prompt 3.5 新增（Search Agent 通用规则缺口，非 query 硬编码）

| ID | 主题 | 说明 | 建议阶段 |
| --- | --- | --- | --- |
| B-16 | 负向题型语义反转 | 已修复：`不要填空题` 不再产生正向 `question_types` 约束，并返回明确 warning；混合的正向题型仍可保留。 | 已完成（2026-08-20，含回归测试） |
| B-17 | 难度粒度：稍难/偏难 | 已修复：`稍难` 映射为难度 4，且在通用“难”之前匹配。 | 已完成（2026-08-20，含回归测试） |
| B-18 | 教学用途裸词 | 已修复：`例题`→classroom_example、`复习`→exam_review，仍只作为 soft 排序偏好。 | 已完成（2026-08-20，含回归测试） |
| B-19 | 相对年份 | `近两年` 未解析为年份（无基准日期语义）；当前诚实返回 year=null，需产品语义确认是否引入“相对当前年份”解析 | 产品语义确认后 |
| B-20 | 解释文本自由格式实体消毒 | assistant_explanation 目前可机械消毒 题目ID/年份/验证声明；学校名/考试名等自由格式实体无法正则消毒（结构化结果仍是唯一事实源并优先展示） | 需要 NL 事实抽取能力时 |
