# 第一阶段数据对象与 API 草案

更新时间：2026-06-30

适用阶段：MVP-0 到 MVP-1

后端方向：Python，建议使用 FastAPI

## 1. 文档目的

本文件用于明确第一阶段需要的数据对象、字段命名、API 草案和前后端协作边界。

第一阶段优先服务主线：

```text
目标 -> 资料 -> AI 整理 -> 计划 -> 打卡 -> 进度
```

当前静态原型仍可继续使用：

```text
app/index.html
app/app.js
app/styles.css
```

MVP-0 阶段先用 `localStorage` 和 mock 逻辑跑通流程。MVP-1 阶段再把这些数据对象迁移到 Python 后端、数据库和真实 API。

## 2. 命名约定

前端 JavaScript 当前使用 camelCase：

```js
dailyMinutes
createdAt
goalId
```

Python 后端和数据库建议使用 snake_case：

```python
daily_minutes
created_at
goal_id
```

第一阶段建议：

```text
1. 前端原型里可以继续使用 camelCase，减少改动成本。
2. 后端 API 文档使用 snake_case，贴近 Python 和数据库习惯。
3. 后续联调时，在前端 API 层做字段转换。
```

统一 ID 命名：

```text
id
goal_id
material_id
task_id
```

统一时间字段：

```text
created_at
updated_at
completed_at
checked_at
```

统一接口返回格式：

```json
{
  "code": 0,
  "message": "success",
  "data": {}
}
```

错误返回格式：

```json
{
  "code": 400,
  "message": "目标名称不能为空",
  "data": null
}
```

## 3. 陈负责模块

陈负责：

```text
目标管理 -> 行动计划 -> 今日任务 -> 打卡 -> 进度统计
```

### 3.1 Goal 成长目标

用途：

```text
记录用户想完成的学习或成长目标。
```

前端原型字段：

```js
{
  id: "goal_001",
  name: "准备英语四级",
  subject: "英语",
  level: "有基础",
  deadline: "2026-07-30",
  dailyMinutes: 60,
  notes: "听力和作文比较弱",
  createdAt: "2026-06-30T09:00:00.000Z",
  updatedAt: "2026-06-30T09:00:00.000Z"
}
```

后端字段草案：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| id | string | 是 | 目标 ID |
| name | string | 是 | 目标名称 |
| subject | string | 是 | 学习科目或方向 |
| level | string | 是 | 当前水平 |
| deadline | date | 是 | 目标截止日期 |
| daily_minutes | int | 是 | 每天可投入分钟数 |
| notes | string | 否 | 重点难点说明 |
| created_at | datetime | 是 | 创建时间 |
| updated_at | datetime | 是 | 更新时间 |

### 3.2 PlanTask 行动计划任务

用途：

```text
记录由目标生成的每日任务，支撑今日任务、打卡和进度统计。
```

前端原型字段：

```js
{
  id: "task_001",
  goalId: "goal_001",
  title: "第 1 天：学习听力核心题型",
  detail: "60 分钟学习，完成 1 次复述和 1 组闪卡复习。",
  date: "2026-06-30",
  priority: "normal",
  done: false,
  completedAt: null,
  createdAt: "2026-06-30T09:00:00.000Z",
  updatedAt: "2026-06-30T09:00:00.000Z"
}
```

后端字段草案：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| id | string | 是 | 任务 ID |
| goal_id | string | 是 | 所属目标 ID |
| title | string | 是 | 任务标题 |
| detail | string | 否 | 任务说明 |
| date | date | 是 | 任务日期 |
| priority | string | 否 | 优先级，默认 normal |
| done | bool | 是 | 是否完成 |
| completed_at | datetime | 否 | 完成时间 |
| created_at | datetime | 是 | 创建时间 |
| updated_at | datetime | 是 | 更新时间 |

### 3.3 CheckInRecord 打卡记录

用途：

```text
记录用户每次完成或取消完成任务的行为。
MVP-0 可以先只存在于 task.done 和 task.completedAt 中。
MVP-1 再考虑单独保存打卡记录。
```

前端原型可先不单独保存，后端字段草案：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| id | string | 是 | 打卡记录 ID |
| goal_id | string | 是 | 所属目标 ID |
| task_id | string | 是 | 所属任务 ID |
| date | date | 是 | 打卡日期 |
| status | string | 是 | completed 或 canceled |
| checked_at | datetime | 是 | 操作时间 |

### 3.4 Progress 进度统计

用途：

```text
展示目标推进情况。
Progress 不一定单独入库，可以根据任务实时计算。
```

接口返回字段草案：

```json
{
  "goal_id": "goal_001",
  "goal_name": "准备英语四级",
  "total_tasks": 7,
  "completed_tasks": 3,
  "completion_rate": 43,
  "today_total": 1,
  "today_completed": 1,
  "material_count": 2,
  "flashcard_count": 8
}
```

