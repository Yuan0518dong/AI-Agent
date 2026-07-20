# 文档索引

本目录区分对外作品集、当前任务、状态、评测证据、工程契约和历史归档。GitHub 访客优先从根目录 `README.md` 开始；继续开发时先读取个人学习助手后续任务执行文档和当前状态。

## 对外作品集

```text
README.md
docs/portfolio/个人贡献说明.md
docs/portfolio/架构与评测边界.md
docs/portfolio/简历材料.md
docs/portfolio/90秒演示脚本.md
docs/videos/v7-batch4-90s-demo.webm
```

这些材料分别说明项目定位、个人贡献边界、架构与评测口径、简历 Bullet 和演示流程。公开 Demo 与录屏使用 Mock Provider，真实模型结论只引用独立评测报告。

## 当前开发入口

```text
docs/planning/个人学习助手后续任务执行文档.md
docs/status/当前状态.md
docs/planning/AI-Agent简历与面试讲解稿.md
docs/evaluation/真实Agent决策失败分类与可靠性实验基线.md
docs/evaluation/真实Agent可靠性A3候选设计与离线验收.md
```

`个人学习助手后续任务执行文档.md` 是唯一当前计划入口；历史“第几版”计划只用于追溯。后续按 Agent 可靠性、学习空间、间隔复习、薄弱点、学习教练、引用详情和完整验收的顺序推进。

## 评测与验收

```text
docs/evaluation/第七版Batch4检索评测报告.json
docs/evaluation/第七版Batch4问答评测报告.json
docs/evaluation/第七版Batch4AgentMock评测报告.json
docs/evaluation/第七版Batch4Agent真实模型评测报告.md
docs/evaluation/第七版Batch4Agent真实模型评测报告.json
docs/status/第七版Batch1本地验收记录.md
docs/status/第七版Batch2验收记录.md
docs/status/第七版Batch3验收记录.md
docs/status/第七版Batch4验收记录.md
```

固定离线、Mock、真实 Provider 和公开 Demo 是四类不同证据，不能互相替代。当前真实模型工具选择与确认完整性仍是下一阶段要改进的基线。

## 工程说明

```text
docs/api/第六版Agent运行时契约与架构.md
docs/api/LLM-provider设计说明.md
docs/api/RAG-chunks接口说明.md
docs/modules/目标模块前后端接口对照.md
docs/modules/资料模块前后端接口对照.md
```

第六版运行时契约仍是当前 Agent 状态机、工具、确认恢复和安全边界的基础；第七版在其上增加部署、摄取、pgvector、评测和作品集交付。

## 历史归档

早期计划、日报、协作草案和旧验收记录统一从 `docs/archive/README.md` 进入。它们用于追溯项目演进，不再指导当前开发。

## 维护规则

1. 根 README 面向访客，只保留定位、Demo、架构、指标、启动方式与限制。
2. 当前事实写入 `docs/status/当前状态.md`，实验结果写入 `docs/evaluation/`。
3. 真实模型失败样例和旧基线不得因优化而删除或改写。
4. 不再指导当前工作的文档移入 `docs/archive/`，避免多个“当前计划”并存。
5. 后续不再新增按版本编号组织的需求文档；任务完成状态统一维护在 `docs/planning/个人学习助手后续任务执行文档.md`。
