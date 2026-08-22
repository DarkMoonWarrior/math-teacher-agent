# 当前架构与模块 seam

更新日期：2026-08-22

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

apps/web (legacy/reference Next.js UI, :3000)
        └── uses the same FastAPI business backend
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
- Current identity: `app/core/identity.py` 是服务端 current-teacher seam；Public 路由不接受浏览器提供的 owner/reviewer，详情、文件、OCR、revision、后台任务和候选访问均通过跨 owner 自动测试。当前 local adapter 固定返回 `owner_teacher`，不是生产认证；真实会话身份在 M12 实现。
- Third slice: `TeacherWorkspace` 隐藏 OCR 后台任务细节；新 Teacher Web 对照原文件、首次提取文本、可编辑校对稿和 revision。本地 PDF OCR 优先，外部 OCR 每次单独同意，任何 OCR 结果仍为待教师校对草稿。
- Fourth slice: 拆题候选绑定教师确认的当前文本版本；浏览器可编辑题目内容但不能提交 owner/editor。教材映射只接受 `node_id`，FastAPI 从受控 Curriculum 补全教材路径。QuestionBank 导入固定为 owner 私有、待审核、待数学验证，并保存资料/版本/候选 provenance。
- Current retrieval seam: 浏览器逐次明确同意后，FastAPI 为当前教师、查询和数量签发短时单次许可；Harness 只能调用固定 `search_private_library` Tool，`PrivateLibrary` 只从 active + confirmed 资源返回有界匹配片段和来源版本/权利状态。owner、原文件、路径与整份正文不越过 seam。
- Completion: 12 个项目自建 synthetic 场景的 8 类违规均为 0，完整工程、静态边界与 320—1920px 浏览器 Gate E 已通过；项目所有者已确认进入 M7。

### Question Capture module（M7 进行中）

- Seam: `QuestionCapture.prepare(QuestionCaptureCommand) -> QuestionInputBundle`。
- Interface: 接收文字或 owner-scoped 单题媒体引用，返回可编辑题面、LaTeX、选项、原图/裁剪引用、视觉推理标志、低置信度区域、revision、consent 与 provider 证据。
- Implementation: 图片验证、旋转裁剪、清晰度、OCR、公式识别、图形存在性判断、owner 隔离和外部处理同意隐藏在模块内部。
- Adapters: 本地 OCR/图像处理 adapter、外部视觉 adapter 和 deterministic test adapter；Solve Agent 不直接调用供应商或读取文件。
- Trust: 带图题的原图/裁剪是 `QuestionInputBundle` 的一部分，不能在 OCR 后丢弃；视觉理解与 MathVerifier 证据范围分开。
- First slice: `QuestionCapture.prepare/transform/get/content` 隐藏真实格式探测、体积/像素/清晰度、EXIF 方向、owner-scoped SQLite/文件 adapter 和 revision。公开路由只接收图片、来源、私有存储确认与受控 asset ID；浏览器不能提交 owner，也看不到存储路径。新 Solve composer 已接入上传、粘贴、拍照、预览、旋转和裁剪。
- Second slice: `QuestionCapture.recognize/review_recognition` 隐藏本地/外部 OCR adapter、逐次外部同意、结构化题面与 append-only 识别 revision。生产 adapter 包括本地 pix2text、DeepSeek `deepseek-v4-flash-vision-exp` 与 OpenAI 图像模型，DeepSeek 优先级只属于路由装配，不进入业务 interface。识别与具体 media revision 绑定；媒体变化后结果显式 `stale`。教师端能校对普通题面、LaTeX、选项和低置信度区域，但在图形保真与 Solve 消费切片完成前不会把图片或 OCR 草稿交给 Solve。

### Private Question Authoring modules（M8 待开始）

