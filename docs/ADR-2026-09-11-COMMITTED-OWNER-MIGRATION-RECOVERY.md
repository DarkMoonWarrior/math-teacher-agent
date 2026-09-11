# ADR：已提交 owner 迁移的前向补偿恢复

日期：2026-09-11
状态：已采纳，M14 PostgreSQL tenant adapter 的合成恢复切片

## 决策

新增操作者专用 `PostgresOwnerMigrationRecovery` 深模块，只暴露 `preview()` 与
`recover()` 两个方法。它只处理 PostgreSQL run 已提交为 `complete`、数据库已经保存
预期 published key，但外部文件发布结果缺失的窗口；不把浏览器、Agent、模型或普通
应用启动接到恢复路径。

预演和恢复都按 target binding 获取与迁移执行相同的 PostgreSQL transaction advisory
lock，并重新读取 run 与全部文件记录。每个目标文件只能进入三种状态：

- published 内容与计划 SHA-256/长度一致：`healthy`；
- published 缺失且 staged 内容一致：`repairable`；
- published 或 staged 内容冲突，或者 staged 内容缺失：`blocked`。

恢复计划只公开状态、数量、稳定问题码和摘要。恢复指纹绑定 plan、target binding、对象
摘要、内容摘要、长度、状态，以及 staging/published key 的单独摘要；不公开原始 owner、
tenant、路径、storage key、文件名或内容。

## 恢复语义

`recover()` 必须同时收到布尔确认、固定确认短语和最新预演指纹。确认失败在连接数据库
或访问文件存储前拒绝；预演后数据库记录、storage key 或文件状态变化都会使旧指纹失效。

恢复只执行前向补偿：将仍匹配预期摘要的 staged 对象幂等、原子地恢复到数据库已经记录
的 published key，随后重新核对全部 published 内容。它不会覆盖冲突内容，不会删除文件，
不会回滚已提交数据库记录，也不会猜测缺失的 staged 内容。重复恢复健康目标返回
`already_healthy`，不重复写入。

多文件恢复不是伪事务：如果部分对象已原子发布、后续对象失败，已完成的前向修复保留。
重新预演会得到新指纹并只列出剩余可修复对象，旧确认不能继续使用。

`OwnerMigrationRecoveryFiles` Interface 要求具体 Adapter 在 `restore()` 内再次验证源内容
并原子发布；目标已经存在且匹配时必须幂等，存在冲突时必须失败关闭。

## 当前限制

- PostgreSQL 与文件存储只使用合成 Adapter 验证，没有连接真实 PostgreSQL 或对象存储。
- 尚无生产 `OwnerMigrationRecoveryFiles` Adapter 或操作者 CLI，因此不能执行真实恢复。
- 只修复数据库已提交为 `complete` 且 staging 仍存在的缺失发布对象；无 staging、内容冲突、
  未提交 run、数据库对象损坏和灾难级恢复仍需人工阻断与后续运维设计。
- 没有迁移、复制、覆盖或删除任何真实用户数据。

因此本切片证明已提交跨系统窗口可被安全识别并前向补偿，不代表真实 PostgreSQL、生产
对象存储、IDOR/tenant isolation 或 M14 Gate 已通过。
