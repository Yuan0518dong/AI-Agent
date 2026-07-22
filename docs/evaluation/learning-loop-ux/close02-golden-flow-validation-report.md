# CLOSE-02 黄金流程验收报告

验收日期：2026-07-22

## 范围与环境

本次只验证一条最小学习闭环，不增加产品功能：目标 -> 资料 -> 引用问答 -> 错题 -> 薄弱点 -> 复习草稿 -> 确认 -> 到期闪卡 -> FSRS 评级 -> Today 变化。

自动化使用 `v7-close02.spec.cjs`，在临时 SQLite、`LLM_PROVIDER=mock`、`EMBEDDING_PROVIDER=mock` 和不存在的本地环境文件下运行。测试通过注册全新本地账户建立夹具，不使用一键试用的种子数据，也不访问真实 Provider、远程服务或个人 Key。

## 固定流程与断言

| 环节 | 用户可见动作 | 关键数据或边界 |
|---|---|---|
| 目标与资料 | 创建一个学习目标和两句文本资料 | 资料整理出 2 个知识点和 2 张初始闪卡 |
| 引用问答 | 在问答页显式“生成片段”后提问 | 回答显示该资料的引用片段；不以无引用常识作答 |
| 错题与薄弱点 | 对目标范围内第一题提交“香蕉” | `isCorrect=false`，Today 出现该资料的 `weak_point` |
| 草稿与确认 | 启动 Agent，继续到“接受” | 首步是 `create_review_draft`；开始和等待确认阶段都不新增正式闪卡，Today 出现 `pending_confirmation` |
| 正式写入 | 点击“接受” | 正式闪卡数增加 1，新增卡为 `reviewCount=0`、`lastRating=null`，并出现在 Today 到期闪卡 |
| FSRS 与 Today | 对同一张新卡点击“已掌握” | 兼容状态接口映射为 FSRS `good`，响应为 `reviewCount=1`、`lastRating=good`、`status=known`；该卡从 Today 到期项移除 |
| 小屏与可访问性 | 切换 390px 今日页 | 无横向溢出，axe `wcag2a/wcag2aa` serious/critical 为 0；截图为 `docs/images/close02-golden-flow-mobile.png` |

## 结果

```text
npx.cmd playwright test v7-close02.spec.cjs --config=playwright.v7-batch4.config.cjs
1 passed (10.6s)
```

## 发现与处理

1. 文本资料的“完成”证据是知识点和整理状态，不使用上传资料的“完成”文本。测试已改为对应真实界面。
2. 文本资料不会自动生成可检索片段；黄金流程明确要求在问答页点击既有“生成片段”，然后才验证引用问答。没有新增自动处理或接口。
3. 首次流程验证发现：接受 `apply_confirmed_draft` 后后端已写入正式闪卡，但前端资料缓存未刷新，用户不能立即给新卡评级。该 P1 已在独立提交 `a786546` 中修复，只在接受该既有动作后调用既有资料读取；修复后同一 UI 流程无需重载页面即可评级。

## 结论与停止边界

`CLOSE-02` 通过。黄金流程同时证明用户确认不可绕过、Agent 写入落到已有 FSRS 数据模型、Today 是只读投影并随评级变化。本报告不替代或覆盖 REL、LOOP、A0/A2/A3、真实 Provider 的原始报告与失败证据。

下一项为 `CLOSE-01`：只补充该流程相关的跨数据库、迁移、隔离、兼容和失败分类回归，并完成工程门禁；不实施新 API、产品改名、技术栈迁移、真实 Provider、推送、PR、合并或部署。
