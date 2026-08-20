# 产品与工程路线图

更新日期：2026-08-20

路线图按门禁顺序推进，不并行铺开后续 Agent。完成旧 REST 工作流不等于完成对应 Agent。

| 阶段 | 状态 | 目标与完成门禁 |
| --- | --- | --- |
| M0 商业迁移与数据隔离 | 已完成 | Clean snapshot、私有仓库、synthetic fixtures、商业数据目录为空、迁移测试稳定。 |
| M1 TeacherAgentRuntime | 已完成 | 产品自有 Runtime seam、Legacy/DSH adapter、独立 Agent Service、五个只读 Tool、安全测试。 |
| M2 Trusted Search Agent | 已完成 | 自然语言意图、grounded 检索、可信状态、去重/多样性、空结果与评测门禁。 |
| M3 新 Teacher Web 基础 | 已完成 | 完全新的视觉系统、Agent 能力导航、上下任务工作台、响应式和动态纸张画布。 |
| **M4 Search 集成稳定化** | **当前** | 新 UI 成为默认入口；同源 API、错误/取消/空状态、解析缺陷、全量测试与文档统一。 |
| M5 Solve Agent | 待开始 | 对新题求解、已验证题优先、标准/第二解法、MathVerifier 分级；不伪装模型结果为验证通过。 |
| M6 Private Library Agent | 待开始 | PDF/DOCX/图片进入 private workspace；OCR/拆题/映射可追踪；绝不自动公开。 |
| M7 Paper Agent | 待开始 | 受控选题、试卷 draft、双向细目表、来源/验证门禁、教师确认后导出。 |
| M8 Lesson Agent | 待开始 | 教案 draft、目标—活动—练习映射、教师逐段编辑、引用题目可信状态。 |
| M9 Teacher Memory | 待开始 | 只在真实教师使用后记录可解释、可查看、可删除的偏好；不存不必要的敏感正文。 |
| M10 Closed Beta | 待开始 | 真实教师验证、账号、云端隔离、监控、备份与恢复；通过越权测试后开放。 |
| M11 商业化 | 待开始 | 权利审查、内容下架、支付/额度、合规、至少一次恢复演练；不提前建设学校 ERP。 |

## 当前之后的启动顺序

`Search 稳定化 → Solve → Private Library → Paper → Lesson → Memory → Closed Beta → 商业化`

下一阶段只能在当前阶段的测试、可信、权利与隐私门禁全部通过后启动。视觉需求可以持续改进，但不得替代数学正确性、来源治理或教师工作流验证。
