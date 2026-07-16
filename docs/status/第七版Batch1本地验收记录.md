# 第七版 Batch 1 本地验收记录

验收日期：2026-07-16

## 状态

本记录描述已经获得的本地、浏览器、真实 Neon、GitHub Actions 和公开 Render 证据。Batch 1 全部需求项已完成最终验收；本记录的独立提交完成后，才可以从它创建 Batch 2 分支。

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
- `DEPLOY-03`：Render Docker 服务重新部署恢复 `Live` 后，部署前建立的临时 Demo Secure Cookie 仍成功读取同一会话与 1 个目标；验收后已删除临时 Cookie。该结果证明公开运行实例依赖 Neon 持久化数据而不是容器本地文件。
- `OPS-01`：`PUBLIC_DEMO_URL` 已作为仓库 Variable 配置，工作流已位于默认分支 `main`。手动 [run 29487956918](https://github.com/Yuan0518dong/AI-Agent/actions/runs/29487956918) 成功完成健康检查、同源 Demo、Cookie `/api/auth/me` 和 `/api/goals` 只读链路；同一工作流保留每月 `17 3 1 * *` 调度，不使用高频保活。
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
- 用户确认 Render 手动重新部署已恢复 `Live` 后，使用部署前保存的临时 Demo Cookie 重新请求 `/api/auth/me` 与 `/api/goals`，会话与 1 个目标均成功读回；Cookie 文件随后删除。
- `Public Demo Smoke` 已随 Batch 1 快进到 `personal/main` 并注册为默认分支工作流。仓库 Variable `PUBLIC_DEMO_URL` 的值为公开 Render Origin；手动 [run 29487956918](https://github.com/Yuan0518dong/AI-Agent/actions/runs/29487956918) 以 `workflow_dispatch` 成功运行，证明该变量、公开 URL、Demo 和只读链路真实可用。月度 cron `17 3 1 * *` 已在同一已验证工作流中生效；首次自然月触发尚未到期，不能伪称已经发生。
- Render 公开 Demo 当前显式使用 Mock Provider；这证明部署、会话、数据和界面链路，不构成真实模型性能或成本证据。

## 平台政策复核

- [Render Free 官方文档](https://render.com/docs/free) 于 2026-07-16 可访问，明确 Free Web Service 在 15 分钟无入站流量后休眠、重新唤醒约需 1 分钟，且本地文件系统会在休眠、重启和重新部署后丢失；免费 Render PostgreSQL 在创建 30 天后过期，14 天宽限期后删除。因此公开服务只使用 Render Web Service，不把本地 SQLite 或 Render PostgreSQL 当作生产数据源。
- [Neon Plans 官方文档](https://neon.com/docs/introduction/plans) 于 2026-07-16 可访问。Free 当前包含 100 CU-hours/项目/月、0.5 GB 存储/项目和 5 GB 公网传输/月；计算或出网超额会暂停到下个计费周期，存储超额会拒绝增加存储的操作，文档明确这些限额不会删除数据。当前用 Neon 作为生产持久化存储仍符合“无固定自动删除期限”的约束。
- 风险与动作：免费方案/额度不是固定承诺；每次求职季前必须复查上述官方页面。若 Neon 出现固定自动删除期限或现有项目接近额度，应先导出数据，再迁移到满足同等持久化约束的托管 PostgreSQL。

## 持续风险与复核

- Render Free Web 可能休眠、重启或消耗完当月免费实例时数；公开首页保留冷启动提示，公开 smoke 不会通过高频请求规避平台政策。
- 在确认 Render 可信代理 CIDR 前保持 `TRUST_PROXY_HEADERS=false`。这避免接受可伪造的转发头，但公共 IP 限流可能按 Render 代理而非真实访客聚合。
- Render/Neon 免费政策和额度须在每次求职季前重查；`OPS-02` 的本次通过不替代下一次复核。

Neon 连接串、Cookie 和 Provider Key 均未写入仓库或状态文档。
