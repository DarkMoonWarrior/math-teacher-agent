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