# 当前架构与模块 seam

更新日期：2026-09-04

## 1. 总体结构

```text
apps/teacher-web (primary Next.js UI, :3001)
        │ same-origin /api/v1
        ▼
apps/api (FastAPI modular backend, :8000)
        ├── public teacher routes
        ├── product-owned TeacherAgentRuntime interface
        ├── business modules and validation/rights rules
        └── internal Agent Tool gateway
                    ▲
                    │ M2M allowlisted HTTP tools
apps/agent (isolated Node/TypeScript runtime, :4100)
        └── DeepSeek Harness adapter/plugins/tools
```

## 2. Deep modules and interfaces

### Teacher Workspace module

- Seam: `apps/teacher-web/lib/teacher-workspace/contracts.ts`.
- Interface: UI submits Search or Solve teaching tasks and receives product-owned progress stages, structured results and errors.
- Adapter: the HTTP adapter consumes same-origin Search/Solve SSE routes, exposes only product progress, returns one structured result, and maps `AbortSignal` to explicit run cancellation.
- Recovery: after a transport interruption with a known `run_id`, the adapter performs one read-only snapshot lookup for that capability. It never repeats the Search/Solve `POST` or Tool execution; a snapshot without a saved terminal state becomes `STREAM_RECOVERY_FAILED`.
- Transport: `apps/teacher-web/app/api/v1/agent/{search,solve}/stream/route.ts` are exact no-buffer streaming proxies to FastAPI; other same-origin API paths continue to use the general Next.js rewrite.
- Rule: React views do not know SSE parsing, backend storage, Harness events, provider payloads, or raw database fields.

### Search Agent module

- Seam: `SearchAgentPipeline.run/stream/cancel` and `SearchAgentResponse`.
- Implementation: deterministic intent parsing, grounded curriculum mapping, rights/visibility gate, verification enrichment, deduplication, ranking, diversity and explanation sanitization.
- Lifecycle: `POST /api/v1/agent/search/stream` executes one real runtime stream; `run_id` is registered before delivery, disconnect/cancel reaches the same in-flight run, and later snapshot reads never execute the query again.
- Trust: model deltas and Tool input/output remain inside FastAPI; the browser receives only payload-free progress events and the final grounded `SearchAgentResponse`.
- Rule: structured business results are the source of truth; model prose cannot add facts.

### Solve Agent module（M5 已完成）

- Seam: `SolveAgentWorkflow.run/stream/cancel/resume`、`SolveAgentCommand` 与 `SolveAgentResponse`。
- Lifecycle: FastAPI 公开接口拥有同步执行、单次真实 SSE、进程内 run 快照、在途取消与同 session 恢复；路由和业务模块均不 import Harness 类型。
- Trust: 一次成功 run 必须且只能包含一次成功的 `solve_question` Tool 调用；最终 `SolutionResult` 只从该结构化输出建立。模型自由文本、额外 Tool 调用、失败 Tool 伪装的成功 payload、可信等级与验证证据冲突都会被拒绝。
- Exposure: 浏览器只接收无原始 input/output 的 Tool 进度和结构化终态；`math_verification` 的 status、capability、scope 和 evidence source 由业务模块拥有。
- UI: `TeacherWorkspace.solveQuestion` 通过同源无缓冲流接入；教师可输入完整题目或从 Search 结果转入，并在三页纸张中查看结构化解析、课堂提示与独立验证证据。
- Current boundary: 代码 feature gate 默认关闭，本地显式开启；固定 synthetic eval 与完整 Gate E 已通过。M5 不再扩展。

### Private Library Agent module（M6 已完成）

