# M12 Closed Beta Readiness

## 状态与目标

M12 于 2026-09-05 完成五条切片及完整 Gate，实现回滚点 `570cf79`。目标是在不增加支付、组织、学生或公开分享范围的前提下，让现有教师工作流具备小规模封闭测试所需的最小身份、能力控制、可观测性、恢复和删除边界。项目所有者已于同日确认进入 M13；本文保留 M12 完成证据，M13 当前状态见 [M13 Closed Beta Validation](M13-CLOSED-BETA-VALIDATION.md)。

## 固定边界

- 浏览器、Agent 和模型 payload 不得选择 owner、角色、tenant 或可信状态。
- 访问码与会话 token 只来自私有配置，不进入 Git、日志、分析或浏览器持久存储。
- Beta 会话 opaque、HttpOnly、SameSite Strict、可过期和可撤销；服务端仅存 token 哈希。HTTPS 部署必须启用 Secure Cookie。
- 仅在明确禁用 Beta 的本地开发模式使用固定 `owner_teacher`；启用 Beta 后无有效会话必须失败关闭。
- 运行事件不得包含 prompt、私人正文、题面、答案、解析、owner、资源 ID、URL、秘密或原始异常。
- 不新增生产账号、密码找回、MFA、RBAC、多租户、支付、组织、班级、学生、团队题库或学校管理。

## 五条已完成切片

1. **会话身份**：`BetaAccess.issue/resolve/revoke` 管理私有名单、能力快照和可撤销会话；两个访问码映射到两个服务端 owner，跨用户不可见。
2. **能力开关**：只允许 `search`、`solve`、`library`、`authoring`、`lesson`、`paper`、`teacher_memory`；未开放能力在业务路由前返回稳定 403，前端不挂载对应持久工作区。
3. **隐私安全运维**：`PrivacySafeOperations` 只记录 allow-list 字段；`ReadinessProbe` 用稳定组件码返回 200/503，不泄露名单、密钥、URL 或原始依赖错误。
4. **备份与恢复**：`BetaBackupRecovery.inventory/create_backup/verify_backup/restore_drill` 使用私有目的地确认、SQLite 在线快照、原子发布、清单/逐文件校验和隔离恢复；浏览器和 Agent 无入口，Beta 会话不备份。
5. **生命周期与 Gate**：当前 owner 的私题、资料、图片、试卷和教案永久删除，删除墓碑阻止旧备份复活；备份 30 天预览/确认清理、失效会话预览/确认清理、临时导出响应后清理、终态任务 24 小时保留；全路由/对象 IDOR、缓存、旧接口和固定质量回归通过。

## 深模块接口

- `BetaAccess` 独占访问码比较、token 生成/哈希、到期、撤销和 SQLite 持久化。
- `PrivacySafeOperations` 与 `ReadinessProbe` 独占稳定运维 schema 和就绪判定。
- `BetaBackupRecovery`、`PrivateBackupDestination` 与 `BetaBackupRetention` 独占 owner store 清单、备份验证、隔离恢复和 30 天保留策略。
- `OwnerDeletionLedger` 与 `RestoredOwnerDataFilter` 独占删除墓碑和恢复抑制；账本固定排除在旧 owner 备份之外。
- `BetaSessionMaintenance` 只维护配置中的会话专库，默认预览、明确确认后才删除失效记录。

这些接口没有浏览器可选路径、owner selector 或 Agent Tool。对象永久删除仍由各业务模块验证 trash/current-version/owner，删除协调器只负责墓碑与失败回滚，不替代领域规则。

## 验收结果

- M12 固定评测：**199 passed、1 skipped**。
- FastAPI 完整测试：**648 passed、1 skipped**。
- Teacher Web：**102 passed**，类型检查、生产构建通过。
- Agent：**42 passed**，类型检查、构建通过。
- 跳过项仅为系统不允许创建真实符号链接；Windows reparse 防护另有确定性覆盖。

详细 Gate 见 [M12 Gate 记录](M12-GATE-REVIEW.md)，删除与保留语义见 [M12 数据生命周期](M12-DATA-LIFECYCLE.md)，教师/模块模型会话决策见 [ADR](ADR-2026-09-04-OWNER-AGENT-SESSIONS.md)。

## M13 期间仍保持的限制

当前模型会话和后台任务为单 API 进程上下文，重启后旧运行态不可重用，但已保存内容不变。备份是本地/私有演练，不含云端密钥管理、自动调度、RTO/RPO 或在线替换。M12 合成评测不能替代真实教师价值、留存、数学错误率或付费意愿；M13 已启动但尚未启用真实采集，也尚未产生 Gate A/B/C/Q 的真实证据。
