# ADR：M14 PostgreSQL 正式身份适配边界

日期：2026-09-10
状态：M14 PostgreSQL tenant adapter 第一段；身份 schema 与运行 adapter 已实现，私人内容迁移尚未开始。

## 背景

现有 `AccountIdentity` 已把账号、personal tenant、稳定内容 owner 与会话分开，但持久实现仍是 SQLite 过渡 adapter。SQLite 可以证明业务 Interface 和本地流程，不能承担生产多进程一致性、受控 schema 部署或后续 tenant 数据隔离。直接在服务启动时创建 PostgreSQL 表或静默搬运本地记录，会把发布、迁移和回滚混进登录请求，是不可接受的边界。

## 决策

1. `AccountIdentity`、`AccountRegistration` 与 `AccountAdministration` 的业务 Interface 保持不变。HTTP、Teacher Web、Agent 与模型不接触 DSN、SQL、schema 或迁移参数。
2. 新增 `PostgresAccountIdentity` adapter。账号、tenant、membership 和会话位于固定 `math_teacher_identity` schema；密码继续使用 scrypt，session token 仍只保存 SHA-256 摘要。网页注册的四项写入使用同一事务，首个 session 写入失败不会遗留半创建账号。
3. 部署通过 `production_identity_provider=postgresql` 显式选择 adapter，DSN 使用 `SecretStr` 配置。`environment=production` 若仍选择 SQLite、PostgreSQL DSN 为空、驱动不可用、连接失败或 schema 不匹配，登录与 `/ready` 失败关闭。
4. adapter 构造与应用启动绝不创建或升级 schema。独立 `PostgresAccountIdentitySchema` 提供只读 `preview` 和显式 `apply`：apply 必须同时携带确认和本次计划指纹，目标出现未知 schema 状态时拒绝执行，并使用事务级 advisory lock 串行化部署。
5. 就绪检查不仅核对版本标记，还对预期表列执行无数据读取；伪造版本标记或缺列不能通过。
6. 旧 SQLite 操作者命令在 PostgreSQL backend 下失败关闭，避免部署人员误改旁边的过渡库。PostgreSQL schema CLI 只输出状态、版本、语句数量、计划指纹和是否改变，不输出 DSN、账号或内容。
7. 当前切片不迁移任何账号、会话或私人内容。后续必须以逐对象只读盘点、源/目标指纹、明确确认、对账和可证明回滚为单位继续；会话默认不跨存储迁移，切换后应重新登录。

## 操作者入口

在私有部署环境配置 PostgreSQL backend 与 DSN 后：

```powershell
python -m app.modules.account_identity.postgres_schema_cli preview
python -m app.modules.account_identity.postgres_schema_cli apply --expected-fingerprint <preview 返回值> --confirm
```

第一次命令只读。第二次只有在当前代码计划指纹仍与预演一致、目标为空或已经是同一版本时才继续。不得把 DSN、命令输出中的私有部署信息或数据库导出提交到 Git。

## 当前未完成

- 尚未对真实 PostgreSQL 实例执行集成 Gate；自动测试使用可替换连接替身验证无隐式连接、预演/确认、schema 形状、身份三标识和 token 摘要。
- 登录防护与生命周期审计仍有 SQLite 过渡实现；生产外部分布式限流、集中审计和密钥管理仍未部署。
- 私题、私人资料、题目图片、试卷、教案、教师记忆、后台任务和文件对象尚未迁移到 tenant-aware PostgreSQL/对象存储。
- 组织角色、RBAC、邮箱验证、找回密码、MFA、Entitlement 和支付仍不在本切片内。

因此本 ADR 只证明正式身份 adapter 可替换及其部署边界，不代表 PostgreSQL tenant 迁移完成，也不代表产品已具备生产多租户或商业发布条件。
