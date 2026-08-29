# 备课伙伴 · 高中数学教师可信 AI Agent

面向中国高中数学教师的 Agent-first 备课工作台。教师用自然语言、题目图片或私人资料描述教学任务，系统通过受控业务能力协助搜题，并逐步扩展到多模态解题、私有辅助命题、私人资料、组卷和教案；来源、权利、数学验证与教师复核状态始终可追踪。

这个仓库不是从零重写旧项目，也不会继续沿用旧界面。`high-school-math-ai` 的成熟业务模块与测试是地基；新的产品入口、交互和 Agent 工作流位于 `apps/teacher-web`。

## 当前能做什么

- 新教师工作台与搜题／解题／资料库／教案／组卷能力导航；
- 可信 Search Agent：自然语言意图、教材映射、真实题库检索、去重与多样性；
- 题目来源、权利状态、验证状态和条件放宽披露；
- 产品自有 `TeacherAgentRuntime` 与隔离的 DeepSeek Harness adapter；
- M5 Solve 后端编排：唯一可信 Tool 结果、分级数学验证、运行/流式/取消/恢复；
- Solve 工作台：完整题目输入、Search 题目转入、结构化三页解析与 MathVerifier 证据；
- 数学内容可读展示：题面、步骤和答案支持行内/独立 KaTeX，并兼容旧结果中的未分隔公式；
- M6 第一条切片：Agent 可读取当前教师资料库的聚合处理状态，但看不到私人正文、文件名或路径；
- M6 第二条切片：新工作台可同源上传 PDF/DOCX/图片，显式记录来源与权利依据，并展示 owner-scoped 私人资料清单；
- M6 第三条切片：可对照原文件、首次提取文本和教师校对稿，运行本地 PDF OCR 或逐次授权的外部 OCR，并保留 owner-scoped 修订记录；
- M6 第四条切片：只从教师确认的当前文本版本生成可编辑候选；教材路径由受控 Curriculum 补全，导入固定为 owner 私有、待审核、待数学验证；
- M6 第五条切片：每次私人检索都需教师明确同意；一次性许可绑定当前教师、查询与数量，Agent 只能看到确认文本的有界匹配片段及来源版本/权利状态；
- M7 多模态 Solve：可上传、粘贴或拍摄单题图片；`QuestionCapture` 保留 owner-scoped private media/OCR revision，并通过本地、DeepSeek Vision 或 OpenAI adapter 输出可校对题面；教师确认后，精确图片/识别 revision 通过短时一次性许可接入 Solve，带图题才逐次授权发送受控原图；15 场景固定评测与 Gate E 已通过；
- M8 私有辅助命题：独立 `PersonalQuestionLibrary` 已建立个人题库/分类、owner 私有命题工作区、append-only revision 与完整个人管理；命题只要求自然语言意图，教材知识点、考查方法和易错点由 Agent 在生成后归纳并交给教师确认/校订。题面与选项先以“不含答案”的结构生成并审核；题面错误自动完善、复审和重新解析，解析错误保留题面并重生成解析，直到题面、解析和解析所得标准答案闭环一致。后台任务可跨页面恢复并由 owner 明确取消；正常完成不会留下半成品。若 owner 在解析完成前主动停止，可选择把最新已审核题面保存到自己的私题库，标准答案和解析明确显示“无”并标注缺少解析，且可主动用于组卷；该状态不会进入公共题库或其他用户视图。选择题题干与 A–D 选项独立，内容限定中国普通高中数学，解析只展示正式成稿。明确保存后可搜索、重命名、分类、复制、私有导出、回收或永久删除。26 场景固定评测 12 类违规为 0，Gate E/Gate P 已通过；Agent 仍无保存、管理、发布、共享或删除能力；
- M9 Paper Agent 六条实现切片：自然语言组卷要求先转为可编辑、未确认、未保存蓝图；教师确认后，系统只从通过范围、验证、审核、权利和相似度门禁的公共题，以及当前 owner 明确勾选的私题中建立候选草案。教师明确选题不受蓝图知识范围或难度二次阻断；服务器在选题后自动总结实际知识点和难度并写入双向细目表。教师可保存任何包含通过门禁完整题目的当前草稿；蓝图未完善时先提供取消/确认提示。保存会重新核对精确题目 revision、可信/完整事实和草稿指纹并建立不可变版本，随后可从当前 owner 的指定版本导出学生卷、答案卷和双向细目表 DOCX/PDF。供给不足仍返回真实缺口，不自动命题；
- QuestionBank、MathVerifier、Curriculum、PrivateLibrary、PDF、试卷、教案等成熟业务模块。

当前 Search、Solve、Private Library、多模态图片解题与私有辅助命题均已接入新工作台；M8 固定评测、Gate E 与 Gate P 于 2026-08-28 通过。M9 Paper Agent 六条实现切片、28 场景固定评测与工作树 Gate E/Gate P 连续性检查已通过；在形成可回滚提交并由项目所有者确认阶段转换前，M9 仍为进行中，教案保持预览。最新状态见 [`docs/PROJECT-STATUS.md`](docs/PROJECT-STATUS.md)。

## 核心原则

