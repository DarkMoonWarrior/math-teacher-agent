# 项目当前状态

更新日期：2026-08-28
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
- M6 Private Library Agent：已完成；六条纵向切片、12 场景固定评测与完整 Gate E 于 2026-08-22 严格通过。
- **M7 多模态题目采集与图片解题：已完成；15 场景固定评测 9 类违规为 0，Gate E 于 2026-08-24 通过。**
- **M8 私有辅助命题：已完成；26 场景固定评测 12 类违规为 0，完整工程回归与 Gate E/Gate P 于 2026-08-28 通过，所有者已确认进入 M9。**
- **M9 Paper Agent：进行中；蓝图规划与教师确认后的受控选题两条切片已实现，结果仍是未保存候选草案。**
- M10-M11：Lesson、Memory 均未开始。
- M12-M13：Closed Beta 准备与数据验证，均未开始。
- M14-M17：商业基础、Teacher Pro、教研组和学校，均未开始。

最新版顺序见 [`ROADMAP.md`](ROADMAP.md)，量化验证和发布门禁见 [`PRODUCT-GATES.md`](PRODUCT-GATES.md)。历史 PDF 的核心原则继续生效，但其中的 Prompt 编号和“当前下一步”不再代表项目现状。

| 能力 | 状态 | 当前事实 |
| --- | --- | --- |
| 新教师工作台 | 可用 | `apps/teacher-web`，端口 3001；新 UI、五能力导航、任务输入、动态纸张、真实 Search/Solve 结果，以及 Private Library 上传、原文件预览、OCR 校对、修订记录、拆题编辑与教材映射。 |
| Search Agent | 可用 | FastAPI SearchAgentPipeline + `/api/v1/agent/search/stream`；单次真实流式执行、同一 run 终态恢复、在途 run 登记、服务端取消、可信标签、相对年份透明解析、放宽披露与空结果。需启用 Search、选择 DSH runtime 并启动 Agent Service。 |
| TeacherAgentRuntime | 可用 | Python 产品接口、Legacy adapter、DSH HTTP adapter；默认 legacy，DSH 不可达时默认不静默降级。 |
| DeepSeek Harness Service | 可用（开发/测试） | `apps/agent`；九个受控工具：八个只读，`create_question_draft` 只返回未保存草稿且不写业务存储；`inspect_private_library` 只返回当前教师聚合状态，`search_private_library` 需要单次许可且只返回有界确认片段。真实模型需私有环境变量。 |
| QuestionBank / MathVerifier / Curriculum | 后端已有 | 核心业务资产继续复用，不因新 UI 重写。 |
| Solve Agent | 可用 | 复用旧 `SolutionAssistant` 可信分层；受控只读 `solve_question` Tool、产品自有 `SolveAgentWorkflow` 与新工作台已接入，支持完整题目输入、Search 转入、同步/真实 SSE/run 快照/取消/同会话恢复和三页可信结果。题面、步骤和答案现统一渲染行内/独立数学公式，并兼容旧式未分隔 LaTeX；固定 synthetic eval 与完整 M5 Gate E 已通过。 |
| Private Library Agent | 可用（M6 已完成） | 成熟 PrivateLibrary/PDF/Curriculum/QuestionBank 模块继续复用；owner-scoped 聚合、同源上传/列表、提取/OCR/校对、拆题编辑、可信教材映射和逐次授权的私人检索已接入。检索许可短时、单次、绑定当前教师与查询，只返回确认文本的有界片段；候选导入仍固定为 owner 私有、待审核、待数学验证。固定评测与 Gate E 已通过。 |
| 多模态图片解题 | 可用；M7 Gate E 已通过 | Solve 可上传、粘贴或拍摄单题图片并校对题面；教师确认后，canonical 题面和精确 media/OCR revision 通过短时一次性许可接入 Solve。只有图形依赖题在逐次同意后读取受控原图；Agent 不获得路径或字节，结果展示实际视觉 provider/model/revision，且不冒充 MathVerifier。15 场景固定评测和完整 Gate E 已通过。 |
| 私有辅助命题 | 可用；M8 Gate E/Gate P 已通过 | 独立 `PersonalQuestionLibrary` 与结构化 `QuestionAuthoring` 已实现。题面、解析和解析所得答案在内部判责返工直至闭环；选择题选项独立，高中范围终检生效。命题在 owner-scoped 后台继续运行、可跨页面恢复并可由 owner 取消；取消不会写入半成品。结果只暂存为 owner 草稿，显式保存后才成为私题；Agent 无管理写权限。26 场景固定评测 12 类违规为 0。 |
| Paper | 进行中（M9 前两条切片） | 新 UI 将自然语言整理为可编辑 PaperBlueprint；教师确认后才从通过范围、验证、审核、权利、owner 和相似度门禁的公共题/明确选择私题中建立未保存候选草案。真实缺口可见，不自动命题、不写存储；覆盖/难度对照、版本和导出仍待后续切片。 |
| Lesson | 界面预览 + 后端已有 | 新 UI 可整理教案需求，但按钮明确禁用；旧 lesson_plans 模块不是 Lesson Agent 完成证明。 |
| Teacher Memory | 未开始 | 等真实教师验证后再定义。 |
| 账号/多租户/支付 | 未开始 | 当前教师/管理员模式不是认证或授权系统。 |
| 商业公共题库 | 未开始填充 | `data/commercial-approved` 保持为空；只允许通过完整门禁的内容进入。 |

