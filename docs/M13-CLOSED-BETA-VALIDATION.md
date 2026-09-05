# M13 Closed Beta Validation

## 当前状态

项目所有者于 2026-09-05 明确确认从已完成的 M12 进入 M13。M13 当前进行中；第一条切片“版本化指标契约”已经实现，其余切片尚未开始。M13 的目标是验证真实教师价值，不是继续堆叠产品功能，也不提前建设 M14 的支付、组织或生产基础设施。

## 唯一目标与完成 Gate

用 20–30 位真实高中数学教师验证有用性、重复使用、数学质量和真实付费意愿：

- Gate A：首次核心任务完成率不低于 70%。
- Gate B：Task Acceptance Rate 不低于 60%，Week-4 留存不低于 35%，至少一个高价值工作流形成重复使用。
- Gate Q：严重数学错误率低于 1%，并按 verified source、program verified、model reviewed、teacher review required 分层。
- Gate C：出现主动询价、申请延长试用或真实付费请求；本阶段不接支付。

M12 合成评测只能证明进入 Beta 的准备条件，不能替代这些真实数据。

## 切片顺序

1. **版本化指标契约（已完成）**：`BetaValidationMetrics.record/snapshot` 是 M13 指标计算的深模块 Interface；`m13.v1` 固定 16 项产品指标的分子、分母、单位、时间窗和可信分层。事件 schema 只允许枚举状态与数值，不存在正文、prompt、答案、解析、文件、URL 或自由文本字段。owner 与任务标识在写入 SQLite 前使用私有密钥 HMAC 摘要，汇总结果不返回任何标识。
2. **采集启用与生命周期（未开始）**：明确事件保留期、教师告知、导出与删除规则；只有这些规则确认并通过测试后，才把指标模块接入真实工作流。当前代码没有全局实例、路由或中间件，不会自动创建指标库或采集真实行为。
3. **核心工作流埋点（未开始）**：从服务端已确认事实记录 Search 选择、Paper 导出、Lesson 保存、私有资料确认导入、私题保存、任务接受/拒绝、可信等级、Tool 成败、耗时和成本。浏览器、Agent 与模型不能提交 owner、可信结论、成本或成功状态。
4. **私有运营读数（未开始）**：提供最小化聚合快照和 cohort 进度，不提供题面、教师内容、逐人内容查看或后台代操作能力；小样本结果必须显示分母，不以百分比掩盖样本不足。
5. **分阶段真实 Beta（未开始）**：先完成操作预演，再邀请 20–30 位真实教师；记录支持请求、严重数学错误证据和主动商业信号，只修真实阻塞与可信问题。
6. **M13 Gate（未开始）**：复核 A/B/C/Q、Gate P 和 Gate E，列明达标、未达标与样本限制；未通过不得扩大用户、营销或进入 M14。

## `m13.v1` 指标口径

| 指标 | 固定口径 |
| --- | --- |
| `activated_teacher` | 窗口内至少完成一次核心任务的去重教师数。 |
| `weekly_verified_teacher_tasks` | 窗口结束前七天内完成、可信等级为 verified source 或 program verified 的去重任务数。 |
| `task_acceptance_rate` | 每个任务最后一次明确接受/拒绝决定中的接受比例。 |
| `search_to_selection_rate` | 已完成搜索中产生明确结果选择的比例。 |
| `paper_generation_to_export_rate` | 已生成试卷中完成导出的比例。 |
| `lesson_generation_to_save_rate` | 已生成教案中明确保存的比例。 |
| `private_library_activation_rate` | 窗口内活跃教师中至少确认一次私有资料导入的比例。 |
| `private_question_authoring_acceptance_rate` | 已完成辅助命题中明确保存到本人私题库的比例。 |
| `week_1_retention` | 首次完成任务后第 7–13 天再次完成任务的 eligible 教师比例。 |
| `week_4_retention` | 首次完成任务后第 28–34 天再次完成任务的 eligible 教师比例。 |
| `verified_math_error_rate` | verified source/program verified 完成任务中，经教师确认的严重数学错误比例。 |
| `agent_tool_failure_rate` | Agent Tool 明确结束事件中的失败比例。 |
| `average_model_cost_per_teacher` | 窗口内模型成本除以产生验证事件的去重教师数。 |
| `average_model_cost_per_completed_task` | 窗口内模型成本除以完成的去重任务数。 |
| `p50_latency` / `p95_latency` | 核心任务完成耗时的 nearest-rank 百分位。 |

所有比率在分母为零时返回 `null`，不能伪装为 0%。留存只纳入已具备完整观察期的 cohort。严重错误同时按四级可信状态分别输出，不能混合口径。

## 隐私和权利边界

- 不记录私人 PDF/DOCX/图片正文、完整题目、答案、解析、完整模型提示词、个人题库名称或学生信息。
- `task_ref` 只接受服务端生成的 ASCII opaque 标识，写入前与 owner 一起摘要；原始 owner/task ID 不进入指标库。
- 不提供浏览器或 Agent 写指标的公开 Interface；后续埋点只能由通过业务门禁后的服务端事实触发。
- 当前切片仅建立并验证模块，没有启用真实采集。保留期、教师告知、删除和导出属于第二条切片，未确认前不得接入真实教师任务。
- M13 不改变私题永久 owner-only、无后台内容权限、无公开发布路径和 Gate P 的既有规则。

## 当前验证

- `apps/api/tests/test_beta_validation_metrics.py`：6 项 synthetic 测试通过。
- 新固定入口：`python -m pytest -c apps/api/pytest-m13.ini -q`，继承 M12 的全部固定安全/质量文件并追加 M13 指标契约；当前结果 **205 passed、1 skipped**。
- 完整 FastAPI：**654 passed、1 skipped**。
- 自动测试使用临时 SQLite、合成 owner/task 标识和固定成本，不调用真实模型、不读取或写入真实教师数据。

M13 只有真实 Beta 达到 Gate 后才能标记完成；当前 6 项新增测试及继承回归不能代表真实教师指标。
