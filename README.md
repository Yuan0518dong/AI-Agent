# AI-Agent

面向个人学习规划的可控学习智能体。项目将目标、资料摄取、带引用问答、错题/薄弱点、可确认的 Agent 运行、FSRS 复习与 Today Actions 串为一个可观察、可恢复的学习闭环。高风险写入必须经用户确认后才进入正式数据。

这是维护者实习期间唯一持续开发的项目，也是可公开展示的个人作品。第一、二版采用双人协作，第三版按方向分工，第四版起由维护者独立推进新增架构、工程化、评测和发布；详细边界见 [个人贡献说明](docs/portfolio/个人贡献说明.md)。

项目已完成求职交付收口并进入维护状态。`v7.1.0` 已合入 `personal/main`，完成 GitHub Release、Render 部署、健康检查、公开 Demo Smoke 和 Mock 黄金流程复验。当前对外指标、证据边界和冻结条件均以 [产品收口最终验收报告](docs/evaluation/产品收口最终验收报告.md) 为唯一汇总来源。

## 学习闭环

```text
学习目标 -> 资料 -> 引用问答 -> 错题/薄弱点 -> 复习草稿
-> 用户确认 -> FSRS 评级 -> Today 建议变化
```

```text
Browser (same-origin JavaScript)
  -> FastAPI API + database session / Origin guard / rate limits
  -> services: ingestion -> chunks -> keyword + dense + RRF -> cited QA
  -> Agent Runtime: decision -> Decision Guard -> tool -> confirmation -> recovery
  -> SQLite for local/test; PostgreSQL + pgvector for integration/production
```

详细架构与数据边界见 [架构与评测边界](docs/portfolio/架构与评测边界.md)。

## 当前交付证据

| 类别 | 当前结果 | 口径 |
|---|---:|---|
| 全量 Mock pytest | `200 passed, 6 skipped` | 系统回归，不是模型能力指标 |
| PostgreSQL/pgvector | `6 passed, 200 deselected` | 含 Alembic 往返 |
| 完整 Playwright | `10 passed` | 含桌面、390px、axe、黄金流程和三角色夹具 |
| 黄金流程 | 目标到 Today 变化可复核 | 用户确认不可绕过，FSRS `good` 后 Today 更新 |
| 固定离线 RAG | hybrid Recall@5=`0.94`；资料不足 F1=`0.8571` | Mock embedding 固定集，不是生产模型结论 |
| 历史真实 Provider | 60 Run；工具选择 `0.6333`、确认完整性 `0.5556` | 原始失败证据保留，不能宣传为稳定模型能力 |

每项的原始报告、fixture 边界、真实 Provider 用量和 corrected suite 的独立说明均在 [最终验收报告](docs/evaluation/产品收口最终验收报告.md) 中列出。Mock、固定离线、真实 Provider 与浏览器回归不能相互替代。

## 演示与材料

- 录屏：[91 秒本地视频](docs/videos/v7-batch4-90s-demo.webm) 和 [分镜/口播脚本](docs/portfolio/90秒演示脚本.md)。它使用隔离 SQLite 与 Mock Provider，不是实时真实模型演示。
- 在线 Demo：[ai-agent-v7-yuan0518dong.onrender.com](https://ai-agent-v7-yuan0518dong.onrender.com)。`SHIP-03` 已验证健康检查、公开 Demo Smoke 和 Mock 黄金流程；它仍只按 Mock Provider 演示表述，不代表在线真实模型能力。
- 求职材料：[简历 Bullet](docs/portfolio/简历材料.md)、[20 秒/1 分钟/3 分钟面试稿](docs/planning/AI-Agent简历与面试讲解稿.md)、[个人贡献边界](docs/portfolio/个人贡献说明.md)。

## 本地运行

前端与 API 由同一 Uvicorn 服务提供，保留同源 Cookie 会话。

```powershell
$env:EMBEDDING_PROVIDER = "mock"
$env:LLM_PROVIDER = "mock"
python -m pip install -r backend/requirements.txt
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8001
```

访问 `http://127.0.0.1:8001/`。常用本地检查：

```powershell
python -m pytest backend/tests -q --tb=short
npm.cmd run test:e2e
python backend/check_sensitive_content.py
```

## 限制与维护边界

- 真实 Provider 的历史固定集未达到稳定能力宣传门槛；Guard `1.0` 仅为受控注入拦截验证。
- 当前不包含 OCR、网页抓取、冲突资料自动裁决、多智能体、MCP、多模型比较、通知、长期记忆或个性化 FSRS。
- 后续只处理 P0 与时间盒内的黄金流程 P1。新增功能、真实 Provider 评测以及新的推送、PR、合并、部署或远程 Demo 操作均需独立任务和明确授权。
