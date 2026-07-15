# 第六版 Batch E 验收报告

更新时间：2026-07-15

范围：只验收路线图 Batch E；未新增数据库字段或公共 API，未实现 Batch F 的 cancel API、并发互斥、timeout/retry、CI 或部署工作。

## 验收结论

| 项目 | 结果 | 证据 |
|---|---|---|
| E1 AgentStep 时间线 | 通过 | 前端按 Step 展示索引、状态、创建时间、历时、Decision、工具、风险与 ActionLog。 |
| E2 Input/Output、Guard、stopReason | 通过 | 大 JSON 默认折叠；展示 Guard 干预/回退、error、stopReason；API Key、Authorization、Token、Password、Secret 脱敏。 |
| E3 确认/拒绝/恢复 | 通过 | 浏览器中 accepted PATCH 与 execute 均返回 200；同一 Run 完成正式写入。rejected PATCH 与 execute 也均返回 200，Step 保留 rejected 且 Run 安全进入 no_progress。 |
| E4 真实模型演示与截图 | 通过 | 真实 `openai-compatible · glm-4-flash-250414` 浏览器 Run 完成 3 个 Step；另保留 Guard 与失败回退证据。 |
| E5 简历与面试材料 | 通过 | `docs/planning/AI-Agent简历与面试讲解稿.md` 已补充可观察性、确认恢复和真实/回退证据讲解。 |

## 浏览器证据

| 场景 | 截图 | 核对点 |
|---|---|---|
| 完整成功 | `docs/images/batch-e-real-model-success.png` | 模型标签显示 `openai-compatible · glm-4-flash-250414`；`create_task_draft -> apply_confirmed_draft -> answer_only`，最终 `completed`。 |
| 确认恢复 | `docs/images/batch-e-confirmation-resume.png` | `waiting_confirmation`、两个明确的接受/拒绝控件、两个 Step 与 ActionLog 状态。 |
| Guard 拦截 | `docs/images/agent-guard-hybrid-fallback.png` | 未知 nextAction 被 Guard 拒绝，展示 `hybrid -> rule-based` 和 fallbackReason。 |
| 失败降级 | `docs/images/batch-e-provider-fallback.png` | 受控的本地 Provider 不可达场景；`Guard: fallback`、`rule-based` 与 `LLM decision provider failed (URLError)` 同时可见。该记录不是模型成功。 |
| 拒绝确认 | `docs/images/batch-e-rejection-resume.png` | `apply_confirmed_draft` 为 `rejected`，ActionLog 为“已忽略”，Run 进入 `no_progress`，没有正式写入。 |

前端浏览器断言：waiting_confirmation 状态下两个控件均出现；两个 Step 的 `<details>` 默认未展开；`redactAgentValue` 对 `apiKey` 和 `Authorization: Bearer ...` 均返回 `[redacted]`。

## 自动化与工程检查

```text
LLM_PROVIDER=mock LLM_ENV_FILE=.missing-test-env python -m pytest backend/tests -q --basetemp .pytest_tmp\batch-e-final
91 passed in 33.82s

LLM_PROVIDER=mock LLM_ENV_FILE=.missing-test-env python backend/smoke_api.py
通过；包含 agent_hybrid_guard_status=fallback、agent_draft_waiting_status=waiting_confirmation、agent_draft_status=applied、agent_draft_readback_status=max_steps、agent_draft_snapshot_matches_get=True。

python -m compileall -q backend
通过

node --check app/api.js
node --check app/app.js
node --check app/modules/agent-workbench.js
通过

git diff --check
通过
```

## 演示复现

```bash
python -m uvicorn backend.app.main:app --reload --port 8001
python -m http.server 5500 --directory app
python backend/init_batch_e_demo_data.py
```

完整讲解顺序见 [第六版BatchE演示脚本.md](第六版BatchE演示脚本.md)。初始化脚本只调用现有 API，不输出或写入 Provider Key。
