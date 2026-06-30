# 资料与 AI 模块字段和 API 草案

更新时间：2026-06-30

## 1. 模块范围

本文件记录赵负责模块的字段和 API 草案，用于先强化静态原型，后续再迁移到后端和数据库。

赵负责主线：

```text
资料管理 -> AI 整理 -> 闪卡 / 测试题 -> 成长问答
```

当前阶段先使用：

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

## 3. 数据对象

### 3.1 Material

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

### 3.2 MaterialSummary

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

### 3.3 Flashcard

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

### 3.4 QuizQuestion

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

### 3.5 AIConversation

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

## 4. localStorage 建议 key

```text
aiAgent.materials
aiAgent.materialSummaries
aiAgent.flashcards
aiAgent.quizQuestions
aiAgent.aiConversations
```

如果当前原型已有旧 key，先兼容旧 key，再逐步迁移。

## 5. 静态原型优先改动

第一批优先：

```text
1. Material 增加 updatedAt。
2. MaterialSummary 扩展为 overview / keyPoints / difficulties / studyOrder / actionItems。
3. Flashcard 增加 materialId，停止依赖 source: material.title。
4. QuizQuestion 增加 materialId。
5. 删除资料时，同步删除对应闪卡和测试题。
```

第二批再补：

```text
1. 资料详情展示。
2. 成长问答记录保存。
3. 成长问答回答尽量基于已有资料摘要和知识点。
4. 真实 AI prompt 输入输出草案。
```

## 6. API 草案

### 6.1 资料 API

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

### 6.2 AI 整理 API

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

### 6.3 闪卡 API

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

### 6.4 测试题 API

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

### 6.5 成长问答 API

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

## 7. 真实 AI prompt 草案

### 7.1 资料整理输入

```text
用户目标：
{goal}

资料标题：
{material.title}

资料内容：
{material.content}

请输出 JSON，包含 overview、keyPoints、difficulties、studyOrder、actionItems。
```

### 7.2 成长问答输入

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

## 8. 模块验收标准

```text
1. 资料可以添加、查看、删除。
2. 资料整理结果结构化展示。
3. 资料整理结果至少包括摘要和知识点。
4. 闪卡和测试题通过 materialId 关联资料。
5. 删除资料时，对应闪卡和测试题同步删除。
6. 成长问答能基于已有资料给出 mock 回答。
7. 页面刷新后资料、摘要、闪卡、测试题和问答记录不丢失。
```
