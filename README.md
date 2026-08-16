# 高中数学教师可信 AI Agent（Commercial V1）

面向中国高中数学教师的可信 AI Agent 工作台：以自然语言、题目图片、PDF 或教师自己的教学资料为输入，
协助完成搜题、解题、相似题与变式、教材知识点映射、数学正确性验证、组卷、教案、资料整理与导入导出等备课工作流。

本仓库是 Commercial V1 主开发仓库（Private）。代码来自公开 Prototype / Alpha 仓库
`DarkMoonWarrior/high-school-math-ai` 的 Clean Snapshot 迁移，不继承旧仓库 Git 历史。
迁移范围、排除范围与数据政策见 `docs/commercial-v1/COMMERCIAL-BASELINE.md`。

## 核心原则

- **可信分级**：所有 AI 结果必须区分"已有可信题库内容 / 程序独立验证通过 / AI 生成待教师复核"，
  不允许把未经验证的内容冒充为已验证。MathVerifier 不可绕过。
- **权利可追溯**：每道题追踪来源、原始文件、权利状态与审核状态；来源不明的数据进入 quarantine / review，
  不默认商用。
- **私人默认私有**：教师上传资料及其派生内容默认 private，任何 public 化必须经过明确授权。
- **Agent 权限边界**：Agent 不得直接访问数据库，只能通过受控 Tool 调用业务服务；
  所有 AI 产物默认 draft，发布必须经过 RightsGate、MathVerifier 与教师审核。

## 目录结构

```text
apps/web          Next.js 教师工作台
apps/api          FastAPI 模块化业务后端（QuestionBank / MathVerifier / PrivateLibrary 等）
data/
  commercial-approved/  经权利+验证+教师审核门禁的内容（当前为空）
  quarantine/           来源或权利不明的隔离内容（仅策略文件）
  private-runtime/      教师私人运行时数据（gitignored）
  test-fixtures/        仅允许 synthetic 测试数据
docs/high-school-math-ai/  产品、架构与治理文档
docs/commercial-v1/        商业迁移审计与基线文档
scripts/                  数据审计与加工工具
```

## 本地运行

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".\apps\api[dev]"
pnpm install
```

- Web：`pnpm dev:web`（默认 http://localhost:3000）
- API：`.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir .\apps\api --reload`（http://localhost:8000/docs）
- 测试：`.\.venv\Scripts\python.exe -m pytest .\apps\api\tests`；`pnpm typecheck:web`；`pnpm build:web`

## 已知基线问题与合规

- Known Migration Issues：`docs/commercial-v1/KNOWN-MIGRATION-ISSUES.md`
- 第三方依赖声明：`THIRD_PARTY_NOTICES.md` 与 `docs/legal/THIRD-PARTY-LICENSES.md`
- 数据与版权政策：`docs/commercial-v1/DATA-RIGHTS-MIGRATION-REVIEW.md`

本仓库不含任何题库内容数据、原始 PDF/DOCX、教师私人资料或密钥。所有内容数据必须经过
`docs/commercial-v1/DATA-RIGHTS-MIGRATION-REVIEW.md` 定义的审查流后进入 `data/commercial-approved/`。