- Seam: `PrivateLibrary` 业务接口与版本化 internal Tool gateway；Agent 只看到产品拥有的结构化结果。
- First slice: `inspect_private_library` 没有 model-supplied owner 参数，只返回本地 current owner 的聚合数量、处理状态和文件类型；`content_included=false`。
- Trust: 标题、文件名、正文、原文件、路径和 owner 标识均不进入第一条 Tool 输出；Agent 不能据此声称已读取资料内容。
- Current identity: `app/core/identity.py` 是服务端 current-teacher seam；Public 路由不接受浏览器提供的 owner/reviewer，详情、文件、OCR、revision、后台任务和候选访问均通过跨 owner 自动测试。M12 `BetaAccess.issue/resolve/revoke` 在启用时把 opaque HttpOnly Cookie 解析为 current teacher，并返回签发时冻结的 allow-list 能力快照；无有效会话 fail closed，未开放模块由集中式能力依赖在业务路由前拒绝。访问码、令牌生成/哈希、能力快照、到期和撤销均隐藏在模块内部。只有显式禁用 Beta 时才固定返回本地 `owner_teacher` 与全部能力。这仍是 Closed Beta 准入，不是生产认证、授权平台或多租户系统。
- Operational seam: M12 `PrivacySafeOperations` 独占运行事件 schema 与结果分类，公开接口只接受请求编号、allow-list 能力、方法、结果、状态码、稳定错误类别和耗时；ASGI 中间件只负责测量完整响应并适配为结构化日志。`ReadinessProbe` 独占 API、Beta session store/roster 与必要 Agent runtime/model 的就绪判定，路由只把稳定结果映射为 200/503。两条 seam 都不接收或返回 headers、query、正文、owner、资源 ID、访问秘密、URL 或原始异常消息。
- Recovery/lifecycle seam: M12 `BetaBackupRecovery.inventory/create_backup/verify_backup/restore_drill` 独占 owner store 清单、SQLite 在线快照、目录复制、manifest/逐文件 SHA-256、原子发布和隔离恢复；`BetaBackupRetention` 固定 30 天并坚持预览/确认清理。`OwnerDeletionLedger` 位于 owner 备份之外，`RestoredOwnerDataFilter` 在隔离恢复中抑制已删除对象，防止旧快照复活。`PrivateBackupDestination` 要求 operator 显式确认私有加密卷或等效保护；浏览器和 Agent 无入口。可撤销 Beta session DB 固定排除。
- Session maintenance seam: 经所有者批准，独立 `BetaSessionMaintenance.preview/prune` 只维护配置中的会话库；默认只读预览，明确确认后在同一事务内重新筛选并删除到期/撤销记录，错误回滚。有效和无法判定的记录保留；缺失库、链接/Windows reparse point、不匹配 schema/触发器拒绝。输出只有计数与截止时间，无浏览器/Agent 入口、自动计划或教师内容删除。
- HTTP privacy: `PrivateApiResponseMiddleware` 为 `/api/v1` 响应设置 `private, no-store`，流式响应保留 `no-transform`，不缓存/拼接响应正文，不改写 Cookie 或 Vary。Teacher Web 搜题/解题代理（含连接失败响应）保持相同约束。此项不是清空已有下载、浏览器页面状态或介质擦除。
- Recognition: `TeacherWorkspace` 隐藏识别后台任务细节；Teacher Web 点击“大模型识别”发起外部识别，左侧原文件与右侧可读整理稿等高、独立滚动，下方编辑中文 + LaTeX 校对稿。当前产品不再提供本地 OCR 按钮或额外授权勾选；服务端仍保存 owner、revision 与本次处理证据，识别不自动升级为数学已验证。
- Fourth slice: 拆题候选绑定教师确认的当前文本版本；浏览器可编辑题目内容但不能提交 owner/editor。教材映射只接受 `node_id`，FastAPI 从受控 Curriculum 补全教材路径。QuestionBank 导入固定为 owner 私有、待审核、待数学验证，并保存资料/版本/候选 provenance。
- Current retrieval seam: 浏览器逐次明确同意后，FastAPI 为当前教师、查询和数量签发短时单次许可；Harness 只能调用固定 `search_private_library` Tool，`PrivateLibrary` 只从 active + confirmed 资源返回有界匹配片段和来源版本/权利状态。owner、原文件、路径与整份正文不越过 seam。
- Completion: 12 个项目自建 synthetic 场景的 8 类违规均为 0，完整工程、静态边界与 320—1920px 浏览器 Gate E 已通过；项目所有者已确认进入 M7。

### Question Capture module（M7 已完成）

