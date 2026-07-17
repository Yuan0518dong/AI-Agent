// goals module extracted from app.js.

async function loadGoalDataFromApi() {
  const [goals, todayTasks, progress] = await Promise.all([
    goalApi.listGoals(),
    goalApi.listTodayTasks(selectedTaskDate),
    goalApi.listProgress()
  ]);

  state.goals = goals.map(goalFromApi);
  state.tasks = todayTasks.map(taskFromApi);
  state.progress = progress.map(progressFromApi);
  state.loadedViews.goals = true;

  if (selectedGoalId && state.goals.some((goal) => goal.id === selectedGoalId)) {
    await loadSelectedGoalFromApi(selectedGoalId);
  } else if (state.goals.length === 1) {
    await loadSelectedGoalFromApi(state.goals[0].id);
  } else {
    clearSelectedGoal();
  }
  await loadDashboardDataFromApi();
  saveState();
}

async function loadSelectedGoalFromApi(goalId) {
  const [goal, tasks, progress] = await Promise.all([
    goalApi.getGoal(goalId),
    goalApi.listGoalTasks(goalId),
    goalApi.getGoalProgress(goalId)
  ]);

  setSelectedGoalId(goalId);
  state.selectedGoal = goalFromApi(goal);
  state.selectedGoalTasks = tasks.map(taskFromApi);
  state.selectedGoalProgress = progressFromApi(progress);
  saveState();
}

function clearSelectedGoal() {
  setSelectedGoalId("");
  state.selectedGoal = null;
  state.selectedGoalTasks = [];
  state.selectedGoalProgress = null;
  saveState();
}

function setSelectedGoalId(goalId) {
  selectedGoalId = goalId || "";
  state.selectedGoalId = selectedGoalId;
  saveState();
}

async function generatePlanForGoalApi(goalId, days = 7) {
  return goalApi.generatePlan(goalId, days);
}

async function generatePlansForAllGoals(days = 7, triggerButton = null) {
  if (state.goals.length === 0) {
    showError(new Error("请先创建目标"));
    return;
  }

  if (!window.confirm(`将为所有目标重新生成 ${days} 天计划，已有任务会被覆盖。确认继续吗？`)) return;

  setButtonLoading(triggerButton, true, "生成中");

  try {
    for (const goal of state.goals) {
      await generatePlanForGoalApi(goal.id, days);
    }

    await loadGoalDataFromApi();
    await loadAgentContextFromApi();
    render();
    showSuccess("计划已重新生成");
  } catch (error) {
    showError(error);
  } finally {
    setButtonLoading(triggerButton, false);
  }
}

async function regenerateGoalPlan(goalId, triggerButton = null, days = getPlanDays("goal-plan-days")) {
  const hasTasks = selectedGoalId === goalId && state.selectedGoalTasks.length > 0;
  if (hasTasks && !window.confirm(`将覆盖该目标已有任务，并重新生成 ${days} 天计划。确认继续吗？`)) {
    return false;
  }

  setButtonLoading(triggerButton, true, "生成中");

  try {
    setSelectedGoalId(goalId);
    await generatePlanForGoalApi(goalId, days);
    await loadGoalDataFromApi();
    await loadAgentContextFromApi();
    render();
    showSuccess("目标计划已更新");
    return true;
  } catch (error) {
    showError(error);
    return false;
  } finally {
    setButtonLoading(triggerButton, false);
  }
}

async function selectGoal(goalId) {
  try {
    await loadSelectedGoalFromApi(goalId);
    render();
  } catch (error) {
    showError(error);
  }
}

function startGoalEdit(goalId) {
  const goal = state.goals.find((item) => item.id === goalId) || state.selectedGoal;
  if (!goal) return;

  editingGoalId = goalId;
  setSelectedGoalId(goalId);
  fillGoalForm(goal);
  renderGoalFormMode();
  switchView("goals");
  document.getElementById("goal-form").scrollIntoView({ behavior: "smooth", block: "start" });
}

function cancelGoalEdit() {
  editingGoalId = "";
  document.getElementById("goal-form").reset();
  renderGoalFormMode();
}

