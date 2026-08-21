# 产品与工程路线图

更新日期：2026-08-21

本路线以当前仓库真实进度为起点，并继承《高中数学教师可信 Agent：商业开发路线与 Codex 提示词手册 v1.0》的核心原则。旧 PDF 的阶段编号和 Prompt 顺序属于历史执行方案；本文件是当前阶段顺序的 source of truth。

## 路线调整原则

1. 不返工已经通过验证的迁移、Runtime、Search 和新 Teacher Web 基础。
2. 一个里程碑只完成一个主要教师工作流或一个商业门禁，不把多个高风险能力捆绑开发。
3. 完成旧 REST 模块不等于对应 Agent 已完成；必须经过新的产品接口、可信状态和教师工作流验收。
4. 功能 Gate、可信 Gate、隐私/权利 Gate 和工程 Gate 全部通过后才能进入下一阶段。
5. Closed Beta 先验证价值，再建设支付和复杂商业基础；Teacher Pro 证明成立后才进入教研组和学校。

## 最新路线 M0-M15

| 阶段 | 状态 | 本阶段唯一主目标 | 完成 Gate |
| --- | --- | --- | --- |
| M0 商业迁移与数据隔离 | 已完成 | 建立商业代码基线、synthetic fixtures、quarantine 与空的 commercial-approved 目录。 | 权利边界清楚；无真实私人数据/密钥；迁移与原系统测试通过。 |
| M1 TeacherAgentRuntime | 已完成 | 建立产品自有 Runtime seam、Legacy/DSH adapter、独立 Agent Service 和五个只读 Tool。 | Agent 不接触数据库；M2M fail closed；Runtime、Tool 与安全测试通过。 |
| M2 Trusted Search Core | 已完成 | 自然语言意图、教材映射、真实检索、权利/验证状态、去重、多样性与空结果。 | 固定 synthetic evaluation 覆盖精确、歧义、无结果、权利拒绝和模型不可用。 |
| M3 新 Teacher Web 基础 | 已完成 | 建立完全新的 Agent-first 教师工作台，旧 `apps/web` 仅保留为业务地基。 | 新视觉、能力导航、响应式、动态纸张和诚实的未接入状态可用。 |
| M4 Search 集成稳定化 | 已完成 | 让新工作台中的 Search 成为稳定、可理解、可恢复的完整入口。 | 同源请求、加载、取消、错误、空结果、可信标签、关键响应式和全量测试全部通过；Gate E 于 2026-08-21 通过。 |
| **M5 Solve Agent** | **已完成（待阶段确认）** | 为题库题和新题提供分层可信解答，不把模型输出冒充 verified。 | 优先复用 verified solution；新解答明确 `teacher_review_required`；MathVerifier 分级、固定 synthetic eval、320—1920px 响应式和 Gate E 通过。 |
| M6 Private Library Agent | 待开始 | 让教师的 PDF/DOCX/图片在 private workspace 内完成导入、OCR、拆题、映射和检索。 | 原文件与 revision 可追踪；private-by-default；owner 隔离与越权测试通过；无自动 public 路径。 |
| M7 Paper Agent | 待开始 | 将自然语言转换为 PaperBlueprint，并生成可编辑试卷草稿和双向细目表。 | 权利/验证/重复/相似度/覆盖/难度门禁通过；不为凑题伪造 verified 题；导出闭环可用。 |
| M8 Lesson Agent | 待开始 | 基于教材、真实题目和教师资料生成可逐段编辑的教案草稿。 | 目标、活动、例题、练习、作业与来源状态可追踪；AI 内容明确标记；教师保存前可编辑。 |
| M9 Teacher Memory | 待开始 | 在真实教师反馈基础上保存可解释、可控制的偏好。 | 偏好可查看、修改、删除和关闭自动学习；推断有来源与 confidence；不保存不必要的敏感正文。 |
| M10 Closed Beta Readiness | 待开始 | 建立让真实教师安全试用所需的最小身份、owner 隔离、feature flags、监控、备份与恢复。 | 越权、会话隔离、故障体验、备份恢复演练通过；不接支付、不扩大功能。 |
| M11 Closed Beta Validation | 待开始 | 停止堆功能，用 20-30 位真实教师验证有用性、重复使用、错误率和付费意愿。 | 达到 `PRODUCT-GATES.md` 的 Gate A/B/Q；Gate C 有真实证据；analytics 不记录私人正文或学生信息。 |
| M12 Commercial Foundation | 待开始 | 在 Beta Gate 通过后建设生产级认证、PostgreSQL、对象存储、后台任务、Entitlement、订单、支付和退款。 | RBAC、IDOR、tenant isolation、支付幂等、Webhook 验签、退款/订阅状态机和恢复能力通过。 |
| M13 Teacher Pro | 待开始 | 面向个人高中数学教师发布 Free + Teacher Pro。 | 权利下架、隐私/条款、成本监控、客服/退款和生产发布 Checklist 完成；留存与单位经济健康。 |
| M14 教研组版 | 待开始 | 在个人版成立后增加小范围共享题库、试卷/教案模板与协同审核。 | private/team 明确分离；分享需授权；撤销、审计与角色权限测试通过。 |
| M15 学校版 | 待开始 | 在教研组权限模型稳定后提供组织级部署和治理。 | organization/private/public 隔离不被破坏；学校管理员不能默认读取教师私人资料；仍不扩展为 ERP/LMS。 |

## 当前启动顺序

`M4 Search 稳定化（已完成） → M5 Solve（已完成，等待所有者确认） → M6 Private Library（未启动） → M7 Paper → M8 Lesson → M9 Memory → M10 Beta 准备 → M11 Beta 验证 → M12 商业基础 → M13 Teacher Pro → M14 教研组 → M15 学校`

任何阶段不得因为后端已有旧模块、界面已经出现入口或模型能够生成文本，就提前宣称完成。详细产品和商业门禁见 [`PRODUCT-GATES.md`](PRODUCT-GATES.md)。
