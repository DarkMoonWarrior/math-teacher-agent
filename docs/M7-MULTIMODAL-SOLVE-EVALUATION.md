# M7 多模态图片解题固定评测

评测日期：2026-08-24

评测集：`multimodal-solve-synthetic-v1`

数据来源：仅使用项目自建 synthetic 图片、题面和 deterministic provider，不读取真实教师图片，不调用真实模型。

## 结论

固定评测共 15 个场景，全部符合预期；9 类隐私、许可、可信、视觉保真与可追踪违规计数均为 0。本结果证明 M7 既定业务边界在确定性评测中的行为，不代表外部 OCR/视觉模型的真实识别准确率、数学正确率或商业多租户隔离已经得到验证。

## 覆盖场景

| 场景 | 预期行为 |
| --- | --- |
| 代数公式图片 | 教师确认后只把 canonical 文字/公式交给 Solve，不发送不必要的原图 |
| 函数图像 | 缺少逐次原图同意时阻断；同意后锁定图片与 OCR revision 并使用视觉输入 |
| 解析几何 | 原图参与且结果固定为 `teacher_review_required` |
| 立体几何 | 原图、图形观察和解答 revision 可追踪，不只凭 OCR 猜图 |
| 统计图表 | 受控原图参与，视觉理解不升级 MathVerifier |
| 低对比度图片 | 明确标记 `review_needed` 并展示质量警告 |
| 截断题面 | 保留低置信度与警告，教师确认前不能进入 Solve |
| 多题图片 | 提示裁剪为单题，教师确认前不能进入 Solve |
| 外部 OCR 未授权 | fail closed，不创建识别 revision |
| OCR 服务失败 | 保持 `not_started`，不伪造识别成功 |
| 视觉模型不可用 | 明确失败，不产生伪解答 |
| 解题取消 | 返回 `cancelled` / `RUN_CANCELLED` |
| Solve 许可重放 | 一次性许可消费后拒绝再次使用 |
| 跨 owner | 其他教师无法读取媒体详情或图片内容 |
| 视觉/MathVerifier 分层 | 视觉生成结果不可伪造为 `program_verified` |

Fixture 位于 [`../data/test-fixtures/multimodal-solve/eval-cases.json`](../data/test-fixtures/multimodal-solve/eval-cases.json)，可执行断言位于 [`../apps/api/tests/test_multimodal_solve_eval.py`](../apps/api/tests/test_multimodal_solve_eval.py)。

## 违规计数

```text
unexpected_outcome: 0
private_state_leak: 0
revision_trace_missing: 0
visual_condition_lost: 0
consent_bypass: 0
cross_owner_leak: 0
failure_masked: 0
verification_overstated: 0
capability_replay: 0
```

## 运行证据

```powershell
.\.venv\Scripts\python.exe -m pytest apps/api/tests/test_multimodal_solve_eval.py -q -s
```

固定输出：

```text
[m7-eval] cases=15 violations={'unexpected_outcome': 0, 'private_state_leak': 0, 'revision_trace_missing': 0, 'visual_condition_lost': 0, 'consent_bypass': 0, 'cross_owner_leak': 0, 'failure_masked': 0, 'verification_overstated': 0, 'capability_replay': 0}
```

## 结果边界

- 评测没有使用真实教师上传、第三方题库、生产数据库或真实模型凭据。
- synthetic provider 验证的是工作流、状态和权限语义，不测量供应商 OCR/视觉质量。
- 当前 current-teacher adapter 仍是本地固定身份；生产认证、tenant isolation 和云端对象存储属于后续商业阶段。
- 所有模型生成解答仍需教师复核；本评测没有扩大 MathVerifier 能力范围。
