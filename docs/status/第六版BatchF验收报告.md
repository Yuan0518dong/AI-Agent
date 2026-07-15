# 第六版 Batch F 验收报告

更新时间：2026-07-15

范围：Batch F 可靠性与可复现交付。未提交或推送代码；保留工作区已有未提交改动。

## 验收结论

| 项目 | 结果 | 证据 |
|---|---|---|
| F1 timeout / retry / cancel / 互斥 | 通过 | `cancelled` 状态与 `POST /api/agent/runs/{run_id}/cancel`；条件更新 executor claim；读工具最多两次尝试，写工具一次尝试。专项并发、取消、读重试、写不重试测试通过。 |
| F2 事务、幂等、脱敏 | 通过 | 既有 Draft 正式写入事务/`appliedEntityIds`/重复恢复测试保持通过；新增 AgentRun、AgentStep、ActionLog 递归脱敏测试。 |
| F3 固定依赖与 CI | 通过 | `backend/requirements.lock` 固定 Python 3.12 依赖，`.env.example` 含 timeout 配置且不含真实 Key；CI 覆盖 pytest、compileall、smoke、前端语法和 diff check。 |
| F4 单命令与录屏 | 通过 | 单条 uvicorn 命令同源服务 `/` 和 `/api`；新进程验证根路径为前端 HTML、健康检查正常；稳定录屏已保留。 |
| F5 契约与架构 | 通过 | [第六版Agent运行时契约与架构.md](../api/第六版Agent运行时契约与架构.md) 已同步 API、状态、timeout/retry、取消、隐私和 Mermaid 架构图。 |

## 可靠性语义

```text
同一 Run：条件 UPDATE 仅允许一个 executor 从可执行状态进入 running。
取消：写入 cancelled 后，Loop 在决策前、入库前、工具返回后协作式检查；普通状态更新不能覆盖 cancelled。
读工具：search_materials / answer_only timeout 后最多重试一次。
写工具：不自动重试；正式写入使用既有事务、ActionLog、Draft 状态、idempotency key 和 appliedEntityIds 恢复。
隐私：持久化 Run/Step/ActionLog 的 apiKey、Authorization、Bearer、token、password、secret 递归替换为 [redacted]。
```

同步写工具无法被 Python 安全强杀，因此取消不回滚一个已经提交的原子正式写入；它会阻止后续步骤，正式写入继续受确认、事务与幂等约束。这一边界已在最终契约中明确。

## 自动化证据

```text
LLM_PROVIDER=mock LLM_ENV_FILE=.missing-test-env EMBEDDING_PROVIDER=mock python -m pytest backend/tests -q --basetemp .pytest_tmp\batch-f-full
98 passed in 38.67s

python backend/smoke_api.py
通过；包括 waiting_confirmation、confirmed apply、readback、重复写入去重和 mock Guard fallback。

python -m compileall -q backend
node --check app/api.js
node --check app/app.js
node --check app/modules/agent-workbench.js
python -m pip check
git diff --check
全部通过

python -m pip install --dry-run -r backend/requirements.txt
全部固定依赖可解析；CI YAML 已解析通过。
```

新增专项覆盖：取消幂等与执行阻断、并发 executor 单次 claim、in-flight 取消不被覆盖、读工具重试一次、写工具不重试、Run/Step/ActionLog 脱敏；单命令根路径返回前端 HTML 的测试也已纳入 pytest。

## 一条命令与稳定录屏

```bash
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8001
```

访问 `http://127.0.0.1:8001/`。同一进程也提供 `/api/health` 和 `/docs`；无需额外静态服务器。

端到端录屏：[batch-f-end-to-end.webm](../videos/batch-f-end-to-end.webm)（573,548 bytes）：同源页面加载、Agent Run waiting_confirmation、接受后同一 Run 恢复与时间线展示。录制使用 mock Provider 和临时本地演示用户，不包含真实 Key、Authorization 或个人账号密码。
