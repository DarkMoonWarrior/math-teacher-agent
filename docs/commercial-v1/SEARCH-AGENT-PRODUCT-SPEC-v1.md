# Search Agent MVP — Product Spec v1

> Prompt 3 历史交付文档 · Commercial Repository: DarkMoonWarrior/math-teacher-agent
> 状态：MVP 已合并并接入 `apps/teacher-web`；当前稳定化状态见 `docs/PROJECT-STATUS.md`。

## 1. 定位

- **Who**：中国高中数学教师。
- **Job**：用自然语言快速找到适合当前教学目的的可信题目。
- **Difference**：不是给传统搜索框套一个 AI。它是「教学意图理解 + 可信检索 + 可解释匹配」：
  教师描述需求，系统理解并结构化教学意图，只返回来自真实题库、经过 Rights / Visibility /
  Publication 门禁和真实验证状态的题目，并明确告诉教师「为什么推荐这些题」。
- 结果必须全部来自真实 Tool / Business Service；LLM 只负责理解需求、制定检索策略和解释结果，
  **绝不负责伪造题库内容**。

## 2. 不可违反的产品原则

1. 所有显示给教师的题目必须具有真实的 `question_id`，来自真实 Tool / Business Service。
2. QuestionBank 没有找到时，如实返回「没有找到完全满足条件的题目」，绝不让模型生成题目补足数量。
3. Rights / Visibility / Publication Gate 永远高于相关性；不可达内容必须在候选流水线中排除。
4. MathVerifier / Verification Status 必须真实展示，不得把 `teacher_review_required` 包装成 `verified`。
5. Hard constraint 绝不静默放宽；Soft preference 的放宽必须结构化披露并在 UI 明示。
6. 来源（年份/地区/考试名/学校）只能来自 Business Service，缺失时显示中性状态，LLM 不得补全。

## 3. SearchIntent（结构化意图，本产品自有 Domain Model）

`SearchIntent` 由确定性解析器（`apps/api/app/modules/search_agent/intent_parser.py`）构建，
不是 LLM JSON 的透传。字段：

- `raw_query` / `subject=math` / `school_stage=high_school`
- `grade`（高一/高二/高三）、`volume`（册）、`book`、`chapter`
- `knowledge_points`、`sub_knowledge_points`
- `question_types`（single_choice / multiple_choice / fill_blank / solution / proof / application）
- `difficulty`（1–5）或 `difficulty_range`
- `requested_count` / `count` / `limit_applied`
- `year_from` / `year_to`、`regions`（省份与全国卷/新高考卷名称）
- `teaching_usage`（classroom_example / in_class_practice / homework / exam_review /
  diagnostic / warm_up / challenge / general）
- `exclude_question_ids` / `exclude_similar_to`、`require_verified`
- `allow_related_fallback`、`deduplicate=true`、`diversify=true`
- `curriculum`（CurriculumMapping：version / textbook / volume / chapter / section /
  `knowledge_point_ids` / `matched_nodes[]`）
- `constraints[]`：每条 constraint 记录 `field / value / strength / origin / confidence / reason`
- `parse_warnings[]`

### Hard / Soft / Default 语义

- `strength = hard | soft | default`，`origin = explicit | inferred | system_default`。
- 典型中文触发词：
  - **hard**：只要 / 必须 / 一定要 / 只能 / 仅要 / 仅限 / 限定 / 严格 / 不要 / 排除 / 避开 / 只收 / 只找
  - **soft**：最好 / 优先 / 尽量 / 偏向 / 偏好 / 如果可能 / 如果有 / 没有的话 / 相近 / 类似 / 也行 / 也可以 / 实在没有
  - 未提供字段 → `default / null`，例如数量默认 5 道并标记 `origin = system_default`。
- 教学用途（如「适合课堂讲解」→ classroom_example）作为 soft 排序偏好，不作为硬过滤条件。

### 数量规则

- 默认 `count = 5`；教师明确指定则遵循。
- 硬上限 `SEARCH_HARD_MAX_COUNT = 20`：要求 100 道时返回结构化
  `requested_count / effective_count / limit_applied=true`，并在 UI 解释「单次最多 20 道」。

## 4. 教材映射（不允许幻觉）

- 教材/章节/知识点只通过真实 Curriculum Catalog（`CsvCurriculumCatalog`，人教 A 版知识树 CSV）
  映射，返回真实 `node_id`；LLM memory 不是教材事实来源。
- 多主题查询命中不同章/册时不臆造单一 `chapter/volume`（例如「导数压轴题」不会被「函数」章污染为 hard 条件）。
- `teacher_text` 保留原话，canonical 映射存于 `SearchIntent.curriculum`。

