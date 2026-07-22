# UX-03 Today Actions 离线验收记录

日期：2026-07-22
分支：`feature/learning-loop-ux`
基线：`personal/main@9d2c59f`；UX-01 纠偏提交：`e0f1014`

## 范围

本次仅实施 `UX-03A` 至 `UX-03D`，没有实施 `UX-02`、`UX-04`、数据库迁移、FSRS 参数调整、真实 Provider 测评、推送、PR、合并或部署。

## 实现结果

- 新增只读 `GET /api/today/actions?limit=1..15`。它按固定类别顺序投影未完成的逾期任务、今日任务、到期闪卡、未解决薄弱点和 `proposed` 且具有目标归属的 Agent 草稿；每类最多 3 条，再按全局 limit 截断。
- 查询只依赖任务、复习队列、薄弱点与草稿存储。它不 import 或调用 Agent Context、Decision、Run 执行器或任何 Provider；响应不包含资料正文、chunks、Context、Decision、时间线或草稿 payload。
- 任务直接以 `tasks JOIN goals` 按用户过滤；薄弱点补入 `goalId`；草稿可按最早创建时间读取。路由可安全按 `goalId -> entity -> view -> focus` 定位任务、闪卡、测试题或 Run。
- 登录先完成既有 Dashboard 渲染，再以非持久化状态异步读取行动区。行动区 loading、empty、error、retry 独立；失败不会清空 Dashboard，也不会把旧缓存展示为当前结果。
- Today 日期切换只刷新 Dashboard 与 Today Actions，移除了该路径的完整 Agent Context 读取。五类“查看”入口只导航和聚焦，不会打卡、评级、确认、提问、创建/advance Run。
- 390px 截图：`docs/images/ux03-today-actions-mobile.png`。同时修复既有 Today 日期输入的可访问名称与提示文字对比度。

## 已通过的验证

| 门禁 | 结果 |
| --- | --- |
| Today Actions 专项 | `python -m pytest backend/tests/test_today_actions.py -q`：`4 passed` |
| 定向学习闭环回归 | `python -m pytest backend/tests/test_today_actions.py backend/tests/test_learning_loop.py -q`：`17 passed`（在新增上限 fixture 前执行；全量回归已包含最终 4 个 Today 专项） |
| 全量 Mock | `python -m pytest backend/tests -q --tb=short`：`200 passed, 6 skipped` |
| Ruff | `python -m ruff check backend`：通过 |
| 编译与依赖 | `python -m compileall -q backend`、`python -m pip check`：通过 |
| 前端与敏感扫描 | `npm.cmd run check`、`python backend/check_sensitive_content.py`：通过 |
| diff | `git diff --check`：通过 |
| UX-03 Playwright | `npx.cmd playwright test v7-ux03.spec.cjs --config tests/browser/playwright.v7-batch4.config.cjs`：`2 passed` |
| 完整浏览器套件 | `npx.cmd playwright test --config tests/browser/playwright.v7-batch4.config.cjs`：`4 passed`，含桌面、390px、axe serious/critical=0、无 page/非预期 console error |
| PostgreSQL/pgvector | 隔离 `pgvector/pgvector:pg16` 容器在 `127.0.0.1:55432` 完成 `upgrade -> downgrade -1 -> upgrade head`；`python -m pytest backend/tests -m postgres -q --tb=short`：`6 passed, 200 deselected` |

浏览器断言覆盖 Dashboard 独立失败/重试、认证后首屏无 `/api/agent/context`、`/api/agent/decide`、`/api/agent/ask`、Run advance 或 Provider 路径，以及五类行动的只读路由与实体聚焦。

## PostgreSQL/pgvector 环境记录

首次尝试时，Docker daemon 未运行，工作区 `backend/.env` 的旧 `POSTGRES_TEST_DATABASE_URL` 也在认证阶段失败；该尝试没有执行迁移或写入。随后发现 Docker Desktop 安装在本机开发目录并启动本地 Linux engine，使用独立、自动删除的 `pgvector/pgvector:pg16` 容器与端口 `55432` 完成迁移回滚和标记集。容器不连接 Neon、Render 或生产数据。

## Provider 与历史证据

Provider 请求、Token 与成本均为 `0`。本记录不改写 REL 的 A0/A2/A3、legacy/corrected 或任何既有失败证据。
