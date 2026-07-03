# 第二版 AI 问答接口交接

更新时间：2026-07-03

## 1. 当前结论

当前 `dev` 已提供并接入：

```text
POST /api/agent/ask
GET /api/materials/{material_id}/qa
```

当前前端已接入：

```text
成长问答页 agent ask
资料总结区问 AI 入口
资料总结区按资料直接提问
资料历史问答列表展示
历史问答复盘草稿入口
复盘草稿确认加入正式闪卡
```

因此当前问答交界面已经形成可演示闭环：资料生成 chunks 后，用户可以围绕资料提问；后端通过 `POST /api/agent/ask` 生成回答并保存 QA 记录；前端通过 `GET /api/materials/{material_id}/qa` 读回历史问答，并可以从单条问答生成前端复盘草稿。用户确认后，复盘草稿可以写入正式闪卡，并保存复习状态。

## 2. POST /api/agent/ask

用途：

```text
用户在成长问答页输入问题后，后端基于 chunks 检索结果组织 mock AI 回答。
```

请求示例：

```json
{
  "question": "How does RAG retrieval answer questions?",
  "goalId": "goal_xxx",
  "materialId": "material_xxx",
  "limit": 3
}
```

请求字段：

| 字段 | 必填 | 说明 |
|---|---|---|
| question | 是 | 用户问题，不能为空 |
| goalId | 否 | 当前目标 ID；如果传入，后端会按目标过滤资料片段 |
| materialId | 否 | 当前资料 ID；如果传入，后端会按资料过滤片段，并保存该资料的问答记录 |
| limit | 否 | 返回引用片段数量，默认 3，范围 1-10 |

响应示例：

```json
{
  "answer": "我先根据已检索到的资料片段回答：...",
  "basis": "依据已检索到的 3 个资料片段，来源资料：RAG notes。",
  "suggestion": "建议先复述命中的资料片段，再补充一个练习或测试题检查理解。",
  "references": [
    {
      "materialId": "material_xxx",
      "materialTitle": "RAG notes",
      "chunkIndex": 0,
      "content": "RAG uses retrieval to find relevant chunks before generating an answer.",
      "score": 5
    }
  ],
  "isFromMaterial": true,
  "confidence": "high",
  "mode": "mock"
}
```

响应字段：

| 字段 | 说明 |
|---|---|
| answer | 回答正文 |
| basis | 回答依据说明 |
| suggestion | 学习建议 |
| references | 命中的资料片段列表 |
| isFromMaterial | 回答是否主要来自资料 |
| confidence | high / medium / low |
| mode | 当前回答模式，现阶段为 mock |

## 3. 前端接入位置

当前前端接入：

```text
app/api.js -> agentApi.ask()
app/app.js -> #chat-form submit
app/modules/chat.js -> renderChat()
app/modules/materials.js -> 资料总结区按资料提问
```

展示位置：

```text
成长问答页：#chat-log
```

前端展示规则：

```text
1. 用户消息展示 question。
2. 助手消息展示 answer。
3. 助手消息下方展示 confidence、mode 和是否基于资料。
4. 展示 basis 为“回答依据”。
5. 展示 suggestion 为“学习建议”。
6. references 默认折叠展示，展开后显示资料标题、chunk 序号、score 和片段内容。
7. isFromMaterial=false 或 confidence=low 时，前端显示“资料不足”状态。
```

## 4. GET /api/materials/{material_id}/qa

当前状态：

```text
后端已实现，前端已在资料总结区接入历史列表展示。
```

预期用途：

```text
按资料读取该资料相关的历史问答记录。
```

当前返回字段：

```text
id
materialId
goalId
question
answer
basis
suggestion
sourceTitle
isFromMaterial
confidence
mode
createdAt
```

前端展示规则：

```text
1. 按资料隔离展示历史问答。
2. 页面初始化时读取并展示。
3. 提问成功后重新读取该资料的历史问答。
4. 展示 question、answer、basis、suggestion、sourceTitle、confidence。
5. isFromMaterial=false 或 confidence=low 时显示资料不足状态。
6. 每条历史问答提供“转闪卡草稿”和“记复习点”入口。
```

## 5. 历史问答复盘入口

当前状态：

```text
已完成前端本地草稿闭环，并已支持用户确认后加入后端正式闪卡。
```

当前规则：

```text
1. “转闪卡草稿”根据 question 和 answer 生成 front/back。
2. “记复习点”优先使用 suggestion，其次使用 basis，再降级为回到资料复述问题。
3. 同一条 QA 的同类型草稿不重复生成。
4. 复盘草稿显示在记忆页。
5. 删除资料时同步删除对应本地复盘草稿。
6. 点击“加入闪卡”后，前端调用 POST /api/materials/{material_id}/flashcards/custom。
7. 记忆页点击“已掌握 / 还要复习”后，前端调用 PATCH /api/materials/{material_id}/flashcards/{flashcard_id} 保存状态。
```

当前边界：

```text
复盘草稿本身仍暂存在前端 localStorage，不自动写入。
用户确认“加入闪卡”后，正式闪卡会写入后端 flashcards 表。
第二版暂不自动生成测试题或任务，也不做完整间隔重复日程。
```

新增闪卡接口：

```text
POST /api/materials/{material_id}/flashcards/custom
PATCH /api/materials/{material_id}/flashcards/{flashcard_id}
```

创建单张闪卡请求示例：

```json
{
  "front": "请解释：RAG 如何使用检索？",
  "back": "RAG 会先检索相关资料片段，再基于证据组织回答。"
}
```

更新闪卡状态请求示例：

```json
{
  "status": "known"
}
```

## 6. 当前验证

```text
python -m pytest backend/tests -v：18 passed
python backend/smoke_api.py：通过，包含 agent_mode / agent_reference_count / agent_from_material / agent_confidence / qa_record_count
node --check app/api.js app/app.js app/modules/chat.js app/modules/materials.js app/modules/goals.js app/modules/progress.js app/modules/utils.js：通过
Edge 浏览器 smoke：资料 QA 历史 -> 转闪卡草稿 -> 记忆页展示；重复点击不重复；删除新建 smoke 资料后复盘草稿清零；无 console error / pageerror
2026-07-03 闪卡闭环补完：backend/tests/test_material_flow.py 3 passed；隔离本地 .env 后全量 pytest 26 passed；8001 接口 smoke 完成创建单张闪卡、PATCH 标记 known、GET 读回和清理临时资料。
```

