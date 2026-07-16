# 第七版 Batch 0 验收记录

验收日期：2026-07-16

## 范围

本批次只收口进入第七版前已经存在的 UX 改动和基线证据：目标选择持久化、界面中文化、测试题答题草稿保留、侧边栏滚动行为，以及 `390px` 基础横向溢出。未实施鉴权、PostgreSQL、公开部署、上传或评测需求。

## 已完成需求

- `BASE-01`：复核现有 UX 改动。
- `BASE-02`：修复 `390px` 横向溢出并准备独立提交。
- `BASE-03`：复核 Dockerfile，未与本批 UX 混合提交。
- `BASE-04`：保存基础门禁结果。
- `BASE-05`：锁定后续 Batch 1 至 Batch 4 分支名称。

## 实施内容

- 目标选择写入 `state.selectedGoalId`，页面刷新和智能助手刷新后仍能读回。
- 智能助手界面采用面向学习场景的中文文案；测试题输入值在重新渲染后保留。
- 桌面端侧边栏保持可视高度内的滚动和吸顶行为。
- `980px` 以下的侧栏和导航允许收缩；七项导航在自身横向滚动区域中使用足以容纳最长标签的固定项宽度，因此不再把页面宽度扩展到 `650px`。

## 自动化与浏览器验收

基础门禁在隔离 Mock 环境执行：

```powershell
$env:LLM_PROVIDER="mock"
$env:EMBEDDING_PROVIDER="mock"
$env:LLM_ENV_FILE=".missing-v7-gate.env"
python -m pytest backend/tests -q --tb=short
python -m compileall -q backend
python -m pip check
node --check app/api.js
node --check app/app.js
node --check app/modules/agent-workbench.js
git diff --check
```

结果：`98 passed`；其余命令均以退出码 `0` 完成。

本地 Edge + Playwright 浏览器验收使用独立临时 SQLite 数据库，真实走完注册、创建目标、目标切换、创建资料和测试题草稿流程。修复前，登录后页面在 `390px` 的 `documentWidth` 为 `650px`；修复后登录页和全部七个已登录页面的 `documentWidth` 均为 `390px`。目标选择在刷新后保持，答题草稿在完整重新渲染后保持，桌面侧边栏滚动后 `top=0`，控制台错误和页面错误均为 `0`。

## Dockerfile 审计

未跟踪 Dockerfile 未纳入本提交。其内容仍为 HuggingFace Spaces 的 `7860` 端口草稿，并设置 `CORS_ORIGINS=*`；该配置不能作为第七版 Render/Neon 生产方案。Batch 1 将在鉴权和 PostgreSQL 部署设计完成后处理 Dockerfile 与 `.dockerignore`。

## 后续分支

按依赖顺序，Batch 1 将从本 Batch 验收提交创建本地 `feature/v7-security-demo`。后续依次为 `feature/v7-ux-runtime`、`feature/v7-ingestion-rag`、`feature/v7-evaluation-portfolio`。本批未推送、未合并、未修改远程仓库。
