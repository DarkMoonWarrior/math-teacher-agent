# 商业 V1 · Baseline Test Failure Matrix

- 文档编号：COMMERCIAL-V1 / DOC-07
- 记录日期：2026-08-16
- 适用对象：Commercial Baseline `d88e7a5`（clean snapshot，无 data/pilot|curated）
- 结果：`stabilize/commercial-baseline-v1` 上诊断并修复；修复后 **159 passed / 0 failed / 0 skipped / 0 xfailed**
  （158 = 迁移的原有用例；+1 = KMI-01 换行稳定性回归用例，见 §4）

## 1. 分类定义

| 分类 | 含义 |
| --- | --- |
| A | KMI-01 / line-ending reproducibility |
| B | Missing fixture caused by commercial data exclusion |
| C | Test directly depends on non-commercial / rights-uncertain data |
| D | Path sanitization regression |
| E | Environment / dependency difference |
| F | Real application regression introduced during migration |
| G | Other |

说明：本次 27 个失败中，26 个的**直接依赖对象**是 `data/pilot/` 与 `data/curated/` 中权利未确认的真实数据（分类 C），其**失败表现**是这些目录被商业快照排除后 fixture 缺失（分类 B）。两个分类是同一事实的两个侧面，矩阵中以 `C（表现为 B）` 记录。没有 D、E、F、G 类失败。

## 2. 失败明细（27/27）

