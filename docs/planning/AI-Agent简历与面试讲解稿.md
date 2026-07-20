# AI-Agent 第七版简历与面试讲解稿

更新时间：2026-07-20

适用方向：Agent 应用后端、AI 应用工程、Python/FastAPI 后端。

使用原则：简历使用 `docs/portfolio/简历材料.md` 的 3-4 条 Bullet；面试根据时长选择 20 秒、1 分钟或 3 分钟版本。离线 Mock、真实 DeepSeek、公开 Demo 三类证据必须分开表述。

## 1. 面试前速记卡

| 项目 | 当前证据 |
|---|---|
| 定位 | 面向个人学习规划的可控、可恢复多步 Agent |
| 技术栈 | FastAPI、原生 JavaScript、SQLAlchemy、Alembic、PostgreSQL/pgvector、SQLite |
| 资料链路 | PDF/Markdown/TXT 内存解析，原文件不落盘，保留页码/标题/段落定位 |
| 检索 | keyword 与 dense 各 Top 20，halfvec HNSW Top 100 候选，全精度 vector(2048) 重排，RRF `k=60` |
| Agent | Context -> Decision -> Guard -> Tool -> Observation，多 Step 持久化，支持确认恢复、拒绝和取消 |
| 安全 | 数据库会话、Origin 校验、原子限流、Decision Guard、草稿态写入、敏感字段脱敏 |
| 自动化 | 150 passed、4 skipped；PostgreSQL 集成 4 passed；Playwright 1 passed |
| 离线指标 | hybrid Recall@5=`0.94`；资料不足 F1=`0.8571` |
| 真实 Agent | 20 场景 x 3，60 Run；工具选择 `0.6333`、确认完整性 `0.5556`、恢复 `1.0` |
| 真实用量 | 107 请求，prompt/completion Token `237971/33611`，估算 `$0.042727` |

## 2. 项目介绍

### 2.1 一句话版本

```text
AI-Agent 是一个面向个人学习规划的可控多步智能体，把资料摄取、混合检索、带引用问答和需要用户确认的 Agent 执行串成一个可观察、可恢复的学习闭环。
```

### 2.2 20 秒版本

```text
我做的是一个 FastAPI 学习 Agent。用户可以上传 PDF 或 Markdown，系统经过切分、向量化和混合检索完成带引用问答；Agent 再根据目标、任务和资料状态循环执行决策与工具调用。高风险写入必须经过用户确认，运行过程会持久化每个 Step，支持恢复、拒绝和取消。
```

### 2.3 1 分钟版本

```text
AI-Agent 是我个人主导迭代的学习规划智能体，目标不是做通用 AutoGPT，而是在一个垂直场景里把 Agent 的数据、检索、执行和安全边界真正闭环。

后端使用 FastAPI、SQLAlchemy、PostgreSQL 和 pgvector。资料上传支持 PDF、Markdown 和 TXT，原文件只在内存中解析，保存提取文本和页码或标题定位。检索同时保留 keyword、dense 和 RRF hybrid；PostgreSQL 先用 halfvec HNSW 召回 Top 100，再按原始 2048 维向量重排。

Agent Runtime 围绕 Context、Decision、Decision Guard、Tool 和 Observation 多步循环，每一步都持久化。高风险动作先生成草稿，用户确认后才写入任务或闪卡，并在同一个 Run 中恢复执行。

我还建立了固定评测和自动化门禁。离线 hybrid Recall@5 是 0.94，资料不足 F1 是 0.8571；真实 DeepSeek 做了 20 场景各 3 次评测。真实工具选择和确认完整性并不高，所以我保留了全部失败数据，没有用 Mock 结果替代真实结论。
```

### 2.4 3 分钟版本