## 2026-08-28 验证快照

- M9 第二条纵向切片：新增 `PaperBlueprintSelection.select(...) -> PaperBlueprintSelectionDraft` 深模块，FastAPI 服务端绑定当前教师身份，浏览器只能提交可编辑蓝图事实和明确勾选的私题 ID。公共候选固定经过 passed/approved/active/public 门禁，私题只能读取当前 owner 明确选择的完整结果；题型、知识范围、高中范围、重复与高相似检查在候选草案前完成。结果按分区保留题面、独立选项、配分、来源、rights、revision、verification、review 与 owner scope；供给不足返回分区级真实缺口，不自动命题、保存、复制或改变可见性。Teacher Web 已接入私题显式选择、公共/私题视觉区分和候选/缺口结果；M9 仍在进行中。
- M9 第一条纵向切片：新增 `PaperBlueprintPlanning.plan(PaperBlueprintBrief) -> PaperBlueprintDraft` 深模块，把自然语言整理为可编辑的年级、用途、时间、总分、难度、知识范围和题型配额；缺失字段以可见假设返回，明确大学范围在业务层拒绝。响应固定 `draft + editable + unconfirmed + unsaved`、无 side effect，并固化 verified-only、owner 明确选择私题和禁止自动命题策略。Teacher Web 的组卷入口已接入蓝图编辑桌面，确认选题按钮保持禁用；真实浏览器验证典型 150 分蓝图、默认假设、本地编辑、高中范围弹窗、375px 无横向溢出和控制台零告警。当前切片不查题、不生成题、不保存；M9 仍在进行中。
- FastAPI：391 项测试通过；另有 1 条来自 Starlette TestClient 的依赖弃用提示。
- Agent Runtime：类型检查、42 项测试和生产构建通过（含 Search/Solve seam、M6 私人聚合与一次性许可检索 Tool、M7 图片 Solve 单一 capability 透传、M8 单次结构化命题 Tool/可信证据契约、开发 mock 能力分流、验证冲突/模型不可用失败路径与 SSE 客户端断开取消）。
- 新教师工作台：类型检查、58 项 TeacherWorkspace / Search/Solve / Private Library / Question Capture / 私有辅助命题 / PaperBlueprint / 数学展示契约测试和生产构建通过；辅助命题请求不提交 owner、隐私状态或可信证据，生成与保存是两个独立动作，后台取消使用 owner-scoped POST，永久删除提交当前版本和固定确认短语；PaperBlueprint 规划请求只提交 brief，受控选题请求只提交可编辑蓝图事实和私题 ID。
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
- M6 第一条切片 Runtime smoke：本地 DeepSeek Harness 只调用一次 `inspect_private_library` 并正常完成；当时空资料库返回 0，Tool 输出未包含私人正文。M6 第五条切片加入受控私人检索后当时精确 allowlist 为 8 个可见 Tool；M8 切片 2 增加不写存储的 `create_question_draft` 后当前为 9 个。
- M6 第二条切片：新 Teacher Web 增加“资料库”能力入口，支持 PDF/DOCX/PNG/JPEG/WebP 选择、50 MB 前端预检、来源/授权说明、明确确认与 owner-scoped 清单。浏览器不发送 `owner_id`；FastAPI 对列表、统计和上传统一绑定当前本地教师，伪造 `owner_id` 的跨 owner 测试通过。320/375/414/768px 导航与表单无横向溢出，浏览器控制台无错误。
- M6 第三条切片：建立可替换 current-teacher seam；详情、原文件、OCR、revision、后台任务与拆题候选均由服务端绑定 owner/reviewer，跨 owner 返回 404，浏览器伪造 actor 字段返回 422。新 Teacher Web 可对照原 PDF/图片、首次提取文本和教师校对稿，保存草稿或确认版本并查看 revision；本地数学 OCR 当前限定 PDF，外部 OCR 每次重新授权且默认禁用。真实浏览器验收确认详情可打开、编辑按钮状态与授权门禁正确，中等宽度导航无重叠且控制台无错误。
- M6 第四条切片：教师确认的当前文本可生成版本绑定的可编辑候选；旧版本、未确认文本、跨 owner、伪造 editor/教材路径和未映射导入均 fail closed。教材搜索复用受控 Curriculum，浏览器仅提交 `node_id`，FastAPI 补全可信册次/章节/小节。导入结果固定为 `private + pending + needs_math_review`，来源证据保存 owner、资料、文本版本和候选 ID。真实页面验收覆盖生成两道候选、编辑后强制先保存、教材搜索/映射和导入解锁；验收条目完成后已移入回收站，未执行题库导入。
- M6 第五条切片：`PrivateLibrary.search_confirmed_text` 仅检索当前 owner 的 active + confirmed 文本；未确认、回收站和其他 owner 均排除。FastAPI 为每次教师同意签发短时单次许可，绑定 owner/query/limit，重放、改写或伪造 owner 均 fail closed。Agent 只可调用固定 `search_private_library` Tool，返回标题、≤480 字匹配片段、文本版本和权利依据，不返回文件名、路径、整份正文或 owner。真实页面验收覆盖未授权阻断、授权后空结果与真实匹配、结果自动定位、授权自动清空、375px 无横向溢出和零控制台告警；验收资料随后移入回收站。
- M6 固定评测与 Gate E：12 个项目自建 synthetic 场景覆盖空库、格式/OCR 失败、模型不可用、Tool 超时、取消、许可重放、跨 owner、未确认/回收站过滤、有界返回、失败后新许可恢复和派生题私有状态，8 类违规均为 0。FastAPI 291 项、Agent 39 项、Teacher Web 28 项测试及全部 typecheck/build 通过；legacy build/typecheck、320—1920px 浏览器、静态边界和仓库卫生通过。
- M7 第一条切片：新增 `QuestionCapture` 深模块和独立 owner-scoped 本地 adapter；实际 PNG/JPEG/WebP、15 MB、2500 万像素、最小尺寸与近空白检查 fail closed，低分辨率/低对比度产生显式警告。原图、旋转、裁剪 revision 可追踪，跨 owner 的详情、内容和变换均返回 404。真实浏览器使用项目 synthetic 图片完成上传、REV 1→旋转 REV 2→裁剪 REV 3、本次任务移除；320/375/768/1440px 无横向溢出，关键入口有可访问名称，控制台零告警。
- M7 第二条切片：新增本地/外部单题 OCR adapter seam、结构化题面/LaTeX/选项/低置信度结果、逐次外部同意和 append-only 识别 revision。识别绑定 media revision，后续图片变换会把旧结果标为 `stale` 并阻止确认；公开路由继续由服务端绑定 teacher，浏览器无法选择 owner/reviewer。教师端提供识别方式、逐次同意、校对、保存草稿和确认入口，并明确不会在当前切片把内容交给 Solve。
- M7 数学展示前置修复：Solution provider 统一要求 `$...$`/`$$...$$` KaTeX 约定并记录 `solution-assistant-v2-math-display`；Teacher Web 识别行内、独立及旧式未分隔公式，失败保留可见原文，步骤正文不再继承编号强调色。该修复不判断课程层级，也不改变数学结论或验证状态。
- M7 第三条切片：`QuestionCapture.prepare_for_solve` 只接受当前 owner、confirmed、current 且精确匹配的 media/OCR revision，canonical 题面与结构化选项由服务端重建。`SolveAgentWorkflow` 签发短时一次性 capability，绑定 owner、canonical 题面、解题模式/要求、asset/media/OCR revision 和本次视觉同意；模型只传递 capability，内部 Tool 在读取图片前消费并恢复完整 server-owned 意图，模型改写普通参数不会改变实际资源或授权。许可重放、跨 owner、未确认或 stale 均 fail closed。只有视觉依赖题读取原图；DeepSeek/OpenAI solution adapter 支持受控图片块，结果显示实际 provider/model/revision 并固定教师复核，视觉理解不升级 MathVerifier。真实 DeepSeek Vision 浏览器验收已确认 `deepseek-v4-flash-vision-exp` 使用原图、证据页显示图片/OCR revision、逐次同意提交后清空且控制台无告警。
- M7 空间几何故障收口：外部识别契约新增 `visual_observations`，把点/线/面标签、连线、虚实线、坐标轴、曲线和表格等直接可见结构作为独立教师核对草稿；旧 revision 保持不可变并提示重新授权识别。真实失败记录定位到 DeepSeek 已响应但 LaTeX 反斜杠未按 JSON 转义，现已增加几何常见命令的确定性回归测试与容错解析；不可恢复的响应格式错误改报 `TOOL_EXECUTION_ERROR`，不再误报 `MODEL_UNAVAILABLE`。视觉解题 prompt 明确禁止只凭 OCR 猜测图形关系。
- M7 长解答格式恢复：复杂轨迹题的真实失败记录定位到模型回答在 JSON 字符串中途截断。DeepSeek adapter 在确定性本地容错失败后只执行一次格式恢复重试，提高但封顶输出预算并继续强制既定 Schema；重试仍失败时保持诚实失败，不循环调用。纯文字题确认后的无操作说明已从 Teacher Web 移除，图形题的一次性原图授权保持不变。
- M7 固定评测与 Gate E：15 个项目自建 synthetic 场景覆盖代数公式、函数图、解析几何、立体几何、统计图、低对比度、截断、多题、外部同意、OCR/视觉失败、取消、许可重放、跨 owner 和 MathVerifier 分层，9 类违规均为 0。FastAPI 318 项、Agent 40 项、Teacher Web 38 项测试及全部 typecheck/build 通过；legacy 回归、320—1920px 浏览器、静态权限和仓库卫生通过。M7 完成，项目所有者随后已确认进入 M8。
- M8 第一条切片：新增与公共 `QuestionBank` 完全分离的 `PersonalQuestionLibrary` 深模块和 `data/private-runtime` SQLite namespace；个人题库/分类支持 owner-scoped 创建、列表、查看与重命名。FastAPI 仅从 current-teacher seam 确定 owner，浏览器额外提交 `owner_id` 返回 422，跨 owner 详情与修改返回 404；响应固定披露 owner-only、不可公共检索/共享/商用/训练，且没有 publish/share/admin/delete 路由。6 项专项测试与 324 项完整后端回归通过。
- M8 第二条切片：新增 `QuestionAuthoring.create_draft` 深模块、DeepSeek provider adapter、公开 Agent workflow 与第 9 个受控 `create_question_draft` Tool。参考母题在 Rights/MathVerifier 检查完成前 fail closed。模型只控制题目内容，不控制隐私与可信字段；结果固定 `owner_only + saved=false`，没有 Agent 存储写入。该切片最初采用生成前 Curriculum 门禁，已由第七条切片替换为生成后归纳。
- M8 第三条切片：`QuestionAuthoring` 返回前强制生成可解性、答案/最终答案一致性、答案数量、干扰项结构、MathVerifier 能力和难度披露六项唯一证据。总状态必须与阻断项一致；明确选项数量错误、最终答案冲突或重复干扰项进入 `checks_failed`。结构完整不等于可解，模型难度不等于校准，当前通用 MathVerifier 不支持任意生成题时固定 `unsupported` 且 `math_verifier_checked=false`。FastAPI 338 项、Agent 42 项、Agent typecheck/build 通过。
- M8 第四条切片：`PersonalQuestionLibrary` 新增 current-owner 私有 authoring workspace、append-only revision 和显式保存到 owned collection/category 的闭环。浏览器只能提交题面内容和期望版本，owner、隐私状态、可信证据均由服务端控制；每次教师编辑由 `QuestionAuthoring.revise_draft` 重跑结构/可信检查，过期版本返回 409。生成接口只登记未保存草稿，Agent Tool 未新增任何保存、覆盖或删除能力；跨 owner、伪造 owner、错误分类、重复保存与计数均有专项测试。FastAPI 342 项、Agent 42 项及 Agent typecheck/build 通过。
- M8 第五条切片：保存后的私题可以继续追加 teacher revision，并在服务端重跑可信检查；个人管理支持 owner-scoped 列表/搜索、重命名、跨个人分类移动、标签/排序、独立复制和 JSON/Markdown 私有下载。回收站、恢复和永久删除均绑定 current owner 与乐观版本；永久删除还要求固定确认短语，并事务性清除该题活动快照、草稿和全部 revision，独立副本不受影响。公开接口没有 publish/share/admin 路径，Agent Tool 未增加管理或删除能力。FastAPI 347 项通过。
- M8 第六条切片：Teacher Web 新增独立辅助命题工作区及新任务、Search 空/不合适结果、Paper 缺题提示三个必需入口，随后增加顶部“命题”直达入口。自然语言 brief、编辑/重检、六项证据、明确选择或新建个人题库/分类、owner 私题管理、私有导出、回收/恢复与固定短语永久删除均通过产品自有 `TeacherWorkspace` contract 调用 FastAPI；浏览器不提交 owner、隐私或可信字段。临时成功/失败反馈与不可逆删除确认采用可访问弹窗，可信检查和数学风险证据继续留在正文。真实本地链路在显式启用 M8 feature flag 并重启 Agent Service 后成功返回 `AI GENERATED · UNSAVED · REV 1`，未执行测试保存。320/375/414/768/1280px 无横向溢出，关键按钮高度均不少于 44px，必需入口、顶部直达入口和上下文继承可见，控制台零告警；Teacher Web 40 项测试、类型检查和生产构建通过。
- M8 第七条切片：移除生成前知识点/考查方法/易错点门禁和对应必填 UI。`QuestionAuthoring` 向 provider 提供受控 Curriculum allowlist，模型完成题目后返回可空节点 ID、细分知识点、考查方法和常见错误；业务层只接受 catalog 内的知识点，未知节点丢弃并保留 warning，无法映射不阻断 owner-only 草稿。Agent 映射保持待确认，教师可在结果页检索教材目录，通过普通 teacher revision 确认/修正映射并编辑教学元数据；隐私、保存、公共禁入和六项可信检查边界不变。真实 DeepSeek 链路已用“考试填空压轴圆锥曲线题”完成生成，返回受控“椭圆综合应用”映射与三类教学元数据，随后在浏览器由教师确认并形成 `REV 2`；未执行私题保存。FastAPI 349 项、Agent 42 项、Teacher Web 40 项测试及全部 typecheck/生产构建通过。
- M8 命题书桌可读性收口：删除页面内重复 revision、生成状态和六项检查明细，以更大的表单标签、完整边框的 Agent 教学归纳区和单一“最终答案”字段替代；owner-only、尚未保存、模型生成、教师复核和阻断检查仍保持可见。非选择题在进入结构与可信检查前由业务层把 `answer_value` 归一到 `final_answer`，教师 revision 同样执行归一，避免同题出现两个冲突答案；选择题仍保留选项编号语义。FastAPI 350 项、Teacher Web 40 项测试、类型检查和生产构建通过。
- M8 长题生成与可读解析收口：此前为规避单次 JSON 截断而设置的题干、解析步骤和 6000 字恢复上限已撤销。`QuestionAuthoring.create_draft` 与 Agent 的一次 `create_question_draft` Tool 契约保持不变，DeepSeek adapter 内部改为先锁定完整题面/唯一最终答案，再生成解析提纲，并行展开各解析段，最后按序组装和执行既有六项检查；某段失败先局部重试，持续截断时只把该段再拆为原子子段，不重新生成题面或其他成功段。命题与 Solve 现共用 `$...$`/`$$...$$` 数学输出规范，Teacher Web 通过共享 `MathSolutionView`/`MathText` 显示可读题面、编号解析和唯一最终答案，原始 LaTeX 收进校订面板。专用命题 Tool、Agent run 和 Web 转发预算扩展到 360 秒，这是失控请求保护而不是内容长度上限。真实 Teacher Web 全链路用三小问 5/5 圆锥曲线解答题完成 62 步、约 17470 字符解析，耗时 264.95 秒，返回 `open_response + owner_only + saved=false + teacher_review_required` 且公式分隔有效。FastAPI 355 项、Agent 42 项、Teacher Web 42 项测试及全部 typecheck/生产构建通过；M8 固定评测与 Gate 仍未执行。
- M8 解析成稿与单独重生成收口：DeepSeek 命题 provider 对解析段新增明确的“只返回正式解析”契约，并在段落返回后检测第一人称试算、自我推翻、失败尝试、提示词或字段讨论；发现污染时只执行一次受控成稿清理，若清理暴露题面与锁定答案冲突则转入待教师核验状态。`QuestionAuthoring.regenerate_solution` 只允许模型重写解析方法和步骤，题面、LaTeX 题面、选项、答案与最终答案全部由业务层锁定；教师触发后追加 `ai_generated` revision、重跑六项可信检查并继续保持 `owner_only + saved=false + teacher_review_required`。浏览器真实验收生成 REV 1 后点击“重新生成解析”得到 REV 2，题面和最终答案未变，未检出试算/自我反思文本；FastAPI 358 项、Agent 42 项、Teacher Web 43 项测试及全部 typecheck/生产构建通过。M8 固定评测与 Gate 仍未执行。
- M8 完整题目优先交付收口：修正“解析阶段数学冲突导致整道题失败”的错误语义。DeepSeek provider 先锁定完整题面、选项和最终答案；后续解析清理确认冲突、仍含自我推翻内容或解析阶段 provider 异常时，返回 `needs_teacher_verification` 草稿并保留全部核心题目字段，解析一致性检查明确为 `checks_failed`，教师可依据完整题面自行核验或单独重新生成解析。检测词覆盖真实返回中的“重新核对初始条件”“题面有误”“与题设不符”“无法选出正确答案”等措辞；只有 core 阶段未完成时才按整项失败处理。隐私、明确保存和 MathVerifier 边界不变。FastAPI 362 项、Agent 42 项、Teacher Web 43 项测试及全部 typecheck/生产构建通过。
- M8 完整选择题、高中范围与生成可见性收口：`question-authoring-v7-high-school-choice-contract` 要求选择题 core 把题干和 A–D 选项分开返回；`QuestionAuthoring` 在进入可信检查前统一选项编号、剥离选项正文中的重复前缀，并清除题干/LaTeX 题干里重复嵌入的选项块，Teacher Web 的 `MathSolutionView` 在题干后以独立边框逐项渲染完整选项。命题 core 被明确限定为中国普通高中数学；发现马尔可夫链、随机过程、傅里叶分析等大学专属概念时先执行一次受控高中范围重写，最终业务层仍会终检并诚实拒绝越界结果。生成按钮进入真实请求后显示持续旋转状态、当前外层阶段和 `MM:SS` 已用时间，不虚构完成百分比、不展示内部推理；整体 Next/FastAPI/Agent/Tool 请求预算从 360 秒扩展为有界 900 秒，内容长度不设硬上限。真实浏览器请求已验证进度面板和计时器；该次请求也暴露了旧 360 秒连接上限，扩展预算后未重复消耗一次完整模型调用。桌面与 375px 移动端检查无横向溢出。FastAPI 364 项、Agent 42 项、Teacher Web 46 项测试及全部 typecheck/生产构建通过；M8 固定评测与 Gate 仍未执行。
- M8 生成前题面自审核收口：DeepSeek 命题 provider 在锁定题面、选项与最终答案后新增独立审核调用，检查条件一致性、对象存在性、可解性、选项完整性与唯一性、锁定答案和高中范围；审核不通过时最多执行三轮受控题面修订与独立复审，仍不通过则在生成解析前停止，且不向弹窗泄露审核计算过程。题面通过后才进入解析生成。服务端新增 owner 绑定、无内容的短时进度登记，Teacher Web 轮询并显示“整理命题要求、命制题面、审核题面、生成解析、建立私有草稿”五个真实阶段、旋转状态与已用时间；此前的说明行已删除。真实浏览器使用高二椭圆离心率单选题完成全链路，独立展示 A–D 选项和正式解析。FastAPI 368 项、Agent 42 项、Teacher Web 47 项测试及全部 typecheck/生产构建通过；M8 固定评测与 Gate 仍未执行。
- M8 题面完善与解析派生答案收口：`question-authoring-v10-reviewed-repair-derived-answer` 不再让 core 生成或锁定答案。第一次独立求解审核只接收题面和选项；审核失败时最多三轮完善并逐轮复审。题面通过后才生成完整解析，标准答案由解析结论产生；第二次独立求解复核题面、解析和答案，单选/多选由服务端比对两次独立审核和解析所得选项，填空题比对三方规范化答案。完整求解若暴露题面漏判，流程执行一次“完善题面 → 重新审核 → 重新解析”的闭环；仍不成立或任一结论不一致时 fail closed，不建立草稿。Teacher Web 增加“完善题面（按需）”成为六步可视化流程。重新生成解析保持题面与选项不变，但标准答案按新解析更新。任意生成题仍无 MathVerifier 形式证明，因此教师复核披露保持不变。
- M8 闭环交付与错误判责收口：`question-authoring-v11-closed-loop-fault-recovery` 修正 v10 将解析不一致直接终止的问题。最终独立审核明确判定题面是否成立、解析是否成立及答案是否一致；题面问题自动进入完善、复审和重新解析，解析/答案问题保留题面并最多三轮重新生成解析。初次审核答案错误但最终解析与最终审核一致时，不再误杀有效题目。命题初次生成与单独重新生成解析均禁止返回 `needs_teacher_verification` 或确定性检查失败的半成品；`draft` 仅表示未保存，用户拿到的内容仍必须包含完整正确题面、选项、正式解析和解析所得标准答案。Teacher Web 扩展为八步真实进度，新增“审核解析与答案”和“重生成解析（按需）”。开发边界新增“所有面向用户的 Agent 内容必须闭环完成”原则；教师可自主编辑，但不承担替 Agent 补全核心交付物的责任。
- M8 最终审核容错：`question-authoring-v12-tolerant-final-audit` 允许失败的最终审核在无法独立求解时返回空答案；只要题面/解析判责字段完整，服务端就继续进入“完善题面”或“重生成解析”分支，不再因缺少独立答案字段抛出 Pydantic 校验错误。未预期的结构错误也只返回受控产品提示，不向教师泄露内部字段名、堆栈或校验链接。
- M8 固定评测、后台取消与完成 Gate：共享 `BackgroundJobRegistry` 新增 owner-scoped 取消终态，并在 domain write 前执行取消检查；Teacher Web 的生成状态提供“取消本次命题”，取消后明确提示且不建立草稿。26 个项目自建 synthetic 场景覆盖四种题型、五个高中模块、内容完整性、大学范围、模型/取消、权利、owner/IDOR、公共 Search、Agent 权限和完整私题生命周期，12 类违规均为 0。FastAPI 381 项、Agent 42 项、Teacher Web 50 项测试及全部类型检查/生产构建通过，legacy 类型检查/构建通过；Gate E 与 Gate P 于 2026-08-28 严格通过。
- 2026-08-22 DeepSeek Vision 更正与实测：官方新增 `deepseek-v4-flash-vision-exp` 图片输入；已作为第二个真实外部 adapter 接入现有识别 seam，复用 DeepSeek Key、base URL、逐次同意与模型运行记录。仓库 synthetic 数学题真实调用准确返回题面、LaTeX、A–D 选项且无低置信度项；旧的“DeepSeek 仅文本”判断已移除。

