# 项目当前状态

更新日期：2026-08-22
分支基线：`codex/teacher-workbench-v1`

## 状态说明

- **可用**：存在当前入口、真实实现与自动测试。
- **后端已有**：迁移自旧项目的业务模块可运行，但尚未进入新 Agent 工作流。
- **界面预览**：只用于确认信息架构和需求输入，运行时未接入。
- **进行中**：已完成可验证切片，但尚未通过该里程碑完整 Gate。
- **未开始**：只有路线图或设计文档。

## 当前路线基线

- M0-M4：已完成，不因路线重排返工；M4 Gate E 于 2026-08-21 严格通过。
- M5 Solve Agent：Gate E 已严格通过并完成阶段确认。
- **M6 Private Library Agent：进行中；聚合概览 Tool 与新工作台同源上传/列表两条切片已完成。**
- M7-M9：Paper、Lesson、Memory 均未开始。
- M10-M11：Closed Beta 准备与数据验证，均未开始。
- M12-M15：商业基础、Teacher Pro、教研组和学校，均未开始。

最新版顺序见 [`ROADMAP.md`](ROADMAP.md)，量化验证和发布门禁见 [`PRODUCT-GATES.md`](PRODUCT-GATES.md)。历史 PDF 的核心原则继续生效，但其中的 Prompt 编号和“当前下一步”不再代表项目现状。

| 能力 | 状态 | 当前事实 |
| --- | --- | --- |
| 新教师工作台 | 可用 | `apps/teacher-web`，端口 3001；新 UI、五能力导航、任务输入、动态纸张、真实 Search/Solve 结果，以及 Private Library 上传与资料清单。 |
| Search Agent | 可用 | FastAPI SearchAgentPipeline + `/api/v1/agent/search/stream`；单次真实流式执行、同一 run 终态恢复、在途 run 登记、服务端取消、可信标签、相对年份透明解析、放宽披露与空结果。需启用 Search、选择 DSH runtime 并启动 Agent Service。 |
| TeacherAgentRuntime | 可用 | Python 产品接口、Legacy adapter、DSH HTTP adapter；默认 legacy，DSH 不可达时默认不静默降级。 |
| DeepSeek Harness Service | 可用（开发/测试） | `apps/agent`；七个受控只读工具，其中 `inspect_private_library` 只返回当前教师聚合状态、不返回私人正文；按 Search/Solve 指令分流的 deterministic mock provider、取消/恢复/安全测试。真实模型需私有环境变量。 |
| QuestionBank / MathVerifier / Curriculum | 后端已有 | 核心业务资产继续复用，不因新 UI 重写。 |
| Solve Agent | 可用 | 复用旧 `SolutionAssistant` 可信分层；受控只读 `solve_question` Tool、产品自有 `SolveAgentWorkflow` 与新工作台已接入，支持完整题目输入、Search 转入、同步/真实 SSE/run 快照/取消/同会话恢复和三页可信结果。固定 synthetic eval 与完整 M5 Gate E 已通过。 |
| Private Library Agent | 进行中 | 成熟 PrivateLibrary/PDF 模块继续复用；owner-scoped 聚合 Tool 与新 Teacher Web 同源上传/列表已接入，来源、权利、private 和处理状态可见。OCR/校对、拆题/映射和私人检索尚未实现。 |
| Paper | 界面预览 + 后端已有 | 新 UI 可整理组卷需求，但按钮明确禁用；旧 exam_papers 模块不是 Paper Agent 完成证明。 |
| Lesson | 界面预览 + 后端已有 | 新 UI 可整理教案需求，但按钮明确禁用；旧 lesson_plans 模块不是 Lesson Agent 完成证明。 |
| Teacher Memory | 未开始 | 等真实教师验证后再定义。 |
| 账号/多租户/支付 | 未开始 | 当前教师/管理员模式不是认证或授权系统。 |
| 商业公共题库 | 未开始填充 | `data/commercial-approved` 保持为空；只允许通过完整门禁的内容进入。 |

## 2026-08-22 验证快照