```text
这个项目解决的是个人学习过程中信息和行动割裂的问题：资料、目标、任务、问答、闪卡和测试通常分别存在，普通聊天机器人也只回答当前问题，不会可靠地把建议接入后续学习流程。

我把系统分成三条主链路。第一条是资料和 RAG：用户上传 PDF、Markdown 或 TXT，后端在内存中做安全校验和文本提取，持久化 chunks、embedding 和来源定位；问答时分别执行关键词检索、向量检索和 RRF 融合，没有充分引用就由服务端直接拒答。

第二条是 Agent Runtime：AgentContext 聚合目标、任务、资料和复习状态；Decision Provider 产生结构化决策；Decision Guard 校验 JSON、动作范围和确认要求；Tool Registry 定义工具风险；工具结果作为 Observation 回灌下一轮 Decision。AgentRun 和 AgentStep 保存完整轨迹，支持 completed、failed、max_steps、waiting_confirmation 和 cancelled 等终态。

第三条是工程安全和交付：认证使用数据库会话而不是客户端可信用户 ID，写请求校验 Origin，限流和模型额度使用 PostgreSQL 原子更新。高风险 Agent 写入先进入草稿，确认后在同一 Run 中恢复，并通过幂等键防止重复写入。CI 包含 Ruff、敏感信息扫描、PostgreSQL/pgvector 和 Playwright。

评测方面，我建立了 10 份资料、50 条中文检索查询、32 条问答和 20 个 Agent 场景。离线 hybrid Recall@5 是 0.94，资料不足 F1 是 0.8571。真实 DeepSeek 运行了 60 个 Run，产生 107 次请求，估算成本 0.042727 美元。真实工具选择是 0.6333、确认完整性是 0.5556，说明当前提示词和工具描述仍需优化；这个结果反而帮助我证明评测不是只挑成功样例。
```

## 3. 架构讲解

```text
同源浏览器
  -> FastAPI 路由
  -> 数据库会话 / Origin 校验 / PostgreSQL 原子限流
  -> 资料上传与解析
       -> chunks + 来源定位
       -> keyword Top 20
       -> halfvec HNSW Top 100 -> vector(2048) 重排 Top 20
       -> RRF hybrid -> 带引用问答 / grounded-refusal
  -> Agent Runtime
       -> Context -> Decision -> Guard -> Tool -> Observation
       -> AgentRun / AgentStep / ActionLog 持久化
       -> waiting_confirmation -> 接受恢复 / 拒绝 / 取消
  -> SQLite（本地快速测试）或 PostgreSQL + pgvector（部署与集成测试）
```

讲架构时优先解释三个设计取舍：

1. 模型只负责受约束的结构化决策，不能绕过 Guard 和工具规则。
2. 检索和拒答由服务端保留确定性边界，不能让模型常识冒充资料证据。
3. 高风险写入必须暂停并等待确认，恢复时继续原 Run，而不是重新生成一次不相关决策。

## 4. 指标如何表述

### 4.1 可以直接说

```text
固定离线检索集包含 10 份资料和 50 条中文查询，hybrid Recall@5 为 0.94；32 条问答集上的资料不足 Precision 为 1.0、Recall 为 0.75、F1 为 0.8571。
```

```text
真实 DeepSeek Agent 评测包含 20 个固定场景，每个场景运行 3 次，共 60 Run、107 次 Provider 请求；估算成本为 0.042727 美元。
```

### 4.2 必须附带限定

- `0.94` 是固定离线 Mock embedding 集的 hybrid 指标，不是真实 embedding 的生产结论。
- Guard 召回 `1.0` 来自真实响应后的受控非法 JSON 注入，只验证拦截链路。
- 公开 Demo 和 91 秒录屏使用 Mock Provider，不是真实模型在线演示。
- 真实 Agent 工具选择 `0.6333`、确认完整性 `0.5556`，不能描述成稳定可用。
- 成本是 Provider usage 乘公开费率的估算，不是账单。

## 5. 高频技术追问

### 5.1 为什么选择垂直学习场景，而不是通用 Agent？

