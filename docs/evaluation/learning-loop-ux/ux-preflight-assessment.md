# 第 3 周学习闭环 UX 实施评估与纠偏

初次评估日期：2026-07-21
纠偏完成日期：2026-07-22

评估结论：**原实施前评估结论撤回；`UX-01` 已按项目原生定位完成纠偏和本地验收，`UX-02` 至 `UX-04` 尚未开始，不得按原“学习空间/学习教练/恰好五项导航”合同继续实施。**

## 基线与授权边界

- 目标仓库为 `Yuan0518dong/AI-Agent`。PR #5 `feature/learning-loop -> main` 已于 2026-07-21 合并，精确基线为 `personal/main@9d2c59f7ac71ec614bf71561d64fc6ab35ed1caf`。
- 基线 GitHub Actions run `29807141471` 已通过 Reliability、PostgreSQL/pgvector（含最新迁移回滚）和 Playwright。
- `UX-01` 原代码提交为 `e4b251e`，原记录提交为 `a72aaaa`；均未推送、创建 PR、合并或部署。后端、数据库迁移、FSRS 参数和真实 Provider 未改动。
- 原截图 `docs/images/ux01-learning-space-mobile.png` 与原测试记录继续保留，只作为被替代实现的历史证据，不覆盖、不改写为纠偏结果。

## 复核发现

| 等级 | 发现 | 纠偏决定 |
|---|---|---|
| 高 | “学习空间”“学习教练”把对标项目词汇提升为本项目页面和模块名称，与“基于可控 Agent 的个人学习助手”定位不一致 | 恢复“学习目标”“智能助手”；对标词只描述机制，不替换业务对象或产品角色 |
| 高 | 原 `UX-02` 强制桌面和移动都恰好五项，并把资料、问答移出桌面主导航，削弱 RAG 与带引用问答的可发现性 | 桌面保留七项；移动保留四项加“更多”；语义一致但不强制同构 |
| 高 | 原 `UX-01` 直接使用持久化 `selectedGoalId` 过滤资料、问答摘要、闪卡、测试和进度，直接导航也会隐藏其他目标数据 | 拆分持久化目标选择和临时视图范围；快捷入口才设置范围，提供“查看全部”，直接主导航清除临时范围 |
| 高 | 原 Today 方案首屏组合 Dashboard、完整 Agent Context、Drafts、Review Queue 和 Weak Points；Agent Context 会逐资料读取 chunks、问答、闪卡、测试和 attempts，并重复计算后三类 | 首屏只渲染 Dashboard；后续只允许有界 Today Actions 读取，不调用完整 Agent Context |
| 高 | Agent Context 已在每目标、每资料和总结果层截断，不能支撑任务书声明的全量全局排序 | Today 排序在有界专用读取中完成，返回已排序投影及明确上限 |
| 中高 | “资料不足”记录没有 `resolved` 状态，无法满足“只显示未解决项” | 本周不把资料不足作为长期 Today 待办，继续在问答或资料页面提示 |
| 中高 | 原排序把待确认草稿放在逾期和今日学习任务之前，使首页偏向 Agent 工程待办 | 固定为逾期、今日、到期复习、薄弱点、待处理助手确认 |
| 中高 | `apply_confirmed_draft` 只允许 accepted/rejected，不能持久化通用 later 状态 | 按动作合同展示按钮；“暂不处理”只能离开提示，不更新状态 |
| 中 | 原合同把所有技术信息全部折叠，削弱可控、可观察、可恢复的作品集表达 | Run 状态、模式、Guard 结果紧凑可见；原始 Tool I/O、Token、JSON 和完整时间线折叠 |

## 项目原生口径

```text
产品品牌：成长学习助手
项目定位：基于可控 Agent 的个人学习助手
核心业务对象：学习目标
Agent 功能模块：智能助手
可使用的交互描述：教练式建议
不得采用的替换命名：学习空间、学习教练、Workspace、Coach
```

借鉴 Open Notebook、AnythingLLM、Anki/Py-FSRS、RAGFlow、Khoj 和 Dify 时，只保留目标范围隔离、工具收缩、间隔复习、来源核对、确定性建议和运行可观察性，不复制导航数量、模块名称、产品角色或品牌表达。

## UX-01 纠偏合同

1. 页面标题和详情标题保持“学习目标”“目标详情”。
2. 目标详情保留资料、问答、测试、复习、进度五个快捷入口。
3. `selectedGoalId` 继续持久化并在刷新后从服务端重校验，只表示用户选中的学习目标。
4. 新增非持久化临时视图范围；只有目标快捷入口设置该范围，资料、复习和进度等直接主导航默认查看全部。
5. 临时范围必须显示“当前目标：名称”和“查看全部”；清除范围不能清除用户选中的学习目标。
6. 目标失效时同时清除目标选择和临时范围；不得回退到其他目标或用户数据。
7. 入口只允许读取、切换和聚焦，不创建 Run、不提交问答、不生成资料、不执行评级或写业务数据。

