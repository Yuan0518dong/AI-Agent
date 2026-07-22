# CLOSE-03 固定角色验收报告

验收日期：2026-07-22

## 方法与边界

这不是用户研究。三个角色均由 Playwright 在隔离 SQLite、Mock LLM/Embedding 和新注册本地账户中执行，结果只代表固定夹具在当前代码基线的可复核行为。没有真实 Provider、远程账户、生产数据或外部用户参与。

命令：

```text
npx.cmd playwright test tests/browser/v7-close03.spec.cjs --config=tests/browser/playwright.v7-batch4.config.cjs
3 passed (18.1s)
```

新增角色后，完整浏览器回归 `npm.cmd run test:e2e` 为 `10 passed in 49.8s`，覆盖 Batch 4、CLOSE-02、CLOSE-03 与 UX-01 至 UX-04。

## 角色结果

| 角色 | 实际步骤与结果 | 截图 | 缺陷 |
|---|---|---|---|
| 首次使用者 | 注册后看到起步引导；创建目标和文本资料；在问答页显式生成来源片段；提问后显示资料引用 | `docs/images/close03-first-use-role.png` | P0=0，P1=0，P2=0 |
| 存在错题的学习者 | 提交错误答案；启动 `create_review_draft` 并接受；正式闪卡从 2 增至 3；对新卡点击“已掌握”后为 `reviewCount=1/lastRating=good/status=known`，Today 不再列出该卡 | `docs/images/close03-weak-answer-role.png` | P0=0，P1=0，P2=0 |
| 高风险确认/拒绝 | 形成等待确认的写入动作；“暂不处理”不发请求；恢复后“拒绝”未写入资料；取消终止 Run；Guard 状态为“未触发” | `docs/images/close03-high-risk-role.png` | P0=0，P1=0，P2=0 |

## 结论

三个固定角色在当前本地基线均得到可解释的结果：首次路径能找到资料依据，错题能进入确认后的 FSRS 闭环，高风险确认场景不会绕过用户决定写入正式内容。本轮没有需要修复的 P0 或时间盒内 P1。

下一项是 `CLOSE-04` 求职交付冻结，只统一已有证据、指标和讲解材料；不把固定夹具验收描述成真实用户数据，也不进行远程操作。
