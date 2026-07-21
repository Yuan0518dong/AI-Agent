# 第 3 周学习闭环 UX 实施前评估

评估日期：2026-07-21

评估结论：**实施前评估通过；`UX-01` 已完成本地验收，`UX-02` 至 `UX-04` 仍未开始。**

## 基线与授权边界

- 目标仓库为 `Yuan0518dong/AI-Agent`。PR #5 `feature/learning-loop -> main` 已于 2026-07-21 合并，merge commit 为 `9d2c59f7ac71ec614bf71561d64fc6ab35ed1caf`。
- `personal/main@9d2c59f` 的 GitHub Actions run `29807141471` 已通过 Reliability、PostgreSQL/pgvector（含最新迁移回滚）和 Playwright。
- 本地 `git fetch personal main` 两次因 `Recv failure: Connection was reset` 失败；没有以旧分支近似替代。GitHub API 返回的已验证 commit payload、PGP signature、父提交和 tree 被本地重建并先计算 SHA，只有结果精确匹配 `9d2c59f` 后才写入对象、更新 `personal/main` 跟踪引用并新建 `feature/learning-loop-ux`。
- `UX-01` 已在 `feature/learning-loop-ux` 实施并提交为 `e4b251e`；没有推送、PR、合并或部署。后端、数据库迁移、FSRS 参数和真实 Provider 均未改动。

## UX-01 实施记录

- 学习空间保留 `goals` 视图 ID 和既有目标详情，只把页面标题、内容标题和空态改为学习空间语义；七项主导航未改，避免提前进入 `UX-02`。
- 当前目标详情新增资料、问答、测试、复习、进度五个快捷入口。入口固定执行“校验目标 -> 保留 `selectedGoalId` -> 加载 -> 切换既有视图 -> 聚焦”的顺序；不创建 Agent Run、不提交问答、不生成资料，也不写入业务数据。
- 资料、问答摘要、闪卡、测试和进度均按 `selectedGoalId` 过滤。会话恢复时保留选择值但清空远端视图加载标记，下一次打开学习空间必定从服务端重校验；目标无效时清除选择并显示重新选择空态。
- 新增 `tests/browser/v7-ux01.spec.cjs`，使用两个目标与两份资料验证范围隔离、五入口、导航只读、刷新保持、失效选择和 390px 文档宽度。`npm.cmd run test:e2e` 为 `2 passed`，`python -m pytest backend/tests -q --tb=short`（Mock）为 `196 passed, 6 skipped in 137.35s`；Ruff、compileall、pip check、敏感扫描、前端语法与 `git diff --check` 均通过。
- 移动截图为 `docs/images/ux01-learning-space-mobile.png`，已人工检查五个入口完整可见且无横向溢出。PostgreSQL/pgvector 未在此仅前端任务重跑，仍以 `9d2c59f` 主分支的已通过 CI 为基线；第 3 周整体收口时必须重新运行。

## 当前架构结论

| 能力 | 当前事实 | 评估 |
|---|---|---|
| 导航 | 桌面 7 项；移动 4 项加“更多”，内部视图为 `today/goals/materials/study/agent/memory/progress` | 可保留视图 ID，只重组五项主导航，风险可控 |
| 目标状态 | `selectedGoalId` 已写入本地 state；目标、资料、Agent 都会读取它 | 有复用基础，但跨视图入口缺少统一的范围与聚焦顺序 |
| 首屏 | 登录后只请求 Dashboard；目标、资料、Agent 通过 `ensureViewData` 延迟加载 | 已满足轻首屏，需要为今日多来源数据增加独立降级 |
| Agent | `POST /agent/decide` 只由显式生成触发；进入 Agent 页只 GET Context/ActionLog/Run | 零 Provider 加载可保留，必须用自动化断言锁定 |
| 今日数据 | Dashboard 只有摘要和今日任务；Agent Context 已有逾期、资料不足和部分复习上下文 | 无需新 Workspace API，可组合既有只读端点 |
| 复习 | 后端已有 Queue、Weak Points 和四档 Rating；前端 API client 未暴露，界面仍调用两档兼容 PATCH | 第 3 周必须接入新 API，并处理并发冲突 |
| 学习教练 | Run、Decision、Guard、Tool、Token 和 fallback 已有；主要内容整体藏在“运行详情”内 | 数据够用，需重新分层而非重写 Runtime |
| 引用 | 已显示资料名、页码/标题路径、原文和分数 | 只缺两个范围安全的导航动作 |
| 浏览器测试 | Batch 4 覆盖 Demo、目标、PDF、引用、确认/拒绝/取消、390px 和 axe | 未覆盖五项导航、今日排序、FSRS 四档、并发 409 和零 Provider 初始化 |

