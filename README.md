# 备课伙伴 · 高中数学教师可信 AI Agent

面向中国高中数学教师的 Agent-first 备课工作台，提供搜题、解题、资料库、命题、教案和组卷。来源、权利、数学验证与教师复核状态可追踪；教师私人内容按用户隔离。

## 当前进度

截至 2026-09-11，M0–M12 已完成。M13 的五条隐私安全验证切片已经实现，但真实教师样本不足，项目所有者明确将真实 Beta 延期并进入 **M14 Commercial Foundation**；M13 Gate 仍未通过。M14 已建立生产身份基础和账号生命周期边界：正式 `AccountIdentity` Interface 分离账号、tenant 与私人内容 owner；Teacher Web 已接入正式登录和独立、默认关闭的个人账号注册，注册输入不能选择 owner、tenant、角色或能力；Agent 仍不能创建账号。本机操作者可显式确认创建、停用和重置密码，相关操作撤销旧会话；失效会话只能先预览再确认清理。正式登录与注册共用账号和网络双范围限流、摘要化安全事实及可信来源适配。登录与操作者审计的 HMAC 已使用彼此独立的版本化密钥环，新记录只用当前密钥，旧密钥在有界过渡期继续匹配且不批量重写历史摘要。PostgreSQL 正式身份 adapter 已接入同一 Interface，schema 只能先预演、再凭一致指纹明确确认部署；生产若仍选择 SQLite 身份、缺少 DSN/驱动或 schema 不符会失败关闭。owner 数据只读清点覆盖七类 SQLite 私人业务存储和四类关联文件目录，四个真实文件域按数据库引用、owner 与磁盘对象完成只读对账；`OwnerMigrationPlanner` 把两份指纹绑定为逐对象、依赖有序、仅摘要且明确不可执行的迁移计划，内部对象/文件物化器再以同一摘要和源文件 Interface 重读计划内容：数据库载荷只改绑目标 owner/tenant，文件流在物化与真正暂存时都复核 SHA-256 和长度，任何计划、对象、依赖或内容漂移都失败关闭。`OwnerMigrationExecutor` 要求精确确认和实时计划复核，并通过原子事务 adapter 约束幂等状态、提交前目标对账与失败回滚。独立 PostgreSQL 迁移落地区域也已固定，使用与运行时身份连接分离的私密目标 DSN，部署必须先预演再凭一致指纹明确确认；它只承载迁移状态、对象暂存和文件发布记录，不是运行时业务内容库。具体 `PostgresOwnerMigrationAdapter` 已把对象/文件物化、SQL 暂存、目标摘要重算、可逆文件发布和完成标记接入同一事务 Interface，并通过合成连接与故障注入验证普通失败回滚。`PostgresOwnerMigrationRecovery` 进一步以摘要化预演、精确确认和重新对账，幂等修复数据库已提交但 published 内容缺失、matching staged 内容仍存在的窗口；冲突或证据缺失均失败关闭。正式账号、封闭测试和纯本地开发模式互斥，任何账号模式都会关闭不安全的旧单用户接口。当前仍无生产文件 staging/recovery Adapter 或恢复 CLI，也未执行真实 PostgreSQL Gate 或 owner-aware 内容迁移；邮箱验证、找回密码、MFA 和外部分布式服务仍未完成，不能据此宣称生产多租户或商业发布就绪。

2026-09-12 增量：正式会话 IDOR/tenant isolation 合成 Gate、私有对象 namespace、本地原子字节 Adapter 与本地持久任务队列 seam 已加入固定回归。任务 subject、命令与结果进入 tenant/owner 授权的私有对象，SQLite 只保留摘要化 scope/idempotency/subject 和状态；结果 binding 会先登记为未就绪，原子发布后才可读取，崩溃残留仍可按保留策略定位清理。重启遗留任务明确中断并须由当前会话显式恢复，恢复操作本身递增 attempt，旧 worker 不能覆盖新结果。该队列尚未接管现有命题/OCR 路由，也不是云队列、多 worker 或 exactly-once 声明；真实 PostgreSQL、多租户和 M14 总 Gate 仍未完成。

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