function fillGoalForm(goal) {
  const form = document.getElementById("goal-form");
  form.elements.name.value = goal.name || "";
  form.elements.subject.value = goal.subject || "";
  form.elements.level.value = goal.level || "刚开始";
  form.elements.deadline.value = goal.deadline || "";
  form.elements.dailyMinutes.value = String(goal.dailyMinutes || 60);
  form.elements.notes.value = goal.notes || "";
}

function goalFromApi(goal) {
  return {
    id: goal.id,
    name: goal.name,
    subject: goal.subject,
    level: goal.level,
    deadline: goal.deadline,
    dailyMinutes: goal.daily_minutes,
    notes: goal.notes || "",
    createdAt: goal.created_at,
    updatedAt: goal.updated_at
  };
}

function taskFromApi(task) {
  return {
    id: task.id,
    goalId: task.goal_id,
    title: task.title,
    detail: task.detail,
    date: task.date,
    priority: task.priority,
    done: task.done,
    goalName: task.goalName || "",
    dailyMinutes: Number(task.dailyMinutes || 0),
    completedAt: task.completed_at,
    createdAt: task.created_at,
    updatedAt: task.updated_at
  };
}

function progressFromApi(progress) {
  return {
    goalId: progress.goal_id,
    goalName: progress.goal_name,
    totalTasks: progress.total_tasks,
    completedTasks: progress.completed_tasks,
    completionRate: progress.completion_rate,
    todayTotal: progress.today_total,
    todayCompleted: progress.today_completed
  };
}

function getPlanDays(elementId) {
  const value = Number(document.getElementById(elementId)?.value || 7);
  return Number.isFinite(value) ? value : 7;
}

async function refreshGoalData(successMessage = "") {
  try {
    await loadGoalDataFromApi();
    await loadAgentContextFromApi();
    render();
    if (successMessage) showSuccess(successMessage);
  } catch (error) {
    showError(error);
  }
}

function getTaskGoal(task) {
  const goal = state.goals.find((item) => item.id === task.goalId);
  if (goal) return goal;
  if (task.goalName || task.dailyMinutes) {
    return {
      id: task.goalId,
      name: task.goalName || "当前目标",
      dailyMinutes: task.dailyMinutes || 0
    };
  }
  return null;
}

function getTaskMinutes(task) {
  const goalMinutes = Number(getTaskGoal(task)?.dailyMinutes || 0);
  if (goalMinutes > 0) return goalMinutes;

  const matched = String(task.detail || "").match(/(\d+)\s*(分钟|minutes?)/i);
  return matched ? Number(matched[1]) : 30;
}

function getTodayStats() {
  const tasks = state.tasks;
  const completedTasks = tasks.filter((task) => task.done);
  const totalMinutes = tasks.reduce((sum, task) => sum + getTaskMinutes(task), 0);
  const completedMinutes = completedTasks.reduce((sum, task) => sum + getTaskMinutes(task), 0);
  const reviewCards = state.flashcards.filter((card) => card.status !== "known");
  const quizAttempts = Object.values(state.quizAttempts || {}).flat();
  const attemptedQuizIds = new Set(quizAttempts.map((attempt) => attempt.quizId));
  const completionRate = tasks.length ? Math.round((completedTasks.length / tasks.length) * 100) : 0;

  return {
    tasks,
    completedTasks,
    pendingTasks: tasks.filter((task) => !task.done),
    totalMinutes,
    completedMinutes,
    reviewCount: reviewCards.length,
    quizTotal: state.quizzes.length,
    quizAttempted: attemptedQuizIds.size,
    completionRate
  };
}

function getGoalProgress(goalId) {
  const loadedProgress = state.progress.find((item) => item.goalId === goalId);
  if (loadedProgress) return loadedProgress;
  const dashboardGoal = state.dashboard?.primaryGoal;
  if (dashboardGoal?.id === goalId && dashboardGoal.progress) {
    return progressFromApi(dashboardGoal.progress);
  }
  return null;
}

