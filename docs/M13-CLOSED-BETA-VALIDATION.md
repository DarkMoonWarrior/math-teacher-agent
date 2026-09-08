# M13 Closed Beta Validation

## 当前状态

项目所有者于 2026-09-05 明确确认从已完成的 M12 进入 M13。“版本化指标契约”“采集启用与生命周期”“核心工作流埋点”“私有运营读数”和“操作预演”五条切片已经实现。由于暂时找不到足够真实教师样本，项目所有者于 2026-09-08 明确决定暂停真实 Beta 并授权进入 M14。M13 真实验证因此延期，Gate A/B/C/Q、Gate P/E **未通过也未豁免**；合成测试不能被解释为产品合理或验证成功。未来恢复真实 Beta 时继续使用本文件冻结的口径。

## 唯一目标与完成 Gate

用 20–30 位真实高中数学教师验证有用性、重复使用、数学质量和真实付费意愿：

- Gate A：首次核心任务完成率不低于 70%。
- Gate B：Task Acceptance Rate 不低于 60%，Week-4 留存不低于 35%，至少一个高价值工作流形成重复使用。
- Gate Q：严重数学错误率低于 1%，并按 verified source、program verified、model reviewed、teacher review required 分层。
- Gate C：出现主动询价、申请延长试用或真实付费请求；本阶段不接支付。

M12 合成评测只能证明进入 Beta 的准备条件，不能替代这些真实数据。

## 切片顺序

1. **版本化指标契约（已完成）**：`BetaValidationMetrics` 是 M13 指标计算的深模块 Interface；`m13.v1` 固定 16 项产品指标的分子、分母、单位、时间窗和可信分层。事件 schema 只允许枚举状态与数值，不存在正文、prompt、答案、解析、文件、URL 或自由文本字段。owner 与任务标识在写入 SQLite 前使用私有密钥 HMAC 摘要，汇总结果不返回任何标识。
2. **采集启用与生命周期（已完成）**：采集开关与 Beta 访问门禁分离并默认关闭；教师必须先在右上角“设置 → 封闭测试与数据”阅读并确认 `m13.notice.v1`，模块才接受该教师的事件。事件固定保留 90 天；教师可在同一面板导出本人保留期内的聚合和分母，可二次确认退出并原子删除本人事件与确认记录。关闭采集不能关闭既有导出/删除权。操作者过期清理默认预览、明确确认后才执行，且保留异常记录。生命周期入口与业务埋点保持解耦；核心服务端事实已由切片 3 接入，默认配置仍不会采集真实行为。
3. **核心工作流埋点（已完成）**：`BetaValidationFacts` 已把采集关闭、未确认告知和指标存储异常收口为不影响业务的结果，并把主事件、任务完成与 Tool 结果在同一事务写入。Search/Solve 成功与耗时、命题完成/私题保存、Paper 版本生成/导出、Lesson 草稿生成/版本保存、私人资料题目确认导入均只从 current-owner 的服务端成功节点触发。Search 只有点击本次返回的真实题目才记录选择；Search/Solve 接受或拒绝只作用于本人已完成 run，并以最后一次决定为准。模型成本只从 FastAPI 直接持有可信 owner 的 provider 调用产生，且仅使用操作者显式配置的 OpenAI/DeepSeek 费率快照；隔离 Agent 内部调用在建立签名 owner 上下文前不归因，绝不使用占位 owner。浏览器、Agent 与模型不能提交 owner、可信结论、成本或成功状态。
4. **私有运营读数（已完成）**：`BetaValidationMetrics.private_operations_readout` 输出 1–90 天窗口内的最小化聚合快照、明确分子/分母、周激活 cohort 的 Week-1/Week-4 eligible 与 retained 数量，以及相对 20–30 位目标样本的 `empty/below_target/target_range/above_target` 状态。读数仅由本机操作者命令访问，不提供 HTTP、浏览器或 Agent 路由，不返回 owner/task 摘要或逐行事件，也不能创建缺失指标库或后台代操作。
5. **操作预演（已完成）**：本机命令在一次性临时 SQLite 中合成两位教师和四个无正文事件，依次验证未确认告知不能记录、本人导出隔离、只读运营汇总不含标识、90 天预览不删除、确认清理只删过期事件、退出只删本人，以及临时库在返回前删除。随后只读检查当前部署的 Beta 访问、采集开关、摘要密钥和既有指标库，输出布尔状态与稳定 blocker，不输出路径或密钥，也不自动启用采集或创建配置库。
6. **分阶段真实 Beta（未开始）**：先解决部署 preflight blocker，再邀请 20–30 位真实教师；记录支持请求、严重数学错误证据和主动商业信号，只修真实阻塞与可信问题。
7. **M13 Gate（延期、未通过）**：复核 A/B/C/Q、Gate P 和 Gate E，列明达标、未达标与样本限制。项目所有者明确接受“未验证”风险并授权先建设 M14 基础边界，但这不允许扩大用户、营销、宣称产品 Gate 通过，或用工程回归替代真实证据。

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
- `MATH_AI_BETA_VALIDATION_ENABLED` 默认关闭；打开后仍须由教师确认当前告知版本。摘要密钥在同一 Beta 周期必须稳定保存，不能在没有迁移方案时轮换，否则既有本人导出/删除关联会失效。
- 教师导出只包含本人最近 90 天的聚合值、分子、分母和确认时间，不返回事件清单、任务摘要或任何标识。明确退出会删除本人指标事件和确认记录；若重新加入，必须再次确认告知。
- M13 指标库不进入 M12 的 owner 内容备份，避免教师退出删除后的指标事件被旧内容备份恢复；指标库只受本切片的 90 天保留与退出删除规则管理。
- 操作者命令 `python -m app.modules.beta_validation.maintenance_cli preview` 默认只报告计数；仅 `prune --confirm` 删除早于 90 天且结构可验证的事件。它不接受浏览器/Agent 参数，不删除确认记录、教师内容、近期事件或无法分类记录。
- 私有运营读数从 `apps/api` 执行 `..\..\.venv\Scripts\python.exe -m app.modules.beta_validation.operations_cli --days 90`；命令以 SQLite 只读模式打开既有指标库，配置、密钥或存储未就绪时只返回稳定错误码。输出只有版本、窗口、事件/参与/激活计数、16 项聚合指标、可信分层错误率和周 cohort 分母，不含任何个人或任务标识。
- 操作预演从 `apps/api` 执行 `..\..\.venv\Scripts\python.exe -m app.modules.beta_validation.rehearsal_cli`。所有写操作仅发生在自动删除的合成临时库；当前部署只接受只读 schema/汇总检查。退出码 `0` 只表示合成检查和部署 preflight 同时就绪；退出码 `2` 表示合成检查通过但部署仍有 blocker。只有 `all_checks_passed=true` 且 `deployment.ready_for_invitation=true` 才具备邀请首批教师的技术配置条件，这仍不替代所有者的实际邀请决定。
- 只有在操作者打开独立采集开关且教师确认当前告知版本后，首批服务端节点才会产生事件；默认配置仍不采集。未来账户注销 Interface 必须复用同一退出删除语义；当前产品尚不存在账户注销。
- M13 不改变私题永久 owner-only、无后台内容权限、无公开发布路径和 Gate P 的既有规则。

