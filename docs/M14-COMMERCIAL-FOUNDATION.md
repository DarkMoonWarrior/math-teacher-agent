# M14 Commercial Foundation

更新日期：2026-09-11。

项目所有者因暂时缺少足够真实教师样本，明确决定暂停 M13 真实 Beta，不把合成测试误记为产品 Gate 通过，并授权进入 M14。M13 状态因此是“切片 1–5 完成、真实验证延期、Gate 未通过”，不是“验证成功”。M14 当前进行中，只建设商业化前必须成立的生产边界；支付、组织和学校能力不能反向定义身份或数据所有权。

## 1. 不可混用的三个标识

- `account_id`：登录凭据对应的账号主体，只由账号模块创建和解析。
- `tenant_id`：授权与未来数据隔离边界。当前只支持一账号一个个人 tenant，不宣称已经具备组织多租户。
- `owner_id`：现有私人内容的稳定所有者标识。业务模块继续只接收服务端解析出的 owner；浏览器、Agent、模型、请求正文和查询参数都不能选择它。

三者必须分别持久化、分别测试，不允许因为当前个人账号是一对一关系而合并字段。账号停用、tenant 成员关系和内容归属也必须独立表达。

## 2. 身份 Interface 与运行模式

`AccountIdentity` 是业务与传输层依赖的正式身份深模块 Interface，只负责验证凭据、解析不透明会话和撤销会话。独立的 `AccountRegistration` 只创建个人账号并签发正式会话；独立的 `AccountAdministration` 供本机操作者执行创建、停用账号和重置密码。HTTP 开放登录、会话状态、退出，以及由独立部署开关控制的个人账号注册；Agent 没有创建账号的入口。

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

### 3.1.1 网页个人账号注册

- 项目所有者于 2026-09-10 明确将正式登录页与网页注册纳入 M14。Teacher Web 会先探测正式会话；正式身份未启用时才回退到现有封闭测试入口。
- `AccountRegistration` 的浏览器契约只有邮箱、显示名称、密码与密码确认；额外的 owner、tenant、role、capabilities 字段会被拒绝。
- 账号、个人 tenant、稳定 owner、`personal_owner` 角色和工作台能力由服务端创建。注册成功自动签发与登录相同的 HttpOnly 会话，公开响应不含内部身份 ID。
- `production_self_registration_enabled` 与正式身份总开关分离且默认关闭；仅在正式身份开启、Beta 关闭时生效，状态接口只暴露布尔可用性。
- 注册复用正式登录的可信网络来源和双范围防护；身份或防护存储不可用时失败关闭。Agent、模型与内部 Tool 均无注册入口。
- 该切片没有静默迁移当前 `owner_teacher` 或 Beta owner 数据。切换运行模式前仍需逐对象映射、预览、对账与回滚，避免已有私人内容在新账号下不可见。

具体决策与未完成条件见 [`ADR-2026-09-10-WEB-ACCOUNT-REGISTRATION.md`](ADR-2026-09-10-WEB-ACCOUNT-REGISTRATION.md)。

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

### 3.6 可信代理与分布式限流 adapter

- 独立 `LoginNetworkOrigin` 解析登录来源。本地 `direct` 忽略所有转发头；生产 `trusted_proxy` 只信任显式 CIDR 白名单中的直接 peer，并只接受边缘覆盖后的单一规范 `X-Forwarded-For` IP。
- 独立 `HttpDistributedAccountLoginProtection` 在本地把邮箱与网络来源转换为版本化 HMAC，只向受控内部服务发送摘要候选、非敏感 key tag、策略和有界结果。它不发送邮箱、IP、密码、token、Cookie 或正文。
- 远端协议固定为 `m14.login-protection.v1`，禁止重定向和环境代理；错误协议、响应、网络或存储全部失败关闭。生产只允许 HTTPS，服务 token 至少 32 字符且独立保存。
- `environment=production` 若仍配置 `direct` 或 `sqlite`，登录与 `/ready` 明确不可用。本地开发仍可使用两者。
- 仓库只实现 adapter 和可测试契约，不捆绑或假装实现外部分布式原子服务；部署责任、原子性、TLS、告警与数据最小化见 [`ADR-2026-09-09-TRUSTED-LOGIN-EDGE.md`](ADR-2026-09-09-TRUSTED-LOGIN-EDGE.md)。

