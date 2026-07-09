# AI-Agent 简历与面试讲解稿

更新时间：2026-07-08

## 1. 项目一句话

```text
AI-Agent 是一个面向个人学习规划的可控学习智能体，能够聚合目标、任务、资料、问答、测试和复习状态，生成下一步学习建议，并在用户确认后把建议转成任务草稿或复习内容。
```

第五版增强版：

```text
AI-Agent 是一个面向学习规划场景的可控 AI Agent，支持状态感知、结构化决策、模型输出评审、工具风险分层、用户反馈记忆、运行轨迹记录和 LLM JSON 决策兜底回退。
```

## 2. 架构图文字版

```text
前端工作台
-> 调用 AgentContext 接口读取当前学习状态
-> 调用 AgentDecision 接口生成结构化建议
-> Decision Guard 评审 LLM 结构化输出，非法动作回退，高风险动作强制确认
-> Tool Registry 为建议补充工具名、风险等级、草稿态和执行目标
-> 用户采纳 / 忽略 / 稍后处理
-> ActionLog 记录反馈和状态
-> AgentRun 记录本轮上下文快照、决策快照和反馈摘要
-> Draft Execute 生成任务草稿 / 复盘草稿 / 补资料表单
-> 用户确认后写入 tasks / flashcards / materials
-> 下一轮 AgentContext 重新读回状态变化
-> 下一轮 AgentDecision 继续判断
-> LLM JSON Decision 可增强结构化决策，失败时回退 rule-based
```

核心拆层：

```text
AgentContext：Agent 能看见什么。
AgentDecision：Agent 如何判断下一步。
Decision Guard：模型输出能不能进入系统，是否需要回退或修正。
Tool Registry：Agent 建议要调用什么工具、风险多高、是否只能生成草稿。
AgentActionLog：用户如何反馈，系统如何留下可追踪记录。
AgentRun：一次 Agent 运行当时看到了什么、为什么建议、后来反馈如何。
Draft Execute：建议如何进入真实学习流程，但不越过用户确认。
```

## 3. 简历 Bullet

推荐放在“项目经历”里：

```text
AI-Agent：个人主导的可控学习智能体项目
- 基于 FastAPI + SQLite + 原生 JavaScript 实现学习 Agent，覆盖目标管理、资料理解、任务规划、资料问答、闪卡复习、测试批改和进度统计等学习闭环。
- 设计 AgentContext / AgentDecision / AgentActionLog / Draft Execute 四层闭环，使 Agent 能聚合学习状态、输出结构化建议、记录用户反馈，并在用户确认后转入任务草稿或复习草稿。
- 构建 AgentRun 与 Tool Registry 机制，为每次 Agent 运行保留上下文/决策快照，并为 proposedActions 标注工具名、风险等级、草稿态和执行目标。
- 增加 LLM JSON Decision hybrid 与 Decision Guard，支持真实模型输出结构化建议；当 JSON 解析失败、字段缺失或 action 非法时回退 rule-based，高风险动作漏标确认时自动修正为用户确认。
- 实现用户确认式执行机制：高风险动作先生成草稿，不直接覆盖任务表或写入正式学习内容，降低自动化破坏用户计划的风险。
- 设计 mock 与 OpenAI-compatible LLM Provider 切换机制，保证本地测试稳定，同时支持真实模型联调和资料不足判断验收。
- 使用 pytest、smoke API 和 node --check 验证核心链路，其中上下文回读验收覆盖“确认写入 -> AgentContext 读回 -> AgentDecision 重新判断”。
```

如果简历空间很紧，可以压缩成 3 条：

```text
- 设计并实现可控学习 Agent，基于 AgentContext / AgentDecision / AgentActionLog / Draft Execute 串联目标、资料、任务、复习和测试状态。
- 引入 AgentRun、Tool Registry 和 Feedback Memory，为 Agent 建议提供运行轨迹、工具风险分层和用户反馈记忆。
- 建立 mock / OpenAI-compatible LLM Provider、LLM JSON Decision hybrid 与 Decision Guard，模型结构化决策失败时回退 rule-based，高风险动作强制用户确认，并通过 pytest + smoke 验证。
```

## 4. 1 分钟项目介绍

### 4.1 20 秒开场版

```text
这是一个基于 FastAPI、SQLite 和原生 JavaScript 的个人学习规划可控智能体。我把 Agent 拆成 Context、Decision、ActionLog 和 Draft Execute 四层，让它先聚合学习状态，再生成结构化建议，并记录用户反馈。为了避免自动化破坏用户计划，高风险动作先生成草稿，用户确认后才写入任务或闪卡；最后通过上下文回读验收，证明写入后下一轮 Agent 能继续基于新状态判断。
```

第五版 20 秒版：

```text
这是一个面向学习规划的可控 AI Agent。我在原有 Context、Decision、ActionLog 和草稿执行闭环上继续加入 AgentRun、Decision Guard、Tool Registry 和 LLM JSON Decision hybrid，让每次建议都能追踪上下文、评审模型输出、映射到受控工具，并在结构化决策失败时回退规则决策。
```

### 4.2 1 分钟展开版

