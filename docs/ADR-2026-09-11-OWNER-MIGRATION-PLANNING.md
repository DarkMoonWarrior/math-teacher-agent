# ADR：M14 owner 逐对象迁移计划

日期：2026-09-11
状态：M14 PostgreSQL tenant adapter 第二段的第三切片；只读计划已实现，迁移执行尚未开始。

## 决策

在任何 owner 内容迁移写入之前，必须由独立 `OwnerMigrationPlanner` 生成逐对象计划。Planner 只接受固定业务存储目录、固定 ownership 查询图、源 owner、目标 owner/tenant，以及操作者先前取得的 owner 数据清点和文件引用对账指纹。它不接 HTTP、浏览器、Agent 或模型，也不连接目标 PostgreSQL、不复制文件、不写入计划或源存储。

返回计划包含：

- 每张表按依赖顺序排列的对象摘要、绑定完整源记录的指纹和父对象依赖摘要；
- 每个文件域的文件对象摘要；
- 清点、文件对账和目标绑定指纹；
- 绑定上述全部事实的计划指纹；
- 固定的 `execution_allowed=false`，防止把预演结果误作写入授权。

报告不返回源/目标 owner、tenant、数据库路径、表主键、文件名或正文。对象摘要只用于同一次明确绑定下的集合核对，不能反查内容，也不是迁移确认令牌。

## 失败关闭条件

- 清点或文件对账指纹与操作者提交的预期值不一致；
- 计划扫描前后任一指纹变化；
- 旧无 owner 数据、未知 schema、缺失/孤儿/跨 owner 文件等既有阻塞仍存在；
- 子记录没有可解析父 owner、多个 owner 不一致，或父对象没有进入同一计划；
- 对象键不完整、重复，固定查询结果形状异常，或计划目录未覆盖全部非旧版表；
- 文件对象数量与已通过的文件引用对账不一致；
- 源 owner 与目标 owner 相同，或任一绑定/指纹格式无效。

Planner 在对象扫描后重新执行两份只读证据并再次扫描完整对象图；对象身份、记录内容、依赖或文件引用发生并发变化即拒绝返回计划。未来执行器仍必须在目标事务和文件复制边界内再次核对计划、源快照与幂等状态，不能只信任本报告。

## 操作者入口

先分别运行清点和文件对账命令取得指纹，再执行：

```powershell
python -m app.modules.tenant_migration.planning_cli `
  --source-owner-id owner_source `
  --target-owner-id owner_target `
  --target-tenant-id tenant_target `
  --inventory-fingerprint <64位清点指纹> `
  --file-reconciliation-fingerprint <64位文件对账指纹>
```

失败只输出稳定的 `OWNER_MIGRATION_PLAN_UNAVAILABLE`，避免把 owner、路径或对象信息带入日志。该命令无需确认，因为它严格只读且不能执行迁移。

## 未完成

- 没有连接或部署真实 PostgreSQL 内容 schema；
- 没有写入、复制、删除、重命名或清理任何真实记录和文件；
- 没有实现幂等执行、双写冻结、目标逐对象对账、失败补偿或回滚；
- 没有通过真实 PostgreSQL、IDOR 和 tenant isolation Gate。

下一切片只能在本计划边界之上设计“预演 → 精确计划确认 → 幂等执行 → 源/目标对账 → 可恢复回滚”，不能让浏览器或 Agent 获得迁移能力。