function getPrimaryGoal(stats) {
  const pendingGoalId = stats.pendingTasks.find((task) => task.goalId)?.goalId;
  if (pendingGoalId) {
    const pendingGoal = state.goals.find((goal) => goal.id === pendingGoalId);
    if (pendingGoal) return pendingGoal;
    if (state.dashboard?.primaryGoal?.id === pendingGoalId) {
      return goalFromApi(state.dashboard.primaryGoal);
    }
  }

  if (selectedGoalId) {
    const selected = state.goals.find((goal) => goal.id === selectedGoalId);
    if (selected) return selected;
  }

  const todayGoalId = stats.tasks.find((task) => task.goalId)?.goalId;
  if (todayGoalId) {
    return state.goals.find((goal) => goal.id === todayGoalId) || null;
  }

  if (state.goals[0]) return state.goals[0];
  return state.dashboard?.primaryGoal ? goalFromApi(state.dashboard.primaryGoal) : null;
}

function buildTodayAdvice(goal, stats, progress) {
  if (!goal) {
    return "先创建一个成长目标，再生成行动计划。这样今日页才能给出明确的学习路线。";
  }

  if (stats.tasks.length === 0) {
    return `当前主线是“${goal.name}”。建议先生成 ${getPlanDays("quick-plan-days")} 天计划，让系统拆出今天要完成的任务。`;
  }

  const firstPending = stats.pendingTasks.find((task) => task.goalId === goal.id) || stats.pendingTasks[0];
  if (firstPending) {
    return `先完成“${firstPending.title}”，预计 ${getTaskMinutes(firstPending)} 分钟。完成后再处理 ${stats.reviewCount} 张待复习闪卡。`;
  }

  if (stats.reviewCount > 0) {
    return `今日任务已完成。建议进入记忆训练，优先复习 ${stats.reviewCount} 张未掌握或新闪卡。`;
  }

  if (stats.quizTotal > stats.quizAttempted) {
    return `今日任务已完成。还可以做 ${stats.quizTotal - stats.quizAttempted} 道测试题，检查资料理解是否扎实。`;
  }

  return `今天节奏很好，主线目标整体完成率 ${progress?.completionRate || 0}%。可以查看进度页复盘下一步。`;
}

function setFocusButton(button, disabled, handler) {
  if (!button) return;
  button.disabled = disabled;
  button.onclick = disabled ? null : handler;
}

function renderTodayFocus(stats) {
  const title = document.getElementById("focus-title");
  if (!title) return;

  const goal = getPrimaryGoal(stats);
  const progress = goal ? getGoalProgress(goal.id) : null;
  const goalTasks = goal ? stats.tasks.filter((task) => task.goalId === goal.id) : [];
  const goalCompleted = goalTasks.filter((task) => task.done).length;
  const remaining = goal ? getRemainingDays(goal.deadline) : "-";
  const status = goal
    ? progress?.completionRate >= 100
      ? "已完成"
      : "进行中"
    : "未开始";

  document.getElementById("focus-status").textContent = status;
  document.getElementById("focus-badge").textContent = goal?.name ? goal.name.slice(0, 1) : "目";
  title.textContent = goal ? goal.name : "先创建一个成长目标";
  document.getElementById("focus-text").textContent = goal
    ? `${goal.subject} | ${goal.level} | 每天 ${goal.dailyMinutes} 分钟`
    : "设置目标后，系统会根据资料和截止时间生成行动计划。";
  document.getElementById("focus-rate").textContent = `${progress?.completionRate || 0}%`;
  document.getElementById("focus-remaining").textContent = goal ? `${remaining} 天` : "-";
  document.getElementById("focus-today").textContent = goal ? `${goalCompleted}/${goalTasks.length}` : "0/0";
  document.getElementById("focus-advice").textContent = buildTodayAdvice(goal, stats, progress);

  setFocusButton(document.getElementById("focus-view-goal"), !goal, async () => {
    await selectGoal(goal.id);
    switchView("goals");
  });
  setFocusButton(document.getElementById("focus-view-progress"), !goal, () => switchView("progress"));
  setFocusButton(document.getElementById("focus-generate-plan"), !goal, (event) => {
    regenerateGoalPlan(goal.id, event.currentTarget, getPlanDays("quick-plan-days"));
  });
}

