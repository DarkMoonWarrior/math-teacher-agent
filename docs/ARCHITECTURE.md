# 当前架构与模块 seam

更新日期：2026-08-21

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
- Interface: UI submits a teaching task and receives product-owned progress stages, structured results and errors.
- Adapter: current HTTP adapter consumes the same-origin Search SSE route, exposes only `connecting / understanding / searching / checking / recovering` progress, returns one structured result, and maps `AbortSignal` to explicit run cancellation.
- Recovery: after a transport interruption with a known `run_id`, the adapter performs one read-only `GET /api/v1/agent/search/{run_id}/stream` snapshot lookup. It never repeats the Search `POST` or Tool execution; a snapshot without a saved terminal state becomes `STREAM_RECOVERY_FAILED`.
- Transport: `apps/teacher-web/app/api/v1/agent/search/stream/route.ts` is an exact no-buffer streaming proxy to FastAPI; other same-origin API paths continue to use the general Next.js rewrite.
- Rule: React views do not know SSE parsing, backend storage, Harness events, provider payloads, or raw database fields.

### Search Agent module

- Seam: `SearchAgentPipeline.run/stream/cancel` and `SearchAgentResponse`.
- Implementation: deterministic intent parsing, grounded curriculum mapping, rights/visibility gate, verification enrichment, deduplication, ranking, diversity and explanation sanitization.
- Lifecycle: `POST /api/v1/agent/search/stream` executes one real runtime stream; `run_id` is registered before delivery, disconnect/cancel reaches the same in-flight run, and later snapshot reads never execute the query again.
- Trust: model deltas and Tool input/output remain inside FastAPI; the browser receives only payload-free progress events and the final grounded `SearchAgentResponse`.
- Rule: structured business results are the source of truth; model prose cannot add facts.

### Solve Agent module（M5 开发中）

- Seam: `SolveAgentWorkflow.run/stream/cancel/resume`、`SolveAgentCommand` 与 `SolveAgentResponse`。
- Lifecycle: FastAPI 公开接口拥有同步执行、单次真实 SSE、进程内 run 快照、在途取消与同 session 恢复；路由和业务模块均不 import Harness 类型。
- Trust: 一次成功 run 必须且只能包含一次成功的 `solve_question` Tool 调用；最终 `SolutionResult` 只从该结构化输出建立。模型自由文本、额外 Tool 调用、失败 Tool 伪装的成功 payload、可信等级与验证证据冲突都会被拒绝。
- Exposure: 浏览器只接收无原始 input/output 的 Tool 进度和结构化终态；`math_verification` 的 status、capability、scope 和 evidence source 由业务模块拥有。
- Current boundary: 后端工作流已实现但 feature gate 默认关闭；`apps/teacher-web` 尚未接入，因此 M5 尚未完成。

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
```

Forbidden:

```text
teacher-web → Agent Service
teacher-web → database
Agent Service → database or private files
Agent Service → public browser routes
business modules → DeepSeek Harness
private data → public/commercial data without an explicit authorization workflow
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

- UI adapter tests and type checks target `TeacherWorkspace` observable progress, completion, failure and cancellation states, plus the exact same-origin streaming proxy.
- Search tests target `SearchAgentPipeline` and the HTTP route, not private ranking internals alone.
- Solve tests target 唯一 Tool 证据、可信字段校验、结构化错误、真实 SSE、取消、恢复和 feature gate。
- Runtime conformance tests exercise both runtime adapters through the product-owned interface.
- Security tests enforce the exact read-only Tool allowlist and absence of database access in `apps/agent`.
- Business tests use synthetic/local adapters and assert published behaviour, rights, verification and privacy invariants.

## 7. Future evolution

Keep the modular monolith. Introduce new network services only when deployment constraints make a seam real. PostgreSQL, object storage, persistent jobs and multi-tenant identity are future adapters; they must not leak into current UI or Agent interfaces.
