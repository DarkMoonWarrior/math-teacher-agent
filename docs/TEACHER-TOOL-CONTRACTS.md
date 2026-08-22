# Teacher Tool 当前契约

更新日期：2026-08-22

本文档是当前 model-visible Tool allowlist 的 source of truth。历史第一版五工具契约保留在 `docs/commercial-v1/TEACHER-TOOL-CONTRACTS-v1.md`，不代表 M5 当前状态。

## 精确 Allowlist

1. `search_questions`
2. `get_question`
3. `solve_question`
4. `find_similar_questions`
5. `verify_question`
6. `get_curriculum_node`
7. `inspect_private_library`
8. `search_private_library`

自动测试要求可见工具恰好等于该集合。bash、filesystem、web、subagent、workflow、terminal、数据库、私人文件和任意 URL 能力均禁止。

## `inspect_private_library`

- 路由：`POST /internal/agent-tools/v1/inspect-private-library`
- 认证：`Authorization: Bearer <MATH_AI_TOOL_GATEWAY_TOKEN>`
- 请求：空对象；`owner_id` 和其他额外字段一律拒绝
- 业务接口：`PrivateLibrary.stats(owner_id=current_owner)`
- 成功响应：资料总数、待校对数、已确认数、待 OCR 数、回收站数、文件类型计数、`visibility=private`、`content_included=false`
- 禁止返回：owner 标识、标题、文件名、正文、路径、哈希、权利声明或原始文件
- 当前本地 current owner 固定为 `owner_teacher`；M6 完成前必须替换为可验证的 current-owner seam，模型始终不能选择 owner

该 Tool 只读且不代表模型已读取资料内容，不执行上传、OCR、校对、拆题、导入、删除、共享或发布。

## `search_private_library`

- 路由：`POST /internal/agent-tools/v1/search-private-library`
- 认证：M2M token；另必须携带 FastAPI 为当前教师本次操作签发的 opaque `consent_token`
- 请求：`query`、`limit<=8`、`consent_token`；`owner_id` 和额外字段一律拒绝
- 许可：短时、单次消费，并严格绑定 server-owned current owner、规范化 query 与 limit；过期、重放、改写或 owner 不匹配均返回 `PRIVATE_CONSENT_REQUIRED`
- 业务接口：`PrivateLibrary.search_confirmed_text(query, owner_id=current_owner)`
- 成功响应：active + confirmed 资料的标题、最多 480 字匹配片段、文本版本、权利依据、`visibility=private` 与 `content_scope=matching_excerpts`
- 禁止返回：owner、原文件名、存储名/路径、哈希、权利声明、未确认正文或整份正文

该 Tool 只读，不改变资料、候选、题库、验证或发布状态。浏览器每次调用后清空授权确认，许可不能作为会话级或长期授权复用。

## `solve_question`

- 路由：`POST /internal/agent-tools/v1/solve-question`
- 认证：`Authorization: Bearer <MATH_AI_TOOL_GATEWAY_TOKEN>`
- 请求：`question_text`、`solution_mode=standard|alternative`、可选 `teacher_instruction`
- 业务接口：`SolutionAssistant.solve(SolutionRequest) -> SolutionResult`
- 成功响应：结构化解法、最终答案、知识点、易错点、教学提示、`confidence_status`、`math_verification`、`verification_evidence`、provider/model、mode、匹配题目 ID、题库修订计数与 warnings
- `math_verification`：包含 `status=passed|failed|inconclusive`、`capability=supported|unsupported`、验证 `scope`、证据来源、方法、独立答案、来源答案、明细与 verifier 版本
- 已验证题库解析：`mode=verified_bank`、`confidence_status=program_verified`
- 模型新解答：`mode=live_ai`、`confidence_status=teacher_review_required`
- 任意模型新解答未被现有 MathVerifier 覆盖时：`math_verification=unsupported/inconclusive`，scope 为 `generated_solution`
- 精确匹配到来源矛盾题：不得继承可信解析；无模型时 HTTP 409 + `VERIFICATION_FAILED`，有模型时仍保持 `teacher_review_required` 并保留冲突证据及 `matched_question_record` scope
- 精确匹配到证据不足题：不得继承可信解析；无模型时 HTTP 409 + `VERIFICATION_INCONCLUSIVE`
- 无已验证解析且模型不可用：HTTP 503 + `MODEL_UNAVAILABLE`
- 超时：HTTP 504 + `TOOL_TIMEOUT`

Tool 不保存、不发布、不批准答案或解析，不改变题库、权利、验证或 private/public 状态。Agent 必须原样保留可信等级与验证证据。

其他五个历史只读工具的请求/响应继续沿用历史 v1 契约；FastAPI Pydantic 模型与 Agent TypeScript 类型是可执行契约，文档不覆盖实现门禁。
