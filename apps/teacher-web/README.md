# Teacher Web（主产品 UI）

`apps/teacher-web` 是唯一的教师产品 UI，采用 Agent-first 信息架构和统一的左右工作区布局。旧界面已移除。

## 当前能力

- 搜题、解题、资料库、命题、教案、组卷六项能力导航；命题为 owner-only 私有工作区直达入口；
- Search Agent 单次真实流式请求、服务端取消、错误/空结果/可信状态；
- Solve Agent 单次真实流式请求、同一 run 恢复、服务端取消与结构化错误；
- 完整题目输入、Search 结果一键转入解题、三页纸张式解析／课堂提示／MathVerifier 证据；
- 单题图片上传、粘贴、拍照、旋转与裁剪；本地或逐次授权的 DeepSeek Vision/外部 OCR 生成可编辑题面、LaTeX、选项、识别 revision，以及可核对的图形元素/连线/虚实线观察草稿；
- 教师确认题面后锁定精确媒体/OCR revision；带图题另行逐次同意本次视觉解题，提交后自动清空，并在可信证据页展示原图是否实际参与及 provider/model；
- 私人资料同源上传与清单：PDF/DOCX/图片、可选来源说明、private 与处理状态；不再要求额外权利选项或存入确认勾选；
- 私人资料详情与校对：点击发起大模型识别，原稿与可读整理稿等高、独立滚动并可拖动分隔，下方中文 + LaTeX 编辑同步预览，保留修订记录；
- 私人资料拆题：仅使用教师确认的当前文本，逐题编辑题干/选项/答案/解析/难度，搜索并确认可信教材知识点后才允许存入私人题库；
- 私有辅助命题：可从顶部“命题”、新任务、Search 空/不合适结果或 Paper 缺题提示进入独立命题工作区；填写结构化要求后生成未保存草稿，编辑并重跑六项检查，明确选择或新建个人题库/分类后才保存；我的私题支持 owner 自主管理、私有导出、回收、恢复和固定短语永久删除；临时成功/失败提示与永久删除确认采用弹窗，可信检查和数学风险证据保留在正文；
- 教案与组卷完整工作流已接入：蓝图、受控选题/来源、可读草稿编辑、本人历史及不可变版本 DOCX/PDF 导出；
- 教师偏好与当前用户/退出统一放在右上角设置；M12 会话/能力 gate 已完成并通过固定回归；
- 六模块可拖动/折叠左右栏，切换保留当前任务，明确清空任务；命题题面先展示、解析后台生成，停止时可保留标注缺少解析的私题；
- 桌面与手机响应式动态纸张画布。

## 运行

从仓库根目录：

```powershell
pnpm dev:teacher
```

访问 <http://127.0.0.1:3001>。Next.js 将同源 `/api/v1/*` 转发到 `MATH_AI_API_INTERNAL_URL`，默认是 `http://127.0.0.1:8000`。

要使用 Search、Solve 与私有辅助命题 Agent，需要同时启动 FastAPI 与 `apps/agent`，并设置：

```dotenv
MATH_AI_SEARCH_AGENT_ENABLED=true
MATH_AI_SOLVE_AGENT_ENABLED=true
MATH_AI_QUESTION_AUTHORING_AGENT_ENABLED=true
MATH_AI_AGENT_RUNTIME=dsh
MATH_AI_AGENT_PROVIDER=test-mock
```

除非部署架构明确要求浏览器直连另一域名，否则不要设置 `NEXT_PUBLIC_MATH_AI_API_URL`；本地开发优先使用同源 rewrite。

## 模块 seam

- `lib/teacher-workspace/contracts.ts`：UI 可见的稳定接口和结果模型。
- `lib/teacher-workspace/http-adapter.ts`：Search/Solve/Private Library/Question Capture/Private Question Authoring 同源 FastAPI adapter；内部处理 SSE、同一 run 恢复、服务端取消、owner-free multipart 上传、受控图片变换、OCR 后台任务轮询及 owner-bound 私题版本动作，不向 React 泄漏传输或存储细节。
- `components/workbench/teacher-workbench.tsx`：视图与交互状态。
- `components/workbench/private-library-workspace.tsx`：私人资料上传、权利声明、owner-scoped 清单、原文件对照、OCR 校对、revision、拆题编辑和教材映射界面。
- `components/workbench/personal-question-authoring-workspace.tsx`：结构化 brief、未保存草稿、教师 revision、六项可信状态、明确保存、个人题库/分类和 owner 私题 lifecycle 界面。
- `components/workbench/workbench-notice-dialog.tsx`：工作台临时成功/失败提示和不可逆操作确认的原生 `dialog` 组件。

React 代码不得依赖数据库、Harness 类型、供应商响应或后端内部存储字段。

## 检查

```powershell
pnpm typecheck:teacher
pnpm test:teacher
pnpm build:teacher
```
