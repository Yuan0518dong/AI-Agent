# RAG chunks 接口说明

更新时间：2026-07-15

适用分支：`feature/v3-agent-action-entry`

## 1. 文档目的

本文件说明资料模块新增的 RAG chunks 能力，包括数据表、切分逻辑、后端接口、测试方式和后续演进方向。

当前版本目标不是直接完成完整 RAG，而是先打通基础链路：

```text
资料 content -> 文本切分 -> embedding 入库 -> 语义 Top-K 检索 -> 返回相关片段
```

后续接入大模型时，可以继续演进为：

```text
用户问题 -> 检索相关 chunks -> 拼接上下文 -> 调用大模型 -> 返回答案和引用来源
```

## 2. 当前能力边界

当前已完成：

```text
1. 新增 material_chunks 数据表。
2. 支持按资料生成 chunks。
3. 支持查看某个资料的 chunks。
4. 支持基于 cosine similarity 的语义 Top-K 搜索。
5. 自动化测试和冒烟测试覆盖基础链路。
6. embedding 不可用时自动回退关键词搜索。
```

当前暂未完成：

```text
1. 暂未接入独立向量数据库。
2. 暂未接入真实 embedding 服务，当前使用确定性 MockEmbeddingProvider。
3. 暂未做前端 chunks 页面展示。
```

当前版本是在 SQLite 中保存 JSON 向量的第一阶段语义检索，不是完整向量数据库方案。

## 3. 数据表设计

### 3.1 material_chunks

用途：

```text
保存资料切分后的文本片段，为后续 RAG 检索和问答提供上下文来源。
```

表结构：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | TEXT PRIMARY KEY | chunk ID |
| material_id | TEXT NOT NULL | 所属资料 ID |
| chunk_index | INTEGER NOT NULL | chunk 在原资料中的顺序 |
| content | TEXT NOT NULL | chunk 文本内容 |
| keywords | TEXT NOT NULL | 关键词数组的 JSON 字符串 |
| embedding | TEXT NOT NULL | embedding 向量的 JSON 字符串，不通过 chunks API 返回 |
| created_at | TEXT NOT NULL | 创建时间 |
| updated_at | TEXT NOT NULL | 更新时间 |

外键关系：

```sql
FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE CASCADE
```

含义：

```text
删除资料时，对应 chunks 会被 SQLite 自动删除，避免产生孤儿数据。
```

## 4. 数据对象

API 返回使用前端友好的 camelCase：

```js
MaterialChunk = {
  id,
  materialId,
  chunkIndex,
  content,
  keywords,
  createdAt,
  updatedAt
}
```

搜索接口会额外返回：

```js
{
  materialTitle,
  goalId,
  score,
  searchMode
}
```

字段说明：

| 字段 | 说明 |
|---|---|
| materialId | chunk 所属资料 |
| chunkIndex | chunk 顺序，用于还原原文顺序 |
| content | 切分后的文本片段 |
| keywords | 从标题和 chunk 内容中提取的简单关键词 |
| materialTitle | 搜索结果所属资料标题 |
| goalId | 搜索结果所属目标 ID |
| score | semantic 模式为 cosine similarity；keyword 模式为关键词匹配分数 |
| searchMode | `semantic` 或 `keyword`，用于标识本条结果的检索策略 |

## 5. 切分逻辑

核心函数：

```python
split_material_content(content: str, max_chars: int = 320, overlap_chars: int = 40)
```

处理流程：

```text
1. 清洗多余空白字符。
2. 按中文标点、英文标点和换行切分文本。
3. 将短句合并成不超过 max_chars 的 chunk。
4. 如果单段文本超过 max_chars，则强制按长度切分。
5. 相邻 chunk 保留 overlap_chars 个字符的重叠内容。
```

为什么要保留 overlap：

```text
资料被切开后，句子之间可能存在上下文依赖。
保留少量重叠内容，可以减少语义断裂。
```

示例：

```text
原文：
第一段介绍 RAG。第二段介绍 chunks。第三段介绍检索。

切分后：
chunk 0: 第一段介绍 RAG。
chunk 1: 第二段介绍 chunks。
chunk 2: 第三段介绍检索。
```

## 6. API 说明

统一返回格式：

```json
{
  "code": 0,
  "message": "success",
  "data": {}
}
```

### 6.1 生成资料 chunks

接口：

```http
POST /api/materials/{material_id}/chunks
```

用途：

```text
根据指定资料的 content 或 url 生成 chunks，并保存到 material_chunks 表。
```

路径参数：

| 参数 | 说明 |
|---|---|
| material_id | 资料 ID |

处理逻辑：

```text
1. 查询资料是否存在。
2. 读取 material.content；如果 content 为空，则使用 material.url。
3. 调用 split_material_content() 进行切分。
4. 为每个 chunk 生成 id、chunkIndex、keywords、embedding 和时间字段。
5. 删除该资料旧 chunks。
6. 写入新 chunks。
7. 返回最新 chunks。
```

成功响应示例：

```json
{
  "code": 0,
  "message": "success",
  "data": [
    {
      "id": "chunk_xxx",
      "materialId": "material_xxx",
      "chunkIndex": 0,
      "content": "This material explains how goals, plans, and review tasks work.",
      "keywords": ["learning", "material", "this", "explains"],
      "createdAt": "2026-07-02T10:00:00+00:00",
      "updatedAt": "2026-07-02T10:00:00+00:00"
    }
  ]
}
```

