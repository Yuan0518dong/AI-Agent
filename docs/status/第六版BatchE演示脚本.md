# 第六版 Batch E 演示脚本

更新时间：2026-07-15

本脚本对应路线图 Batch E 的前端可观察化演示，时长约 3–5 分钟。演示只使用本地数据；不要把 Provider Key 粘贴到页面、终端截图或文档中。

## 0. 演示前准备（约 30 秒）

在两个终端分别启动后端和前端：

```bash
python -m uvicorn backend.app.main:app --reload --port 8001
python -m http.server 5500 --directory app
```

然后初始化幂等演示数据：

```bash
python backend/init_batch_e_demo_data.py
```

脚本会打印一个仅用于本地演示的账号。打开 `http://127.0.0.1:5500/index.html`，使用该账号登录。

若要演示真实模型，先在本地 `backend/.env` 配置 Provider；页面 Run 摘要中的“模型”标签必须显示实际 provider/model 才能称为真实模型演示。未配置或调用失败时，页面会明确显示 fallback，不应把它说成模型成功。

## 1. 完整成功与时间线（约 60 秒）

1. 在“成长目标”选择 `Batch E demo - confirmation and resume`。
2. 进入“智能体工作台”，输入 objective：`Create a safe next learning task that a user can confirm.`，最大步骤设为 `3`，点击“启动 Run”。
3. 展示 Run 摘要中的 status、stopReason、Guard 和模型标签；在时间线中依次解释 `create_task_draft`、`apply_confirmed_draft` 和终态 Step。
4. 展开任一“查看输入、输出与决策详情”，说明大 JSON 默认收起；展示 Tool Input/Output、Decision、Context 摘要均在同一 Step，敏感字段会显示为 `[redacted]`。

## 2. 确认、拒绝与恢复（约 60 秒）

1. 当 `apply_confirmed_draft` 进入 `waiting_confirmation`，说明正式写入尚未发生，ActionLog 状态为“已建议”。
2. 点击“接受并恢复原 Run”：系统在同一 Run/Step 中执行正式写入，读回新 Context 后继续决策；显示 `Applied ... formal record` 和最终 completed/max_steps 状态。
3. 如需展示拒绝，选择独立的 `Batch E demo - rejection` 空目标，运行到同一确认点后点击“拒绝并继续 Run”；时间线显示 rejected，ActionLog 显示“已忽略”，且没有正式写入。

## 3. Guard 与失败降级（约 45 秒）

1. 打开 README 中的 Guard 截图，指出未知 nextAction 被 Decision Guard 拦截并回退 rule-based。
2. 打开 Provider 不可达截图，指出 Run 摘要中的 `Guard: fallback`、时间线中的 `回退原因` 和 rule-based Decision。该记录是受控故障注入证据，用于证明安全降级，不是模型成功案例。

## 4. 收尾（约 30 秒）

总结一句：

```text
这个 Run 不是只给出最终答案；每一步都有可审计的 Context、Decision、Guard、Tool、确认状态和终态证据，模型不可用时也会保留原因并安全回退。
```

对应截图：

- `docs/images/batch-e-real-model-success.png`：真实 Provider 成功与完整 Run。
- `docs/images/batch-e-confirmation-resume.png`：waiting_confirmation 与接受/拒绝/恢复入口。
- `docs/images/agent-guard-hybrid-fallback.png`：未知动作的 Guard 拦截。
- `docs/images/batch-e-provider-fallback.png`：Provider 不可达后的安全回退。
- `docs/images/batch-e-rejection-resume.png`：拒绝正式写入后的同一 Run 终态。
