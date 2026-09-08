# M10 Lesson Agent 固定范围与切片顺序

> 状态同步（2026-09-09）：M0–M12 已完成；M13 工程切片已完成但真实验证延期、Gate 未通过；项目所有者已授权进入 M14，当前进行中。本文的切片过程、测试数量和 Gate 结论保留为当时证据；后续行为与当前边界见 [开发状态](PROJECT-STATUS.md) 和 [开发边界](DEVELOPMENT-BOUNDARY.md)。

更新日期：2026-08-31
状态：已完成。六条纵向切片、固定评测和完成 Gate 已通过；回滚点为 `9997fc8`，项目所有者于 2026-08-31 确认进入 M11。

## 1. 唯一目标

让中国普通高中数学教师从一段自然语言课堂要求出发，在明确选择教材、真实题目和本人私人资料后，得到一份来源可追踪、可逐块编辑、可显式保存和按精确版本导出的完整教案。

“草稿”只表示未由教师保存，不表示残缺或把核心补全责任交给教师。M10 正常完成态必须包含教学目标、重难点、课堂活动、例题/练习、评价、作业、板书与教师备注；目标、活动和评价必须能相互对应。

## 2. 深模块与 Interface

M10 使用以下产品 Interface 隔离实现细节：

1. `LessonBlueprintPlanning.plan(brief) -> LessonBlueprintDraft`：把课堂要求整理为无副作用蓝图。
2. `LessonSourceSelection.select(blueprint, public_question_ids, private_question_ids, private_resource_ids) -> LessonSourceDraft`：只读取教师明确选择且通过门禁的来源。
3. `LessonDrafting.build(source_draft) -> LessonEditableDraft`：生成完整、可追踪的教案正文。
4. `LessonBlockEditing.rewrite(draft, block, instruction) -> LessonEditableDraft`：只修改明确目标块并保留其他块及来源关系。
5. `LessonVersioning.save(draft, fingerprint) -> LessonSavedVersion`：显式保存当前 owner 的不可变版本。
6. `LessonSavedExporting.export(lesson_plan_id, version, format) -> artifact`：只导出指定已保存版本。

旧 `LessonPlanStudio` 会立即写入 SQLite，且旧请求可携带浏览器 `teacher_id`。它是历史业务知识，不是新的产品 Interface；在身份、来源选择、编辑、版本和 Gate 完成前不得原样暴露为 M10 工作流。

## 3. 固定切片顺序

### 切片 1：教案蓝图规划（已接入）

- 教师只提交 `brief`；owner、可信状态和保存命令不来自浏览器。
- 业务层拒绝大学范围，解析年级、课型、时间、学情、侧重与计划题量。
- 只从封存的人教 A 版课程基线产生教材候选，并如实显示基线状态、reviewer 与匹配度。
- 返回教学目标、重难点、课堂阶段与可见默认假设。
- 响应固定为 `editable + unconfirmed + unsaved`，`side_effects=[]`。
- Teacher Web 使用左右可拖动布局；右侧所有蓝图字段可本地编辑。
- 不查题、不读取私人资料、不生成教案正文、不保存。

### 切片 2：教师明确选择受控来源

- 教师先确认蓝图，再明确选择教材节点、公共题、当前 owner 私题与当前 owner 私人资料。
- 公共题固定经过公开、在架、权利、教师审核、数学验证和高中范围门禁。
- 私题和私人资料只可读取当前 owner 明确勾选的 ID；浏览器不能提交 owner、路径或可信结论。
- 未选择的私人内容不可被 Agent 自动检索；一次性私人检索许可仍不得扩大为全库访问。
- 来源不足返回真实缺口，不临时编题、不自动保存、不改变可见性。

实现状态：已接入。新增 `LessonSourceSelection.options(...)` 与
`LessonSourceSelection.select(...)`、`/blueprints/source-options` 和
`/blueprints/select-sources`。Teacher Web 只有在教师确认可编辑蓝图后才展示
受控公共题、当前 owner 私题和当前 owner 已确认文本的私人资料；候选必须明确
勾选，提交后服务端重新解析精确 ID/revision、权利和可信状态。未勾选的私人资料
内容不进入来源草案；题量不足返回真实缺口，固定 `unsaved + side_effects=[]`。

### 切片 3：完整教案草稿生成

- 基于已确认蓝图和受控来源生成完整教学目标、重难点、教学流程、例题/练习、评价、作业、板书和教师备注。
- 每个来源型内容保留题目/资料/教材的精确 ID、revision、rights、verification 和 owner scope。
- AI 组织文本明确标记 `draft_requires_teacher_review`，不得冒充教材原文、教师审定或 MathVerifier 结论。
- 服务端检查时间总和、必需内容块、目标—活动—评价对应、题目完整性和高中范围；正常完成不交付半份教案。

