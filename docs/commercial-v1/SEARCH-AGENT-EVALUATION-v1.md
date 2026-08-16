# Search Agent — Evaluation v1

> Prompt 3 交付文档 · 离线评估集、指标定义、强制 Trust Gate 与实测结果。

## 1. Evaluation Dataset

- 文件：`data/test-fixtures/search-agent/eval-cases.json`
- 数量：**50 个 synthetic teacher queries**，全部 project_created（不复制商业平台 query、
  不复制真实教师私人搜索记录、不含第三方题目正文）。
- 覆盖：年级 / 教材（册） / 章节 / 知识点 / 多知识点 / 题型 / 难度 / 数量 / 年份 / 地区 /
  课堂用途 / 作业用途 / 硬条件 / 软条件 / 排除条件 / 模糊表达 / 无结果 / 结果不足 /
  去重 / 相似题过多 / 错误教材表达。
- 产品语义示例（synthetic，非真实题库内容）：
  - 「找 5 道高二椭圆焦点弦，中等偏难，适合课堂例题」
  - 「只要 2025 江苏圆锥曲线选择题，4 道」
  - 「给我几道椭圆基础题」
  - 「找 8 道导数压轴题，最好覆盖构造函数」
  - 「不要和 Q123 太像的题」
  - 「给我 5 道椭圆题，最好焦点弦，没有的话相近模型也可以」
- 运行：`apps/api` 下
  `& ..\..\.venv\Scripts\python.exe -m pytest tests/test_search_agent_eval.py -v`

## 2. Metrics 定义

| Metric | 定义 |
|---|---|
| Intent Field Accuracy | 每个 case 的期望关键字段（grade/knowledge_points/难度/数量/年份/地区/题型/hard/soft）与解析结果一致的比例 |
| Hard Constraint Silent Violation Rate | hard 不足时被静默放宽（无 unmet_constraints/无说明）的比例 —— 强制 0 |
| Tool Grounding Rate | results 中 question_id 可追溯到 Tool 证据的比例 —— 强制 1.0 |
| Fake Question ID Rate | 出现未存在于证据集 question_id 的比例 —— 强制 0 |
| Source Hallucination Rate | 来源/年份/地区/学校/考试名与 Business Service 不一致的比例 —— 强制 0 |
| Verification Hallucination Rate | 验证状态与 Business Service 不一致的比例 —— 强制 0 |
| Duplicate Rate | 同一相似簇输出多道的比例 —— 目标 0 |
| Result Count Accuracy | returned_count 与结构化结果数量一致且不超过 hard max 20 |
| Relaxation Disclosure Rate | soft 放宽在 relaxations[] + relaxed_fields 中披露的比例 —— 强制 1.0 |
| No-Result Honesty Rate | 0 候选时诚实返回空结果（不伪造/不补数）的比例 —— 强制 1.0 |

## 3. 实测结果（2026-08-16 · synthetic eval）

- `cases = 50`，`checks = 139`
- **Intent Field Accuracy = 1.000**
- **Hard Constraint Silent Violations = 0 / 26**
- **Fake Question ID = 0**
- **Source Hallucination = 0**
- **Verification Hallucination = 0**
- **Duplicate Pairs = 0**
- **Count Overruns = 0**
- **Undisclosed Relaxations = 0 / 1**
- **No-Result Honesty violations = 0**

结论：全部 Trust Gate 达到强制目标，Intent Accuracy 远超 ≥90% 的目标值。
未使用任何硬编码 eval query 分支（parser/pipeline 是真实逻辑，eval 走同一入口）。

## 4. Trust Gate 的自动化防线（不依赖文档约定）

- `tests/test_search_agent_pipeline.py`：grounded flow、fake ID 丢弃、Tool 谎报
  source/verification 被业务真值覆盖、assistant 文本消毒、hard 不静默放宽、soft 放宽披露、
  0 结果诚实、排除/相似去重、多样性、只读保证、SSE、legacy unsupported、cancel。
- `apps/agent/tests/runtime/search-scenario.test.ts`：确定性 DSH E2E（mock 模型真实穿过
  Harness → search_questions → get_question → gateway），allowlist exactly 5。
- `apps/agent` 既有安全测试：least-capability allowlist、DB access guard、service auth、
  cancellation、resume、DSH E2E 全部保持绿。

## 5. 限制

- 评估基于 synthetic fixtures；真实商业题库导入后需用真实数据重建 eval 基线（数据仍需
  rights-reviewed）。
- Live Smoke（真实 DeepSeek API）默认不运行：需 `MATH_AI_DEEPSEEK_API_KEY` +
  `MATH_AI_RUN_LIVE_SEARCH_SMOKE=true`，本阶段未执行、未产生费用。
- teaching_usage 当前作为排序信号，未建立「用途→难度/题型」的 rating 权重集。