- Seam: `QuestionAuthoring.create_draft(QuestionDesignBrief) -> GeneratedQuestionDraft`，隐藏教材映射、结构化生成、答案/解析一致性、选择题唯一性、MathVerifier、provider 和错误语义。
- Storage seam: `PersonalQuestionLibrary` 独立拥有 owner 私题的个人题库命名、分类、CRUD、revision、导出和删除语义。
- Isolation: `PersonalQuestionLibrary` 不只是公共 `QuestionBank` 的一个 visibility 过滤器；它使用独立业务接口和 owner-isolated storage namespace，没有 publish/share/public/commercial-approved 接口。
- Ownership: current owner 只来自服务端认证上下文；Public Search、Public QuestionBank、后台内容工具、其他 owner、教研组和学校管理员均没有读取接口。
- Management: Agent 生成或提出修改草稿，教师在受认证 UI 中明确保存；编辑、分类、回收站、恢复和永久删除由 owner 直接调用 FastAPI 业务接口，Agent 与后台管理员无永久删除工具。
- Reuse: Curriculum、MathVerifier、RightsGate 和已验证且允许 adaptation 的参考母题可被调用，但不得把辅助命制题复制到公共题库。

### Teacher Agent Runtime module

- Seam: product-owned Python and TypeScript runtime contracts.
- Adapters: `LegacyTeacherAgentRuntime` and isolated DeepSeek Harness runtime.
- Rule: Harness-specific event names and types stop at the adapter. Business callers and tests cross only the product interface.

### Business modules

- Seam: FastAPI module interfaces for QuestionBank, MathVerifier, Curriculum, PrivateLibrary, Paper, Lesson, Similarity and related workflows.
- Implementation: local SQLite/file adapters at the current stage.
- Rule: storage details remain local to these modules so future PostgreSQL/object-storage adapters do not affect UI or Agent interfaces.

## 3. Dependency rules

Allowed:

```text
teacher-web → public FastAPI routes
legacy web → public FastAPI routes
FastAPI routes → business modules
FastAPI runtime adapter → Agent Service
Agent Service → internal Tool gateway
internal Tool gateway → business modules
business modules → their owned storage adapters
QuestionAuthoring → PersonalQuestionLibrary only after owner save confirmation
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

## 4. Primary and legacy UI policy

`apps/teacher-web` is the primary product surface and default `dev:web` target. It owns the new visual language and Agent-first navigation.

`apps/web` is a legacy/reference surface containing mature workflows inherited from `high-school-math-ai`. It remains valuable for business behaviour, regression comparison and gradual extraction, but it is not a design template and does not define whether a new Agent capability is complete.

## 5. Local deployment

- Teacher Web: `127.0.0.1:3001`.
- Legacy Web: `127.0.0.1:3000`.
- FastAPI: `127.0.0.1:8000`.
- Agent Service: `127.0.0.1:4100` when DSH runtime is enabled.

The primary UI should normally call `/api/v1` on its own origin. Next.js rewrites that route to FastAPI using `MATH_AI_API_INTERNAL_URL`, avoiding browser CORS coupling. Direct browser-to-API URLs are an explicit deployment override, not the local default.

## 6. Testing at the seam

- UI adapter tests and type checks target Search/Solve observable progress, completion, same-run recovery, failure and cancellation states, plus both exact same-origin streaming proxies；M6 UI 接入后扩展同一产品接口。
- Search tests target `SearchAgentPipeline` and the HTTP route, not private ranking internals alone.
- Solve tests target 唯一 Tool 证据、可信字段校验、结构化错误、真实 SSE、取消、恢复和 feature gate。
- Private Library tests target owner-scoped 结果、private-by-default、revision、逐次外部处理同意、无正文概览 Tool 与越权失败路径。
- M7 tests target `QuestionCapture` 的图片/公式/图形保真、revision、逐次外部同意、Solve 可观察结果和跨 owner 失败，不测试供应商内部实现。
- M8 tests target `QuestionAuthoring` 与 `PersonalQuestionLibrary` 的可观察接口，强制公共 Search/QuestionBank/后台访问缺失、跨 owner fail closed、owner 管理和永久删除语义。
- Runtime conformance tests exercise both runtime adapters through the product-owned interface.
- Security tests enforce the exact read-only Tool allowlist and absence of database access in `apps/agent`.
- Business tests use synthetic/local adapters and assert published behaviour, rights, verification and privacy invariants.

## 7. Future evolution

Keep the modular monolith. Introduce new network services only when deployment constraints make a seam real. PostgreSQL, object storage, persistent jobs and multi-tenant identity are future adapters; they must not leak into current UI or Agent interfaces. 商业化替换存储 adapter 时必须保留 `PersonalQuestionLibrary` 的独立 namespace 和 owner-only 接口，不能为了统一后台而并入公共题库管理。
