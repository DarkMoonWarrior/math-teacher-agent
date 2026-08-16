# UI Polish v1 — 教师工作台 & Search Agent 商业 UI 打磨

- 日期：2026-08-16
- 分支：`feat/ui-polish-teacher-workspace-v1`
- 基线：`main` @ `02ee832`
- 范围：纯前端 UI/UX polish；不改 Backend、Search Agent 业务逻辑、权限/验证门禁、Agent Tool、数据库边界

## 1. 设计目标

把现有约 8/10 的教师工作台 UI 提升到“可以正式给高中数学教师内测”的完成度。保留既有视觉体系（深蓝侧栏、浅灰 Canvas、白色卡片、蓝色主操作、青绿信任、琥珀提示、宋体标题 + 无衬线正文），不做 AI 渐变风、ChatGPT Clone、玻璃拟态或娱乐化设计。

本阶段解决五类问题：

1. 内部技术字段泄漏到教师界面（P0）
2. 零结果页信息重复、大面积红色误用
3. “可信度”与“匹配度”语义混淆
4. AI 搜题与传统高级筛选像两个独立产品
5. 字号过小、层级权重雷同、技术信息抢占主视图

## 2. 页面范围

| 页面 | 改动 |
| --- | --- |
| `/` 首页 | 搜索快捷卡文案改为“AI 智能搜题 / 描述教学需求，自动匹配知识点、难度与题型”；全局可读性调整 |
| `/search` 高级筛选 | 顶部增加 `SearchModeTabs`（AI 搜题 / 高级筛选）；右上角入口改为次级按钮“使用 AI 搜题 →” |
| `/search/agent` AI 搜题 | 整页重构：Task Composer、示例 Chips、已理解为 + 图例、结果卡、零结果卡、错误态、检索详情折叠 |
| Sidebar / Topbar | 活跃态匹配 `/search` 与 `/search/agent`；全局搜索 placeholder 与 AI Composer 区分；字号下限提升 |

路由未改变：`/search/agent` 与 `/search` 保持不变。

## 3. 视觉语言

- 主操作蓝色 Primary Button；次级 Ghost Button；危险/错误仍用红，但“没搜到题”不再使用红色主视觉。
- 零结果使用中性卡 + 琥珀强调，动作靠近结果，一屏内可读完。
- 新增样式统一使用 `search-agent-*` 命名，未引入 `!important`。
- 三级表面：Primary Surface（白卡 + shadow）、Secondary Surface（白/浅灰 + border）、Inline Notice（soft background + thin border）。

## 4. 教师可读性（字号审计）

原则：Readable Dense UI，不暴力放大、不牺牲信息密度。本轮把教师主工作区可见文本从 7–10px 提升到至少 11px：

- Topbar 任务角标 7→11px、任务弹窗标签 8/9→10/11px、搜索按钮 9→12px
- Sidebar 导航 13→14px、模式标签 9→10px、角色菜单说明 9→11px
- AI 搜题：示例 10→12px、图例 9→12px、Loading/Error 12→13px、提交按钮 44px 高
- 题干使用数学文本组件，保持 16px 附近阅读基线

## 5. 教师面向字段映射（P0）

`apps/web/app/search/agent/ui.tsx` 建立 `FIELD_LABELS`，内部 domain 字段不再直接展示：

- `volume` → 教材、`chapter` → 章节、`section` → 小节、`knowledge_points` → 知识点、`difficulty_range` → 难度、`question_types` → 题型、`teaching_usage` → 教学用途
- `kp_xxx` 内部节点 id：通过 `isInternalNodeId` 识别，主视图不展示；有真实名称时展示名称（`translateKnowledgePointValues`），否则剔除
- 难度数字 → 基础/中等偏易/中等/中等偏难/较难；题型与教学用途枚举 → 中文标签
- `question_id`、原始 status 枚举只出现在结果卡底部“高级信息（题目编号与状态）”折叠区

## 6. Match vs Trust 视觉隔离

- 搜索层匹配：`✓ 完全匹配` / `≈ 相近条件补充`（`MatchBadge`）
- 信任层：`TrustBadge` 忠实映射后端 status，不伪造状态：
  - `passed` / `program_verified` / `teacher_review_approved` → teal“程序验证通过”
  - `teacher_review_required` / `needs_math_review` / `needs_formula_review` → amber“需要教师复核”
  - `source_inconsistency_detected` → alert“来源待核查”
  - 其他/缺省 → neutral“尚未验证”
- “可信度”文案统一改为“匹配度”，只表达搜索条件与结果的匹配程度。
- 来源状态映射：`commercial_granted` → 来源已记录、`rights_unclear` → 权利待审核（琥珀警示）。

## 7. Hard / Soft / Default 用户语言

- `hard` → 必须满足（蓝）
- `soft` → 优先满足（琥珀）
- `default` → 系统补充（灰）
- “已理解为”区域保留，chip 高度/间距统一，饱和度降低，下方固定三色图例。
- Chip 不可编辑（当前产品无 Chip Editor），不假装可点击。

