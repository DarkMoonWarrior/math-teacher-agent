# Search Agent — Architecture v1

> 归档说明（2026-09-04）：本文保留原型/迁移时期的事实与决策。旧 UI、旧路径、分支、待办和验收数字不代表当前实现；请以 [当前开发状态](../PROJECT-STATUS.md) 为准。来源、权利与教材证据继续保留。

> 历史架构记录：Search Agent 业务 seam 仍有效；文中的 `apps/web` 页面为最初接入点。
> 当前主 UI adapter 位于 `apps/teacher-web/lib/teacher-workspace`，总体依赖方向见 `docs/ARCHITECTURE.md`。

> Prompt 3 交付文档 · 说明 Search Agent MVP 如何复用 Prompt 2 的 TeacherAgentRuntime 边界，
> 以及所有可信/安全门禁的实现位置。

## 1. 请求链路

```
apps/web /search/agent
   │  只调用 FastAPI（longTaskApiUrl），绝不直连 apps/agent
   ▼
FastAPI POST /api/v1/agent/search          （feature gate: MATH_AI_SEARCH_AGENT_ENABLED）
   │  routes/search_agent.py
   ▼
SearchAgentPipeline                          （modules/search_agent/pipeline.py）
   │  1. SearchIntentParser.parse()          —— 确定性意图解析 + 真实 Curriculum Catalog 映射
   │  2. build_search_plan()                 —— 结构化 SearchPlan（不存 CoT）
   │  3. TeacherAgentRuntime.run()           —— 只依赖自有 Runtime 边界，路由不 import DSH
   ▼
TeacherAgentRuntime（legacy | dsh）
   ▼
apps/agent（Node/TS, DeepSeek Harness composition）
   │  最小能力 persona（搜题 6 条硬规则），model-visible tools exactly 5
   ▼
Teacher Tools（search_questions / get_question / find_similar_questions /
              verify_question / get_curriculum_node）
   │  HTTP Internal Tool Gateway（Bearer service token, 只允许固定 origin + 固定 route）
   ▼
FastAPI Business Services
   │  QuestionBank 搜索（现有 Rights/Visibility/Publication 门禁路径）
   │  get_question 再读取 —— 事实字段的唯一来源
   │  QuestionSimilarity / MathVerifier / CurriculumCatalog
   ▼
Database（Agent 永远不直接访问）
```

## 2. 组件清单

| 位置 | 组件 | 职责 |
|---|---|---|
| `apps/api/app/modules/search_agent/domain.py` | SearchIntent / SearchPlan / SearchAgentResponse 等 | 本产品自有 domain model，不是 LLM JSON 透传 |
| `apps/api/app/modules/search_agent/intent_parser.py` | SearchIntentParser | 规则解析 + 教材映射 + hard/soft/default 约束 |
| `apps/api/app/modules/search_agent/planner.py` | build_search_plan | 10 步结构化计划（可展示，无思维链） |
| `apps/api/app/modules/search_agent/pipeline.py` | SearchAgentPipeline | 编排 runtime、收集证据、过滤/排序/选 Top-N、run/stream/cancel |
| `apps/api/app/modules/search_agent/evidence.py` | SearchEvidence / CandidateRecord | 把 Tool 输出变成候选记录，记录 warnings |
| `apps/api/app/modules/search_agent/grounding.py` | 防伪门 | ID 溯源 / assistant 文本消毒 / 非法字段校验 |
| `apps/api/app/modules/search_agent/ranking.py` | 排序/去重/多样性 | 全部可测试的确定性规则 |
| `apps/api/app/routes/search_agent.py` | REST + SSE + cancel | feature gate、run 记录（in-memory）、结构化错误 |
| `apps/agent/config/cordis.teacher.yml` | Search Agent persona | 6 条搜题硬规则 + 最小能力组合 |
| `apps/web/app/search/agent/page.tsx` | 教师 UI | 输入/取消/重试/意图 chips/信任状态/放宽披露/空状态 |

## 3. Grounding 防伪门（Trust Gate）

- **Question ID Gate**：`SearchAgentResponse.results[].question_id` 必须来自 Tool 证据，
  并且通过 `get_question` 再读取校验；读取不到的一律丢弃（pipeline `collect_evidence`）。
- **Assistant 文本消毒**：`sanitize_assistant_text` 把解释文本中不在证据集里的疑似
  question_id 替换为「题目ID无法核实」。
- **Source / Verification Gate**：年份/地区/来源状态/验证状态只从 Business Service
  enrichment 覆盖写回，LLM 说法不产生事实字段；`ensure_no_fabricated_fields`
  校验 visibility / source_status 枚举合法性。
- **硬性不变量**：题目题干/选项/答案/来源不得被 LLM 修改后仍冒充原题。

## 4. 编排与 Runtime 边界