## 5. SearchPlan（结构化检索计划）

`SearchPlan` 只保存可安全展示的结构化检索决策，**不保存、不暴露模型私有思维过程**。步骤：

1. resolve_curriculum
2. apply_hard_filters
3. search_candidates
4. apply_rights_publication_visibility_gate
5. verification_enrichment
6. deduplicate
7. similarity_diversity
8. difficulty_knowledge_rerank
9. select_top_n
10. generate_explanation

最终 plan 记录 `applied_filters / soft_preferences / relaxations / candidate_count / selected_count`。

## 6. Ranking / Dedup / Diversity（全部可测试规则，无神秘 AI_SCORE）

- **Ranking**（`ranking.score_candidate`）：教材知识点命中 +40、每个知识点词命中 +25、
  子知识点 +20、难度命中 +15 / 相邻 +5 / 不匹配 -20、题型命中 +10、年份命中 +10、
  地区命中 +10、验证通过 +15、需教师复核 +5、非 private 可见性 +5。
- **Dedup**：使用现有 QuestionSimilarity 证据（exact_duplicate /
  same_problem_different_source / same_problem_different_solution，confidence ≥ 0.6），
  每组只保留得分最高的一道；`exclude_similar_to` 也会被聚类排除。默认 `deduplicate=true`。
- **Diversity**：greedy 选择在保持排序优先级的前提下，为新题型 / 新知识点 / 新难度桶加分
  （+6/+6/+4），避免 5 道题高度雷同；不违反 hard constraint。

## 7. 不足与放宽策略

- **Hard 不足**：绝不静默放宽。返回 `exact_match=false` + `unmet_constraints[]`
  （field / requested / matched_count / reason），UI 明示「没有足够完全匹配的题目：要求 N 道，完全匹配 M 道」。
- **Soft 放宽**：允许逐级补充同章节高相关题，但必须写 `relaxations[]`
  （field / from_value / to_value / reason=insufficient_candidates / disclosed=true），
  对应结果带 `relaxed_fields`，UI 显示「相近条件补充」标记与说明，绝不假装全部满足。
- **Zero Result**：返回空结果 + 诚实结论 + safe suggestions（放宽难度/年份/地区、查看相近知识点），
  不自动违反 hard constraint、不生成题目、不捏造 ID。

## 8. 澄清策略

尽量先给有用结果而不是追问：未说明字段使用系统默认（5 道 / 中等 / general），并在「已理解为」
区域展示，教师可修改后重新搜索。Prompt 3 不新增 `ask_user` Tool。

## 9. SearchAgentResponse（输出 Domain Model）

`request_id / session_id / run_id / raw_query / status / intent / plan_summary / results[] /
requested_count / effective_count / returned_count / exact_match_count / exact_match /
relaxations[] / unmet_constraints[] / warnings[] / answer_summary / assistant_explanation /
search_confidence(high|medium|low) / suggestions[] / duration_ms / tool_call_count /
candidate_count / error`。

每个 result：`question_id / stem / stem_preview / question_type / knowledge_points[] /
difficulty / verification_status / source_status / visibility / chapter / section / volume /
year / region / match_reasons[] / relaxed_fields[] / similarity_group / grounded`。
前端不解析 Assistant Markdown，只读结构化字段。

## 10. 可信状态展示（Trust UI）

- 验证状态：`passed / program_verified → 程序验证通过`；`teacher_review_approved → 教师复核通过`；
  `teacher_review_required / needs_math_review / needs_formula_review → 需要教师复核 / 待数学验算 / 待公式校正`；
  其余 → `未验证`。不使用「100% 正确 / 绝对可信 / 官方认证」。
- 来源状态：`commercial_granted / public_permissive / question_content_user_declared_usable → 来源已记录`；
  `rights_unclear → 权利待审核`；缺失 → `来源信息暂缺`（中性状态，不由 LLM 补全）。
- `match_reasons` 来自结构化流水线，LLM 只能转述，不能编造事实依据。

## 11. 本阶段明确不做

Solve Agent（不做「用户提交新题 → AI 完整解题」）、Paper Agent、Teacher Memory、
账号/支付系统。Search 结果只展示题库中已有的解析/验证摘要。

## 12. 数据边界

- 开发/测试只使用 `data/test-fixtures/search-agent/` 中 project_created 的 synthetic fixtures
  （provenance 记录在 `data/test-fixtures/MANIFEST.json`）。
- synthetic fixture 仅用于测试/开发，**不会**在生产 Search Agent 中默认展示给真实教师。
- `data/commercial-approved/` 保持为空（仅 README）。
