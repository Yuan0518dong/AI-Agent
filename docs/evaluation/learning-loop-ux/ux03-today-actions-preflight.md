# UX-03 Today Actions 实施前检查

日期：2026-07-22
分支：`feature/learning-loop-ux`
基线：`personal/main@9d2c59f`；UX-01 纠偏本地提交 `e0f1014`

## 启动卡

- 为什么做：登录后的今日页已有 Dashboard 摘要，但学习者仍需要在一个确定性、可解释且不消耗模型的区域看到真正未完成的下一步。
- 练什么：受限读模型设计、跨目标隔离、无副作用的跨视图路由与端到端网络断言。
- 怎么验：五类乱序 fixture 的固定排序和上限；Dashboard 先渲染；Today Actions 失败可单独重试；五类入口只导航；Provider、`/api/agent/context`、`/api/agent/decide`、`/api/agent/ask`、Run advance 均为零。
- 留什么证据：后端专项测试、Playwright 网络断言与截图、离线验收报告、本地提交。
- 停止边界：不实现 UX-02/UX-04、完整目标工作区聚合、数据库迁移、FSRS 参数调整、真实 Provider 测评或远程操作。

## 已核对的事实

| 区域 | 当前实现 | UX-03 结论 |
| --- | --- | --- |
| Dashboard | `GET /api/dashboard`，认证后的 `enterApp()` 只等待它完成 | 保留为第一屏，不把 Today Actions 合并进该接口 |
| Agent Context | `build_agent_context()` 会逐资料读取 summary、chunks、QA、闪卡、测试和 attempts | 禁止 Today 调用或 import Context、Decision、Provider |
| 任务 | `tasks JOIN goals` 可按用户隔离；现有 `list_tasks_by_date()` 不含逾期 | 新服务直接执行有界 SQL，分别读取未完成逾期和今日任务 |
| 到期闪卡 | `list_due_flashcards(None, user_id, limit)` 已按 `due_at ASC, id ASC` 排序 | 复用并只投影 `id/materialId/goalId/materialTitle/dueAt` |
| 薄弱点 | `list_weak_points_for_scope()` 已按资料范围隔离，但缺少 `goalId` | 补入 `goalId`，只保留 `resolved=false` 的前三条 |
| 助手草稿 | `list_agent_drafts()` 已按用户和状态过滤，原顺序为最新优先 | 增加最早优先选项，Today 只投影草稿 ID、Run、目标、类型和时间，不返回 payload |
| 前端刷新 | Today 日期切换会调用 `refreshGoalData()`，其后读取完整 Agent Context | 改为 Dashboard 与 Today Actions 的独立刷新；不读取 Context |

## API 合同

```text
GET /api/today/actions?limit=15
limit: 1..15，默认 15
```

响应只包含：

```json
{
  "date": "YYYY-MM-DD",
  "limit": 15,
  "items": [{
    "id": "实体 ID",
    "kind": "overdue_task | today_task | due_flashcard | weak_point | pending_confirmation",
    "label": "类别标签",
    "title": "用户可读标题",
    "detail": "有限的定位说明",
    "goalId": "目标 ID",
    "target": {
      "view": "goals | memory | agent",
      "taskId": "可选",
      "materialId": "可选",
      "flashcardId": "可选",
      "quizId": "可选",
      "runId": "可选",
      "draftId": "可选"
    }
  }],
  "categoryCounts": {"...": 0}
}
```

不返回资料正文、chunks、完整 Agent Context、Decision、时间线或草稿 payload。`categoryCounts` 仅计入已受每类上限约束、实际展示的条目。

## 固定排序与路由

每类最多 3 条，先按下列类别顺序拼接，再按全局 `limit` 截断：

1. `overdue_task`：`date ASC`、`high > normal > low > unknown`、`id ASC`；进入目标详情并聚焦任务。
2. `today_task`：`high > normal > low > unknown`、`id ASC`；进入目标详情并聚焦任务。
3. `due_flashcard`：`dueAt ASC`、`flashcardId ASC`；进入复习并定位闪卡。
4. `weak_point`：`latestAttemptAt DESC`、`quizId ASC`；进入复习并定位现有测试题。
5. `pending_confirmation`：`createdAt ASC`、`id ASC`；进入指定 Run 的智能助手并定位该 Run。

时间缺失或不可识别时排在本类末尾，再用实体 ID 稳定收口。路由遵循 `goalId -> entity -> view -> focus`；实体删除或不属于当前用户时显示安全错误，不回退到其他数据。入口不产生打卡、评级、确认、问答或 Agent Run 写入。

## 降级与测试合同

- Dashboard 与 Today Actions 使用独立状态：Dashboard 成功而行动区失败时，保留 Dashboard，显示单独重试；不能把本地旧结果冒充当前结果。
- 登录先 await Dashboard 并 render，再异步加载 Today Actions。
- 后端 fixture 覆盖五类、排序、各类上限、总上限、参数校验、跨用户/跨目标隔离、轻量字段与 Provider 0；将 `build_agent_context()` 和 Provider 调用替换为抛错后，Today 请求仍须成功。
- Playwright 覆盖 Dashboard 首屏先完成、行动区 loading/error/retry、五类只读路由、桌面/390px、axe、无 page/console error，且网络没有 Context/Decision/Ask/Run advance 请求。
