# 商业 V1 迁移 · 产品与技术基线

- 文档编号：COMMERCIAL-V1 / DOC-01
- 审计日期：2026-08-16
- 审计基线：`DarkMoonWarrior/high-school-math-ai` @ `1de7d4a`（main，共 57 个提交）
- 文档性质：只读审计结论，不改变任何用户功能、API 行为或数据含义

## 1. 一句话定位

当前仓库是一个"教师优先、题库质量门禁优先"的高中数学备课工作台原型（Prototype / Alpha），
已经跑通 `资料登记 → PDF 分析 → 拆题校对 → 公式/图片处理 → 私人题库 → 人教 A 版映射 → 数学核验 →
教师审核 → 搜题/解题/教案/组卷/导出` 全链路。它是未来商业 V1 的主要代码来源，按"新商业仓库，但不从零重写"处理。

## 2. 系统总览

- 前端：Next.js 16（App Router）单页应用，`apps/web`，页面包括
  `/`（工作台）、`/search`、`/solve`、`/curriculum`、`/library`、`/imports`、`/papers`、
  `/lesson-plans`、`/admin`、`/admin/duplicates`、`/admin/models`。
- 后端：FastAPI 0.141 模块化单体，`apps/api`，所有路由挂载在 `/api/v1` 下；
  Next.js 通过同源 rewrite 代理到 `http://127.0.0.1:8000`（`MATH_AI_API_INTERNAL_URL` 可覆盖）。
- 存储：当前为本地阶段实现——每个业务模块各自拥有一个 SQLite 文件与文件目录，全部位于
  `data/runtime/`（已 Git 忽略）。模块接口未泄漏 SQLite 细节，云端阶段可替换为 PostgreSQL/对象存储。
- 身份模型：教师/管理员是 UI 工作模式切换，**不是安全认证**（见 DEVELOPMENT-BOUNDARY-AND-ROADMAP-v2.md）。
- AI：DeepSeek / OpenAI 都是可选文本模型适配器，均有本地确定性回退；模型输出默认 draft，
  界面与数据严格区分"程序验证 / 模型生成待复核"。

## 3. 模块清单与职责（审计现状）

| 模块 | 主要文件 | 自有存储 | 测试 | 职责与当前形态 |
| --- | --- | --- | --- | --- |
| `question_bank` | `bank.py`（约 85KB） | `question-bank.sqlite3` + 题目配图目录 | 17 | 批量导入、修订历史、题库状态、图片槽、审核与发布门禁、派生题/私人资料题、教材映射、手动验证记录；权利判定内嵌在 `create_derived_question` / `publish` 路径 |
| `math_verifier` | `verifier.py`（约 33KB） | 无（纯函数） | 通过 bank/quality 间接覆盖 | 规则型独立验证：集合、概率枚举、函数性质等模块级 spec；输出 `passed/failed/inconclusive` + 证据 |
| `question_quality` | `workflow.py`（约 15KB） | 无（复用 bank） | 8 | 教材知识点推荐、批量映射、手动验证证据记录 |
| `question_similarity` | `registry.py`（约 23KB） | `question-similarity.sqlite3` | 9 | 规范化/骨架/ngram/SequenceMatcher 规则型去重与变式候选；承诺永不改、并、删题目 |
| `question_variants` | `providers.py` + `service.py` | 复用 bank | 9 | 本地错因诊断变式（确定性）+ OpenAI/DeepSeek 数值/难度/情境变式；教师变式草稿保存与润色 |
| `solution_assistant` | `assistant.py` + `providers.py` | 复用 bank | 5 | 优先匹配已验证私有题库（`program_verified`），未命中再走模型（`teacher_review_required`）；标准/第二解法 |
| `private_library` | `library.py`（约 40KB）+ `providers.py` | `private-library.sqlite3` + 文件目录 | 22 | 上传权利登记、真实格式校验、SHA-256 去重、文本提取、OCR/人工转录队列、AI 修复、拆题候选；默认永远 private |
| `pdf_imports` | `studio.py`（约 122KB）+ `math_ocr.py` + `text_repair.py` | `pdf-imports.sqlite3` + 文件目录 | 27+ | 批次登记、来源配对、条目匹配、题界候选、结构化草稿、公式复核、图片裁剪、分页检查点队列 |
| `exam_papers` | `studio.py` + `composer.py` + `templates.py` | `exam-papers.sqlite3` + 快照资产目录 | 15 | 组卷草稿/版本/不可变题目快照；仅从验证通过题库选题；内置新高考Ⅰ卷 19 题模板 |
| `exam_exports` | `renderer.py` + `math_text.py` | 无（文件输出） | 间接 | 学生卷/答案卷/双向细目表 DOCX+PDF；不泄漏答案；带 AI 标识 |
| `lesson_plans` | `studio.py` + `providers.py` | `lesson-plans.sqlite3` | 5 | 教案草稿、版本、块级锁定与 AI 局部改写；模板/OpenAI/DeepSeek 三种 provider |
| `lesson_exports` | `renderer.py` | 无（文件输出） | 间接 | 教案 DOCX/PDF；审核提示、题库联动、版本化文件名 |
| `curriculum` | `catalog.py` + `baseline.py` | 无（CSV+清单） | 6 | 人教 A 版五册知识树（CSV 内存目录）；SHA-256 封存基线，启动/教案前校验 |
| `model_operations` | `registry.py`（约 18KB） | `model-operations-v1.sqlite3` | 4 | 模型运行元数据（路由、成功率、耗时、token、提示版本、脱敏错误）；不存题目正文/提示词/密钥 |
| `deepseek.py` | 独立文件 | 无 | 3 | OpenAI 兼容 Chat Completions 客户端 + LaTeX 安全 JSON 归一化 |
| `background_jobs.py` | 独立文件 | 内存 | 间接 | 进程内后台任务注册表（OCR、AI 修复），重启后任务丢失但领域数据持久 |
| `routes/*` | 9 个路由文件 | 无 | HTTP 测试 7+ | 服务层：以 `lru_cache` 工厂装配模块与 provider，暴露 REST API |
| `scripts/*` | 8 个数据脚本 | 无 | 无 | 审计、导入、目录构建、重复页检测等一次性/运维工具 |

