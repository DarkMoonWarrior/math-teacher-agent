# M8 私有辅助命题完成 Gate 评审

评审日期：2026-08-28

分支：`codex/teacher-workbench-v1`

结论：**M8 功能 Gate、Gate E 与 Gate P 通过；M8 完成。M9 仍等待项目所有者在查看本评审后确认。**

## 1. 范围核对

- 已完成：自然语言要求到完整结构化题目、题面自审核与按需完善、可读解析、解析派生答案、最终一致性复核、选择题独立选项、高中范围终检、教师编辑/revision、显式保存、个人分类、复制/导出、回收/恢复/永久删除、上一次与命题历史。
- 已完成：owner-scoped 后台命题、跨页面恢复、真实阶段/耗时、由 owner 明确取消；取消在私人草稿写入前再次检查，不提交半成品。
- 已完成：Search 空/不合适结果、新任务、未来 Paper 询问契约及顶部直达入口；均不自动生成、保存或入卷。
- 部分完成：本地 current-teacher adapter 只用于开发，不代表生产认证、云 tenant isolation 或备份到期治理。
- 未开始：M9 Paper、M10 Lesson、Memory、Closed Beta、支付、多租户、教研组和学校能力。
- 超范围修改：无；没有新增依赖、迁移公共题库或放宽私题可见性。

## 2. 固定评测

[`M8-PRIVATE-QUESTION-AUTHORING-EVALUATION.md`](M8-PRIVATE-QUESTION-AUTHORING-EVALUATION.md) 记录 26 个项目自建 synthetic 场景；题型、高中模块、内容闭环、模型失败、取消、权利拒绝、owner/IDOR、公共搜索、Agent 权限、保存/revision/删除共 12 类违规全部为 0。

## 3. Gate E

1. 范围：已完成、部分、未开始与超范围项已在上节列明。
2. 工程回归：FastAPI `381 passed`（仅 1 条 Starlette TestClient 依赖弃用提示）；Teacher Web 类型检查、50 项测试、生产构建通过；Agent 类型检查、42 项测试、生产构建通过；legacy Web 类型检查和生产构建通过。
3. 故障体验：模型/结构不可用、大学范围、权限拒绝使用产品错误；内容质量失败在后台内部整题重命；取消返回明确 `cancelled`，结果为空且不写草稿。既有 Search/Solve Gate 继续覆盖 Tool 超时、网络失败和空结果。
4. 可信边界：Agent 只经 allowlisted Tool；无数据库直连、无 MathVerifier/RightsGate 绕过、无自动 publish。
5. 仓库卫生：未跟踪 `.env`、数据库、上传、私题或商业内容；`data/commercial-approved` 仍只有说明文件。
6. 依赖/迁移/删除：无新依赖和破坏性迁移；永久删除仍需要 owner、回收站状态、当前版本与固定确认短语。
7. owner 权限：浏览器 owner 伪造、跨 owner、IDOR、公共 Search、后台/Agent 权限和取消 owner 隔离测试通过。

## 4. Gate P

- `PersonalQuestionLibrary` 与公共 `QuestionBank` 的业务接口和存储命名空间分离，没有 publish/share/public/commercial-approved 迁移。
- owner 只由 FastAPI 认证依赖注入；浏览器、Agent 和模型不能指定 owner。
- 只有 owner 可以查看、编辑、分类、复制、导出、回收、恢复和永久删除；后台和 Agent 无内容管理或永久删除 Tool。
- 生成题不进入公共 Search、公共 QuestionBank、运营面板、商业批准目录或模型训练路径。
- Search/Paper 只能显式引导，不能自动命题、自动保存或混入真实题目。
- 日志静态检查未发现命题要求、题面、答案或解析正文写入运行日志；评测与测试数据均为 synthetic。
- 历史删除不会连带删除已保存私题；owner 删除不影响公共母题或其他 owner。

## 5. 界面与可访问性

- 本轮浏览器复核：1280px 页面 `scrollWidth=1265`，无横向溢出、无 Pydantic/HTTP 500/内部字段异常泄露；命题书桌、上一次、历史和 owner-only 标识可见。
- M8 累计浏览器证据覆盖 320/375/414/768/1280px；题面、独立选项、可读解析、真实阶段与历史恢复均已验收。
- 取消入口是可聚焦的原生按钮；进度区域保留 `role=status`、`aria-live=polite`，旋转动画遵循既有 reduced-motion 规则。组件契约测试验证九个真实阶段、计时和取消文案。

## 6. 阶段转换

M8 已达到当前仓库的完成定义并形成可回滚提交。依据路线规则，本评审本身不授权开始 M9；只有项目所有者查看结果并明确确认后，才进入 M9 Paper Agent。
