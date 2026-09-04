# M8 私有辅助命题 Agent

> 状态同步（2026-09-04）：M0–M11 已完成并完成阶段转换，当前为 M12 切片 1–4。本文的切片过程、测试数量和 Gate 结论保留为当时证据；后续行为与当前边界见 [开发状态](PROJECT-STATUS.md) 和 [开发边界](DEVELOPMENT-BOUNDARY.md)。

更新日期：2026-08-28
状态：已完成；固定评测、Gate E 与 Gate P 已通过，进入 M9 的阶段转换已确认。

## 实施进度

- **切片 1 已完成**：独立 `PersonalQuestionLibrary` 使用 `data/private-runtime/personal-question-library.sqlite3`，不复用公共 `QuestionBank` 表或接口；个人题库集合与分类可由当前 owner 创建、查看和重命名。
- **切片 2 已完成**：`QuestionAuthoring.create_draft` 将自然语言 brief 转换为结构化题干、选项、答案、分步解析、命题意图和预计难度；模型或结构不可用时诚实失败。
- **切片 3 已完成**：每份草稿必须携带可解性、答案/最终答案一致性、选择题答案数量、干扰项结构、MathVerifier 能力和难度披露六项唯一证据；明确矛盾进入 `checks_failed`，其余仍为 `teacher_review_required`。
- **切片 4 已完成**：成功生成的内容只暂存为当前 owner 的未保存命题工作区草稿；教师提交完整编辑快照会追加不可覆盖的 revision 并重跑结构/可信检查。只有认证教师明确指定自己拥有的个人题库、分类、名称和当前版本后才创建私题，旧版本提交返回冲突。
- **切片 5 已完成**：active 私题可按 owner 列表/搜索、重命名、移动分类、标签排序、保存后继续追加 revision、独立复制及以 JSON/Markdown 私有导出；回收站与恢复使用乐观版本。永久删除只接受已进回收站的当前版本和固定 owner 确认短语，并在同一事务中清除该题独占的活动快照、命题草稿与全部 revision；独立副本不受影响。
- **切片 6 已完成**：Teacher Web 已从“新任务”、Search 空结果/不合适结果和 Paper 题量不足提示三个必需位置接入独立辅助命题工作区，并在顶部能力导航增加“命题”直达入口。教师可填写结构化 brief、查看并编辑未保存草稿、记录 revision、重新执行六项检查、明确选择或新建个人题库/分类后保存；保存后可在同一 owner 工作区管理、导出、回收、恢复或确认永久删除。生成题始终以 `AI GENERATED · UNSAVED` 与真实检索题分开，Paper 入口不自动生成、不自动保存，也不自动加入试卷。临时成功、失败和不可逆删除确认使用可关闭弹窗；可信检查与数学风险披露仍保留在正文。
- **切片 7 已完成**：知识点、考查方法和易错点不再作为生成前门禁。教师只需自然语言意图，年级、题型、难度和其他限制均为可选约束；provider 在题目完成后归纳细分知识点、考查方法、常见错误并建议受控 Curriculum 节点。未知节点被业务层丢弃，无法映射也不阻断 owner-only 草稿；Agent 推断固定为待确认，教师可在结果页检索目录并通过 revision 确认或修正，同时校订全部教学元数据。
- **切片 8 已完成**：选择题题干与选项采用强制分离契约，provider 不得把 A–D 写进题干，业务层会清理重复嵌入的选项并规范化选项编号，Teacher Web 在题面下逐项显示完整选项。命题 provider 明确限定中国普通高中数学范围，业务层对明确大学专属概念执行终检；首次越界会在锁定题面阶段受控重写，仍越界则诚实失败。长时间生成显示持续旋转状态、当前真实外层阶段和已用时间，不虚构百分比也不展示模型思维链。整体 Tool/API 转发预算扩展为有界 15 分钟，内容仍不设长度上限。
- **切片 7 长题能力收口已完成**：撤销“缩短题干/限制解析总字数”方案，DeepSeek adapter 在单一 `create_draft` seam 内生成完整题面，规划解析段、并行展开各段、按序组装。单段格式失败只重试该段；持续截断时仅把该段再拆成原子子段。Teacher Web 使用与 Solve 相同的数学展示契约和 KaTeX 组件呈现题面、长解析步骤与唯一最终答案，原始 LaTeX 只放在可展开校订区。
- **M8 解析质量补强已完成**：解析段契约只允许可直接展示的成稿推导，禁止第一人称试算、自我怀疑、回退、提示词或内部字段讨论。标准答案不在题面生成阶段预设，只能在完整解析完成后提取；教师点击“重新生成解析”时保持题面和选项不变，标准答案随新解析重新推导并追加 `ai_generated` revision。未记录的本地编辑会先提示保存，避免静默覆盖。
- **M8 题面、解析与答案闭环补强已完成**：不含答案的题面生成后、解析规划前执行第一次独立求解审核，检查条件相容性、数学对象存在性、全部小问可答性、高中范围及选择题唯一性。审核失败最多触发三轮不降低难度、不改变题型、不删除教师要求的题面完善，每轮完善后必须重新审核。完整解析完成后执行最终独立求解审核并判责：题面错误进入“完善题面 → 重新审核 → 重新解析”，题面成立但解析或解析所得答案错误进入“保留题面 → 重新生成解析 → 再审核”。初次审核答案与最终审核不一致但解析和最终审核一致时，由最终审核纠正内部初审，不丢弃有效题目。只有完整题面、完整选项、正式解析和解析所得标准答案闭环一致时才建立草稿；不得返回 `needs_teacher_verification` 半成品让教师替 Agent 修错。Teacher Web 显示八步真实进度与已用时间：“整理命题要求、命制题面、审核题面、完善题面（按需）、生成解析、审核解析与答案、重生成解析（按需）、建立私有草稿”。
- **M8 后台闭环与命题历史补强已完成**：同一候选题的题面或解析恢复耗尽后自动整题重命，非大学范围内容不会以“无法交付半成品”结束。命题由 owner-scoped 后台任务持有，切换页面只停止当前页面轮询；返回命题区会恢复真实阶段和计时。可视化增加“重新命题（按需）”。“上一次”直接恢复最近完整结果，“命题历史”可打开和删除任意 owner 自有记录；删除已保存记录不删除私题。
- **M8 后台取消补强已完成**：教师可以明确取消自己的在途命题；共享 `BackgroundJobRegistry` 在 provider 返回后、私人草稿写入前再次执行取消检查。停止时若已有最新审核通过题面，系统会把它作为 owner-only 的“题面已审核、缺少解析”结果保存，答案和解析字段明确为“无”，并允许该 owner 主动加入组卷；若用户放弃则不保留。其他 owner 不能查看或取消，也不会出现界面已取消但后台仍保存的假取消。
- DeepSeek 只实现可替换 provider adapter；Agent 必须且只能调用一次 `create_question_draft`，模型不能增加 owner、保存、发布、共享或删除参数。Agent Tool 仍只返回 `owner_only + saved=false`；暂存和保存由公开 FastAPI 在认证业务层分别执行，Agent 没有相应写 Tool。
- 当前 MathVerifier 只接受带受控 `verification_spec` 的已知规则；任意模型生成题没有这种独立证据，因此固定诚实披露 `math_verifier_status=unsupported`，不得用模型自述冒充程序验证。结构检查通过也不等于数学正确。
- FastAPI 只从 `get_current_teacher` 注入 owner；请求模型 `extra=forbid`，浏览器伪造 `owner_id` 返回 422，跨 owner 读取或修改返回 404。
- 所有返回固定为 `owner_only`，并明确 `public_search_allowed=false`、`share_allowed=false`、`commercial_use_allowed=false`、`model_training_allowed=false`；没有 publish/share/admin 接口。唯一 DELETE 路由只属于认证 owner 的私题，且受回收站、版本与固定确认三重门禁保护。
- **切片 9 与完成 Gate 已通过**：26 场景固定 synthetic evaluation 的 12 类违规均为 0；完整 FastAPI、Teacher Web、Agent 与 legacy 回归通过；Gate E/Gate P 评审见 [`M8-GATE-REVIEW.md`](M8-GATE-REVIEW.md)。M8 已完成，但在所有者查看 Gate 结果并确认前仍不得进入 M9。