### 3.7 PostgreSQL tenant adapter 第一段：正式身份

- `PostgresAccountIdentity` 在不改变登录、注册和账号管理 Interface 的前提下实现账号、personal tenant、membership、稳定 owner 与摘要会话；浏览器和 Agent 仍看不到数据库或内部身份标识。
- `production_identity_provider` 显式区分本地过渡 SQLite 与 PostgreSQL。生产环境若仍选 SQLite、缺少私有 DSN、驱动/连接不可用或 schema 不符，身份服务与 `/ready` 失败关闭。
- 应用启动和 adapter 构造不会创建表。独立 schema 工具先只读预演，应用时必须同时提交确认和预演指纹；未知目标拒绝写入，部署由 PostgreSQL 事务 advisory lock 串行化。
- schema 版本与预期列形状都要通过无数据读取才算就绪。旧 SQLite 生命周期 CLI 在 PostgreSQL backend 下拒绝运行，避免误改过渡库。
- 本段没有连接真实 PostgreSQL、没有迁移现有账号/会话/私人内容，也没有完成 owner-aware 业务存储；具体决策见 [`ADR-2026-09-10-POSTGRES-IDENTITY-ADAPTER.md`](ADR-2026-09-10-POSTGRES-IDENTITY-ADAPTER.md)。

### 3.8 PostgreSQL tenant adapter 第二段：owner 数据只读清点

- 新增不接 HTTP/浏览器/Agent 的 `OwnerDataInventory`，固定列出私人资料、截图识别、个人题库、PDF 导入、教案、试卷和教师记忆的 owner-bearing SQLite 表及关联文件目录。
- 表被明确分类为直接 owner、继承父对象 owner 和旧版无 owner；只对直接 owner 表计算指定源 owner 的行数，不把继承关系伪装成已完成映射。
- 清点只读打开既有库，不创建或修复存储。未知表、视图、触发器、关键列漂移、链接和不可读目标全部阻塞；惰性初始化而尚不存在的已知表不阻塞。
- 非空文件目录在逐文件引用对账完成前保持阻塞。报告不返回 owner、路径、行 ID 或内容；指纹只用于比较清点结果，不是迁移确认令牌。
- 本切片没有迁移、更新或删除任何账号与内容。完整边界见 [`ADR-2026-09-10-OWNER-DATA-INVENTORY.md`](ADR-2026-09-10-OWNER-DATA-INVENTORY.md)。

### 3.9 PostgreSQL tenant adapter 第二段：owner 文件引用只读对账

- 新增不接 HTTP/浏览器/Agent 的 `OwnerFileReconciliation`，把私人资料、题图 revision、PDF 原文件/媒体裁剪和试卷版本资源分别映射到数据库 owner 事实。
- 平面目录严格对照 `stored_name`；试卷目录同时核对 paper owner 和当前/历史不可变版本里的 asset ID。文件正文不读取，文件名、路径、owner、对象 ID 和原始 JSON 不出现在报告。
- 缺失、孤儿、跨 owner 共用、悬空父引用、路径穿越、链接、异常目录布局、未知 SQL 对象和 schema 漂移全部阻塞。每个文件域生成仅摘要的证据指纹，避免只比较数量。
- 本切片没有生成迁移命令，也没有写入、移动或删除任何数据库记录与文件。完整边界见 [`ADR-2026-09-10-OWNER-FILE-RECONCILIATION.md`](ADR-2026-09-10-OWNER-FILE-RECONCILIATION.md)。

### 3.10 PostgreSQL tenant adapter 第二段：owner 逐对象迁移计划

