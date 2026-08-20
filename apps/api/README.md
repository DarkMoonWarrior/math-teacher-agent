# FastAPI Business Backend

`apps/api` 是业务规则和数据访问的唯一所有者。QuestionBank、MathVerifier、Curriculum、PrivateLibrary、PDF、Paper、Lesson、Search Agent 等模块都在这里执行权限、权利、验证与发布门禁。

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

## Search Agent

默认 feature gate 关闭。新工作台本地使用时，需启动 `apps/agent` 并在 `.env` 设置：

```dotenv
MATH_AI_SEARCH_AGENT_ENABLED=true
MATH_AI_AGENT_RUNTIME=dsh
MATH_AI_AGENT_PROVIDER=test-mock
```

Search Agent 的结构化结果是事实来源。模型说明不得补充结果中不存在的题目、学校、年份、考试或验证状态。

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest .\apps\api\tests
```

测试只读取 `data/test-fixtures` 中的 synthetic 数据，不调用真实模型。
