# 第七版 Batch 1 本地验收记录

验收日期：2026-07-16

## 状态

本记录描述已经获得的本地、浏览器和真实 Neon 证据。Batch 1 尚未完成 Render/公开 Demo 验收，当前不得创建 Batch 2 分支，也不得把 Docker、部署或公开 smoke 写成已完成。

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

结果为 `3 passed, 117 deselected`。测试实际验证 `vector` 扩展、会话令牌 SHA-256 哈希、注册/登录/Demo/LLM 的 PostgreSQL 原子限流与 `429`、并发额度预留、资料批量写入、chunks、总结、闪卡和测试题。

生产 Neon 分支使用直连 `MIGRATION_DATABASE_URL` 迁移到 `20260716_01`；直连查询确认 `vector` 扩展与 `users` 表，池化 `DATABASE_URL` 也确认可读 schema。生产配置下的两次 FastAPI 生命周期实际完成一键试用，第二次实例可通过 Secure Cookie 读回同一会话和 1 个目标。

未设置 `POSTGRES_TEST_DATABASE_URL` 时，执行：

```powershell
python -m pytest backend/tests -m postgres -q --tb=short
```

结果为 `3 skipped, 117 deselected`，不是 PostgreSQL 通过证据。本机 `docker` 命令不可用，未执行 Docker build 或容器迁移。

## 剩余部署缺口

以下需求保持未勾选：

- `DB-02`：PostgreSQL CI job 已定义且本地 Neon 集成通过，但尚未在 GitHub Actions 实际运行；生产环境在 Render 上的无 SQLite 回退仍需部署证据。
- `DEPLOY-03`：尚未构建 Docker 镜像或向 Render 注入真实 Provider/Neon 配置。
- `OPS-01`：公开 Demo smoke 工作流已定义，但没有 `PUBLIC_DEMO_URL`，未实际唤醒 Render、连接 Neon 或运行线上链路。
- `OPS-02`：属于求职季前持续复核事项，尚未发生。

## 需要的外部授权

继续 Batch 1 最终验收需要用户授权：

```text
向个人 GitHub 远程推送当前 Batch 1 分支，仅用于 Render 部署，不合并
Render 服务配置和 PUBLIC_DEMO_URL
```

Neon 连接串仍不得写入仓库或状态文档。取得远程推送和 Render 授权后，应构建 Docker、验证 Render 重启/重新部署后 Neon 数据可读回，并手动触发公开 Demo smoke。只有这些证据存在时才能勾选剩余 Batch 1 条目、创建本批验收提交并进入 Batch 2。
