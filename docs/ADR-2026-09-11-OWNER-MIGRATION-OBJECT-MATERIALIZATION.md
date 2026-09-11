# ADR：owner 迁移对象只读物化

日期：2026-09-11
状态：已采纳，M14 PostgreSQL tenant adapter 的内部存储切片

## 背景

`OwnerMigrationPlanner` 只输出摘要，不携带源主键、owner、tenant 或正文；
`OwnerMigrationExecutor` 只定义确认、幂等、事务和对账顺序。目标事务 adapter
最终需要真实行内容，但如果直接让 adapter 自由读取 SQLite，它会同时拥有计划解释、
owner 选择和源数据访问三项职责，难以证明只搬计划内对象。

## 决策

新增内部 `OwnerMigrationObjectMaterializer` Interface。它只接收已生成的迁移计划、
显式源 owner 和目标 owner/tenant，并通过固定 ownership 查询目录只读重开源 SQLite：

1. 在打开源库前重新计算完整计划指纹和目标绑定指纹；
2. 按计划表顺序重建当前源 owner 的对象集合与依赖摘要；
3. 对每个计划对象重新读取唯一完整行，并用与 Planner 共用的规范化摘要算法核对；
4. 只在内存中产生目标 adapter 所需的 JSON 载荷，`owner_id` 和已有的
   `tenant_id` 列改写为目标绑定；BLOB 使用明确的 Base64 包装；
5. 表、对象、依赖、行内容、数量或绑定有任何变化都失败关闭。

共享的 `fingerprints.py` 是 Planner 与 Materializer 之间的小型内部 seam，避免两处
摘要算法逐渐分叉。物化结果类型关闭 `repr`，不从包入口导出，也没有 HTTP、浏览器、
Agent、模型或 CLI 入口。错误只返回稳定代码，不拼接 owner、路径、主键或正文。

## 安全与事务边界

- 源 SQLite 使用 `mode=ro` 和 `PRAGMA query_only=ON`；物化不连接 PostgreSQL，
  不创建、更新、移动或删除数据库记录与文件。
- 计划完整性与目标绑定在任何源连接前校验，错误目标不能触发源读取。
- 其他 owner 的行用于验证 owner 关系，但绝不进入载荷；继承对象必须保持计划中的
  父依赖摘要。
- 私密载荷只允许交给后续受控目标事务 adapter，不能写入日志、操作回执或计划报告。
- 文件流由后续 `OwnerMigrationSourceFiles` / `OwnerMigrationFileMaterializer`
  独立物化。数据库对象与文件的提交/发布仍必须由后续具体事务 adapter 明确定义，
  不能在此处假装跨系统原子性。

## 结果与限制

该 Interface 把“只读源对象解释”从 PostgreSQL 写入实现中分离出来，使目标 adapter
只需消费已经逐对象核对、目标绑定的载荷。后续具体 SQL adapter 已在合成连接中消费
这些载荷；后续已完成已提交文件发布缺失的合成前向补偿，当前仍没有生产文件
staging/recovery、真实 PostgreSQL 集成 Gate 或真实数据迁移。
