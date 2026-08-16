# 第三方依赖许可清单（Commercial V1）

核验日期：2026-08-16
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

## Node 前端依赖（apps/web）

| 包 | 版本 | 许可 | 状态 |
| --- | --- | --- | --- |
| next | 16.2.12 | MIT | VERIFIED |
| react / react-dom | 19.2.8 | MIT | VERIFIED |
| katex | 0.18.1 | MIT | VERIFIED |
| typescript（dev） | 5.9.2 | Apache-2.0 | VERIFIED |
| @types/*（dev） | 见锁文件 | MIT | VERIFIED |

传递依赖（代表性）：sharp（Next 可选图像处理依赖，许可待核验）→ REVIEW。

## 待办（合规）

- 对 `REVIEW` 项逐一下载许可证全文并归档到 `docs/legal/`，确认分发与 NOTICE 义务。
- 商业发布前由法务复核全部依赖许可与聚合分发的合规要求。
