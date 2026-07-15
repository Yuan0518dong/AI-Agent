# 第六版 Batch C 真实 Provider 验收记录

验收日期：2026-07-15

所有验证均使用临时 SQLite 数据库；不记录 API Key、Authorization、Base URL、原始模型输出或用户数据。普通 `backend/smoke_api.py` 强制 Mock，本页只记录显式发起的真实 Provider 验收。

| 场景 | Provider / Model | Prompt Version | 耗时 | Step / Tool Sequence | 终态 | Fallback Reason | 结果 |
|---|---|---|---:|---|---|---|---|
| C0 真实 Embedding 检索基线 | openai-compatible / `embedding-3` | `embedding-v1` | 437 ms | 2 个 chunk -> semantic search | baseline complete | 空 | 2048 维向量；相关资料位居语义检索首位 |
| C4 正常三步循环 | openai-compatible / `glm-4-flash-250414` | `batch-c-v1` | 35 s | `create_task_draft -> apply_confirmed_draft -> answer_only` | `completed` | 空 | 3 个持久化 Step 均为真实 hybrid 决策 |
| C4 资料不足 | openai-compatible / `glm-4-flash-250414` | `grounded-answer-v1` | 4312 ms | grounded answer | answer returned | 空 | 非相关资料被判定为非资料依据，返回 `ask_for_more_material` |
| C4 非法参数 Guard | openai-compatible / `glm-4-flash-250414` | `guard-illegal-payload-v1` | 3.3 s | raw decision -> JSON/schema Guard | Guard fallback | `unknown fields` | 真实 Provider 输出的未注册 payload 字段被拒绝 |
| C4 确认恢复 | openai-compatible / `glm-4-flash-250414` | `batch-c-v1` | 40 s | `create_task_draft -> apply_confirmed_draft` | `max_steps` | 空 | ActionLog accepted 后仅写入一次正式任务，`appliedCount=1` |
| C4 模型失败降级 | openai-compatible / `validation-model` | `failure-fallback-v1` | 1.4 s | decision request | rule-based fallback | `LLM decision provider failed (URLError).` | 无效端点只触发 Decision fallback，不触发格式重试或写工具重试 |

相关实现与离线验证：

- `backend/tests`：LLM_PROVIDER=mock 时 `87 passed`。
- `backend/smoke_api.py`：通过，输出 `agent_hybrid_provider=mock`、`agent_hybrid_prompt_version=batch-c-v1` 与 `agent_loop_reflection=True`。
- `python -m compileall backend`、`git diff --check`：通过。
