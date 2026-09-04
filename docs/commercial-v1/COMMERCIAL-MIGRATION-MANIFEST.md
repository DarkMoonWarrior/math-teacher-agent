# 商业 V1 迁移 · 代码与数据迁移清单

> 归档说明（2026-09-04）：本文保留原型/迁移时期的事实与决策。旧 UI、旧路径、分支、待办和验收数字不代表当前实现；请以 [当前开发状态](../PROJECT-STATUS.md) 为准。来源、权利与教材证据继续保留。

- 文档编号：COMMERCIAL-V1 / DOC-02
- 审计日期：2026-08-16
- 审计基线：`1de7d4a`
- 决策状态：**建议案，待项目所有者确认后执行**（本阶段不做任何实际迁移）

## 1. 迁移总原则

1. 新商业仓库（暂名 `math-teacher-agent`），但不从零重写：成熟代码优先迁移。
2. 代码迁移与题库/资料数据迁移是两套独立流程，任何数据未经权利审查不得进入商业数据集。
3. 每个模块按 `KEEP / REFACTOR / AGENT_TOOL / LEGACY / REVIEW_DATA_RIGHTS` 五类归档；
   `AGENT_TOOL` 与 `KEEP` 正交（KEEP 模块可以同时是 Tool 候选）。
4. 重构必须有明确技术原因；禁止为了"架构更漂亮"重写稳定模块。
5. 旧仓库继续作为 Prototype / Alpha 与历史仓库保留，不做破坏性操作。

## 2. 模块分类总表

| 模块 | 分类 | 理由与迁移动作 | Tool 候选 |
| --- | --- | --- | --- |
| `question_bank` | **KEEP**（含一项定点抽取） | 核心资产。修订、图片槽、审核、发布门禁全部保留。唯一例外：内嵌权利判定抽取为独立 RightsGate 服务（技术原因：变式、相似度、发布多处需要一致权利决策，见第 3 节） | `search_questions`、`get_question` |
| `math_verifier` | **KEEP** | 核心资产，纯函数规则验证，不可绕过、不可简化 | `verify_question` |
| `question_quality` | **KEEP** | 教材推荐与手动验证证据，稳定 | （后续）`propose_curriculum_mapping` |
| `question_similarity` | **KEEP** | 规则型去重注册表，承诺不修改题目，商业可复用 | `find_similar_questions` |
| `question_variants` | **KEEP** | 母题权利检查 + 本地确定性变式 + 模型变式均已落地 | `create_question_variant`（第二批，仅设计） |
| `solution_assistant` | **KEEP** | 已验证题库优先的解题链路，可信分级已落地 | （后续）`solve_question` |
| `private_library` | **KEEP** | 私人空间核心，默认 private 不变量正确 | `import_private_resource`（第二批，仅设计） |
| `pdf_imports` | **KEEP** | 成熟的生产流水线（122KB 单文件偏大，但不重写；仅在需要独立 Tool 面时渐进拆分接口） | 无（教师人工流程，Agent 不代操作） |
| `exam_papers` | **KEEP** | 组卷 + 不可变快照 + 模板，核心资产 | `create_paper_draft`（第二批，仅设计） |
| `exam_exports` | **KEEP** | 三种导出物稳定 | （后续）`export_paper` |
| `lesson_plans` | **KEEP** | 教案工作台 + 三 provider | `create_lesson_draft`（第二批，仅设计） |
| `lesson_exports` | **KEEP** | 稳定 | （后续）`export_lesson` |
| `curriculum` | **KEEP** | 封存基线 + CSV 目录；权利依据单独审查（SRC-001/002） | `get_curriculum_node` |
| `model_operations` | **KEEP** | 模型可观测性；迁移后扩展记录 Agent 运行 | 无 |
| `deepseek.py` | **REFACTOR** | 迁移为独立 `model_adapters` 包（隔离 transport），**保留** LaTeX JSON 归一化逻辑与测试；不重写 | 无 |
| 路由内 provider 装配工厂 | **REFACTOR** | 抽成统一 ProviderRegistry，供 REST 与未来 Agent Runtime 共用；装配语义不变 | 无 |
| `background_jobs.py` | **REFACTOR**（延后） | 进程内注册表，云端多 worker 前替换为持久化队列；本地阶段保留现状 | 无 |
| `routes/*` | **KEEP** | 业务服务层，Agent Tool 网关将直接调用其背后的模块服务，不绕开 | Tool 网关宿主 |
| `apps/web` | **KEEP** | 整体保留；本次审计不改任何 UI 行为 | 无 |
| `scripts/*`（数据加工） | **KEEP** | 审计/导入/目录构建工具随代码迁移；见第 6 节 LEGACY 例外 | 无 |
| 现有 158 个后端测试 | **KEEP** | 迁移验收门禁 | 无 |
| `data/pilot/*`、`data/curated/*`、`data/source-pairs/*` | **REVIEW_DATA_RIGHTS** | 内容数据，不得自动迁移 | 无 |
| `docs/high-school-math-ai/audits/*`、`rights/*`、`data-source-register.csv` | **REVIEW_DATA_RIGHTS** | 治理元数据，随代码迁移但权利结论不继承 | 无 |
| `<LOCAL_CORPUS_PATH>`（31 份 PDF）与 `data/runtime/*` | **REVIEW_DATA_RIGHTS / 禁止迁移** | 原文件与运行时数据永远不进入商业仓库 | 无 |