1. 大模型输出不等于数学验证，`MathVerifier` 不可绕过。
2. 题目来源和权利必须可追踪；来源不明内容进入 quarantine/review。
3. 教师上传及其派生内容默认 private，未经明确授权不得共享或公开。
4. Agent 不直接访问数据库，只能调用受控 Tool 和 FastAPI 业务模块。
5. AI 产物默认 draft；发布必须经过 RightsGate、MathVerifier 与 Teacher Review。
6. DeepSeek Harness 是可替换运行时，业务系统只依赖产品自有接口。
7. 每个阶段必须通过功能、可信、隐私/权利和工程 Gate；真实 Beta 验证前不把支付当作主要工程。
8. 辅助命制题永久只属于创建教师的私题库；公共题库、公共搜索、后台内容管理和其他用户无权读取或管理。

完整边界见 [`docs/DEVELOPMENT-BOUNDARY.md`](docs/DEVELOPMENT-BOUNDARY.md)，量化验证和商业发布条件见 [`docs/PRODUCT-GATES.md`](docs/PRODUCT-GATES.md)。

## 仓库结构

```text
apps/
  teacher-web/   主产品 UI：新的 Agent-first 教师工作台（Next.js，端口 3001）
  api/           模块化业务后端与可信 Search Agent（FastAPI，端口 8000）
  agent/         隔离的 DeepSeek Harness Runtime（Node/TS，端口 4100）
  web/           旧 UI / 业务流程参考（Next.js，端口 3000；不是默认入口）
data/
  commercial-approved/  通过完整商业发布门禁的内容；当前保持为空
  quarantine/           来源或权利不明内容的隔离策略
  test-fixtures/        项目自建 synthetic 测试数据
  runtime/              本地运行数据，Git 忽略
docs/                   当前文档入口与历史迁移/审计记录
scripts/                数据审计、目录与 synthetic fixture 工具
```

架构依赖方向见 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)，文档总索引见 [`docs/README.md`](docs/README.md)。

## 环境要求

- Python 3.12+
- Node.js 24+（DeepSeek Harness 的要求）
- pnpm 10.15.0

## 第一次运行

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".\apps\api[dev]"
pnpm install
pnpm setup:env
```

`setup:env` 不会覆盖已有 `.env`；它会生成两个不同的本地 M2M token，并为 Search Agent 启用 DSH Runtime。随后在 `.env` 中确认：

```dotenv
MATH_AI_SEARCH_AGENT_ENABLED=true
MATH_AI_SOLVE_AGENT_ENABLED=true
MATH_AI_API_INTERNAL_URL=http://127.0.0.1:8000
MATH_AI_AGENT_RUNTIME=dsh
MATH_AI_AGENT_PROVIDER=test-mock
```

分别在三个终端启动业务后端、Agent Runtime 与新工作台：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir .\apps\api --reload
pnpm dev:agent
pnpm dev:web
```

- 新教师工作台：<http://127.0.0.1:3001>
- FastAPI 文档：<http://127.0.0.1:8000/docs>
- Agent Service 健康检查：<http://127.0.0.1:4100/health>（需要 M2M 认证）

`test-mock` 是确定性本地模型，不需要 DeepSeek Key；它会按 Search/Solve 受控指令选择对应 Tool，且仍然经过真实 Harness、Tool gateway 和业务门禁。代码中的 Solve feature gate 默认关闭；本地示例为当前 M5 联调显式开启。使用真实模型时才把 provider 改为 `deepseek-official` 并在私有 `.env` 中设置 Key。

## 常用命令

```powershell
pnpm dev:web                 # 主产品 UI（等同 dev:teacher）
pnpm dev:legacy-web          # 旧 UI，仅用于参考/回归
pnpm typecheck:teacher
pnpm build:teacher
pnpm typecheck:agent
pnpm test:agent
pnpm build:agent
.\.venv\Scripts\python.exe -m pytest .\apps\api\tests
```

## 当前开发顺序

`Search 稳定化（完成） → Solve（完成） → Private Library（完成） → 多模态图片解题（完成） → 私有辅助命题（完成，待转换确认） → Paper → Lesson → Memory → Beta 准备 → Beta 验证 → 商业基础 → Teacher Pro → 教研组 → 学校`

不要并行铺开后续阶段。最新版 M0-M17 路线见 [`docs/ROADMAP.md`](docs/ROADMAP.md)，M8 的固定边界与 Gate 见 [`docs/M8-PRIVATE-QUESTION-AUTHORING.md`](docs/M8-PRIVATE-QUESTION-AUTHORING.md) 与 [`docs/M8-GATE-REVIEW.md`](docs/M8-GATE-REVIEW.md)，每阶段和商业发布门禁见 [`docs/PRODUCT-GATES.md`](docs/PRODUCT-GATES.md)。

## 数据与密钥

仓库不得包含真实 API Key、数据库、上传文件、PDF/DOCX、教师私人资料或来源未审查的题库内容。`.env`、`data/runtime`、`data/private-runtime`、`output` 与上传目录均被忽略。

第三方依赖与权利文件：[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)、[`docs/legal/THIRD-PARTY-LICENSES.md`](docs/legal/THIRD-PARTY-LICENSES.md)、[`docs/commercial-v1/DATA-RIGHTS-MIGRATION-REVIEW.md`](docs/commercial-v1/DATA-RIGHTS-MIGRATION-REVIEW.md)。

## 参与开发

先阅读 [`AGENTS.md`](AGENTS.md) 和 [`CONTRIBUTING.md`](CONTRIBUTING.md)。涉及教师工作流、数据含义、权利、private/public、删除、权限或发布门禁的变更，必须先由项目所有者确认。
