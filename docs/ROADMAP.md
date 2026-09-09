# 产品与工程路线图

更新日期：2026-09-09

本路线以当前仓库真实进度为起点，并继承《高中数学教师可信 Agent：商业开发路线与 Codex 提示词手册 v1.0》的核心原则。旧 PDF 的阶段编号和 Prompt 顺序属于历史执行方案；本文件是当前阶段顺序的 source of truth。

## 路线调整原则

1. 不返工已经通过验证的迁移、Runtime、Search 和新 Teacher Web 基础。
2. 一个里程碑只完成一个主要教师工作流或一个商业门禁，不把多个高风险能力捆绑开发。
3. 完成旧 REST 模块不等于对应 Agent 已完成；必须经过新的产品接口、可信状态和教师工作流验收。
4. 功能 Gate、可信 Gate、隐私/权利 Gate 和工程 Gate 全部通过后才能进入下一阶段。
5. Closed Beta 先验证价值，再建设支付和复杂商业基础；Teacher Pro 证明成立后才进入教研组和学校。

## 最新路线 M0-M17

| 阶段 | 状态 | 本阶段唯一主目标 | 完成 Gate |
| --- | --- | --- | --- |
| M0 商业迁移与数据隔离 | 已完成 | 建立商业代码基线、synthetic fixtures、quarantine 与空的 commercial-approved 目录。 | 权利边界清楚；无真实私人数据/密钥；迁移与原系统测试通过。 |
| M1 TeacherAgentRuntime | 已完成 | 建立产品自有 Runtime seam、Legacy/DSH adapter、独立 Agent Service 和五个只读 Tool。 | Agent 不接触数据库；M2M fail closed；Runtime、Tool 与安全测试通过。 |
| M2 Trusted Search Core | 已完成 | 自然语言意图、教材映射、真实检索、权利/验证状态、去重、多样性与空结果。 | 固定 synthetic evaluation 覆盖精确、歧义、无结果、权利拒绝和模型不可用。 |
| M3 新 Teacher Web 基础 | 已完成 | 建立 Agent-first 教师工作台；旧 UI 已移除，`apps/teacher-web` 为唯一产品界面。 | 新视觉、能力导航、响应式、动态纸张和诚实的未接入状态可用。 |
| M4 Search 集成稳定化 | 已完成 | 让新工作台中的 Search 成为稳定、可理解、可恢复的完整入口。 | 同源请求、加载、取消、错误、空结果、可信标签、关键响应式和全量测试全部通过；Gate E 于 2026-08-21 通过。 |
| M5 Solve Agent | 已完成 | 为题库题和新题提供分层可信解答，不把模型输出冒充 verified。 | 优先复用 verified solution；新解答明确 `teacher_review_required`；MathVerifier 分级、固定 synthetic eval、320—1920px 响应式和 Gate E 通过。 |
| M6 Private Library Agent | 已完成 | 让教师的 PDF/DOCX/图片在 private workspace 内完成导入、OCR、拆题、映射和检索。 | 原文件与 revision 可追踪；private-by-default；owner 隔离与越权测试、固定评测和 Gate E 于 2026-08-22 通过；无自动 public 路径。 |
| **M7 多模态题目采集与图片解题** | **已完成；阶段转换已确认** | 让文字、截图和单题图片经过可核对的文字/公式识别，并把必要原图视觉信息安全接入 Solve。 | owner/private、逐次外部同意、原图与 revision 可追踪；题面/步骤/答案公式可读；带图题不丢失视觉条件；MathVerifier 与视觉判断分层；15 场景固定评测 9 类违规为 0，Gate E 于 2026-08-24 通过。 |
| **M8 私有辅助命题 Agent** | **已完成；阶段转换已确认** | 将教师命题要求转换为结构化题目草稿，并保存到 owner 独占、可命名分类和自主管理的私题库。 | 26 场景固定评测 12 类违规为 0；完整题面/解析/答案闭环、后台恢复与取消、owner 管理、工程回归和 Gate E/Gate P 于 2026-08-28 通过。 |
| **M9 Paper Agent** | **已完成；阶段转换已确认** | 将自然语言转换为 PaperBlueprint，并生成可编辑试卷草稿、不可变版本和双向细目表。 | 权利/验证/重复/相似度/覆盖/难度门禁通过；不为凑题自动生成题；引用私题不改变 owner/visibility；显式保存及精确已保存版本导出闭环可用；28 场景固定评测 15 类违规为 0，Gate E/Gate P 连续性通过；所有者于 2026-08-30 确认进入 M10。 |
| **M10 Lesson Agent** | **已完成；阶段转换已确认** | 基于教材、真实题目和教师资料生成可逐段编辑的教案草稿。 | 六条切片、28 场景固定评测、Gate E/Gate P 连续性和完整 DOCX/PDF 视觉检查通过；回滚点 `9997fc8`，所有者于 2026-08-31 确认进入 M11。 |
| **M11 Teacher Memory** | **已完成；阶段转换已确认** | 在真实教师反馈基础上保存可解释、可控制的偏好。 | 五条切片、26 场景固定评测 12 类违规为 0、完整工程 Gate 通过；回滚点 `5614fc0`，所有者于 2026-09-01 确认进入 M12。 |
| **M12 Closed Beta Readiness** | **已完成；阶段转换已确认** | 建立让真实教师安全试用所需的最小身份、owner 隔离、feature flags、监控、备份、恢复与删除边界。 | 五条切片、固定评测和完整 E/P/Q 连续性 Gate 通过；回滚点 `570cf79`。不接支付、不扩大功能。 |
| M13 Closed Beta Validation | 真实验证延期；切片 1–5 已完成，Gate 未通过 | 用 20-30 位真实教师验证有用性、重复使用、错误率和付费意愿；当前缺少足够样本，不作通过结论。 | 达到 `PRODUCT-GATES.md` 的 Gate A/B/Q；Gate C 有真实证据；analytics 不记录私人正文、私题或学生信息。 |
| **M14 Commercial Foundation** | **进行中；生产身份、账号生命周期、登录防护、操作者审计、摘要密钥轮换、可信代理与分布式限流 adapter 已实现** | 在项目所有者明确接受 M13 未验证风险后，先建立生产身份、PostgreSQL、对象存储、后台任务、Entitlement、订单、支付和退款的严格顺序与边界。 | RBAC、IDOR、tenant isolation、私题永久隔离、支付幂等、Webhook 验签、退款/订阅状态机和恢复能力通过；M13 未验证状态持续披露。 |
| M15 Teacher Pro | 待开始 | 面向个人高中数学教师发布 Free + Teacher Pro。 | 权利下架、隐私/条款、私题数据导出/删除、成本监控、客服/退款和生产发布 Checklist 完成；留存与单位经济健康。 |
| M16 教研组版 | 待开始 | 在个人版成立后增加小范围共享题库、试卷/教案模板与协同审核。 | private/team 明确分离；辅助命制私题仍不可共享；共享需授权；撤销、审计与角色权限测试通过。 |
| M17 学校版 | 待开始 | 在教研组权限模型稳定后提供组织级部署和治理。 | organization/private/public 隔离不被破坏；学校管理员不能读取教师私题或私人资料；仍不扩展为 ERP/LMS。 |

