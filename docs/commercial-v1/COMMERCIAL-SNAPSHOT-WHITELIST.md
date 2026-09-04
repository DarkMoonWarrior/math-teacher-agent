# 商业 V1 迁移 · Clean Snapshot 白名单

> 归档说明（2026-09-04）：本文保留原型/迁移时期的事实与决策。旧 UI、旧路径、分支、待办和验收数字不代表当前实现；请以 [当前开发状态](../PROJECT-STATUS.md) 为准。来源、权利与教材证据继续保留。

- 文档编号：COMMERCIAL-V1 / DOC-06
- 记录日期：2026-08-16
- 用途：Prompt 1 执行"Clean Snapshot 迁移"时的**唯一迁移依据**（与 DOC-02/04 配套使用）。
- 原则：白名单之外的任何文件不得进入商业仓库；数据类目录另有权利审查流程，禁止随快照自动迁移。

## 1. 迁移策略确认

采用 **Commercial Migration Strategy B：Clean Snapshot**：

- 旧仓库 `DarkMoonWarrior/high-school-math-ai` 继续作为公开 Prototype / Alpha 与历史归档，保持只读。
- 新商业仓库使用新的 Private Repository（名称由项目所有者最终确定，暂名 `math-teacher-agent`）。
- 不继承旧仓库 Git 历史；在新仓库建立单一的 initial Commercial Baseline Commit。
- 仅迁移本白名单允许的代码与文档；数据类内容一律不自动迁移。
- 迁移内容 = 当前 HEAD 的文件快照，不含任何运行时/生成/私有/权利不明内容。

## 2. 允许迁移（ALLOW）

### 2.1 代码目录

| 路径 | 说明 |
| --- | --- |
| `apps/web/**` | Next.js 前端全部源码与配置（`next.config.ts`、`tsconfig.json`、`package.json` 等） |
| `apps/api/app/**` | FastAPI 业务代码全部（`core/`、`modules/`、`routes/`、`main.py`） |
| `apps/api/tests/**` | 全部后端测试（158 用例，迁移验收门禁） |
| `apps/api/pyproject.toml` | 依赖与构建配置 |

### 2.2 配置模板与根文件

| 路径 | 说明 |
| --- | --- |
| `package.json`、`pnpm-workspace.yaml`、`pnpm-lock.yaml` | 前端工作区配置 |
| `.gitignore`、`.gitattributes` | 仓库规范 |
| `.env.example` | 配置模板（**只含模板，永不含真实密钥**） |
| `README.md` | 迁移后重写为商业仓库说明（原内容留档于旧仓库） |

### 2.3 测试

| 路径 | 说明 |
| --- | --- |
| `apps/api/tests/**` | 与 2.1 重复强调：测试是迁移验收门禁，必须随代码迁移 |
| `apps/web/scripts/check-api-proxy.mjs` | 前端 API 冒烟脚本 |

### 2.4 文档

| 路径 | 说明 |
| --- | --- |
| `docs/high-school-math-ai/architecture/**` | 架构文档（ERD、模块接口、各 MVP 设计） |
| `docs/high-school-math-ai/audits/**` | 治理与审计证据（**迁移前先执行 2.6 路径脱敏**） |
| `docs/high-school-math-ai/rights/**` | 权利声明记录 |
| `docs/high-school-math-ai/curriculum/pep-a-full-knowledge-tree-v1.csv` | 代码运行时依赖；内容权利依据随 DOC-04 审查 |
| `docs/high-school-math-ai/curriculum/pep-a-sealed-baseline-v1.json` | 封存清单（注意 KMI-01，见 DOC-05） |
| `docs/high-school-math-ai/research/**`、`docs/high-school-math-ai/ui/**` | 研究与 UI 文档 |
| `docs/high-school-math-ai/question-schema.md`、`question-review-media-v0.1.md` | 题目结构与媒体规范 |
| `docs/high-school-math-ai/DEVELOPMENT-BOUNDARY-AND-ROADMAP-v2.md` | 当前开发边界权威文档 |
| `docs/commercial-v1/**` | 本批 Prompt 0 审计文档（DOC-01 ~ DOC-06） |

### 2.5 脚本（数据工具，仅保留活跃工具）

