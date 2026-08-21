# Teacher Tool 当前契约

更新日期：2026-08-21

本文档是当前 model-visible Tool allowlist 的 source of truth。历史第一版五工具契约保留在 `docs/commercial-v1/TEACHER-TOOL-CONTRACTS-v1.md`，不代表 M5 当前状态。

## 精确 Allowlist

1. `search_questions`
2. `get_question`
3. `solve_question`
4. `find_similar_questions`
5. `verify_question`
6. `get_curriculum_node`

自动测试要求可见工具恰好等于该集合。bash、filesystem、web、subagent、workflow、terminal、数据库和任意 URL 能力均禁止。

## `solve_question`

- 路由：`POST /internal/agent-tools/v1/solve-question`
- 认证：`Authorization: Bearer <MATH_AI_TOOL_GATEWAY_TOKEN>`
- 请求：`question_text`、`solution_mode=standard|alternative`、可选 `teacher_instruction`
- 业务接口：`SolutionAssistant.solve(SolutionRequest) -> SolutionResult`
- 成功响应：结构化解法、最终答案、知识点、易错点、教学提示、`confidence_status`、`verification_evidence`、provider/model、mode、匹配题目与 warnings
- 已验证题库解析：`mode=verified_bank`、`confidence_status=program_verified`
- 模型新解答：`mode=live_ai`、`confidence_status=teacher_review_required`
- 无已验证解析且模型不可用：HTTP 503 + `MODEL_UNAVAILABLE`
- 超时：HTTP 504 + `TOOL_TIMEOUT`

Tool 不保存、不发布、不批准答案或解析，不改变题库、权利、验证或 private/public 状态。Agent 必须原样保留可信等级与验证证据。

其他五个工具的请求/响应继续沿用历史 v1 契约；FastAPI Pydantic 模型与 Agent TypeScript 类型是可执行契约，文档不覆盖实现门禁。
