# 备课伙伴 · 高中数学教师可信 AI Agent

面向中国高中数学教师的 Agent-first 备课工作台，提供搜题、解题、资料库、命题、教案和组卷。来源、权利、数学验证与教师复核状态可追踪；教师私人内容按用户隔离。

## 当前进度

截至 2026-09-10，M0–M12 已完成。M13 的五条隐私安全验证切片已经实现，但真实教师样本不足，项目所有者明确将真实 Beta 延期并进入 **M14 Commercial Foundation**；M13 Gate 仍未通过。M14 已建立生产身份基础和账号生命周期边界：正式 `AccountIdentity` Interface 分离账号、tenant 与私人内容 owner；Teacher Web 已接入正式登录和独立、默认关闭的个人账号注册，注册输入不能选择 owner、tenant、角色或能力；Agent 仍不能创建账号。本机操作者可显式确认创建、停用和重置密码，相关操作撤销旧会话；失效会话只能先预览再确认清理。正式登录与注册共用账号和网络双范围限流、摘要化安全事实及可信来源适配。登录与操作者审计的 HMAC 已使用彼此独立的版本化密钥环，新记录只用当前密钥，旧密钥在有界过渡期继续匹配且不批量重写历史摘要。真实生产环境若仍使用直连来源或 SQLite 限流会失败关闭。操作者写操作另由摘要化生命周期审计先记录意图，审计不可用时不执行变更；当前本机操作者标签并非管理员认证。正式账号、封闭测试和纯本地开发模式互斥，任何账号模式都会关闭不安全的旧单用户接口。该能力默认关闭，SQLite 只是过渡 adapter，邮箱验证、找回密码、MFA 和外部分布式服务仍未完成；尚不代表生产认证、多租户或商业发布就绪。

- 搜题/解题：受控工具、真实题库检索、数学验证证据、流式进度、取消与恢复。
- 资料库：私人上传、大模型识别、原稿与可读校对稿对照、中文 + LaTeX 编辑、拆题与教材映射。
- 命题：先展示已审核题面，后台继续解析；可停止并选择保存缺少解析的私题，答案/解析明确显示“无”。
- 组卷：公共/本人私题选择、增删与配分、知识点/难度事后分析、本人历史编辑、不可变版本及学生卷/答案卷/细目表导出。
- 教案：蓝图、受控来源、完整正文、逐块编辑/锁定、本人历史与精确版本 DOCX/PDF 导出。
- 教师偏好：结构化偏好、透明缺省、可解释提议、反馈、导出与删除，统一位于右上角设置。
- 工作区：六模块统一左右布局、可折叠分隔条、切换保留任务、明确清空当前任务。

完整实现状态、限制与下一步见 [项目状态](docs/PROJECT-STATUS.md)。

## 仓库结构

```text
apps/
  teacher-web/   唯一产品 UI（Next.js，3001）
  api/           业务规则、可信检查与存储（FastAPI，8000）
  agent/         隔离的 Node/TypeScript Agent Runtime（4100）
data/
  commercial-approved/  满足发布门禁的内容；当前无商业题目
  quarantine/           来源/权利不明内容的隔离规则
  test-fixtures/        项目自建合成测试数据
docs/                   当前规范、里程碑证据与归档材料
scripts/                环境初始化、验证、数据治理与恢复工具
```

旧 UI 已移除。相关教材基线、来源/权利与迁移证据仍保留，历史说明不代表当前入口或开发进度。本地环境、数据库、上传和生成文件不进入 Git。

## 第一次运行

需要 Python 3.12+、Node.js 24+ 和 pnpm 10.15.0。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".\apps\api[dev]"
pnpm install --frozen-lockfile
pnpm setup:env
```

`setup:env` 不覆盖已有 `.env`。配置说明见 [.env.example](.env.example)；访问码、真实模型密钥与 M2M token 只放私有环境，不能提交。默认 `test-mock` 用于确定性本地验证，不会生成真实模型内容；真实模型接入按 [Agent 说明](apps/agent/README.md) 配置。各业务开关需显式启用。

分别在三个终端运行：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir .\apps\api --reload
pnpm dev:agent
pnpm dev:teacher
```

- 教师工作台：<http://127.0.0.1:3001>
- API 文档：<http://127.0.0.1:8000/docs>
- 就绪检查：<http://127.0.0.1:8000/ready>

启用正式身份或 Closed Beta 后必须使用对应有效会话，两者不能同时开启；两者均关闭才是固定本地教师的开发模式。当前不等同于完整生产认证、组织管理、支付或商业发布。

## 验证

```powershell
pnpm typecheck:teacher
pnpm test:teacher
pnpm build:teacher
pnpm typecheck:agent
pnpm test:agent
pnpm build:agent
.\.venv\Scripts\python.exe -m pytest .\apps\api\tests
```

测试只使用合成数据与测试适配器，不调用真实模型。`dev:web`、`build:web`、`typecheck:web` 是当前 Teacher Web 的兼容别名。

## 开发与可信边界

大模型输出不等于数学验证；Agent 只能经过受控工具访问 FastAPI，不直接访问数据库或执行保存、发布、共享、删除。辅助命题永久 owner-only。来源不明内容隔离，商业发布必须经过权利、数学验证和教师审核。

先阅读 [AGENTS](AGENTS.md)、[参与开发](CONTRIBUTING.md) 与 [文档索引](docs/README.md)。当前路线与边界分别见 [ROADMAP](docs/ROADMAP.md)、[DEVELOPMENT-BOUNDARY](docs/DEVELOPMENT-BOUNDARY.md)、[PRODUCT-GATES](docs/PRODUCT-GATES.md)。第三方声明见 [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES.md) 和 [许可证清单](docs/legal/THIRD-PARTY-LICENSES.md)。