- Seam: `QuestionCapture.prepare(QuestionCaptureCommand) -> QuestionInputBundle`。
- Interface: 接收文字或 owner-scoped 单题媒体引用，返回可编辑题面、LaTeX、选项、原图/裁剪引用、视觉推理标志、低置信度区域、revision、consent 与 provider 证据。
- Implementation: 图片验证、旋转裁剪、清晰度、OCR、公式识别、图形存在性判断、owner 隔离和外部处理同意隐藏在模块内部。
- Adapters: 本地 OCR/图像处理 adapter、外部视觉 adapter 和 deterministic test adapter；Solve Agent 不直接调用供应商或读取文件。
- Trust: 带图题的原图/裁剪是 `QuestionInputBundle` 的一部分，不能在 OCR 后丢弃；视觉理解与 MathVerifier 证据范围分开。
- First slice: `QuestionCapture.prepare/transform/get/content` 隐藏真实格式探测、体积/像素/清晰度、EXIF 方向、owner-scoped SQLite/文件 adapter 和 revision。公开路由只接收图片、来源、私有存储确认与受控 asset ID；浏览器不能提交 owner，也看不到存储路径。新 Solve composer 已接入上传、粘贴、拍照、预览、旋转和裁剪。
- Second slice: `QuestionCapture.recognize/review_recognition` 隐藏本地/外部 OCR adapter、逐次外部同意、结构化题面与 append-only 识别 revision。生产 adapter 包括本地 pix2text、DeepSeek `deepseek-v4-flash-vision-exp` 与 OpenAI 图像模型，DeepSeek 优先级只属于路由装配，不进入业务 interface。识别与具体 media revision 绑定；媒体变化后结果显式 `stale`。教师端能校对普通题面、LaTeX、选项和低置信度区域；只有教师确认的 current revision 才能进入第三切片。
- Third slice: `QuestionCapture.prepare_for_solve` 是 owner-scoped、revision-pinned 的深模块 seam；只把教师确认的 canonical 题面和必要视觉字节交给 `SolutionAssistant`。FastAPI 在 Agent 运行前签发一次性 `QuestionSolveGrant`，绑定 owner、canonical 题面、解题模式/要求、asset/media/OCR revision 与本次视觉同意；模型只转发 capability，Tool 在读取图片前消费并从中恢复完整 server-owned 意图，因此模型改写参数不能替换私人资源或改变授权。Agent/Web 不接触文件路径或字节。视觉结果携带实际 provider/model/revision，始终与 MathVerifier 证据分层。

### Private Question Authoring modules（M8 已完成）

