# M7 多模态题目采集与图片解题

更新日期：2026-08-22
状态：进行中；项目所有者于 2026-08-22 在 M6 Gate 后确认进入 M7

## 1. 本阶段唯一目标

让中国高中数学教师在新 Teacher Web 中通过输入文字、粘贴截图或上传单题图片，得到可核对的题面识别结果，并把文字、公式和必要的原图视觉信息一起交给 Solve Agent。M7 解决的是“单题多模态输入到可信解答”的完整工作流，不把 OCR 文本当作图形题的全部信息。

整份 PDF/DOCX 的资料导入、批量 OCR、拆题和私人检索仍属于 M6；自主命题、组卷和教案不属于 M7。

## 2. 永久可信与隐私规则

- 题目图片及其裁剪、OCR 草稿、视觉观察和教师修订全部继承 `private`，只属于当前 owner。
- 浏览器和 Agent 只使用受控资源 ID，不接触本地路径、对象存储地址、数据库或任意 URL。
- 本地处理优先；把图片、题面或视觉信息发送给外部 OCR/视觉模型前，教师必须对本次动作明确同意。
- OCR 只负责转录文字和公式；几何图、函数图、坐标系、统计图和表格必须保留原图或受控裁剪，不能被一段模型描述替代后丢弃。
- 识别结果默认是可编辑草稿。低置信度文字、公式、图形标签和条件必须显式提示，不能静默补全。
- 视觉模型对图形的理解不等于数学验证；无法可靠读取图形条件时必须返回 `teacher_review_required` 或明确失败。
- M7 不新增 private → shared/public/commercial-approved 路径，也不把题目图片用于模型训练。

## 3. 深模块与 seam

`QuestionCapture.prepare(QuestionCaptureCommand) -> QuestionInputBundle` 与 `QuestionCapture.prepare_for_solve(QuestionSolveReference) -> PreparedQuestionInput` 是本阶段的业务深模块接口。前者拥有图片采集、OCR 与校对，后者只接受当前 owner 已确认且 revision 精确匹配的 bundle，并在 FastAPI 内部解析受控图片字节；图片验证、方向与清晰度检查、裁剪、OCR、公式识别、图形存在性判断、revision、owner 隔离、逐次外部处理同意和错误语义留在实现内部。

`QuestionInputBundle` 至少包含：

- 教师确认或待确认的 `stem_plain` 与 `stem_latex`；
- 结构化选项和题型候选；
- 原图及题目级裁剪的受控 asset 引用；
- `requires_visual_reasoning`、低置信度区域与识别警告；
- OCR/视觉 provider、model、revision 和 consent 证据；
- owner-scoped、不可公开的资源状态。

```text
Teacher Web
  → public FastAPI question-capture routes
  → QuestionCapture
  → owned private media storage + OCR/Vision adapters

Teacher Web
  → Solve workflow
  → controlled solve Tool
  → SolutionAssistant(question bundle)
  → MathVerifier
```

外部 OCR/视觉能力是 true external dependency，只能通过注入的 adapter 使用；测试使用 deterministic adapter。Solve Agent 不直接调用视觉供应商，也不直接读取图片。

## 4. 产品交互

Solve 输入区增加：上传图片、粘贴截图、拍照入口、图片预览、旋转、裁剪和移除。识别完成后展示“原图 / 识别题面”对照，低置信度位置可编辑，并明确标记“图形参与推理”。

教师确认题面后再进入解题；对于图形题，受控原图仍随 `QuestionInputBundle` 参与推理。识别失败、图片模糊、裁剪不完整、包含多道题或视觉服务不可用时，界面提供重试、重新裁剪、人工录入或取消，不把失败伪装成文字题成功。

## 5. 纵向切片顺序

1. **私有单题媒体入口**：上传、粘贴、格式/体积/清晰度检查、旋转裁剪、owner-scoped asset；已完成。
2. **文字与公式识别**：复用 M6 OCR 能力，输出可编辑题面、LaTeX、选项、revision 和低置信度提示；已完成。
2A. **数学结果可读展示前置修复**：统一行内/独立公式约定和 KaTeX 渲染，兼容旧式未分隔 LaTeX，失败保留可见原文；已完成。该修复只处理显示，不增加课程层级判断或改变数学结论。
3. **图形保真输入**：保留原图/裁剪，检测需要视觉推理的题型，让 Solve 同时消费文字与受控视觉信息；已完成。
4. **可信解题接入**：复用 M5 `SolutionAssistant`、MathVerifier 和可信状态，不复制第二套解题实现；进行中，基础 seam 已接入，尚待完整失败/取消/真实场景收口。
5. **固定评测与 Gate E**：覆盖代数公式、函数图像、解析几何、立体几何、统计图表、模糊/截断/多题图片、OCR/视觉服务失败、取消和跨 owner 越权；未开始。

