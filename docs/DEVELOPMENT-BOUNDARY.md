# 当前开发边界

更新日期：2026-08-21
状态：当前 source of truth；历史 PDF 和旧 Prompt 保留为决策证据，但不再决定当前阶段编号。

## 1. 产品定位与唯一目标用户

产品是面向中国高中数学教师的可信 AI Agent 工作台。教师通过自然语言、题目图片、PDF 或私人教学资料描述需求，系统逐步协助完成搜题、解题、私人资料整理、组卷与教案等备课工作流，并为关键结果展示来源、权利、验证和教师复核状态。

它不是传统搜题站，也不是通用聊天机器人。长期竞争力来自高质量结构化题库、`MathVerifier`、`RightsGate`、`PrivateLibrary`、教材知识图谱、题目相似/变式关系、可控教师偏好，以及 Teacher Agent 对完整备课工作流的理解；不得为短期开发速度破坏或复制这些资产。

当前只服务中国高中数学教师。不开发学生端、家长端、小学、初中、其他学科、在线课堂、社区、学校 ERP、成绩管理或全功能 LMS。

## 2. 从历史规划继承的不可违反原则

1. 数学正确性优先；大模型输出不等于 `MathVerifier` 验证。
2. 题目和解析必须保留来源、权利、revision、审核与验证证据。
3. 来源或权利不明内容进入 quarantine/review，不进入商业公共题库。
4. 教师上传及其所有派生内容 private-by-default；private → shared/public 必须明确授权。
5. Agent 不直接访问 SQL、SQLite、PostgreSQL、ORM、数据库文件或教师私人文件。
6. 唯一业务链路是 Agent → allowlisted Tool → FastAPI 业务模块 → Rights/Permission/Validation → storage。
7. AI 产物默认 draft；Agent 不得 publish、批准权利、批准数学验证或永久删除。
8. 业务系统只依赖产品自有 `TeacherAgentRuntime`；DeepSeek Harness 和模型供应商必须可替换。
9. 不修改 Harness core；优先 adapter/plugin/tool/preset；不复制第二套搜索、核验、组卷和教案业务逻辑。
10. 每个阶段通过功能、可信、权利/隐私和工程 Gate 后才能进入下一阶段。
11. 现阶段优先模块化单体和清晰接口，不为“架构高级”提前拆微服务。

完整量化门禁见 [`PRODUCT-GATES.md`](PRODUCT-GATES.md)。

## 3. 当前里程碑：M5 Solve Agent

M0-M4 已完成，项目所有者已确认进入 M5。当前只建设可信解题工作流，不启动 Private Library、Paper、Lesson 或 Memory。

本阶段允许：

- 复用现有 `SolutionAssistant`，优先返回题库中已有的已验证解析；
- 增加受控只读 `solve_question` Tool，并通过 TeacherAgentRuntime / Harness 编排；
- 支持完整文字题与 Search 结果题进入新工作台解题流程；
- 展示解法、最终答案、知识点、易错点、教学提示和验证证据；
- 对模型新解答强制 `teacher_review_required`，对 MathVerifier 不支持或不确定的结果保持待复核；
- 完善加载、取消、模型不可用、Tool 失败、验证不确定和重试体验；
- 补齐 synthetic evaluation、运行说明、测试和 Gate 审计。

本阶段禁止：

- 把旧 `apps/web/solve` 的视觉壳直接搬进新工作台；
- 因为旧 `/api/v1/solutions/solve` 已存在就宣称 Solve Agent 已完成；
- 新增 Agent 写数据库、自动发布、自动批准、批量删除或 private → public 路径；
- 把模型生成解析、第二模型复核或格式校验冒充 `program_verified`；
- 自动保存、覆盖或发布题目答案与解析；
- 顺带开发题目变式、图片/PDF 导入、组卷、教案或教师记忆；
- 提前开发账号、付费、多租户、教研组、学校后台或学生功能；
- 同时铺开 M6-M9；
- 因为 Harness 不可达而静默切换执行语义。可以提供显式、可观测、由产品决定的 fallback，但默认 fail closed。

## 4. M5 完成 Gate

M5 只有同时满足以下条件才完成：

1. 精确匹配的已验证题库解析优先返回，并携带 question/revision/验证证据；
2. 新题或新解法的模型结果始终为 `teacher_review_required`，不自动升级可信等级；
3. MathVerifier 的支持、通过、失败与 inconclusive 状态可区分，失败路径不被模型文字覆盖；
4. 新工作台完成文字输入、Search 结果转入解题、运行、取消、错误、重试和结果可信展示；
5. 模型不可用、Tool 超时、权限拒绝、无已验证解析和验证不确定均有明确体验；
6. Agent 只调用 allowlisted Tool，不访问数据库，不保存、发布或批准解析；
7. 320-1920px 无关键横向溢出，关键操作可键盘访问并尊重 reduced motion；
8. Primary UI、FastAPI、Agent Runtime 的相关测试、类型检查和生产构建通过；
9. `PRODUCT-GATES.md` 的 Gate E 通过；Lesson/Paper 继续诚实显示为预览。

## 5. 下一阶段启动条件

只有 M5 Gate 完整通过、变更形成可回滚提交并由项目所有者确认后，才进入 M6 Private Library Agent。

后续顺序以 [`ROADMAP.md`](ROADMAP.md) 为准：Solve → Private Library → Paper → Lesson → Memory → Beta 准备 → Beta 验证 → 商业基础 → Teacher Pro → 教研组 → 学校。

## 6. 内容、权利、私人资料与发布

- 商业内容必须追踪 source、原始文件/页码、权利状态、商用/修改/公开权限、revision、教师审核和数学验证。
- 测试只使用 `data/test-fixtures` 的项目自建 synthetic 内容。
- `data/commercial-approved` 只接收通过完整发布门禁的内容；当前保持为空。
- OCR、拆题、知识点映射、教师校对和数学验证不会改变 private 所有权。
- 所有展示或导出必须区分 verified source、program verified、model reviewed 和 teacher review required。

## 7. 需要项目所有者确认的变更

教师工作流、业务规则、数据含义、版权处置、private/shared/public 状态、永久删除、破坏性迁移、权限模型、发布门禁、商业规则、目标用户、路线顺序或量化 Gate 发生变化时，编码前先说明影响。

明确 bug、测试、重构、类型、性能、兼容性、文档和不改变行为的工程实现可自主完成，但仍不得跨越当前里程碑。
