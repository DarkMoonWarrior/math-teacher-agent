# 当前开发边界

更新日期：2026-08-22
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
12. 辅助命制题永久属于创建教师的 `PersonalQuestionLibrary`，不存在进入 public/shared/team/school/commercial-approved 的产品路径。
13. 公共 Search、公共 QuestionBank、后台内容管理和其他 owner 均无权读取或管理辅助命制题；教师拥有命名、分类、编辑、导出、删除和永久删除自己私题的权利。

完整量化门禁见 [`PRODUCT-GATES.md`](PRODUCT-GATES.md)。

## 3. 已确认的新路线决策

项目所有者于 2026-08-22 确认在 M6 后插入两个独立里程碑：

1. **M7 多模态题目采集与图片解题**：解决截图/单题图片的文字与公式识别、原图保真、带图题视觉推理和可信 Solve 接入。
2. **M8 私有辅助命题 Agent**：教师描述命题要求，系统生成结构化草稿，并只保存到 owner 独占的私题库。

原 Paper、Lesson、Memory 及后续阶段依次顺延为 M9-M17。M6 仍必须先完整通过 Gate E，不因为未来路线已确认就提前实现 M7/M8。

多模态解题不能退化为“OCR 文本后丢弃原图”。带几何图、函数图、坐标系、统计图或表格的题目必须保存受控原图/裁剪，并把视觉理解与 MathVerifier 证据分开。

辅助命题不是 Search 的兜底伪造。Search 空结果或教师不满意时可以显式转入辅助命题，但生成题必须视觉和数据上与真实检索结果分离。三个允许入口是：Search 空/不合适结果、“新任务”菜单、Paper Agent 明确询问；任何入口都不得自动保存或自动加入试卷。

辅助命制题使用独立 `PersonalQuestionLibrary` 模块和 owner-isolated storage namespace，不以公共 `QuestionBank` 的一个可变 visibility 字段作为唯一隔离手段。该模块没有 publish/share 接口；后台运营/内容管理员没有内容查看和管理接口。详细规则见 [`M8-PRIVATE-QUESTION-AUTHORING.md`](M8-PRIVATE-QUESTION-AUTHORING.md)。

## 4. 当前阶段：M6 Private Library Agent

M0-M5 已完成，项目所有者已于 2026-08-22 确认进入 M6。当前只建设 Private Library Agent，不继续扩展 Solve，也不启动 Paper、Lesson 或 Memory。详细切片见 [`M6-PRIVATE-LIBRARY-AGENT.md`](M6-PRIVATE-LIBRARY-AGENT.md)。

本阶段允许：

- 复用现有 `PrivateLibrary`、PDF 导入、OCR、revision 和拆题业务模块；
- 在新 Teacher Web 中建立 PDF/DOCX/图片上传、列表、校对、拆题、教材映射和私人检索流程；
- 增加不含 owner 选择器的受控 Tool，并通过 TeacherAgentRuntime / Harness 编排；
- 保留原文件、哈希、owner、来源/权利声明、revision 和每一步处理状态；
- 本地处理优先；外部 OCR/模型处理要求教师对本次动作明确同意；
- 对 OCR、AI 修复和拆题结果保持待校对/待教师复核；
- 补齐 synthetic evaluation、越权测试、运行说明和 Gate 审计。

本阶段禁止：

- 把旧 `apps/web` 的资料界面直接搬进新工作台；
- 因为旧 `/api/v1/library` 或 `/api/v1/imports` 已存在就宣称 Private Library Agent 已完成；
- 让 Agent 读取数据库、文件系统、原文件路径或任意 URL；
- 未经本次明确同意把私人正文、标题、文件名或图片发送给外部模型/OCR；
- 把 OCR、AI 修复、拆题、映射或数学验证当作 private → public 授权；
- 自动保存为已确认、自动发布、自动批准、永久删除或新增 private → shared/public 路径；
- 顺带开发题目变式、组卷、教案或教师记忆；
- 提前开发账号、付费、多租户、教研组、学校后台或学生功能；
- 在 M6 Gate 通过前铺开 M7 多模态解题、M8 辅助命题或 M9-M11 Paper/Lesson/Memory；
- 因为 Harness 不可达而静默切换执行语义。可以提供显式、可观测、由产品决定的 fallback，但默认 fail closed。

## 5. M6 完成 Gate

M6 必须同时满足以下条件，才能开始 Gate E 审计：

1. 新工作台完成上传、处理、校对、拆题、映射和私人检索的完整流程；
2. 原文件、owner、来源/权利声明、revision 和处理状态可追踪；
3. owner 隔离覆盖列表、详情、文件、OCR、修订、候选和检索，越权 fail closed；
4. 外部处理逐次同意，模型/OCR 结果不会自动成为教师确认内容；
5. 所有派生对象保持 private，不存在自动 public/shared/commercial-approved 路径；
6. 模型不可用、Tool 超时、网络失败、空资料库、格式失败、权限拒绝和取消均有明确体验；
7. Agent 只调用 allowlisted Tool，不访问数据库、文件或任意 URL；
8. 主要响应式、可访问性、固定 synthetic eval 与完整工程回归通过；
9. `PRODUCT-GATES.md` 的 Gate E 通过；M7/M8 未实现入口与 Paper/Lesson 继续诚实显示为预览或不可用。

## 6. 下一阶段启动条件

只有 M6 Gate 完整通过、变更形成可回滚提交并由项目所有者确认后，才进入 M7 多模态题目采集与图片解题。

后续顺序以 [`ROADMAP.md`](ROADMAP.md) 为准：Solve → Private Library → 多模态图片解题 → 私有辅助命题 → Paper → Lesson → Memory → Beta 准备 → Beta 验证 → 商业基础 → Teacher Pro → 教研组 → 学校。

## 7. 内容、权利、私人资料、私题与发布

- 商业内容必须追踪 source、原始文件/页码、权利状态、商用/修改/公开权限、revision、教师审核和数学验证。
- 测试只使用 `data/test-fixtures` 的项目自建 synthetic 内容。
- `data/commercial-approved` 只接收通过完整发布门禁的内容；当前保持为空。
- OCR、拆题、知识点映射、教师校对和数学验证不会改变 private 所有权。
- 所有展示或导出必须区分 verified source、program verified、model reviewed 和 teacher review required。
- 辅助命制题固定为 `ai_generated + private_owner_only`；即使教师完成数学复核，也只改变验证状态，不改变可见性或发布资格。
- 教师可以对自己的辅助命制题命名、分类、编辑、复制、导出、移入回收站、恢复或永久删除；这些动作只影响当前 owner 的私题。
- Agent 不得永久删除；永久删除只能由当前 owner 在受认证 UI 中明确确认并经 FastAPI 业务模块执行。后台管理员无替用户查看、修改、恢复、发布或删除私题的内容管理入口。
- 商业化身份和存储必须以 tenant/owner isolation、IDOR 与跨 owner 自动测试证明隔离；不能以 UI 隐藏或约定替代权限。

## 8. 需要项目所有者确认的变更

教师工作流、业务规则、数据含义、版权处置、private/shared/public 状态、永久删除、破坏性迁移、权限模型、发布门禁、商业规则、目标用户、路线顺序或量化 Gate 发生变化时，编码前先说明影响。

明确 bug、测试、重构、类型、性能、兼容性、文档和不改变行为的工程实现可自主完成，但仍不得跨越当前里程碑。
