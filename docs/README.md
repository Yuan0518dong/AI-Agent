# 文档索引

本目录按用途拆分，避免文档都堆在 `docs/` 根目录。第二版开发期间，优先读“当前入口”，历史文档只在需要追溯时查看。

## 当前入口

```text
docs/status/当前状态.md
docs/status/MVP第一版验收记录.md
docs/status/第二版阶段验收记录.md
docs/status/第二版最终验收记录.md
docs/status/第二版验收样例与演示脚本.md
docs/planning/第二版项目计划书.md
docs/README.md
```

## status

记录项目当前状态、验收结果、长期进度和历史问题。每天启动优先读取 `docs/status/当前状态.md`。

```text
docs/status/当前状态.md
docs/status/MVP第一版验收记录.md
docs/status/第二版阶段验收记录.md
docs/status/第二版最终验收记录.md
docs/status/第二版验收样例与演示脚本.md
docs/status/真实模型联调记录.md
docs/status/MVP第一版进度评估与下一步计划.md
docs/status/项目进度记录.md
docs/status/dev-demo-smoke.png
```

## planning

记录版本计划、技术方案、协作规则和长期工作规则。第二版以 `docs/planning/第二版项目计划书.md` 为主。

```text
docs/planning/第二版项目计划书.md
docs/planning/第一版技术实现方案.md
docs/planning/第一版功能开发边界与分工.md
docs/planning/两人协作开发分工文档.md
docs/planning/每日工作安排规则.md
```

## api

记录数据对象、字段命名和 API 草案。

```text
docs/api/第一阶段数据对象与API草案.md
docs/api/资料与AI模块字段和API草案.md
docs/api/RAG-chunks接口说明.md
docs/api/第二版AI问答接口交接.md
docs/api/LLM-provider设计说明.md
```

## modules

记录具体模块的前后端接口对照、测试清单和模块级验收内容。

```text
docs/modules/目标模块前后端接口对照.md
docs/modules/目标模块测试清单.md
docs/modules/资料模块前后端接口对照.md
```

## daily

记录每天的工作安排、联调记录和日终小结。每日文件使用 `YYYY-MM-DD工作安排.md`。

```text
docs/daily/2026-06-30工作安排.md
docs/daily/2026-07-01工作安排.md
docs/daily/2026-07-02工作安排.md
docs/daily/2026-07-03工作安排.md
```

## 归档规则

```text
1. 当前状态只维护 docs/status/当前状态.md。
2. 版本计划统一放 docs/planning/。
3. API 字段草案统一放 docs/api/。
4. 模块级接口对照和测试清单统一放 docs/modules/。
5. 每日安排和当天记录统一放 docs/daily/。
6. 第一版文档保留，不删除；第二版开发时只把它们作为历史依据。
```