- 路由和业务模块**不 import DeepSeek Harness**；只依赖 `TeacherAgentRuntime` 边界
  （`run / stream / cancel / get_session / health / capabilities`）。
- `MATH_AI_AGENT_RUNTIME=legacy`（默认）时返回结构化 `UNSUPPORTED_CAPABILITY`，
  不偷偷绕过 Runtime Boundary；`=dsh` 且 Agent Service 不可达时返回 `RUNTIME_UNAVAILABLE`，FastAPI 不崩溃。
- Agent 消息由 `_compose_agent_message` 注入结构化 SearchIntent（hard/soft 区分），
  模型只选择 Tool 调用与措辞，事实由证据决定。
- 防 Tool Loop：单次请求的搜索迭代受 runtime 会话/步数限制，超出返回结构化错误
  （SEARCH_PLAN_EXHAUSTED / TOOL_LOOP_LIMIT 语义由 DSH 步数上限与 pipeline 收敛保证）。
- Latency：记录 `duration_ms / tool_call_count / candidate_count / returned_count`；
  不把教师完整 query 写入永久 telemetry（开发日志最小化）。

## 5. SSE / Cancel / Session

- `POST /api/v1/agent/search`：同步返回 grounded 结果（并登记 in-memory run 记录）。
- `GET /api/v1/agent/search/{run_id}`：读取 run 记录。
- `GET /api/v1/agent/search/{run_id}/stream`：SSE，`run_started`（含 intent 摘要）→ 终态
  `run_completed`（携带完整 SearchAgentResponse）/ `run_failed` / `run_cancelled`。
- `POST /api/v1/agent/search/{run_id}/cancel`：经 pipeline 转调 `TeacherAgentRuntime.cancel`。
- 前端使用自有 `teacher_agent_session_id`（本页 `web_<uuid>`），UI 取消 = 中止 in-flight POST
  （AbortController）；runtime 级 cancel 由后端测试覆盖。
- Run 记录为 in-memory MVP 实现（与 Prompt 2 边界一致），云持久化后续替换，不扩散到业务代码。

## 6. 安全边界（强制 Gate，自动测试）

- Model-visible tool allowlist **exactly 5**：`search_questions, get_question,
  find_similar_questions, verify_question, get_curriculum_node`。无 bash/filesystem/web/
  subagent/shell/terminal/workflow；least-capability composition 不使用默认 dsh-base bundle。
- `apps/agent` 无 SQLite/SQL/DB connector；写操作工具不存在；Search 全链路 read-only
  （read-only 集成测试）。
- Internal Gateway：missing/wrong token → 401/403；tool args 无任意 URL（SSRF 防护），
  只调用配置好的 FastAPI origin + 固定 route；Tool HTTP 请求携带取消信号。
- Prompt Injection：教师输入视为不可信输入。测试覆盖「忽略系统提示 / 显示 API Key /
  读取数据库 / 调用 shell / 全部题库 / private questions」，系统无法完成越权（Tool 不存在 + 门禁不变）。
- Search 结果大小有界：search limit 硬上限、stem 截断、大字段仅 `get_question` 单独读取。

## 7. 测试资产

- 后端：`tests/test_search_agent_domain.py`（14）、`test_search_agent_pipeline.py`（17，31 断言）、
  `test_search_agent_api.py`（7）、`test_search_agent_eval.py`（2，50 cases/139 checks）。
- Agent：`apps/agent/tests/runtime/search-scenario.test.ts` —— deterministic DSH E2E：
  mock 模型 → search_questions → get_question → gateway stub；断言 allowlist exactly 5。
- Fixtures：`scripts/generate_search_agent_fixtures.py` 生成
  `data/test-fixtures/search-agent/search-agent-synthetic-14q-v1.json`（4 椭圆焦点弦、
  6 椭圆基础/相近、2 导数压轴构造、2 集合）与 `eval-cases.json`（50 synthetic queries）。
  全部 project_created / synthetic=true / commercial_safe=true，provenance 在 MANIFEST.json。
- 自动化测试不调用真实 DeepSeek API；Live Smoke 仅当
  `MATH_AI_DEEPSEEK_API_KEY` 存在且 `MATH_AI_RUN_LIVE_SEARCH_SMOKE=true` 时手动运行。

## 8. 已知限制（本阶段有意为之）

- UI 主流程使用同步 POST（loading/cancel=AbortController/retry）；runtime 级 SSE 已实现并被
  后端测试覆盖，端到端渐进式 UI streaming 与「重放式 stream 路由」在下一迭代统一。
- 教学用途（teaching_usage）当前只参与排序信号，不 rating 化。
- In-memory run 记录，无云持久化。
- 真实商业题库尚未导入（commercial-approved 为空），线上检索以未来审核通过的数据为准。