| 路径 | 说明 |
| --- | --- |
| `scripts/audit_math_pdfs.py` | PDF 审计 |
| `scripts/build_math_bank_manifest.py` | 题库清单构建 |
| `scripts/build_pep_a_full_catalog.py` | 课程目录构建 |
| `scripts/estimate_math_question_counts.py` | 题量估计 |
| `scripts/find_extracted_page_duplicates.py` | 重复页检测 |
| `scripts/render_pdf_audit_samples.py` | 审计抽样渲染 |

### 2.6 迁移前必须执行的脱敏操作

- `docs/high-school-math-ai/audits/batch-2026-08-001-manifest.csv`：`source_path` 列含
  `<LOCAL_CORPUS_PATH>\...` 本机绝对路径，迁移前替换为相对标识（如 `SRC-007/<file_id>/<filename>`）。
- `data/source-pairs/*.json` 若日后进入任何仓库，同样必须先脱敏本地路径；
  当前快照迁移**不包含** `data/` 内容文件。
- 全文检索 `D:\高中数学`、`D:/高中数学`、API Key 模式、邮箱与密钥文件名，确认无泄漏后再提交。

## 3. 禁止自动迁移（DENY）

| 类别 | 路径/模式 | 理由 |
| --- | --- | --- |
| 运行时数据 | `data/runtime/**` | 各模块 SQLite、私库文件、导入 PDF、题目配图、试卷快照、模型运行库；含教师私人数据 |
| 未审核题库内容 | `data/pilot/**`、`data/curated/**`、`data/source-pairs/**` | 权利依据不足（SRC-007 声明≠书面授权），走独立审查流 |
| 原始 PDF/资料 | `D:/高中数学/**` 及任何本地副本、`*.pdf`（未在 Git 的） | 原件永不进入商业仓库 |
| 教师私人资料 | private-library 文件、`*.docx`（未在 Git 的）、任何 uploads | private 默认原则 |
| 密钥与本地配置 | `.env`、`.env.local`、`.env.*.local`、任何 API Key | 密钥永不入库 |
| 数据库文件 | `*.sqlite3`、`*.db`、`*.sqlite` | 运行时状态，不迁移 |
| 缓存与生成物 | `node_modules/`、`.venv/`、`.next/`、`out/`、`dist/`、`build/`、`__pycache__/`、`.pytest_cache/`、`*.tsbuildinfo`、`output/**` | 可再生或含工作产物 |
| 历史遗留 | `docs/high-school-math-ai/PRD-v0.1.md`、`PROJECT-BASELINE-v1.md`、`docs/high-school-math-ai/curriculum/pep-a-required-1-v0.1.csv`、`pep-a-required-1-knowledge-tree-v1.csv`、`scripts/build_pilot_question_batch.py`、`scripts/validate_pilot_question_batch.py` | 已被替代的 LEGACY 项，留档旧仓库 |
| 权利不明数据 | 任何未出现在 ALLOW 清单中的数据/内容文件 | 默认拒绝（DOC-04 出口条件） |
| 平台目录 | `.git/`、`.hallmark/`（如无商业需要） | 旧仓库元数据 |

## 4. 快照执行顺序（Prompt 1 时执行）

1. 以本白名单为准生成文件清单，逐文件复制（不使用 `cp -r` 全目录拷贝）。
2. 执行 2.6 脱敏与扫描（gitleaks/trufflehog + 大文件 + 路径关键词）。
3. 在新仓库初始化，提交 single initial Commercial Baseline Commit。
4. 安装依赖并跑迁移验收：`pytest apps/api/tests`（158/158 预期）+ `pnpm typecheck:web` + `pnpm build:web`。
5. KMI-01（CRLF/LF 封存哈希）按项目所有者批准，作为基线后的第一个独立修复提交处理；未批准前保持 Open。
6. 数据侧不迁移任何内容文件；仅建立 quarantine → review → commercial-approved 流程骨架。

## 5. 与其它文档的关系

- 模块分类与重构决策：`COMMERCIAL-MIGRATION-MANIFEST.md`（DOC-02）。
- 数据权利审查：`DATA-RIGHTS-MIGRATION-REVIEW.md`（DOC-04）。
- 已知问题：`KNOWN-MIGRATION-ISSUES.md`（DOC-05）。
- 本清单与上述文档冲突时，以本清单为准（最严格者生效）。
