# v7.1.0 PR 说明草案

建议标题：

```text
release: publish v7.1 learning loop closeout
```

## Summary

- 将学习目标、资料、引用问答、错题/薄弱点、确认草稿、FSRS 复习与 Today Actions 串成可复现黄金流程。
- 收敛智能助手首层和桌面/移动导航语义，不改路由结构或加载时调用模型。
- 增加 Today Actions 只读投影、黄金流程和三个固定角色的浏览器证据。
- 统一 README、简历、面试稿和评测指标来源，准备 `v7.1.0` 发布。

## Scope

PR 基于 `personal/main@9d2c59f`，合入 `feature/learning-loop-ux` 的 14 个收口提交及一个本地发布准备提交。范围不包含产品改名、新 API 横向能力、数据库迁移、FSRS 参数调整、真实 Provider 复跑、OCR、MCP、多智能体、通知、长期记忆或 UI 框架迁移。

## Validation

- Mock pytest：`200 passed, 6 skipped`
- PostgreSQL/pgvector：`6 passed, 200 deselected`
- Alembic：`upgrade head -> downgrade -1 -> upgrade head`，最终 `20260721_03`
- Playwright：`10 passed`
- Ruff、compileall、pip check、前端语法、敏感扫描和 diff check：通过

完整命令、耗时与隔离环境见 [SHIP-01 发布审计](ship01-release-audit.md)。

## Evidence boundaries

- 浏览器和全量 pytest 使用 Mock Provider，不能替代真实模型结论。
- 历史 A0 真实固定集的工具选择为 `0.6333`、确认完整性为 `0.5556`；失败 Run 保持原样。
- REL corrected 使用不同 fixture，含 Runtime 确定性 Decision 和本地事务夹具，不接入 A0/A2/A3 同一提升曲线。
- Guard `1.0` 来自受控非法输出注入，只验证拦截链路。
- 三个固定角色是自动化自测，不是外部用户研究。

统一口径见 [产品收口最终验收报告](../产品收口最终验收报告.md)。

## Remote boundary

本 PR 草案不代表已经推送、创建 PR、合并、发布或部署。远程步骤必须在实际观察 CI 和部署结果后逐项更新，失败不得删除或改写。
