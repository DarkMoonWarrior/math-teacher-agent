# ADR：教师与模块绑定的模型会话

日期：2026-09-04。状态：Accepted（M12 隔离缺陷修复，不新增产品权限）。

## 问题

Search/Solve 的进程内任务记录此前只有 run ID，没有 owner。真实双用户 Cookie 测试复现另一教师能读取、回放、取消或恢复任务。另一个独立问题是浏览器提交的 session ID 直接到达 Runtime；两个账号提交相同 ID 时可能复用模型上下文。不可猜测的 ID 不能代替所有权校验。

## 决策

1. Search/Solve 在创建同步/流式任务记录时绑定服务端 current teacher；读取、回放、取消和恢复先核对 owner，其他教师与不存在的记录统一返回 404。无 owner 的旧记录不被调用者认领。Runtime 返回冲突 run ID 时不得覆盖另一 owner 的记录。
2. `TeacherAgentSessions.resolve(owner_id, workflow, client_session_id)` 是浏览器会话别名到模型会话的唯一转换接口。四个入口 Search、Solve、命题（含后台任务）、私人资料检索都在调用 Runtime 前使用它。
3. 未签名浏览器编号只是别名：以进程私有随机密钥对 owner、模块和别名做 HMAC，产生不含明文 owner 的名字。返回的签名编号只能在原 owner、原模块重用；篡改、跨 owner、跨模块的编号在模型调用前返回 404。
4. 内部 Runtime/Tool 接口和可信校验不变；Agent 不取得数据库、owner 选择、保存或删除权限。

## 后果与限制

- 正常同用户同模块连续任务仍可复用模型上下文；不同账号或不同模块不共用。
- 密钥只在当前 API 进程内存在；重启后旧签名编号失效，界面提示清空当前任务后重试。已经保存的私题、试卷、教案不受影响。
- 当前部署要求单 API 进程（单 worker）；进程内任务注册表本来也不支持多 worker 共享。不能把它宣传为分布式会话或跨重启任务恢复。将来采用持久任务/多 worker 时须明确共享密钥治理、过期和撤销策略，另行决策，不静默引入固定密钥。
- 这里不是模型服务端会话清理策略，也不删除登录会话或已保存内容。
- 相比把 owner 文本拼在 ID 前面，签名方案避免 owner 明文泄露和拿到其他模块编号后直接重用；相比增加永久会话数据库，本修复不引入新的持久化正文或迁移。

## 证据

`test_beta_task_isolation.py` 的真实 Cookie 与合成 Runtime 测试先复现 14 个跨账号任务操作及 2 个别名共用失败，再验证修复；后续增加签名重放、冲突、无 owner 记录和其他 Agent 入口。`test_agent_sessions.py` 验证跨模块、重启、Unicode 篡改和同作用域复用。固定入口见 [M12 Gate 记录](M12-GATE-REVIEW.md)。
