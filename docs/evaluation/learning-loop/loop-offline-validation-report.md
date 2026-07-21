# LOOP 离线与数据库验收报告

日期：2026-07-21
分支：`feature/learning-loop`
基线：`d12f00c`（`personal/main`，PR #4 合并提交）
实现提交：`4637833`

## 范围与停止边界

本报告只覆盖 `LOOP-01` 至 `LOOP-06`：FSRS 调度、SQLite/PostgreSQL schema、复习队列和评级、弱项派生、测验历史保护及 Agent Context 回读。没有实现 UX、产品页面、数据库以外的部署改动或第 3 周任务。

本轮没有调用真实 Provider：请求数、prompt Token、completion Token 和成本均为 `0`。这不是 Agent 模型评测，不能替代或改写 `docs/evaluation/agent-reliability-*` 中的 A0/A2/A3、legacy 或 corrected 证据。

## 已验证不变量

- `fsrs==6.3.1`（MIT），固定 `desired_retention=0.9`、`maximum_interval=365`、`enable_fuzzing=false` 和 UTC。
- `fsrs_card` 为 JSON 文本事实来源；`due_at` 为索引投影。创建、四档评级与旧状态兼容均在同一事务写入 `status/fsrs_card/due_at/review_count/last_rating`，并验证 `dueAt == Card.from_json(fsrsCard).due`。
- SQLite 旧卡与 PostgreSQL 迁移中的旧卡均统一为立即到期、`new`、`review_count=0`，不从旧 status 推断虚构复习历史。
- 资料批量生成、手工创建、Agent review draft 正式确认、Demo 和旧状态 API 均经统一调度服务；账户导出保留调度字段。`retrievability` 仅在读取响应中计算，不落库。
- 损坏 `fsrs_card` 返回 `409 flashcard_schedule_invalid`，不重置或覆盖原状态；`known -> Good`、`review -> Again`，已复习卡请求 `new` 返回 `409 flashcard_review_history_exists`。
- 薄弱点仅由 `quiz_attempts` 按 `quizId` 派生。已有 attempts 后的 quiz 重新生成返回 `409 quiz_history_exists`，题目和全部 attempts 均保留；后续正确且分数不低于 70 会将该弱项标记为已解决。
- Agent Context 读取到期卡和未解决薄弱点；复习草稿仍通过原确认状态机写入正式闪卡，没有 Agent 创建的测试题草稿。

## 自动化结果

| 验证 | 结果 |
| --- | --- |
| LOOP 专项 + Agent 确认写入回归 | 通过：`11 passed` |
| 资料流程回归 | 通过：`5 passed` |
| 全量 Mock `python -m pytest backend/tests -q --tb=short` | 通过：`193 passed, 5 skipped` |
| PostgreSQL/pgvector | 通过：隔离容器升级 `20260716_01 -> 20260717_02 -> 20260721_03` 后，`backend/tests/test_postgres_integration.py` 为 `5 passed` |
| 前端语法与 Playwright | 通过：`npm.cmd run check`；Batch 4 桌面/390px/axe 为 `1 passed` |
| Ruff、compileall、pip check、敏感扫描、`git diff --check` | 通过 |

本机原 `backend/.env` 指向的 PostgreSQL 测试连接被服务端拒绝认证，且 5432 已由其他工作区容器占用；为避免触碰该数据库，验证改用独立、临时的 pgvector 容器和独立端口。连接信息未写入仓库。本机 CI 同样使用独立 pgvector 服务，因此该替代保持测试拓扑一致。

所有静态、安全和 diff 门禁已在提交前复跑通过。
