# 第七版 Batch 4 验收记录

验收日期：2026-07-20

分支：`feature/v7-evaluation-portfolio`

状态：**全部验收通过**。本记录区分离线 Mock、受限真实模型和实际 PostgreSQL/pgvector 集成证据；不会把三者混写为单一结论。

## 已完成证据

| 需求 | 状态 | 证据 |
|---|---|---|
| `EVAL-01` | 通过 | `backend/evaluation/v7_retrieval_corpus.json` 有 10 份资料；`v7_retrieval_cases.json` 有 50 条中文查询。 |
| `EVAL-02` | 通过 | `backend/evaluate_batch4.py` 输出 keyword/dense/hybrid 的 Recall@3/5、MRR、nDCG@5、p50/p95 与逐条排名。 |
| `EVAL-03` | 通过 | `v7_qa_cases.json` 有 32 条问答：可回答、跨资料、资料不足、冲突资料各 8 条。 |
| `EVAL-04` | 通过 | 固定 QA 报告包含引用准确率、groundedness 与资料不足 P/R/F1；修复后 F1=0.8571，初始失败样例已保留。 |
| `EVAL-05` | 通过 | 20 场景 Mock 回归保持通过；已配置 DeepSeek Provider 对每个固定场景运行 3 次，共 60 个真实 Run。 |
| `EVAL-06` | 通过 | 真实报告保留工具/Guard/确认/恢复、延迟、Token、成本和逐 Run 失败；低成功率与 84 次安全回退未被隐藏。 |
| `E2E-01` | 通过 | `v7-batch4.spec.cjs` 覆盖 Demo、创建目标、PDF、引用问答、确认恢复、拒绝、取消。 |
| `E2E-02` | 通过 | `npm.cmd run test:e2e` 为 `1 passed (10.7s)`；桌面和 390px 无横向溢出，axe serious/critical=0，页面异常=0，非预期 console error=0。 |
| `CI-01` | 通过 | 工作流包含 Ruff、pgvector 服务测试、敏感信息扫描和 Playwright；隔离直连库迁移到 `20260717_02` 后，PostgreSQL 标记集实际为 `4 passed, 150 deselected`。 |
| `DOC-01` | 通过 | README 收敛为作品集入口；`docs/videos/v7-batch4-90s-demo.webm` 在隔离 Mock 流程中录制，Windows 元数据时长 `00:01:31`。 |
| `DOC-02` | 通过 | [个人贡献说明](../portfolio/个人贡献说明.md) 明确区分早期协作模块与 2026-07-06 后的维护者独立实现。 |
| `CV-01` | 通过 | [简历材料](../portfolio/简历材料.md) 的 4 条 Bullet 均链接至当前固定数据、测试或验收证据，并写明 Mock/未验收限制。 |

## 离线指标

运行模式固定为 `LLM_PROVIDER=mock`、`EMBEDDING_PROVIDER=mock`；数据集指纹、逐条结果与报告均在 `docs/evaluation/`。

| 模式 | Recall@3 | Recall@5 | MRR | nDCG@5 | p50 ms | p95 ms |
|---|---:|---:|---:|---:|---:|---:|
| keyword | 0.94 | 0.94 | 0.9167 | 0.9226 | 14.145 | 16.216 |
| dense | 0.28 | 0.28 | 0.2367 | 0.2479 | 14.447 | 17.357 |
| hybrid | 0.94 | 0.94 | 0.9067 | 0.9152 | 14.547 | 16.927 |

问答集的引用准确率为 `0.75`、groundedness 为 `0.75`，资料不足 Precision 为 `1.0`、Recall 为 `0.75`、F1 为 `0.8571`，达到 `0.80` 门槛。初始失败中 `qa18` 至 `qa23` 曾被通用中文二字问句片段误召回；初始数据与修复过程保留在 `../evaluation/第七版Batch4资料不足修复记录.md`，修复后完整逐条结果在 `第七版Batch4问答评测报告.json`。

20 个 Agent Mock 场景均通过：工具选择成功率、Guard 召回、确认完整性和可恢复确认的恢复成功率均为 `1.0`；本次复跑 p50/p95 为 `407/546 ms`，prompt token、completion token 和成本均为 `0`。这些是 Mock 回归结果，不是 DeepSeek 真实模型指标。

## 真实模型指标

