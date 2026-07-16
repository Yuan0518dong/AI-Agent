# 第七版 Batch 1 本地验收记录

验收日期：2026-07-16

## 状态

本记录描述已经获得的本地、浏览器、真实 Neon、GitHub Actions 和公开 Render 证据。Batch 1 尚未完成最终验收，当前不得创建 Batch 2 分支；尚未完成的 Render 重启持久化、默认分支公开 smoke 和求职季政策复核不得写成已完成。

## 已验证需求

- `AUTH-01`：`ai_agent_session` 使用 32-byte 随机不透明令牌；数据库仅保存 SHA-256 哈希。注册、登录和试用响应设置 `HttpOnly`、`SameSite=Lax` Cookie，生产环境设置 `Secure`。
- `AUTH-02`：`GET /api/auth/me` 与 `POST /api/auth/logout` 已实现；所有业务路由依赖 Cookie 会话，未登录返回统一的 `401` 错误包络和 `requestId`。
- `AUTH-03`：新密码为 Argon2id；旧 PBKDF2 账号成功登录后原地重哈希。前端删除 `X-User-Id`、令牌和可信用户 ID 的存储。
- `AUTH-04`：隔离 Neon `batch1-test` 分支实际执行的 PostgreSQL 测试覆盖注册、登录和 Demo IP 限流的 `429` 包络、受控 Provider 的 `/api/agent/ask` 首次成功/第二次 `429`、以及并发额度预留只有一条成功。
- `DEMO-01`：`POST /api/auth/demo` 在一个事务中建立隔离 Demo 用户和 24 小时会话，写入 1 个目标、3 个任务、1 份已处理资料、闪卡、测试题及一个 `waiting_confirmation` Run，不调用模型。
- `DEMO-02`：Demo 默认每日 10 次 LLM 调用、100 个 chunk embedding；首笔超额预留会被原子拒绝。真实 OpenAI-compatible LLM/embedding HTTP 调用在 Provider 边界计量，工具线程复制调用上下文。
- `DEPLOY-01`、`DEPLOY-02`：前端请求固定为同源 `/api`；CORS 使用显式列表，`*` 被拒绝，生产写请求要求允许的 Origin。错误均包含类型、用户消息、字段错误和 `requestId`。
- `DEPLOY-04`：README、登录页和部署说明都提示 Render 免费 Web 服务闲置 15 分钟后可能休眠，首次访问可能需要约 1 分钟唤醒。
- `DB-01`：隔离 Neon 测试分支与生产 Neon 分支均通过 Alembic `20260716_01` 迁移；生产直连已实际读取 `vector` 扩展和 `users` 表，生产池化 URL 也可读取 schema。
- `DB-02`：GitHub Actions [run 29485625666](https://github.com/Yuan0518dong/AI-Agent/actions/runs/29485625666) 成功；其中 `PostgreSQL pgvector integration` job 在 `pgvector/pgvector:pg16` 服务中执行 Alembic 并通过 `3 passed, 117 deselected`，Reliability job 也通过 Mock 全量门禁、语法与提交范围空白检查。生产代码在 `APP_ENV=production` 下拒绝缺失、非 Neon 或非池化的运行连接；公开服务的 Demo 数据读写已实际经过该配置。
- `OPS-02`：2026-07-16 已完成求职季前平台政策复核，结论记录在本文件的“平台政策复核”部分；后续每次求职季开始前仍须重新执行。

## 本地证据

在以下隔离 Mock 环境执行：

```powershell
$env:LLM_PROVIDER="mock"
$env:EMBEDDING_PROVIDER="mock"
$env:LLM_ENV_FILE=".missing-v7-gate.env"
python -m pytest backend/tests -q --tb=short --basetemp .test_artifacts\pytest-v7-batch1-neon-local-final
python -m compileall -q backend
python -m pip check
node --check app/api.js
node --check app/app.js
node --check app/modules/agent-workbench.js
node --check app/modules/utils.js
python backend/smoke_api.py
git diff --check
```

结果：全量测试 `117 passed, 3 skipped`；compileall、pip check、四个前端语法检查、Mock smoke 和 diff check 均以退出码 `0` 完成。专项认证测试为 `21 passed`，数据库配置测试为 `3 passed`。

使用临时 PostgreSQL URL 执行 `python -m alembic -c backend/alembic.ini upgrade head --sql` 可生成 PostgreSQL DDL，其中包含 `CREATE EXTENSION IF NOT EXISTS vector`。这是离线迁移语法证据，不是 Neon、pgvector 实例或持久化读回的通过证据。

本地 Edge + Playwright 使用独立 SQLite 数据库和 `http://127.0.0.1:8014` 同源服务，实际验证：

- 登录页显示冷启动提示，`390px` 文档宽度为 `390px`。
- 一键试用返回隔离 Demo 会话，浏览器读取到 1 个目标、3 个任务、1 份资料和 `waiting_confirmation` Run。
- 点击退出后回到认证页；注册后刷新仍能由 Cookie 恢复会话，`document.cookie` 不含 `ai_agent_session`。
- `390px` 与 `1440px` 的文档宽度不超过视口，桌面侧栏可见；控制台错误与页面错误均为 `0`。

## 真实 Neon 证据

在与生产分支隔离的 Neon `batch1-test` 分支使用直连 URL 执行：

```powershell
python -m alembic -c backend/alembic.ini upgrade head
python -m pytest backend/tests -m postgres -q --tb=short
```

结果为 `3 passed, 117 deselected`；2026-07-16 以同一隔离分支重复执行仍为 `3 passed, 117 deselected`。测试实际验证 `vector` 扩展、会话令牌 SHA-256 哈希、注册/登录/Demo/LLM 的 PostgreSQL 原子限流与 `429`、并发额度预留、资料批量写入、chunks、总结、闪卡和测试题。

生产 Neon 分支使用直连 `MIGRATION_DATABASE_URL` 迁移到 `20260716_01`；直连查询确认 `vector` 扩展与 `users` 表，池化 `DATABASE_URL` 也确认可读 schema。生产配置下的两次 FastAPI 生命周期实际完成一键试用，第二次实例可通过 Secure Cookie 读回同一会话和 1 个目标。

未设置 `POSTGRES_TEST_DATABASE_URL` 时，执行：

```powershell
python -m pytest backend/tests -m postgres -q --tb=short
```

结果为 `3 skipped, 117 deselected`，不是 PostgreSQL 通过证据。本机 `docker` 命令不可用，未执行本地 Docker build 或容器迁移。

## GitHub Actions 与公开 Render 证据

- `46d62ec` 的部署候选及后续验收/CI 修正提交已推送到 `personal/feature/v7-security-demo`。GitHub Actions [run 29485625666](https://github.com/Yuan0518dong/AI-Agent/actions/runs/29485625666) 于 2026-07-16 成功完成 `Reliability checks` 和 `PostgreSQL pgvector integration` 两个 job。
- 验收记录提交的首次 CI run `29485463169` 失败是一个真实发现：浅克隆使 `git show --check` 将仓库既有历史空白问题当作当前提交检查。后续提交改为 `fetch-depth: 2` 与 `git diff --check HEAD^ HEAD`，最终 run `29485625666` 两个 job 均通过；历史文件未被伪装为本批修复。
- Render Docker Web 服务公开地址为 [https://ai-agent-v7-yuan0518dong.onrender.com](https://ai-agent-v7-yuan0518dong.onrender.com)。`GET /` 与 `GET /api/health` 均为 `200`；公开 API smoke 真实验证同源 `POST /api/auth/demo`、Cookie `GET /api/auth/me`、`GET /api/goals` 的 1 个隔离目标、未知 Origin 的 `403 origin_forbidden`，以及 `Secure; HttpOnly; SameSite=Lax` Cookie 属性。
- 公开 URL 的 Edge + Playwright 验收真实点击“一键试用”：Demo Cookie 会话与 1 个目标可读回，`document.cookie` 不含会话名；登出后 `/api/auth/me` 返回 `401 auth_required`；`390px` 和 `1440px` 的文档宽度均不超过视口。页面无异常，除登出后的预期 `401 /api/auth/me` 外无失败 API 响应，console/page error 均为 `0`。
- Render 公开 Demo 当前显式使用 Mock Provider；这证明部署、会话、数据和界面链路，不构成真实模型性能或成本证据。

## 平台政策复核

- [Render Free 官方文档](https://render.com/docs/free) 于 2026-07-16 可访问，明确 Free Web Service 在 15 分钟无入站流量后休眠、重新唤醒约需 1 分钟，且本地文件系统会在休眠、重启和重新部署后丢失；免费 Render PostgreSQL 在创建 30 天后过期，14 天宽限期后删除。因此公开服务只使用 Render Web Service，不把本地 SQLite 或 Render PostgreSQL 当作生产数据源。
- [Neon Plans 官方文档](https://neon.com/docs/introduction/plans) 于 2026-07-16 可访问。Free 当前包含 100 CU-hours/项目/月、0.5 GB 存储/项目和 5 GB 公网传输/月；计算或出网超额会暂停到下个计费周期，存储超额会拒绝增加存储的操作，文档明确这些限额不会删除数据。当前用 Neon 作为生产持久化存储仍符合“无固定自动删除期限”的约束。
- 风险与动作：免费方案/额度不是固定承诺；每次求职季前必须复查上述官方页面。若 Neon 出现固定自动删除期限或现有项目接近额度，应先导出数据，再迁移到满足同等持久化约束的托管 PostgreSQL。

## 剩余部署缺口

以下需求保持未勾选：

- `DEPLOY-03`：Dockerfile、`.dockerignore`、Neon 连接分工和 Provider 变量说明已提交，Render Docker 服务也已上线；仍需在 Render 重新部署后用既有 Cookie/数据读回，才能证明运行实例不依赖临时本地状态。
- `OPS-01`：公开 API 链路已手工验证，但 `public-demo-smoke.yml` 只存在于功能分支；GitHub 默认分支为 `main`，`workflow_dispatch` 与 `schedule` 因此不能实际运行。`PUBLIC_DEMO_URL` 变量应先由仓库管理员配置，随后需将已验收的工作流放入默认分支并手动运行一次。

## 需要的外部授权

继续 Batch 1 最终验收需要用户授权：

```text
在个人 GitHub 仓库配置 PUBLIC_DEMO_URL
将已验收的 Public Demo Smoke 工作流合并或单独提交到个人仓库默认分支 main
在 Render 执行一次重新部署，并允许用临时 Demo Cookie 做重启后的只读回验
```

Neon 连接串仍不得写入仓库或状态文档。取得上述授权后，应验证 Render 重新部署后 Neon 数据可读回，并从默认分支手动触发公开 Demo smoke。只有这些证据存在时才能勾选剩余 Batch 1 条目、创建本批验收提交并进入 Batch 2。
