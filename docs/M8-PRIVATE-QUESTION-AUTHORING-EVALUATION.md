# M8 私有辅助命题固定评测

评测日期：2026-08-28

数据来源：项目自建 synthetic fixture

评测标识：`private-question-authoring-synthetic-v1`

## 结论

固定评测共 26 个场景，12 类违规计数全部为 0。评测只使用仓库自建合成内容，不调用真实模型、不读取教师私人资料，也不把评测题写入公共或商业题库。

```text
[m8-eval] cases=26 violations={
  unexpected_outcome: 0,
  incomplete_draft: 0,
  scope_escape: 0,
  privacy_policy_leak: 0,
  cross_owner_leak: 0,
  public_search_leak: 0,
  agent_privilege_escalation: 0,
  failure_masked: 0,
  revision_trace_missing: 0,
  delete_guard_bypass: 0,
  saved_question_loss: 0,
  cancellation_masked: 0
}
```

## 固定场景

| 分组 | 场景 | 验收点 |
| --- | --- | --- |
| 题型 | 单选、多选、填空、解答 | 题面、适用选项、可读解析和解析所得答案完整，未返回半成品 |
| 高中模块 | 圆锥曲线、概率、数列、三角、立体几何 | 保持在普通高中数学范围并形成完整草稿 |
| 内容契约 | 选择题选项分离、未完成解析拒绝、大学范围拒绝 | 题干不串入 A–D；已知缺陷不成为正常交付；明确越界才终止 |
| 故障 | 模型不可用、后台取消 | 故障诚实可解释；取消后结果为空且不会越过提交边界 |
| 权利 | 未验证参考母题 | adaptation 权利不明时 fail closed |
| 隐私 | owner-only 策略、浏览器 owner 伪造、跨 owner、公共 Search、Agent 管理权限 | owner 由服务端绑定；无公共泄漏或特权 Tool |
| 生命周期 | 显式保存、独立复制、回收/恢复、受控永久删除、历史删除、append-only revision | 保存和删除都由 owner 明确触发，已保存私题不随历史删除 |

完整机器可读场景位于 `data/test-fixtures/private-question-authoring/eval-cases.json`，执行器位于 `apps/api/tests/test_private_question_authoring_eval.py`。

## 执行方法

```powershell
$env:PYTHONPATH='apps/api'
.\.venv\Scripts\python.exe -m pytest apps/api/tests/test_private_question_authoring_eval.py -q -s
```

## 边界

- 本评测证明确定性业务契约、隐私边界和恢复语义，不把合成题通过冒充真实模型数学正确率。
- 任意模型生成题仍显示 `teacher_review_required`；当前通用 `MathVerifier` 不支持时必须如实披露。
- 真实教师严重数学错误率属于 Closed Beta Gate Q，尚无数据，不在本次 M8 Gate 中虚构。
