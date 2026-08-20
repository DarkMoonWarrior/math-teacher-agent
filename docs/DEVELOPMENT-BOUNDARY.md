# 当前开发边界

更新日期：2026-08-20
状态：当前 source of truth，取代旧路线图中的当前阶段判断。

## 1. 产品定位

产品是面向中国高中数学教师的可信 AI Agent 工作台。教师通过自然语言、题目图片、PDF 或私人教学资料描述需求，系统逐步协助完成搜题、解题、资料整理、组卷与教案等备课工作流。

它不是传统搜题站、通用聊天机器人或把大模型包装成答案生成器。长期竞争力来自结构化题库、MathVerifier、RightsGate、PrivateLibrary、教材知识图谱、题目关系、教师偏好与完整教师工作流。

## 2. 当前唯一目标用户

当前只服务中国高中数学教师。不开发学生端、家长端、小学、初中、其他学科、在线课堂、社区、学校 ERP、成绩管理或全功能 LMS。

## 3. 当前里程碑

当前里程碑是 **M4：新教师工作台与可信 Search Agent 稳定化**。

本里程碑允许：

- 完善 `apps/teacher-web` 的新视觉、导航、响应式与无障碍体验；
- 打通新工作台到 Search Agent 的同源请求、错误状态、取消、空结果和可信状态；
- 修复 SearchIntent 的明确解析缺陷并扩充 synthetic 评测；
- 补齐运行、测试、文档和仓库入口；
- 保持 `TeacherWorkspace`、`TeacherAgentRuntime` 和 FastAPI 业务模块的 seam 清晰；
- 为下一阶段 Solve Agent 记录接口需求，但不提前实现整套后续 Agent。

本里程碑不允许：

- 把旧 `apps/web` 的界面直接搬进新工作台；
- 把已有 REST 页面或本地模板能力宣称为已完成的 Lesson/Paper Agent；
- 同时铺开 Solve、Private Library、Paper、Lesson 和 Memory；
- 新增 Agent 写数据库、自动发布、自动批准、批量删除或 private → public 路径；
- 提前开发账号、付费、多租户、学校后台或学生功能；
- 为增加题量导入来源不明或商业题库内容。

## 4. 可信与发布规则

所有展示或导出的内容必须区分：

- 已有题库且来源/状态可追踪；
- 程序独立验证通过；
- 教师审核通过；
- AI 生成或计算但仍需教师复核。

模型不得修改验证结论。无真实结果时返回空结果和可解释建议，不生成假题补足数量。AI 产物首先是 draft；题目进入公共商业题库必须经过 RightsGate、MathVerifier 与 Teacher Review。

## 5. 内容、权利与私人资料

- 每道商业内容需追踪 source、原始文件、权利状态、是否允许商用/修改/公开、教师审核与数学验证。
- 来源不明内容进入 quarantine/review，不进入 `commercial-approved`。
- 教师上传与其 OCR、拆题、映射、修改、验证后的派生内容仍默认 private。
- private → shared/public 只能由明确授权动作触发；Agent 没有该权限。
- 测试只使用 `data/test-fixtures` 的 synthetic 项目自建内容。

## 6. Agent 权限边界

唯一允许链路：

```text
Teacher UI
  → FastAPI public route
  → TeacherAgentRuntime / business module
  → allowlisted Tool
  → FastAPI business module
  → Rights / Permission / Validation
  → storage
```

禁止 `Agent → SQL/SQLite/PostgreSQL/ORM/filesystem`。DeepSeek Harness 只能位于 `apps/agent`，通过 adapter、plugin、tool、preset 扩展，不修改 Harness core。业务代码只依赖产品自有接口。

## 7. 需要所有者确认的变更

以下事项在编码前必须停下说明影响：教师工作流、业务规则、数据含义、版权处置、private/public 状态、永久删除或破坏性迁移、权限模型、发布门禁、商业规则、目标用户或路线图顺序。

明确的 bug、测试、重构、类型、性能、兼容性、文档和不改变行为的工程实现可自主完成。

## 8. 当前完成标准

M4 完成需同时满足：

1. 新工作台是默认 Web 入口，旧 UI 只作为 legacy/reference；
2. Search Agent 可从新工作台经同源代理访问 FastAPI；
3. 关闭、不可达、空结果、取消和可信标签均有明确 UI；
4. 320–1920px 无横向溢出，关键操作可键盘访问；
5. Primary UI、Agent Runtime、FastAPI 测试与构建通过；
6. Lesson/Paper 仍诚实显示为待接入，不越级宣称完成。