```text
通用 Agent 很容易只剩提示词和工具列表，难以定义完成条件和风险边界。学习场景有明确状态、资料来源、任务写入和复习反馈，适合验证多步执行、引用可靠性、人工确认和状态回读。我优先把一个垂直闭环做深，而不是扩大成不可控的平台。
```

### 5.2 这个系统为什么算 Agent，而不只是固定工作流？

```text
运行时不是固定顺序调用所有工具。每一步会读取最新 Context，由 Decision 根据目标和 Observation 选择下一动作，再经过 Guard 和 Tool Registry 执行。工具结果会改变下一轮上下文和决策，运行可以因完成、失败、步数上限、确认或取消而停止。不过它仍是垂直、受控 Agent，不宣称是通用自主智能体。
```

### 5.3 为什么没有使用 LangChain？

```text
这个项目需要我明确控制每一步持久化、确认恢复、幂等、额度预留和错误边界。直接实现 Runtime 可以把这些核心机制完整展示出来，也避免框架抽象掩盖关键设计。后续如果工具和 Provider 数量扩大，可以再评估框架，但当前规模下自定义服务层更容易测试和解释。
```

### 5.4 为什么认证用数据库会话，而不是 JWT？

```text
这是同源 Web 应用，不需要无状态跨服务鉴权。随机不透明 Session Cookie 可以由服务端立即吊销，数据库只保存 SHA-256 哈希；HttpOnly、SameSite 和 Origin 校验共同降低令牌泄漏与跨站写入风险。相比 JWT，它更适合 Demo 账号过期和账户删除场景。
```

### 5.5 PostgreSQL 为什么区分 pooled 和 direct URL？

```text
应用请求使用 pooled URL，减少短连接成本，并启用 pool_pre_ping；Alembic、CREATE EXTENSION 和集成测试使用 direct URL，避免连接池代理对 DDL、扩展安装或事务语义造成限制。生产数据库错误不会静默回退 SQLite。
```

### 5.6 PDF 上传做了哪些安全处理？

```text
接口同时校验扩展名、MIME、PDF 文件签名、5 MB 大小和 50 页限制；拒绝加密 PDF、压缩包、路径型文件名和无文本扫描件。原文件只在请求内存中解析，提取后释放，不参与服务器路径拼接。资料文本被视为不可信输入，不能覆盖系统提示或触发工具。
```

### 5.7 hybrid 检索怎么实现？

```text
keyword 和 dense 分别保留 Top 20。PostgreSQL dense 先用 embedding_vector::halfvec(2048) 的 cosine HNSW 召回 Top 100，再用完整 vector(2048) cosine 距离重排为 Top 20。最后使用 RRF k=60 融合；embedding 不可用时明确降级为纯关键词。
```

### 5.8 为什么使用 halfvec HNSW？

```text
真实迁移时发现 pgvector 的 vector HNSW 操作符类不支持超过 2000 维，而当前 embedding 是 2048 维。我没有降低已锁定的 embedding 维度，而是用 halfvec(2048) expression index 做候选召回，再用原始 vector(2048) 全精度重排，兼顾索引可用性和最终排序精度。
```

### 5.9 如何防止 RAG 编造资料依据？

```text
引用不是模型自己生成的字符串，而是检索层返回的资料 ID、标题、页码或标题路径、原文和分数。没有达到资料充分条件时，服务端直接返回 grounded-refusal，不调用模型用常识补答案。冲突资料目前只验证引用范围，不自动裁决来源优先级，这是已记录限制。
```

### 5.10 AgentContext、Decision Guard 和 Tool Registry 分别做什么？

```text
AgentContext 决定模型能看到哪些学习状态；Decision Guard 判断结构化输出是否合法、是否需要回退或补确认；Tool Registry 定义合法动作对应哪个工具、风险等级和写入边界。简单说，Context 是输入边界，Guard 是决策入口，Registry 是执行规则。
```

### 5.11 确认恢复怎么保证是同一次运行？

