# 资料与 AI 模块字段和 API 草案

更新时间：2026-07-01

## 1. 模块范围

本文件记录赵负责模块的字段和 API 草案。当前赵模块的 MVP-0 静态原型已完成并合入 dev，后续重点是从前端 localStorage/mock AI 迁移到后端 API、SQLite 和可替换 AI service。

赵负责主线：

```text
资料管理 -> AI 整理 -> 闪卡 / 测试题 -> 成长问答
```

当前已完成的 MVP-0 原型使用：

```text
localStorage
mock AI
单用户数据
```

后续 MVP-1A / MVP-1B 再迁移到：

```text
REST API
SQLite
可替换 AI service
```

## 2. 字段命名约定

静态原型和前端 API 草案使用 camelCase：

```text
createdAt
updatedAt
materialId
relatedMaterialIds
```

后端数据库字段后续可使用 snake_case：

```text
created_at
updated_at
material_id
related_material_ids
```

时间字段统一使用 ISO 字符串。

## 3. 数据库设计与演进原则

赵模块后端迁移不要只按页面状态存数据，而要围绕学习链路设计：

```text
资料 -> AI 理解 -> 练习生成 -> 成长问答
```

### 3.1 原始数据和派生数据分离

```text
原始数据：
materials

派生数据：
material_summaries
flashcards
quiz_questions
ai_conversations / conversation_messages
```

`materials` 只保存用户输入或上传得到的资料本体。AI 整理、闪卡、测试题和问答记录都属于后续处理结果，应单独建表。这样资料可以保持稳定，派生结果可以重新生成、更新或替换 AI 实现。

### 3.2 稳定关联优先使用 ID

资料相关派生表统一优先使用 `material_id` 关联，不使用 `title`、`source` 或正文片段关联。

原因：

```text
1. title 可能重复。
2. title 可能被用户修改。
3. source / content 不适合作为稳定外键。
4. material_id 便于删除资料时清理派生数据。
```

闪卡和测试题后续也应优先基于 `material_summaries.key_points` 生成，而不是直接依赖 `materials.content`。原文适合保存事实来源，summary 的结构化字段更适合驱动练习和问答。

### 3.3 当前有效结果用 upsert，历史版本另建表

当前阶段默认只保留一份当前有效整理结果：

```text
material_summaries.material_id PRIMARY KEY
```

重复调用 `POST /api/materials/{id}/summarize` 时更新同一条 summary，而不是追加多条。只有后续明确需要比较历史版本时，再新增类似 `material_summary_versions` 的版本表。

判断规则：

```text
当前状态：upsert
历史记录：append
```

### 3.4 SQLite 数组字段用 JSON 字符串存储

SQLite 当前没有单独的数组字段，以下字段在数据库中可用 JSON 字符串保存：

```text
key_points
difficulties
study_order
action_items
options
related_material_ids
messages
```

但 API 返回仍保持前端友好的数组或对象结构：

```text
数据库：snake_case + JSON string
API：camelCase + array/object
```

### 3.5 删除主数据时清理派生数据

删除资料时，后端必须同步处理派生数据，避免孤儿记录：

```text
materials
  -> material_summaries
  -> flashcards
  -> quiz_questions
  -> AI conversations 中的 relatedMaterialIds 引用
```

数据库层优先使用外键和 `ON DELETE CASCADE`；如果某些字段是 JSON 引用，则需要在 service 层显式清理或标记失效。

### 3.6 MVP 阶段数据库维护方式

MVP-1A 暂不引入复杂 migration 工具，先采用：

```text
1. 新表写入 store.init_db()。
2. 新 store 方法配套 CRUD。
3. smoke 覆盖关键路径。
4. backend/data/ai_agent.db 只作为本地开发数据，不提交 Git。
```

如果后续给已存在的表新增字段，不能只改 `CREATE TABLE IF NOT EXISTS`，需要补兼容升级逻辑，例如检查列是否存在后再 `ALTER TABLE ADD COLUMN`。

长期进入 MVP-2 或部署前，再考虑：

```text
1. 正式 migration 工具。
2. 数据库版本号。
3. 测试数据库和种子数据。
4. 用户隔离字段 user_id。
```

### 3.7 新增表前的判断清单

每次新增资料模块表或字段前，先判断：

```text
1. 这是原始数据，还是派生数据？
2. 它属于 goal，还是属于 material？
3. 删除 material 时，它要不要一起删除？
4. 它会不会被重新生成？
5. 前端刷新后，需要从哪个 API 重新读取它？
6. smoke 如何验证它不会产生孤儿数据？
```

