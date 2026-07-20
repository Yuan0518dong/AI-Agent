# AI-Agent Backend

第七版后端基于 FastAPI、SQLAlchemy 与 Alembic，提供学习目标、资料摄取、带引用问答和可恢复多步 Agent Runtime。运行时将 Context、Decision、Guard、Tool 与 Observation 持久化，并对高风险写入执行确认、拒绝、取消和幂等保护。

## 核心能力

- 数据库 Cookie 会话、Origin 校验、限流和模型用量预算
- PDF、Markdown、TXT 内存式解析与来源定位
- keyword、dense 与 RRF 混合检索；PostgreSQL 使用 pgvector
- `AgentRun` / `AgentStep` 多步循环、Tool Registry 与 Decision Guard
- 高风险草稿确认恢复、写入幂等、取消互斥和安全回退
- 固定检索、问答、Agent 场景评测与真实 Provider 成本记录

本地和自动化测试默认使用 SQLite；生产部署使用 PostgreSQL + pgvector。生产数据库错误不会静默回退到 SQLite。

## 本地启动

从项目根目录执行：

```powershell
python -m pip install -r backend/requirements.txt
$env:LLM_PROVIDER="mock"
$env:EMBEDDING_PROVIDER="mock"
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8001
```

浏览器访问 `http://127.0.0.1:8001/`，API 文档位于 `http://127.0.0.1:8001/docs`。前端与 API 需要由同一个 Uvicorn 服务提供，以保留同源 Cookie 会话。

## 验证

```powershell
$env:LLM_PROVIDER="mock"
$env:EMBEDDING_PROVIDER="mock"
$env:LLM_ENV_FILE=".missing-v7-gate.env"
python -m pytest backend/tests -q --tb=short
python -m ruff check backend
python -m compileall -q backend
python backend/smoke_api.py
```

PostgreSQL、Playwright 和受限真实模型评测的口径与证据见根目录 [README](../README.md) 和 [架构与评测边界](../docs/portfolio/架构与评测边界.md)。真实模型评测必须显式配置 Provider 与成本预算，不能由默认测试命令触发。

