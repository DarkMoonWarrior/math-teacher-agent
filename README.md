# 备课伙伴 · 高中数学教师可信 AI Agent

面向中国高中数学教师的 Agent-first 备课工作台。教师用自然语言描述教学任务，系统通过受控业务能力协助搜题，并逐步扩展到解题、私人资料、组卷和教案；来源、权利、数学验证与教师复核状态始终可追踪。

这个仓库不是从零重写旧项目，也不会继续沿用旧界面。`high-school-math-ai` 的成熟业务模块与测试是地基；新的产品入口、交互和 Agent 工作流位于 `apps/teacher-web`。

## 当前能做什么

- 新教师工作台与搜题／解题／教案／组卷能力导航；
- 可信 Search Agent：自然语言意图、教材映射、真实题库检索、去重与多样性；
- 题目来源、权利状态、验证状态和条件放宽披露；
- 产品自有 `TeacherAgentRuntime` 与隔离的 DeepSeek Harness adapter；
- M5 Solve 后端编排：唯一可信 Tool 结果、分级数学验证、运行/流式/取消/恢复；
- Solve 工作台：完整题目输入、Search 题目转入、结构化三页解析与 MathVerifier 证据；
- QuestionBank、MathVerifier、Curriculum、PrivateLibrary、PDF、试卷、教案等成熟业务模块。

当前 Search 与 Solve Agent 已接入新工作台；Solve 的固定 synthetic eval 与完整 M5 Gate E 已严格通过。M6 仍需项目所有者确认后才可启动，教案和组卷在新 UI 中继续明确标记为工作流预览。最新状态见 [`docs/PROJECT-STATUS.md`](docs/PROJECT-STATUS.md)。

## 核心原则

1. 大模型输出不等于数学验证，`MathVerifier` 不可绕过。
2. 题目来源和权利必须可追踪；来源不明内容进入 quarantine/review。
3. 教师上传及其派生内容默认 private，未经明确授权不得共享或公开。
4. Agent 不直接访问数据库，只能调用受控 Tool 和 FastAPI 业务模块。
5. AI 产物默认 draft；发布必须经过 RightsGate、MathVerifier 与 Teacher Review。
6. DeepSeek Harness 是可替换运行时，业务系统只依赖产品自有接口。
7. 每个阶段必须通过功能、可信、隐私/权利和工程 Gate；真实 Beta 验证前不把支付当作主要工程。

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

`Search 稳定化（完成） → Solve（完成，等待阶段确认） → Private Library（未启动） → Paper → Lesson → Memory → Beta 准备 → Beta 验证 → 商业基础 → Teacher Pro → 教研组 → 学校`

不要并行铺开后续阶段。最新版 M0-M15 路线见 [`docs/ROADMAP.md`](docs/ROADMAP.md)，每阶段和商业发布门禁见 [`docs/PRODUCT-GATES.md`](docs/PRODUCT-GATES.md)。

## 数据与密钥

仓库不得包含真实 API Key、数据库、上传文件、PDF/DOCX、教师私人资料或来源未审查的题库内容。`.env`、`data/runtime`、`data/private-runtime`、`output` 与上传目录均被忽略。

第三方依赖与权利文件：[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)、[`docs/legal/THIRD-PARTY-LICENSES.md`](docs/legal/THIRD-PARTY-LICENSES.md)、[`docs/commercial-v1/DATA-RIGHTS-MIGRATION-REVIEW.md`](docs/commercial-v1/DATA-RIGHTS-MIGRATION-REVIEW.md)。

## 参与开发

先阅读 [`AGENTS.md`](AGENTS.md) 和 [`CONTRIBUTING.md`](CONTRIBUTING.md)。涉及教师工作流、数据含义、权利、private/public、删除、权限或发布门禁的变更，必须先由项目所有者确认。
