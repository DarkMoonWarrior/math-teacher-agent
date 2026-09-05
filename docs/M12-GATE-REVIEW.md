# M12 Gate 核对记录（已完成）

核对日期：2026-09-05。**M12 Closed Beta Readiness 的五条切片与完整工程/隐私/可信连续性 Gate 已通过。** 实现回滚点为 `570cf79`。项目所有者已于同日确认阶段转换并启动 M13；本文仍只记录 M12 完成证据，M13 状态见 [M13 Closed Beta Validation](M13-CLOSED-BETA-VALIDATION.md)。

## 固定验证入口

```powershell
python -m pytest -c apps/api/pytest-m12.ini -q
python -m pytest apps/api/tests -q
pnpm test:teacher
pnpm typecheck:teacher
pnpm build:teacher
pnpm test:agent
pnpm typecheck:agent
pnpm build:agent
pnpm check:repo
```

`pytest-m12.ini` 显式固定 M12 身份、能力、运维、备份恢复、生命周期、业务对象、任务/模型会话、路由、缓存及 Search 至 Teacher Memory 的既有合成质量评测，不通过动态通配符扩大范围。

| Gate | 结论与证据 |
| --- | --- |
| 身份与能力 | opaque HttpOnly 会话、哈希存储、到期/退出重放拒绝、签发时冻结的七类能力；匿名、到期、已撤销和空能力逐路由失败关闭。 |
| owner/对象隔离 | Search/Solve 任务及四类模型会话按教师和模块隔离；资料、图片、候选、后台任务、试卷/教案历史与导出在昂贵处理前校验 owner，跨用户统一不可见。 |
| 旧接口 | Closed Beta 在存储/provider 之前停用没有安全 owner 契约的旧导入、题库、相似度、解题、教案、组卷写入及全局模型管理入口；当前工作台和本地开发不受影响。 |
| 备份恢复 | 私有目的地确认、SQLite 在线快照、精确清单/SHA-256、路径/链接/reparse 防护、隔离恢复与完整性检查通过；可撤销会话和删除账本不进入 owner 备份。 |
| 删除与保留 | 当前 owner 可固定确认删除私题、资料、图片、试卷和教案；失败不留错误墓碑，旧备份恢复应用当前墓碑。备份 30 天预览/确认清理、失效会话预览/确认清理、导出响应后删除和终态任务 24 小时保留均已实现。 |
| Gate E | 完整 API **648 passed、1 skipped**；M12 固定集 **199 passed、1 skipped**；Teacher Web **102 passed**、Agent **42 passed**，双方类型检查和生产构建通过。 |
| Gate P | owner-only 私题、私人资料、图片、历史版本、导出与删除连续回归；Agent/管理员不能代删或恢复，独立快照保留边界明确。M12 范围内通过。 |
| Gate Q | 既有固定合成质量评测持续通过，未升级模型草稿信任等级。此处只证明回归连续性；真实教师任务错误率与价值指标必须在 M13 采集。 |

跳过项为当前系统缺少创建真实符号链接权限；相同 Windows reparse/路径拒绝逻辑有确定性覆盖。唯一提示是既有 Starlette/httpx 弃用警告，无新依赖、数据库迁移或真实数据清理。

## 完成边界

M12 证明封闭测试的最小准入、能力控制、隐私安全运行状态、私有备份/隔离恢复和数据生命周期可重复演练。它不证明生产认证、MFA/RBAC、多租户、云对象存储、自动备份调度、生产灾备、内容合规审计或商业可用性。

测试全部位于临时目录，使用合成内容和 provider 替身，不是 199 次真实教师任务。M13 才验证 20–30 位真实教师的有用性、重复使用、错误率和付费意愿；在所有者明确确认前不得进入或以 M12 数字替代真实指标。
