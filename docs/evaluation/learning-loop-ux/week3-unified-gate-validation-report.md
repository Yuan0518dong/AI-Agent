# 第 3 周统一门禁验收报告

验收日期：2026-07-22

## 范围

本报告验证 `UX-01`、`UX-02`、`UX-03` 和 `UX-04` 在同一 `feature/learning-loop-ux` 本地基线共同运行。范围只包含学习闭环界面收口与其回归修复：不新增 API、数据库迁移、FSRS 参数、真实 Provider 调用、推送、PR、合并、部署或远程 Demo 操作。

测试一律强制 `LLM_PROVIDER=mock`、`EMBEDDING_PROVIDER=mock`，并使用不存在的本地环境文件隔离个人 Key。浏览器测试使用临时 SQLite 数据库；为了让同一隔离套件中的六个一键试用场景不触发生产默认的每 IP 5 次保护，Playwright 专用环境设置 `DEMO_IP_HOURLY_LIMIT=20`，不改变生产默认限流。

## 结果

| 门禁 | 命令或环境 | 结果 |
|---|---|---|
| 全量 Mock | `python -m pytest backend/tests -q --tb=short` | `200 passed, 6 skipped in 137.66s` |
| Ruff | `python -m ruff check backend` | 通过 |
| 编译 | `python -m compileall -q backend` | 通过 |
| 依赖 | `python -m pip check` | `No broken requirements found` |
| 敏感扫描 | `python backend/check_sensitive_content.py` | 通过 |
| PostgreSQL/pgvector | 一次性 `pgvector/pgvector:pg16` 容器，`127.0.0.1:55432`，`upgrade head -> downgrade -1 -> upgrade head` | `6 passed, 200 deselected in 2.47s`；迁移回到 `20260721_03` |
| 完整浏览器套件 | `npm.cmd run test:e2e` | `6 passed in 28.2s`，覆盖 Batch 4、UX-01、UX-02、UX-03（2 项）和 UX-04 |
| 可访问性与响应式 | Playwright 中 390px 宽度断言与 axe `wcag2a/wcag2aa` | 文档/页面无横向溢出，serious/critical 为 `0` |
| Diff | `git diff --check` | 通过 |

## 发现与修复

1. 第一轮完整 Playwright 发现“当前行动”和已展开的“运行详情”同时渲染相同的推进、确认和取消按钮。这个重复既让用户看到两套控制，也让测试选择器不唯一。已将用户操作固定在首层“当前行动”，运行详情只保留状态、Guard、时间线和技术 I/O；现有浏览器测试同步改为定位首层。
2. 第一轮完整 Playwright 的连续 Demo 登录超过了生产默认 `DEMO_IP_HOURLY_LIMIT=5`，后续测试收到 `429 rate_limited`。这不是产品流程失败；已只在隔离 Playwright 环境提高该变量至 `20`。第二轮完整套件全部通过。
3. `UX-04` 用例补充等待 `#app-shell` 完成登录渲染，避免在认证尚未完成时检查导航。`UX-03` 的 Today Actions 等待时间从 5 秒提高到 15 秒，以覆盖共享 Demo 数据下的异步读取。

上述均为第 3 周 P1 可用性或测试隔离问题；未发现 P0 数据、用户/目标隔离、确认写入、安全 Guard 或迁移回滚问题。

## 结论与边界

第 3 周总门禁通过。`UX-01` 的目标范围、`UX-02` 的导航语义、`UX-03` 的确定性 Today Actions 与 `UX-04` 的智能助手首层可在同一基线复核。浏览器测试继续断言不在加载时调用 Decision、Provider 或非 GET Run 接口；本轮没有真实 Provider 请求、Token 或成本。

本报告不替代 REL legacy/corrected、LOOP 或真实 Provider 原始报告，也不修改其 fixture、失败 Run 或指标。下一项仅进入 `CLOSE-02` 黄金流程审计与 E2E，不顺手实施数据库、FSRS、产品改名、通知、OCR、MCP、多模型或其他横向功能。
