# M14 Commercial Foundation

更新日期：2026-09-09。

项目所有者因暂时缺少足够真实教师样本，明确决定暂停 M13 真实 Beta，不把合成测试误记为产品 Gate 通过，并授权进入 M14。M13 状态因此是“切片 1–5 完成、真实验证延期、Gate 未通过”，不是“验证成功”。M14 当前进行中，只建设商业化前必须成立的生产边界；支付、组织和学校能力不能反向定义身份或数据所有权。

## 1. 不可混用的三个标识

- `account_id`：登录凭据对应的账号主体，只由账号模块创建和解析。
- `tenant_id`：授权与未来数据隔离边界。当前只支持一账号一个个人 tenant，不宣称已经具备组织多租户。
- `owner_id`：现有私人内容的稳定所有者标识。业务模块继续只接收服务端解析出的 owner；浏览器、Agent、模型、请求正文和查询参数都不能选择它。

三者必须分别持久化、分别测试，不允许因为当前个人账号是一对一关系而合并字段。账号停用、tenant 成员关系和内容归属也必须独立表达。

## 2. 身份 Interface 与运行模式

`AccountIdentity` 是业务与传输层依赖的正式身份深模块 Interface，只负责验证凭据、解析不透明会话和撤销会话。独立的 `AccountAdministration` 只供本机操作者创建、停用账号和重置密码。HTTP 只开放登录、会话状态和退出；没有公开注册或由 Agent 创建账号的入口。

运行模式互斥：

1. `production_identity_enabled=true`：只接受正式账号会话。
2. `beta_access_enabled=true`：只接受 M12 临时封闭测试会话。
3. 两者都关闭：固定 `owner_teacher`，仅供本地开发。
4. 两者同时开启：服务端 fail closed，返回 `IDENTITY_MODE_CONFLICT`。

任何账号模式都停用缺少安全 owner 契约的旧版单用户接口。能力门禁使用全局 `WorkbenchCapability`，不再由 Beta 模块拥有业务能力定义。

## 3. 已实现切片

### 3.1 生产身份基础

- 独立 `AccountIdentity` Protocol，并提供内存测试 adapter 与 SQLite 过渡 adapter。
- 账号、个人 tenant、成员关系、owner 和会话分别建模；当前角色只有 `personal_owner`。
- 密码使用带随机 salt 的 scrypt；会话 token 只保存 SHA-256 摘要，支持到期和撤销。
- 登录失败统一为“邮箱或密码无效”，公开响应不返回 account、tenant 或 owner 内部标识。
- Cookie 为 HttpOnly、SameSite Strict；正式配置默认要求 Secure。
- 正式身份功能默认关闭；关闭时不创建身份数据库。
- 生产身份和 Beta 身份不能同时启用；生产模式中的旧单用户接口统一拒绝。
- `/ready` 只检查当前模式实际使用的身份 adapter；纯本地模式不创建无用身份库，模式冲突明确返回降级状态。
- 现有私人内容仍以 `owner_id` 隔离，正式会话只把服务端解析出的 owner 交给业务模块。

当前 SQLite adapter 只是验证 Interface 和迁移边界，不是生产数据库声明。当前切片没有创建真实账号、迁移真实内容或启用正式登录。

### 3.2 账号生命周期第一段

- 新增独立的 `AccountAdministration` Interface。停用账号和重置密码只允许本机操作者调用，没有 HTTP、浏览器或 Agent 入口。
- 创建、停用和重置都要求操作者显式传入 `--confirm`；密码只通过交互式隐藏输入读取两次，不接受命令行密码参数，也不写入输出。
- 停用账号与重置密码在一个事务中撤销该账号全部未撤销会话；旧密码、旧会话都不能继续使用。
- 操作者回执只包含动作、是否改变和撤销会话数，不返回邮箱、account、tenant、owner、密码或 token。
- 正式会话维护默认只预览，只有 `session-prune --confirm` 才删除已过期或已退出会话；有效会话和无法安全分类的异常记录保留。
- 维护工具只接受配置中的既有正式身份库，先只读核对精确 schema；缺库、错误库、符号链接/reparse 或错误运行模式均 fail closed，不创建或修补目标库。

操作者入口（需先显式启用正式身份并关闭 Closed Beta）：

```powershell
python -m app.modules.account_identity.operator_cli provision --email teacher@example.com --display-label "教师" --operator local-admin --confirm
python -m app.modules.account_identity.operator_cli disable --email teacher@example.com --operator local-admin --confirm
python -m app.modules.account_identity.operator_cli reset-password --email teacher@example.com --operator local-admin --confirm
python -m app.modules.account_identity.operator_cli session-preview
python -m app.modules.account_identity.operator_cli session-prune --operator local-admin --confirm
python -m app.modules.account_identity.operator_cli audit-summary
python -m app.modules.account_identity.operator_cli keyring-status
```

命令需从 `apps/api` 可导入的 Python 环境运行。示例中的 `--operator` 标签由部署人员替换，且只作为摘要化审计线索，不等于已认证管理员身份。这里的 SQLite 操作者流程仍是过渡验证，不是面向真实生产环境的账号后台。

### 3.3 登录防护与会话轮换