## 必须先补齐的合同

### 1. 视图和状态

主导航映射固定为 `今日=today`、`学习空间=goals`、`学习教练=agent`、`复习=memory`、`进度=progress`。`materials/study` 继续存在，但只能作为学习空间、今日项和引用动作的上下文目的地。

跨视图动作必须通过一个统一入口完成：验证目标归属并设置 `selectedGoalId`，加载目标相关数据，切换现有视图，最后按 material/run/task/quiz/flashcard ID 聚焦。不能先渲染旧目标再异步切范围，也不能在目标失效时静默选中其他目标。

### 2. 今日页数据和排序

不创建大型聚合接口。计划使用以下现有读取：

| 数据 | 读取来源 | 使用字段 |
|---|---|---|
| 摘要、今日任务 | `GET /api/dashboard?date=...` | `summary/todayTasks/primaryGoal` |
| 逾期任务、资料不足 | `GET /api/agent/context` | `tasks[].overdueItems/qa.insufficiencies` |
| 待确认草稿 | `GET /api/agent/drafts?status=proposed&limit=20` | `id/goalId/runId/draftType/createdAt` |
| 到期闪卡 | `GET /api/review/queue?limit=100` | `flashcardId/materialId/goalId/dueAt` |
| 未解决薄弱点 | `GET /api/review/weak-points` | `quizId/materialId/latestAttemptAt/resolved` |

各请求独立 loading/error/empty，使用等价于 `Promise.allSettled` 的组合方式。成功数据不能因另一来源失败而消失；重试只重读失败来源。输入先过滤已完成任务、非 `proposed` 草稿、未来卡和已解决薄弱点，再按任务书中的六级优先顺序与 tie-break 排序。每类最多 3 条，总数最多 18 条。

### 3. 路由矩阵

| 来源 | 目的地 | 必须携带 | 不得发生 |
|---|---|---|---|
| 待确认草稿 | 学习教练 | `goalId + runId` | 自动接受、拒绝或 advance |
| 逾期/今日任务 | 学习空间 | `goalId + taskId` | 自动打卡或重排 |
| 到期闪卡 | 复习 | `goalId + flashcardId` | 自动评级 |
| 薄弱点 | 复习中的测试题 | `goalId + materialId + quizId` | 重新生成有历史的题目 |
| 资料不足 | 继续提问 | `goalId + materialId + 原问题` | 自动提交问答或生成资料 |
| 打开对应资料 | 资料 | `goalId + materialId` | 打开来源抽屉或伪造 PDF 查看 |

### 4. 复习冲突和学习教练反馈

新复习界面只调用四档 Rating API。提交时锁定四个评级按钮；成功后合并返回的调度投影并重新读取队列。`flashcard_review_conflict` 表示当前显示已过期，只刷新，不自动重放用户评级；`flashcard_schedule_invalid` 不做客户端修复。

学习教练首层展示选中 Run 最新 Step 的行动、原因、依据与反馈。技术元数据继续存在，但默认折叠。“稍后”是安全暂停：对待确认写入不执行、不确认、不拒绝，保持 `proposed/waiting_confirmation`，因此可以在今日页再次找到；不能为了凑齐三个按钮而放宽 confirmed-draft 状态机。

