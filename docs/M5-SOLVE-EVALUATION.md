# M5 Solve Agent 固定合成评测

> 状态同步（2026-09-09）：M0–M12 已完成；M13 工程切片已完成但真实验证延期、Gate 未通过；项目所有者已授权进入 M14，当前进行中。本文的切片过程、测试数量和 Gate 结论保留为当时证据；后续行为与当前边界见 [开发状态](PROJECT-STATUS.md) 和 [开发边界](DEVELOPMENT-BOUNDARY.md)。

- 评测日期：2026-08-21
- 评测 ID：`solve-agent-synthetic-v1`
- 数据来源：项目自建 synthetic fixture，不含真实教师资料或第三方题库内容
- 执行入口：`apps/api/tests/test_solve_agent_eval.py`
- 固定样本：`data/test-fixtures/solve-agent/eval-cases.json`

## 评测目的

这组评测只验证 M5 的可信边界，不把合成测试结果误写成真实教师质量指标。它检查题库已验证解析是否优先、改题是否错误继承原题可信状态、新解答是否保持待教师复核，以及验证失败或不确定状态是否被模型文字掩盖。

## 固定样本覆盖

共 9 个固定场景：

1. 精确匹配且已验证的题库题，返回题目 ID、修订计数和 MathVerifier 证据；
2. 已验证题请求新解法但 provider 不可用；
3. 在已验证题后追加条件，不能继承原题解析；
4. 未知题且 provider 不可用；
5. 未知题由 synthetic provider 生成，保持 `teacher_review_required`；
6. 题库验证失败且 provider 不可用；
7. 题库验证失败时生成新解答，失败证据仍保留；
8. 题库验证不确定且 provider 不可用；
9. 题库验证不确定时生成新解答，不确定证据仍保留。

## 结果

2026-08-21 固定运行结果：9 个场景全部符合预期，以下六类违规计数均为 0。

| 违规指标 | 结果 |
| --- | ---: |
| 非预期成功或失败 | 0 |
| 模型生成内容被提升为程序验证 | 0 |
| 验证状态被夸大或覆盖 | 0 |
| 验证明细与评估对象不一致 | 0 |
| 改题继承原题已验证解析 | 0 |
| 题目、修订或验证追踪缺失 | 0 |

自动化输出：

```text
[solve-eval] cases=9 violations={'unexpected_outcome': 0, 'generated_promoted': 0, 'verification_overstated': 0, 'evidence_mismatch': 0, 'modified_inherited': 0, 'trace_missing': 0}
```

## 解释边界

- synthetic provider 只用于可重复测试，不代表真实 DeepSeek 模型质量。
- 本评测不能代替真实教师复核、严重数学错误率、任务采用率或 Week-4 留存指标。
- 任意新题的通用数学验证能力仍未被宣称；不支持时必须显示 `unsupported` 或 `inconclusive`。
- 商业发布 Gate、RightsGate、教师审核和 private/public 边界没有因 M5 通过而改变。