## 后续实施合同

### 导航

桌面继续使用 `today/goals/materials/study/agent/memory/progress` 七个视图，对应“今日、学习目标、资料、问答、智能助手、复习、进度”。移动端保留“今日、目标、资料、智能助手 + 更多”；“更多”继续提供问答、复习、进度和账号操作。

### 今日

认证后的首屏只请求并渲染 Dashboard。首屏完成后可读取 `GET /api/today/actions?limit=15`；该端点只返回逾期任务、今日任务、到期闪卡、未解决薄弱点和 `proposed` 助手草稿，不返回资料正文、chunks、完整 Agent Context 或历史时间线。

每类最多 3 条、总数最多 15 条，顺序固定为：逾期任务、今日任务、到期闪卡、未解决薄弱点、待处理助手确认。时间无效时排在类末尾，再以稳定 ID 收口。Dashboard 与行动区分别处理 loading/error/empty；行动区失败不能清空 Dashboard。

### 复习与智能助手

复习继续使用 Queue、Weak Points 和四档 Rating API；并发 `409` 只刷新、不重放评级，损坏调度不在客户端修复。

智能助手首层展示行动、原因、依据、Run 状态、模式和 Guard 结果。confirmed-draft 只允许接受/拒绝状态转换；暂不处理不写状态。Decision、Tool I/O、Token、fallback、Step 时间线和原始 JSON 保留在可展开技术详情中。

### 引用动作

“打开对应资料”和“继续提问”继续保留。两者必须校验 `goalId + materialId`，后者只预填输入框，不自动提交或触发 Provider；资料不存在时显示失效来源，不跳转到无关资料。

## 验收重点

- `UX-01`：双目标、五入口、显式范围、查看全部、直接导航显示全部、刷新重校验、失效目标清除、入口只读、1440px/390px 无溢出。
- `UX-02`：桌面七项和移动四项加“更多”均可访问；资料、问答、智能助手和账号操作可直接到达。
- `UX-03`：Dashboard 轻首屏、Today Actions 有界读取、五类稳定排序、局部失败、五类路由、Provider 0。
- `UX-04`：项目原生命名、动作合同匹配的按钮、紧凑运行证据、完整可展开技术详情、引用动作安全降级。
- 最终门禁：全量 pytest、Ruff、compileall、pip check、敏感扫描、PostgreSQL/pgvector、桌面/390px Playwright、axe 和 `git diff --check`。

## UX-01 纠偏验收结果

| 门禁 | 结果 |
|---|---|
| 前端语法 | `npm.cmd run check` 通过 |
| Playwright | `2 passed in 16.1s`；包含既有 Batch 4 黄金流程和纠偏后的 UX-01 |
| UX-01 浏览器断言 | 双目标、五入口、快捷入口临时范围、查看全部、直接导航显示全部、刷新重校验、失效选择清除、只读请求和 390px 无溢出全部通过 |
| 全量 Mock | `196 passed, 6 skipped in 133.17s` |
| Ruff | 通过 |
| compileall | 通过 |
| pip check | `No broken requirements found` |
| 敏感扫描 | 通过 |
| `git diff --check` | 通过 |
| PostgreSQL/pgvector | 本次仅前端和文档纠偏，未改后端、迁移或 FSRS，未重复运行；精确基线 `personal/main@9d2c59f` 已通过，第 3 周整体收口必须重跑 |

新截图为 `docs/images/ux01-goal-shortcuts-mobile.png`。原截图 `docs/images/ux01-learning-space-mobile.png` 保留为被替代实现的历史证据，没有覆盖或伪造。纠偏期间 Provider 请求、Token 和成本均为 `0`。

## 实施顺序

1. 纠偏 `UX-01` 并重新验收，未通过前保持未勾选。
2. `UX-03` 接入四档复习和有界 Today Actions，不调用完整 Agent Context。
3. `UX-04` 重排智能助手信息层级与引用动作，不改名、不放宽状态机。
4. `UX-02` 只修导航文案、选中状态和移动可达性，不隐藏资料与问答。
5. 完成全部离线门禁、截图和网络断言后更新任务书、当前状态与 PR 说明；推送、PR、合并和部署继续等待明确授权。

本次复核不授权数据库迁移、FSRS 参数调整、真实 Provider 评测、来源抽屉、相邻片段、PDF 查看器、第 4 周功能、推送、合并或部署。
