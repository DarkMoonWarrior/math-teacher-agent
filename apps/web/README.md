# Legacy Web（旧 UI / 业务流程参考）

`apps/web` 是从 `high-school-math-ai` 迁移的旧教师工作台。它保留了搜题、解题、PDF、私人资料、组卷、教案与管理流程，作为成熟业务行为和回归参考。

它不是当前主产品入口，也不是新 UI 的视觉模板。新的 Agent-first 体验写在 `apps/teacher-web`；不要把本应用的侧边栏、页面壳或旧信息架构复制到新工作台。

仅在以下情况修改本应用：

- 项目所有者明确要求修复旧流程；
- 需要保持后端兼容性并有回归测试；
- 需要从旧实现提取业务规则到稳定的 FastAPI/TeacherWorkspace seam。

## 运行

```powershell
pnpm dev:legacy-web
```

访问 <http://127.0.0.1:3000>。

## 检查

```powershell
pnpm typecheck:legacy-web
pnpm build:legacy-web
```
