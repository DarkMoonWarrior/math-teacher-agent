# 商业 V1 迁移 · 数据与版权审查清单

- 文档编号：COMMERCIAL-V1 / DOC-04
- 审计日期：2026-08-16
- 审计基线：`1de7d4a` + 开发者本机数据目录盘点
- 状态：审查结论；任何"进入商业数据集"的决定由项目所有者确认后执行

## 1. 核心结论

1. 当前 Git 仓库本身是**相对干净**的：没有提交原始 PDF、没有 API Key、没有 >1MB 大文件、
   运行时数据全部被忽略。真正的版权风险集中在**开发者本机语料**（`<LOCAL_CORPUS_PATH>`）与其派生产物。
2. 全部试点内容当前目标可见性就是 `rights_quarantine_until_evidence_checked`；
   **没有任何数据可以"自动进入 commercial-approved"**。
3. 数据迁移与代码迁移必须分开执行；本清单规定三层处置：禁止迁移 / 治理元数据 / 内容数据审查流。

## 2. 数据资产盘点

### 2.1 Git 跟踪的数据文件（9 个）

| 路径 | 内容 | 权利依据 | 初步判定 |
| --- | --- | --- | --- |
| `data/pilot/batch-2026-08-001-30q.json` | 30 道试点题（含 2022 天津高考真题等题源标记） | SRC-007 用户声明 + `rights_boundary` 字段 | **quarantine**：声明≠书面授权，题目级证据链不完整 |
| `data/pilot/function-properties-5q-v1.json` | 函数性质 5 题试点批 | 同上 | **quarantine** |
| `data/curated/set-10q-corrections-v1.json` | 集合 10 题修正包 | SRC-007 + curation 报告 | **review**：有审核报告，仍需书面授权依据 |
| `data/curated/probability-4q-corrections-v1.json` | 概率 4 题修正包 | 同上 | **review** |
| `data/curated/probability-6q-corrections-v1.json` | 概率 6 题修正包 | 同上 | **review** |
| `data/curated/function-properties-5q-corrections-v1.json` | 函数性质修正包 | 同上 | **review** |
| `data/source-pairs/high1-inequality-functions-trigonometry-v1.json` | 原卷/解析卷结构配对（674 题） | 仅结构配对元数据 | **quarantine**：含本机绝对路径 `D:/高中数学/...`，入商业仓库前必须脱敏 |
| `data/source-pairs/solved-source-supersessions-v1.json` | 解析版替代原卷登记 | 仅治理元数据 | **quarantine**：含文件名与路径，同上 |
| `data/inbox/README.md` | 说明文件 | 无内容 | 随文档迁移 |

### 2.2 docs 中的治理资产

| 路径 | 判定 | 说明 |
| --- | --- | --- |
| `docs/high-school-math-ai/data-source-register.csv` | 随代码迁移（元数据） | SRC-001~009；注册结论不继承，逐条复核 |
| `docs/high-school-math-ai/rights/user-declaration-2026-08-03.md` | 随代码迁移（证据） | 用户声明线索，**不等同于书面授权** |
| `docs/high-school-math-ai/audits/batch-2026-08-001-manifest.csv` | 迁移前脱敏 | 31 行含本机绝对路径 `<LOCAL_CORPUS_PATH>\...` |
| `docs/high-school-math-ai/audits/*`（报告/JSON/CSV） | 随代码迁移（证据） | 保留审计历史；不改变权利结论 |
| `docs/high-school-math-ai/curriculum/pep-a-full-knowledge-tree-v1.csv` | 代码依赖，随代码迁移；权利单独审 | 依据 SRC-001（课程标准，官方文件，限制性使用）+ SRC-002（人教 A 版教材，未授权）。当前仅结构化目录与知识点名称，不复制教材原文；商业使用前需法务确认 |
| `docs/high-school-math-ai/curriculum/pep-a-sealed-baseline-v1.json` | 随代码迁移 | 含教育部/人教社来源引用 |

### 2.3 本机未入库资产（禁止迁移）

| 位置 | 内容 | 处置 |
| --- | --- | --- |
| `<LOCAL_CORPUS_PATH>` | 31 份 PDF、2,209 页、约 66.6 MiB；19 份检出第三方来源/平台信号，12 份带 EduEditer 元数据，部分含微信公众号来源 | **永远禁止**整体或原件进入商业仓库；仅允许按题目级、经授权的结构化事实继续试点 |
| `data/runtime/` | 7 个 SQLite + 私库文件 + PDF 导入文件 + 题目配图 + 试卷快照 + 模型运行库 | **禁止迁移**；其中 `private-library.sqlite3` 与私库文件是教师私人数据，任何情况下不随仓库走 |
| `output/` | 导出 DOCX/PDF | 禁止迁移（含教师工作产物） |
| `.env` | API Key | 禁止迁移；仅迁 `.env.example` |

## 3. 来源登记逐条风险（SRC-001 ~ SRC-009）

