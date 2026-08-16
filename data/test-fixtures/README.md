# test-fixtures

只允许放置：

- 项目自行创建（synthetic）的数据；
- 权利明确用于测试的数据（例如程序生成的几何图、合成 PDF/DOCX）。

禁止把真实第三方题目、试卷原文或教师私人资料复制进 fixture 以让测试通过。
需要真实数据的测试必须显式记录为 blocker / migration issue
（见 `docs/commercial-v1/KNOWN-MIGRATION-ISSUES.md`）。

## 当前 fixture 家族

| 路径 | 内容 | 来源 |
| --- | --- | --- |
| `question-bank/pilot/batch-synthetic-set-probability-30q-v1.json` | 30 道合成题：集合 10 + 概率 10 + 圆锥曲线 10，复现原批次统计结构 | 项目自建 |
| `question-bank/pilot/function-properties-synthetic-5q-v1.json` | 5 道函数性质合成题 | 项目自建 |
| `question-bank/curated/set-10q-synthetic-corrections-v1.json` | 集合 10 题校正包（9 通过 / 1 不一致） | 项目自建 |
| `question-bank/curated/probability-4q-synthetic-corrections-v1.json` | 概率 4 题校正包（4/4 通过） | 项目自建 |
| `question-bank/curated/probability-6q-synthetic-corrections-v1.json` | 概率 6 题校正包（5 通过 / 1 不一致） | 项目自建 |
| `question-bank/curated/function-properties-5q-synthetic-corrections-v1.json` | 函数 5 题校正包（4 通过 / 1 不一致） | 项目自建 |
| `search-agent/search-agent-synthetic-14q-v1.json` | 14 道 Search Agent 合成题（椭圆/集合/导数，全部 verification=passed、rights 自建声明） | 项目自建 |
| `search-agent/eval-cases.json` | 50 条合成搜索评估 query（含 expected 字段） | 项目自建 |
| `search-agent/holdout-cases.json` | 27 条独立 Holdout query（Prompt 3.5，与原 50 条不重复） | 项目自建 |

## 原则

- 所有题目 ID（`q_pilot_set_*`、`q_pilot_probability_*`、`q_pilot_ellipse_*`、`q_function_properties_*`）保留原测试契约，只替换了题干/选项/解析正文。
- 题干使用项目自建的简单数学内容；数值正确性由 `MathVerifier` 规则作为权威来源（规则名与验证规格是代码契约，不是第三方内容）。
- 每题 `source.document_path = null`，不含任何本机路径；来源记录统一为项目自建声明。
- 生成器与自检：`scripts/generate_synthetic_test_fixtures.py`（可重复生成，内置与迁移测试断言一致的自检）。
- 完整清单与逐文件哈希见 `MANIFEST.json`。

## 禁止

- 从 `data/pilot`、`data/curated`、`data/source-pairs` 或任何本地语料复制真实题目正文；
- 把商业题库候选内容伪装成 synthetic fixture；
- 用 skip / xfail 隐藏依赖真实数据的失败。
