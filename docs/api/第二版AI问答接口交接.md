# 第二版 AI 问答接口交接

更新时间：2026-07-02

## 1. 当前结论

当前 `dev` 已提供并接入：

```text
POST /api/agent/ask
```

当前后端尚未提供：

```text
GET /api/materials/{material_id}/qa
```

因此赵前端本轮先接入 `POST /api/agent/ask`，历史问答列表暂时沿用前端现有会话展示；等 `GET /api/materials/{material_id}/qa` 后端稳定后，再接持久化历史问答。

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
  "limit": 3
}
```

请求字段：

| 字段 | 必填 | 说明 |
|---|---|---|
| question | 是 | 用户问题，不能为空 |
| goalId | 否 | 当前目标 ID；如果传入，后端会按目标过滤资料片段 |
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
后端尚未实现，前端暂不接入。
```

预期用途：

```text
按资料读取该资料相关的历史问答记录。
```

待后端稳定后再确认：

```text
1. 是否按 materialId 查询。
2. 是否支持 goalId 过滤。
3. 是否返回 answer、basis、suggestion、references、isFromMaterial、confidence、createdAt。
4. 是否需要分页或 limit。
```

## 5. 当前验证

```text
python -m pytest backend/tests -v：14 passed
python backend/smoke_api.py：通过，包含 agent_mode / agent_reference_count / agent_from_material / agent_confidence
node --check app/api.js app/app.js app/modules/chat.js app/modules/materials.js：通过
Edge 浏览器 smoke：成长问答页提交问题 -> 调用 /api/agent/ask -> 展示 answer / basis / suggestion / references / confidence，无控制台错误
```

