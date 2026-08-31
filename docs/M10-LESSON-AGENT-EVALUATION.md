# M10 Lesson Agent 固定评测

评测日期：2026-08-31

结论：**28 个项目自建 synthetic 场景全部执行，15 类违规均为 0。**

## 1. 评测资产

- 固定用例：`data/test-fixtures/lesson-agent/eval-cases.json`
- 执行入口：`apps/api/tests/test_lesson_agent_eval.py`
- 数据性质：`project-authored-synthetic`；不包含真实教师资料、私人题目、商业题库或生产凭据。
- 复现命令：`python -m pytest apps/api/tests/test_lesson_agent_eval.py -q -s`

## 2. 覆盖范围

28 个场景覆盖：

1. 无副作用、可编辑、未确认、未保存的教案蓝图，以及可见默认假设；
2. 明确大学范围拒绝与普通高中范围保持；
3. 教师确认后的来源草案、当前 owner 私人资料、真实来源缺口和精确 revision；
4. 教学目标、重难点、完整流程、完整题面/选项/答案/解析、评价、作业、板书和备注；
5. 课时总和、目标—活动、目标—评价和来源清单闭环；
6. 只改变目标块的定向改写、锁定保护和题目事实不可漂移；
7. 浏览器 owner 伪造拒绝、显式保存、append-only 版本、本人历史和可恢复生命周期；
8. 指定已保存版本 DOCX/PDF、后续版本不串入、跨 owner 导出拒绝；
9. Agent allowlist 不含教案保存、导出、删除、恢复、发布或共享 Tool。

## 3. 违规结果

以下 15 类结果均为 `0`：

`unexpected_outcome`、`scope_escape`、`source_gate_bypass`、`cross_owner_leak`、`incomplete_lesson_delivered`、`question_completeness_lost`、`alignment_broken`、`source_traceability_lost`、`targeted_edit_drift`、`locked_edit_bypass`、`question_fact_drift`、`implicit_save`、`immutable_version_drift`、`export_snapshot_drift`、`agent_privilege_escalation`。

## 4. 解释边界

- 评测证明当前确定性业务 Interface 在固定场景下遵守 M10 开发边界，不代表真实教师认可率、长期数学错误率或商业题库供给已经验证。
- `draft_requires_teacher_review` 在保存和导出后仍保持；排版成功、教师保存和本评测都不会把 AI 文本升级为教师审定或数学验证。
- 来源不足时不会交付半份教案；正常完成态必须是闭环完整教案。
- DOCX/PDF 只证明从精确不可变版本生成，不能替代生产认证、云租户隔离、备份恢复和真实设备兼容验证。

## 5. 文档视觉检查

使用同一精确已保存版本生成教师教案 DOCX 5 页和 PDF 4 页并逐页检查。题面、选项、参考答案、完整解析、目标—活动—评价关系、私人资料摘录边界和来源摘要均可读；未发现裁切、重叠、乱码或版本二内容混入版本一。DOCX 首轮来源表跨页后已调整为独立来源页并重新检查。
