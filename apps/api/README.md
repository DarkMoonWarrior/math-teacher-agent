# FastAPI Business Backend

`apps/api` 是业务规则和数据访问的唯一所有者。QuestionBank、MathVerifier、Curriculum、PrivateLibrary、PDF、Paper、Lesson、Search Agent、Solve Agent 等模块都在这里执行权限、权利、验证与发布门禁。

## 运行

从仓库根目录：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir .\apps\api --reload
```

- 健康检查：<http://127.0.0.1:8000/health>
- API 文档：<http://127.0.0.1:8000/docs>

## 重要 seam

- `app/modules/*`：深业务模块，拥有规则与存储 adapter。
- `app/routes/*`：公开教师接口与内部 Agent Tool 网关。
- `app/agent_runtime/*`：产品自有 TeacherAgentRuntime 接口与 adapter。
- `/internal/agent-tools/v1/*`：M2M token 保护、模型可见 Tool 的唯一入口，不进入公开 OpenAPI。

Agent 不得直接访问本目录的数据库实现；它只能经过内部 Tool gateway 调用业务模块。

## Private Library（M6 进行中）

Public 路由通过 `app/core/identity.py` 的 current-teacher seam 在服务端绑定 owner 和 reviewer；浏览器不能提交或选择身份。列表、详情、原文件、OCR、revision、后台任务和拆题候选均按 owner fail closed。当前 adapter 仅用于本地开发并固定返回 `owner_teacher`，不代表生产认证已经完成。

本地数学 OCR 当前只支持 PDF；外部 OCR 每次调用都必须重新提交明确同意。两类 OCR 只生成待教师校对草稿，不会改变 private 状态或自动进入题库。

## Search Agent

默认 feature gate 关闭。新工作台本地使用时，需启动 `apps/agent` 并在 `.env` 设置：

```dotenv
MATH_AI_SEARCH_AGENT_ENABLED=true
MATH_AI_AGENT_RUNTIME=dsh
MATH_AI_AGENT_PROVIDER=test-mock
```

Search Agent 的结构化结果是事实来源。模型说明不得补充结果中不存在的题目、学校、年份、考试或验证状态。

## Solve Agent（M5 开发中）

Solve workflow 已提供同步、真实 SSE、run 快照、取消和同会话恢复接口：

- `POST /api/v1/agent/solve`
- `POST /api/v1/agent/solve/stream`
- `GET /api/v1/agent/solve/{run_id}`
- `GET /api/v1/agent/solve/{run_id}/stream`
- `POST /api/v1/agent/solve/{run_id}/cancel`
- `POST /api/v1/agent/solve/{run_id}/resume`

默认保持 `MATH_AI_SOLVE_AGENT_ENABLED=false`。最终数学结果只接受唯一一次成功的 `solve_question` Tool 结构化输出；模型自由文本和原始 Tool payload 不会越过业务 seam。该后端接口完成不代表 M5 已完成，新 Teacher Web 解题流程和完整 Gate 仍待实施。

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest .\apps\api\tests
```

测试只读取 `data/test-fixtures` 中的 synthetic 数据，不调用真实模型。
