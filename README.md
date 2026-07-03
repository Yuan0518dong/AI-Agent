# AI-Agent

通用成长学习助手 App 的第二版开发原型。

## 当前版本

- 创建成长目标
- 添加学习或成长资料
- 自动整理资料摘要和知识点
- 将资料切分为可检索片段 chunks
- 支持按关键词检索资料片段
- 自动生成 7 天行动计划
- 生成闪卡和简单测试题
- 支持成长问答，并通过 `POST /api/agent/ask` 返回答案、依据、学习建议和来源片段
- 支持任务打卡和进度查看
- 目标、任务、打卡、资料、摘要、闪卡、测试题、资料片段已接入后端 SQLite 持久化
- 当前仍是单用户 MVP，没有注册登录和用户隔离

当前第二版已完成的 AI 学习链路：

```text
添加资料 -> 生成 chunks -> 搜索资料片段 -> 成长问答提问 -> 展示 answer / basis / suggestion / references
```

当前限制：

```text
1. /api/agent/ask 仍是 mock / rule-based 问答底座，尚未接入真实大模型。
2. GET /api/materials/{material_id}/qa 尚未实现，历史问答持久化列表暂不接入。
3. 资料不足判断已有前端提示基础，但仍需后续用评估样例继续收紧。
```

## 环境要求

建议环境：

```text
Python 3.12+
PowerShell 或其他终端
浏览器
```

确认 Python 可用：

```bash
python --version
```

## 安装依赖

在项目根目录执行：

```bash
pip install -r backend/requirements.txt
```

如果 Windows 提示 `pip.exe` 被应用程序控制策略阻止，可以改用：

```bash
python -m pip install -r backend/requirements.txt
```

## 启动后端

在项目根目录执行：

```bash
python -m uvicorn backend.app.main:app --reload
```

启动成功后可以访问：

```text
后端服务：http://127.0.0.1:8000
接口文档：http://127.0.0.1:8000/docs
健康检查：http://127.0.0.1:8000/api/health
```

看到类似下面内容，说明后端正常：

```text
Uvicorn running on http://127.0.0.1:8000
Application startup complete.
```

## 启动前端

推荐用本地静态服务打开前端：

```bash
python -m http.server 5500 --directory app
```

然后访问：

```text
http://127.0.0.1:5500/index.html
```

如果只是看静态页面，也可以直接打开：

```text
app/index.html
```

但当前前端需要调用后端 API，推荐先启动后端，再用 `http://127.0.0.1:5500/index.html` 测试。

## 运行测试

运行全部后端自动化测试：

```bash
python -m pytest backend/tests -v
```

运行后端冒烟测试：

```bash
python backend/smoke_api.py
```

如果 Windows 临时目录出现权限问题，例如：

```text
PermissionError: [WinError 5] 拒绝访问: ...\Temp\pytest-of-26696
```

可以改用项目内临时目录：

```bash
python -m pytest backend/tests -v --basetemp .pytest_tmp
```

## SQLite 数据库

本地开发数据库默认位置：

```text
backend/data/ai_agent.db
```

当前保存的数据包括：

```text
goals
tasks
checkins
materials
material_summaries
flashcards
quiz_questions
material_chunks
```

说明：

```text
1. backend/data/ 已加入 .gitignore，不会提交到 Git。
2. 后端重启后，本地 SQLite 数据仍会保留。
3. 自动化测试使用临时 SQLite 数据库，不会清空本地开发数据。
4. 如果想重新开始测试，可以停止后端后手动删除 backend/data/ai_agent.db。
```

## 常见问题

### 1. 打开 http://127.0.0.1:8000 显示 404

这是正常的。当前后端没有定义首页接口。

请访问：

```text
http://127.0.0.1:8000/docs
http://127.0.0.1:8000/api/health
```

### 2. 请求返回 422

`422 Unprocessable Entity` 通常表示请求体字段不符合后端 Pydantic schema。

常见原因：

```text
1. JSON 格式写错，例如末尾多了逗号。
2. 字段名写错，例如 dailyMinutes 和 daily_minutes 混用。
3. 必填字段缺失。
4. 数字范围不合法，例如 daily_minutes <= 0。
```

### 3. 端口 8000 或 5500 被占用

先关闭之前启动服务的终端，或按 `Ctrl + C` 停止服务。

如果仍然占用，可以换一个端口。例如前端换成 5501：

```bash
python -m http.server 5501 --directory app
```

如果后端换端口，需要同时修改前端 `app/api.js` 中的 API 地址。

### 4. 前端拿不到后端数据

优先检查：

```text
1. 后端是否启动。
2. http://127.0.0.1:8000/api/health 是否返回 success。
3. 前端是否通过 http://127.0.0.1:5500/index.html 打开。
4. app/api.js 中 API_BASE_URL 是否是 http://127.0.0.1:8000/api。
```

### 5. 成长问答回答不准确

当前问答通过 `POST /api/agent/ask` 基于资料 chunks 返回 mock / rule-based 结果，不是真正的大模型问答。

如果资料库里没有相关资料，系统会尽量显示资料不足状态，但后续仍需要通过评估样例、真实模型调用或 LangChain 问答链继续收紧回答边界。

## 重要文档

- 通用成长学习助手App简单版PRD.md
- docs/README.md
- docs/status/当前状态.md
- docs/status/第二版阶段验收记录.md
- docs/status/项目进度记录.md
- docs/status/MVP第一版进度评估与下一步计划.md
- docs/daily/2026-07-02工作安排.md
- docs/planning/两人协作开发分工文档.md
- docs/planning/第一版功能开发边界与分工.md
- docs/planning/第一版技术实现方案.md
- docs/planning/每日工作安排规则.md
- docs/planning/第二版项目计划书.md
- docs/api/资料与AI模块字段和API草案.md
- docs/api/RAG-chunks接口说明.md
- docs/api/第二版AI问答接口交接.md
- docs/modules/目标模块前后端接口对照.md
- docs/modules/资料模块前后端接口对照.md

## 版本控制

本项目使用 Git 管理。

推荐开发流程：

```text
1. git switch dev
2. git pull origin dev
3. git switch -c feature/your-task
4. 完成功能并自测
5. git add .
6. git commit -m "type: 描述"
7. git push origin feature/your-task
8. 在 GitHub 创建 PR 合并到 dev
```

## 后续计划

- 接入真实大模型接口
- 保存并读取历史问答记录
- 增加 AI 回答评估样例
- 支持 PDF 文件上传和解析
- 增加用户登录
- 增加用户数据隔离
- 增加 GitHub Actions CI
- 部署后端和前端
- 打包为移动端 App
