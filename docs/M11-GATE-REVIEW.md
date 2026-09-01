# M11 Teacher Memory Gate 评审

评审日期：2026-09-01

结论：**M11 五条纵向切片、固定评测、功能/可信/隐私权利 Gate 和 Gate E 工程检查已通过。变更已形成可回滚提交 `5614fc0`，项目所有者于 2026-09-01 明确确认按原路线进入 M12。**

## 1. 范围核对

- 已完成：仅本人可见、allow-listed、结构化显式偏好；来源与置信度由服务端生成。
- 已完成：Lesson/Paper 缺失字段透明应用偏好；任务显式输入和当次编辑始终优先。
- 已完成：自动学习默认关闭；只从产品拥有的已确认保存版本结构化信号形成提议，至少三次不同证据，绝不静默晋升。
- 已完成：教师明确接受、拒绝或修正；拒绝后三个新证据冷却期；反馈可检查且不含正文。
- 已完成：JSON 导出、保留说明、固定口令永久删除、删除后版本防陈旧覆盖和 owner 隔离。
- 部分完成：本地 current-teacher adapter 不等于生产认证、云 tenant isolation、备份恢复、合规审计或真实教师 Beta。
- 未开始：M12 Closed Beta 身份、feature flags、监控、备份与恢复；支付、学生、教研组、学校能力。
- 超范围修改：无；没有新增 Agent 记忆写权限、公共/共享记忆、任务正文存储或门禁绕过。

## 2. 固定评测

[`M11-TEACHER-MEMORY-EVALUATION.md`](M11-TEACHER-MEMORY-EVALUATION.md) 记录 26 个项目自建 synthetic 场景；偏好、规划、推断、反馈、生命周期、隐私和 Agent 权限共 12 类违规全部为 0。

## 3. Gate E

1. 范围：完成、部分完成、未开始和超范围项已明确列出。
2. 工程回归：FastAPI `459 passed`（仅 1 条既有 Starlette TestClient 依赖弃用提示）；Teacher Web 19 个测试文件、96 项测试；Agent 10 个测试文件、42 项测试；Teacher Web、Agent 与 legacy Web 类型检查及生产构建全部通过。
3. 故障体验：非法偏好、伪造 owner/证据、跨 owner、过期版本、错误删除口令和不存在提议均 fail closed；自动学习关闭或证据不足不会产生提议。
4. 可信边界：`TeacherMemory.profile/apply/planning_defaults` 集中 owner-scoped 存储、校验、推断与生命周期；Agent 无数据库直连，也无记忆写入、导出、删除 Tool。
5. 仓库卫生：评测只使用 synthetic 数据和临时数据库；真实教师记忆、运行数据库、导出文件、密钥和私人正文均未作为产品数据提交。
6. 依赖/迁移/删除：无新依赖、无破坏性迁移；删除只由 current owner 在受控 UI 输入固定口令后调用业务模块，版本保持单调递增。
7. owner 权限：profile、提议、反馈、规划默认值、导出和删除均从服务端身份解析；另一 owner 得到空/不存在视图，不能读取或处理目标数据。

## 4. 页面验证

- 真实 Teacher Web 偏好抽屉显示“导出与删除”、JSON 导出和永久删除入口。
- 未输入固定口令时删除按钮保持禁用；验证未输入完整口令，也未触发真实删除。
- 面板内容在自身区域滚动；页面 `scrollWidth == viewport width`，无横向溢出。
- 浏览器控制台无 warning/error；前端、API（8000）与 Agent Service（4100）均保持启动。

## 5. 阶段转换

M11 已形成可回滚提交 `5614fc0`。项目所有者查看 Gate 结果后，于 2026-09-01 明确要求“继续按照原路线开发”，M12 Closed Beta Readiness 因此成为唯一活动里程碑。
