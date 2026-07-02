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

  if (selectedGoalId && state.goals.some((goal) => goal.id === selectedGoalId)) {
    await loadSelectedGoalFromApi(selectedGoalId);
  } else {
    clearSelectedGoal();
  }
}

async function loadSelectedGoalFromApi(goalId) {
  const [goal, tasks, progress] = await Promise.all([
    goalApi.getGoal(goalId),
    goalApi.listGoalTasks(goalId),
    goalApi.getGoalProgress(goalId)
  ]);

  selectedGoalId = goalId;
  state.selectedGoal = goalFromApi(goal);
  state.selectedGoalTasks = tasks.map(taskFromApi);
  state.selectedGoalProgress = progressFromApi(progress);
}

function clearSelectedGoal() {
  selectedGoalId = "";
  state.selectedGoal = null;
  state.selectedGoalTasks = [];
  state.selectedGoalProgress = null;
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
    render();
    showSuccess("计划已重新生成");
  } catch (error) {
    showError(error);
  } finally {
    setButtonLoading(triggerButton, false);
  }
}

async function regenerateGoalPlan(goalId, triggerButton = null) {
  const days = getPlanDays("goal-plan-days");
  const hasTasks = selectedGoalId === goalId && state.selectedGoalTasks.length > 0;
  if (hasTasks && !window.confirm(`将覆盖该目标已有任务，并重新生成 ${days} 天计划。确认继续吗？`)) return;

  setButtonLoading(triggerButton, true, "生成中");

  try {
    selectedGoalId = goalId;
    await generatePlanForGoalApi(goalId, days);
    await loadGoalDataFromApi();
    render();
    showSuccess("目标计划已更新");
  } catch (error) {
    showError(error);
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
  selectedGoalId = goalId;
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
    done: task.done,
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
    render();
    if (successMessage) showSuccess(successMessage);
  } catch (error) {
    showError(error);
  }
}

function renderToday() {
  const list = document.getElementById("today-task-list");
  document.getElementById("today-date-filter").value = selectedTaskDate;
  list.innerHTML = "";

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
        try {
          await goalApi.checkinTask(task.id, event.currentTarget.checked);
          await loadGoalDataFromApi();
          render();
          showSuccess(event.currentTarget.checked ? "任务已打卡" : "已取消打卡");
        } catch (error) {
          event.currentTarget.checked = task.done;
          showError(error);
        }
      });
      list.appendChild(item);
    });
  }

  const currentGoal = state.goals[0];
  document.getElementById("focus-title").textContent = currentGoal
    ? currentGoal.name
    : "先创建一个成长目标";
  document.getElementById("focus-text").textContent = currentGoal
    ? `${currentGoal.subject}｜${currentGoal.level}｜每天 ${currentGoal.dailyMinutes} 分钟`
    : "设置目标后，系统会根据资料和截止时间生成行动计划。";
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
    render();
    showSuccess(done ? "任务已打卡" : "已取消打卡");
  } catch (error) {
    showError(error);
  }
}