## 1. 已确认的产品规则

教师可以向 Agent 描述命题要求，由系统生成一道可编辑、可验算的高中数学题目草稿。辅助命制题是教师个人工作内容，永久只进入该教师的私题库：

- 不得进入公共题库、商业题库、共享题库、教研组题库或学校题库；
- 不得出现在公共 Search 结果、公共推荐、运营审核队列、模型训练集或商业内容加工流程；
- 不存在 private → shared/public/commercial-approved 的产品路径，即使未来商业化也不改变；
- 只有 owner 可以查看、命名、分类、编辑、复制、导出、移入回收站、恢复或永久删除；
- 后台运营人员、内容管理员和其他教师没有查看、编辑、审核、移动、发布、恢复或删除这些题目的权限；
- 系统后台只执行 owner 明确发起的受控存储操作与必要的非内容性运行保障，不以运营、审核、推荐或商业理由干涉题目内容。

这组规则的优先级高于历史“私人题目未来可授权公开”的一般描述。辅助命制题在本产品内永不公开。

## 2. 本阶段唯一目标

建立完整的“教师描述要求 → Agent 生成结构化题目草稿 → 数学与结构检查 → 教师编辑确认 → 保存到个人私题库 → owner 自主管理”工作流。

M8 不建设公共投稿、公共发布、共享协作、商业内容审核、组卷自动补题、学生端或题目交易。Paper Agent 只能在教师明确选择时引用当前 owner 的私题，不能复制或提升其可见性。

