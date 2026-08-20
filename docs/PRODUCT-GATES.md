# 产品验证与商业发布门禁

更新日期：2026-08-21

本文件把历史规划 PDF 中最重要的验证原则转化为当前路线的长期门禁。这里的数字是产品决策目标和工作假设，不是收入、留存或质量现状，也不是商业承诺。进入真实 Beta、支付或学校阶段前必须用最新数据和法规重新确认。

## 1. 永久可信红线

以下红线不因里程碑、模型或商业压力而降低：

- 模型输出不等于数学验证；不得绕过 `MathVerifier`。
- 来源、权利、原始文件和 revision 必须可追踪；来源不明内容进入 quarantine/review。
- 教师上传及其 OCR、拆题、修改和验证派生内容始终 private-by-default。
- Agent 只能通过 allowlisted Tool 调用 FastAPI 业务模块，不直接访问数据库、ORM 或私人文件。
- AI 产物默认 `draft` / `teacher_review_required`，不得自动 publish。
- 题库公开发布需要 RightsGate、MathVerifier 和 Teacher Review。
- DeepSeek Harness 与模型供应商是可替换 adapter，不是业务核心或产品品牌。
- 结构化题库、验证、权利、私人资料、教材映射和教师偏好是长期资产，不为短期速度复制或绕过。
- 没有真实记录时返回空结果和可解释建议，不生成假题填满数量。

## 2. 每阶段工程 Gate E

每个里程碑结束都必须通过：

1. 对照阶段目标列出已完成、部分完成、未完成和超范围修改。
2. 相关测试、完整后端测试、主 UI typecheck/build、Agent typecheck/test/build 按修改 seam 通过。
3. 模型不可用、Tool 超时、网络失败、空结果、权限拒绝和取消路径可解释。
4. 没有 Agent 直连数据库、RightsGate/MathVerifier 绕过、private 泄露或自动 publish。
5. 没有 API Key、真实私人资料、运行数据库、来源未审核题库进入 Git。
6. 新依赖完成许可证检查；迁移可回滚；永久删除和破坏性迁移有所有者确认。

Gate E 未通过时，只修当前阶段 blocker，不开始下一阶段。

## 3. 可信质量 Gate Q

进入 Closed Beta 前需要固定 synthetic/evaluation set；进入 Beta 后再用真实教师任务统计：

- 严重数学错误率目标 `<1%` 且持续下降；达不到时不得扩大用户和营销。
- 任何错误率统计必须区分 verified source、program verified、model reviewed 和 teacher review required。
- Rights denied、verification failed、错误教材映射、重复结果和模型不可用均有独立测试。
- 严重错误必须保留 question/run/revision 证据，支持追踪修复影响范围。

`<1%` 是历史规划继承的目标阈值，不代表当前已经达到。

## 4. Closed Beta 产品 Gate

### Gate A：有用

- 20-30 位真实高中数学教师完成封闭测试。
- 首次核心任务完成率目标 `>=70%`。
- 教师能独立完成核心工作流，不依赖开发者手把手代操作。

### Gate B：重复使用

- Week-4 留存目标 `>=35%`。
- Task Acceptance Rate 目标 `>=60%`。
- 使用不是一次性尝鲜；至少有一个高价值工作流形成重复使用。

### Gate C：付费意愿

- 出现真实主动询价、试用延长或付费请求，而不是只回答问卷“愿意付费”。
- activated teacher 付费转化工作目标 `8%-12%`，需由 Beta 数据重新校准。
- Gate A/B/Q 未通过时，不把支付、套餐或营销当作主要工程目标。

## 5. 必须计算的指标

- `activated_teacher`
- `weekly_verified_teacher_tasks`（北极星指标）
- `task_acceptance_rate`
- `search_to_selection_rate`
- `paper_generation_to_export_rate`
- `lesson_generation_to_save_rate`
- `private_library_activation_rate`
- `week_1_retention`
- `week_4_retention`
- `verified_math_error_rate`
- `agent_tool_failure_rate`
- `average_model_cost_per_teacher`
- `average_model_cost_per_completed_task`
- `p50_latency` / `p95_latency`

指标定义必须版本化。模型、题库、工作流或事件定义改变时，不得把前后口径混合比较。

## 6. Analytics 隐私边界

Analytics 禁止记录：

- 私人 PDF/DOCX/图片正文；
- 完整私人题目或完整模型提示词；
- 学生姓名、证件、电话、人脸和家庭信息；
- API Key、M2M token 或认证凭据；
- 能够跨教师反推出私人内容的原始 payload。

事件默认只保存最小化标识、能力类型、可信状态、耗时、结果数量、错误分类和教师主动反馈。数据保留期限、删除和导出规则必须在 Beta 前明确。

## 7. 商业发布 Gate D

Teacher Pro 开放付费前至少满足：

- Gate A/B/C/Q 有真实数据支持；
- owner/tenant isolation、RBAC、IDOR 测试通过；
- 备份与恢复至少完成一次演练；
- 支付幂等、Webhook 验签、订阅/退款状态机通过；
- 权利投诉、内容下架、权利撤销影响追踪可用；
- 用户协议、隐私政策、AI 内容标识、退款和数据导出/删除流程就绪；
- 第三方 License 清单和生产密钥治理完成；
- 单位成本可监控，模型/API 故障有明确体验，不用静默降级伪装成功。

教研组版只有在 Teacher Pro 留存和付费成立后启动；学校版只有在 team/private 权限模型经过真实使用和越权测试后启动。