## 4. 数据与治理资产

- 教材目录：`docs/high-school-math-ai/curriculum/pep-a-full-knowledge-tree-v1.csv`（人教 A 版五册）+ 封存清单
  `pep-a-sealed-baseline-v1.json`（SHA-256 + 教育部/人教社来源引用）。
- 来源登记：`docs/high-school-math-ai/data-source-register.csv`，SRC-001 ~ SRC-009。
- 权利声明：`docs/high-school-math-ai/rights/user-declaration-2026-08-03.md`（27 份 PDF 的批次声明及边界）。
- 批次审计：`docs/high-school-math-ai/audits/`（31 份 PDF 文件级清单、题量估计、技术审计、重复页检查、
  多份 curation report）。
- 试点数据：`data/pilot/`、`data/curated/`、`data/source-pairs/`（共 9 个 Git 跟踪文件，详见
  `DATA-RIGHTS-MIGRATION-REVIEW.md`）。

## 5. AI 调用现状（迁移前事实）

- 尚无独立 `AIOrchestrator` 实现（`module-interfaces-v0.1.md` 中有设计，未落地）。
- 实际装配方式：各路由文件内 `lru_cache` 工厂按 `MATH_AI_*_PROVIDER=auto` 依次选择
  DeepSeek（有 key）→ OpenAI（有 key）→ 本地规则/模板。
- provider 形态统一：`Protocol` + 同名方法 + `ModelRunRecorder.track` 包裹 + Pydantic 严格校验输出。
- DeepSeek 走 `DeepSeekJsonClient`（Chat Completions + JSON Schema 指令）；OpenAI 走 Responses API。
- 长任务（OCR、AI 修复）通过 `BackgroundJobRegistry` 进程内队列执行，前端轮询 `/jobs/{job_id}`。
- 可信分级已落地：`program_verified`（题库独立验证）/ `teacher_review_required`（模型生成待复核）；
  教案、变式、解题结果均带审核提示，不冒充已验证。

## 6. 质量与发布门禁链

1. 导入/拆题：来源配对、公式复核、结构化草稿审核（`pdf_imports`）。
2. 数学验证：`MathVerifier` 规则独立验证；题干/选项/答案变更自动失效旧验证。
3. 教师审核：`review` → `approved` 留痕；发布前 `_publication_blockers` 必须为空。
4. 权利检查：变式要求母题验证通过 + 权利记录允许改编；私人资料派生题默认私有不可发布。
5. 发布：`publish` 是唯一 public 出口，AI 无任何直接发布路径。

## 7. 当前验证状态（2026-08-16 实测）

- 后端：158 个 pytest 用例全部通过（`apps/api/tests`）。
- 前端：`pnpm typecheck:web` 通过；`pnpm build:web` 通过（13 个路由全部预渲染成功）。
- 审计中发现一个上游自带缺陷（CRLF/LF 封存哈希问题，详见 `KNOWN-MIGRATION-ISSUES.md` KMI-01）。
  按 Prompt 0 边界要求**未修改业务代码**；临时验证过的修复已在验收阶段恢复，仓库相对初始 HEAD
  无任何业务代码差异。
- 提示：由于该缺陷，干净克隆上直接运行 `test_http.py::test_lesson_plan_generation_and_update_endpoints`
  会失败；这是上游 HEAD 的已知状态，与本次审计无关。

## 8. 已知限制（进入商业 V1 前必须解决）

- 单用户本地模型：无真实账号、认证、授权；教师/管理员只是工作模式。
- 每模块独立 SQLite；云端需替换为 PostgreSQL/pgvector/对象存储（接口不变）。
- `BackgroundJobRegistry` 进程内实现，多 worker 下不共享。
- 模型直连 HTTP 适配器无重试/熔断统一层；密钥仅存 `.env`（已 Git 忽略）。
- 数据权利整体处于 `rights_quarantine_until_evidence_checked`，不满足商业发布条件。