- Seam: `QuestionAuthoring.create_draft(QuestionDesignBrief) -> GeneratedQuestionDraft` 负责整题生成；`QuestionAuthoring.regenerate_solution(GeneratedQuestionDraft) -> GeneratedQuestionDraft` 保持题面与选项不变，重新求解并用新解析推导标准答案，再重建可信证据。两者隐藏 provider、受控教材映射、结构检查、MathVerifier 和错误语义。
- Live-progress seam: `QuestionAuthoringProgressRegistry` 是 owner + job 绑定的唯一进行态接口。它发布真实阶段、已用时间、题面 revision 和 `pending/approved/adjusting` 状态；provider 只能在独立题面审核通过后发布 answer-free snapshot，返工开始即把旧 revision 标为调整中，再次审核通过后原子替换。左右界面都只读这一个快照，因此进度与题面不会各自猜测状态。
- Storage seam: `PersonalQuestionLibrary` 独立拥有 owner 私题的个人题库命名、分类、CRUD、revision、导出和删除语义。
- Isolation: `PersonalQuestionLibrary` 不只是公共 `QuestionBank` 的一个 visibility 过滤器；它使用独立业务接口和 owner-isolated storage namespace，没有 publish/share/public/commercial-approved 接口。
- Ownership: current owner 只来自服务端认证上下文；Public Search、Public QuestionBank、后台内容工具、其他 owner、教研组和学校管理员均没有读取接口。
- Management: Agent 生成或提出修改草稿，教师在受认证 UI 中明确保存；编辑、分类、回收站、恢复和永久删除由 owner 直接调用 FastAPI 业务接口，Agent 与后台管理员无永久删除工具。
- Reuse: Curriculum、MathVerifier、RightsGate 和已验证且允许 adaptation 的参考母题可被调用，但不得把辅助命制题复制到公共题库。
- First slice: `PersonalQuestionLibrary` 已以单独 `data/private-runtime` SQLite namespace 实现个人题库集合与分类；它把名称规范化、owner 隔离、重复约束和固定 owner-only policy 隐藏在小接口后。公开 FastAPI 路由只从 current-teacher seam 注入 owner，payload 中额外的 `owner_id` 被拒绝；跨 owner 的集合/分类详情与更新统一返回不存在。
- Second/third slices: `QuestionAuthoring.create_draft` 以严格 `QuestionDesignBrief` 为界面，完成题型补全、可替换 provider、结构验证、六项分级可信检查和诚实错误语义。DeepSeek Harness 只能调用一次 `create_question_draft`；Tool 请求没有 owner/save/publish/share/delete 字段。
- Fourth slice: 公开 FastAPI 在成功生成后把结果登记为当前 owner 的未保存 authoring workspace revision；Agent 本身仍不写存储。浏览器只能提交可编辑题面和 `expected_revision`，`QuestionAuthoring.revise_draft` 在服务端重建可信证据，`PersonalQuestionLibrary` 以 append-only revision 和乐观版本冲突保护修改。显式保存还必须验证 collection/category 属于 current owner，且只写独立的 `personal_questions`，公共 `QuestionBank` 不参与。
- Fifth slice: `PersonalQuestionLibrary` 的同一 interface 隐藏 owner 私题列表/搜索、保存后内容 revision、元数据与分类、标签排序、独立复制、JSON/Markdown 导出及 lifecycle。复制创建独立 draft/revision 链；永久删除只对已 trashed 的当前版本生效，并在事务中删除个人题目快照及其独占 revision 链。公开路由只做认证绑定和下载响应适配，Agent/Internal Tool Gateway 没有这些管理能力。
- Sixth slice: `apps/teacher-web` 只依赖产品自有 `TeacherWorkspace` contract，把新任务、Search 空/不合适结果和 Paper 缺题提示转入独立 authoring workspace。生成、教师 revision、明确保存和 owner 管理是可观察的不同动作；生成题保持 `AI GENERATED · UNSAVED`，不进入 Search result，Paper 也不会自动生成、保存或加题。浏览器 payload 不暴露 owner、policy 或可信证据控制面。
- Seventh slice: 教师不再需要在生成前填写教材知识点、考查方法或易错点。provider 在完成题目后返回细分知识点、方法、常见错误和一个可空的 Curriculum node ID；业务层只接受 catalog allowlist 内的知识点，并把 Agent 映射标记为待确认。教师可在结果页检索目录并用普通 teacher revision 确认/修正，未知或无法映射的节点不会阻断 owner-only 草稿，也不会获得可信状态。
- Long-form hardening: `QuestionAuthoring` 对外仍只有一次 `create_draft`，Agent 仍只能调用一次 `create_question_draft`。DeepSeek adapter 内部先生成不含答案的题面与选项，再由第一次独立求解审核检查条件相容性、对象存在性、可答性、高中范围与选择题唯一性；未通过时最多执行三轮题面完善，每次完善后必须重新审核。通过后，进度 seam 立即发布可读题面，后台继续生成解析提纲与解析段，标准答案只在完整解析组装后提取。最终独立审核是判责 seam：`question_valid=false` 先把题面标为调整中，再进入“完善题面 → 重新审核 → 发布新 revision → 重新解析”；题面成立但 `solution_valid=false`、答案不一致或解析结论与最终独立答案不同则进入“保留题面 → 重新生成解析 → 再审核”。初次审核答案与最终审核不同但最终解析和最终审核一致时，以最终审核纠正内部初审，不丢弃有效题目。正常完成只有完整题面、解析和解析所得答案闭环一致时才返回 owner-only 未保存草稿；`draft` 不等于半成品。owner 主动停止时可选择把最新 approved snapshot 保存到 owner-only `PersonalQuestionLibrary`，其答案和解析字段明确为“无”、状态标注缺少解析；它可以被该 owner 主动加入组卷，组卷/导出中的解析和答案显示“无”，但不会进入公共题库、完整公共历史或其他 owner 的视图。该实现不截短题目，不新增模型权限。命题和 Solve 共用数学内容输出规范与 Teacher Web `MathText`/`MathSolutionView` 渲染路径。
- Solution presentation guard: provider 解析段只允许成稿推导；确定性元推理检测会触发单段清理，持续污染或确认数学冲突时 fail closed。教师触发的解析重生成由认证 FastAPI 直接调用业务 seam，并通过 `PersonalQuestionLibrary.append_ai_revision` 追加版本；Agent Tool、owner/policy 字段和公共题库接口均不扩张。
- Third slice: 同一深模块在返回前生成六项固定可信证据，并由 `QuestionDraftVerification` 强制检查项唯一、总状态与阻断项一致、MathVerifier 能力与是否真正运行一致。答案数量、明显答案冲突、选项重复和难度偏差可确定性检查；一般数学可解性、干扰项语义及无受控 rule spec 的任意生成题保持 `inconclusive/unsupported`，模型自述不能升级为 MathVerifier 证据。