### LEGACY（逐步淘汰，保留审计入口）

| 对象 | 处置 |
| --- | --- |
| `docs/high-school-math-ai/curriculum/pep-a-required-1-v0.1.csv`、`pep-a-required-1-knowledge-tree-v1.csv` | 已被五册全量目录替代；留档，不进入商业运行时默认路径 |
| `docs/high-school-math-ai/PRD-v0.1.md`、`PROJECT-BASELINE-v1.md` | 已被 DEVELOPMENT-BOUNDARY-AND-ROADMAP-v2.md 替代；历史留档 |
| `scripts/build_pilot_question_batch.py`、`scripts/validate_pilot_question_batch.py` | pilot 批次一次性脚本；完成数据审计后归档 |
| `data/pilot/*` 旧批次 JSON | 仅作 provenance 证据留存，永不进入商业题库 |

## 3. 十五个指定模块的专项结论

- `question_bank`：KEEP。发布门禁（`_publication_blockers`）与修订失效逻辑质量高，是核心资产。
  专项建议：把散落的权利判定（变式改编许可、私人不可发布、许可状态）抽取为 `RightsGate` 服务，
  bank 只调用不内嵌。**抽取不改动现有判定结论**，先用现有测试锁定行为。
- `question_quality`：KEEP。无独立存储，与 bank/curriculum 组合良好。
- `question_similarity`：KEEP。当前为规则型（规范化、骨架、ngram、SequenceMatcher），无向量依赖；
  商业阶段再评估语义检索，不提前替换。
- `question_variants`：KEEP。`LocalDiagnosticVariantProvider` 是确定性兜底；模型 provider 输出强制
  `needs_math_review`。Tool 化时只允许"教师已确认母题"的上下文。
- `solution_assistant`：KEEP。可信三档已落地，Agent 接入时直接复用其返回分级。
- `math_verifier`：KEEP，最高优先级资产。只允许新增题型 spec 与测试，不允许绕过。
- `private_library`：KEEP。private 默认、哈希去重、格式校验、OCR 队列全部保留；
  `import_private_resource` Tool 必须强制携带 `rights_basis`，服务端拒绝无依据上传。
- `pdf_imports`：KEEP。人工拆题流程，不交给 Agent 自动完成；随代码整体迁移。
- `exam_papers`：KEEP。组卷只从验证通过题库选题，快照不可变。
- `exam_exports`：KEEP。AI 标识与答案隔离规则保留。
- `lesson_plans`：KEEP。块级锁定/改写/版本逻辑保留。
- `lesson_exports`：KEEP。
- `curriculum`：KEEP（代码）；其内容权利依据（课程标准 + 人教 A 版教材目录）单独审查，
  见 `DATA-RIGHTS-MIGRATION-REVIEW.md`。
- `model_operations`：KEEP；扩展点：Agent 运行记录（run/session/tool_call）沿用同一记录器，仍不存正文/提示词/密钥。
- `deepseek.py`：REFACTOR。迁入 `model_adapters` 包并保持协议与 JSON 修复不变；任何 Harness 依赖都不得出现在该包。

## 4. AIOrchestrator / model provider 迁移分析

- 现状：`AIOrchestrator` 只有接口设计没有实现；真实装配在路由层 `lru_cache` 工厂完成，provider 已统一为
  `Protocol + ModelRunRecorder + Pydantic 输出校验`。
- 迁移路径（两阶段，不打断现有 API）：
  1. 把路由内工厂抽成 `ProviderRegistry`（DeepSeek/OpenAI/local 三段式选择不变）。
  2. TeacherAgentRuntime 不直接 new provider，而是通过 `AgentCapabilityClient` 调 FastAPI 业务服务；
     模型能力继续由业务服务内部的 ProviderRegistry 选择。
- 结果：业务系统只依赖 `TeacherAgentRuntime` 接口与业务服务，Harness 永远被隔离在 Runtime 适配器之后。

## 5. Git 历史处置建议