```text
高风险 Step 会持久化为 waiting_confirmation，同时保存 Run、Step、草稿和幂等键。用户接受后，后端在原 Run 和原 Step 上应用草稿，再读回正式数据继续决策；拒绝时不写正式数据，取消后条件更新保证 Run 不能再次推进。重复恢复不会重复写入。
```

### 5.12 如何处理并发、超时和重复执行？

```text
Run 推进使用数据库条件更新限制同一时刻只有一个 executor。写工具依赖幂等键，不盲目重试；读工具超时最多重试一次。取消和执行互斥，终态 Run 不再推进。模型用量在请求发送前通过 PostgreSQL 原子计数预留。
```

### 5.13 如何让 Agent 可观察和可调试？

```text
每个 AgentStep 保存 context、decision、Guard、tool input/output、ActionLog、错误、耗时和 stopReason，前端按时间线展示，大 JSON 默认折叠并脱敏。这样可以定位具体是哪一步选错工具、被 Guard 回退、等待确认或因预算停止，而不是只看到最终一句回答。
```

### 5.14 测试和 CI 覆盖了什么？

```text
最终 Mock pytest 是 150 passed、4 skipped；隔离 PostgreSQL/pgvector 集成集是 4 passed，覆盖会话哈希、原子限流和额度、vector(2048)/halfvec HNSW 重排及资料批量写入。Playwright 覆盖 Demo、目标、PDF、引用问答、确认恢复、拒绝、取消、桌面和 390px，并检查严重无障碍问题、页面异常、控制台错误和横向溢出。CI 还执行 Ruff 和敏感信息扫描。
```

### 5.15 为什么 Mock Agent 是 1.0，真实模型却明显更低？

```text
Mock 的作用是验证 Runtime、Guard、工具和确认状态机是否稳定，不衡量模型理解能力。真实模型会受到提示词、工具描述、上下文长度和结构化输出稳定性的影响。60 个真实 Run 中，工具选择只有 0.6333，确认完整性是 0.5556，说明当前模型层仍是主要短板；我保留了 22 个失败 Run，并把它作为下一轮优化基线。
```

### 5.16 Guard 召回 1.0 是否说明模型输出很安全？

```text
不能这样解释。三个 Guard 场景是在真实 Provider 返回后固定注入非法 JSON，测的是 Guard 能否拦截，结果是 1.0；它不衡量模型自然产生非法输出的比例。真实运行中的 84 次安全回退更能说明模型输出稳定性仍需改进。
```

### 5.17 如何控制真实模型成本和凭据风险？

```text
运行前先计算 20 场景 x 3 的请求、Token 和成本上限，必须显式授权后才加载 backend/.env。每次请求发送前限制 12,000 UTF-8 字节和 350 completion token，并在 Provider 边界预留请求和成本预算。报告只保存用量、耗时、工具序列和失败 ID，不保存 API Key、提示词或模型原文。
```

### 5.18 真实 Agent 指标不高，为什么还放在作品集中？

```text
因为 Agent 工程不只是在成功截图里展示能力，还要能测出失败。这个评测证明我能定义固定场景、限制预算、记录 Token 和成本、区分状态机正确性与模型质量，并保留失败数据。下一步会针对失败类别优化工具描述、决策 schema 和上下文裁剪，然后用同一 20 x 3 数据集复跑，而不是改样例让数字变好看。
```

### 5.19 个人贡献边界是什么？

```text
早期目标、任务和进度看板属于协作开发基础模块，我不会说成个人从零实现。根据提交历史，2026 年 7 月 6 日之后的多步 Runtime、AgentStep、Tool Registry、Decision Guard、确认恢复、取消互斥，以及第七版的数据库会话、摄取、pgvector、评测、Playwright 和 CI 由我独立设计实现。
```

### 5.20 当前最重要的限制和下一步是什么？

