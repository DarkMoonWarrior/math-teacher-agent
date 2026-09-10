# 第三方依赖许可清单（Commercial V1）

核验日期：2026-08-20（新增 `apps/teacher-web` 入口复核；依赖版本未变化）
维护说明（2026-09-04）：移除旧 UI 后仅调整应用范围；本次锁文件未升级依赖。下表保留原包元数据核验日期与 REVIEW 项，不把仓库清理视为新的许可证全文审核。
核验方式：已安装发行版的包元数据（Python: `importlib.metadata`；Node: 各包 `package.json` 的 `license` 字段）。

状态定义：

- `VERIFIED`：从本机已安装发行版元数据中读取到许可证标识。
- `REVIEW`：元数据缺失、许可复杂或未安装（可选依赖），需要进一步核验许可证全文与义务。

## Python 运行时依赖（apps/api）

| 包 | 版本 | 许可 | 状态 |
| --- | --- | --- | --- |
| fastapi | 0.141.1 | MIT | VERIFIED |
| uvicorn | 0.52.3 | BSD-3-Clause | VERIFIED |
| pydantic | 2.13.4 | MIT | VERIFIED |
| pydantic-settings | 2.15.0 | MIT | VERIFIED |
| pillow | 11.3.0 | MIT-CMU | VERIFIED |
| pypdf | 6.14.2 | BSD-3-Clause | VERIFIED |
| pypdfium2 | 5.12.1 | BSD-3-Clause + Apache-2.0（含依赖许可） | REVIEW |
| python-multipart | 0.0.32 | Apache-2.0 | VERIFIED |
| python-docx | 1.2.0 | MIT | VERIFIED |
| reportlab | 4.5.1 | BSD（见其 license.txt） | VERIFIED |
| psycopg / psycopg-binary | >=3.2,<4（PostgreSQL 生产 adapter；当前环境未安装） | 待核验 | REVIEW |
| httpx（测试） | 0.28.1 | BSD-3-Clause | VERIFIED |
| pytest（测试） | 8.4.2 | MIT | VERIFIED |

主要传递依赖：starlette（BSD-3-Clause）、anyio（MIT）、typing-extensions（PSF-2.0）、
pydantic-core（MIT）、idna（BSD-3-Clause）、certifi（MPL-2.0）、httpcore（BSD-3-Clause）、
h11（MIT）、click（BSD-3-Clause）、python-dotenv（BSD-3-Clause）、watchfiles（MIT）、
websockets（BSD-3-Clause）、packaging（Apache-2.0 OR BSD-2-Clause）、pygments（BSD-2-Clause）、
pluggy（MIT）、iniconfig（MIT）。

## 可选依赖（未安装于当前基线）

| 包 | 用途 | 许可（待核验） | 状态 |
| --- | --- | --- | --- |
| pix2text（math-ocr extra） | 本地数学公式 OCR | PyPI 声明待核验 | REVIEW |

## Node 前端依赖（apps/teacher-web）

| 包 | 版本 | 许可 | 状态 |
| --- | --- | --- | --- |
| next | 16.2.12 | MIT | VERIFIED |
| react / react-dom | 19.2.8 | MIT | VERIFIED |
| katex | 0.18.1 | MIT | VERIFIED |
| typescript（dev） | 5.9.2 | Apache-2.0 | VERIFIED |
| @types/*（dev） | 见锁文件 | MIT | VERIFIED |

传递依赖（代表性）：sharp（Next 可选图像处理依赖，许可待核验）→ REVIEW。


`apps/teacher-web/public/images/math-atlas.png` 为本项目生成的 UI 视觉资产，不是迁入的第三方题库或教材图片。

## Node Agent Service 依赖（apps/agent）

DSH 全部直接依赖精确锁定 0.1.0-rc.6；以下许可来自已安装发行版的 package.json 元数据
（pnpm licenses list，核验日期 2026-08-16）。

| 包 | 版本 | 许可 | 状态 |
| --- | --- | --- | --- |
| @deepseek-ai/dsh-app-boot / dsh-agent / dsh-agent-loop / dsh-llm / dsh-llm-deepseek / dsh-session / dsh-session-persistence / dsh-session-persistence-jsonl / dsh-system-prompt / dsh-tools | 0.1.0-rc.6 | MIT | VERIFIED |
| @deepseek-ai/cordis | 4.0.1 | MIT | VERIFIED |
| @deepseek-ai/cordis-plugin-include / cordis-plugin-loader | 1.0.6 / 1.0.2 | MIT | VERIFIED |
| @deepseek-ai/schemastery | 3.18.1 | MIT | VERIFIED |
| tsx / vitest / typescript / @types/node（dev） | 4.23.12 / 4.1.10 / 5.9.2 / 24.x | MIT / MIT / Apache-2.0 / MIT | VERIFIED |

传递依赖（dsh-attachment、dsh-brand、dsh-invariants、dsh-scope、dsh-timeout、
dsh-code-runtime、dsh-anonymous-user-id、dsh-home-paths、dsh-launch-environment、
dsh-settings、dsh-typert-protocol、dsh-user-approval、cosmokit、cordis-plugin-group 等）
发布元数据同样为 MIT；esbuild/koffi 原生二进制为 MIT；其余为 Apache-2.0 / BSD-3-Clause / ISC。

声明：以上核验基于发布包元数据，不构成对“所有依赖允许商业使用”的声明；
商业发布前仍需法务复核许可证全文与 NOTICE/分发义务。DSH 为 Developer Preview，
升级时需同步更新本清单与 DSH-INTEGRATION-LOCK.md。

## 待办（合规）

- 对 `REVIEW` 项逐一下载许可证全文并归档到 `docs/legal/`，确认分发与 NOTICE 义务。
- 商业发布前由法务复核全部依赖许可与聚合分发的合规要求。
