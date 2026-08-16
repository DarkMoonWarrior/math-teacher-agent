# Prompt 3 Acceptance

> Search Agent MVP 验收记录 · 生成日期 2026-08-16 · 分支 feat/search-agent-mvp-v1（Draft PR，未合并）

## 1. 验收 Gate（Prompt 3 §65 A–M）

| Gate | 结论 |
|---|---|
| A. LLM 不能伪造题目 | ✅ 题目只能来自 Tool 证据并经 get_question 再读取；无生成路径 |
| B. 所有 Question ID Grounded | ✅ validate_response_grounding + 未核实 ID 丢弃/消毒 |
| C. 所有 Source Grounded | ✅ source/year/region 由 Business Service enrichment 覆盖，LLM 说法不生效 |
| D. 所有 Verification Grounded | ✅ 同上；ensure_no_fabricated_fields 校验枚举 |
| E. Hard Constraint 不 Silent Relax | ✅ 不足时 exact_match=false + unmet_constraints[]；eval 0/26 违规 |
| F. Soft Relaxation 必须 Disclosure | ✅ relaxations[] + relaxed_fields + UI「相近条件补充」；eval 0/1 未披露 |
| G. Rights Gate 不绕过 | ✅ 只走 QuestionBank 现有 Rights/Visibility/Publication 业务路径 |
| H. MathVerifier Status 不伪造 | ✅ 状态真实映射，teacher_review_required 不包装成 verified |
| I. Tool Allowlist 仍然 EXACTLY 5 | ✅ search_questions/get_question/find_similar_questions/verify_question/get_curriculum_node（自动测试强制） |
| J. Agent 无 DB Access | ✅ apps/agent 无 SQLite/SQL/DB connector，DB access guard 保持绿 |
| K. Search 是 Read Only | ✅ 无任何写 Tool；read-only 集成测试 |
| L. 现有 Search 不被破坏 | ✅ /search 页面仅新增教师入口链接；传统检索 API/行为不变 |
| M. 现有全部 Tests 继续通过 | ✅ 见下 |

## 2. 测试结果

- Backend 原有（Prompt 2.5 基线）184 tests：全部通过
- Backend 新增 40 tests：全部通过
  - domain 14 · pipeline 17 · API 7 · eval 2（eval 内 50 cases / 139 checks）
- Agent 原有 28 tests：全部通过
- Agent 新增 1 test（search-scenario DSH E2E）：通过 → 29/29
- `pnpm typecheck:web`：通过
- `pnpm build:web`：通过（含新路由 /search/agent 静态生成）
- `pnpm typecheck:agent` / `pnpm build:agent`：通过
- 总计 backend：224 passed / 0 failed / 0 skipped / 0 xfailed

## 3. UI 状态矩阵（人工验证清单）

页面 `/search/agent`（`apps/web/app/search/agent/page.tsx`）实现并覆盖以下状态：

- 自然语言输入 + 示例快捷填充；Loading（spinner + 取消按钮）；Cancel（AbortController）；
  Error（结构化 code/message + 针对 FEATURE_DISABLED / UNSUPPORTED_CAPABILITY /
  RUNTIME_UNAVAILABLE 的提示）+ Retry
- Success：意图 chips（「已理解为」，标注 必须/偏好/默认）+ 结果卡片
- Partial match：unmet_constraints 红框「没有足够完全匹配的题目」
- Relaxation notice：amber 框「有 N 处软偏好使用了相近条件补充」+ 逐条放宽明细 + 卡片「相近条件补充」标记
- Empty result：诚实空状态 + suggestions
- Runtime unavailable：错误态与重试
- 验证/来源信任徽章、match_reasons、检索结论、结构化 SearchPlan 过程（无思维链）

## 4. 数据与安全

- `data/commercial-approved/`：仍为空（仅 README）
- 新 fixtures 全部 synthetic / project_created，provenance 写入 `data/test-fixtures/MANIFEST.json`
- Secret/数据扫描：无 API Key、无 .env、无 PDF/DOCX、无 SQLite、无 node_modules、
  无 DSH 本地状态进入 tracked tree；`git status` 干净（仅本阶段白名单文件）
- Live Smoke：未执行（默认不运行、不产生费用）

## 5. Known Limitations

- UI 主流程使用同步 POST；runtime 级 SSE 已实现并有后端测试，渐进式 UI streaming 后续统一。
- teaching_usage 只作排序信号；in-memory run 记录；真实商业题库未导入（线上以 rights-reviewed 数据为准）。
- 商业仓库当前无教师真实身份系统，session 为客户端生成的前缀 id，未来接入 Minimal Identity Boundary。

