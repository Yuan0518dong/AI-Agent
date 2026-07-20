# AI-Agent

面向个人学习规划的可控学习智能体。项目把目标、资料摄取、带引用问答和可确认的 Agent 运行串成一个可观察的学习闭环；高风险写入必须经用户确认后才会进入正式任务或闪卡。

在线 Demo：[ai-agent-v7-yuan0518dong.onrender.com](https://ai-agent-v7-yuan0518dong.onrender.com)。Render Free 服务闲置 15 分钟后可能休眠，首次访问可能需要约 1 分钟唤醒。公开 Demo 刻意使用 Mock Provider，绝不把它表述为真实模型演示。

90 秒演示材料：[91 秒本地录屏](docs/videos/v7-batch4-90s-demo.webm) 与 [分镜/口播脚本](docs/portfolio/90秒演示脚本.md)。录屏使用隔离 SQLite 与 Mock Provider，展示 Demo、目标、PDF、引用问答、确认恢复和移动端；不把它表述为真实模型视频。

## 架构

```text
Browser (same-origin JavaScript)
  -> FastAPI API + database session / Origin guard / rate limits
  -> services: ingestion -> chunks -> keyword + dense + RRF -> cited QA
  -> Agent Runtime: decision -> Decision Guard -> tool -> confirmation -> recovery
  -> SQLite for local/test; Neon PostgreSQL + pgvector for production
```

详细边界见 [架构与评测说明](docs/portfolio/架构与评测边界.md)。

## 已测指标

以下记录区分固定中文集的离线 Mock 结果与独立执行的受限 DeepSeek Agent 评测；两者均不是完整生产模型结论：

| 评测 | 结果 | 证据 |
|---|---:|---|
| 检索集 | 10 份资料、50 条中文查询 | [固定数据集](backend/evaluation/v7_retrieval_cases.json) |
| hybrid Recall@5 | 0.94 | [检索报告](docs/evaluation/第七版Batch4检索评测报告.json) |
| keyword / dense Recall@5 | 0.94 / 0.28 | 同上 |
| 问答集 | 32 条，四类覆盖 | [问答报告](docs/evaluation/第七版Batch4问答评测报告.json) |
| 资料不足 F1 | 0.8571 | 同上；[初始失败与修复记录](docs/evaluation/第七版Batch4资料不足修复记录.md) |
| Agent Mock 回归 | 20/20 通过；工具选择、Guard、确认完整性、恢复均为 1.0 | [Agent 报告](docs/evaluation/第七版Batch4AgentMock评测报告.json) |
| Agent 真实评测 | 20 场景 x 3，60 Run；工具选择 0.6333、确认完整性 0.5556、恢复 1.0 | [真实报告](docs/evaluation/第七版Batch4Agent真实模型评测报告.json) |
| Batch 4 Playwright | 1 passed；桌面与 390px、axe serious/critical=0、页面异常=0 | [移动端截图](docs/images/v7-batch4-mobile-e2e.png) |

受授权的 DeepSeek Agent 评测已完成：20 个固定场景各运行 3 次，共 60 个 Run、107 次 Provider 请求；prompt/completion Token 为 `237971/33611`，按 2026-07-20 公开 cache-miss 费率估算 `$0.042727`。工具选择成功率仅 `0.6333`、确认完整性仅 `0.5556`，有 22 个 Run 未满足场景断言、84 次安全回退，因此不能把这次运行宣传为完整 Agent 成功结论。恢复成功率为 `1.0`，p50/p95 延迟为 `5781/9750 ms`。Guard `1.0` 是真实 Provider 响应后的固定非法输出注入验证，不是模型自然非法输出率；详见 [真实报告](docs/evaluation/第七版Batch4Agent真实模型评测报告.md) 与 [预算报告](docs/evaluation/第七版Batch4真实模型预算报告.json)。

## 快速启动

```powershell
python -m pip install -r backend/requirements.txt
$env:LLM_PROVIDER="mock"
$env:EMBEDDING_PROVIDER="mock"
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8001
```

访问 `http://127.0.0.1:8001/`。前端与 API 必须由同一 Uvicorn 服务提供，以保留同源 Cookie 会话。

离线 Batch 4 评测和浏览器验收：

```powershell
python backend/evaluate_batch4.py
npm ci
npm run test:e2e
npm run record:batch4-demo
```

## 限制

- Mock dense 基线 Recall@5 为 0.28，明显低于 keyword/hybrid；资料不足初始误召回已修复并保留失败样例记录。
- 冲突资料当前只评估引用范围，不自动裁决资料之间的冲突或优先级。
- 真实 DeepSeek 20 x 3 评测已完成，但工具选择为 0.6333、确认完整性为 0.5556，且 22 个 Run 未满足断言；Mock 的 1.0 不代表真实模型表现。
- Guard 召回 1.0 来自受控非法输出注入；它不衡量真实模型自然产生无效决策的概率。90 秒录屏仍使用 Mock Provider，不是实时真实模型演示。
- 公开服务依赖 Render/Neon 免费层，求职季前需重新核对其额度和政策。

## 交付材料

- [个人贡献说明](docs/portfolio/个人贡献说明.md)
- [简历材料](docs/portfolio/简历材料.md)
- [Batch 4 离线评测报告](docs/evaluation/第七版Batch4离线评测报告.md)
- [Batch 4 验收记录](docs/status/第七版Batch4验收记录.md)
