# ADR：PostgreSQL owner 迁移目标事务 adapter

日期：2026-09-11
状态：已采纳，M14 PostgreSQL tenant adapter 的合成验证切片

## 决策

新增 `PostgresOwnerMigrationAdapter`，直接满足 `OwnerMigrationExecutor` 已固定的
`transaction()` Interface。调用方无需知道 SQL、物化顺序或文件暂存细节；adapter
内部完成目标状态读取、数据库对象与文件流物化、目标写入、实际摘要重算、文件发布
映射及完成状态更新。

adapter 在构造时固定 source owner、target owner 与 target tenant；执行控制器传入的
目标绑定或计划指纹不一致时，在连接 PostgreSQL 或打开文件事务前失败关闭。数据库
对象和文件内容只能来自既有两个 Materializer，不能由 SQL adapter 自行选择源路径、
表、owner 或内容。

## 事务顺序

1. 打开可逆的文件 staging 事务，再打开 PostgreSQL 事务，并按目标绑定获取 transaction advisory lock；
2. 只在目标为空时物化并暂存全部文件，随后插入 run、对象和文件记录；
3. 从目标表重新读取对象/文件摘要并由 Executor 对照计划；
4. staging adapter 返回完整发布映射，SQL 更新每个发布 key 和 run 完成状态；
5. PostgreSQL 提交成功后，文件事务才结束其可逆阶段。

对账失败、发布集合缺失、短写、SQL 行数异常或数据库提交失败都会退出两个事务。
文件 staging Interface 必须保证：在 context manager 收到异常时，撤销本事务创建或
发布的对象；只有正常退出后才可丢弃回滚信息。

同一目标绑定的迁移由 PostgreSQL transaction advisory lock 串行化。锁键只从目标
绑定摘要派生，不把 owner 或 tenant 原文写入 SQL、日志或回执；不同计划不能并发观察
同一目标为空并同时开始写入。

## 当前限制

- 当前 PostgreSQL 行为只通过合成连接验证，没有连接、建表或写入真实 PostgreSQL。
- 文件 staging 只有合成测试 Adapter；生产对象存储 Adapter 尚未实现。
- 普通异常路径的提交前回滚已验证，但进程在文件发布与数据库提交之间崩溃时仍需
  后续恢复器根据 `in_progress`、staged/published key 和内容摘要完成补偿。
- 没有 HTTP、浏览器、Agent、模型或自动运行入口；没有迁移任何真实用户数据。

因此本切片证明具体 PostgreSQL SQL adapter 与既有 Executor Interface 可以组合，
不代表真实迁移、跨系统崩溃恢复、IDOR/tenant isolation 或 M14 Gate 已通过。
