# test-fixtures

只允许放置：

- 项目自行创建（synthetic）的数据；
- 权利明确用于测试的数据（例如程序生成的几何图、合成 PDF/DOCX）。

禁止把真实第三方题目、试卷原文或教师私人资料复制进 fixture 以让测试通过。
需要真实数据的测试必须显式记录为 blocker / migration issue
（见 `docs/commercial-v1/KNOWN-MIGRATION-ISSUES.md`）。