| # | 测试 | 错误类型 | 根因 | 受影响生产模块 | 原型(含数据) | 排除数据 | 路径脱敏 | 环境 | KMI-01 | 生产回归 | 分类 | 处理 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | test_http.py::test_question_bank_stats_and_search_endpoints | AssertionError `0 >= 35` | 默认题库未播种：Settings 指向的 `data/pilot` 与 `data/curated` 被 DENY 排除 | routes/questions.py `get_question_bank`、question_bank stats/search | 通过（158/158） | 是 | 否 | 否 | 否 | 否 | C（表现为 B） | synthetic fixtures + conftest 路径覆盖 |
| 2 | test_http.py::test_lesson_plan_generation_and_update_endpoints | CurriculumBaselineError | 封存清单 `catalog_sha256` 为 CRLF 哈希，干净克隆为 LF 文件（KMI-01） | curriculum/baseline.py、routes/lesson_plans.py | 同样失败（干净克隆，上游自带） | 否 | 否 | 否 | 是 | 否 | A | 独立 commit：换行规范化哈希 + 更新清单 |
| 3 | test_question_bank.py::test_batch_import_is_validated_and_idempotent | FileNotFoundError / QuestionBankError | PILOT_BATCH 指向被排除的真实试点批次 | question_bank.import_batch | 通过 | 是 | 否 | 否 | 否 | 否 | C（表现为 B） | synthetic fixtures |
| 4 | test_question_bank.py::test_search_combines_keyword_and_structured_filters | 同上 | 同上 | question_bank.search | 通过 | 是 | 否 | 否 | 否 | 否 | C（表现为 B） | synthetic fixtures |
| 5 | test_question_bank.py::test_teacher_search_scope_excludes_unfinished_questions | 同上 | PILOT_BATCH + SET_CURATION 被排除 | question_bank.apply_curation_package / search | 通过 | 是 | 否 | 否 | 否 | 否 | C（表现为 B） | synthetic fixtures |
| 6 | test_question_bank.py::test_search_supports_complete_module_and_review_work_queues | 同上 | 同上 | question_bank.search / stats | 通过 | 是 | 否 | 否 | 否 | 否 | C（表现为 B） | synthetic fixtures |
| 7 | test_question_bank.py::test_publishable_work_queue_matches_publication_gate | 同上 | 同上 | question_bank.review / search / stats | 通过 | 是 | 否 | 否 | 否 | 否 | C（表现为 B） | synthetic fixtures |
| 8 | test_question_bank.py::test_curation_package_is_independently_verified_and_idempotent | 同上 | 同上 | question_bank.apply_curation_package、math_verifier | 通过 | 是 | 否 | 否 | 否 | 否 | C（表现为 B） | synthetic fixtures |
| 9 | test_question_bank.py::test_probability_composite_questions_are_independently_verified | 同上 | PROBABILITY_CURATION 被排除 | question_bank、math_verifier | 通过 | 是 | 否 | 否 | 否 | 否 | C（表现为 B） | synthetic fixtures |
| 10 | test_question_bank.py::test_remaining_probability_questions_include_source_error_isolation | 同上 | PROBABILITY_CURATION_2 被排除 | question_bank、math_verifier | 通过 | 是 | 否 | 否 | 否 | 否 | C（表现为 B） | synthetic fixtures |
| 11 | test_question_bank.py::test_function_properties_batch_is_imported_verified_and_isolates_open_endpoint_error | 同上 | FUNCTION_PILOT / FUNCTION_CURATION 被排除 | question_bank、math_verifier | 通过 | 是 | 否 | 否 | 否 | 否 | C（表现为 B） | synthetic fixtures |
| 12 | test_question_bank.py::test_teacher_cannot_approve_before_independent_verification | 同上 | PILOT_BATCH 被排除 | question_bank.review | 通过 | 是 | 否 | 否 | 否 | 否 | C（表现为 B） | synthetic fixtures |
| 13 | test_question_bank.py::test_legacy_unverified_approval_is_repaired_on_open | 同上 | 同上 | question_bank 打开修复逻辑 | 通过 | 是 | 否 | 否 | 否 | 否 | C（表现为 B） | synthetic fixtures |
| 14 | test_question_bank.py::test_verified_question_can_be_teacher_approved_and_published | 同上 | PILOT_BATCH + SET_CURATION 被排除 | question_bank.review / publish | 通过 | 是 | 否 | 否 | 否 | 否 | C（表现为 B） | synthetic fixtures |
| 15 | test_question_bank.py::test_teacher_revision_keeps_history_and_resets_only_math_critical_edits | 同上 | 同上 | question_bank.revise | 通过 | 是 | 否 | 否 | 否 | 否 | C（表现为 B） | synthetic fixtures |
| 16 | test_question_bank.py::test_question_images_are_validated_ordered_and_audited | 同上 | 同上 | question_bank.add/update/reorder/delete_image | 通过 | 是 | 否 | 否 | 否 | 否 | C（表现为 B） | synthetic fixtures |
| 17 | test_question_bank.py::test_question_image_rejects_non_image_payload | 同上 | 同上 | question_bank.add_image | 通过 | 是 | 否 | 否 | 否 | 否 | C（表现为 B） | synthetic fixtures |
| 18 | test_question_variants.py::test_verified_single_choice_creates_auditable_private_diagnostic_variant | FileNotFoundError / QuestionBankError | PILOT_BATCH + SET_CURATION 被排除 | question_variants.service、question_bank.create_derived_question | 通过 | 是 | 否 | 否 | 否 | 否 | C（表现为 B） | synthetic fixtures |
| 19 | test_question_variants.py::test_generated_variant_enters_existing_teacher_editing_workflow | 同上 | 同上 | question_variants、question_bank.revise | 通过 | 是 | 否 | 否 | 否 | 否 | C（表现为 B） | synthetic fixtures |
| 20 | test_question_variants.py::test_teacher_custom_variant_is_private_and_does_not_change_source | 同上 | 同上 | question_variants.save_teacher_draft | 通过 | 是 | 否 | 否 | 否 | 否 | C（表现为 B） | synthetic fixtures |
| 21 | test_question_variants.py::test_teacher_scope_only_returns_the_current_teachers_private_variants | 同上 | 同上 | question_bank.search（teacher scope） | 通过 | 是 | 否 | 否 | 否 | 否 | C（表现为 B） | synthetic fixtures |
| 22 | test_question_variants.py::test_admin_revision_flows_to_teachers_after_reverification_without_touching_private_copy | 同上 | 同上 | question_bank.revise / record_manual_verification / search | 通过 | 是 | 否 | 否 | 否 | 否 | C（表现为 B） | synthetic fixtures |
| 23 | test_question_variants.py::test_teacher_can_remove_only_their_own_private_variant_while_admin_can_remove_any_question | 同上 | 同上 | question_bank.change_library_state | 通过 | 是 | 否 | 否 | 否 | 否 | C（表现为 B） | synthetic fixtures |
| 24 | test_question_variants.py::test_unverified_source_and_nonlocal_modes_are_blocked | 同上 | 同上 | question_variants.generate 门禁 | 通过 | 是 | 否 | 否 | 否 | 否 | C（表现为 B） | synthetic fixtures |
| 25 | test_question_variants.py::test_question_variant_http_endpoint_uses_private_draft_workflow | 同上 | 同上 | routes/questions.py variants 端点 | 通过 | 是 | 否 | 否 | 否 | 否 | C（表现为 B） | synthetic fixtures |
| 26 | test_solution_assistant.py::test_solve_exact_verified_bank_question | IndexError（空题库 [0] 越界） | 默认题库未播种（同 #1） | solution_assistant.assistant、question_bank.search | 通过 | 是 | 否 | 否 | 否 | 否 | C（表现为 B） | synthetic fixtures |
| 27 | test_solution_assistant.py::test_short_fragment_cannot_inherit_verified_answer | IndexError（同上） | 同上 | solution_assistant.assistant | 通过 | 是 | 否 | 否 | 否 | 否 | C（表现为 B） | synthetic fixtures |
## 3. 汇总统计