function renderTodayDashboard() {
  const ring = document.getElementById("today-progress-ring");
  if (!ring) return;

  const stats = getTodayStats();
  const taskTotal = stats.tasks.length;
  const pendingTotal = stats.pendingTasks.length;
  const isToday = selectedTaskDate === todayString();
  const dateText = isToday ? "今天" : selectedTaskDate;
  const rate = Math.min(100, Math.max(0, stats.completionRate));
  const nextTasks = (stats.pendingTasks.length ? stats.pendingTasks : stats.completedTasks).slice(0, 3);

  ring.style.background = `conic-gradient(var(--blue) ${rate * 3.6}deg, #e8edf5 0deg)`;
  document.getElementById("today-progress-value").textContent = `${rate}%`;
  document.getElementById("today-progress-label").textContent = taskTotal ? "今日完成率" : "暂无任务";
  document.getElementById("today-progress-bar").style.width = `${rate}%`;
  document.getElementById("today-date-label").textContent = dateText;
  document.getElementById("today-study-minutes").textContent = `${stats.completedMinutes}/${stats.totalMinutes} 分`;
  document.getElementById("today-study-text").textContent = taskTotal
    ? `已完成 ${stats.completedTasks.length} / ${taskTotal} 项任务`
    : "今日暂无学习时长";
  document.getElementById("today-next-count").textContent = taskTotal
    ? `${pendingTotal} 项待完成`
    : "0 项";
  renderTodayFocus(stats);

  const goalTotal = state.dashboard?.summary?.goalTotal ?? state.goals.length;
  if (goalTotal === 0) {
    document.getElementById("today-headline").textContent = "先创建目标，让系统生成今日行动";
    document.getElementById("today-suggestion").textContent = "目标、资料和任务接入后，今日页会自动汇总学习节奏。";
  } else if (taskTotal === 0) {
    document.getElementById("today-headline").textContent = `${dateText} 暂无任务`;
    document.getElementById("today-suggestion").textContent = "可以选择计划天数并生成计划，或切换日期查看其他任务。";
  } else if (pendingTotal === 0) {
    document.getElementById("today-headline").textContent = `${dateText} 任务已完成`;
    document.getElementById("today-suggestion").textContent = "可以进入记忆训练复习闪卡，或查看进度页确认整体完成情况。";
  } else {
    document.getElementById("today-headline").textContent = `${dateText} 还有 ${pendingTotal} 项任务`;
    document.getElementById("today-suggestion").textContent = "优先完成下方未打卡任务，再进入资料问答或闪卡复习巩固。";
  }

  const nextList = document.getElementById("today-next-list");
  nextList.innerHTML = "";
  if (nextTasks.length === 0) {
    nextList.appendChild(emptyNode("暂无今日重点", "创建目标并生成计划后，这里会显示最应该先做的任务。"));
    return;
  }

  nextTasks.forEach((task) => {
    const goal = getTaskGoal(task);
    const item = document.createElement("article");
    item.className = `today-next-item ${task.done ? "done" : ""}`;
    item.innerHTML = `
      <span>${task.done ? "已完成" : "待完成"}</span>
      <div>
        <strong>${escapeHtml(task.title)}</strong>
        <p>${escapeHtml(goal ? `${goal.name} · ${getTaskMinutes(task)} 分钟` : `${getTaskMinutes(task)} 分钟`)}</p>
      </div>
    `;
    nextList.appendChild(item);
  });
}

