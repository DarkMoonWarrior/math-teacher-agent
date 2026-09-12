# ADR：tenant/owner 绑定的本地持久任务队列

- 日期：2026-09-12
- 状态：已接受并实现本地 Adapter
- 范围：M14 Commercial Foundation / 对象存储与持久任务

## 1. 背景

现有 `BackgroundJobRegistry` 保存任意 Python runner，并以线程执行。它适合当前单进程 OCR/命题任务，但 API 重启后任务元数据和结果都会消失。直接把旧 Registry 的字典写入 SQLite 不能恢复 Python 回调，也无法证明旧 worker、重启后的新 worker 和取消操作之间不会互相覆盖。

私有对象命名空间与本地原子字节 Adapter 已经固定 tenant/owner 授权、完整性和 24 小时终态任务保留语义。本切片在该 Interface 上建立可替换的持久任务 seam；不修改现有产品路由，也不把本地实现宣称为云队列。

## 2. 决策

新增 `SqlitePersistentTaskQueue`，并保留旧 `BackgroundJobRegistry` 作为独立的进程内 Adapter。

持久任务由以下边界组成：

1. `PrivateObjectScope` 必须由服务端当前会话提供 tenant 与 owner；浏览器、Agent 和模型不能选择。
2. SQLite 只保存版本化 HMAC 的 scope/idempotency/subject 摘要、状态、进度、时间和不透明对象 binding，不保存原始 tenant、owner、subject、命令或结果。
3. 私密 subject、命令与结果以固定 JSON envelope 写入 `PrivateObjectDomain.BACKGROUND_JOB_RESULT`，沿用 namespace 授权、SHA-256 envelope、无覆盖原子发布和 `terminal-24h` 保留策略；授权读取任务时才从命令对象恢复 subject 展示值。
4. 同一 scope、任务类型和 idempotency key 的相同请求返回同一任务；subject 或命令变化时失败关闭，不重复执行。
5. worker 首次领取任务时建立第一个 `attempt`；显式恢复在重新入队的同一原子更新中递增 attempt。所有进度、成功和失败写入都以当前 attempt 比较交换，因此恢复已成功但新 worker 尚未领取的间隙也不能被旧 worker 覆盖。
6. 本地 Adapter 不反序列化 runner。初始化时发现遗留 `queued` / `running` 记录会标记为 `interrupted`；只有当前会话重新绑定同一 scope 并显式调用 `resume`，同时重新提供受信 runner，才能进入下一 attempt。
7. 取消仍由 scope 限制，并与 worker 最终提交共享进程内临界区。取消后的旧 worker不能提交迟到结果。
8. `succeeded`、`failed`、`cancelled` 和 `interrupted` 在 24 小时后从读接口隐藏；scope 内清理会先按 binding 和校验和删除命令/结果对象，再删除元数据。清理受阻会返回计数，不能把过期记录重新暴露。
9. 结果发布使用 intent/ready 两阶段：先把预期 binding 与校验和登记为 `result_ready=0`，再原子写对象，最后以同 attempt 标记 ready 和终态。读取端只读取 ready 结果；若进程在对象写入后中断，重启仍能定位、校验并在恢复或过期清理时删除孤立结果。
10. 新建专用 SQLite 可以显式 `prepare()`；非空且缺少精确 schema marker、表或列形状的既有文件拒绝接管。数据库路径及祖先链接/reparse 失败关闭。

## 3. Interface 与 Adapter

- 产品 seam：`SqlitePersistentTaskQueue.start/get/list/cancel/resume/prune`。
- 状态 Adapter：当前为专用 SQLite。
- 私密 payload Adapter：当前为 `FilesystemPrivateObjectStore`，通过 `_PrivateObjectStore` 小型协议注入；未来云对象存储不得重新解释身份或保留策略。
- 旧 `BackgroundJobRegistry` 没有被静默升级；现有命题和资料库路由仍保持原行为，直到各自命令能够从持久 payload 安全重建、且领域写入具备幂等键后再逐条迁移。

## 4. 安全与恢复语义

- 已知 task ID 在另一 tenant 或 owner 下与不存在一致，返回 `KeyError`，不先探测对象。
- scope 与 idempotency 摘要支持当前/旧 HMAC 密钥候选；轮换不会批量重写历史记录。
- runner 异常不会把异常正文写入状态库或公开 `error`；非结构化异常统一为“任务执行失败”。
- 命令/结果 binding、checksum、envelope 或对象内容任一篡改都返回统一 payload 不可用错误。
- 本切片选择显式恢复，而不是自动重放。因为 OCR、命题和领域写入的 exactly-once 语义必须由各业务模块的幂等命令共同证明，队列不能独自猜测。

## 5. 验证

固定合成测试覆盖：

- tenant/owner 已知 ID 隔离和 SQLite 不落原始身份/正文；
- 相同请求幂等与不同请求冲突；
- 重启中断、显式恢复和旧 attempt 迟到写入拒绝；
- 结果对象已发布但 ready 状态未提交的崩溃窗口、恢复清理与旧 worker fencing；
- owner 绑定取消及取消后结果保留；
- 24 小时对象与元数据清理；
- scope/object HMAC 密钥轮换；
- 未知 SQLite schema 拒绝接管；
- 私有对象篡改失败关闭；
- runner 私密异常不落元数据、不返回给调用方。

## 6. 明确未完成

- 现有命题、资料 OCR/修复等产品路由尚未迁移到持久队列。
- 没有云对象存储、PostgreSQL/Redis 队列、分布式 lease、多 worker 调度、自动重试、dead-letter、告警、全局保留清理或生产灾备。
- 没有证明跨数据库领域写入与队列完成标记的 exactly-once；恢复仍需要业务命令提供稳定幂等语义。
- 没有迁移、读取、清理或修改任何真实任务和用户数据。

因此，本 ADR 证明的是持久任务状态与私密 payload 的本地安全 Interface，不是生产队列或 M14 Gate 完成。