- 总计：27 个失败。
- A（KMI-01 / 行尾可复现性）：**1**（`test_http.py::test_lesson_plan_generation_and_update_endpoints`）。
- C（表现为 B，直接依赖被排除的真实数据）：**26**。
  - `test_http.py`：1（stats/search 端点依赖默认题库播种）
  - `test_question_bank.py`：15
  - `test_question_variants.py`：8（基线文档曾误记为 9，本矩阵为准）
  - `test_solution_assistant.py`：2
- D（路径脱敏回归）：**0**。Prompt 1 的脱敏改动只影响文档/审计文件，未被测试引用。
- E（环境/依赖差异）：**0**。
- F（迁移引入的真实应用回归）：**0**。
  - 佐证 1：用原型 `data/pilot|curated` 数据在商业仓库代码上全新播种，`total=35 / passed=22 / source_inconsistency_detected=4 / needs_math_review=5 / needs_formula_review=4`、模块分布与原型一致。
  - 佐证 2：synthetic fixtures 复现全部 27 个用例断言的导入/校正/统计/发布/变式契约，替换数据后全部通过。
  - 结论：26 个失败是“测试直接依赖被排除数据”造成的可复现性问题，不是迁移改写代码造成的回归。
- G（其他）：**0**。

## 4. 修复与验证

- 26 个数据类失败：建立 `data/test-fixtures/question-bank/` synthetic fixtures（项目自建内容），
  生成器 `scripts/generate_synthetic_test_fixtures.py` 内置自检；测试路径通过
  `apps/api/tests/conftest.py` 环境覆盖与两个测试文件的常量接线到 fixtures。未修改任何业务代码。
- 1 个 KMI-01：`curriculum/baseline.py` 在哈希前按 LF 归一化行尾，封存清单更新为 LF 哈希，
  并新增 `test_curriculum_baseline_hash_is_newline_stable` 回归用例（158 → 159）。
- 最终门禁：backend pytest **159 passed / 0 failed / 0 skipped / 0 xfailed**；
  frontend typecheck / build 通过（见 COMMERCIAL-BASELINE 稳定化记录）。
- 测试数量差异说明：158（迁移原有用例，0 删除 / 0 skip / 0 xfail）+ 1（KMI-01 回归用例）= 159。

## 5. 关联文档

- `KNOWN-MIGRATION-ISSUES.md`：KMI-01（行尾哈希）、KMI-02（测试依赖被排除数据）。
- `data/test-fixtures/README.md` + `MANIFEST.json`：fixture 来源与权利声明。
- `COMMERCIAL-BASELINE.md`：基线快照的原始测试状态（131/27）作为历史记录保留。