- FastAPI：276 项测试通过；另有 1 条来自 Starlette TestClient 的依赖弃用提示。
- Agent Runtime：类型检查、38 项测试和生产构建通过（含 Search/Solve seam、M6 私人资料聚合 Tool、开发 mock 能力分流、验证冲突/模型不可用失败路径与 SSE 客户端断开取消）。
- 新教师工作台：类型检查、21 项 TeacherWorkspace / Search 与 Solve 同源流 Route / Private Library adapter 契约测试和生产构建通过。
- 新教师工作台浏览器验收：320px 无关键横向溢出；记录抽屉的初始焦点、Tab 约束、Escape 关闭、焦点返回和关闭态 `inert` 通过；检索完成与历史恢复会自动定位结果区，新任务会返回输入区并恢复焦点；延迟 SSE 下理解、搜索、可信核对、中途取消和同一 run 恢复状态均可见。
- Search 故障体验验收：模型不可用、Tool 超时、网络失败、权限拒绝均展示明确原因、处置建议与请求编号，输入框恢复可编辑且允许重试；真实 QuestionBank 枚举 `single_choice`、`passed` 和 `commercial_granted` 分别显示为“单选题”“程序验证通过”和“已获商业使用授权”，未验证或冲突状态不会使用可信样式。
- Search 恢复故障演练：主流中断后严格保持一次 Search `POST`，仅追加一次同一 `run_id` 的只读快照 `GET`；有终态时恢复结果，无终态时展示 `STREAM_RECOVERY_FAILED` 和请求编号。
- 旧界面：类型检查和生产构建通过，确保地基能力未被整理工作破坏。
- 2026-08-21 本机 `test-mock` 真实链路复验：Teacher Web → 无缓冲同源流 Route → FastAPI → DeepSeek Harness Runtime → 受控 `search_questions` Tool 调用成功；页面可依次展示理解、搜索和可信核对阶段，空商业题库返回可信的 0 结果，不生成假题。
- 相对年份浏览器验收：按请求发生时的北京时间自然年解释“近 N 年”并包含当前年；2026-08-21 的“近两年”透明披露为 2025—2026；无数字“近年”不设置年份硬条件并提示教师改用明确表达；完成后自动定位结果，320px 下无关键横向溢出。
- M5 第一条 vertical slice：`solve_question` 经 M2M FastAPI Tool Gateway 接入 Harness；题库已验证解析保持 `program_verified`，模型新解答保持 `teacher_review_required`，无解析/模型与超时均返回结构化错误；尚未接入新 Teacher Web 完整解题工作流。
- M5 第二条 vertical slice：解题结果新增 MathVerifier 分级对象；题库通过、来源矛盾、证据不足和模型新解答不支持自动验证四类状态可区分，验证作用范围不能被 Agent 改写；任意新题的通用数学验证能力仍未虚构。
- M5 第三条 vertical slice：产品自有 `SolveAgentWorkflow` 与公开 FastAPI 生命周期已实现；只接受唯一成功的 `solve_question` 结构化输出，模型自由文本与原始 Tool payload 不越过业务 seam；同步、SSE、终态快照、在途取消、失败/取消后同 session 恢复、feature gate 与错误分类均有自动测试。
- M5 第四条 vertical slice：新 Teacher Web 已接入 Solve；教师可输入完整题目或从 Search 题目转入，页面在运行与成功终态自动定位结果区，并以三页纸张分别展示解析、课堂提示和 MathVerifier 证据。320/375/414/768/1440px 无关键横向溢出，本地 `test-mock` 真实链路可返回题库精确匹配、`program_verified`、独立答案和 verifier 版本；模型不可用时仍诚实失败。
- M5 固定评测与 Gate E：9 个项目自建 synthetic 场景覆盖精确已验证题、改题、未知题、失败/不确定验证及 provider 有无两类路径，六类可信违规均为 0；题目 ID、修订计数和验证证据已贯穿 FastAPI、Tool、Agent 与 UI。320—1920px 响应式、完整工程回归和仓库卫生检查通过。
- M6 第一条切片：`PrivateLibrary.stats(owner_id=...)` 只统计指定 owner；内部 `inspect-private-library` 拒绝 model-supplied owner，Tool 输出固定 `visibility=private`、`content_included=false`，不含标题、文件名、正文、路径或 owner 标识。当前本地身份仍固定为 `owner_teacher`，不是生产认证。
- M6 真实 Runtime smoke：本地 DeepSeek Harness 只调用一次 `inspect_private_library` 并正常完成；当前空资料库返回 0，Tool 输出未包含私人正文。Teacher Web/FastAPI/Agent Service 健康检查分别为 200/ok/ok，Agent 报告 7 个可见 Tool。
- M6 第二条切片：新 Teacher Web 增加“资料库”能力入口，支持 PDF/DOCX/PNG/JPEG/WebP 选择、50 MB 前端预检、来源/授权说明、明确确认与 owner-scoped 清单。浏览器不发送 `owner_id`；FastAPI 对列表、统计和上传统一绑定当前本地教师，伪造 `owner_id` 的跨 owner 测试通过。320/375/414/768px 导航与表单无横向溢出，浏览器控制台无错误。

## 已知未决项

- 自由格式解释中的学校名/考试名等事实仍以结构化结果为唯一可信来源；通用实体消毒是后续增强。
- Search run 记录当前为进程内实现；云端持久化在封闭测试阶段处理。
- Lesson/Paper 导航当前只展示未来工作流和需求草稿，不调用后端生成。
- 真实教师身份、会话级权限、云端数据隔离和下架流程尚未上线。
- Closed Beta 指标事件、Week-4 留存、任务采用率、严重数学错误率和单位成本尚未进入真实教师统计阶段。
- M6 当前已完成聚合概览 Tool 与新工作台资料入口；逐次外部处理同意、OCR/校对、拆题/映射、私人检索，以及详情/文件等全链路 owner 权限 seam 仍待后续切片。

## 历史能力与新产品的关系

旧 `apps/web` 及 `docs/high-school-math-ai` 是新产品的业务地基，不是要照搬的产品界面。迁移原则是：复用成熟业务模块和测试，通过新的稳定接口逐项接入 Agent，而不是重新实现全部业务，也不是把旧页面换色后继续使用。

M4 的逐项通过证据见 [`M4-GATE-REVIEW.md`](M4-GATE-REVIEW.md)；M5 评测与 Gate 证据见 [`M5-SOLVE-EVALUATION.md`](M5-SOLVE-EVALUATION.md) 和 [`M5-GATE-REVIEW.md`](M5-GATE-REVIEW.md)。
