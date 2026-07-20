# 真实 Agent 可靠性 A3 候选设计与离线验收

更新时间：2026-07-20

## 目标

A2 将真实工具选择率从 `0.6333` 提升到 `0.75`、确认完整性从 `0.5556` 提升到 `0.6667`，但 `014` 确认复盘恢复和 `016` 无效批次回滚仍为 3/3 系统性失败。A3 不继续增加关键词或工具，而是减少模型需要承担的运行时控制职责。

当前 Prompt version：`agent-reliability-a3-compact-v1`。

## A3-1：单一合法动作确定性短路

当 allowed-action policy 只剩一个可安全构造的动作时，Runtime 直接生成完整 Decision，不调用 LLM：

- 证据目标首次执行 `search_materials`。
- no-progress 目标执行一次观测型 search，重复 fingerprint 由现有 Runtime 停止。
- 最近拒绝且明确要求避免重复时执行 `answer_only`。
- 已有 proposed draft 时，使用真实 draft IDs 构造 `apply_confirmed_draft`。
- 缺 chunks 且只有资料处理动作时，可按当前 scope 构造 `review_material`。

确定性 Decision 使用 `mode=rule-based`、保留原 `requestedMode`，并增加：

```json
{
  "decisionPolicy": {
    "status": "deterministic",
    "reason": "single_allowed_action",
    "allowedActionTypes": ["search_materials"]
  }
}
```

如果动作需要不存在的 ID，策略不会伪造参数，而是返回 `None` 继续走受 Guard 保护的模型路径。因此 `016` 没有 draft ID 的旧 fixture 不会通过硬编码作弊。

## A3-2：复盘草稿阶段约束

当 objective 明确包含“创建/确认/应用复盘草稿”时，在草稿创建前只暴露 `create_flashcards` 和 `create_quiz`，不再允许模型以 `answer_only` 提前结束。草稿创建后，Context 中的 proposed draft 会触发确定性 apply 路径。

## A3-3：精简模型 Decision Schema

模型只需返回：

```json
{
  "nextAction": "create_flashcards",
  "reason": "short reason",
  "proposedActions": [
    {"type": "create_flashcards", "payload": {}}
  ]
}
```

`stateSummary`、`problems`、`requiresConfirmation`、`reflection`、label 和 description 不再要求模型重复生成。Guard 继续接受旧完整 Schema，并由服务端 fallback Decision 补齐缺失状态字段；确认要求仍由 Tool Registry 风险策略计算，不能由模型关闭。

## 离线证据

- 全量 Mock pytest：`166 passed, 4 skipped`。
- 集成测试将 LLM Provider 替换为“一旦调用就失败”，证据检索 Run 仍成功持久化 `search_materials` Step，证明单动作路径真实绕过模型。
- 固定20场景假 Provider 审计：执行决策请求由 A2 的 29 降到 A3 的 21（单次覆盖口径），减少约 27.6%。
- 最大请求包为 `9065` UTF-8 bytes，低于 `12000` 上限。
- 所有请求继续携带 `350` completion token cap。
- Ruff、compileall、pip check、前端语法、敏感信息扫描与 diff check：通过。
- Batch 4 Playwright：`1 passed`，原桌面、390px、PDF、引用问答、确认、拒绝和取消流程保持通过。

上述结果只证明结构、兼容性和请求包边界，不代表真实 DeepSeek 指标已经提升。

## 真实复跑判定

A3 仍需使用原 20 × 3 固定集，与 A0、A2 三列并排报告：

- 工具选择成功率目标 `>=0.80`。
- 确认完整性目标 `>=0.85`。
- 恢复成功率保持 `1.0`。
- 单独报告 `decisionPolicy.status=deterministic` 的 Run 数，避免把 Runtime 确定性选择误写为模型工具选择能力。
- 使用修复后的 fallback 统计，同时计入不同于 Step snapshot 的终态 decision。
- 保留请求、Token、成本、p50/p95 和全部失败 Run。

## 真实复跑结果

用户授权最多126次请求、最高`$0.27`后，A3完成相同20×3真实DeepSeek复跑：

```text
系统工具选择成功率：0.8833
确认完整性：0.7778
恢复成功率：1.0
失败Run：7
Provider请求：67
prompt/completion Token：109995/7400
估算成本：$0.017471
Runtime确定性Decision：41，覆盖32个Run
```

工具选择达到`>=0.80`，确认仍未达到`>=0.85`。A3分支继续不合并、不部署到Render；完整三版本对比见`docs/evaluation/agent-reliability-a3/A0-A2-A3真实评测对比.md`。
