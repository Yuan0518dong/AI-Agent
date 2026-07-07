# 文档索引

本目录只保留当前开发和作品集展示需要的入口文档。历史计划、日报、阶段验收和早期草案已归档到 `docs/archive/`，需要追溯项目演进时再查看。

## 当前必读

```text
docs/status/当前状态.md
docs/planning/个人项目简历化与第四版智能体方案.md
README.md
```

用途：

```text
当前状态：记录最新阶段、分支、验证结果和下一步。
第四版方案：记录个人项目定位、简历表达边界和完整学习 Agent 路线。
README：面向 GitHub 访客和面试官，说明项目价值、启动方式和当前能力。
```

## 当前计划

```text
docs/planning/个人项目简历化与第四版智能体方案.md
docs/planning/第三版项目计划书.md
```

说明：

```text
个人项目简历化与第四版智能体方案：当前主线。
第三版项目计划书：上一阶段可控学习智能体 MVP 的计划记录，仍作为第四版前置背景。
```

## 当前验收

```text
docs/status/第三版资料学习智能体验收样例.md
```

说明：

```text
记录资料内回答、复习建议、资料不足三类真实模型验收样例。
```

## 工程说明

```text
docs/api/LLM-provider设计说明.md
docs/api/RAG-chunks接口说明.md
docs/modules/目标模块前后端接口对照.md
docs/modules/资料模块前后端接口对照.md
```

说明：

```text
LLM Provider：mock / OpenAI-compatible Provider 配置和行为。
RAG chunks：资料片段生成、检索和接口说明。
目标模块接口对照：目标、任务、打卡、进度链路。
资料模块接口对照：资料、摘要、chunks、问答、复盘、闪卡链路。
```

## 历史归档

```text
docs/archive/README.md
```

归档内容包括：

```text
第一版 / 第二版计划
旧协作分工
每日工作安排
旧阶段验收记录
早期 API 草案
旧测试清单和截图
```

## 维护规则

```text
1. 当前主线只更新 docs/status/当前状态.md 和第四版方案文档。
2. README 面向外部展示，避免堆过程细节。
3. 历史证据不删除，统一移入 docs/archive/。
4. 新增第四版工程设计时，优先放在 docs/planning/ 或 docs/api/，不要再散落 daily/status。
5. 如果文档不再指导当前开发，就移入 archive。
```