function renderToday() {
  const list = document.getElementById("today-task-list");
  const goalTotal = state.dashboard?.summary?.goalTotal ?? state.goals.length;
  const gettingStarted = document.getElementById("getting-started");
  const dashboardContent = document.getElementById("dashboard-content");
  gettingStarted.hidden = goalTotal > 0;
  dashboardContent.hidden = goalTotal === 0;
  if (goalTotal === 0) return;
  document.getElementById("today-date-filter").value = selectedTaskDate;
  list.innerHTML = "";
  renderTodayDashboard();

  if (state.tasks.length === 0) {
    list.appendChild(emptyNode("还没有任务", `${selectedTaskDate} 暂无任务，可以创建目标或重新生成计划。`));
  } else {
    state.tasks.slice(0, 10).forEach((task) => {
      const item = document.createElement("article");
      item.className = "item";
      item.innerHTML = `
        <label class="check-row">
          <input type="checkbox" ${task.done ? "checked" : ""} data-task-id="${task.id}" />
          <span>
            <strong>${escapeHtml(task.title)}</strong>
            <p>${escapeHtml(task.detail)}</p>
          </span>
        </label>
      `;
      item.querySelector("input").addEventListener("change", async (event) => {
        const checkbox = event.currentTarget;
        const checked = checkbox.checked;
        try {
          await goalApi.checkinTask(task.id, checked);
          await loadGoalDataFromApi();
          await loadAgentContextFromApi();
          render();
          showSuccess(checked ? "任务已打卡" : "已取消打卡");
        } catch (error) {
          checkbox.checked = task.done;
          showError(error);
        }
      });
      list.appendChild(item);
    });
  }
}

function renderGoals() {
  const list = document.getElementById("goal-list");
  list.innerHTML = "";

  if (state.goals.length === 0) {
    list.appendChild(emptyNode("暂无成长目标", "从左侧表单创建第一个目标。"));
    return;
  }

  state.goals.forEach((goal) => {
    const item = document.createElement("article");
    item.className = "item";
    item.innerHTML = `
      <div class="item-head">
        <div>
          <h3>${escapeHtml(goal.name)}</h3>
          <p>${escapeHtml(goal.notes || "暂无重点难点说明")}</p>
        </div>
        <div class="inline-actions">
          <button class="ghost-button" data-action="detail" title="查看目标详情">详情</button>
          <button class="ghost-button" data-action="edit" title="编辑目标">编辑</button>
          <button class="ghost-button" data-action="plan" title="重新生成计划">计划</button>
          <button class="ghost-button" data-action="delete" title="删除目标">×</button>
        </div>
      </div>
      <div class="tag-row">
        <span class="tag">${escapeHtml(goal.subject)}</span>
        <span class="tag">${escapeHtml(goal.level)}</span>
        <span class="tag">每天 ${goal.dailyMinutes} 分钟</span>
        <span class="tag">截止 ${escapeHtml(goal.deadline)}</span>
      </div>
    `;
    item.querySelector('[data-action="detail"]').addEventListener("click", () => selectGoal(goal.id));
    item.querySelector('[data-action="edit"]').addEventListener("click", () => startGoalEdit(goal.id));
    item.querySelector('[data-action="plan"]').addEventListener("click", (event) => {
      regenerateGoalPlan(goal.id, event.currentTarget);
    });
    item.querySelector('[data-action="delete"]').addEventListener("click", () => deleteGoal(goal.id));
    list.appendChild(item);
  });
}

function renderGoalFormMode() {
  const title = document.getElementById("goal-form-title");
  const submitButton = document.getElementById("goal-submit-button");
  const cancelButton = document.getElementById("cancel-goal-edit");

  if (editingGoalId) {
    title.textContent = "编辑成长目标";
    submitButton.textContent = "保存修改";
    cancelButton.hidden = false;
  } else {
    title.textContent = "新建成长目标";
    submitButton.textContent = "＋ 创建目标";
    cancelButton.hidden = true;
  }
}

