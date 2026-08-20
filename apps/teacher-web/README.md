# Teacher Web（主产品 UI）

`apps/teacher-web` 是当前默认的教师产品入口。它采用新的 Agent-first 信息架构和视觉系统，不继承 `apps/web` 的页面壳。

## 当前能力

- 搜题、教案、组卷三项 Agent 能力导航；
- Search Agent 真实请求、加载/取消/错误/空结果/可信状态；
- 教案与组卷需求草稿及工作流预览（运行时尚未接入，提交按钮禁用）；
- 桌面与手机响应式动态纸张画布。

## 运行

从仓库根目录：

```powershell
pnpm dev:teacher
```

访问 <http://127.0.0.1:3001>。Next.js 将同源 `/api/v1/*` 转发到 `MATH_AI_API_INTERNAL_URL`，默认是 `http://127.0.0.1:8000`。

要使用 Search Agent，需要同时启动 FastAPI 与 `apps/agent`，并设置：

```dotenv
MATH_AI_SEARCH_AGENT_ENABLED=true
MATH_AI_AGENT_RUNTIME=dsh
MATH_AI_AGENT_PROVIDER=test-mock
```

除非部署架构明确要求浏览器直连另一域名，否则不要设置 `NEXT_PUBLIC_MATH_AI_API_URL`；本地开发优先使用同源 rewrite。

## 模块 seam

- `lib/teacher-workspace/contracts.ts`：UI 可见的稳定接口和结果模型。
- `lib/teacher-workspace/http-adapter.ts`：同源 FastAPI adapter。
- `components/workbench/teacher-workbench.tsx`：视图与交互状态。

React 代码不得依赖数据库、Harness 类型、供应商响应或后端内部存储字段。

## 检查

```powershell
pnpm typecheck:teacher
pnpm build:teacher
```