### Paper Agent modules（M9 已完成）

- Planning seam: `PaperBlueprintPlanning.plan` 只把自然语言整理为可编辑、未确认、未保存蓝图；缺失字段用可见假设补全，不查题、不写存储。
- Selection seam: `PaperBlueprintSelection.select` 只在教师确认后调用受控题库能力。公共题经过范围、权利、verification、review、active 与相似度门禁；私题只允许当前 owner 明确选择，且保持 owner/visibility/revision 不变。供给不足返回真实缺口，不调用辅助命题。
- Audit/edit seam: `PaperBlueprintCoverage.audit` 用确定性规则核对分区和配分，并归纳教师所选题目的实际知识范围与难度；后两者是非阻断分析。`PaperEditableDrafting.build` 在服务器重新执行选题后，只接受完整的题号/分区/分值布局编辑并生成草稿指纹、修改记录和双向细目表。两者都无业务写入。
- Version seam: `PaperVersioning.save` 是第五切片的唯一持久化入口。Teacher Web 对所有保存请求先提供取消/确认二次选择；它从 current-teacher context 获得 owner，重新解析公共题和当前 owner 私题的精确 current revision，重新构建草稿并核对浏览器持有的 `draft_fingerprint`、题目完整性和可信状态。题量、题型/分区、配分、总分、知识范围和难度按实际状态写入版本与细目表，但不阻止教师确认保存；无题、题目不完整、越权、可信状态变化或过期指纹仍 fail closed。成功时调用 `ExamPaperStudio` 建立 append-only 不可变版本；失败没有版本副作用。
- Lesson version seam: `LessonVersioning` 是 M10 第五切片唯一持久化 Interface。保存、历史读取和回收/恢复的 owner 只取 current-teacher context；保存前重新构建来源草案，核对教材、公共题、当前 owner 私题/资料及精确 revision，并再次执行完整性、课时对应和高中范围检查。每次成功保存追加不可变快照，编辑历史教案产生新版本，不覆盖旧版本；跨 owner 读取/生命周期操作按不存在处理，保存不把 `draft_requires_teacher_review` 升级为已验证。
- Lesson export seam: `LessonSavedExporting.export` 只接受 current-teacher owner 的精确 `lesson_plan_id + version + format`，读取 `LessonVersioning` 的不可变快照并复核草稿指纹；`SavedLessonPlanDocumentRenderer` 是 DOCX/PDF Adapter，完整渲染目标、流程、题面/选项/答案/解析、评价与来源摘要。导出不读取页面草稿、来源最新 revision 或其他 owner 内容，也不改变业务状态。
- Export seam: `PaperSavedExporting.export` 只接受当前 owner 的精确 `paper_id + version + kind + format`，读取保存时的题目快照与双向细目表，不读取页面草稿或题库最新 revision。它复用 `ExamPaperDocumentRenderer` 生成学生卷、答案卷和双向细目表的 DOCX/PDF，不改变任何业务状态。
- Ownership: 浏览器和 Agent 均不能提交 owner、版本号生成规则、可信结论或保存结论；跨 owner 的版本与导出统一不可见。保存试卷不会复制、发布或改变 PersonalQuestionLibrary 内容。
- Teacher Memory seam: `TeacherMemory.profile/apply/planning_defaults` 是 M11 的产品 Interface。SQLite、值编码、版本冲突、来源和置信度生成都隐藏在模块内部；公开路由只从 current-teacher context 绑定 owner。模块只接受 allow-listed 结构化偏好，显式值固定 `teacher_explicit + confidence 1.0`，自动学习只从已确认保存版本形成可解释提议且永不自动晋升；反馈、导出和删除均不接收浏览器 owner，也不保存任务或私人资料正文。
- Beta validation seam: `BetaValidationMetrics` 是 M13 的版本化指标与教师权利 Interface。调用方只能提交严格枚举的无内容 observation；Implementation 在 SQLite 写入前以私有 HMAC 摘要 owner/task，并集中处理 `m13.notice.v1` 确认、16 项 `m13.v1` 聚合、eligible cohort 留存、四级可信错误率、当前教师 90 天聚合导出和原子退出删除。`BetaValidationFacts` 是业务侧唯一记录 seam：路由只声明已经成功的服务端事实，它隐藏采集关闭、未参与、事件映射、原子主事件/任务完成/Tool 结果及 fail-open 存储故障；Search/Solve、命题、Paper、Lesson、资料确认导入和私题保存均已接入。Search 明确选题和 Search/Solve 决定通过 owner/run/result 校验后才进入事实层。`ModelOperationsRegistry` 仅在 provider 调用已携带服务器可信 owner 且供应商费率快照完整时向事实层报告成本；OpenAI 与 DeepSeek 费率独立配置，未配置费率保持未知，隔离 Agent 内部占位身份不归因。`BetaValidationRetention.preview/prune` 是独立操作者维护 Interface，只识别精确 schema 中早于 90 天的合法事件，默认预览且明确确认后才删；异常行和教师确认记录保留。指标库不进入 M12 owner 内容备份，避免退出删除的数据被旧内容备份恢复。采集开关与 Beta 访问开关分离且默认关闭；关闭采集不关闭既有数据导出/删除权。
- Current completion boundary: M0–M12 已完成，项目所有者于 2026-09-05 确认进入 M13。M13 进行中且切片 1–4 已完成；操作预演、真实 Beta 和 Gate 尚未完成。私有运营读数复用 `BetaValidationMetrics` 聚合器，只通过本机 CLI 以 SQLite 只读模式输出显式分母与周 cohort，不存在 HTTP/Agent/逐人入口。M12/M13 当前实现不代表生产认证、多租户、云端容灾或真实教师指标已经完成。

