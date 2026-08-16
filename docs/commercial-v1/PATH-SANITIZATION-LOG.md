# 路径与文件标识脱敏日志（Clean Snapshot）

迁移时对以下内容执行了脱敏替换。原则：只替换本机路径与私人文件名标识，
不改变治理文档的业务含义（来源文件仍可通过 `file_id` 对应）。

## 1. 替换规则

| 原内容 | 替换为 |
| --- | --- |
| `D:\高中数学\2026-08\...` / `D:/高中数学/2026-08/...` | `<LOCAL_CORPUS_PATH>/...` |
| `D:\Vibecoding\data\...` | `<PROTOTYPE_WORKSPACE>/data\...` |
| 31 个私人 PDF 文件名（取自 `batch-2026-08-001-manifest.csv`） | `<FILE:USRPDF-001>` ~ `<FILE:USRPDF-031>` |

## 2. 受影响的文件

- `docs/high-school-math-ai/audits/batch-2026-08-001-manifest.csv`：`source_path` 与 `filename` 列全部脱敏。
- `docs/high-school-math-ai/audits/batch-2026-08-001-question-estimates.csv`：`filename` 列全部脱敏。
- `docs/high-school-math-ai/audits/batch-2026-08-001-duplicate-page-check.json`：文件名脱敏。
- `docs/high-school-math-ai/audits/pilot-30q-validation.json`：输入路径与来源计数键脱敏。
- `docs/high-school-math-ai/rights/user-declaration-2026-08-03.md`：语料路径脱敏。
- `docs/high-school-math-ai/audits/*.md`：引用到上述文件名的段落脱敏。
- `docs/commercial-v1/COMMERCIAL-MIGRATION-MANIFEST.md`、`COMMERCIAL-SNAPSHOT-WHITELIST.md`、
  `DATA-RIGHTS-MIGRATION-REVIEW.md`：语料路径引用脱敏。

## 3. 排除迁移的文件（比白名单更严格）

- `docs/high-school-math-ai/audits/batch-2026-08-001-technical-audit.csv`：
  含原 PDF 提取的题目/解析正文样本与微信联系方式，属于未审核第三方内容，禁止进入商业仓库。
  该文件保留在原公开仓库，作为历史证据。

## 4. 审查后保留（非私人路径，记录说明）

- `apps/api/app/modules/*/renderer.py`、`private_library/exports.py` 中的
  `C:/Windows/Fonts/*.ttc` 字体候选：平台标准系统字体路径，非用户私人目录；
  为保持基线忠实于原代码，未改动业务代码，已在此记录。
- 治理文档中对"学科网 / 微信公众号 / EduEditer / 数学第六感"等来源信号的**描述性提及**：
  属于权利审计证据，不是本机路径或密钥，予以保留。
- 架构文档中对来源文档简称的提及（如《大题 函数与导数（解析版）》）：保留为治理上下文。

## 5. 遗留检查

迁移后全文扫描确认：无 `D:/`、`D:\`、`Users/` 形式的私人绝对路径残留；
无原始 PDF 文件名残留；无密钥文件。