错误响应：

```text
资料不存在：404 Material not found
```

### 6.2 查看资料 chunks

接口：

```http
GET /api/materials/{material_id}/chunks
```

用途：

```text
查看某个资料已经生成的 chunks。
```

成功响应：

```json
{
  "code": 0,
  "message": "success",
  "data": [
    {
      "id": "chunk_xxx",
      "materialId": "material_xxx",
      "chunkIndex": 0,
      "content": "chunk content",
      "keywords": ["chunk", "content"],
      "createdAt": "2026-07-02T10:00:00+00:00",
      "updatedAt": "2026-07-02T10:00:00+00:00"
    }
  ]
}
```

特殊情况：

```text
资料存在但还没有生成 chunks：返回空数组 []
资料不存在：404 Material not found
```

### 6.3 搜索资料 chunks

接口：

```http
GET /api/materials/search?query=review%20tasks&limit=5
```

用途：

```text
优先按 query embedding 与 chunk embedding 的 cosine similarity 返回 Top-K 片段；向量不可用或没有语义结果时使用关键词检索兜底。
```

查询参数：

| 参数 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| query | 是 | 无 | 搜索关键词，最少 1 个字符 |
| limit | 否 | 5 | 返回数量，范围 1 到 20 |

成功响应：

```json
{
  "code": 0,
  "message": "success",
  "data": [
    {
      "id": "chunk_xxx",
      "materialId": "material_xxx",
      "chunkIndex": 0,
      "content": "This material explains how goals, plans, and review tasks work.",
      "keywords": ["updated", "material", "review", "tasks"],
      "createdAt": "2026-07-02T10:00:00+00:00",
      "updatedAt": "2026-07-02T10:00:00+00:00",
      "materialTitle": "Updated material",
      "goalId": "goal_xxx",
      "score": 0.912341,
      "searchMode": "semantic"
    }
  ]
}
```

特殊情况：

```text
没有命中结果：返回空数组 []
query 为空：422 参数校验失败
limit 小于 1 或大于 20：422 参数校验失败
```

## 7. 当前检索评分规则

当前使用“语义优先、关键词兜底”的两级检索：

```text
1. 生成 query embedding。
2. 对已有 embedding 的 chunks 计算 cosine similarity。
3. 过滤低相似度结果，按相似度从高到低返回 Top-K。
4. Top-K 未满时用关键词结果补位，并按 chunk ID 去重。
5. provider 异常、query embedding 为空或历史 chunk 缺少 embedding 时保留关键词 fallback。
```

注意：

```text
MockEmbeddingProvider 只用于离线开发和稳定测试，不代表真实模型的召回质量。
后续接入真实 embedding provider 时不需要改动 SQLite 检索与 fallback 边界。
```

## 8. 测试方式

### 8.1 自动化测试

运行：

```powershell
python -m pytest backend/tests -v --basetemp .pytest_tmp_rag_chunks_final
```

已覆盖：

```text
1. 资料存在时 chunks 初始为空。
2. POST chunks 后可以生成切片。
3. GET chunks 可以读回切片。
4. 搜索关键词可以命中相关 chunk。
5. 无关关键词返回空数组。
6. 删除资料后，chunks 相关接口返回 404。
7. 不存在的资料生成 chunks 返回 404。
8. 关键词不重合但语义接近的查询可以命中目标 chunk。
9. embedding provider 失败时，chunk 生成和搜索仍可走关键词链路。
```

### 8.2 冒烟测试

运行：

```powershell
python backend/smoke_api.py
```

关注输出：

```text
chunk_count
chunk_readback
chunk_search_count
```

示例：

```text
'chunk_count': 1
'chunk_readback': True
'chunk_search_count': 1
```

## 9. 前端联调建议

前端后续可以增加 3 个动作：

```text
1. 在资料详情页增加“生成切片”按钮。
2. 在资料详情页展示 chunks 列表。
3. 在问答或搜索区域调用 /api/materials/search。
```

建议前端 API 方法：

```js
generateMaterialChunks(materialId)
listMaterialChunks(materialId)
searchMaterialChunks(query, limit)
```

## 10. 后续演进方向

建议下一步按这个顺序推进：

```text
1. 新增 POST /api/agent/ask。
2. ask 接口先复用 search_chunks() 找相关片段。
3. 将命中的 chunks 拼成 context。
4. 先返回 mock answer 和 references。
5. 再接入真实大模型。
6. 按真实数据规模评估是否从 SQLite JSON 向量迁移到独立向量索引。
```

完整 RAG 链路目标：

```text
资料入库
-> 文本切分
-> 生成 embedding
-> 向量检索
-> 上下文拼接
-> 大模型回答
-> 返回引用来源
```

## 11. 分工建议

陈继续负责：

```text
RAG chunks
检索接口
agent ask 接口
后端测试
后续大模型接入
```

赵继续负责：

```text
资料录入
资料摘要
闪卡和测验
资料模块前端展示
前端联调
```

这样可以减少冲突，同时两个人都能接触 AI 应用开发主线。