## 8. AI Search Composer

- 标题“描述你正在准备什么题”，副文案“年级、知识点、难度、题型与用途都可以直接说”。
- textarea 64–160px 高、可纵向拉伸；Primary CTA“AI 搜题 →”位于右侧，Loading 时显示 Ghost“停止搜索”。
- 普通态只显示 3 个示例 Chip，提供“换一批”轻量切换；示例 Chip 不截断。
- 与 Topbar 全局搜索（“搜索全站知识点、题目或内容”）视觉与语义区分。

## 9. Zero Result 新结构

单一紧凑卡片，去除“三处重复说没找到”与红色 Error 风格：

- 标题“暂时没有完全匹配的题目”+ 说明“系统不会为了凑数而生成或伪造题目”
- “必须满足 / 优先满足”两组条件 chips + “当前：0 道完全匹配 · 匹配度：…”
- “可以尝试”建议列表（来自后端 `suggestions`）
- 动作：“修改搜索条件”（回到 Composer）、“高级筛选搜题”（`/search`）
- 检索说明收敛到“为什么没有找到？查看检索详情”折叠区

## 10. Error / Cancel / Loading

- 教师语言优先：`SEARCH_PLAN_EXHAUSTED` → “这次搜索没有找到合适结果”；`RUNTIME_UNAVAILABLE` → “AI 搜题服务暂时不可用”。
- 原始 error code 只进入“技术详情（仅供技术支持参考）”折叠区；不显示 stack/local path/secret。
- Loading 使用中性文案“正在理解你的教学需求…”，不伪造 Tool 级进度；Cancel 为 Ghost“停止搜索”。

## 11. 技术信息下沉

- 普通视图不显示 候选数 / 工具调用次数 / SearchPlan / request_id。
- 折叠区“为什么得到这些结果？查看检索详情”：结果说明、条件调整记录、本次搜索条件（SearchPlan 中文步骤）、技术信息（请求/会话/运行编号、候选数、工具调用数、耗时）。

## 12. Responsive 检查

人工 QA 已覆盖 1440×900、1280×800、1024×768、768px 四种宽度（截图见第 14 节）。检查点：AI Composer、Intent Chips、Result Cards、Topbar、Sidebar、传统双栏题库。本轮未做大型移动端导航重构；768px 以下保持可用，不追求手机原生体验。

## 13. Known UI Test Debt

- 项目当前没有浏览器自动化测试框架（Playwright/Cypress）；本轮按要求未引入，视觉回归依赖人工截图 QA（第 14 节）。
- 建议在 Closed Beta 前引入最少量的 Playwright 冒烟（导航、P0 字段不泄漏、零结果卡结构、错误码下沉），并把本轮截图矩阵转成自动化回归。
- `globals.css` 仍为单文件技术债，本轮按要求未拆分；后续阶段可渐进抽取 `search-agent-*` 样式。

## 14. Screenshot QA Matrix

截图与 QA 记录保存在本机临时目录 `<LOCAL_TEMP>/ui-polish-qa/`，不入库；QA 期间注入的合成题已从运行时题库删除。

| 检查点 | 视口 | 结果 | 截图 |
| --- | --- | --- | --- |
| A. 首页 | 1440×900 | 标题无遮挡，通过 | `06-home-1440.png` |
| B. /search 高级筛选 | 1440×900 | 模式切换正常，通过 | `07-search-advanced-1440.png` |
| C. /search/agent 初始态 | 1440 / 1280 / 1024 | Composer 为第一视觉焦点，通过 | `01-search-agent-1440-initial.png`、`08-search-agent-1280-initial.png`、`05-search-agent-1024-initial.png` |
| D. /search/agent 零结果 | 1440 / 1024 | 单卡结构、无内部字段泄漏、非红色、amber 强调，DOM 断言通过 | `09-search-agent-1440-zero-final.png`、`03-search-agent-1024-zero.png` |
| E. 部分结果 | 1440 | “找到 3 道完全匹配 · 另有 2 道相近条件补充”，通过 | `10-search-agent-1440-partial-real.png` |
| F. 成功结果 | 1440 | 3 张完全匹配卡，Match/Trust/来源/高级信息齐全，通过 | `11-search-agent-1440-success-real.png` |
| G. 1024 零结果 | 1024×768 | 无横向溢出，通过 | 同 D |
| H. 768 初始态 | 768 | 可用，无横向溢出，通过 | `04-search-agent-768-initial.png` |

成功/部分结果使用 synthetic 合成题 + 真实管线复现；合成题已从运行时数据库移除，`data/commercial-approved/` 未受影响（仍为空）。

## 15. 边界与未改动

- 未修改 Backend、SearchIntent/SearchPlan/Ranking、Rights/Visibility Gate、MathVerifier、QuestionBank、Agent Tool Allowlist、DSH Runtime、TeacherAgentRuntime、数据库结构。
- 未新增 Tool；未把 UI 问题通过修改业务规则解决。
- 未引入真实题库数据；`data/commercial-approved/` 保持空。