### 5. Provider 0 的证明方式

“没有点击生成”不等于已经证明零调用。验收必须同时具备：

1. 后端 Provider spy：认证完成后读取 Dashboard、Agent Context、Drafts、Review Queue 和 Weak Points，调用数仍为 0。
2. Playwright 网络记录：Demo 登录完成后的今日加载、刷新和五项导航期间，没有 `/agent/decide`、`/agent/ask`、Run create/advance 或其他生成类请求；允许认证和明确列出的 GET。
3. 确定性测试：同一 fixture 多次乱序输入仍产生完全相同的今日列表，不借助 LLM 补全标题、原因或排序。

## 风险与处理

| 等级 | 风险 | 处理 |
|---|---|---|
| 高 | 在已合并旧分支继续开发，导致 PR 基线和 CI 证据混乱 | 从 `personal/main@9d2c59f` 新建独立 UX 分支 |
| 高 | 今日加载隐式触发 Agent/Provider | 只读端点白名单、Provider spy、Playwright 网络断言三重锁定 |
| 高 | 四档评级并发覆盖或自动重试造成重复学习记录 | 409 只刷新不重放，后端条件更新保持不变 |
| 中 | 改成五项导航后资料、问答、账号操作不可达 | 保留上下文入口和独立账号工具入口，并纳入桌面/移动 E2E |
| 中 | `selectedGoalId` 与延迟加载竞态导致串目标 | 统一导航入口按范围、加载、视图、聚焦顺序执行 |
| 中 | 一个读取失败使整个今日页空白 | 分来源状态和局部重试，禁止全页 catch 覆盖成功数据 |
| 中 | “稍后”被误实现为接受或拒绝 | 断言刷新后仍为 pending，且正式实体计数不变 |
| 低 | 技术详情搬动时丢失排查信息 | 保留现有快照字段并测试默认关闭、展开完整 |

## 实施顺序

1. Preflight：同步 `personal/main@9d2c59f`，新建 `feature/learning-loop-ux`，核对干净工作区、现有 API、测试命令与无迁移要求。
2. `UX-01`：先建立统一目标范围导航，改名学习空间并补五个快捷入口；验证刷新保持和失效目标。
3. `UX-02`：收敛桌面/移动五项主导航，保留资料、问答和账号操作的上下文入口；完成 1440px/390px 导航断言。
4. `UX-03`：接入 Review API，完成四档评级与 409；实现纯确定性 Today composer、局部失败和六类路由；加入 Provider 0 断言。
5. `UX-04`：重排学习教练首层信息和安全的稍后语义；增加引用的打开资料/继续提问；技术详情保持折叠可核对。
6. 收口：运行定向测试和全部门禁，保存桌面/390px 截图、axe、网络请求清单和失败证据，更新任务书/当前状态/UX 评估报告与新 PR 说明。

## 验收门

只有同时满足下列条件才可勾选第 3 周：

- `UX-01` 至 `UX-04` 的验收矩阵全部通过，且没有以静态文案代替真实路由或状态变化。
- 全量 pytest、Ruff、compileall、pip check、敏感扫描、PostgreSQL/pgvector、桌面/390px Playwright、axe 和 `git diff --check` 全部通过。
- 页面初始化 Provider 调用为 0；没有真实 Provider 评测，也不根据 Mock 宣称模型指标变化。
- 没有数据库迁移、FSRS 参数调整、大型 Workspace API、来源抽屉、相邻片段、PDF 查看器、第 4 周功能或 Render 部署。
- UX 实现形成独立提交和独立 PR；合并与部署继续等待用户明确授权。

评估后不存在需要扩大范围解决的阻塞。下一步应只从同步后的主分支启动 `UX-01`，而不是同时改四个页面。