### Teacher Agent Runtime module

- Seam: product-owned Python and TypeScript runtime contracts.
- Adapters: `LegacyTeacherAgentRuntime` and isolated DeepSeek Harness runtime.
- Rule: Harness-specific event names and types stop at the adapter. Business callers and tests cross only the product interface.
- Session boundary: `TeacherAgentSessions.resolve` 在四类公开 Agent 入口把浏览器别名转换为绑定教师和模块的签名会话；外来或篡改的签名编号在 Runtime 前拒绝。Search/Solve run 快照单独绑定 owner，读取/回放/取消/恢复先校验身份。当前单进程密钥在 API 重启后失效，保存内容不变；不支持多 worker 共享上下文。见 [会话隔离 ADR](ADR-2026-09-04-OWNER-AGENT-SESSIONS.md)。

### Business modules

- Seam: FastAPI module interfaces for QuestionBank, MathVerifier, Curriculum, PrivateLibrary, Paper, Lesson, Similarity and related workflows.
- Implementation: local SQLite/file adapters at the current stage.
- Rule: storage details remain local to these modules so future PostgreSQL/object-storage adapters do not affect UI or Agent interfaces.

## 3. Dependency rules

Allowed:

```text
teacher-web → public FastAPI routes
FastAPI routes → business modules
FastAPI runtime adapter → Agent Service
Agent Service → internal Tool gateway
internal Tool gateway → business modules
business modules → their owned storage adapters
QuestionAuthoring → owner-only authoring workspace（unsaved revision）
Teacher-confirmed edit → QuestionAuthoring recheck → append-only revision
Teacher-confirmed save → PersonalQuestionLibrary private question
Owner management → append-only revision / metadata / copy / private export / trash
Owner-confirmed permanent delete → active snapshot + owned revision chain removed
PersonalQuestionLibrary → owner-isolated private storage adapter
```

