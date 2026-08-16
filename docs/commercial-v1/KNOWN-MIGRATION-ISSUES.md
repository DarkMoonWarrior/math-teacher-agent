# 商业 V1 迁移 · Known Migration Issues

- 文档编号：COMMERCIAL-V1 / DOC-05
- 记录日期：2026-08-16
- 用途：记录 Prompt 0 审计发现的已知问题。本文件只记录，不修改业务代码；
  每个问题在项目所有者确认并进入对应开发阶段后才落地修复。

## KMI-01 课程封存基线哈希受 CRLF/LF 影响（Prompt 0 发现）

- 状态：**Open（已记录，未修复）**
- 受影响文件：
  - `apps/api/app/modules/curriculum/baseline.py`（哈希计算未归一化行尾）
  - `docs/high-school-math-ai/curriculum/pep-a-sealed-baseline-v1.json`（`catalog_sha256` 与仓库文件不符）
  - 行为影响：`routes/lesson_plans.py` 的教案生成/导出链路
- 根因：封存清单中的 `catalog_sha256 = f982b884...` 是在 Windows CRLF 工作副本上计算的；
  而仓库 `.gitattributes` 规定 `*.csv text eol=lf`，任何干净克隆得到的规范文件哈希为
  `5c949611...`，两者永远不相等。
- 触发条件：在干净克隆（或任何按 LF 检出 CSV 的环境）上触发教案相关流程
  （`CurriculumBaseline.load`）。
- 当前表现：`CurriculumBaselineError: 人教 A 版课程目录已偏离封存基线，已拒绝用于教案生成`；
  `test_http.py::test_lesson_plan_generation_and_update_endpoints` 在干净克隆上失败
  （其余 157 个测试通过）。这是上游 HEAD 自带状态，非本次审计引入。
- 推荐修复方式（二选一，实施时再定）：
  1. 代码侧：`baseline.py` 哈希前按 LF 归一化行尾（`replace(b"\r\n", b"\n").replace(b"\r", b"\n")`），
     并把清单 `catalog_sha256` 更新为规范 LF 哈希 `5c94961195771fc225133ba19d64b6771f228b15c1fe8af1358d59c308454bfa`。
  2. 仅数据侧：保持代码不变，只把清单哈希更新为 LF 哈希（跨平台稳定性弱于方案 1）。
- 为什么当前没有修改：Prompt 0 的任务边界明确规定"不修改业务代码、不改变当前行为"；
  审计期间的临时修复已按要求恢复到初始 HEAD。
- 建议修复阶段：Prompt 1 建立商业仓库基线时，作为第一个独立小提交处理，并同步更新
  `COMMERCIAL-SNAPSHOT-WHITELIST.md` 中的迁移说明；修复后必须重新跑全量后端测试确认
  教案链路 158/158 全绿。
- 安全影响：无。该问题不涉及数据损坏、密钥或权限；只影响教案功能在干净克隆上的可用性。
- Commercial Baseline 实测：新仓库中 `test_http.py::test_lesson_plan_generation_and_update_endpoints`
  失败（Expected Baseline Failure，未修复）。

## KMI-02 测试依赖被排除的真实数据（Prompt 1 发现）

- 状态：**Fixed（Prompt 1.5 / stabilize/commercial-baseline-v1，synthetic fixtures 方案）**
- 受影响文件：
  - `apps/api/tests/test_question_bank.py`（15 个用例）
  - `apps/api/tests/test_question_variants.py`（8 个用例）
  - `apps/api/tests/test_solution_assistant.py`（2 个用例）
  - `apps/api/tests/test_http.py::test_question_bank_stats_and_search_endpoints`（1 个用例）
- 根因：这些测试直接读取 `data/pilot/batch-2026-08-001-30q.json` 与
  `data/curated/*-corrections-v1.json` 等真实试点数据；Prompt 1 的 DENY BY DEFAULT
  政策排除了这些数据目录，导致 fixture 缺失。
- 触发条件：在任何不包含原 `data/pilot|curated` 内容的干净仓库中运行后端测试。
- 当前表现：27 个失败中的 26 个（另 1 个为 KMI-01）。
- 为什么当前没有修改：不允许把真实第三方题目复制进 fixture 让测试通过；
  Prompt 1 边界不允许为迁移大规模重写测试。
- 推荐处理方式（按优先级，需项目所有者确认后以独立提交落地）：
  1. 为各测试组建立 synthetic fixture（保持题目结构与验证语义等价，不含第三方内容）；
  2. 或对数据依赖用例增加 `skipif`（fixture 缺失时跳过并输出明确原因）；
  3. 或把这些用例改为只在新数据审查流中随数据一起运行。
- 建议修复阶段：Prompt 1 验收后，作为基线后的独立测试策略提交（见 POST-BASELINE-BACKLOG B-14）。
- 实际修复（Prompt 1.5，独立 commit）：
  1. 建立 `data/test-fixtures/question-bank/` synthetic fixtures（全部项目自建内容，见
     `data/test-fixtures/README.md` 与 `MANIFEST.json`）；
  2. 生成器 `scripts/generate_synthetic_test_fixtures.py` 内置与迁移测试断言一致的自检；
  3. `apps/api/tests/conftest.py` 以 `MATH_AI_*` 环境变量把 Settings 数据路径覆盖到 fixtures，
     `test_question_bank.py` / `test_question_variants.py` 常量改为 fixture 路径；
  4. 未删除/跳过/xfail 任何用例，未降低任何断言，未绕过 RightsGate/MathVerifier/private 边界；
  5. 详细失败矩阵见 `BASELINE-TEST-FAILURE-MATRIX.md`（26 个数据类失败 + 1 个 KMI-01）。