- 新增不接 HTTP/浏览器/Agent/模型的 `OwnerMigrationPlanner`，要求同时提交清点与文件对账的精确指纹，任一证据变化即拒绝生成计划。
- 固定 ownership 查询图覆盖 33 张非旧版表，按父对象先于子对象的顺序输出对象摘要、完整源记录指纹与依赖摘要；四个文件域输出逐文件摘要、内容 SHA-256 与字节长度并与对账数量复核。计划 schema v2 将文件字节纳入确认指纹。
- 子记录 owner 无法解析、多条 owner 路径不一致、依赖对象未进入同一计划、对象重复、旧无 owner 行或文件异常全部失败关闭。
- 源/目标 owner、tenant、路径、主键、文件名和正文均不出现在报告；输出固定 `execution_allowed=false`，计划指纹也不是写入确认令牌。
- 对象扫描后再次执行两份只读证据并重建完整对象/文件计划，防止扫描期间的对象、记录内容、依赖、文件引用或文件字节漂移。本切片没有连接目标 PostgreSQL，也没有写入、复制、移动、删除或持久化计划。完整边界见 [`ADR-2026-09-11-OWNER-MIGRATION-PLANNING.md`](ADR-2026-09-11-OWNER-MIGRATION-PLANNING.md)。

### 3.11 PostgreSQL tenant adapter 第二段：迁移执行控制器

- 新增不接 HTTP/浏览器/Agent/模型的 `OwnerMigrationExecutor`。只有显式确认值、预期计划指纹和重新生成的实时计划完全一致时，才允许打开注入的目标事务 adapter。
- adapter 的小 Interface 只提供目标状态、应用、摘要对账和完成标记。首次执行只接受空目标；同一绑定和计划已完成且对账一致时幂等返回，不重复应用；遗留进行中、错误绑定、错误计划或未知状态全部失败关闭。
- 首次执行在同一事务内按“应用 → 逐集合摘要对账 → 标记完成”推进。对象/文件数量、计划指纹或摘要集合任一不符即抛错，由 adapter 在提交前回滚；回执不返回 owner、tenant、主键、文件名、路径或正文。
- 本控制器最初只以合成事务 adapter 验证控制语义；后续具体 PostgreSQL 目标 adapter 已接入同一 Interface，但仍没有运行时业务内容 schema、生产文件 staging 或真实数据迁移。完整边界见 [`ADR-2026-09-11-OWNER-MIGRATION-EXECUTION-CONTROLLER.md`](ADR-2026-09-11-OWNER-MIGRATION-EXECUTION-CONTROLLER.md)。

### 3.12 PostgreSQL tenant adapter 第二段：迁移落地区域

- 新增不接 HTTP/浏览器/Agent/模型的 `PostgresOwnerMigrationSchema`，固定保存目标绑定 run、对象暂存和文件发布记录；它使用独立私密目标 DSN，不复用运行时身份连接，也不是运行时业务内容库。
- 构造对象和应用启动不连接数据库或建表。操作者必须先只读预演，再提交完全一致的 SQL 计划指纹和明确确认；未知既有结构、指纹变化、连接失败或列形状异常全部失败关闭。
- 部署在 PostgreSQL 事务 advisory lock 中串行化；同一版本和预期形状已存在时幂等返回。目标记录不保存 `source_owner_id`，旧身份不能成为新系统授权事实。
- 独立本机 CLI 提供 `preview` 与 `apply`；未确认的 apply 在读取私密配置前拒绝，输出不含 DSN 或身份。当前只以合成连接验证 schema 门禁，没有连接真实 PostgreSQL，没有创建 schema，没有写入、复制、移动或删除任何真实数据。完整边界见 [`ADR-2026-09-11-POSTGRES-OWNER-MIGRATION-SCHEMA.md`](ADR-2026-09-11-POSTGRES-OWNER-MIGRATION-SCHEMA.md)。

### 3.13 PostgreSQL tenant adapter 第二段：owner 数据库对象只读物化