实现状态：已接入。新增 `LessonDrafting.build(...)` 与
`POST /blueprints/build-draft`。服务端不信任浏览器回传的来源可信事实，而会以
当前 owner 再次执行来源选择并核对题目/资料精确 revision、权利、审核、验证与
owner scope；来源漂移、解析缺失、选择题选项缺失或大学范围均不会形成正文。
成功结果一次性交付目标与证据、重难点、完整课堂流程、题面/选项/完整解析与答案、
评价、作业、板书、教师备注和精确来源清单，并执行时间与目标—活动—评价闭环检查。
Teacher Web 在同一可编辑桌面展示完整结果，明确标记“待教师复核 · 未保存”；本切片
仍不建立版本、不保存、不导出。

### 切片 4：逐块编辑与锁定

- 教师可以编辑或锁定任意内容块；定向重写只能改变目标块。
- 重写后重新执行结构、时间、来源与高中范围检查。
- 页面本地修改和服务端 revision 必须可区分；未应用编辑不得静默丢失。

实现状态：已接入。新增 `LessonBlockEditing.rewrite(...)` 与
`POST /blueprints/rewrite-block`。该深模块只有一个面向调用者的改写 Interface，
内部统一完成当前 owner 来源重验、精确题目事实保护、锁定检查、目标块替换、草稿
revision 递增以及结构、时间、目标对应和高中范围复检。Teacher Web 对九类内容块
提供本地编辑、锁定/解锁和定向重写，并明确区分服务器 revision 与尚未应用的本地修改。
定向重写保证非目标块原样保留；题目块只调整课堂用途，题干、选项、答案和解析不允许
借改写发生漂移。结果仍是待教师复核、未保存且无副作用的草稿。

### 切片 5：显式版本保存、历史与生命周期

- 保存前重新解析精确来源 revision、可信事实和草稿 fingerprint。
- 只有当前 owner 可保存、列出、读取、编辑为新版本、移入回收站和恢复。
- 历史版本不可变；编辑历史教案建立新版本，不覆盖旧版本。
- Agent 无保存、删除、发布或共享能力。

实现状态：已接入。`LessonVersioning` 是唯一持久化 Interface；保存前重建来源草案并核对题目事实与结构，只接受 current-teacher owner 和教师显式确认。本人历史、历史编辑另存新版本、回收与恢复均已接入，旧版本不可变保留。

### 切片 6：精确版本导出与完成 Gate

- DOCX/PDF 只读取当前 owner 指定的已保存版本，不读取页面临时状态，不漂移到来源最新 revision。
- 教师版必须包含来源/可信摘要；面向课堂的版本按产品定义控制内部元数据展示。
- 固定 synthetic evaluation 覆盖范围、来源、owner/IDOR、隐私、题目完整性、目标对应、逐块编辑、版本与导出。
- 完整工程回归、响应式/可访问性、DOCX/PDF 视觉检查、Gate E 和 Gate P 全部通过后，才可请求进入 M11。

实现状态：已接入。`LessonSavedExporting` 只读取当前 owner 的指定 `lesson_plan_id + version`，并经 `SavedLessonPlanDocumentRenderer` 输出教师教案 DOCX/PDF。Teacher Web 只在存在已保存版本时提供下载；页面修改不会被导出为旧版本。28 场景固定评测、完整工程回归、Gate E/Gate P 连续性和真实文档逐页检查已通过。

## 4. 永久边界

- 只支持中国普通高中数学，不扩展大学、小学、初中、其他学科或学生端。
- Agent 永不直连数据库或私人文件；唯一链路仍是 Agent → Tool → FastAPI business module → gates → storage。
- 私人资料、私题和派生教案 private-by-default；M10 不新增 public/shared/team/school 发布路径。
- 来源不明、权利不明、未审核或未验证内容不能被描述成可信公共来源。
- 排版成功、模型自评和教师保存都不能升级数学验证状态。
- 未完成切片不得以旧 REST 接口、导航入口或模型能生成文本为理由宣称 M10 完成。

## 5. 当前验收事实

六条切片均已建立。`LessonSavedExporting` 和 `SavedLessonPlanDocumentRenderer` 已把当前 owner 的指定不可变版本导出为完整教师教案 DOCX/PDF；浏览器请求不含 owner，导出不读取页面临时状态，也不会漂移到来源或教案的后续版本。固定评测 28 个 synthetic 场景、15 类违规为 0；FastAPI、Teacher Web、Agent 及两套 Web 生产构建均通过，DOCX/PDF 已逐页检查。变更已进入回滚点 `9997fc8`，所有者已确认阶段转换。
