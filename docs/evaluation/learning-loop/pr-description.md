# Learning Loop PR 说明（待创建）

## 目的

完成第 2 周 `LOOP-01` 至 `LOOP-06`：让既有闪卡和测试链路具备可审计的 FSRS 间隔复习、错题保护与 Agent Context 回读，而不扩张到 UX、部署或新的模型评测。

## 变更摘要

- 新增 `fsrs==6.3.1` 与统一 `Flashcard Review Service`；全部闪卡创建入口产生完整 UTC 调度状态。
- 新增 PostgreSQL Alembic `20260721_03` 及 SQLite 兼容迁移：`fsrs_card`、`due_at`、`last_reviewed_at`、`review_count`、`last_rating`、到期索引。
- 新增 `GET /api/review/queue`、`GET /api/review/weak-points` 和 `POST /api/materials/{material_id}/flashcards/{flashcard_id}/reviews`。
- 保持历史 PATCH 状态接口：`known -> Good`、`review -> Again`；只允许未复习卡幂等保持 `new`。
- 按 `quizId` 从 attempts 派生弱项，阻止含历史的 quiz 重新生成；Agent Context 读取到期卡和未解决弱项，但 review draft 仍须确认。

## 安全与数据不变量

- `fsrs_card` 是调度事实来源，`due_at` 必须等于其 `Card.due`；相关字段在一个事务中成功或回滚。
- 损坏 FSRS JSON 返回 `409 flashcard_schedule_invalid`，不静默重置历史。
- 旧卡不依据旧 status 伪造历史，统一转为立即到期、未复习。
- 不增加弱项表、不提供破坏性 reset，不删除已有 quiz attempts。
- 不修改 REL 的动作契约、legacy/corrected 报告或 A0/A2/A3 原始证据。

## 验证

- 全量 Mock：`193 passed, 5 skipped`
- 隔离 PostgreSQL/pgvector：`5 passed`，已验证 `20260721_03`
- Playwright（桌面、390px、axe）：`1 passed`
- 本轮没有真实 Provider 请求、Token 或成本。

## 非目标

不包含产品界面改动、部署/Render、PR 合并、第 3 周 UX、FSRS 参数个性化训练或新的真实 Provider 评测。
