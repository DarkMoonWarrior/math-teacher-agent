# M11 Teacher Memory 固定评测

评测日期：2026-09-01

评测集：`data/test-fixtures/teacher-memory/eval-cases.json`

## 范围

本评测只使用项目自建 synthetic owner、结构化偏好和临时 SQLite 数据库，不读取、修改或导出真实教师账户数据。26 个固定场景覆盖：

- 五类 allow-listed 显式偏好、非法值与乐观版本冲突；
- `planning_defaults` 最小只读视图、任务显式字段优先、缺失字段透明应用；
- 自动学习关闭、三次不同保存版本阈值、重复证据幂等和提议不自动晋升；
- 接受、拒绝、修正、拒绝后冷却期、跨 owner 提议处理和反馈隔离；
- profile/export 不含 owner、证据版本标识或题目/解析/教案/资料正文；
- 固定口令删除、全量 owner 数据清理、其他 owner 不受影响、删除后版本单调递增；
- 浏览器不能伪造 owner/证据，Agent allowlist 不含记忆写入、导出或删除工具。

## 结果

执行：`.venv\\Scripts\\python.exe -m pytest apps/api/tests/test_teacher_memory_eval.py -q -s`

- 场景：26
- `unexpected_outcome`：0
- `invalid_preference_accepted`：0
- `cross_owner_leak`：0
- `stale_write_accepted`：0
- `planning_default_drift`：0
- `silent_inference`：0
- `proposal_threshold_bypass`：0
- `duplicate_signal_counted`：0
- `feedback_drift`：0
- `retention_bypass`：0
- `private_content_exposed`：0
- `agent_privilege_escalation`：0

结论：**26 个场景、12 类违规全部为 0。**

## 边界

该评测证明当前本地 current-teacher seam 的业务隔离和失败关闭行为，不代表生产认证、云 tenant isolation、备份恢复、合规审计或真实教师 Beta 已完成；这些属于 M12/M13。
