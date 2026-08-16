# Prompt 2 验收记录（Teacher Agent Runtime Foundation + DSH Read-Only Integration）

阶段：Prompt 2 v2
分支：`feat/teacher-agent-runtime-v1`
基线：main `514afc1`（tag `commercial-baseline-v1.0-stable`）
验收日期：2026-08-16

## 目标达成情况

| 验收项 | 状态 |
| --- | --- |
| TeacherAgentRuntime 自有接口（run/stream/cancel/resume/get_session/health/capabilities） | 达成（Python Protocol + Node 实现） |
| LegacyTeacherAgentRuntime 默认、行为不变 | 达成（原 159 测试全部保持通过） |
| DeepSeekHarnessRuntime 经独立 Agent Service | 达成 |
| DSH 官方公开扩展机制（boot / Cordis plugin / defineTool / agents API） | 达成 |
| 5 个只读 Teacher Tools 经 FastAPI Internal Tool Gateway | 达成 |
| Agent 不直接访问数据库（静态门禁测试） | 达成 |
| M2M 双方向认证（两个独立 token，fail closed） | 达成 |
| 固定内部地址、模型不可提供 URL（防 SSRF） | 达成 |
| 结果大小限制（search/similar hard max 20） | 达成 |
| 产品自有事件词汇表 streaming | 达成 |
| cancel 中止在途工具请求 + RUN_CANCELLED（E2E 测试） | 达成 |
| resume（官方 ctx.agents.resume + JSONL 持久化，跨实例测试） | 达成（capabilities.resume=true） |
| deterministic DSH E2E（mock model 真穿 Harness） | 达成 |
| model-visible tool allowlist 自动测试 | 达成（强制安全 Gate） |
| DSH failure isolation（legacy 不受影响 / dsh 不可达 → RUNTIME_UNAVAILABLE） | 达成 |
| 不新增用户功能、不改 UI、不改现有 API | 达成 |
| DSH 精确 pin + 集成锁定文档 | 达成（0.1.0-rc.6，DSH-INTEGRATION-LOCK.md） |

## 测试结果

- Backend pytest：184 passed（原 159 + 新增 25），0 failed / 0 skipped / 0 xfailed。
- apps/agent：typecheck passed；vitest 22 passed（5 个测试文件）。
- Frontend：typecheck passed；build passed。

## 能力矩阵

| 能力 | 状态 |
| --- | --- |
| run | true |
| stream | true |
| cancel | true |
| resume | true（依赖 DSH 官方 sessionPersistence；breaking 时降级为 false 并记录） |
| get_session | true |
| health | true |
| model-visible tools | search_questions / get_question / find_similar_questions / verify_question / get_curriculum_node（恰好 5 个） |
| bash / filesystem / web / subagent / workflow | 无（测试强制） |
| 写工具 | 无（第二批只设计不实现） |

## 已知限制

- `get_session.run_ids` 为进程内记录（跨进程不聚合历史 run）。
- 未做 UI streaming / Search Agent / Solve Agent / Paper Agent / Lesson Agent / Teacher Memory。
- DSH 为 Developer Preview，升级政策见 `DSH-INTEGRATION-LOCK.md`。
- 手动真实模型 smoke test 需显式配置 `MATH_AI_DEEPSEEK_API_KEY` +
  `MATH_AI_AGENT_PROVIDER=deepseek-official`，默认不运行。

## 下一步（Prompt 3 候选，不在此阶段执行）

- Search Agent MVP（在 5 个只读工具之上编排搜索工作流）。
- 第二批写工具（create_paper_draft / create_lesson_draft / create_question_variant /
  import_private_resource）仍为 draft，且不得绕过 RightsGate / MathVerifier / Teacher Review。
