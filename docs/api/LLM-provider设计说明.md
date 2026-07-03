# LLM Provider 设计说明

更新时间：2026-07-03

## 目标

本次调整的目标不是直接接入真实大模型，而是先把 Agent 问答链路拆成清晰的工程边界：

```text
agent_service.py
负责检索 chunks、过滤 goal/material、组织 references、组装统一返回结构。

llm_provider.py
负责根据 question、goal、references 生成 answer、basis、suggestion、confidence。
```

这样后续接 OpenAI、DeepSeek、Qwen 或 LangChain 时，只需要替换 Provider，不需要改动 API、SQLite 存储和前端字段。

## 当前实现

新增文件：

```text
backend/app/services/llm_provider.py
```

核心对象：

```text
LLMAnswerContext：传给 Provider 的上下文
LLMAnswer：Provider 返回的结构化回答
LLMProvider：Provider 协议
MockLLMProvider：当前默认 mock 实现
get_llm_provider()：按环境变量选择 Provider
```

当前默认：

```text
LLM_PROVIDER=mock
```

当前已新增：

```text
OpenAICompatibleLLMProvider
```

它使用兼容 OpenAI Chat Completions 形状的 HTTP 接口。只有在以下配置齐全时才会启用：

```text
LLM_PROVIDER=openai-compatible
LLM_API_KEY=你的密钥
LLM_MODEL=模型名称
LLM_BASE_URL=https://api.openai.com/v1 或其他兼容服务地址
LLM_TIMEOUT_SECONDS=20
```

如果 `LLM_PROVIDER` 未配置、配置成未知值，或选择 `openai-compatible` 但缺少 `LLM_API_KEY` / `LLM_MODEL`，系统会安全回退到 `MockLLMProvider`，保证本地开发、测试和 smoke 不受真实模型配置影响。

## 调用链路

```text
POST /api/agent/ask
-> agent_service.answer_question()
-> material_store.search_chunks()
-> llm_provider.get_llm_provider()
-> provider.generate_answer()
-> 保存 material_qa_records
-> 返回统一响应
```

当使用 `OpenAICompatibleLLMProvider` 时：

```text
1. agent_service 仍负责检索 chunks、过滤 goal/material 和组织 references。
2. provider 只负责把 question、goal 和 references 交给模型生成结构化回答。
3. 模型必须返回 answer、basis、suggestion、isFromMaterial、confidence。
4. 如果模型调用失败、超时或返回格式不可解析，自动降级为 MockLLMProvider。
```

## 为什么不直接把真实模型写进 agent_service

```text
1. agent_service 已经负责检索、过滤、返回结构和持久化边界。
2. 真实大模型调用会引入 API Key、超时、异常、JSON 解析和 fallback。
3. 如果混在一起，后续很难测试，也很难切换模型。
4. Provider 抽象能让 mock、真实 API、LangChain 逐步替换。
```

## 下一步

```text
1. 使用真实 API Key 做人工联调。
2. 准备 3 类资料不足 / 部分命中 / 明确命中问题样例。
3. 根据联调结果继续收紧 Prompt 和结构化输出解析。
4. 再评估是否引入 LangChain 管理 Prompt 和输出解析。
```