## 3. 深模块与 seam

### QuestionAuthoring

`QuestionAuthoring.create_draft(QuestionDesignBrief) -> GeneratedQuestionDraft` 与 `QuestionAuthoring.regenerate_solution(GeneratedQuestionDraft) -> GeneratedQuestionDraft` 是命题业务深模块接口。前者拥有可选需求约束、题面完善、结构化生成和生成后教学元数据归纳；后者保持题面与选项不变，重新求解并同时替换解析和解析所得标准答案。两者共同把受控教材映射、题面审核、答案/解析一致性检查、选择题唯一性检查、MathVerifier、可信状态和错误语义留在实现内部。

这里的 `draft` 只表示当前 owner 尚未明确保存或确认，不表示正常生成允许内容残缺。AI 初次生成和“重新生成解析”都只能返回通过闭环审核的完整结果；已知题面错误、已知解析错误、答案冲突、缺失选项、占位内容或 `solution_status=needs_teacher_verification` 不得成为正常用户交付。唯一例外是 owner 主动停止解析阶段：若题面已经通过独立审核，系统可以把该题面保存为明确标注 `solution_status=needs_teacher_verification`、`solution_issue` 含“解析未生成”的私题，答案、解析方法、步骤和最终答案统一为“无”；该题可由同一 owner 主动用于组卷，组卷/导出显示“无”，但不得标记为完整闭环或数学验证通过。教师仍可主动编辑完整草稿，教师编辑后的 revision 可以诚实显示阻断检查，但系统不得把正常命题未完成的核心责任转嫁给教师。

初次长题生成不会增加 Agent Tool。DeepSeek provider 在内部执行 `answer-free statement → independent statement review → conditional statement repair → solution → solution-derived answer → final fault-classifying review → conditional statement repair or solution regeneration → accepted complete draft`。多个解析段可并行生成，某一段失败时只在 provider 内局部重试；数学冲突必须标记来自题面还是当前解析并进入对应恢复分支。教师明确点击“重新生成解析”时，认证 FastAPI 业务接口从 owner 当前 revision 恢复题面与选项，不经浏览器或 Agent 选择 owner；新解析完成后重新推导标准答案并再次审核，失败时在内部受控重试而不是返回冲突 revision。内容 Schema 与业务模型允许长题干和长解析，基础设施保留 15 分钟有界总预算以防失控请求，但不得把超时保护变成删题、压缩步骤或降低难度的内容规则。

