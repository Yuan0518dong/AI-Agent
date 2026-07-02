const STORAGE_KEY = "student-assistant-mvp";
const defaultState = {
  goals: [],
  materials: [],
  tasks: [],
  progress: [],
  selectedGoal: null,
  selectedGoalTasks: [],
  selectedGoalProgress: null,
  flashcards: [],
  quizzes: [],
  activeConversationId: "default-conversation",
  aiConversations: [
    {
      id: "default-conversation",
      goalId: "",
      relatedMaterialIds: [],
      messages: [
        {
          id: "welcome-message",
          role: "assistant",
          content: "你好，我会根据你的目标和资料帮你学习。先创建一个成长目标，或添加一份资料。",
          createdAt: new Date().toISOString()
        }
      ],
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString()
    }
  ],
  chat: []
};

const state = loadState();
let activeCardIndex = 0;
let editingGoalId = "";
let selectedGoalId = "";
let selectedTaskDate = todayString();

const views = {
  today: "今日行动",
  goals: "成长目标",
  materials: "成长资料",
  study: "成长问答",
  memory: "记忆训练",
  progress: "成长进度"
};

document.querySelectorAll(".nav-item").forEach((button) => {
  button.addEventListener("click", () => switchView(button.dataset.view));
});

document.getElementById("goal-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const submitButton = document.getElementById("goal-submit-button");
  const data = new FormData(event.currentTarget);
  const payload = {
    name: data.get("name").trim(),
    subject: data.get("subject").trim(),
    level: data.get("level"),
    deadline: data.get("deadline"),
    daily_minutes: Number(data.get("dailyMinutes")),
    notes: data.get("notes").trim()
  };

  setButtonLoading(submitButton, true, editingGoalId ? "保存中" : "创建中");

  try {
    if (editingGoalId) {
      await goalApi.updateGoal(editingGoalId, payload);
      selectedGoalId = editingGoalId;
      editingGoalId = "";
      showSuccess("目标已更新");
    } else {
      const goal = await goalApi.createGoal(payload);

      selectedGoalId = goal.id;
      await generatePlanForGoalApi(goal.id, getPlanDays("goal-plan-days"));
      showSuccess("目标已创建，并生成行动计划");
    }

    form.reset();
    await loadGoalDataFromApi();
    render();
  } catch (error) {
    showError(error);
  } finally {
    setButtonLoading(submitButton, false);
  }
});

document.getElementById("cancel-goal-edit").addEventListener("click", () => {
  cancelGoalEdit();
});

document.getElementById("clear-goal-detail").addEventListener("click", () => {
  clearSelectedGoal();
  render();
});

document.getElementById("today-date-filter").addEventListener("change", async (event) => {
  selectedTaskDate = event.currentTarget.value || todayString();
  await refreshGoalData("任务日期已切换");
});

document.getElementById("reset-today-date").addEventListener("click", async () => {
  selectedTaskDate = todayString();
  document.getElementById("today-date-filter").value = selectedTaskDate;
  await refreshGoalData("已回到今天");
});

document.getElementById("material-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const data = new FormData(event.currentTarget);
  const content = data.get("content").trim();
  const timestamp = new Date().toISOString();
  const materialId = makeId();
  const summary = summarizeContent(content, {
    materialId,
    timestamp
  });
  const material = {
    id: materialId,
    goalId: "",
    title: data.get("title").trim(),
    type: data.get("type"),
    content,
    url: data.get("type") === "网页链接" ? content : "",
    summary,
    createdAt: timestamp,
    updatedAt: timestamp
  };

  state.materials.unshift(material);
  createMemoryItems(material);
  saveAndRender();
  event.currentTarget.reset();
});

document.getElementById("chat-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const data = new FormData(event.currentTarget);
  const question = data.get("question").trim();
  const timestamp = new Date().toISOString();
  const answer = answerQuestion(question);
  const conversation = getActiveConversation();
  conversation.messages.push({
    id: makeId(),
    role: "user",
    content: question,
    createdAt: timestamp
  });
  conversation.messages.push({
    id: makeId(),
    role: "assistant",
    content: answer.text,
    relatedMaterialIds: answer.relatedMaterialIds,
    createdAt: new Date().toISOString()
  });
  conversation.relatedMaterialIds = mergeUniqueIds(conversation.relatedMaterialIds, answer.relatedMaterialIds);
  conversation.updatedAt = new Date().toISOString();
  saveAndRender();
  event.currentTarget.reset();
});