## 6. 下一步

验收通过后进入 Solve Agent MVP 规划；本阶段不 merge main、不开始 Solve Agent。
## 7. Prompt 3.5 最终验收（Trusted Search Agent Final Verification & Merge Gate）

- 日期：2026-08-16
- PR：#3（Draft → Ready for review）https://github.com/DarkMoonWarrior/math-teacher-agent/pull/3
- Merge SHA：`0c59b77e347b7820cc97b0c7dc5ea46de3fb3cf2`
- main HEAD（merge 后）：`0c59b77e347b7820cc97b0c7dc5ea46de3fb3cf2`
- Tag：`search-agent-mvp-v1.0`（annotated，指向 0c59b77；Tag message: Trusted Teacher Search Agent MVP before Solve Agent integration）

### 7.1 独立验收 Gate

| Gate | 结果 |
| --- | --- |
| Overfitting audit | 无硬编码：生产代码无 eval query 字符串 / KNOWN_EVAL / query 分支；eval 文本仅存在于 fixture 与测试 |
| Holdout Evaluation | 27 条新 synthetic query（`holdout-cases.json`，与原 50 条不重复）；Intent Field Accuracy **270/278 = 0.971**；hard/soft 21/21=1.000；count 26/26=1.000；teaching usage 3/5=0.600（真实弱点）；curriculum mapping 39/39=1.000 |
| Hard Constraint Silent Violation | 0（原 50 条 0/26；holdout outcome 用例 0） |
| Fake Question ID / Source / Verification Hallucination | 0 / 0 / 0 |
| Explanation Grounding | 通过：assistant 解释中未核实年份/验证声明消毒；answer_summary / match_reasons 由结构化结果生成（grounding.py 扩展 + 测试） |
| Production Fixture Isolation | 通过：生产模块不引用 test-fixtures；默认 bank 在 data/runtime；空生产 bank → 0 results 诚实空态；commercial-approved 仅 README/policy |
| Rights / Visibility / Read-only | 通过（原有 224 测试继续全绿） |
| Tool Allowlist / DB Guard | EXACTLY 5；apps/agent 无 DB 访问 |
| Prompt Injection / Search Limit | 通过；count 硬上限 20 + limit_applied；**Tool Loop Gate 新增**：`MATH_AI_SEARCH_TOOL_CALL_LIMIT`（默认 6），反复 search → `SEARCH_PLAN_EXHAUSTED`（`apps/agent` E2E 测试） |
| Feature Flag | `MATH_AI_SEARCH_AGENT_ENABLED` 默认 false；关闭时 4 个端点 404 `FEATURE_DISABLED`，传统搜索不受影响 |

### 7.2 合并前/后最终测试

- Backend（合并前与合并后 main 各跑一次）：**233 passed / 0 failed / 0 skipped / 0 xfailed**
  （224 原有 + holdout 3 + isolation 4 + grounding 2）
- Agent：**30 passed / 0 failed**（29 + loop guard 1）；typecheck / build 通过
- Web：`pnpm typecheck:web` 通过；`pnpm build:web` 通过
- 全部使用 deterministic mock provider，无真实 DeepSeek API 调用、无费用

### 7.3 UI 人工验证矩阵（Known Test Debt）

页面 `/search/agent`（`apps/web/app/search/agent/page.tsx`）人工验证覆盖：

Natural Query → Loading → Success → Partial Match（unmet_constraints）→
Soft Relaxation（相近条件补充 + 披露）→ Hard Shortage（exact_match=false + 说明）→
Zero Result（诚实空态 + suggestions）→ Runtime Unavailable（RUNTIME_UNAVAILABLE 结构化错误 + Retry）→
Cancel（AbortController）→ Retry → Feature Disabled（FEATURE_DISABLED）→
Malformed API Response（结构化错误渲染）。

**明确记录：当前 Web 项目没有自动化浏览器/UI 测试框架，本阶段未为单页面引入大型测试框架；
上述矩阵为人工验证清单，不是自动化覆盖 —— Known Test Debt。**

### 7.4 Known Limitations（Prompt 3.5 后）

- 解析器真实弱点（holdout 首轮成绩，非硬编码，Backlog B-16..B-19）：负向题型语义反转（`不要填空题`）、
  `稍难` 粒度、`例题/复习` 用途裸词、相对年份不支持；修复需重跑 50+27 全部用例并经项目所有者确认。
- assistant 解释可机械消毒 题目ID/年份/验证声明；学校名/考试名等自由格式实体需 NL 事实抽取（B-20）。
- `data/commercial-approved/` 仍为空（仅 README）；Search Agent 无真实题库可搜时诚实返回 0 results。