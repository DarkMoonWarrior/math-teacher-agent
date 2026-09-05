# M6 Private Library Agent

> 状态同步（2026-09-05）：M0–M12 已完成，M13 等待项目所有者确认。本文的切片过程、测试数量和 Gate 结论保留为当时证据；后续行为与当前边界见 [开发状态](PROJECT-STATUS.md) 和 [开发边界](DEVELOPMENT-BOUNDARY.md)。

更新日期：2026-08-22
状态：已完成；Gate E 于 2026-08-22 通过，进入 M7 的阶段转换已确认。后续实现以 [项目状态](PROJECT-STATUS.md) 为准。

## 1. 本阶段唯一目标

让中国高中数学教师在新的 Teacher Web 中，把 PDF、DOCX 和图片放入自己的 private workspace，完成可追踪的提取、OCR、校对、拆题、教材映射和私人检索。M6 不建立 public/shared 出口，不顺带开发组卷、教案、记忆、账号或商业发布。

## 2. 永久不变的资料边界

- 原文件、提取文字、OCR 草稿、修订、拆题候选和导入题目始终继承 `private`。
- 上传必须保存 owner、原文件摘要、revision、来源声明和权利依据；来源声明不会自动变成商业授权。
- Agent Service 不读取文件系统、数据库或原文件；只能调用 FastAPI 暴露的 allowlisted Tool。
- 私人正文、标题、文件名或路径不得因为“方便模型理解”默认发给外部模型。
- 外部 OCR/模型处理必须由教师对本次动作明确同意；模型产物保持待校对或 `teacher_review_required`。
- OCR、拆题、教材映射、数学验证和教师修改都不会自动改变 private/public 状态。
- 永久删除、private → shared/public、自动发布和批量商业导入不属于 M6。

## 3. 深模块与 seam

`PrivateLibrary` 是业务深模块：文件验证、类型识别、哈希去重、提取、revision、权利状态和 owner 过滤留在实现内部。Teacher Web 和 Agent 只通过小型产品接口使用这些行为。

```text
Teacher Web → public FastAPI private-library routes → PrivateLibrary → owned storage
Agent Runtime → inspect_private_library Tool → internal M2M gateway → PrivateLibrary
```

第一条 Agent 接口 `inspect_private_library` 只返回当前教师的聚合数量、处理状态和文件类型统计。接口没有 `owner_id` 参数，也不返回标题、文件名、正文、路径或 owner 标识。Public UI 同样不允许浏览器选择 owner：`app/core/identity.py` 提供可替换的 current-teacher seam，路由从服务端身份上下文绑定 owner 与 reviewer。列表、统计、上传、详情、原文件、OCR、修订、后台任务和拆题候选均已按 owner fail closed，并以跨 owner 自动测试覆盖；浏览器提交 actor 字段会被拒绝。当前 seam 的 adapter 在本地仍返回固定 `owner_teacher`，它不是生产认证；真实会话认证与多租户身份落在 M12，不得把本地 adapter 当成商业隔离已完成。

## 4. 纵向切片顺序

1. **聚合概览 Tool**：owner-scoped 统计、M2M fail closed、无私人正文；已完成。
2. **新工作台资料入口**：同源上传/列表、权利声明、格式/体积错误和 private 标签；已完成。
3. **提取与 OCR 校对**：本地处理优先；外部处理逐次同意；原页、草稿和 revision 可核对；已完成。
4. **拆题与教材映射**：只从教师确认文本生成可编辑候选，导入后仍为 private + pending review；已完成。
5. **私人检索 Agent**：显式同意后按最小必要内容检索，结果保留来源/revision/权利状态；已完成。许可由 FastAPI 按当前教师、查询和数量签发，短时且单次消费；只检索 active + confirmed 文本并返回不超过 480 字的匹配片段，不暴露原文件、路径、整份正文或 owner selector。
6. **固定评测与 Gate E**：空库、格式失败、OCR 失败、模型不可用、权限拒绝、取消、跨 owner、private 泄漏和恢复路径；已完成。12 个 synthetic 场景的 8 类违规均为 0，完整工程与浏览器门禁通过。

第四条切片的实现证据：候选与资料文本版本绑定，文本未确认或版本过期时 fail closed；题干、题型、选项、答案、解法和难度可由教师编辑。浏览器只提交教材 `node_id`，教材名称、册次、章节和小节由 FastAPI 的受控 Curriculum 目录解析；导入前强制完成映射。导入结果固定为 `private + pending + needs_math_review`，并在来源证据中保存 owner、资料、文本版本与候选标识。浏览器不能提交 owner/editor 或伪造教材路径，跨 owner 候选访问返回 404。

第五条切片的实现证据：浏览器必须对每次查询单独勾选授权，且请求完成后自动清空。FastAPI 根据服务端 current-teacher 身份签发短时、单次、绑定 query/limit 的 opaque 许可；模型不能提交 owner。受控 Tool 仅返回 active + confirmed 资源的标题、≤480 字片段、来源版本与权利依据；未确认、回收站、其他 owner、原文件、路径与整份正文均不可见。许可重放与参数改写会被拒绝。

## 5. M6 完成 Gate

- 新 Teacher Web 中 PDF/DOCX/图片上传、处理、校对、拆题、映射和私人检索形成完整可恢复流程。
- 原文件与每次修订可追踪；重复、失败和回收站状态可解释，不进行永久删除。
- owner 隔离与越权测试覆盖列表、详情、文件、OCR、修订、候选和检索。
- 外部处理逐次同意，取消与失败不会伪装成功，也不会把草稿提升为已确认。
- 所有派生对象保持 private；不存在自动 public/shared/commercial-approved 路径。
- Agent 只使用 allowlisted Tool，且不获得文件、路径、数据库或任意 URL 能力。
- 固定 synthetic evaluation、主要 UI 响应式/可访问性、FastAPI、Agent 和 Gate E 全部通过。

M6 的 OCR/修订能力是后续单题图片采集可复用的地基，但本阶段不接入 Solve，也不提前实现多模态解题。

固定评测见 [`M6-PRIVATE-LIBRARY-EVALUATION.md`](M6-PRIVATE-LIBRARY-EVALUATION.md)，逐项审计见 [`M6-GATE-REVIEW.md`](M6-GATE-REVIEW.md)。M6 已完成，但项目所有者确认阶段转换前仍不进入 M7 多模态题目采集与图片解题。
