# 文档索引

本目录按用途拆分，避免每天新增文档后堆在 `docs/` 根目录。

## daily

每天的工作安排、联调记录和日终小结。每天只维护一份 `YYYY-MM-DD工作安排.md`，避免“分工”和“清单”重复。

```text
docs/daily/2026-06-30工作安排.md
docs/daily/2026-07-01工作安排.md
```

## status

项目当前进度、已完成内容、缺口和下一步。每天启动优先读取 `docs/status/当前状态.md`。

```text
docs/status/当前状态.md
docs/status/项目进度记录.md
```

## planning

产品边界、协作规则、技术方案和每天早上安排工作的长期规则。

```text
docs/planning/两人协作开发分工文档.md
docs/planning/第一版功能开发边界与分工.md
docs/planning/第一版技术实现方案.md
docs/planning/每日工作安排规则.md
```

## api

数据对象、字段命名和 API 草案。

```text
docs/api/第一阶段数据对象与API草案.md
docs/api/资料与AI模块字段和API草案.md
```

## 命名规则

```text
1. 每日文件使用 `YYYY-MM-DD工作安排.md`。
2. 长期规则放 planning，不按日期复制。
3. 每天启动只读 status/当前状态.md；长周期进度再看 status/项目进度记录.md。
4. API 和字段文档统一放 api。
```