在显式授权最多 126 次请求、`$0.27` 成本上限后，已配置的 DeepSeek OpenAI-compatible Provider 对固定 20 个 Agent 场景各运行 3 次。评测创建 Run 时使用规则初始快照，执行阶段使用真实 `llm-json`；工具中的问答/摘要保持离线确定性，以限制付费调用范围。没有保存 Provider 配置、提示词、模型原文或任何凭据。

| 指标 | 真实结果 |
|---|---:|
| Run / 场景 | 60 / 20 x 3 |
| Provider 请求 | 107 |
| 工具选择成功率 | 0.6333 |
| Guard 召回 | 1.0 |
| 确认完整性 | 0.5556 |
| 恢复成功率 | 1.0 |
| p50 / p95 延迟 | 5781 / 9750 ms |
| prompt / completion Token | 237971 / 33611 |
| Token 估算成本 | `$0.042727` |
| 发送前保守预留成本 | `$0.136668` |
| 未满足场景断言 / 安全回退 | 22 / 84 |

Guard 的三个场景在真实 Provider 已返回一次决策后，向 Guard 输入固定非法 JSON；`1.0` 仅证明该拦截链路，不是模型自然非法输出率。工具选择和确认完整性显著低于完整成功，22 个失败 Run（包括 `agent_case_003#1` 至 `#3` 等）与每次回退均保留在 [真实模型报告](../evaluation/第七版Batch4Agent真实模型评测报告.json)；不得以 Mock 的 `1.0` 代替这些真实结果。

## 自动化与门禁

```text
python -m pytest backend/tests -q --tb=short      150 passed, 4 skipped (105.98s)
python -m compileall -q backend                    passed
python -m pip check                                passed
python -m ruff check backend                       passed
npm.cmd run check                                  passed
python backend/check_sensitive_content.py          passed
git diff --check                                   passed
npm.cmd run test:e2e                               1 passed (10.7s)
backend.evaluate_batch4.verify_repeatability()     passed (延迟字段排除比较)
python -m pytest backend/tests -m postgres -q      4 passed, 150 deselected (251.68s)
```

隔离直连 `POSTGRES_TEST_DATABASE_URL` 已在命令进程内同时作为应用、迁移和测试连接使用，未输出或提交连接串。Alembic `current` 为 `20260717_02 (head)`；完整标记集 `4 passed, 150 deselected in 251.68s`，覆盖会话哈希与原子用量计数、`vector(2048)`/`halfvec(2048)` HNSW 和全精度重排、认证限流与并发预留、资料批量写入。工作流已包含 Ruff、敏感信息扫描、pgvector service 和 Playwright job。

## 真实模型与预算

真实 Provider 预算范围为：20 场景 x 3 次即 60 个完整 Agent Run，最少 60、最多 126 次 Provider 请求；120 次为各场景 Step 上界，另有 6 次来自两类接受确认后的恢复读回。创建 Run 的初始快照使用规则决策，执行阶段才使用真实 `llm-json`，避免计入一个不会被执行使用的创建期决策。固定问答集继续走离线确定性评测，不产生该批付费请求；格式修复重试在受限真实评测中关闭。每次请求发送前限制为 12,000 UTF-8 字节与 350 completion token，20 场景无联网路径审计最大为 11,430 字节；prompt token 以一字节一 token 保守预留为 1,512,000，completion token 上界 44,100。

按 2026-07-20 [DeepSeek 官方定价](https://api-docs.deepseek.com/quick_start/pricing)，以 cache-miss 输入 `$0.14/M`、输出 `$0.28/M` 的保守价格计算，原始最坏情况预留为 `$0.224028`，加 20% 缓冲为 `$0.268834`。本次已在授权范围内执行 107 次请求，实际 Provider 用量为 `237971/33611` prompt/completion Token，按该公开费率估算 `$0.042727`；报告的运行时保守预留为 `$0.136668`。这是基于 usage 字段和公开费率的估算，不是账单。

`backend/batch4_real_evaluation_preflight.py` 在任何真实运行前强制校验显式授权、请求上限和成本上限；默认拒绝，不实例化 Provider、不发送 HTTP 请求、不显示或保存凭据。

## 已知限制

- 真实 Agent 的工具选择成功率为 `0.6333`、确认完整性为 `0.5556`；这些未达到稳定能力宣传标准的失败证据已保留，不会被 Mock 结果覆盖。

本批未推送、未合并、未创建 PR，未修改 `personal/main`、`personal/feature/v7-ingestion-rag` 或 `origin`。
