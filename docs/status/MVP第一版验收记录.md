# MVP 第一版验收记录

验收日期：2026-07-02

验收基线：

```text
本地 dev 验收基线已合入 feature/material-ai-memory 最新成果。
当前远程 origin/dev 尚未推送本次验收基线。
```

## 1. 第一版定义

第一版是“可持久化的学习助手 MVP”，不是完整 LangChain / Agent 系统。

第一版目标是跑通：

```text
创建目标 -> 新增资料 -> 资料整理 -> 闪卡/测试题 -> 行动计划 -> 今日打卡 -> 查看进度 -> 刷新后数据仍在
```

第一版暂不包含：

```text
LangChain
真实 Agent 循环
RAG
向量数据库
PDF 上传解析
登录注册
正式部署
```

## 2. 验收结果

自动化验证：

```text
python -m pytest backend/tests -v
结果：10 passed

python backend/smoke_api.py
结果：通过
```

浏览器主流程验证：

```text
1. 创建成长目标：通过
2. 自动生成行动计划：通过
3. 新增资料：通过
4. 生成资料摘要：通过
5. 生成闪卡和测试题：通过
6. 今日任务打卡：通过
7. 查看进度：通过
8. 刷新后读回目标、资料、摘要：通过
```

## 3. 验收中修复的问题

问题：

```text
今日任务打卡时，前端异步事件处理在 await 之后继续读取 event.currentTarget，
浏览器可能将 currentTarget 置空，导致页面错误：
Cannot set properties of null (setting 'checked')
```

处理：

```text
在 app/modules/goals.js 中先保存 checkbox 和 checked，再执行 await。
```

判断：

```text
该问题影响第一版主流程“今日任务打卡”，属于验收中需要修复的问题。
```

## 4. 当前能力边界

已实现：

```text
目标、任务、打卡、进度：FastAPI + SQLite
资料、摘要、闪卡、测试题：FastAPI + SQLite
资料模块前端新增、编辑、删除、生成、读回均已接 API
README 已包含启动、测试、SQLite 基础说明
GitHub Actions 后端测试工作流已存在
```

仍是 mock / rule-based：

```text
资料摘要生成
闪卡生成
测试题生成
成长问答
行动计划生成逻辑
```

记忆功能说明：

```text
第一版“记忆”指闪卡复习和简单测试题，不是 LangChain memory，也不是 Agent 长期记忆。
```

## 5. 剩余问题

P0：

```text
暂无。
```

P1：

```text
1. 需要将本地 dev 验收基线推送或通过 PR 合入 origin/dev。
2. 需要两人共同确认第一版演示脚本和 README 是否足够清楚。
```

P2：

```text
1. favicon 404 控制台噪声。
2. 资料编辑时暂未单独编辑 goalId 归属。
3. 真实 AI / LangChain / RAG 放到第二版。
```

## 6. 结论

```text
本地 dev 验收基线已通过第一版主流程验收。
建议先同步给同事 review，再决定是否推送 origin/dev 和准备 main 合并判断。
```
