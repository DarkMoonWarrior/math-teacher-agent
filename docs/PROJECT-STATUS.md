# 项目当前状态

更新日期：2026-08-21
分支基线：`codex/teacher-workbench-v1`

## 状态说明

- **可用**：存在当前入口、真实实现与自动测试。
- **后端已有**：迁移自旧项目的业务模块可运行，但尚未进入新 Agent 工作流。
- **界面预览**：只用于确认信息架构和需求输入，运行时未接入。
- **未开始**：只有路线图或设计文档。

## 当前路线基线

- M0-M3：已完成，不因路线重排返工。
- **M4 Search 集成稳定化：当前唯一开发里程碑。**
- M5-M9：五个独立 Agent 工作流，均未开始。
- M10-M11：Closed Beta 准备与数据验证，均未开始。
- M12-M15：商业基础、Teacher Pro、教研组和学校，均未开始。

最新版顺序见 [`ROADMAP.md`](ROADMAP.md)，量化验证和发布门禁见 [`PRODUCT-GATES.md`](PRODUCT-GATES.md)。历史 PDF 的核心原则继续生效，但其中的 Prompt 编号和“当前下一步”不再代表项目现状。

| 能力 | 状态 | 当前事实 |
| --- | --- | --- |
| 新教师工作台 | 可用 | `apps/teacher-web`，端口 3001；新 UI、Agent 导航、任务输入、动态纸张、真实 Search 进度与结果状态。 |
| Search Agent | 可用 | FastAPI SearchAgentPipeline + `/api/v1/agent/search/stream`；单次真实流式执行、在途 run 登记、服务端取消、可信标签、放宽披露与空结果。需启用 Search、选择 DSH runtime 并启动 Agent Service。 |
| TeacherAgentRuntime | 可用 | Python 产品接口、Legacy adapter、DSH HTTP adapter；默认 legacy，DSH 不可达时默认不静默降级。 |
| DeepSeek Harness Service | 可用（开发/测试） | `apps/agent`；五个只读工具、mock provider、取消/恢复/安全测试。真实模型需私有环境变量。 |
| QuestionBank / MathVerifier / Curriculum | 后端已有 | 核心业务资产继续复用，不因新 UI 重写。 |
| Solve 工作流 | 后端已有 | 旧 solution assistant/legacy UI 存在；新的 Solve Agent 与新 UI 尚未实现。 |
| Private Library / PDF import | 后端已有 | 私有资料和导入模块存在；新的 Private Library Agent 与新 UI 尚未实现。 |
| Paper | 界面预览 + 后端已有 | 新 UI 可整理组卷需求，但按钮明确禁用；旧 exam_papers 模块不是 Paper Agent 完成证明。 |
| Lesson | 界面预览 + 后端已有 | 新 UI 可整理教案需求，但按钮明确禁用；旧 lesson_plans 模块不是 Lesson Agent 完成证明。 |
| Teacher Memory | 未开始 | 等真实教师验证后再定义。 |
| 账号/多租户/支付 | 未开始 | 当前教师/管理员模式不是认证或授权系统。 |
| 商业公共题库 | 未开始填充 | `data/commercial-approved` 保持为空；只允许通过完整门禁的内容进入。 |

## 2026-08-21 验证快照

- FastAPI：238 项测试通过；另有 1 条来自 Starlette TestClient 的依赖弃用提示。
- Agent Runtime：类型检查、31 项测试和生产构建通过（含 SSE 客户端断开取消）。
- 新教师工作台：类型检查、7 项 TeacherWorkspace / 同源流 Route 测试和生产构建通过。
- 新教师工作台浏览器验收：320px 无关键横向溢出；记录抽屉的初始焦点、Tab 约束、Escape 关闭、焦点返回和关闭态 `inert` 通过；检索完成与历史恢复会自动定位结果区，新任务会返回输入区并恢复焦点；延迟 SSE 下理解、搜索、可信核对和中途取消状态均可见。
- 旧界面：类型检查和生产构建通过，确保地基能力未被整理工作破坏。
- 2026-08-21 本机 `test-mock` 真实链路复验：Teacher Web → 无缓冲同源流 Route → FastAPI → DeepSeek Harness Runtime → 受控 `search_questions` Tool 调用成功；页面可依次展示理解、搜索和可信核对阶段，空商业题库返回可信的 0 结果，不生成假题。

## 已知未决项

- SearchIntent 对相对年份（如“近两年”）的基准日期语义尚未由产品所有者确认。
- 自由格式解释中的学校名/考试名等事实仍以结构化结果为唯一可信来源；通用实体消毒是后续增强。
- Search run 记录当前为进程内实现；云端持久化在封闭测试阶段处理。
- Lesson/Paper 导航当前只展示未来工作流和需求草稿，不调用后端生成。
- 真实教师身份、会话级权限、云端数据隔离和下架流程尚未上线。
- Closed Beta 指标事件、Week-4 留存、任务采用率、严重数学错误率和单位成本尚未进入真实教师统计阶段。

## 历史能力与新产品的关系

旧 `apps/web` 及 `docs/high-school-math-ai` 是新产品的业务地基，不是要照搬的产品界面。迁移原则是：复用成熟业务模块和测试，通过新的稳定接口逐项接入 Agent，而不是重新实现全部业务，也不是把旧页面换色后继续使用。