## 4. 数据对象

### 4.1 Material

资料对象。

```js
Material = {
  id,
  goalId,
  title,
  type,
  content,
  url,
  createdAt,
  updatedAt
}
```

字段说明：

| 字段 | 说明 |
|---|---|
| id | 资料 ID |
| goalId | 关联目标 ID，静态原型可先为空 |
| title | 资料标题 |
| type | text / link |
| content | 文本内容 |
| url | 网页链接 |
| createdAt | 创建时间 |
| updatedAt | 更新时间 |

### 4.2 MaterialSummary

资料 AI 整理结果。

```js
MaterialSummary = {
  materialId,
  overview,
  keyPoints,
  difficulties,
  studyOrder,
  actionItems,
  aiMode,
  createdAt,
  updatedAt
}
```

字段说明：

| 字段 | 说明 |
|---|---|
| materialId | 关联资料 ID |
| overview | 资料摘要 |
| keyPoints | 关键知识点数组 |
| difficulties | 难点解释数组 |
| studyOrder | 建议学习顺序数组 |
| actionItems | 可执行小任务数组 |
| aiMode | mock / real |
| createdAt | 创建时间 |
| updatedAt | 更新时间 |

### 4.3 Flashcard

闪卡对象。

```js
Flashcard = {
  id,
  materialId,
  front,
  back,
  status,
  createdAt,
  updatedAt
}
```

字段说明：

| 字段 | 说明 |
|---|---|
| id | 闪卡 ID |
| materialId | 关联资料 ID |
| front | 正面问题 |
| back | 背面答案 |
| status | new / mastered / review |
| createdAt | 创建时间 |
| updatedAt | 更新时间 |

### 4.4 QuizQuestion

测试题对象。

```js
QuizQuestion = {
  id,
  materialId,
  question,
  type,
  options,
  answer,
  explanation,
  createdAt,
  updatedAt
}
```

字段说明：

| 字段 | 说明 |
|---|---|
| id | 题目 ID |
| materialId | 关联资料 ID |
| question | 题干 |
| type | single / short |
| options | 选项数组，简答题可为空 |
| answer | 正确答案 |
| explanation | 答案解释 |
| createdAt | 创建时间 |
| updatedAt | 更新时间 |

### 4.5 AIConversation

成长问答记录。

```js
AIConversation = {
  id,
  goalId,
  relatedMaterialIds,
  messages,
  createdAt,
  updatedAt
}
```

消息结构：

```js
Message = {
  id,
  role,
  content,
  createdAt
}
```

字段说明：

| 字段 | 说明 |
|---|---|
| id | 对话 ID |
| goalId | 关联目标 ID，静态原型可先为空 |
| relatedMaterialIds | 本次回答参考的资料 ID 数组 |
| messages | 用户和 AI 的消息数组 |
| role | user / assistant |
| content | 消息内容 |
| createdAt | 创建时间 |
| updatedAt | 更新时间 |

## 5. localStorage 建议 key

```text
aiAgent.materials
aiAgent.materialSummaries
aiAgent.flashcards
aiAgent.quizQuestions
aiAgent.aiConversations
```

如果当前原型已有旧 key，先兼容旧 key，再逐步迁移。

## 6. 静态原型优先改动

第一批已完成：

```text
1. Material 增加 updatedAt。
2. MaterialSummary 扩展为 overview / keyPoints / difficulties / studyOrder / actionItems。
3. Flashcard 增加 materialId，停止依赖 source: material.title。
4. QuizQuestion 增加 materialId。
5. 删除资料时，同步删除对应闪卡和测试题。
```

第二批已完成或基本完成：

```text
1. 资料详情展示。
2. 成长问答记录保存。
3. 成长问答回答尽量基于已有资料摘要和知识点。
4. 真实 AI prompt 输入输出草案。
```

当前仍需迁移：

```text
1. 资料、整理结果、闪卡、测试题和问答仍保存于前端 localStorage。
2. 当前 AI 整理和成长问答仍是 mock AI。
3. 后端已存在目标/计划/打卡/进度模块骨架，但资料与 AI 模块 API 尚未实现。
4. 下一步应先实现资料 API 和 summarize mock service，再迁移闪卡、测试题和问答 API。
```

## 7. API 草案

### 7.1 资料 API