## 当前启动顺序

`M4 Search 稳定化（已完成） → M5 Solve（已完成） → M6 Private Library（已完成） → M7 多模态图片解题（已完成） → M8 私有辅助命题（已完成） → M9 Paper（已完成） → M10 Lesson（已完成） → M11 Memory（已完成） → M12 Beta 准备（已完成） → M13 Beta 验证（真实验证延期） → M14 商业基础（进行中） → M15 Teacher Pro → M16 教研组 → M17 学校`

M6 的固定范围、评测与完成 Gate 见 [`M6-PRIVATE-LIBRARY-AGENT.md`](M6-PRIVATE-LIBRARY-AGENT.md)、[`M6-PRIVATE-LIBRARY-EVALUATION.md`](M6-PRIVATE-LIBRARY-EVALUATION.md) 和 [`M6-GATE-REVIEW.md`](M6-GATE-REVIEW.md)。M7 的范围、评测与完成 Gate 见 [`M7-MULTIMODAL-QUESTION-SOLVE.md`](M7-MULTIMODAL-QUESTION-SOLVE.md)、[`M7-MULTIMODAL-SOLVE-EVALUATION.md`](M7-MULTIMODAL-SOLVE-EVALUATION.md) 和 [`M7-GATE-REVIEW.md`](M7-GATE-REVIEW.md)。M8 的固定边界、评测与完成 Gate 见 [`M8-PRIVATE-QUESTION-AUTHORING.md`](M8-PRIVATE-QUESTION-AUTHORING.md)、[`M8-PRIVATE-QUESTION-AUTHORING-EVALUATION.md`](M8-PRIVATE-QUESTION-AUTHORING-EVALUATION.md) 和 [`M8-GATE-REVIEW.md`](M8-GATE-REVIEW.md)。M9 的固定范围、评测与 Gate 证据见 [`M9-PAPER-AGENT.md`](M9-PAPER-AGENT.md)、[`M9-PAPER-AGENT-EVALUATION.md`](M9-PAPER-AGENT-EVALUATION.md) 和 [`M9-GATE-REVIEW.md`](M9-GATE-REVIEW.md)。M10 的固定范围、评测与 Gate 证据见 [`M10-LESSON-AGENT.md`](M10-LESSON-AGENT.md)、[`M10-LESSON-AGENT-EVALUATION.md`](M10-LESSON-AGENT-EVALUATION.md) 和 [`M10-GATE-REVIEW.md`](M10-GATE-REVIEW.md)。M11 的固定边界、评测与 Gate 证据见 [`M11-TEACHER-MEMORY.md`](M11-TEACHER-MEMORY.md)、[`M11-TEACHER-MEMORY-EVALUATION.md`](M11-TEACHER-MEMORY-EVALUATION.md) 和 [`M11-GATE-REVIEW.md`](M11-GATE-REVIEW.md)。M12 的固定边界与切片顺序见 [`M12-CLOSED-BETA-READINESS.md`](M12-CLOSED-BETA-READINESS.md)。M13 的已实现切片、延期状态和未来真实采集条件见 [`M13-CLOSED-BETA-VALIDATION.md`](M13-CLOSED-BETA-VALIDATION.md)。M14 当前边界和开发顺序见 [`M14-COMMERCIAL-FOUNDATION.md`](M14-COMMERCIAL-FOUNDATION.md)。

任何阶段不得因为后端已有旧模块、界面已经出现入口或模型能够生成文本，就提前宣称完成。详细产品和商业门禁见 [`PRODUCT-GATES.md`](PRODUCT-GATES.md)。