document.getElementById("quick-plan").addEventListener("click", async (event) => {
  await generatePlansForAllGoals(getPlanDays("quick-plan-days"), event.currentTarget);
});

document.getElementById("generate-all-plans").addEventListener("click", async (event) => {
  await generatePlansForAllGoals(getPlanDays("goal-plan-days"), event.currentTarget);
});

document.getElementById("shuffle-cards").addEventListener("click", () => {
  if (state.flashcards.length === 0) return;
  activeCardIndex = (activeCardIndex + 1) % state.flashcards.length;
  renderFlashcard();
});

document.getElementById("card-known").addEventListener("click", () => rateCard("known"));
document.getElementById("card-review").addEventListener("click", () => rateCard("review"));

document.getElementById("export-data").addEventListener("click", () => {
  const blob = new Blob([JSON.stringify(state, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "student-assistant-data.json";
  link.click();
  URL.revokeObjectURL(url);
});

document.getElementById("reset-data").addEventListener("click", () => {
  const confirmed = window.confirm("确认清空所有本地学习数据吗？");
  if (!confirmed) return;
  localStorage.removeItem(STORAGE_KEY);
  Object.assign(state, normalizeState(structuredClone(defaultState)));
  activeCardIndex = 0;
  saveAndRender();
});

init();

async function init() {
  document.getElementById("today-date-filter").value = selectedTaskDate;

  try {
    await loadGoalDataFromApi();
  } catch (error) {
    showError(error);
  } finally {
    render();
  }
}

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

function showError(error) {
  console.error(error);
  showToast(error.message || "操作失败，请确认后端服务已经启动。", "error");
}

function showSuccess(message) {
  showToast(message, "success");
}

function showToast(message, type = "success") {
  const toast = document.getElementById("toast");
  toast.textContent = message;
  toast.className = `toast show ${type}`;
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => {
    toast.className = "toast";
  }, 2400);
}

function setButtonLoading(button, loading, loadingText = "处理中") {
  if (!button) return;

  if (loading) {
    button.dataset.originalText = button.textContent;
    button.textContent = loadingText;
    button.disabled = true;
    return;
  }

  button.textContent = button.dataset.originalText || button.textContent;
  button.disabled = false;
  delete button.dataset.originalText;
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

function loadState() {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return normalizeState(structuredClone(defaultState));

  try {
    const normalized = normalizeState({ ...structuredClone(defaultState), ...JSON.parse(raw) });
    localStorage.setItem(STORAGE_KEY, JSON.stringify(normalized));
    return normalized;
  } catch {
    return normalizeState(structuredClone(defaultState));
  }
}

function normalizeState(nextState) {
  const materialsByTitle = new Map();

  nextState.materials = nextState.materials.map((material) => {
    const timestamp = material.createdAt || new Date().toISOString();
    const normalized = {
      ...material,
      goalId: material.goalId || "",
      url: material.url || "",
      createdAt: timestamp,
      updatedAt: material.updatedAt || timestamp
    };
    normalized.summary = normalizeSummary(normalized);
    materialsByTitle.set(normalized.title, normalized.id);
    return normalized;
  });

  nextState.flashcards = nextState.flashcards.map((card) => {
    const timestamp = card.createdAt || new Date().toISOString();
    return {
      ...card,
      materialId: card.materialId || materialsByTitle.get(card.source) || "",
      status: card.status || "new",
      createdAt: timestamp,
      updatedAt: card.updatedAt || timestamp
    };
  });

  nextState.quizzes = nextState.quizzes.map((quiz) => {
    const timestamp = quiz.createdAt || new Date().toISOString();
    return {
      ...quiz,
      materialId: quiz.materialId || "",
      type: quiz.type || "short",
      options: quiz.options || [],
      explanation: quiz.explanation || "回到资料摘要和关键知识点中核对答案。",
      createdAt: timestamp,
      updatedAt: quiz.updatedAt || timestamp
    };
  });

  nextState.chat = nextState.chat.map((message) => {
    const timestamp = message.createdAt || new Date().toISOString();
    return {
      id: message.id || makeId(),
      role: message.role === "agent" ? "assistant" : message.role,
      content: message.content || message.text || "",
      relatedMaterialIds: message.relatedMaterialIds || [],
      createdAt: timestamp
    };
  });

  nextState.aiConversations = normalizeConversations(nextState.aiConversations, nextState.chat);
  const activeExists = nextState.aiConversations.some((conversation) => {
    return conversation.id === nextState.activeConversationId;
  });
  nextState.activeConversationId = activeExists
    ? nextState.activeConversationId
    : nextState.aiConversations[0].id;
  nextState.chat = getConversationMessages(nextState, nextState.activeConversationId);

  return nextState;
}

function normalizeConversations(conversations, legacyChat) {
  const hasLegacyChat = Array.isArray(legacyChat) && legacyChat.length;
  const hasRealConversations = Array.isArray(conversations)
    && conversations.some((conversation) => {
      const messageCount = Array.isArray(conversation.messages) ? conversation.messages.length : 0;
      return conversation.id !== "default-conversation" || messageCount > 1;
    });
  const source = hasRealConversations
    ? conversations
    : [conversationFromMessages(hasLegacyChat ? legacyChat : [])];

  return source.map((conversation) => {
    const timestamp = conversation.createdAt || new Date().toISOString();
    const messages = Array.isArray(conversation.messages) && conversation.messages.length
      ? conversation.messages
      : createWelcomeMessages(timestamp);

    return {
      id: conversation.id || makeId(),
      goalId: conversation.goalId || "",
      relatedMaterialIds: conversation.relatedMaterialIds || [],
      messages: messages.map(normalizeMessage),
      createdAt: timestamp,
      updatedAt: conversation.updatedAt || timestamp
    };
  });
}

function conversationFromMessages(messages) {
  const timestamp = new Date().toISOString();
  return {
    id: "default-conversation",
    goalId: "",
    relatedMaterialIds: collectRelatedMaterialIds(messages),
    messages: Array.isArray(messages) && messages.length ? messages : createWelcomeMessages(timestamp),
    createdAt: timestamp,
    updatedAt: timestamp
  };
}

function normalizeMessage(message) {
  const timestamp = message.createdAt || new Date().toISOString();
  return {
    id: message.id || makeId(),
    role: message.role === "agent" ? "assistant" : message.role,
    content: message.content || message.text || "",
    relatedMaterialIds: message.relatedMaterialIds || [],
    createdAt: timestamp
  };
}

function createWelcomeMessages(timestamp) {
  return [
    {
      id: "welcome-message",
      role: "assistant",
      content: "你好，我会根据你的目标和资料帮你学习。先创建一个成长目标，或添加一份资料。",
      createdAt: timestamp
    }
  ];
}

function collectRelatedMaterialIds(messages) {
  if (!Array.isArray(messages)) return [];
  return [...new Set(messages.flatMap((message) => message.relatedMaterialIds || []))];
}

function normalizeSummary(material) {
  const timestamp = material.createdAt || new Date().toISOString();
  const fallback = summarizeContent(material.content || "", {
    materialId: material.id,
    timestamp
  });
  const summary = material.summary || {};

  return {
    materialId: summary.materialId || material.id,
    overview: summary.overview || fallback.overview,
    keyPoints: normalizeArray(summary.keyPoints, fallback.keyPoints),
    difficulties: normalizeArray(summary.difficulties, fallback.difficulties),
    studyOrder: normalizeArray(summary.studyOrder, fallback.studyOrder),
    actionItems: normalizeArray(summary.actionItems, fallback.actionItems),
    aiMode: summary.aiMode || "mock",
    createdAt: summary.createdAt || timestamp,
    updatedAt: summary.updatedAt || material.updatedAt || timestamp
  };
}

function normalizeArray(value, fallback) {
  return Array.isArray(value) && value.length ? value : fallback;
}

function saveAndRender() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  render();
}

function switchView(name) {
  document.querySelectorAll(".nav-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.view === name);
  });
  document.querySelectorAll(".view").forEach((view) => {
    view.classList.toggle("active", view.id === `view-${name}`);
  });
  document.getElementById("page-title").textContent = views[name];
}

function render() {
  renderMetrics();
  renderToday();
  renderGoalFormMode();
  renderGoals();
  renderGoalDetail();
  renderMaterials();
  renderSummaries();
  renderChat();
  renderFlashcard();
  renderQuizzes();
  renderProgress();
}

function renderMetrics() {
  const total = state.progress.reduce((sum, item) => sum + item.totalTasks, 0);
  const completed = state.progress.reduce((sum, item) => sum + item.completedTasks, 0);
  const rate = total ? Math.round((completed / total) * 100) : 0;
  document.getElementById("metric-goals").textContent = state.goals.length;
  document.getElementById("metric-tasks").textContent = state.tasks.length;
  document.getElementById("metric-rate").textContent = `${rate}%`;
  document.getElementById("metric-cards").textContent = state.flashcards.length;
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

function renderMaterials() {
  const list = document.getElementById("material-list");
  list.innerHTML = "";

  if (state.materials.length === 0) {
    list.appendChild(emptyNode("暂无资料", "粘贴一段文本、PDF 摘录或网页链接。"));
    return;
  }

  state.materials.forEach((material) => {
    const item = document.createElement("article");
    item.className = "item";
    const summary = material.summary;
    const points = summary.keyPoints.map((point) => `<li>${escapeHtml(point)}</li>`).join("");
    const difficulties = summary.difficulties.map((point) => `<li>${escapeHtml(point)}</li>`).join("");
    item.innerHTML = `
      <div class="item-head">
        <div>
          <h3>${escapeHtml(material.title)}</h3>
          <p>${escapeHtml(summary.overview)}</p>
        </div>
        <button class="ghost-button" title="删除资料">×</button>
      </div>
      <div class="tag-row">
        <span class="tag">${escapeHtml(material.type)}</span>
        <span class="tag">${summary.keyPoints.length} 个知识点</span>
        <span class="tag">${summary.aiMode}</span>
      </div>
      <details class="material-detail">
        <summary>查看整理详情</summary>
        <strong>关键知识点</strong>
        <ul>${points}</ul>
        <strong>可能难点</strong>
        <ul>${difficulties}</ul>
      </details>
    `;
    item.querySelector("button").addEventListener("click", () => deleteMaterial(material.id));
    list.appendChild(item);
  });
}

function renderSummaries() {
  const list = document.getElementById("summary-list");
  list.innerHTML = "";

  if (state.materials.length === 0) {
    list.appendChild(emptyNode("等待资料", "资料整理结果会显示在这里。"));
    return;
  }

  state.materials.forEach((material) => {
    const item = document.createElement("article");
    item.className = "item";
    const summary = material.summary;
    const points = summary.keyPoints.map((point) => `<li>${escapeHtml(point)}</li>`).join("");
    const difficulties = summary.difficulties.map((point) => `<li>${escapeHtml(point)}</li>`).join("");
    const studyOrder = summary.studyOrder.map((point) => `<li>${escapeHtml(point)}</li>`).join("");
    const actionItems = summary.actionItems.map((point) => `<li>${escapeHtml(point)}</li>`).join("");
    item.innerHTML = `
      <h3>${escapeHtml(material.title)}</h3>
      <p>${escapeHtml(summary.overview)}</p>
      <h4>关键知识点</h4>
      <ul>${points}</ul>
      <h4>可能难点</h4>
      <ul>${difficulties}</ul>
      <h4>学习顺序</h4>
      <ul>${studyOrder}</ul>
      <h4>行动建议</h4>
      <ul>${actionItems}</ul>
    `;
    list.appendChild(item);
  });
}

function renderChat() {
  const log = document.getElementById("chat-log");
  log.innerHTML = "";
  getActiveConversation().messages.forEach((message) => {
    const node = document.createElement("div");
    node.className = `message ${message.role === "user" ? "user" : "agent"}`;
    node.textContent = message.content;

    if (message.role === "assistant" && message.relatedMaterialIds.length) {
      node.appendChild(referenceNode(message.relatedMaterialIds));
    }

    log.appendChild(node);
  });
  log.scrollTop = log.scrollHeight;
}

function renderFlashcard() {
  const card = document.getElementById("flashcard");
  const flashcard = state.flashcards[activeCardIndex];

  if (!flashcard) {
    card.innerHTML = "<span>暂无闪卡</span><strong>添加资料后会自动生成记忆卡片</strong>";
    return;
  }

  card.innerHTML = `
    <span>${escapeHtml(getMaterialTitle(flashcard.materialId))}</span>
    <strong>${escapeHtml(flashcard.front)}</strong>
    <p>${escapeHtml(flashcard.back)}</p>
  `;
}

function renderQuizzes() {
  const list = document.getElementById("quiz-list");
  list.innerHTML = "";

  if (state.quizzes.length === 0) {
    list.appendChild(emptyNode("暂无测试题", "添加资料后会自动生成简单测试题。"));
    return;
  }

  state.quizzes.slice(0, 8).forEach((quiz) => {
    const item = document.createElement("article");
    item.className = "item";
    item.innerHTML = `
      <h3>${escapeHtml(quiz.question)}</h3>
      <p>参考答案：${escapeHtml(quiz.answer)}</p>
      <p>解释：${escapeHtml(quiz.explanation)}</p>
      <div class="tag-row">
        <span class="tag">${escapeHtml(getMaterialTitle(quiz.materialId))}</span>
        <span class="tag">${escapeHtml(quiz.type)}</span>
      </div>
    `;
    list.appendChild(item);
  });
}

function renderProgress() {
  const list = document.getElementById("progress-list");
  list.innerHTML = "";

  if (state.progress.length === 0) {
    list.appendChild(emptyNode("暂无进度", "创建目标并完成任务后会生成进度。"));
    return;
  }

  [...state.progress]
    .sort((a, b) => b.completionRate - a.completionRate)
    .forEach((progress) => {
    const goal = state.goals.find((item) => item.id === progress.goalId);
    const remaining = goal ? getRemainingDays(goal.deadline) : "-";
    const row = document.createElement("div");
    row.className = "progress-row";
    row.innerHTML = `
      <div class="progress-meta">
        <strong>${escapeHtml(progress.goalName)}</strong>
        <span>${progress.completionRate}%</span>
      </div>
      <div class="bar"><span style="width:${progress.completionRate}%"></span></div>
      <p>${progress.completedTasks}/${progress.totalTasks} 个任务已完成，今日 ${progress.todayCompleted}/${progress.todayTotal}</p>
      <div class="tag-row">
        <span class="tag">剩余 ${remaining} 天</span>
      </div>
      <div class="inline-actions">
        <button class="ghost-button" data-goal-id="${escapeHtml(progress.goalId)}">查看详情</button>
      </div>
    `;
    row.querySelector("button").addEventListener("click", () => {
      selectGoal(progress.goalId);
      switchView("goals");
    });
    list.appendChild(row);
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

function summarizeContent(content, options = {}) {
  const sentences = splitSentences(content);
  const keyPoints = sentences.slice(0, 6).map((text) => text.slice(0, 60));
  const points = keyPoints.length ? keyPoints : ["提炼资料中的核心概念", "复习关键定义和例子"];
  const timestamp = options.timestamp || new Date().toISOString();

  return {
    materialId: options.materialId || "",
    overview: sentences.slice(0, 2).join("。").slice(0, 140) || "这份资料已保存，可用于成长问答和记忆训练。",
    keyPoints: points,
    difficulties: points.slice(0, 3).map((point) => `容易卡住：${point}。先用自己的话复述，再回到原文核对。`),
    studyOrder: [
      "先快速通读资料，标出不熟悉的词句。",
      `再重点理解：${points[0]}。`,
      "最后用闪卡和测试题检查是否能独立复述。"
    ],
    actionItems: [
      "用 3 句话写下资料摘要。",
      "完成 1 轮闪卡复习。",
      "任选 1 个知识点做简答自测。"
    ],
    aiMode: "mock",
    createdAt: timestamp,
    updatedAt: timestamp
  };
}

function createMemoryItems(material) {
  const timestamp = new Date().toISOString();
  material.summary.keyPoints.forEach((point) => {
    state.flashcards.push({
      id: makeId(),
      materialId: material.id,
      front: `请解释：${point}`,
      back: `围绕“${point}”进行复述，并补充一个例子。`,
      status: "new",
      createdAt: timestamp,
      updatedAt: timestamp
    });
    state.quizzes.push({
      id: makeId(),
      materialId: material.id,
      type: "short",
      options: [],
      question: `简答：${point} 的核心含义是什么？`,
      answer: "先说明定义，再结合资料中的例子解释。",
      explanation: `这道题对应资料《${material.title}》中的知识点“${point}”。`,
      createdAt: timestamp,
      updatedAt: timestamp
    });
  });
}

function answerQuestion(question) {
  const relevant = findRelevantMaterials(question);

  if (relevant.length) {
    const material = relevant[0];
    const points = material.summary.keyPoints.slice(0, 3).join("；");
    return {
      text: `我先参考《${material.title}》来回答。它的核心线索是：${points}。建议你先复述摘要，再挑一个知识点举例，最后用测试题检查是否真正理解。`,
      relatedMaterialIds: relevant.map((item) => item.id)
    };
  }

  return {
    text: "现在还没有可参考的资料。你可以先添加一份成长资料，我再基于资料帮你解释和出题。",
    relatedMaterialIds: []
  };
}

function findRelevantMaterials(question) {
  const query = question.toLowerCase();
  const scored = state.materials
    .map((material) => {
      const summary = material.summary;
      const haystack = [
        material.title,
        summary.overview,
        ...summary.keyPoints,
        ...summary.difficulties
      ]
        .join(" ")
        .toLowerCase();
      const score = splitSentences(question).reduce((total, part) => {
        return haystack.includes(part.toLowerCase()) ? total + 1 : total;
      }, haystack.includes(query.slice(0, 6)) ? 1 : 0);
      return { material, score };
    })
    .filter((item) => item.score > 0)
    .sort((a, b) => b.score - a.score)
    .map((item) => item.material);

  return scored.length ? scored.slice(0, 2) : state.materials.slice(0, 1);
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

function deleteMaterial(id) {
  if (!window.confirm("确认删除这份资料吗？")) return;
  state.materials = state.materials.filter((item) => item.id !== id);
  state.flashcards = state.flashcards.filter((card) => card.materialId !== id);
  state.quizzes = state.quizzes.filter((quiz) => quiz.materialId !== id);
  state.aiConversations = state.aiConversations.map((conversation) => ({
    ...conversation,
    relatedMaterialIds: conversation.relatedMaterialIds.filter((materialId) => materialId !== id),
    messages: conversation.messages.map((message) => ({
      ...message,
      relatedMaterialIds: (message.relatedMaterialIds || []).filter((materialId) => materialId !== id)
    })),
    updatedAt: new Date().toISOString()
  }));
  state.chat = getActiveConversation().messages;
  activeCardIndex = 0;
  saveAndRender();
}

function rateCard(status) {
  const card = state.flashcards[activeCardIndex];
  if (!card) return;
  card.status = status;
  card.updatedAt = new Date().toISOString();
  activeCardIndex = state.flashcards.length ? (activeCardIndex + 1) % state.flashcards.length : 0;
  saveAndRender();
}

function getMaterialTitle(materialId) {
  const material = state.materials.find((item) => item.id === materialId);
  return material ? material.title : "未关联资料";
}

function getActiveConversation() {
  const conversation = state.aiConversations.find((item) => item.id === state.activeConversationId);
  return conversation || state.aiConversations[0];
}

function getConversationMessages(sourceState, conversationId) {
  const conversation = sourceState.aiConversations.find((item) => item.id === conversationId);
  return conversation ? conversation.messages : [];
}

function mergeUniqueIds(currentIds, nextIds) {
  return [...new Set([...(currentIds || []), ...(nextIds || [])])];
}

function referenceNode(materialIds) {
  const wrapper = document.createElement("div");
  wrapper.className = "message-references";
  const label = document.createElement("span");
  label.textContent = "参考资料";
  wrapper.appendChild(label);

  materialIds.forEach((materialId) => {
    const material = state.materials.find((item) => item.id === materialId);
    if (!material) return;
    const tag = document.createElement("strong");
    tag.textContent = material.title;
    wrapper.appendChild(tag);
  });

  return wrapper;
}

function emptyNode(title, body) {
  const template = document.getElementById("empty-template");
  const node = template.content.firstElementChild.cloneNode(true);
  node.querySelector("strong").textContent = title;
  node.querySelector("p").textContent = body;
  return node;
}

function splitSentences(text) {
  return text
    .replace(/\s+/g, " ")
    .split(/[。！？!?；;\n]/)
    .map((item) => item.trim())
    .filter((item) => item.length > 2);
}

function daysUntil(dateString) {
  const end = new Date(dateString);
  const today = new Date();
  const diff = end.getTime() - today.getTime();
  return Math.ceil(diff / 86400000);
}

function offsetDate(days) {
  const date = new Date();
  date.setDate(date.getDate() + days);
  return date.toISOString().slice(0, 10);
}

function todayString() {
  const date = new Date();
  date.setMinutes(date.getMinutes() - date.getTimezoneOffset());
  return date.toISOString().slice(0, 10);
}

function getRemainingDays(dateString) {
  if (!dateString) return "-";
  return Math.max(0, daysUntil(dateString));
}

function formatDateTime(value) {
  if (!value) return "";
  return new Date(value).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  });
}

function makeId() {
  return crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