- 新增内部 `OwnerMigrationObjectMaterializer`，只把已确认计划中的源 SQLite 行重读为后续目标事务 adapter 可消费的目标绑定载荷；它没有 HTTP、浏览器、Agent、模型或 CLI 入口。
- Planner 与 Materializer 共用规范化摘要 seam。物化前重新核对完整计划与目标绑定，随后逐表核对对象集合、依赖摘要、唯一完整行和源记录指纹；任一变化都失败关闭。
- 只选择明确源 owner 的对象；载荷中的 `owner_id` 和已有 `tenant_id` 改绑到目标，BLOB 使用明确 Base64 表达。其他 owner 的内容不会进入载荷，私密载荷不会出现在报告、错误或 `repr`。
- 源库以 SQLite 只读模式和 `query_only` 打开，测试验证文件字节不变。当前不连接 PostgreSQL、不物化文件、不写入、复制、移动或删除真实数据；完整边界见 [`ADR-2026-09-11-OWNER-MIGRATION-OBJECT-MATERIALIZATION.md`](ADR-2026-09-11-OWNER-MIGRATION-OBJECT-MATERIALIZATION.md)。

### 3.14 PostgreSQL tenant adapter 第二段：owner 文件流式物化

- 新增内部 `OwnerMigrationSourceFiles`，把固定数据库引用、owner 过滤、安全路径解析和内容指纹收口为同一只读 Interface；Planner 与文件物化器复用它，不各自解释文件引用。
- `OwnerMigrationFileMaterializer` 在读取前核对完整计划、目标绑定、文件域和逐文件 SHA-256/长度。物化完成后的每次流式复制仍会重新拒绝链接并在 EOF 复核内容，计划后或物化后的替换都失败关闭。
- 文件流只能交给目标事务 adapter 所拥有、失败可丢弃的 staging sink；成功复核前不得记录暂存完成，更不得发布。批次表示、错误与公开报告不含 owner、tenant、路径、引用名或正文。
- 当前测试只使用临时文件和内存 staging sink；没有连接 PostgreSQL，没有复制/发布真实文件，也没有 HTTP、Agent、模型或 CLI 入口。完整边界见 [`ADR-2026-09-11-OWNER-MIGRATION-FILE-MATERIALIZATION.md`](ADR-2026-09-11-OWNER-MIGRATION-FILE-MATERIALIZATION.md)。

### 3.15 PostgreSQL tenant adapter 第二段：具体目标事务 adapter

- 新增 `PostgresOwnerMigrationAdapter`，直接满足 Executor 的小型事务 Interface；目标状态、两类物化、PostgreSQL INSERT/UPDATE、实际摘要重算和完成标记均封装在 adapter 内。
- source owner、target owner 和 tenant 在构造时固定，目标绑定或计划不符会在连接 PostgreSQL、打开 staging 事务前拒绝。进入数据库事务后按目标绑定摘要获取 advisory lock，使不同计划不能并发观察同一目标为空；SQL adapter 不能自行选择源表、文件路径、owner 或正文。
- 文件 staging 的可逆事务包住 PostgreSQL 事务：物化/暂存、数据库写入、目标对账、可逆发布和完成标记后才提交数据库；对账、发布、SQL 或提交失败会让两侧合成 adapter 回滚。
- 当前只用合成 PostgreSQL 连接和文件 staging Adapter 验证普通异常，没有真实数据库、生产对象存储或真实迁移。后续切片已为数据库提交后 published 内容缺失且 matching staged 内容仍存在的窗口增加前向补偿；详见 [`ADR-2026-09-11-POSTGRES-OWNER-MIGRATION-ADAPTER.md`](ADR-2026-09-11-POSTGRES-OWNER-MIGRATION-ADAPTER.md)。

### 3.16 PostgreSQL tenant adapter 第二段：已提交迁移补偿恢复