Forbidden:

```text
teacher-web → Agent Service
teacher-web → database
Agent Service → database or private files
Agent Service → public browser routes
business modules → DeepSeek Harness
private data → public/commercial data without an explicit authorization workflow
PersonalQuestionLibrary → public/shared/team/school/commercial-approved data（始终禁止，不存在授权例外）
Public Search / Admin content tools → PersonalQuestionLibrary
```

## 4. 唯一产品 UI

`apps/teacher-web` 是唯一产品界面和 `dev:web` 的目标，拥有统一的左右工作区与 Agent-first 导航。

旧 UI 源码、启动命令和 workspace 依赖已移除。迁移/权利/教材证据保留于明确标记的归档目录；历史页面和旧 REST 实现不代表当前 Agent 完成状态。

## 5. Local deployment

- Teacher Web: `127.0.0.1:3001`.
- FastAPI: `127.0.0.1:8000`.
- Agent Service: `127.0.0.1:4100` when DSH runtime is enabled.

The primary UI should normally call `/api/v1` on its own origin. Next.js rewrites that route to FastAPI using `MATH_AI_API_INTERNAL_URL`, avoiding browser CORS coupling. Direct browser-to-API URLs are an explicit deployment override, not the local default.

## 6. Testing at the seam

- UI adapter tests and type checks target Search/Solve observable progress, completion, same-run recovery, failure and cancellation states, plus both exact same-origin streaming proxies；M6 UI 接入后扩展同一产品接口。
- Search tests target `SearchAgentPipeline` and the HTTP route, not private ranking internals alone.
- Solve tests target 唯一 Tool 证据、可信字段校验、结构化错误、真实 SSE、取消、恢复和 feature gate。
- Private Library tests target owner-scoped 结果、private-by-default、revision、逐次外部处理同意、无正文概览 Tool 与越权失败路径。
- M7 tests target `QuestionCapture` 的图片/公式/图形保真、revision、逐次外部同意、Solve 可观察结果和跨 owner 失败，不测试供应商内部实现。15 场景固定 synthetic evaluation 与 Gate E 已于 2026-08-24 通过。
- M8 tests target `QuestionAuthoring`、`PersonalQuestionLibrary` 与 Teacher Web adapter 的可观察接口，强制公共 Search/QuestionBank/后台访问缺失、跨 owner fail closed、浏览器无 owner/policy/trust 控制面、生成与明确保存分离、owner 管理和永久删除语义。
- M9 tests target规划/确认/受控选题/覆盖审计/编辑/保存/导出的深模块 seam：浏览器不能伪造 owner、version 或 trust；过期草稿指纹不得产生版本；成功保存必须是不可变快照；六种导出必须精确读取当前 owner 的指定版本。真实学生卷、答案卷和双向细目表 PDF 还需逐页检查公式、分页、裁切、答案泄露与反向规格完整性。
- Runtime conformance tests exercise both runtime adapters through the product-owned interface.
- Security tests enforce the exact Tool allowlist and absence of database access in `apps/agent`；当前 8 个 Tool 只读，第 9 个 `create_question_draft` 只生成未保存草稿且不执行业务写入。
- Business tests use synthetic/local adapters and assert published behaviour, rights, verification and privacy invariants.

## 7. Future evolution

Keep the modular monolith. Introduce new network services only when deployment constraints make a seam real. PostgreSQL, object storage, persistent jobs and multi-tenant identity are future adapters; they must not leak into current UI or Agent interfaces. 商业化替换存储 adapter 时必须保留 `PersonalQuestionLibrary` 的独立 namespace 和 owner-only 接口，不能为了统一后台而并入公共题库管理。
