# CLOSE-01 一致性门禁验收报告

验收日期：2026-07-22

## 范围

`CLOSE-01` 只处理 `CLOSE-02` 黄金流程暴露的问题：确认写入后前端资料状态没有刷新。修复位于独立提交 `a786546`：仅在已接受的 `apply_confirmed_draft` 成功推进后调用既有资料读取，使用户可立即对新正式闪卡完成既有评级流程。

没有新增 API、数据库迁移、FSRS 参数、数据表、横向功能或真实 Provider 调用。审计确认既有测试已经覆盖本任务要求的后端风险，因此不为凑数量重写已有测试。

| 一致性主题 | 已有或新增证据 |
|---|---|
| 动作兼容、非空范围、Guard 脱敏 | `test_agent_reliability_rel.py` 覆盖历史动作归一化、`materialIds`、范围和脱敏分类；legacy/corrected 报告测试继续保留 A0/A2/A3 证据 |
| 确认、回滚与用户/目标隔离 | `test_agent_flow.py` 覆盖草稿确认、`apply_confirmed_draft`、同批回滚和跨用户/目标拒绝；`test_user_isolation.py` 覆盖账户边界 |
| SQLite FSRS 与 Today | `test_learning_loop.py` 覆盖四档评级、`fsrsCard/dueAt` 投影、兼容 `known/review/new`、损坏调度与并发冲突；`test_today_actions.py` 覆盖只读投影与类别路由 |
| PostgreSQL/pgvector 与迁移 | `test_postgres_integration.py` 覆盖 vector schema、FSRS 持久化和并发评级；本次实际运行 Alembic 往返 |
| 浏览器黄金路径 | `v7-close02.spec.cjs` 覆盖确认前零正式写入、接受后新卡、FSRS `good` 和 Today 移除，且验证 390px 与 axe |

## 结果

| 门禁 | 结果 |
|---|---|
| 目标后端回归 | `90 passed in 73.88s`：REL、评测保留、Agent 流程、FSRS、Today、用户隔离 |
| Alembic | 隔离 `pgvector/pgvector:pg16`，`upgrade head -> downgrade -1 -> upgrade head`，最终版本 `20260721_03` |
| PostgreSQL/pgvector | `6 passed, 200 deselected in 10.11s`，临时 `127.0.0.1:55432` 容器已停止 |
| 全量 Mock | `200 passed, 6 skipped in 137.83s` |
| 完整 Playwright | `7 passed in 34.0s`，含 Batch 4、UX-01 至 UX-04 与 CLOSE-02；所有小屏/axe 断言通过 |
| 静态与安全 | `npm.cmd run check`、Ruff、compileall、pip check、敏感扫描和 `git diff --check` 全部通过 |

## 失败与处理

本轮唯一产品 P1 是黄金流程首次运行发现的资料缓存陈旧，已由 `a786546` 修复并经定向和完整浏览器套件验证。文本资料的片段需要用户在已有问答页显式生成，是现有可见流程前置而非产品错误，已被固定在黄金流程中。没有 P0，未登记 P2。

## 结论与边界

`CLOSE-01` 通过。SQLite 与 PostgreSQL 路径、FSRS 状态投影、动作兼容、隔离和失败分类均可在当前本地提交基线复核。下一项仅为 `CLOSE-03` 固定三角色验收；不进行真实 Provider、推送、PR、合并、部署或远程 Demo 复验。
