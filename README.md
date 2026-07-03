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
- 支持按资料保存和读回历史问答
- 支持从资料历史问答生成复盘草稿：闪卡草稿或复习点
- 支持用户确认后把复盘草稿加入正式闪卡，并保存已掌握 / 还要复习状态
- 支持任务打卡和进度查看
- 支持基础登录注册和用户数据隔离
- 目标、任务、打卡、资料、摘要、闪卡、测试题、资料片段、资料问答记录已接入后端 SQLite 持久化

当前第二版已完成的 AI 学习链路：

```text
添加资料 -> 生成 chunks -> 搜索资料片段 -> 围绕资料问 AI -> 展示 answer / basis / suggestion / references -> 保存并读回历史问答 -> 从问答生成复盘草稿 -> 加入正式闪卡 -> 复习打分保存
```

当前限制：

```text
1. /api/agent/ask 默认仍使用 mock / rule-based 问答底座。
2. 已提供 OpenAI-compatible Provider 入口；配置 LLM_PROVIDER、LLM_API_KEY 和 LLM_MODEL 后可切换真实模型。
3. 复盘草稿本身仍保存在前端 localStorage，用户点击“加入闪卡”后会写入后端 flashcards 表。
4. 第二版只保存 new / known / review 状态，不做完整间隔重复日程。
5. 资料不足判断已有提示和真实模型联调样例，后续更换模型时需要复跑评估样例。
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

## 可选：配置真实模型 Provider

默认不配置任何密钥时，系统使用 `MockLLMProvider`，本地测试和 smoke 不受影响。

如果要联调兼容 OpenAI Chat Completions 形状的模型服务，可以复制本地配置文件：

```powershell
Copy-Item backend/.env.example backend/.env
```

然后编辑 `backend/.env`：

```env
LLM_PROVIDER=openai-compatible
LLM_API_KEY=你的密钥
LLM_MODEL=glm-4-flash-250414
LLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4
LLM_TIMEOUT_SECONDS=30
```

`backend/.env` 已加入 `.gitignore`，不要提交真实 API Key。

也可以临时用 PowerShell 环境变量启动，环境变量会优先于 `.env`：

```powershell
$env:LLM_PROVIDER="openai-compatible"
$env:LLM_API_KEY="你的密钥"
$env:LLM_MODEL="你的模型名称"
$env:LLM_BASE_URL="https://api.openai.com/v1"
$env:LLM_TIMEOUT_SECONDS="20"
python -m uvicorn backend.app.main:app --reload
```

说明：

```text
1. LLM_API_KEY 或 LLM_MODEL 缺失时会自动回退 mock。
2. 模型调用失败、超时或返回格式不可解析时会自动回退 mock。
3. 兼容服务需要提供 /chat/completions 接口。
4. 后端会读取 backend/.env，但不会覆盖系统环境变量。
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
material_qa_records
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

当前问答默认通过 `POST /api/agent/ask` 基于资料 chunks 返回 mock / rule-based 结果。配置 `openai-compatible` Provider 后，可以把同一套检索和返回结构切到真实模型。

如果资料库里没有相关资料，系统会尽量显示资料不足状态，但后续仍需要通过评估样例、真实模型调用或 LangChain 问答链继续收紧回答边界。

## 重要文档

- 通用成长学习助手App简单版PRD.md
- docs/README.md
- docs/status/当前状态.md
- docs/status/第二版阶段验收记录.md
- docs/status/第二版最终验收记录.md
- docs/status/第二版验收样例与演示脚本.md
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
- docs/api/LLM-provider设计说明.md
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

- 增加 AI 回答评估样例
- 更换真实模型时复跑 OpenAI-compatible Provider 三类验收样例
- 评估是否接入 LangChain 问答链
- 评估是否增加完整间隔重复日程
- 支持 PDF 文件上传和解析
- 增加 GitHub Actions CI
- 部署后端和前端
- 打包为移动端 App