```text
GET    /api/materials?goalId=:goalId
POST   /api/materials
GET    /api/materials/:id
PUT    /api/materials/:id
DELETE /api/materials/:id
```

`POST /api/materials` 请求示例：

```json
{
  "goalId": "goal_001",
  "type": "text",
  "title": "英语口语练习方法",
  "content": "这里是用户粘贴的资料内容",
  "url": ""
}
```

删除资料时，后端需要同步处理：

```text
material_summaries
flashcards
quiz_questions
```

### 7.2 AI 整理 API

```text
POST /api/materials/:id/summarize
```

返回示例：

```json
{
  "materialId": "material_001",
  "overview": "资料摘要",
  "keyPoints": ["知识点 1", "知识点 2"],
  "difficulties": ["难点 1", "难点 2"],
  "studyOrder": ["先理解概念", "再做练习"],
  "actionItems": ["完成 10 分钟朗读", "整理 5 个例句"],
  "aiMode": "mock"
}
```

### 7.3 闪卡 API

```text
GET  /api/materials/:id/flashcards
POST /api/materials/:id/flashcards
PUT  /api/flashcards/:id
```

`POST /api/materials/:id/flashcards` 返回示例：

```json
{
  "cards": [
    {
      "materialId": "material_001",
      "front": "什么是刻意练习？",
      "back": "围绕明确目标、即时反馈和持续修正进行的练习方式。"
    }
  ]
}
```

### 7.4 测试题 API

```text
GET  /api/materials/:id/quiz
POST /api/materials/:id/quiz
```

`POST /api/materials/:id/quiz` 返回示例：

```json
{
  "questions": [
    {
      "materialId": "material_001",
      "type": "single",
      "question": "刻意练习最重要的特点是什么？",
      "options": ["重复次数多", "目标明确并持续反馈", "学习时间长"],
      "answer": "目标明确并持续反馈",
      "explanation": "刻意练习强调明确目标、及时反馈和持续修正。"
    }
  ]
}
```

### 7.5 成长问答 API

```text
POST /api/ask
GET  /api/conversations
GET  /api/conversations/:id
```

`POST /api/ask` 请求示例：

```json
{
  "goalId": "goal_001",
  "relatedMaterialIds": ["material_001"],
  "question": "这份资料最适合先学哪一部分？"
}
```

返回示例：

```json
{
  "answer": "建议先学习资料中的核心概念，再根据 actionItems 做小任务。",
  "relatedMaterialIds": ["material_001"],
  "aiMode": "mock"
}
```

## 8. 真实 AI prompt 草案

### 8.1 资料整理输入

```text
用户目标：
{goal}

资料标题：
{material.title}

资料内容：
{material.content}

请输出 JSON，包含 overview、keyPoints、difficulties、studyOrder、actionItems。
```

### 8.2 成长问答输入

```text
用户问题：
{question}

可参考资料摘要：
{materialSummaries}

回答要求：
1. 优先基于资料摘要和知识点回答。
2. 如果资料不足，明确说明“不确定”。
3. 给出一个可执行的下一步建议。
```

## 9. 模块验收标准

```text
1. 资料可以添加、查看、删除。
2. 资料整理结果结构化展示。
3. 资料整理结果至少包括摘要和知识点。
4. 闪卡和测试题通过 materialId 关联资料。
5. 删除资料时，对应闪卡和测试题同步删除。
6. 成长问答能基于已有资料给出 mock 回答。
7. 页面刷新后资料、摘要、闪卡、测试题和问答记录不丢失。
```

当前验收状态：

```text
MVP-0 静态原型已通过本地 smoke test：
1. 添加资料后生成结构化整理结果。
2. 闪卡和测试题均通过 materialId 关联资料。
3. 成长问答消息和会话能记录 relatedMaterialIds。
4. 删除资料后，关联闪卡、测试题和问答引用同步清理。
5. 刷新后资料、整理结果、闪卡、测试题和问答记录仍可保留。
6. 该模块已合入 dev，等待和陈模块一起跑完整演示流程。
```

## 10. 下一步迁移建议

```text
1. 在 backend/app 下补 materials router、schemas 和 store 方法。
2. 先实现 GET /api/materials、POST /api/materials、GET /api/materials/:id、DELETE /api/materials/:id。
3. 再实现 POST /api/materials/:id/summarize，先使用 mock AI service。
4. 最后迁移 flashcards、quiz 和 ask/conversations。
5. 前端保留 localStorage fallback，逐步切换到 API。
```
