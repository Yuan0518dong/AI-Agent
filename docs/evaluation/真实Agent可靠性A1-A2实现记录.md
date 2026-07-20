# 真实 Agent 可靠性 A1–A2 实现记录

更新时间：2026-07-20

## 当前结论

A1 和 A2 已完成本地实现，但尚未运行新的真实 Provider 评测。第七版 `0.6333` 工具选择率、`0.5556` 确认完整性和 22 个失败 Run 仍是唯一真实基线；本记录不能替代相同 20 × 3 固定集的付费复跑。

## A1：动作与工具契约对齐

代码审计发现原 Prompt 暴露 `availableTools`，其中包含 `create_task_draft`、`create_review_draft` 等底层工具名；Decision Guard 实际接受的却是 `create_followup_tasks`、`reschedule_tasks`、`create_flashcards` 和 `create_quiz` 等动作类型。系统提示同时要求模型从 `availableTools` 选择 action type，形成不一致契约。

A1 新增 `list_model_actions()`：

- 每项明确给出 Guard 可接受的 `type`。
- 同时保留对应的 `toolName`，用于观察底层执行工具。
- 暴露与该动作匹配的 `inputSchema`、风险、确认和 draft-only 属性。
- Prompt 字段由 `availableTools` 改为 `availableActions`，明确禁止把 `toolName` 当作 action type。

该变化只影响模型决策契约；对外 `/api/agent/tools` 和 Tool Registry 执行接口保持兼容。

## A2：状态感知 allowed-action policy

新增纯函数 `agent_action_policy_service.allowed_action_types()`，仅对具有明确 objective 的 Agent Run 生效；没有 objective 的通用 `/api/agent/decide` 继续使用完整动作集。

当前策略优先级：

1. 已有 proposed draft 时，只允许 `apply_confirmed_draft`。
2. 回滚无效草稿目标只允许确认应用动作，以验证事务失败路径。
3. accepted/rejected feedback memory 同时兼容历史 action type 和 tool name。
4. 缺少 chunks 时优先资料处理或材料不足建议。
5. 证据目标在首次检索前只允许 `search_materials`；检索完成后才开放带引用回答或资料不足。
6. 复盘、任务、资料处理和 no-progress 目标使用中英文关键词路由到较小动作集合。
7. Prompt 只发送策略允许的动作，Decision Guard 对相同集合执行强校验。
8. 如果 Provider 失败或模型输出被 Guard 拒绝，rule-based fallback 中不属于当前集合的动作会被删除；没有合法 fallback 时安全结束为 no-progress，不执行无关工具。

## 已覆盖的失败族

| 原失败族 | 约束方式 |
|---|---|
| `003` 检索后创建任务 | 证据目标首次只允许 search，完成后只允许 grounded answer/gap/answer |
| `004` 复盘草稿走普通任务 | 复盘目标只暴露 review-draft actions 与 answer |
| `008` 跨目标检索走任务草稿 | 证据目标只允许 scoped search |
| `013` 拒绝后状态误判 | rejected memory + 已有等待 Step 由 Runtime 恢复，后续避免重复动作 |
| `014` 确认恢复重新规划 | proposed draft 状态只允许 apply |
| `016` 事务回滚选择新建草稿 | rollback objective 只允许 apply action |
| `018` 过早 answer-only | no-progress 目标先执行观测型 search |
| `019` 重复被拒复盘方向 | tool-name/action-type 归一化后只允许 answer-only |

这张表描述预期机制，不表示真实场景已经通过。

## 本地验证

- 全量 Mock pytest：`160 passed, 4 skipped`。
- `backend/smoke_api.py`：通过，记录 Prompt version `agent-reliability-a2-policy-v1`。
- Ruff：通过。
- compileall、pip check、前端语法、敏感信息扫描和 diff check：通过。
- Batch 4 Playwright：`1 passed`，覆盖桌面、390px、PDF、引用问答、确认、拒绝和取消。

## 真实复跑预算

现有预检重新计算的上限不变：

```text
20 场景 × 3 = 60 Run
Provider 请求：最少 60，最多 126
单请求：发送前最多 12,000 UTF-8 bytes；最多 350 completion tokens
保守成本估算：$0.224028
含 20% buffer 的授权门槛：$0.268834，执行时取 $0.27 上限
```

真实复跑必须由用户再次明确授权 `最多 126 次 Provider 请求、最高 $0.27`，之后才能设置 `BATCH4_REAL_EVAL_APPROVED=yes`。未获授权前只执行离线和 Mock 验证。