## 已知未决项

- 自由格式解释中的学校名/考试名等事实仍以结构化结果为唯一可信来源；通用实体消毒是后续增强。
- Search run 记录当前为进程内实现；云端持久化在封闭测试阶段处理。
- Lesson 导航当前仍只展示未来工作流；Paper 已进入 M9 前两条切片，尚未接入正式试卷保存与导出。
- 真实教师身份、会话级权限、云端数据隔离和下架流程尚未上线。
- Closed Beta 指标事件、Week-4 留存、任务采用率、严重数学错误率和单位成本尚未进入真实教师统计阶段。
- 当前身份 adapter 仍是本地固定教师，不代表生产认证、商业多租户或云端隔离已经完成。
- M7 已完成；只有结果中的 `visual_context.image_used=true` 才能描述为“原图参与本次推理”。固定评测和 Gate E 证据见 `M7-MULTIMODAL-SOLVE-EVALUATION.md` 与 `M7-GATE-REVIEW.md`。
- M8 已完成，固定评测、Gate E 与 Gate P 证据见 `M8-PRIVATE-QUESTION-AUTHORING-EVALUATION.md` 和 `M8-GATE-REVIEW.md`。项目所有者已确认进入 M9；M10 及后续阶段仍不得开始。

## 历史能力与新产品的关系

旧 `apps/web` 及 `docs/high-school-math-ai` 是新产品的业务地基，不是要照搬的产品界面。迁移原则是：复用成熟业务模块和测试，通过新的稳定接口逐项接入 Agent，而不是重新实现全部业务，也不是把旧页面换色后继续使用。

M4 的逐项通过证据见 [`M4-GATE-REVIEW.md`](M4-GATE-REVIEW.md)；M5 评测与 Gate 证据见 [`M5-SOLVE-EVALUATION.md`](M5-SOLVE-EVALUATION.md) 和 [`M5-GATE-REVIEW.md`](M5-GATE-REVIEW.md)；M6 证据见 [`M6-PRIVATE-LIBRARY-EVALUATION.md`](M6-PRIVATE-LIBRARY-EVALUATION.md) 和 [`M6-GATE-REVIEW.md`](M6-GATE-REVIEW.md)。
