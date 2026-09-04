# Commercial V1 · Clean Snapshot Baseline

> 归档说明（2026-09-04）：本文保留原型/迁移时期的事实与决策。旧 UI、旧路径、分支、待办和验收数字不代表当前实现；请以 [当前开发状态](../PROJECT-STATUS.md) 为准。来源、权利与教材证据继续保留。

- 建立日期：2026-08-16
- 原 Prototype 仓库：`https://github.com/DarkMoonWarrior/high-school-math-ai`（Public）
- Snapshot 原 commit SHA：`1de7d4a`（记录 SHA 仅为 provenance，**不代表继承原 Git 历史**）
- Snapshot 策略：Strategy B — Clean Snapshot（新仓库、新 Git 历史、单一商业基线提交）

## 1. 迁移范围（163 个文件 + 6 个审计文档）

- `apps/web/**`（Next.js 教师工作台）
- `apps/api/app/**`、`apps/api/tests/**`、`apps/api/pyproject.toml`（FastAPI 业务与测试）
- 根配置：`package.json`、`pnpm-workspace.yaml`、`pnpm-lock.yaml`、`.gitattributes`、`.env.example`
- `docs/high-school-math-ai/`：architecture、audits、rights、research、ui、question-schema、
  question-review-media、DEVELOPMENT-BOUNDARY-AND-ROADMAP-v2、curriculum（全量 CSV + 封存清单）
- `docs/commercial-v1/**`（Prompt 0/0.5 审计文档 + 本基线文档）
- `scripts/`：6 个活跃数据工具（pilot 一次性脚本不迁移）

完整依据：`COMMERCIAL-SNAPSHOT-WHITELIST.md`。

## 2. 排除范围（DENY BY DEFAULT）

- `data/pilot/**`、`data/curated/**`、`data/source-pairs/**`（未审核题库内容）
- `data/runtime/**`、`data/private-runtime/**`（运行时数据库与私人资料）
- `<LOCAL_CORPUS_PATH>/**` 全部原始 PDF 及任何本机语料
- `docs/high-school-math-ai/audits/batch-2026-08-001-technical-audit.csv`
  （含原 PDF 提取的题目/解析正文样本，比白名单更严格地排除，见 PATH-SANITIZATION-LOG）
- `docs/high-school-math-ai/PRD-v0.1.md`、`PROJECT-BASELINE-v1.md`、
  旧版必修一 CSV、pilot 构建/校验脚本（LEGACY，留档原公开仓库）
- `.env`、任何密钥/token、PDF/DOCX/上传文件、SQLite/DB、缓存与生成物（`node_modules`、`.venv`、`.next`、`output/` 等）

## 3. 数据政策

- `data/commercial-approved/`：初始为空；只接受通过 RightsGate + MathVerifier + Teacher Review 的内容。
- `data/quarantine/`：仅策略文件；来源或权利不明内容一律隔离，默认不可商用。
- `data/private-runtime/`：gitignored；教师私人运行时数据永不入库。
- `data/test-fixtures/`：仅允许 synthetic、项目自建、权利明确用于测试的数据。
- 任何内容进入商业数据集前必须满足 `DATA-RIGHTS-MIGRATION-REVIEW.md` 的出口条件。

## 4. 路径与标识脱敏

- 本机语料路径统一替换为 `<LOCAL_CORPUS_PATH>`、`<PROTOTYPE_WORKSPACE>`；
  私人 PDF 文件名统一替换为 `<FILE:USRPDF-001>` ~ `<FILE:USRPDF-031>`。
- 明细与保留项说明见 `PATH-SANITIZATION-LOG.md`。

## 5. Known Issues

- KMI-01：课程封存哈希 CRLF/LF 不一致（上游自带，本基线**未修复**）。
- KMI-02：26 个测试依赖被排除的真实 pilot/curated 数据（本基线**未绕过**）。
- 详见 `KNOWN-MIGRATION-ISSUES.md`；修复必须经项目所有者确认，以独立提交落地，不混入本基线。

## 6. 基线测试状态（在新仓库实测）

- 后端 pytest：**131 passed / 27 failed**。
  - 1 个失败 = KMI-01（`test_lesson_plan_generation_and_update_endpoints`）。
  - 26 个失败 = KMI-02（`test_question_bank` 16、`test_question_variants` 9、
    `test_solution_assistant` 2、`test_http` 统计/搜索 1，均因真实数据被排除）。
- 前端：`pnpm typecheck:web` 通过；`pnpm build:web` 通过（13 个路由）。
- 无 lint 配置，未运行 lint。
- 对照：原仓库含数据时 158/158 通过；KMI-01 在干净克隆上始终失败（原仓库同样存在）。
- Prompt 1.5 稳定化（`stabilize/commercial-baseline-v1`）：26 个数据类失败以 synthetic fixtures 修复，
  KMI-01 以独立 commit 修复；最终后端 pytest **159 passed / 0 failed / 0 skipped / 0 xfailed**。
  明细见 `BASELINE-TEST-FAILURE-MATRIX.md`。

## 7. 迁移执行记录

- 复制方式：按白名单逐文件复制并脱敏，非目录级拷贝。
- Secret 扫描：见本阶段执行报告；未发现真实密钥。
- 原公开仓库：只读，未做任何写操作。

## 8. Stable Baseline

- 建立日期：2026-08-16
- Original Commercial Baseline SHA：`d88e7a5e0f24821d567aeb9311ab890f170ae16e`
- 稳定化 PR：[#1 chore: stabilize commercial v1 baseline](https://github.com/DarkMoonWarrior/math-teacher-agent/pull/1)
- Stabilization merge SHA：`46afdcadbd72fba547f4ce6d348453e86f8f1626`
- Tag：`commercial-baseline-v1.0-stable`（annotated，指向 merge SHA）
- 最终测试结果：后端 pytest **159 passed / 0 failed / 0 skipped / 0 xfailed**；
  `pnpm typecheck:web` 通过；`pnpm build:web` 通过。
- KMI-01 状态：Fixed（newline-stable canonical hashing，独立 commit `942c2dc`，含回归测试）。
- KMI-02 状态：Fixed（26 个数据类失败以 synthetic commercial-safe fixtures 修复，独立 commit `d769021`；
  `data/test-fixtures/` 全部为项目自建 synthetic 数据，无第三方真实题目）。
- 该 tag 是 Teacher Agent / DeepSeek Harness 接入之前的正式回滚点，不得移动或覆盖。
