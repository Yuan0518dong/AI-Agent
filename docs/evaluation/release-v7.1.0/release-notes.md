# v7.1.0 Release Notes 草案

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

## 发布后待验证

- [ ] `personal/main` 指向合并后的 `v7.1.0` 提交。
- [ ] Reliability、PostgreSQL/pgvector 和 Playwright CI 全部通过。
- [ ] `v7.1.0` 标签与 GitHub Release 创建成功。
- [ ] Render 实际部署 commit 与标签一致。
- [ ] Public Demo Smoke 通过。
- [ ] Mock 公开主流程实际走通并记录结果。

上述项目只有观察到远程结果后才能勾选。本草案当前不构成发布成功声明。
