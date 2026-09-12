# ADR：正式会话 IDOR 与 tenant 隔离合成 Gate

日期：2026-09-12
状态：已采纳，M14 PostgreSQL tenant adapter 的合成隔离切片

## 决策

增加固定测试 `test_m14_tenant_isolation_gate.py`，把正式身份与当前 owner-scoped
业务 Interface 组合验证。Gate 不新增浏览器参数、运行时权限服务或新的 owner 来源；
`account_id`、`tenant_id` 与 `owner_id` 仍只能由服务端正式会话解析。

Gate 同时固定两层证据：

1. 枚举 FastAPI 的有效路由依赖图。所有使用当前教师身份且不属于已停用旧工作流的
   路由，都不得把 `account_id`、`tenant_id` 或 `owner_id` 暴露为 path、query、header、
   cookie 或请求体字段。
2. 使用两个独立的正式账号和真实 HttpOnly 会话 Cookie，访问同一组合成教师记忆、
   私有资料与个人题库分类。列表必须只返回当前 owner，对另一 owner 的已知对象 ID
   必须返回 404，匿名访问必须返回 401，伪造归属的写请求必须在存储变化前返回 422。

公开响应还必须继续隐藏 account、tenant 与 owner 内部标识。路由依赖覆盖不能替代
业务对象查询中的 owner 条件，业务对象测试也不能替代正式 Cookie 到 owner 的解析；
两层必须同时保留。

## 当前限制

- 测试只使用内存正式身份 adapter 和临时 SQLite 私有存储，不连接真实 PostgreSQL。
- 当前只支持 `personal_owner`，没有组织成员、共享资源、管理员或跨 tenant 授权模型。
- 该 Gate 是当前个人工作台的合成 IDOR/tenant 隔离证据，不代表真实多租户部署 Gate、
  渗透测试、生产 RBAC 或 M14 总 Gate 已通过。
- 没有读取、修改、迁移或删除真实用户数据。

后续对象存储和持久任务必须沿用同一服务端 owner/tenant 绑定，并加入对象 key、任务 ID、
下载与恢复路径的跨 owner 自动测试；不能靠 UI 隐藏实现隔离。
