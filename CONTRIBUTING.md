# 参与开发

## 开始之前

1. 阅读 `AGENTS.md`、`docs/DEVELOPMENT-BOUNDARY.md` 和 `docs/PROJECT-STATUS.md`。
2. 确认修改落在当前里程碑内；不要因为旧后端已有某项能力就把它宣称为新 Agent 已完成。
3. 从功能分支开发，分支默认使用 `codex/` 前缀。

## 修改范围

- 新 UI 与 Agent-first 交互写入 `apps/teacher-web`。
- 业务规则、验证、权利、私有性与存储访问写入 `apps/api` 对应业务模块。
- Harness、Agent loop、模型插件与 Tool transport 只写入 `apps/agent`。
- `apps/teacher-web` 是唯一产品 UI；旧界面已移除，不再维护第二套页面壳。

## 数据规则

- 自动测试只能使用项目自建 synthetic fixture。
- 不提交 `.env`、密钥、数据库、上传、导出、私人资料或第三方题库内容。
- 不删除来源、权利、验证、审核或修订证据。
- 不创建自动 public/publish 路径。

## 测试

按修改的 seam 运行：

```powershell
pnpm typecheck:teacher
pnpm check:repo
pnpm test:teacher
pnpm build:teacher
pnpm typecheck:agent
pnpm test:agent
pnpm build:agent
.\.venv\Scripts\python.exe -m pytest .\apps\api\tests
```

## 提交

- 一个提交解决一个清晰问题。
- 提交信息说明结果，例如 `fix(search): keep negative question types out of positive constraints`。
- 提交前检查 staged diff，禁止使用无法确认范围的全仓库批量暂存。
- commit、push 与创建 Pull Request 分别需要明确授权。

## 必须先确认的事项

教师工作流、产品范围、数据含义、版权处置、private/public 状态、永久删除、破坏性迁移、权限模型、发布门禁、商业规则或目标用户发生变化时，先向项目所有者说明影响，再编码。
