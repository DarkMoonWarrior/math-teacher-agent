# 当前开发边界

更新日期：2026-08-26
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

## 4. 当前阶段：M8 私有辅助命题 Agent

M0-M7 已完成；项目所有者在查看 M7 Gate E 结果后于 2026-08-24 明确确认进入 M8。当前只能按 [`M8-PRIVATE-QUESTION-AUTHORING.md`](M8-PRIVATE-QUESTION-AUTHORING.md) 的纵向切片开发私有辅助命题，不得并行进入 Paper、Lesson、Memory 或其他后续阶段。

M8 切片 1–8 已建立独立 `PersonalQuestionLibrary` 深模块、本地 owner-isolated SQLite namespace、身份绑定的个人题库/分类、结构化生成、六项可信检查、私有命题工作区、append-only revision、显式保存、完整 owner 管理接口及 Teacher Web 入口。教师只需描述命题意图；年级、题型、难度是可选便捷约束，教材知识点、细分知识点、考查方法和易错点由 Agent 在生成后归纳。provider 必须先生成不含答案的题面与选项，再进行独立求解审核；审核发现条件矛盾、对象不存在、结论不唯一或题目不可作答时，进入按需题面完善，并在每次完善后重新审核。只有审核通过的题面才能生成解析；标准答案只能从完整解析推导，随后由第二次独立求解审核题面、解析与答案。若审核判定题面有误，必须完善题面、重新审核并重新生成解析；若题面成立但解析或答案有误，必须保留题面并重新生成解析。初次题面审核答案、解析结论与最终独立审核不一致时，以最终审核判责并进入对应返工分支，而不是直接终止或返回半成品。只有题面、解析和标准答案闭环一致后才能建立草稿。命题生成只能落在中国普通高中数学范围；明确大学专属术语触发受控重写，仍越界时诚实失败。选择题题干与选项必须分字段，展示层逐项渲染。生成 UI 显示“整理命题要求、命制题面、审核题面、完善题面（按需）、生成解析、审核解析与答案、重生成解析（按需）、建立私有草稿”八个真实阶段、旋转状态和已用时间，不暴露思维链或虚构进度。解析只允许展示正式成稿。教师单独重新生成解析时，业务层保持题面和选项不变，标准答案按新解析重新推导，新 revision 再经过一致性检查。模型只能选择受控 Curriculum 节点；浏览器不能提交 owner、隐私状态或可信证据；Agent 没有保存、管理、发布、共享或删除权限。

本阶段允许：

- 建立 `QuestionAuthoring.create_draft(QuestionDesignBrief) -> GeneratedQuestionDraft`，隐藏需求补全、Curriculum、provider、结构检查、MathVerifier 和错误语义；
- 在 `apps/teacher-web` 接入 Search 空/不合适结果、“新任务”和未来 Paper 明确询问三个入口，并保持 AI 生成题与真实检索题视觉和数据分离；
- 接入 Search 空/不合适结果和“新任务”两个现有入口，并为未来 Paper 保留只询问、不自动生成的入口契约；
- 使用 synthetic provider 和项目自建题目验证结构、数学可信状态、取消/失败及隐私语义；
- 只记录不含完整提示与题目正文的最小运行元数据。

本阶段禁止：

- 把辅助命制题写入、复制到或映射为公共 `QuestionBank` 记录；
- 提供 publish/share/public/team/school/commercial-approved 状态或接口；
- 让 Agent、模型、浏览器或管理员选择 owner、自动保存、覆盖或永久删除；
- 把 Search 结果和生成题混合展示，或在 Search 空结果时自动生成；
- 为未来 Paper 凑题而自动命题、自动保存或自动加入试卷；
- 允许后台运营、内容管理员、其他 owner 或模型训练流程读取私题内容；
- 把模型生成或排版成功冒充 MathVerifier 验证；
- 提前开发 M9 Paper、M10 Lesson、M11 Memory、账号、支付、多租户、教研组、学校后台或学生功能。

## 5. M8 完成 Gate

M8 必须同时满足 [`M8-PRIVATE-QUESTION-AUTHORING.md`](M8-PRIVATE-QUESTION-AUTHORING.md) 的功能 Gate、[`PRODUCT-GATES.md`](PRODUCT-GATES.md) 的 Gate E 与 Gate P，并完成固定 synthetic evaluation、跨 owner/IDOR/公共搜索泄漏/后台权限测试、完整工程回归和响应式/可访问性验收。当前切片 1–8 完成，尚未达到 M8 Gate。

## 6. 下一阶段启动条件

只有 M8 Gate E 与 Gate P 完整通过、变更形成可回滚提交并由项目所有者再次确认后，才进入 M9 Paper Agent。

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
