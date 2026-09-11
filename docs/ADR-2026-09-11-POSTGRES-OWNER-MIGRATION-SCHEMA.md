# ADR：M14 PostgreSQL owner 迁移落地区域

日期：2026-09-11。

状态：M14 PostgreSQL tenant adapter 第二段的第五切片；固定迁移落地区域及其部署门禁已实现，后续数据库对象只读物化已建立，具体 PostgreSQL 目标事务 adapter 尚未实现。

## 决策

1. owner 内容迁移使用独立的 `math_teacher_content_migration` schema。它只保存一次迁移的目标绑定、状态、对象暂存记录和文件发布记录，不是面向业务请求的正式内容 schema。
2. schema 版本固定为 `m14.owner_migration.v1`。部署入口只接受注入连接或独立的 `production_owner_migration_postgres_dsn`，不得复用运行时身份 DSN；它不接 HTTP、浏览器、Agent 或模型，构造对象和应用启动均不得连接数据库或建表。
3. 操作者必须先只读 `preview`，再把返回的完整计划指纹和明确布尔确认提交给 `apply`。确认缺失、代码中的 SQL 计划变化、未知既有 schema、连接失败或列形状异常全部失败关闭。
4. 部署在 PostgreSQL 事务 advisory lock 内串行执行；同一版本和预期形状已经存在时幂等返回，不重复写入。
5. 迁移 run 明确绑定目标 tenant、目标 owner 和执行器的目标绑定指纹。对象记录保存依赖摘要、源记录指纹和待写入 JSON；文件记录保存源校验和、长度、暂存 key 与发布 key。落地区域不保存 `source_owner_id`，避免把旧身份作为新的授权事实。
6. 对外错误只有稳定代码，不回显 DSN、凭据、SQL 异常、owner、tenant、路径、主键、文件名或正文。

操作者从可导入 `apps/api` 的 Python 环境运行：

```powershell
python -m app.modules.tenant_migration.postgres_schema_cli preview
python -m app.modules.tenant_migration.postgres_schema_cli apply --expected-fingerprint <preview-fingerprint> --confirm
```

`apply` 未明确确认时在读取私密配置前直接拒绝。命令只输出动作、状态、schema 版本、语句数量、计划指纹和是否改变，不输出 DSN 或身份信息。

## 为什么单独建落地区域

执行控制器需要一个可审计、可幂等检查、可在提交前对账的位置，但当前 33 张业务表仍是 SQLite 时代的不同领域模型。直接把迁移日志混入正式业务表，会在具体映射、RLS 和恢复策略尚未完成时扩大运行时信任面。独立落地区域把“部署迁移基础设施”和“改变教师内容事实”分开，使后续 adapter 可以先暂存、核对，再在明确事务边界中发布。

## 明确未完成

- 本切片没有连接真实 PostgreSQL，没有创建 schema，也没有读取、迁移、复制、更新或删除任何真实用户数据。
- 尚无把 33 张源表映射到正式 tenant-aware 业务表的具体 adapter，也没有文件复制或对象存储发布实现。
- 尚未建立运行时业务表的 RLS、RBAC/IDOR 和 tenant isolation Gate。该迁移 schema 是操作者专用区域，不能被业务 API 当作内容查询来源。
- 尚未实现提交后补偿恢复、真实 PostgreSQL 故障注入和生产灾备。

数据库对象和文件流只读物化已经实现；下一切片实现具体 PostgreSQL 目标事务 adapter。它必须复用既有 `OwnerMigrationExecutor`，并证明对象暂存、文件暂存、目标摘要对账、原子完成标记和失败回滚。完成该 adapter 仍不等于真实迁移 Gate 通过；真实 PostgreSQL、IDOR、tenant isolation 与补偿恢复必须单独验证。
