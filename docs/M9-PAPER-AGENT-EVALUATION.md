# M9 Paper Agent 固定评测

评测日期：2026-08-29

数据来源：项目自建 synthetic fixture

评测标识：`paper-agent-synthetic-v1`

## 结论

固定评测共 28 个场景，15 类违规计数全部为 0。评测只使用仓库自建合成需求与题目，不调用真实模型、不读取教师私人资料，也不把评测题写入公共题库、私人题库或商业批准目录。

```text
[m9-eval] cases=28 violations={
  unexpected_outcome: 0,
  scope_escape: 0,
  trust_gate_bypass: 0,
  rights_gate_bypass: 0,
  cross_owner_leak: 0,
  explicit_selection_lost: 0,
  duplicate_inclusion: 0,
  supply_gap_masked: 0,
  coverage_overstated: 0,
  draft_state_escalation: 0,
  forged_layout_accepted: 0,
  stale_draft_accepted: 0,
  immutable_version_drift: 0,
  export_answer_leak: 0,
  agent_privilege_escalation: 0
}
```

## 固定场景

| 分组 | 场景 | 验收点 |
| --- | --- | --- |
| 蓝图与范围 | 明确期中卷、缺省字段、大学范围 | 总分守恒；假设可见可改；明确大学范围在业务层拒绝 |
| 公共可信门禁 | 可用公共题、待审核题、权利阻断题、验证失败题 | 只有 public、active、approved、通过 MathVerifier 且权利完备的题进入候选 |
| 显式选题与隐私 | 公共题显式选择、私题显式选择、四道跨知识范围私题、跨 owner 私题 | 教师显式意图不被软范围误过滤；私题只引用不复制；跨 owner fail closed |
| 去重与供给 | 重复题、题量不足 | 重复/高相似题被排除；真实缺口可见且不自动命题 |
| 结构与选题分析 | 知识点缺失、难度偏差、题量/分区/配分缺口 | 所有偏差可见但不阻止教师明确选题；保存前二次确认，确认后保存当前精确版本 |
| 可编辑草稿 | 未保存状态、伪造布局、双向细目表 | 服务端重建候选；浏览器不能注入题；编辑不隐式保存；正反向规格完整 |
| 身份与保存 | 浏览器伪造 owner/可信字段、显式保存、过期指纹 | owner 由服务端注入；只有显式动作建立版本；陈旧草稿不产生版本 |
| 版本与导出 | 跨 owner 导出、题库变更、学生卷、答案卷、细目表、六种导出 | 精确版本不可变；学生卷无答案；答案卷含完整解析；细目表双向；导出契约固定 |
| Agent 权限 | 组卷写入/保存/导出 Tool 检查 | Agent allowlist 不含组卷写入、保存、导出、发布或删除能力 |

完整机器可读场景位于 `data/test-fixtures/paper-agent/eval-cases.json`，执行器位于 `apps/api/tests/test_paper_agent_eval.py`。

## 执行方法

```powershell
$env:PYTHONPATH='apps/api'
.\.venv\Scripts\python.exe -m pytest apps/api/tests/test_paper_agent_eval.py -q -s
```

## 边界

- 本评测证明确定性的蓝图、选题、可信/权利、owner、覆盖、版本和导出业务契约，不把 synthetic 通过冒充真实教师场景的数学正确率。
- 本地公共题库目前没有通过全部公共门禁的可用供给；系统如实展示空状态，不以私题、待审核题或合成题填充生产候选。
- 学生卷、答案卷和双向细目表的逐页视觉质量已有真实本地导出回归证据；本固定评测补充验证其内容隔离与不可变版本语义。
- 真实教师采用率、严重数学错误率和单位成本属于 Closed Beta Gate Q/C，尚无数据，不在 M9 Gate 中虚构。
