# FE-03 Today 首屏层级验收记录

验收日期：2026-07-24

分支：`feature/learning-loop-ux`

基线：`69b5729`

实现提交：`69a4c61`

状态：**通过**

## 结果

Today 页面将主线目标卡移至指标之后、今日看板之前。Demo 用户在 `1440×900` 首屏可同时看到当前目标、状态、今日建议和“生成计划”主操作；移动版保持主线目标在今日行动之前，底部导航不遮挡操作。

此次调整仅改变前端 DOM 展示顺序，保留既有目标、任务、dashboard 与 Today Actions 请求及所有写入行为。

## 验证

- `FE-03` Playwright：`1 passed`，等待最终 DOM 顺序，不使用固定延迟。
- 完整 E2E：`14 passed (2.1m)`。
- `npm.cmd run check`、`python backend/check_sensitive_content.py`、`git diff --check` 通过。
- 已实际复核 `fe03-today-demo-desktop.png` 及同轮 7 张回归截图。

## 下一阶段

仅启动 FE-04：统一目标、资料与引用问答的前端工作区，不修改摄取、检索、RRF 或引用生成实现。