审计事实：57 个提交、单作者；未发现 >1MB 的历史 blob；未发现历史中的 API Key（`.env` 一直被忽略）；
历史中无第三方 PDF/题库二进制；文档类决策历史价值集中在 `docs/` 当前内容。

三个选项评估：

| 选项 | 适用性 | 风险 | 建议 |
| --- | --- | --- | --- |
| A. 完整保留历史 | 需要逐提交追溯原型演进 | 历史含内部审计笔记与本地路径，开源/闭源边界与商业干净度受影响 | 不推荐 |
| B. 迁移当前 clean snapshot | 商业仓库从干净基线开始，旧仓库保留完整历史可查 | 丢失新仓库内的提交级演进（旧仓库仍在） | **推荐** |
| C. 新 initial baseline commit | 与 B 等价，仅提交元数据不同 | 无 | B 的子选项 |

建议：**B（clean snapshot）**；旧仓库保持只读作为历史归档。执行前补充一轮
`gitleaks`/`trufflehog` 扫描 + 大文件清单复核，由项目所有者最终确认。

## 6. 代码迁移范围（待确认）

> 最终执行以 `COMMERCIAL-SNAPSHOT-WHITELIST.md`（DOC-06）为准；本节与 DOC-06 冲突时以 DOC-06 为准。

- **允许迁移**：`apps/web`、`apps/api`（含 tests）、`scripts/`（KEEP 类）、
  `docs/high-school-math-ai/`（治理与架构文档）、`.gitignore`、`.gitattributes`、`.env.example`、
  `package.json`、`pnpm-*`、`README.md`（重写为商业仓库说明）。
- **条件迁移**：`docs/high-school-math-ai/curriculum/*`（代码依赖，随代码迁，权利状态保持 REVIEW）、
  `docs/high-school-math-ai/audits/*`（治理元数据，不继承权利结论）。
- **禁止迁移**：`data/runtime/` 全部（各 SQLite、私库文件、PDF 导入文件、题目配图、试卷快照）、
  `output/`、`.env`、`<LOCAL_CORPUS_PATH>` 原 PDF、`data/pilot|curated|source-pairs` 内容数据
  （仅在完成 `DATA-RIGHTS-MIGRATION-REVIEW.md` 审查后按独立数据流程处理）。

## 7. 回滚策略

- 代码：迁移以单次 PR 进入新仓库，可整体 revert；旧仓库全程不动。
- 运行时：TeacherAgentRuntime 由配置选择（Legacy 默认），任何 Agent 问题一键切回旧 UI 工作流。
- 数据：quarantine/review/approved 单向流转，未批准的批次保留在隔离目录；任何"发布"只能经原有教师审核台。
- 门禁：迁移后必须满足"158 后端测试 + typecheck + build 全绿 + 五条主流程 smoke"，否则不进入下一步。

## 8. 测试策略

- 迁移验收：现有 158 个后端测试 + `pnpm typecheck:web` + `pnpm build:web` 在新仓库全绿（基线已实测）。
- 新增测试（下一阶段才写）：
  - Tool 网关契约测试：每个 Tool 的 schema、权限拒绝、审计记录；
  - Runtime conformance 套件：Legacy 与未来 Harness Runtime 共用同一断言集；
  - RightsGate 抽取的等价性测试：用现有 bank 测试锁定判定行为不变。
- 明确不测：AI 内容正确性（由 MathVerifier + 教师审核负责）；数据内容自动校验（只校验哈希与元数据完整性）。

## 9. 本次审计对仓库的改动声明

- **无**。Prompt 0 边界要求不修改业务代码；审计期间为验证而做的临时修复（`baseline.py` 行尾归一化 +
  封存清单哈希更新）已在 Prompt 0 验收阶段全部 `git restore` 回初始 HEAD。
- 该缺陷作为 Known Migration Issue 记录在 `KNOWN-MIGRATION-ISSUES.md`（KMI-01），修复方式与
  建议修复阶段见该文档；在项目所有者确认前不落地任何代码修改。

## 10. 下一步最小实现范围（迁移启动后的第一批工作）

1. 建立新私有仓库骨架：`apps/`、`agent/`（接口包）、`docs/`、`scripts/`、CI。
2. 按第 6 节范围复制代码；不含任何数据目录。
3. `TeacherAgentRuntime` 接口 + `LegacyTeacherAgentRuntime` + 5 个只读 Tool + FastAPI Tool 网关
   （能力令牌 + 审计），详见 `AGENT-ARCHITECTURE-v1.md`。
4. 迁移验收：全部现有测试 + typecheck + build 通过。
5. 数据侧只建立 quarantine → review → approved 的流程骨架与元数据登记，不做实际数据迁移。
6. DeepSeek Harness：仅定义适配器接口与 conformance 测试，不接真实 Harness。