| 编号 | 风险级别 | 说明与处置 |
| --- | --- | --- |
| SRC-001 课程标准 | 中 | 官方文件"限制性使用"；仅允许引用与结构化概括，不整本复制；上线前法务确认 |
| SRC-002 人教 A 版教材 | 高 | 版权教材、未授权；当前只做目录映射，不抓取教材内容；商用前联系出版社 |
| SRC-003 GAOKAO-Bench | 中 | Apache-2.0 仓库许可 ≠ 底层试题/解析权利；仅离线评测与标签研究，不进入商业库 |
| SRC-004 CMM-Math | 中 | BSD-3-Clause 数据页许可待溯源审计；仅 OCR 标签与验证实验 |
| SRC-005 CMMaTH | 高 | 未发现清晰数据许可，**不可用于商业库**；未获书面许可前不得商业展示或训练 |
| SRC-006 DeepMind 数据集 | 低 | Apache-2.0；验证器与合成基础题实验，保留 LICENSE/NOTICE |
| SRC-007 用户题库（31 PDF） | **最高** | 用户声明（题目可用、PDF 整体不可商用、可改编/训练）≠ 书面授权；19 份检出第三方信号；**全部保持 quarantine，直至逐文件书面授权证据齐备** |
| SRC-008 签约教师原创 | 低（未启动） | 需签署著作权许可/转让条款，保存作者与审核记录 |
| SRC-009 AI/程序生成题 | 低 | 查重 + MathVerifier + 教师审核 + AI 标识；不模仿特定教辅表达 |

## 4. 商业数据风险清单（按严重度）

| ID | 风险 | 影响 | 处置 |
| --- | --- | --- | --- |
| R-01 | 31 份 PDF 中 19 份有第三方来源/平台信号（学科网、微信公众号、EduEditer 版式） | 商业发布即侵权风险 | 逐文件 `hold_for_written_license_evidence`；未获书面授权不进商业库 |
| R-02 | 用户权利声明缺少书面授权文件 | 权利链在法务上不成立 | 起草授权/许可协议，逐文件补签；此前仅试点 |
| R-03 | 原 PDF 的封面/水印/版式/讲义表述 | 不得复制 | 继续执行现有边界：只结构化题干、选项、客观答案；解析/标签/图形重做 |
| R-04 | 试点题包含高考真题（如 2022 天津卷） | 真题本身权属与使用规则特殊 | 标记 exam 来源，逐题确认使用边界；不自动进入商业展示 |
| R-05 | 内容 JSON 与本机绝对路径混存（source-pairs、audits CSV） | 商业仓库信息卫生问题 | 入库前批量脱敏路径列；生成 provenance 用相对标识 |
| R-06 | `data/runtime/` 含教师私人资料 | 隐私 | 永不迁移；私有目录在迁移脚本中显式排除并校验 |
| R-07 | 课程目录可能被认为接近教材目录作品 | SRC-002 未授权 | 仅保留节点/知识点名称与层级，不上教材原文、例题、表述；法务确认后定版 |
| R-08 | 旧批次/旧版本数据残留（旧 4 套 CSV、pilot 旧批） | 混乱与误用 | 归档为 LEGACY，不进入默认导入队列（现有 supersessions 策略继续有效） |
| R-09 | 模型运行库中的脱敏错误日志 | 低，但属运行时数据 | 不迁移；需要时按元数据口径重建 |
| R-10 | 派生图/题目配图来源于原 PDF 裁剪 | 图片权属跟随原文件 | 商业使用前必须与题目同链审查；不可单独放行 |

## 5. 数据迁移三层处置（执行规则）

- **T0 禁止自动迁移**：`data/runtime/**`、`output/**`、`.env`、`D:/高中数学/**`、
  任何含本机绝对路径的文件（脱敏前）。
- **T1 治理元数据（随代码迁，不继承结论）**：source register、rights 声明、audits 报告、
  curriculum CSV + sealed baseline、脱敏后的 manifest/source-pairs。
- **T2 内容数据（独立审查流）**：`data/pilot|curated|source-pairs` 内容项按
  `quarantine → review → commercial-approved` 单向流转，每项必须携带：
  source 证据 + RightsGate 决定 + MathVerifier 结论 + Teacher Review 记录 + takedown 路径。

## 6. commercial-approved 出口条件（逐题/逐批）

1. 来源与权利：文件级书面授权或明确许可记录；题目级允许用途（view/adapt/export）明确。
2. 验证：`MathVerifier` `passed`，且验证与当前题目版本一致。
3. 审核：教师 review `approved`，有记录与时间。
4. 追溯：页码/题号/来源文件/修订历史齐全。
5. 下架：takedown 流程可用（当前 ERD 已设计，代码未实现，需在商业化前补齐）。

## 7. 待项目所有者确认事项（不自行决定）

1. 商业仓库 Git 历史策略（建议 B：clean snapshot，见 DOC-02 第 5 节）。
2. 是否启动 SRC-007 书面授权补签流程（决定数据能否走出 quarantine）。
3. 人教 A 版目录的使用边界（仅知识点层级 vs 更细内容），建议引入法务确认。
4. 检出第三方信号的 19 份 PDF 是否继续试点（技术可导，权利待证）。
5. 新仓库名称、可见性与成员范围。