第一条切片实现证据：`QuestionCapture.prepare` 对实际 PNG/JPEG/WebP 内容进行探测，限制 15 MB 与 2500 万像素，拒绝损坏、过小和近乎空白图片，并对低分辨率/低对比度返回可见警告。原图、旋转和裁剪使用同一 owner-scoped `asset_id` 与递增 revision；原始 revision 不覆盖。公开路由从服务端 current-teacher seam 绑定 owner，返回值只有受控相对内容端点，不含 owner、存储名或文件路径。新 Solve composer 提供上传、剪贴板与系统相机入口、预览、旋转、裁剪和本次任务移除。

第二条切片实现证据：`QuestionCapture.recognize/review_recognition` 将本地与外部识别隐藏在同一 adapter seam 后，结构化保存普通题面、LaTeX、选项、低置信度区域、provider/model、处理模式、外部同意证据和教师校对备注。识别记录使用独立 append-only revision，并绑定当时的 media revision；图片继续旋转或裁剪后旧识别自动变成 `stale`，不能确认。外部 OCR 只有在当前动作明确同意时才调用；已接入 DeepSeek 官方实验视觉模型 `deepseek-v4-flash-vision-exp`，未配置 DeepSeek 时仍可使用 OpenAI 图像 adapter，本地可选依赖未安装则显式失败。教师端可选择识别方式、查看低置信度提示、编辑题面/LaTeX/选项并保存草稿或确认，且明确不会在本切片自动送入 Solve。

第三条切片实现证据：教师确认题面后，Web 使用 canonical 题面并锁定 media/OCR revision；依赖或可能依赖图形时必须另行勾选“仅本次视觉解题”，该同意在发起动作后自动清空，不能复用 OCR 同意。`SolveAgentWorkflow` 为当前教师、canonical 题面、解题模式/要求、精确 asset/media/OCR revision 与视觉同意签发短时一次性 capability；Agent 只原样转发该 capability，不获得 owner/resource selector、路径、内容端点或图片字节。内部 Tool 在读取图片前消费 capability 并恢复完整 server-owned Solve 意图，模型即使改写普通 Tool 参数也不能替换题面、资源或授权。`QuestionCapture.prepare_for_solve` 再次校验 owner、confirmed、current/stale 状态；只有视觉依赖题才读取受控原图。DeepSeek/OpenAI solution adapter 接收多模态输入，结果返回实际使用的 provider/model/revision 证据，并固定保持 `teacher_review_required`；视觉理解明确不是 MathVerifier 证据。真实浏览器链路已用 DeepSeek `deepseek-v4-flash-vision-exp` 验收原图参与、REV/OCR REV 证据、逐次授权清空、无横向溢出和零控制台告警。

2026-08-22 能力更正：DeepSeek 官方文档新增 `deepseek-v4-flash-vision-exp` 图片输入能力；仓库先前“DeepSeek 仅支持文本”的判断已废止。项目使用 OpenAI-compatible Chat Completions 图片块、JSON 输出和 `detail=original`，真实 synthetic 数学题验证已准确返回题面、LaTeX、四个选项与视觉依赖标记。该模型仍按 true external adapter 治理，实验状态不会降低逐次同意、教师校对或 private 约束。

## 6. M7 完成 Gate

- 文字题、公式题和带图题都能从单题图片进入可核对的 Solve 工作流。
- 原图、裁剪、识别草稿、教师修订和最终解答之间可追踪，且始终 owner-scoped/private。
- 图形题不会只凭 OCR 文本丢失视觉条件；无法可靠理解时诚实降级或失败。
- 外部处理逐次同意，取消、超时、失败和模型不可用有明确体验且不继续隐形计费。
- Agent 不获得文件、路径、数据库、对象存储凭据或任意 URL 能力。
- MathVerifier 证据范围与视觉理解范围清楚分开，模型判断不能升级为 `program_verified`。
- 题面、解题步骤与最终答案中的数学表达均以人类可读公式显示；公式失败可见降级，且不造成页面级横向溢出。
- 固定 synthetic evaluation、跨 owner 安全测试、主要响应式/可访问性、完整工程回归和 Gate E 全部通过。

M7 Gate E 通过并由项目所有者确认前，不进入 M8 私有辅助命题 Agent。