- 新增操作者专用 `PostgresOwnerMigrationRecovery`，以 `preview()` / `recover()` 小型 Interface 封装已提交 run、文件记录和外部存储状态解释；没有 HTTP、浏览器、Agent、模型或应用启动入口。
- 预演与恢复按目标绑定获取同一 transaction advisory lock。published 内容匹配为健康；published 缺失且 staged 内容匹配才可修复；任一内容冲突、staged 缺失、数据库数量或状态异常都失败关闭。
- 恢复指纹绑定计划、目标、文件内容和 storage key 摘要，但公开计划不返回 owner、tenant、路径、key、文件名或正文。恢复要求固定短语、布尔确认与最新预演指纹，变化后旧确认失效。
- 恢复只做幂等前向补偿并在完成后重新核对全部 published 内容；不覆盖冲突对象、不删除文件、不回滚数据库记录、不猜测缺失内容。当前只通过合成 PostgreSQL 和文件存储验证，尚无生产文件 Adapter 或 CLI；详见 [`ADR-2026-09-11-COMMITTED-OWNER-MIGRATION-RECOVERY.md`](ADR-2026-09-11-COMMITTED-OWNER-MIGRATION-RECOVERY.md)。

## 4. 后续切片顺序

1. **账号生命周期加固（进行中）**：网页个人账号注册、操作者创建/停用、密码重置、失效会话预览/确认清理、登录双范围限流、摘要化登录安全事实、当前浏览器会话轮换、MFA 决策、操作者生命周期审计、摘要密钥轮换、可信生产代理来源与分布式限流 adapter 已实现；邮箱验证、找回密码、外部分布式服务、边缘部署、告警、已认证操作者/RBAC、MFA 与集中式密钥管理仍未完成。下一段进入 PostgreSQL tenant adapter。
2. **PostgreSQL tenant adapter（进行中）**：正式身份 adapter、显式 schema 预演/确认、owner-aware 只读存储清单、四类文件域引用对账、逐对象迁移计划、明确确认/幂等/对账/事务回滚控制器、固定迁移落地区域、数据库对象/文件流只读物化、具体 PostgreSQL 目标事务 adapter 和已提交文件发布前向补偿的合成验证已实现；下一段验证 IDOR/tenant isolation。
3. **对象存储与持久任务**：原文件、导出和后台任务获得明确 owner/tenant key、保留期、幂等和恢复语义。
4. **Entitlement**：只表达账号可用能力，不替代身份、owner 权利或内容可信门禁。
5. **订单、订阅、支付与退款**：最后接入；要求幂等、Webhook 验签、状态机、对账和退款恢复全部独立验证。
6. **M14 Gate**：认证、RBAC/IDOR、tenant 隔离、私题永久隔离、恢复与商业状态机证据齐全后才可进入 M15。

## 5. 明确未完成

- 正式 owner-aware PostgreSQL 业务内容 schema、生产文件 staging/recovery Adapter、恢复 CLI、无 staging 或内容冲突时的人工处置、真实 PostgreSQL 集成 Gate、云对象存储、持久队列、多进程完整一致性和生产灾备。已实现的合成目标 adapter、前向补偿、只读对象/文件物化与迁移落地区域都不等同于真实迁移或业务内容 schema。
- 无约束公网注册、邮箱验证、自助找回密码、MFA、设备管理、已认证操作者/RBAC、不可抵赖审计、集中式密钥管理、生产级分布式限流与告警。当前只实现默认关闭的个人账号网页注册工程路径。
- 除 `personal_owner` 外的角色、组织 tenant、成员邀请、学生和学校后台。
- Entitlement、订单、订阅、支付、Webhook 和退款。
- M13 的真实教师价值、重复使用、错误率与付费意愿 Gate。

因此当前实现可作为 M14 身份边界的工程基础，但不能对外称为生产认证或商业发布就绪。

## 6. 验证入口

- M14 固定回归：`python -m pytest -c apps/api/pytest-m14.ini -q`
- 完整 API：`python -m pytest apps/api/tests -q`
- Teacher Web：`pnpm test:teacher`、`pnpm typecheck:teacher`、`pnpm build:teacher`
- Agent：`pnpm test:agent`、`pnpm typecheck:agent`、`pnpm build:agent`

最终测试数字以 `PROJECT-STATUS.md` 和 `REPOSITORY-SYNC.md` 的同一提交快照为准。