## 当前验证

- `apps/api/tests/test_beta_validation_metrics.py`：6 项 synthetic 指标测试通过。
- `apps/api/tests/test_beta_validation_lifecycle.py`、`test_beta_validation_maintenance.py` 与 `test_beta_validation_server_facts.py`：15 项告知、隔离导出、退出删除、禁用后权利、保留清理、原子服务端事实和 Tool 结果测试通过。
- `apps/api/tests/test_beta_validation_rehearsal.py`：4 项临时库清理、生命周期预演、只读部署审核和输出脱敏测试通过。
- 新固定入口：`.\.venv\Scripts\python.exe -m pytest -c apps/api/pytest-m13.ini -q`，继承 M12 的全部固定安全/质量文件并追加 M13 指标契约、生命周期、服务端事实、明确选择/评价、成本归因、只读运营读数和操作预演；当前结果 **255 passed、1 skipped**。
- 完整 FastAPI：**685 passed、1 skipped**。
- Teacher Web：**105 passed**，类型检查与生产构建通过；设置面板覆盖默认关闭告知、明确加入、本人汇总导出和退出删除入口，Search/Solve 结果页提供非阻塞的明确评价。
- 自动测试使用临时 SQLite、合成 owner/task 标识和固定成本，不调用真实模型、不读取或写入真实教师数据。

M13 只有真实 Beta 达到 Gate 后才能标记完成；当前合成测试及继承回归不能代表真实教师指标。当前阶段状态为“真实验证延期”，不是“完成”。