```text
我做的 AI-Agent 是一个面向个人学习规划的可控学习智能体。它不是通用 AutoGPT，而是围绕学习场景，把目标、资料、任务、问答、测试、闪卡复习和进度统计串成一个闭环。

我把 Agent 拆成四层：AgentContext 负责聚合系统当前能看到的学习状态；AgentDecision 根据上下文输出结构化建议，比如补资料、生成复习卡片、重排任务；AgentActionLog 记录用户对建议的采纳、忽略、稍后和已执行状态；最后是 Draft Execute，把建议转成任务草稿、复盘草稿或补资料表单。

我没有让 Agent 直接自动改用户计划，因为学习计划会影响真实时间安排，所以高风险动作都先进入草稿态，用户确认后才写入正式任务或闪卡。最后我用 pytest 和 smoke 验证了闭环：用户确认写入后，下一轮 AgentContext 能读回状态变化，AgentDecision 也能基于新的复习队列继续判断。
```

### 4.3 第五版 1 分钟展开版

```text
第五版我重点做的是把这个学习 Agent 从“能给建议”升级成“可追踪、可校验、可回退”的 Agent 系统。

在原来的 AgentContext、AgentDecision、ActionLog 和草稿执行基础上，我新增了几层能力：AgentRun 用来记录一次智能体运行的上下文快照、决策快照和反馈摘要；Tool Registry 把原来的 actionType 映射成受控工具，并标注 riskLevel、draftOnly 和 applyTarget；LLM JSON Decision hybrid 让真实模型可以输出结构化决策；Decision Guard 则负责评审模型输出，如果 JSON 解析失败、字段缺失或 action 不合法，就回退到 rule-based，如果高风险动作漏标确认，就强制改成用户确认。

这个设计的核心取舍是，我没有为了“智能”让模型直接执行，而是让模型只能提出可校验的 proposedActions，再经过 Decision Guard、Tool Registry 和用户确认流程。最后我用 pytest 和 smoke 覆盖了反馈记忆、AgentRun、Tool Registry、Decision Guard、hybrid 回退和上下文回读，证明它不是一次性问答，而是一个可控闭环。
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

### 5.6 第五版为什么要做 AgentRun？

```text
ActionLog 记录的是某个建议的用户反馈，而 AgentRun 记录的是一次完整智能体运行：当时 AgentContext 看到了什么、AgentDecision 为什么给出这个建议、后续反馈摘要是什么。这样系统可以解释“这次建议是怎么来的”，而不是只保存一个按钮点击记录。对调试、验收和面试讲解都更清楚。
```

关键词：运行轨迹、快照、可复盘。

### 5.7 Tool Registry 解决了什么问题？

```text
Tool Registry 解决的是 Agent 动作边界问题。原来 proposedActions 只有 actionType，例如 create_flashcards 或 reschedule_tasks；第五版保留这些旧 actionType，但额外映射出 toolName、riskLevel、draftOnly 和 applyTarget。这样既不破坏旧执行链路，又能让系统知道哪些动作低风险、哪些必须进入草稿态、哪些需要用户确认。
```

关键词：兼容式演进、风险分层、工具边界。

### 5.8 LLM JSON Decision hybrid 为什么需要回退？

```text
真实模型输出不一定稳定，可能 JSON 解析失败、缺字段，或者返回系统不支持的 actionType。所以我没有让 LLM 直接控制系统，而是让它输出结构化建议，再由 Decision Guard 评审；非法输出回退 rule-based，高风险但漏标确认的动作会被修正为需要用户确认，之后再进入 Tool Registry 风险映射。这样模型是增强层，不是单点风险。
```

关键词：结构化输出、规则兜底、模型不可控风险。

### 5.9 Decision Guard 和 Tool Registry 有什么区别？

```text
Decision Guard 解决的是模型输出治理问题：模型输出能不能进入系统，非法 action 要不要回退，高风险动作是否漏了确认。Tool Registry 解决的是工具边界问题：合法 action 对应哪个工具、风险多高、是否只能草稿执行。简单说，Guard 是入口评审，Registry 是工具规则。
```

关键词：输出治理、入口评审、工具规则。

### 5.10 这个项目体现了什么工程化思维？

```text
第五版不是推倒重做，而是兼容式迭代。我保留已有 actionType、rule-based 决策和草稿执行链路，在外层逐步增加 AgentRun、Decision Guard、Tool Registry、Feedback Memory 和 LLM JSON Decision hybrid。这样旧流程继续稳定，新能力逐步接管解释、校验和展示，每一步都有测试和 smoke 证明没有破坏原闭环。
```

关键词：兼容式演进、稳定基线、持续验证。

## 6. 你需要会复述的核心句

```text
这个项目最重要的不是“我接了大模型接口”，而是我设计了一个可控学习 Agent 闭环：先聚合上下文，再结构化决策，再记录用户反馈，最后用草稿态执行把建议接入真实学习流程，并通过上下文回读证明下一轮 Agent 能看到状态变化。
```

第五版复述句：

```text
第五版的核心是把 Agent 从“能给建议”升级成“可追踪、可校验、可回退”：AgentRun 记录运行轨迹，Decision Guard 评审模型输出，Tool Registry 控制工具风险，Feedback Memory 读取用户反馈，LLM JSON Decision 只作为增强层，失败时回退 rule-based。
```