## 4. 赵负责模块

赵负责：

```text
资料管理 -> AI 整理 -> 闪卡 / 测试题 -> 成长问答
```

### 4.1 Material 成长资料

用途：

```text
保存用户添加的文本资料、网页链接或 PDF 摘录。
```

前端原型字段：

```js
{
  id: "material_001",
  title: "英语听力技巧",
  type: "文本",
  content: "资料正文内容",
  createdAt: "2026-06-30T09:00:00.000Z",
  updatedAt: "2026-06-30T09:00:00.000Z"
}
```

后端字段草案：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| id | string | 是 | 资料 ID |
| title | string | 是 | 资料标题 |
| type | string | 是 | text、url、pdf_excerpt |
| content | string | 是 | 资料内容 |
| created_at | datetime | 是 | 创建时间 |
| updated_at | datetime | 是 | 更新时间 |

### 4.2 MaterialSummary 资料整理结果

用途：

```text
保存 AI 或 mock AI 对资料的结构化整理结果。
```

前端原型字段：

```js
{
  materialId: "material_001",
  overview: "这份资料主要讲英语听力题型和练习方法。",
  keyPoints: ["听前预判", "关键词定位", "错题复盘"],
  difficulties: ["长对话信息量较大", "同义替换容易干扰判断"],
  studyOrder: ["先理解题型", "再练关键词", "最后做整套听力"],
  actionItems: ["每天听 20 分钟", "整理 5 个高频表达"],
  createdAt: "2026-06-30T09:00:00.000Z"
}
```

后端字段草案：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| material_id | string | 是 | 所属资料 ID |
| overview | string | 是 | 摘要 |
| key_points | list[string] | 是 | 关键知识点 |
| difficulties | list[string] | 否 | 难点说明 |
| study_order | list[string] | 否 | 建议学习顺序 |
| action_items | list[string] | 否 | 可执行小任务 |
| created_at | datetime | 是 | 创建时间 |

### 4.3 Flashcard 闪卡

用途：

```text
根据资料知识点生成记忆卡片。
```

后端字段草案：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| id | string | 是 | 闪卡 ID |
| material_id | string | 是 | 来源资料 ID |
| front | string | 是 | 卡片正面 |
| back | string | 是 | 卡片背面 |
| status | string | 是 | new、known、review |
| created_at | datetime | 是 | 创建时间 |
| updated_at | datetime | 是 | 更新时间 |

### 4.4 QuizQuestion 测试题

用途：

```text
根据资料生成简单练习题。
```

后端字段草案：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| id | string | 是 | 题目 ID |
| material_id | string | 是 | 来源资料 ID |
| question | string | 是 | 题干 |
| answer | string | 是 | 参考答案 |
| type | string | 是 | short_answer、choice、blank |
| created_at | datetime | 是 | 创建时间 |

### 4.5 AIConversation 成长问答

用途：

```text
保存用户围绕目标和资料进行的问答记录。
```

后端字段草案：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| id | string | 是 | 对话 ID |
| goal_id | string | 否 | 关联目标 ID |
| related_material_ids | list[string] | 否 | 关联资料 ID 列表 |
| messages | list[object] | 是 | 消息列表 |
| created_at | datetime | 是 | 创建时间 |
| updated_at | datetime | 是 | 更新时间 |

消息对象草案：

```json
{
  "role": "user",
  "content": "这个知识点是什么意思？",
  "created_at": "2026-06-30T09:00:00Z"
}
```

## 5. 陈负责 API 草案

### 5.1 目标管理

获取目标列表：

```http
GET /api/goals
```

创建目标：

```http
POST /api/goals
```

请求体：

```json
{
  "name": "准备英语四级",
  "subject": "英语",
  "level": "有基础",
  "deadline": "2026-07-30",
  "daily_minutes": 60,
  "notes": "听力和作文比较弱"
}
```

获取目标详情：

```http
GET /api/goals/{goal_id}
```

修改目标：

```http
PUT /api/goals/{goal_id}
```

删除目标：

```http
DELETE /api/goals/{goal_id}
```

删除规则：

```text
删除目标时，同步删除该目标下的计划任务和打卡记录。
```

### 5.2 行动计划

为目标生成计划：

```http
POST /api/goals/{goal_id}/plans
```

请求体：

```json
{
  "days": 7,
  "regenerate": true
}
```

说明：

```text
MVP-1 可以先用规则生成计划，不一定调用真实 AI。
```

获取目标下的任务：

```http
GET /api/goals/{goal_id}/tasks
```

获取今日任务：

```http
GET /api/tasks/today
```

### 5.3 打卡

完成任务：

