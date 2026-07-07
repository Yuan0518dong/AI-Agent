# AI-Agent 简历与面试讲解稿

更新时间：2026-07-07

## 1. 项目一句话

```text
AI-Agent 是一个面向个人学习规划的可控学习智能体，能够聚合目标、任务、资料、问答、测试和复习状态，生成下一步学习建议，并在用户确认后把建议转成任务草稿或复习内容。
```

## 2. 架构图文字版

```text
前端工作台
-> 调用 AgentContext 接口读取当前学习状态
-> 调用 AgentDecision 接口生成结构化建议
-> 用户采纳 / 忽略 / 稍后处理
-> ActionLog 记录反馈和状态
-> Draft Execute 生成任务草稿 / 复盘草稿 / 补资料表单
-> 用户确认后写入 tasks / flashcards / materials
-> 下一轮 AgentContext 重新读回状态变化
-> 下一轮 AgentDecision 继续判断
```

核心拆层：

```text
AgentContext：Agent 能看见什么。
AgentDecision：Agent 如何判断下一步。
AgentActionLog：用户如何反馈，系统如何留下可追踪记录。
Draft Execute：建议如何进入真实学习流程，但不越过用户确认。
```

## 3. 简历 Bullet

推荐放在“项目经历”里：

```text
AI-Agent：个人主导的可控学习智能体项目
- 基于 FastAPI + SQLite + 原生 JavaScript 实现学习 Agent，覆盖目标管理、资料理解、任务规划、资料问答、闪卡复习、测试批改和进度统计等学习闭环。
- 设计 AgentContext / AgentDecision / AgentActionLog / Draft Execute 四层闭环，使 Agent 能聚合学习状态、输出结构化建议、记录用户反馈，并在用户确认后转入任务草稿或复习草稿。
- 实现用户确认式执行机制：高风险动作先生成草稿，不直接覆盖任务表或写入正式学习内容，降低自动化破坏用户计划的风险。
- 设计 mock 与 OpenAI-compatible LLM Provider 切换机制，保证本地测试稳定，同时支持真实模型联调和资料不足判断验收。
- 使用 pytest、smoke API 和 node --check 验证核心链路，其中上下文回读验收覆盖“确认写入 -> AgentContext 读回 -> AgentDecision 重新判断”。
```

如果简历空间很紧，可以压缩成 3 条：

```text
- 设计并实现可控学习 Agent，基于 AgentContext / AgentDecision / AgentActionLog / Draft Execute 串联目标、资料、任务、复习和测试状态。
- 实现用户确认式执行，Agent 建议先进入任务草稿 / 复盘草稿，确认后才写入正式 tasks / flashcards，避免自动化覆盖用户学习计划。
- 建立 mock / OpenAI-compatible LLM Provider 与 pytest + smoke 验证体系，覆盖资料问答、资料不足判断、ActionLog 状态流转和上下文回读闭环。
```

## 4. 1 分钟项目介绍

### 4.1 20 秒开场版

```text
这是一个基于 FastAPI、SQLite 和原生 JavaScript 的个人学习规划可控智能体。我把 Agent 拆成 Context、Decision、ActionLog 和 Draft Execute 四层，让它先聚合学习状态，再生成结构化建议，并记录用户反馈。为了避免自动化破坏用户计划，高风险动作先生成草稿，用户确认后才写入任务或闪卡；最后通过上下文回读验收，证明写入后下一轮 Agent 能继续基于新状态判断。
```

### 4.2 1 分钟展开版

```text
我做的 AI-Agent 是一个面向个人学习规划的可控学习智能体。它不是通用 AutoGPT，而是围绕学习场景，把目标、资料、任务、问答、测试、闪卡复习和进度统计串成一个闭环。

我把 Agent 拆成四层：AgentContext 负责聚合系统当前能看到的学习状态；AgentDecision 根据上下文输出结构化建议，比如补资料、生成复习卡片、重排任务；AgentActionLog 记录用户对建议的采纳、忽略、稍后和已执行状态；最后是 Draft Execute，把建议转成任务草稿、复盘草稿或补资料表单。

我没有让 Agent 直接自动改用户计划，因为学习计划会影响真实时间安排，所以高风险动作都先进入草稿态，用户确认后才写入正式任务或闪卡。最后我用 pytest 和 smoke 验证了闭环：用户确认写入后，下一轮 AgentContext 能读回状态变化，AgentDecision 也能基于新的复习队列继续判断。
```

## 5. 面试追问回答

### 5.1 为什么不让 Agent 自动执行？

```text
因为学习计划会影响用户真实时间安排，直接自动执行可能覆盖用户计划，所以我把执行拆成草稿态和确认态：Agent 先生成可见、可删除、可确认的草稿，用户确认后才写入正式任务或闪卡。这样既保留了 Agent 的主动建议能力，又保证了用户控制权和操作可追踪。
```

关键词：用户控制权、操作可追踪。

### 5.2 AgentContext 解决了什么问题？

```text
AgentContext 解决的是决策前的信息聚合问题。它把目标、任务、资料、问答、复习、测试和进度统一整理成结构化上下文。这样 Decision 层不是只看用户当前一句话，而是能知道用户现在有没有逾期任务、资料是否不足、是否有待复习闪卡，再生成下一步建议。
```

### 5.3 ActionLog 的价值是什么？

```text
ActionLog 的价值是让 Agent 的建议、用户反馈和执行状态可追踪。它会记录 Agent 当时基于什么上下文做判断、给出了什么建议、用户是采纳、忽略还是稍后处理，以及这个建议后续是否进入执行流程。这样 Agent 不只是一次性问答，而是有反馈记录，后续也方便复盘、调试和解释系统行为。
```

关键词：可追踪、可复盘、可解释。

### 5.4 怎么证明闭环真的成立？

```text
我做了上下文回读验收。用户确认写入正式闪卡后，我重新请求 AgentContext，验证 flashcardTotal 从写入前到写入后发生变化；然后再请求 AgentDecision，验证它能识别新的 review_queue。这个过程我用 pytest 和 smoke 都做了覆盖，所以系统不是只完成了一次写入，而是下一轮 Agent 能读回状态变化并继续判断。
```

### 5.5 为什么 Decision 先用 rule-based？

```text
因为第四版要先验证闭环可靠性，而不是追求模型效果。rule-based 决策稳定、可测试、方便定位问题；等上下文、日志和草稿执行链路稳定后，再把 Decision 层替换或增强为 LLM 输出，会更安全。
```

## 6. 你需要会复述的核心句

```text
这个项目最重要的不是“我接了大模型接口”，而是我设计了一个可控学习 Agent 闭环：先聚合上下文，再结构化决策，再记录用户反馈，最后用草稿态执行把建议接入真实学习流程，并通过上下文回读证明下一轮 Agent 能看到状态变化。
```