`QuestionDesignBrief` 只强制要求自然语言命题意图；年级、教师明确选择的教材节点、题型、目标难度、教学用途、预计用时、显式方法/干扰项约束、可选参考题和补充限制都是可选信息。不得因教师没有先填写知识点、考查方法或易错点而拒绝生成。`GeneratedQuestionDraft` 包含题干、LaTeX、选项、答案、分步解析、命题意图、可空的教材映射、细分知识点、考查方法、常见易错点、目标/预计难度、验证证据、warnings、provider/model/prompt revision 和 `source_type=ai_generated`。

所有生成题必须属于中国普通高中数学。不得因教师要求“难”而引入随机过程、马尔可夫链、傅里叶分析、测度论、泛函分析、偏微分方程等大学专属内容。选择题的 `stem`/`stem_latex` 只保存题干，A–D 只保存在 `options` 数组；任一层都不得通过字面 `\\nA.` 串接选项或把选择题退化成解答题。Teacher Web 的可读题面必须在题干后独立渲染全部选项。

模型只能从业务层提供的 Curriculum allowlist 中返回节点 ID，不能创建教材节点或自行升级审核状态。教师明确选择的节点优先于模型建议；Agent 推断的节点标记为 `pending_teacher_confirmation`，只有 owner 在结果页明确确认或修正后才成为 `teacher_confirmed`。无法可靠映射时保留空映射和诚实 warning，不阻断私人草稿，也不把“未映射”冒充教材证据。

参考母题模式可以复用现有题目变式能力，但只有在母题已验证且 RightsGate 明确允许 adaptation 时可用。完全自主命题不得虚构题源、年份、学校、试卷或教材页码。

### PersonalQuestionLibrary

`PersonalQuestionLibrary` 是独立于公共 `QuestionBank` 的 owner-scoped 深模块。它拥有个人集合命名、分类、题目 CRUD、revision、导出和删除语义；公共题库没有读取它的接口，它也没有 publish/share 接口。

current owner 只能由认证上下文在服务端确定，任何浏览器或模型参数中的 `owner_id` 都必须拒绝。商业化后使用 tenant/owner 隔离的存储 adapter，并以跨 owner、IDOR、备份恢复和删除测试证明隔离，而不是只依赖 UI 隐藏。

```text
Teacher Web → QuestionAuthoring → MathVerifier/Curriculum/RightsGate
                         ↓ owner 工作区草稿（尚未成为私题）
教师编辑 → append-only revision → 服务端重跑可信检查
教师明确保存 → owned collection/category → owner-isolated private question

Public Search / Public QuestionBank / Admin content tools ──X──> PersonalQuestionLibrary
```

Agent 只生成或提出修改草稿；保存、覆盖、删除和永久删除必须由教师在受认证 UI 中明确确认，并通过 FastAPI 业务模块执行。Agent、后台管理员和模型均无永久删除工具。

## 4. 三个已确认入口

1. Search 结果不合适或为空时，显示“根据当前条件辅助命题”，携带当前检索条件但不把生成题伪装成搜索结果。
2. “新任务”菜单提供独立“辅助命题”入口。
3. 未来 Paper Agent 发现题目不足时，只能询问教师是否进入辅助命题；不得为凑题量自动生成或自动加入试卷。

Teacher Web 顶部能力导航另提供“命题”直达入口，方便教师不依赖某次 Search/Paper 上下文直接进入；它不改变上述三个业务触发条件，也不会自动生成或保存。

生成结果页提供：重新生成解析、编辑题面/答案/解析、记录校订并重检、命名、选择或新建分类、保存为我的私题。重新生成解析创建新的 AI revision，不改变题面与选项，标准答案按新解析更新；保存前后始终显示“仅自己可见”和可信状态。

## 5. 数据与管理规则

