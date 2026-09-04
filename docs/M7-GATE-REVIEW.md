# M7 多模态题目采集与图片解题 · Gate E 审计

> 状态同步（2026-09-04）：M0–M11 已完成并完成阶段转换，当前为 M12 切片 1–4。本文的切片过程、测试数量和 Gate 结论保留为当时证据；后续行为与当前边界见 [开发状态](PROJECT-STATUS.md) 和 [开发边界](DEVELOPMENT-BOUNDARY.md)。

审计日期：2026-08-24

审计分支：`codex/teacher-workbench-v1`

审计起点：`06ec505ec24b6ffe8185baaabbbefd077b673766`

## 结论

**M7 Gate E 已严格通过，M7 完成。M8 尚未启动，必须等待项目所有者在本结论之后明确确认阶段转换。**

本结论只覆盖本地产品和工程边界，不代表真实视觉模型的数学正确率、生产认证、多租户隔离或商业发布 Gate 已完成。

## Gate 核对

| 维度 | 结论 | 证据摘要 |
| --- | --- | --- |
| 功能 | 通过 | 文字、截图和单题图片可经过上传/粘贴/拍照、旋转裁剪、OCR/公式识别、教师校对与确认进入同一 Solve 工作流。 |
| 图形保真 | 通过 | 函数图、解析几何、立体几何和统计图仅在逐次同意后读取锁定原图；结果记录 media/OCR revision、provider、model 与 `image_used`。 |
| 可信 | 通过 | 视觉模型新解固定 `teacher_review_required`；MathVerifier 的 capability/scope/evidence 独立展示，不能由视觉结果升级为 `program_verified`。 |
| 隐私与权限 | 通过 | 媒体、识别、观察与教师修订始终 owner-scoped/private；浏览器和 Agent 不获得 owner selector、路径、对象存储地址或图片字节。 |
| 逐次同意 | 通过 | 外部 OCR 与视觉 Solve 分别要求当前动作同意；许可绑定完整服务端意图、短时一次性使用，重放与跨 owner 均 fail closed。 |
| 失败与取消 | 通过 | 模糊/截断/多题、OCR/视觉不可用、模型格式错误、Tool 失败、取消和许可失效均有明确语义，不伪装成功。 |
| 数学展示 | 通过 | 题面、步骤和答案通过统一数学展示组件渲染；旧式 LaTeX 有可见降级，响应式验收无页面级横向溢出。 |
| Agent 权限 | 通过 | 仍只有 8 个 allowlisted Tool；静态审计未发现 Agent 直接文件系统、数据库、ORM 或任意 URL 能力。 |
| 工程与仓库 | 通过 | 全量测试、类型检查、构建、固定评测和浏览器验收通过；无新依赖、密钥、运行数据库、私人媒体或商业题库 payload 入库。 |
| 后续边界 | 通过 | M8 仅保留边界文档；私有辅助命题、Paper、Lesson、Memory 与商业基础均未实现。 |

## 固定评测

15 个项目自建 synthetic 场景覆盖代数公式、函数图、解析几何、立体几何、统计图、低对比度、截断、多题、外部同意、OCR/视觉失败、取消、许可重放、跨 owner 和 MathVerifier 分层；9 类违规均为 0。完整记录见 [`M7-MULTIMODAL-SOLVE-EVALUATION.md`](M7-MULTIMODAL-SOLVE-EVALUATION.md)。

## Gate E 工程检查

- FastAPI：`318 passed`，另有 1 条 Starlette TestClient 依赖弃用提示。
- Agent Runtime：类型检查、`40 passed`、生产构建通过。
- Teacher Web：类型检查、`38 passed`、生产构建通过。
- Legacy Web：类型检查与生产构建通过；本阶段未修改 legacy UI。
- 静态边界：Agent 无直接文件系统/数据库 import；无新依赖；`data/commercial-approved` 仅保留边界 README。
- 仓库卫生：未追踪 `.env`、API Key、运行数据库、上传图片、私人资料或第三方题目。

## 浏览器验收

- 320、375、768、1440、1920px 的 Solve 初始工作流均无页面级横向溢出。
- “解题”“上传图片”“粘贴截图”“拍照”“新任务”和题目输入框在全部视口可见且具有可访问名称。
- 浏览器控制台 `warn` / `error` 为 0。
- 既有真实 DeepSeek Vision 验收记录已证明原图实际参与、REV/OCR REV 证据展示和逐次同意提交后清空；本次 Gate 不重复发送任何私人图片。

## 范围核对

### 已完成

- M7 五条纵向切片及完整 Gate E。
- 私有单题媒体、OCR/公式识别、教师校对、图形观察、图形保真 Solve、数学展示、错误恢复和固定评测。

### 部分完成

- 无 M7 范围内部分完成项。

### 未完成

- 无 M7 范围内未完成项。

### 明确未启动或超出范围

- M8 私有辅助命题 Agent。
- M9-M11 Paper、Lesson、Memory Agent。
- 生产认证、多租户、云端隔离、Beta、支付与商业发布。

## 阶段转换

M7 已形成可回滚终态，但本次“继续开发”发生在 Gate E 结论之前，不自动视为对 M8 的阶段确认。只有项目所有者在看到本审计结果后明确确认，才可进入 M8。
