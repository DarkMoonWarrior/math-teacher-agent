# Teacher Web（主产品 UI）

`apps/teacher-web` 是当前默认的教师产品入口。它采用新的 Agent-first 信息架构和视觉系统，不继承 `apps/web` 的页面壳。

## 当前能力

- 搜题、解题、资料库、教案、组卷五项 Agent 能力导航；
- Search Agent 单次真实流式请求、服务端取消、错误/空结果/可信状态；
- Solve Agent 单次真实流式请求、同一 run 恢复、服务端取消与结构化错误；
- 完整题目输入、Search 结果一键转入解题、三页纸张式解析／课堂提示／MathVerifier 证据；
- 单题图片上传、粘贴、拍照、旋转与裁剪；本地或逐次授权的 DeepSeek Vision/外部 OCR 生成可编辑题面、LaTeX、选项、识别 revision，以及可核对的图形元素/连线/虚实线观察草稿；
- 教师确认题面后锁定精确媒体/OCR revision；带图题另行逐次同意本次视觉解题，提交后自动清空，并在可信证据页展示原图是否实际参与及 provider/model；
- 私人资料同源上传与清单：PDF/DOCX/图片、来源与权利说明、明确确认、private 与处理状态；
- 私人资料详情与校对：原 PDF/图片预览、首次提取文本、可编辑草稿、本地 PDF OCR、逐次授权外部 OCR 和修订记录；
- 私人资料拆题：仅使用教师确认的当前文本，逐题编辑题干/选项/答案/解析/难度，搜索并确认可信教材知识点后才允许存入私人题库；
- 教案与组卷需求草稿及工作流预览（运行时尚未接入，提交按钮禁用）；
- 桌面与手机响应式动态纸张画布。

## 运行

从仓库根目录：

```powershell
pnpm dev:teacher
```

访问 <http://127.0.0.1:3001>。Next.js 将同源 `/api/v1/*` 转发到 `MATH_AI_API_INTERNAL_URL`，默认是 `http://127.0.0.1:8000`。

要使用 Search 与 Solve Agent，需要同时启动 FastAPI 与 `apps/agent`，并设置：

```dotenv
MATH_AI_SEARCH_AGENT_ENABLED=true
MATH_AI_SOLVE_AGENT_ENABLED=true
MATH_AI_AGENT_RUNTIME=dsh
MATH_AI_AGENT_PROVIDER=test-mock
```

除非部署架构明确要求浏览器直连另一域名，否则不要设置 `NEXT_PUBLIC_MATH_AI_API_URL`；本地开发优先使用同源 rewrite。

## 模块 seam

- `lib/teacher-workspace/contracts.ts`：UI 可见的稳定接口和结果模型。
- `lib/teacher-workspace/http-adapter.ts`：Search/Solve/Private Library/Question Capture 同源 FastAPI adapter；内部处理 SSE、同一 run 恢复、服务端取消、owner-free multipart 上传、受控图片变换与 OCR 后台任务轮询，不向 React 泄漏传输或存储细节。
- `components/workbench/teacher-workbench.tsx`：视图与交互状态。
- `components/workbench/private-library-workspace.tsx`：私人资料上传、权利声明、owner-scoped 清单、原文件对照、OCR 校对、revision、拆题编辑和教材映射界面。

React 代码不得依赖数据库、Harness 类型、供应商响应或后端内部存储字段。

## 检查

```powershell
pnpm typecheck:teacher
pnpm test:teacher
pnpm build:teacher
```