```text
第一，真实模型工具选择和确认完整性不足，需要优化工具描述、结构化 schema 和上下文裁剪；第二，dense 的固定 Mock 基线较弱，需要用真实 embedding 固定集重新评测；第三，冲突资料没有来源权重和自动裁决；第四，上传处理仍是同步流程，大文件需要异步队列和 OCR。下一步优先优化真实 Agent 决策质量，再用原固定集复跑。
```

## 6. 三个 STAR 案例

### 6.1 2048 维向量无法直接建立 HNSW

- Situation：真实 Neon 迁移时，pgvector 拒绝为 `vector(2048)` 建立目标 HNSW 索引。
- Task：保持已锁定的 2048 维 embedding，同时让 dense 查询实际使用近似索引。
- Action：确认 `vector` HNSW 的 2000 维限制，改为 `halfvec(2048)` expression index；候选阶段取 Top 100，再按原始向量全精度重排，并用 `EXPLAIN` 验证索引生效。
- Result：迁移到 `20260717_02`，PostgreSQL/pgvector 集成测试通过，保留完整 2048 维 source vector。

### 6.2 资料不足 F1 从 0.4 修复到 0.8571

- Situation：初始问答评测把 `qa18` 至 `qa23` 的无关问题误召回，资料不足 F1 只有 `0.4`。
- Task：修复误召回，但不能删除失败样例或更换测试集。
- Action：定位到查询侧中文二字 n-gram 与通用问句片段相交，改为三至四字 n-gram 并过滤问句停用词；保留原失败记录和相同固定集复跑。
- Result：Precision=`1.0`、Recall=`0.75`、F1=`0.8571`，达到门槛，同时保留仍未召回的限制。

### 6.3 真实模型评测没有达到 Mock 水平

- Situation：Mock 20 场景全部通过，但缺少真实模型的重复运行、Token 和成本证据。
- Task：在有限预算下运行 20 场景各 3 次，并避免凭据和模型原文进入报告。
- Action：先做提示 envelope 审计和预算预留，关闭格式修复重试，创建 Run 时使用规则快照，执行阶段才调用 DeepSeek；报告只保存结构化结果和 usage。
- Result：完成 60 Run、107 请求，估算 `$0.042727`；发现工具选择 `0.6333`、确认完整性 `0.5556`，保留 22 个失败 Run 和 84 次回退，形成下一轮真实优化基线。

## 7. 演示顺序

1. 一键试用，说明隔离 Demo 数据和 Mock Provider。
2. 创建目标并上传 PDF，展示处理阶段和来源定位。
3. 提问并展开引用，再演示资料不足拒答。
4. 进入智能任务，展开 AgentStep、Guard 和 Tool I/O。
5. 接受一次确认并恢复，再演示拒绝或取消。
6. 切换 390px，最后展示离线报告与真实 Agent 报告的边界。

不要在演示中打开 `.env`、Cookie、连接串、个人用户数据或 Provider 原始响应。

## 8. 面试红线

- 不说“真实模型工具选择率 100%”；真实值是 `0.6333`。
- 不说“Guard 1.0 证明模型不会违规”；它只证明受控注入下的拦截链路。
- 不说“hybrid 0.94 是真实 embedding 生产指标”；它是固定离线 Mock 集。
- 不说“公开 Demo 使用 DeepSeek”；公开 Demo 和录屏均使用 Mock Provider。
- 不说“系统自动修改用户计划”；高风险动作必须确认。
- 不说“实现了 OCR、网页抓取或冲突自动裁决”；这些仍是限制。
- 不说“整个项目从零独立完成”；早期目标、任务和进度模块属于协作开发。

## 9. 最后复述句

```text
这个项目的核心不是接入一个模型接口，而是把 Agent 的上下文、结构化决策、工具边界、状态持久化、人工确认、RAG 引用和评测证据做成一个可复现的工程闭环；真实模型表现不理想的部分也有固定数据和失败记录，而不是只展示成功样例。
```
