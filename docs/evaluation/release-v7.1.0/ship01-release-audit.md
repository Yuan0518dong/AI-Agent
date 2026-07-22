# v7.1.0 SHIP-01 本地发布审计报告

审计日期：2026-07-22

## 基线与范围

| 项目 | 结果 |
|---|---|
| 当前分支 | `feature/learning-loop-ux` |
| 审计起点 | `9f9a509` |
| 合并目标 | `personal/main@9d2c59f` |
| 起点差异 | 当前分支领先 `14` 个提交，落后 `0` 个提交 |
| 变更规模 | `52 files changed, 3018 insertions, 225 deletions` |
| 发布版本 | `7.1.0` |

14 个既有提交按顺序覆盖：学习目标快捷入口及命名纠偏、Today Actions、产品收口计划、智能助手首层、导航语义、第 3 周门禁、确认后缓存刷新、黄金流程、一致性门禁、三角色验收和最终材料冻结。发布准备只增加版本元数据与发布文档，不新增业务行为。

差异审计确认变更位于现有边界内：原生 JavaScript 前端、FastAPI Today 只读投影、既有 Agent 草稿确认后的缓存刷新、测试、截图和文档。没有 OCR、MCP、多智能体、通知、长期记忆、UI 框架迁移、新数据库迁移、FSRS 参数调整或新真实 Provider 调用。

## 本地发布门禁

所有 Provider 相关测试均强制 `LLM_PROVIDER=mock`、`EMBEDDING_PROVIDER=mock`，并使用不存在的环境文件隔离本地凭据。

| 门禁 | 结果 |
|---|---|
| 全量 Mock pytest | `200 passed, 6 skipped in 141.27s` |
| Ruff | `All checks passed` |
| compileall | 通过 |
| pip check | `No broken requirements found` |
| 前端语法 | `npm.cmd run check` 通过 |
| 敏感扫描 | `Sensitive-content scan passed for repository text files` |
| 差异空白检查 | `personal/main...HEAD` 与当前工作区均通过 |
| Alembic | `upgrade head -> downgrade -1 -> upgrade head`，最终 `20260721_03` |
| PostgreSQL/pgvector | 独立 `pgvector/pgvector:pg16` 容器，`6 passed, 200 deselected in 2.34s` |
| 完整 Playwright | `10 passed in 49.6s` |

Playwright 覆盖 Batch 4、黄金流程、三角色、UX-01 至 UX-04、桌面、390px 和 axe。测试生成的已跟踪截图变化属于浏览器重录漂移，审计后已恢复，不纳入发布准备提交。一次性 PostgreSQL 容器已停止。

## 缺陷与结论

- P0：`0`
- 阻断发布的 P1：`0`
- P2：不进入本次版本

`SHIP-01` 本地发布门通过。当前候选可进入 `SHIP-02`，但推送、创建 PR、合并、标签、Release、部署和远程 Demo 复验均尚未执行，继续分别等待明确授权。

本报告只记录工程发布门禁。Mock、历史 A0/A2/A3、REL corrected、Guard 注入和用户自测的指标边界仍以 [产品收口最终验收报告](../产品收口最终验收报告.md) 为唯一汇总来源。