```http
POST /api/tasks/{task_id}/checkin
```

请求体：

```json
{
  "done": true
}
```

取消完成：

```http
POST /api/tasks/{task_id}/checkin
```

请求体：

```json
{
  "done": false
}
```

返回示例：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "id": "task_001",
    "done": true,
    "completed_at": "2026-06-30T10:00:00Z"
  }
}
```

### 5.4 进度统计

获取整体进度：

```http
GET /api/progress
```

获取某个目标进度：

```http
GET /api/goals/{goal_id}/progress
```

## 6. 赵负责 API 草案

### 6.1 资料管理

获取资料列表：

```http
GET /api/materials
```

创建资料：

```http
POST /api/materials
```

请求体：

```json
{
  "title": "英语听力技巧",
  "type": "text",
  "content": "资料正文内容"
}
```

获取资料详情：

```http
GET /api/materials/{material_id}
```

删除资料：

```http
DELETE /api/materials/{material_id}
```

删除规则：

```text
删除资料时，同步删除对应的 summary、flashcards、quiz_questions。
```

### 6.2 AI 整理

整理资料：

```http
POST /api/materials/{material_id}/summarize
```

返回示例：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "material_id": "material_001",
    "overview": "这份资料主要讲英语听力题型和练习方法。",
    "key_points": ["听前预判", "关键词定位"],
    "difficulties": ["同义替换容易干扰判断"],
    "study_order": ["先理解题型", "再做专项练习"],
    "action_items": ["每天听 20 分钟"]
  }
}
```

说明：

```text
MVP-1 可以先接 mock AI service，接口保持不变。
后续切换真实大模型时，不影响前端调用。
```

### 6.3 闪卡和测试题

获取闪卡：

```http
GET /api/flashcards
```

更新闪卡状态：

```http
PUT /api/flashcards/{flashcard_id}
```

请求体：

```json
{
  "status": "known"
}
```

获取测试题：

```http
GET /api/quizzes
```

根据资料生成练习：

```http
POST /api/materials/{material_id}/practice
```

说明：

```text
practice 接口可以同时生成 flashcards 和 quiz_questions。
```

### 6.4 成长问答

发送问题：

```http
POST /api/chat
```

请求体：

```json
{
  "goal_id": "goal_001",
  "related_material_ids": ["material_001"],
  "question": "这个知识点是什么意思？"
}
```

返回示例：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "answer": "这个知识点可以先理解为......",
    "conversation_id": "conversation_001"
  }
}
```

获取对话记录：

```http
GET /api/chat/conversations
```

获取对话详情：

```http
GET /api/chat/conversations/{conversation_id}
```

## 7. Python 后端模块建议

如果后端使用 FastAPI，建议目录先按模块拆：

```text
backend/
  app/
    main.py
    models/
      goal.py
      material.py
      task.py
      practice.py
      chat.py
    routers/
      goals.py
      materials.py
      tasks.py
      progress.py
      chat.py
    services/
      plan_service.py
      summary_service.py
      practice_service.py
      progress_service.py
      ai_service.py
    schemas/
      goal.py
      material.py
      task.py
      progress.py
      chat.py
```

第一阶段可以先不急着建完整目录，但 API 和对象命名尽量按这个方向设计。

## 8. MVP-0 到 MVP-1 迁移方式

MVP-0 当前做法：

```text
浏览器页面 -> app.js state -> localStorage
```

MVP-1 目标做法：

```text
浏览器页面 -> fetch API -> Python FastAPI -> 数据库
```

建议迁移顺序：

```text
1. 先把 app.js 里的数据对象字段补齐。
2. 再把 mock 逻辑整理成函数，例如 generatePlan、summarizeContent。
3. 后端先实现 goals、tasks、progress。
4. 前端把目标、任务、打卡从 localStorage 改成 API。
5. 后端再实现 materials、summary、flashcards、chat。
6. 最后替换 mock AI 为真实大模型接口。
```

## 9. 第一阶段验收标准

数据对象验收：

```text
1. Goal、PlanTask、Material、MaterialSummary 等核心对象字段清晰。
2. 陈和赵负责的对象能互相关联。
3. ID、时间字段、状态字段命名统一。
4. 前端对象和后端对象之间能找到明确对应关系。
```

API 草案验收：

```text
1. 能支持创建目标、添加资料、生成计划、打卡和查看进度。
2. 能支持资料整理、生成闪卡、生成测试题和成长问答。
3. 每个接口都能说明请求方式、路径和核心请求体。
4. mock AI 和真实 AI 可以使用同一套接口。
```

演示流程验收：

```text
1. 创建目标。
2. 添加资料。
3. 整理资料。
4. 生成计划。
5. 今日任务打卡。
6. 查看进度变化。
```