- 独立 `AccountLoginProtection` 在密码验证前按账号线索和服务端连接来源双重限流；未知账号与既有账号使用相同错误响应。
- principal/network 在写入独立安全库前使用部署密钥 HMAC；库内只有摘要、`succeeded`/`failed`/`throttled` 和服务端时间，不含邮箱、原始 IP、密码、token 或正文。
- 默认窗口 15 分钟、账号线索 5 次、网络来源 30 次；安全事实默认保留 168 小时。阈值可由部署配置收紧，但不能由浏览器或 Agent 选择。
- 至少 32 字符的独立登录防护密钥是正式登录和 `/ready` 的必要条件；缺失或安全存储故障时 fail closed。
- 只使用连接层来源，忽略不可信 `X-Forwarded-For`；生产边缘仍必须提供可信代理链、外层限流和分布式计数。
- 成功重登会撤销当前浏览器旧 token；安全事实无法写入时撤销刚签发的新 token，不把未审计登录放行。
- MFA 当前明确未实现。个人商业登录、未来组织特权角色、恢复码和 step-up 的固定决策见 [`ADR-2026-09-09-PRODUCTION-LOGIN-SECURITY.md`](ADR-2026-09-09-PRODUCTION-LOGIN-SECURITY.md)。

### 3.4 操作者生命周期审计

- 独立 `AccountLifecycleAudit` 只审计创建、停用、密码重置和失效会话清理，不混入登录限流、产品指标或教师内容。
- 每个写操作先记录 `started`，审计密钥、路径、schema 或存储不可用时失败关闭；随后只记录成功/失败、是否改变与受影响会话数。
- 操作者和目标账号只保存独立密钥 HMAC，不保存邮箱、标签、密码、token 或任何 account/tenant/owner ID；`audit-summary` 只返回动作与状态计数。
- 当前两个 SQLite adapter 不具备跨库原子事务。业务成功后异常中断会留下 `started` 供核对，不自动重试、不伪装结论；`--operator` 也只是本机审计线索，不是管理员认证。
- 当前不自动清理或导出生命周期审计。正式保留、受控调查和不可抵赖存储必须后续单独实现；详见 [`ADR-2026-09-09-ACCOUNT-LIFECYCLE-AUDIT.md`](ADR-2026-09-09-ACCOUNT-LIFECYCLE-AUDIT.md)。

### 3.5 摘要密钥版本与轮换

- `VersionedHmacKeyRing` 统一承担版本格式、当前写入、旧密钥候选、旧版无版本摘要兼容与配置校验；登录防护和生命周期审计仍使用互不复用的两套密钥环。
- 新摘要记录 key ID 和非敏感密钥指纹，不记录密钥。新事件只用当前密钥；既有摘要不批量重写，也不为迁移反查邮箱、IP 或操作者标签。
- 登录轮换会跨当前/旧密钥统计失败。保留期内若版本化事件所需密钥被提前移除或同一 ID 被错误复用，防护和 `/ready` 失败关闭，不能靠换钥清零限流。
- 旧密钥配置最多三个。`keyring-status` 只验证配置并输出当前 ID/旧密钥数量，不读取或创建数据库。首次升级、轮换、保留和退出顺序见 [`ADR-2026-09-09-HMAC-KEY-ROTATION.md`](ADR-2026-09-09-HMAC-KEY-ROTATION.md)。

## 4. 后续切片顺序

1. **账号生命周期加固（进行中）**：操作者创建/停用、密码重置、失效会话预览/确认清理、登录双范围限流、摘要化登录安全事实、当前浏览器会话轮换、MFA 决策、操作者生命周期审计和摘要密钥轮换已实现；下一段补可信生产代理与分布式限流 adapter。
2. **PostgreSQL tenant adapter**：在不改变业务 Interface 的前提下替换身份和 owner-aware 存储；提供逐对象盘点、迁移、对账、回滚和 IDOR/tenant isolation 测试。
3. **对象存储与持久任务**：原文件、导出和后台任务获得明确 owner/tenant key、保留期、幂等和恢复语义。
4. **Entitlement**：只表达账号可用能力，不替代身份、owner 权利或内容可信门禁。
5. **订单、订阅、支付与退款**：最后接入；要求幂等、Webhook 验签、状态机、对账和退款恢复全部独立验证。
6. **M14 Gate**：认证、RBAC/IDOR、tenant 隔离、私题永久隔离、恢复与商业状态机证据齐全后才可进入 M15。

## 5. 明确未完成

- PostgreSQL、云对象存储、持久队列、多进程会话一致性和生产灾备。
- 公开注册、邮箱验证、自助找回密码、MFA、设备管理、已认证操作者/RBAC、不可抵赖审计、集中式密钥管理、生产级分布式限流与告警。
- 除 `personal_owner` 外的角色、组织 tenant、成员邀请、学生和学校后台。
- Entitlement、订单、订阅、支付、Webhook 和退款。
- M13 的真实教师价值、重复使用、错误率与付费意愿 Gate。

因此当前实现可作为 M14 身份边界的工程基础，但不能对外称为生产认证或商业发布就绪。

## 6. 验证入口

- M14 固定回归：`python -m pytest -c apps/api/pytest-m14.ini -q`
- 完整 API：`python -m pytest apps/api/tests -q`
- Teacher Web：`npm --prefix apps/teacher-web test`、类型检查与生产构建
- Agent：`npm --prefix apps/agent test`、类型检查与生产构建

最终测试数字以 `PROJECT-STATUS.md` 和 `REPOSITORY-SYNC.md` 的同一提交快照为准。
