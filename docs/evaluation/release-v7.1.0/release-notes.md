# v7.1.0 Release Notes

## Highlights

- 完成“目标 -> 资料 -> 引用问答 -> 错题/薄弱点 -> 草稿确认 -> FSRS -> Today 变化”的学习闭环。
- Today Actions 使用有界、只读投影，不在首屏加载时生成 Agent Decision 或推进 Run。
- 智能助手首层优先显示当前行动、原因、依据和确认状态，技术 I/O 默认折叠。
- 桌面和移动导航统一文案、选中状态、键盘焦点与 ARIA。
- 增加黄金流程、三角色、桌面/390px 与 axe 自动化证据。

## Verification

- Mock pytest：`200 passed, 6 skipped`
- PostgreSQL/pgvector：`6 passed, 200 deselected`
- Playwright：`10 passed`
- Ruff、compileall、pip check、前端语法、敏感扫描和 diff check：通过

这些是系统工程门禁，不是纯模型能力指标。完整指标和不可比较边界见 [产品收口最终验收报告](../产品收口最终验收报告.md)。

## Known limits

- 公开 Demo 只使用 Mock Provider。
- 历史真实模型固定集未达到稳定能力宣传门槛。
- 冲突资料没有来源权重或自动裁决。
- 不支持 OCR、网页抓取、多智能体、MCP、通知或长期记忆。

## 发布验证

- [x] `personal/main` 的普通 merge commit [`09f6266`](https://github.com/Yuan0518dong/AI-Agent/commit/09f6266d1ffb32802106c92ec1a9370ea7e82f66) 合入 PR #6，父提交为 `9d2c59f` 与 `5b6f6a9`。
- [x] 主分支 CI [run 29898589032](https://github.com/Yuan0518dong/AI-Agent/actions/runs/29898589032) 的 Reliability checks、PostgreSQL pgvector integration 与 Playwright portfolio E2E 全部通过。
- [x] [`v7.1.0` 标签与 GitHub Release](https://github.com/Yuan0518dong/AI-Agent/releases/tag/v7.1.0) 已创建并精确指向 `09f6266`。
- [x] Render Deploy Hook 的部署 `dep-d9g7gubtqb8s73b65d9g` 已在服务 Events 中显示 `Live@09f6266`；后续公开 `https://ai-agent-v7-yuan0518dong.onrender.com/api/health` 实测 HTTP 200，响应 `status=ok`。
- [x] [Public Demo Smoke run 29902464916](https://github.com/Yuan0518dong/AI-Agent/actions/runs/29902464916) 成功，工作流 HEAD 为 `09f6266`。
- [x] 公开 Mock 黄金流程完成：Demo 账户创建 1 个目标、1 份资料和 1 个来源片段；`decisionMode=rule-based`，等待工具为 `create_task_draft`，确认后精确创建 1 个草稿；FSRS `good` 后 `reviewCount=1`，队列从 `2 -> 1`，Today 到期闪卡从 `2 -> 1`、行动项从 `5 -> 4`。全程没有 Provider 调用。

首次手工复核曾因核验脚本传入不存在的 `flashcardId` 得到 404；按 API 契约改用闪卡 `id` 后重跑通过。该记录是核验过程证据，不是产品回归。
