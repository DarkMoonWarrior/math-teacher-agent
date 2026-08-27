# 当前开发边界

更新日期：2026-08-28
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
14. 面向教师展示的数学内容必须渲染为可读公式；不能把 LaTeX 源码作为默认正文，也不能把排版成功冒充数学验证通过。统一规范见 [`MATH-CONTENT-PRESENTATION.md`](MATH-CONTENT-PRESENTATION.md)。
15. 所有面向用户交付的 Agent 内容必须闭环完成。“草稿”只表示尚未由用户保存或确认，不表示允许残缺、已知错误或需要用户代替系统完成核心工作。辅助命题交付前必须具备完整题面、完整选项（如适用）、可读解析、由解析推导的标准答案和一致性审核；发现题面或解析问题必须在内部判责并返工，不能把半成品交给教师自行修错。教师可以自主编辑已完成内容，但不承担替 Agent 补全交付物的责任。
16. 辅助命题的单个候选或同一题解析重试耗尽不是用户终点。系统必须在后台继续完善题面、重生成解析或整题重命，直至交付完整正确题目；只有明确检测到大学范围内容时可以终止并说明边界。后台任务不与页面生命周期绑定，切换页面不得取消已受理任务。
17. “上一次”和“命题历史”只能读取当前 owner 的完整结果。owner 可以删除历史；未保存结果随历史删除，已保存私题仅隐藏历史入口，不得连带删除私题。

完整量化门禁见 [`PRODUCT-GATES.md`](PRODUCT-GATES.md)。

## 3. 已确认的新路线决策

项目所有者于 2026-08-22 确认在 M6 后插入两个独立里程碑：

1. **M7 多模态题目采集与图片解题**：解决截图/单题图片的文字与公式识别、原图保真、带图题视觉推理和可信 Solve 接入。
2. **M8 私有辅助命题 Agent**：教师描述命题要求，系统生成结构化草稿，并只保存到 owner 独占的私题库。

原 Paper、Lesson、Memory 及后续阶段依次顺延为 M9-M17。M6 仍必须先完整通过 Gate E，不因为未来路线已确认就提前实现 M7/M8。

多模态解题不能退化为“OCR 文本后丢弃原图”。带几何图、函数图、坐标系、统计图或表格的题目必须保存受控原图/裁剪，并把视觉理解与 MathVerifier 证据分开。

辅助命题不是 Search 的兜底伪造。Search 空结果或教师不满意时可以显式转入辅助命题，但生成题必须视觉和数据上与真实检索结果分离。三个允许入口是：Search 空/不合适结果、“新任务”菜单、Paper Agent 明确询问；任何入口都不得自动保存或自动加入试卷。

辅助命制题使用独立 `PersonalQuestionLibrary` 模块和 owner-isolated storage namespace，不以公共 `QuestionBank` 的一个可变 visibility 字段作为唯一隔离手段。该模块没有 publish/share 接口；后台运营/内容管理员没有内容查看和管理接口。详细规则见 [`M8-PRIVATE-QUESTION-AUTHORING.md`](M8-PRIVATE-QUESTION-AUTHORING.md)。

## 4. 当前阶段：M9 Paper Agent 进行中

M0-M8 已完成；M8 的固定评测、Gate E 与 Gate P 于 2026-08-28 通过。项目所有者于 2026-08-28 明确确认进入 M9。当前只开发 Paper Agent；M10 Lesson、M11 Memory 和后续阶段仍未获准启动。

M8 已建立独立 `PersonalQuestionLibrary` 深模块、本地 owner-isolated SQLite namespace、身份绑定的个人题库/分类、结构化生成、六项可信检查、私有命题工作区、append-only revision、显式保存、完整 owner 管理接口及 Teacher Web 入口。教师只需描述命题意图；教材知识点、细分知识点、考查方法和易错点由 Agent 在生成后归纳。provider 先生成不含答案的题面与选项，再独立审核；题面错误进入完善、复审和重新解析，解析错误保留题面并重生成解析。标准答案只从完整解析推导并接受最终一致性审核。只有题面、选项、可读解析和答案闭环一致后才能建立草稿。命题限定普通高中数学，明确大学专属术语经受控重写后仍越界才终止。后台任务独立于页面生命周期并可恢复；owner 可显式取消，且取消在私人草稿写入前再次检查，保证不提交半成品。模型只能选择受控 Curriculum 节点；浏览器不能提交 owner、隐私状态或可信证据；Agent 没有保存、管理、发布、共享或删除权限。

M9 的固定范围、切片顺序和验收见 [`M9-PAPER-AGENT.md`](M9-PAPER-AGENT.md)。当前第一切片只建立 `PaperBlueprintPlanning.plan(PaperBlueprintBrief) -> PaperBlueprintDraft`：将自然语言整理为可编辑、未确认、未保存的蓝图，不查询题目、不生成题目、不写入存储。

本阶段允许：

- 建立自然语言到可编辑 `PaperBlueprint` 的深模块与 FastAPI 产品接口；
- 在 `apps/teacher-web` 接入蓝图规划、可见默认假设和本地编辑；
- 后续切片在教师确认蓝图后复用既有组卷、版本快照和导出业务模块；
- 使用项目自建 synthetic 需求和题目验证蓝图、选题、权利、验证、相似度、覆盖、难度和导出语义。

本阶段禁止：

- 在蓝图规划阶段查题、选题、生成题目、保存蓝图或建立试卷；
- 为满足题量自动命题、自动保存私题或自动加入试卷；
- 让 Agent、模型或浏览器选择 owner、rights、verification、visibility 或发布状态；
- 复制私题、改变私题 owner/visibility，或让其他 owner、管理员、公共 Search 和训练流程读取私题；
- 把模型判断、排版成功或教师确认蓝图冒充 MathVerifier 验证或正式试卷保存；
- 提前开发 M10 Lesson、M11 Memory、账号、支付、多租户、教研组、学校后台或学生功能。

## 5. M9 当前 Gate

M9 尚未完成。第一切片只验收蓝图规划接口、总分守恒、显式默认假设、无副作用和 Teacher Web 可编辑性；完整 M9 仍需通过权利、验证、重复/相似、覆盖、难度、私题 owner/visibility、保存版本和导出 Gate。

## 6. 下一阶段启动条件

只有 M9 全部功能、可信、隐私/权利和工程 Gate 通过、变更形成可回滚提交并由项目所有者再次确认后，才进入 M10 Lesson Agent。

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