- 私题库支持教师自定义题库名称、分类名称、标签和排序，不使用管理员维护的公共分类替代个人分类。
- 每次 AI 修改形成新 revision；教师可以比较并选择保留版本。
- 教师可以保留数学验证未通过或 inconclusive 的私人草稿，但界面不能把它标为已验证，也不能自动用于正式试卷。主动停止后保存的“仅题面、缺少解析”私题是唯一可由教师明确加入组卷的例外；组卷与导出必须把答案和解析显示为“无”。
- 教师删除只影响自己的私题；删除不得触碰参考母题、公共题库或其他 owner 的内容。
- 产品可以提供回收站以避免误删，但必须同时提供 owner 明确确认的永久删除能力；后台没有替用户恢复或阻止删除的内容管理入口。
- 永久删除必须清除活动存储中的题目正文、解析、图片和个人分类关系；商业化前必须公开说明备份到期和最终清除期限，后台不得借备份建立内容查看或恢复工具。
- Analytics、日志和模型运行记录不得保存完整私题、完整命题提示、答案、解析或可反推出内容的 payload。

## 6. 纵向切片顺序

1. **PersonalQuestionLibrary 基线**：独立存储命名空间、current-owner seam、个人题库命名/分类和跨 owner fail-closed。
2. **结构化命题草稿**：自然语言 brief、完整题干/答案、分阶段长解析和命题意图；不把知识点表单作为生成门禁，也不以缩短内容规避模型输出问题。
3. **可信检查**：可解性、答案与解析一致性、选择题唯一性、干扰项、MathVerifier 和预计难度披露。
4. **教师编辑与保存**：局部修改、revision、明确保存到个人分类，不自动写入任何公共业务模块。
5. **个人管理**：列表、搜索、重命名、分类、复制、导出、回收站、恢复和 owner 确认的永久删除。
6. **入口接入**：Search 空/不合适结果、新任务、Paper 明确询问三个必需入口，加顶部“命题”直达入口；生成内容和真实检索内容始终视觉分离。
7. **生成后归纳与教师确认**：Agent 根据最终题目归纳教材节点、细分知识点、考查方法和易错点；业务层校验节点，教师可在 revision 中确认或修正。
8. **完整题型与过程可见性**：选择题题干/选项强制分离，高中范围终检，长请求显示真实阶段与已用时间，并保留有界 15 分钟总预算。
9. **固定评测与 Gate E**：覆盖主要高中模块和题型、模型不可用、验证失败、权利拒绝、重复、越权、公共搜索泄漏、后台权限、删除与恢复。

以上九个切片均已完成。固定评测见 [`M8-PRIVATE-QUESTION-AUTHORING-EVALUATION.md`](M8-PRIVATE-QUESTION-AUTHORING-EVALUATION.md)，完成评审见 [`M8-GATE-REVIEW.md`](M8-GATE-REVIEW.md)。

## 7. M8 完成 Gate

- 教师能够从自然语言要求生成一题结构化草稿，编辑、命名、分类并明确保存到自己的私题库。
- 所有辅助命制题只有 owner 可见；跨 owner、管理员、公共 Search、公共 QuestionBank、共享/商业流程访问均 fail closed。
- 数据模型和接口不存在 publish/share/public/commercial-approved 状态迁移。
- 三个入口均不会把 AI 生成题伪装成真实检索题，也不会自动保存或自动加入试卷。
- 数学验证、预计难度、生成来源和教师复核状态诚实展示；严重错误评测与固定 synthetic set 通过。
- owner 的编辑、分类、回收站、恢复和永久删除可用；Agent 与后台管理员没有删除工具。
- Analytics/日志不记录私题正文或完整命题提示；生产 owner/tenant isolation 与 IDOR 测试在商业化前持续保留。
- FastAPI、Agent、Teacher Web、响应式/可访问性、完整工程回归和 Gate E 全部通过。

M8 Gate E 与 Gate P 已通过；项目所有者确认阶段转换前，不进入 M9 Paper Agent。
