# M6 Private Library 固定评测

> 状态同步（2026-09-09）：M0–M12 已完成；M13 工程切片已完成但真实验证延期、Gate 未通过；项目所有者已授权进入 M14，当前进行中。本文的切片过程、测试数量和 Gate 结论保留为当时证据；后续行为与当前边界见 [开发状态](PROJECT-STATUS.md) 和 [开发边界](DEVELOPMENT-BOUNDARY.md)。

评测日期：2026-08-22

评测集：`private-library-agent-synthetic-v1`

数据来源：仅使用项目自建 synthetic fixture，不读取真实教师资料

## 结论

固定评测共 12 个场景，全部符合预期；8 类隐私、可信与可追踪违规计数均为 0。本结果只证明 M6 既定边界在确定性测试中的行为，不代表真实教师质量、OCR 准确率、数学正确率或商业多租户隔离已经得到验证。

## 覆盖场景

| 场景 | 预期行为 |
| --- | --- |
| 空资料库 | 返回真实空结果，不生成内容填充 |
| 不支持格式 | 明确校验失败，不写入伪成功记录 |
| OCR 失败 | 条目保持 private + pending |
| 模型不可用 | 独立错误，不伪装成功 |
| Tool 超时 | 独立错误，不伪装成功 |
| 运行取消 | 返回 `cancelled` / `RUN_CANCELLED` |
| 许可重放 | 单次许可消费后拒绝重放 |
| 跨 owner | 其他教师内容不可见 |
| 未确认与回收站 | 均不参与私人检索 |
| 有界成功结果 | 只返回确认文本的最多 480 字片段及必要 provenance |
| 失败后恢复 | 新请求使用新的单次许可，成功不复用旧许可 |
| 派生题导入 | 固定 `private + pending + needs_math_review` |

Fixture 位于 [`../data/test-fixtures/private-library/eval-cases.json`](../data/test-fixtures/private-library/eval-cases.json)，可执行断言位于 [`../apps/api/tests/test_private_library_eval.py`](../apps/api/tests/test_private_library_eval.py)。

## 违规计数

```text
unexpected_outcome: 0
cross_owner_leak: 0
unconfirmed_or_trashed_leak: 0
excessive_content_leak: 0
consent_bypass: 0
private_state_promoted: 0
failure_masked: 0
trace_missing: 0
```

## 运行证据

```powershell
.\.venv\Scripts\python.exe -m pytest apps/api/tests/test_private_library_eval.py -q -s
```

固定输出：

```text
[private-library-eval] cases=12 violations={'unexpected_outcome': 0, 'cross_owner_leak': 0, 'unconfirmed_or_trashed_leak': 0, 'excessive_content_leak': 0, 'consent_bypass': 0, 'private_state_promoted': 0, 'failure_masked': 0, 'trace_missing': 0}
```

## 结果边界

- 评测没有使用真实教师上传、第三方题库或生产凭据。
- 当前 current-teacher adapter 仍是本地固定身份；生产会话、租户隔离和云端存储属于 M12，不能由本评测推断为已完成。
- OCR 场景验证失败语义和状态不提升，不测量供应商识别准确率。
- 派生题只验证隐私、审核和数学验证状态，不表示题目数学质量已经通过。