function renderGoalDetail() {
  const panel = document.getElementById("goal-detail-panel");
  const detail = document.getElementById("goal-detail");

  if (!state.selectedGoal) {
    panel.hidden = true;
    detail.innerHTML = "";
    return;
  }

  panel.hidden = false;
  const goal = state.selectedGoal;
  const progress = state.selectedGoalProgress || {
    completionRate: 0,
    completedTasks: 0,
    totalTasks: 0,
    todayCompleted: 0,
    todayTotal: 0
  };
  const tasks = state.selectedGoalTasks;
  const remaining = getRemainingDays(goal.deadline);
  const taskDrafts = getAgentTaskDraftsForGoal(goal.id);
  const taskDraftRows = renderAgentTaskDrafts(taskDrafts);
  const taskRows = tasks.length
    ? tasks.map((task) => `
      <div class="task-row ${task.done ? "done" : ""}">
        <span>${escapeHtml(task.date)}</span>
        <div>
          <strong>${escapeHtml(task.title)}</strong>
          <p>${escapeHtml(task.detail || "")}</p>
          ${task.completedAt ? `<p>完成时间：${escapeHtml(formatDateTime(task.completedAt))}</p>` : ""}
        </div>
        <label class="task-check">
          <input class="detail-task-check" type="checkbox" data-task-id="${escapeHtml(task.id)}" ${task.done ? "checked" : ""} />
          <span>${task.done ? "已完成" : "打卡"}</span>
        </label>
      </div>
    `).join("")
    : `<div class="empty"><strong>暂无任务</strong><p>点击目标卡片中的“计划”生成行动任务。</p></div>`;

  detail.innerHTML = `
    <article class="item">
      <div class="item-head">
        <div>
          <h3>${escapeHtml(goal.name)}</h3>
          <p>${escapeHtml(goal.notes || "暂无重点难点说明")}</p>
        </div>
        <div class="inline-actions">
          <button class="ghost-button" id="detail-edit-goal">编辑</button>
          <button class="ghost-button" id="detail-plan-goal">重新生成计划</button>
        </div>
      </div>
      <div class="tag-row">
        <span class="tag">${escapeHtml(goal.subject)}</span>
        <span class="tag">${escapeHtml(goal.level)}</span>
        <span class="tag">每天 ${goal.dailyMinutes} 分钟</span>
        <span class="tag">截止 ${escapeHtml(goal.deadline)}</span>
      </div>
      <div class="detail-grid">
        <div class="detail-stat"><span>完成率</span><strong>${progress.completionRate}%</strong></div>
        <div class="detail-stat"><span>总任务</span><strong>${progress.totalTasks}</strong></div>
        <div class="detail-stat"><span>已完成</span><strong>${progress.completedTasks}</strong></div>
        <div class="detail-stat"><span>今日进度</span><strong>${progress.todayCompleted}/${progress.todayTotal}</strong></div>
        <div class="detail-stat"><span>剩余天数</span><strong>${remaining}</strong></div>
      </div>
      ${taskDraftRows}
      <h4>行动任务</h4>
      <div class="task-list">${taskRows}</div>
    </article>
  `;

  document.getElementById("detail-edit-goal").addEventListener("click", () => startGoalEdit(goal.id));
  document.getElementById("detail-plan-goal").addEventListener("click", (event) => {
    regenerateGoalPlan(goal.id, event.currentTarget);
  });
  detail.querySelectorAll(".detail-task-check").forEach((checkbox) => {
    checkbox.addEventListener("change", (event) => {
      checkinTaskFromDetail(event.currentTarget.dataset.taskId, event.currentTarget.checked);
    });
  });
  detail.querySelectorAll('[data-action="apply-agent-task-draft"]').forEach((button) => {
    button.addEventListener("click", (event) => {
      applyAgentTaskDraft(event.currentTarget.dataset.draftId, event.currentTarget);
    });
  });
  detail.querySelectorAll('[data-action="delete-agent-task-draft"]').forEach((button) => {
    button.addEventListener("click", (event) => {
      deleteAgentTaskDraft(event.currentTarget.dataset.draftId);
    });
  });
}

function getAgentTaskDraftsForGoal(goalId) {
  return (state.agentTaskDrafts || []).filter((draft) => draft.goalId === goalId);
}

function renderAgentTaskDrafts(drafts) {
  if (!drafts.length) return "";

  return `
    <section class="agent-task-draft-panel">
      <div class="agent-task-draft-head">
        <div>
          <h4>智能体任务草稿</h4>
          <p>草稿不会直接改任务表，确认后才进入正式计划生成。</p>
        </div>
        <span>${drafts.length} 条</span>
      </div>
      <div class="agent-task-draft-list">
        ${drafts.slice(0, 3).map((draft) => renderAgentTaskDraftItem(draft)).join("")}
      </div>
    </section>
  `;
}

function renderAgentTaskDraftItem(draft) {
  return `
    <article class="agent-task-draft-item" data-agent-task-draft-id="${escapeHtml(draft.id)}">
      <div class="agent-task-draft-title">
        <div>
          <strong>${escapeHtml(draft.title)}</strong>
          <p>${escapeHtml(draft.reason || "智能体建议先生成待确认任务草稿。")}</p>
        </div>
        <span>${draft.suggestedDays} 天</span>
      </div>
      <div class="agent-task-draft-tasks">
        ${(draft.tasks || []).slice(0, 4).map((task) => `
          <div>
            <span>${escapeHtml(task.date || "")}</span>
            <p>${escapeHtml(task.title || "")}</p>
          </div>
        `).join("")}
      </div>
      <div class="agent-task-draft-actions">
        <button class="primary-button" data-action="apply-agent-task-draft" data-draft-id="${escapeHtml(draft.id)}" type="button">按草稿生成计划</button>
        <button class="ghost-button" data-action="delete-agent-task-draft" data-draft-id="${escapeHtml(draft.id)}" type="button">删除草稿</button>
      </div>
    </article>
  `;
}

async function applyAgentTaskDraft(draftId, triggerButton = null) {
  const draft = (state.agentTaskDrafts || []).find((item) => item.id === draftId);
  if (!draft) {
    showError(new Error("没有找到这条任务草稿"));
    return;
  }

  const days = Number(draft.suggestedDays || getPlanDays("goal-plan-days"));
  const applied = await regenerateGoalPlan(draft.goalId, triggerButton, days);
  if (!applied) return;

  state.agentTaskDrafts = state.agentTaskDrafts.filter((item) => item.id !== draftId);
  saveState();
  render();
}

function deleteAgentTaskDraft(draftId) {
  state.agentTaskDrafts = (state.agentTaskDrafts || []).filter((draft) => draft.id !== draftId);
  saveAndRender();
  showSuccess("任务草稿已删除");
}

function focusAgentTaskDraft(draftId) {
  if (!draftId) return;
  requestAnimationFrame(() => {
    const draftNode = Array.from(document.querySelectorAll("[data-agent-task-draft-id]")).find((item) => {
      return item.dataset.agentTaskDraftId === draftId;
    });
    if (draftNode) {
      draftNode.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  });
}

function generatePlanForGoal(goal) {
  state.tasks = state.tasks.filter((task) => task.goalId !== goal.id);
  const topics = collectTopics(goal);
  const days = Math.min(7, Math.max(3, daysUntil(goal.deadline)));

  for (let index = 0; index < days; index += 1) {
    const topic = topics[index % topics.length];
    state.tasks.push({
      id: makeId(),
      goalId: goal.id,
      title: `第 ${index + 1} 天：学习 ${topic}`,
      detail: `${goal.dailyMinutes} 分钟学习，完成 1 次复述和 1 组闪卡复习。`,
      done: false,
      date: offsetDate(index)
    });
  }
}

function collectTopics(goal) {
  const materialPoints = state.materials.flatMap((item) => item.summary.keyPoints);
  const base = [goal.subject, goal.notes, ...materialPoints]
    .filter(Boolean)
    .flatMap((text) => splitSentences(text))
    .map((text) => text.slice(0, 24));
  return base.length ? base : [goal.subject || "核心知识点"];
}

async function deleteGoal(id) {
  if (!window.confirm("确认删除这个成长目标吗？")) return;

  try {
    await goalApi.deleteGoal(id);
    if (selectedGoalId === id) {
      clearSelectedGoal();
    }
    if (editingGoalId === id) {
      cancelGoalEdit();
    }
    await loadGoalDataFromApi();
    await loadAgentContextFromApi();
    render();
    showSuccess("目标已删除");
  } catch (error) {
    showError(error);
  }
}

async function checkinTaskFromDetail(taskId, done) {
  try {
    await goalApi.checkinTask(taskId, done);
    await loadGoalDataFromApi();
    await loadAgentContextFromApi();
    render();
    showSuccess(done ? "任务已打卡" : "已取消打卡");
  } catch (error) {
    showError(error);
  }
}
