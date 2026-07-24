const STORAGE_KEY = "student-assistant-mvp";
const SESSION_HINT_STORAGE_KEY = "ai-agent-session-hint";
const SIDEBAR_STORAGE_KEY = "student-assistant-sidebar-collapsed";
const defaultState = {
  goals: [],
  materials: [],
  tasks: [],
  progress: [],
  dashboard: null,
  loadedViews: {
    goals: false,
    materials: false,
    agent: false
  },
  materialChunks: {},
  materialQaRecords: {},
  agentContext: null,
  agentDecision: null,
  agentActionLogs: [],
  agentRuns: [],
  selectedAgentRunId: "",
  selectedAgentRun: null,
  qaReviewDrafts: [],
  agentTaskDrafts: [],
  chunkSearch: {
    query: "",
    results: []
  },
  selectedGoal: null,
  selectedGoalId: "",
  selectedGoalTasks: [],
  selectedGoalProgress: null,
  flashcards: [],
  quizzes: [],
  quizAttempts: {},
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

var currentUser = null;
var state = loadState();
var activeCardIndex = 0;
var editingGoalId = "";
var editingMaterialId = "";
var selectedGoalId = state.selectedGoalId || "";
var activeGoalScopeId = "";
var selectedTaskDate = todayString();
var pendingChatMaterialId = "";
var initialDataLoadPromise = null;
var todayActionsState = { status: "idle", data: null, error: null };

const views = {
  today: "今日行动",
  goals: "学习目标",
  materials: "成长资料",
  study: "成长问答",
  agent: "智能学习助手",
  memory: "记忆训练",
  progress: "成长进度"
};

document.getElementById("show-login").addEventListener("click", () => switchAuthMode("login"));
document.getElementById("show-register").addEventListener("click", () => switchAuthMode("register"));
document.querySelector(".auth-tabs").addEventListener("keydown", (event) => {
  if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
  event.preventDefault();
  const mode = event.key === 'ArrowLeft' ? 'login' : 'register';
  switchAuthMode(mode);
  document.getElementById(mode === 'login' ? 'show-login' : 'show-register').focus();
});
document.getElementById("demo-login").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  setButtonLoading(button, true, "正在准备演示");

  try {
    const user = await authApi.demo();
    markSessionHint();
    await enterApp(user);
    showSuccess("已进入独立演示环境");
  } catch (error) {
    showError(error);
  } finally {
    setButtonLoading(button, false);
  }
});

document.getElementById("login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const submitButton = document.getElementById("login-submit");
  const data = new FormData(form);

  setButtonLoading(submitButton, true, "登录中");

  try {
    const user = await authApi.login({
      email: data.get("email").trim(),
      password: data.get("password")
    });
    markSessionHint();
    await enterApp(user);
    form.reset();
    showSuccess("登录成功");
  } catch (error) {
    showError(error);
  } finally {
    setButtonLoading(submitButton, false);
  }
});

document.getElementById("register-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const submitButton = document.getElementById("register-submit");
  const data = new FormData(form);
  const password = data.get("password");
  const confirmPassword = data.get("confirmPassword");

  if (password !== confirmPassword) {
    showError(new Error("两次输入的密码不一致"));
    return;
  }

  setButtonLoading(submitButton, true, "创建中");

  try {
    const user = await authApi.register({
      name: data.get("name").trim(),
      email: data.get("email").trim(),
      password
    });
    markSessionHint();
    await enterApp(user);
    form.reset();
    showSuccess("注册成功");
  } catch (error) {
    showError(error);
  } finally {
    setButtonLoading(submitButton, false);
  }
});

document.getElementById("logout-button").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  setButtonLoading(button, true, "退出中");

  try {
    await authApi.logout();
    clearAuthenticatedState();
    renderAuth();
    showSuccess("已退出登录");
  } catch (error) {
    showError(error);
  } finally {
    setButtonLoading(button, false);
  }
});

document.getElementById("sidebar-toggle").addEventListener("click", () => {
  const shell = document.getElementById("app-shell");
  const collapsed = !shell.classList.contains("sidebar-collapsed");
  shell.classList.toggle("sidebar-collapsed", collapsed);
  localStorage.setItem(SIDEBAR_STORAGE_KEY, collapsed ? "1" : "0");
  updateSidebarToggleLabel();
});

document.querySelectorAll(".nav-item[data-view]").forEach((button) => {
  button.addEventListener("click", async () => {
    clearGoalViewScope();
    const switched = await switchView(button.dataset.view);
    if (switched && button.closest("#mobile-more-menu")) {
      document.getElementById("mobile-more-toggle").focus();
    }
  });
});

document.querySelectorAll("[data-clear-goal-scope]").forEach((button) => {
  button.addEventListener("click", () => {
    clearGoalViewScope();
    render();
  });
});

document.getElementById("agent-refresh-button")?.addEventListener("click", async (event) => {
  await refreshAgentContext(event.currentTarget);
});

document.querySelectorAll("[data-agent-preset]").forEach((button) => {
  button.addEventListener("click", () => {
    const input = document.getElementById("agent-run-objective");
    if (!input) return;
    input.value = button.dataset.agentPreset || "";
    document.querySelectorAll("[data-agent-preset]").forEach((item) => {
      item.classList.toggle("active", item === button);
    });
    input.focus();
  });
});

document.getElementById("agent-run-start").addEventListener("click", async (event) => {
  await startAgentRun(event.currentTarget);
});

document.getElementById("agent-goal-select").addEventListener("change", async (event) => {
  await selectAgentGoal(event.currentTarget.value, event.currentTarget);
});

document.getElementById("agent-open-progress").addEventListener("click", () => switchView("progress"));
document.getElementById("agent-open-goals").addEventListener("click", () => switchView("goals"));
document.getElementById("agent-open-materials").addEventListener("click", () => switchView("materials"));
document.getElementById("agent-open-memory").addEventListener("click", () => switchView("memory"));
document.getElementById("agent-open-quiz").addEventListener("click", () => switchView("memory"));
document.getElementById("agent-open-study").addEventListener("click", () => switchView("study"));

document.querySelectorAll("[data-agent-sample]").forEach((button) => {
  button.addEventListener("click", () => prefillAgentSampleQuestion(button.dataset.agentSample));
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
      setSelectedGoalId(editingGoalId);
      editingGoalId = "";
      showSuccess("目标已更新");
    } else {
      const goal = await goalApi.createGoal(payload);

      setSelectedGoalId(goal.id);
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
  await refreshTodayData("任务日期已切换");
});

document.getElementById("reset-today-date").addEventListener("click", async () => {
  selectedTaskDate = todayString();
  document.getElementById("today-date-filter").value = selectedTaskDate;
  await refreshTodayData("已回到今天");
});

document.getElementById("material-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const submitButton = document.getElementById("material-submit-button");
  const data = new FormData(event.currentTarget);
  const content = String(data.get("content") || "").trim();
  const type = data.get("type");

  setButtonLoading(submitButton, true, type === "upload" ? "处理中" : "保存中");

  try {
    let material;
    if (type === "upload") {
      const file = data.get("file");
      if (!(file instanceof File) || file.size === 0) {
        throw new Error("请选择 PDF、Markdown 或 TXT 文件");
      }
      const uploadData = new FormData();
      uploadData.set("goalId", selectedGoalId || "");
      uploadData.set("title", String(data.get("title") || "").trim());
      uploadData.set("file", file);
      material = await materialApi.uploadMaterial(uploadData);
    } else {
      const payload = {
        goalId: selectedGoalId || "",
        title: String(data.get("title") || "").trim(),
        type,
        content: type === "text" ? content : "",
        url: type === "link" ? content : ""
      };
      material = editingMaterialId
        ? await materialApi.updateMaterial(editingMaterialId, payload)
        : await materialApi.createMaterial(payload);

      if (type !== "link") {
        await materialApi.summarizeMaterial(material.id);
        await materialApi.generateFlashcards(material.id);
        await materialApi.generateQuiz(material.id);
      }
    }
    editingMaterialId = "";
    await loadMaterialDataFromApi();
    await loadDashboardDataFromApi();
    await loadAgentContextFromApi();
    render();
    form.reset();
    updateMaterialInputMode();
    if (type === "upload") {
      const failedStage = Object.entries(material.processingStatus || {}).find(([, state]) => state.status === "failed");
      showSuccess(failedStage ? `资料已保存，${failedStage[0]} 阶段可单独重试` : "文件已处理，已生成可检索资料");
    } else if (type === "link") {
      showSuccess("链接已保存，不解析网页正文");
    } else {
      showSuccess("资料已保存，并完成摘要、闪卡和测试题");
    }
  } catch (error) {
    showError(error);
  } finally {
    setButtonLoading(submitButton, false);
  }
});

document.getElementById("cancel-material-edit").addEventListener("click", () => {
  cancelMaterialEdit();
});

document.getElementById("chat-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const data = new FormData(event.currentTarget);
  const question = data.get("question").trim();
  const submitButton = form.querySelector("button[type='submit']");
  if (!question) return;

  const timestamp = new Date().toISOString();
  const conversation = getActiveConversation();
  conversation.messages.push({
    id: makeId(),
    role: "user",
    content: question,
    relatedMaterialIds: pendingChatMaterialId ? [pendingChatMaterialId] : [],
    createdAt: timestamp
  });
  saveAndRender();
  setButtonLoading(submitButton, true, "发送中");

  try {
    const answer = await agentApi.ask({
      question,
      goalId: selectedGoalId || undefined,
      materialId: pendingChatMaterialId || undefined,
      limit: 3
    });
    const relatedMaterialIds = collectReferenceMaterialIds(answer.references);
    conversation.messages.push({
      id: makeId(),
      role: "assistant",
      content: answer.answer,
      materialId: answer.materialId || "",
      qaRecordId: answer.id || "",
      basis: answer.basis,
      suggestion: answer.suggestion,
      references: answer.references || [],
      relatedMaterialIds,
      isFromMaterial: answer.isFromMaterial,
      confidence: answer.confidence,
      mode: answer.mode,
      nextAction: answer.nextAction,
      requiresConfirmation: answer.requiresConfirmation,
      insufficiencyReason: answer.insufficiencyReason,
      reviewDrafts: answer.reviewDrafts || [],
      createdAt: new Date().toISOString()
    });
    conversation.relatedMaterialIds = mergeUniqueIds(conversation.relatedMaterialIds, relatedMaterialIds);
    conversation.updatedAt = new Date().toISOString();
    syncMaterialQaRecordFromAgentAnswer(answer, question);
    await loadAgentContextFromApi();
    pendingChatMaterialId = "";
    saveAndRender();
    focusMaterialQaRecord(answer.id);
    form.reset();
  } catch (error) {
    showError(error);
  } finally {
    setButtonLoading(submitButton, false);
  }
});

document.getElementById("chunk-search-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const data = new FormData(form);
  const query = data.get("query").trim();
  const submitButton = document.getElementById("chunk-search-button");

  if (!query) return;

  setButtonLoading(submitButton, true, "搜索中");

  try {
    const results = await materialApi.searchChunks(query, 5);
    state.chunkSearch = { query, results };
    renderSummaries();
    showSuccess(results.length ? "已找到相关片段" : "没有命中相关片段");
  } catch (error) {
    showError(error);
  } finally {
    setButtonLoading(submitButton, false);
  }
});

document.getElementById("quick-plan").addEventListener("click", async (event) => {
  await generatePlansForAllGoals(getPlanDays("quick-plan-days"), event.currentTarget);
});

document.getElementById("generate-all-plans").addEventListener("click", async (event) => {
  await generatePlansForAllGoals(getPlanDays("goal-plan-days"), event.currentTarget);
});

document.getElementById("shuffle-cards").addEventListener("click", () => {
  const flashcards = getScopedFlashcards();
  if (flashcards.length === 0) return;
  activeCardIndex = (activeCardIndex + 1) % flashcards.length;
  renderFlashcard();
});

document.getElementById("card-known").addEventListener("click", () => rateCard("known"));
document.getElementById("card-review").addEventListener("click", () => rateCard("review"));

document.getElementById("export-data").addEventListener("click", () => void exportAccountData());
document.getElementById("mobile-export-data").addEventListener("click", () => void exportAccountData());
document.getElementById("reset-data").addEventListener("click", () => void deleteAccountData());
document.getElementById("mobile-reset-data").addEventListener("click", () => void deleteAccountData());

document.getElementById("mobile-more-toggle").addEventListener("click", () => {
  const menu = document.getElementById("mobile-more-menu");
  const toggle = document.getElementById("mobile-more-toggle");
  const open = menu.hidden;
  menu.hidden = !open;
  toggle.setAttribute("aria-expanded", String(open));
});

document.getElementById("mobile-more-menu").addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  const menu = document.getElementById("mobile-more-menu");
  const toggle = document.getElementById("mobile-more-toggle");
  menu.hidden = true;
  toggle.setAttribute("aria-expanded", "false");
  toggle.focus();
});

document.getElementById("material-form").elements.type.addEventListener("change", updateMaterialInputMode);
updateMaterialInputMode();

function updateMaterialInputMode() {
  const form = document.getElementById("material-form");
  const type = form.elements.type.value;
  const contentField = document.getElementById("material-content-field");
  const fileField = document.getElementById("material-file-field");
  const linkNote = document.getElementById("material-link-note");
  const content = form.elements.content;
  const file = form.elements.file;
  const isUpload = type === "upload";

  contentField.hidden = isUpload;
  fileField.hidden = !isUpload;
  linkNote.hidden = type !== "link";
  content.required = !isUpload;
  file.required = isUpload;
  if (type === "link") {
    content.placeholder = "粘贴网页链接；本版本只保存链接";
  } else if (type === "text") {
    content.placeholder = "粘贴资料正文";
  }
}

document.querySelectorAll("[data-onboarding-view]").forEach((button) => {
  button.addEventListener("click", () => {
    void switchView(button.dataset.onboardingView);
  });
});

init();

async function init() {
  removeLegacyAuthState();
  document.getElementById("today-date-filter").value = selectedTaskDate;
  applySidebarState();
  renderAuth();
  if (!hasSessionHint()) {
    return;
  }

  try {
    const user = await authApi.me();
    await enterApp(user, { restoreLocalState: true });
  } catch (error) {
    if (error && error.status === 401) {
      clearAuthenticatedState();
      renderAuth();
      return;
    }
    showError(error);
  }
}

function applySidebarState() {
  const collapsed = localStorage.getItem(SIDEBAR_STORAGE_KEY) === "1";
  document.getElementById("app-shell").classList.toggle("sidebar-collapsed", collapsed);
  updateSidebarToggleLabel();
}

function updateSidebarToggleLabel() {
  const shell = document.getElementById("app-shell");
  const button = document.getElementById("sidebar-toggle");
  const collapsed = shell.classList.contains("sidebar-collapsed");
  button.textContent = collapsed ? "›" : "‹";
  button.title = collapsed ? "展开侧边栏" : "折叠侧边栏";
}

async function enterApp(user, { restoreLocalState = false } = {}) {
  currentUser = user;
  if (restoreLocalState) {
    state = loadState();
    // Persist the user's selected goal, but always revalidate server-backed view data.
    state.loadedViews = {
      goals: false,
      materials: false,
      agent: false
    };
  } else {
    resetLocalAppState();
  }
  selectedGoalId = state.selectedGoalId || "";
  activeGoalScopeId = "";
  activeCardIndex = 0;
  setActiveView("today");
  renderAuth();
  const dataLoad = loadAppDataFromApi();
  initialDataLoadPromise = dataLoad;
  try {
    await dataLoad;
  } finally {
    if (initialDataLoadPromise === dataLoad) initialDataLoadPromise = null;
  }
  render();
  void loadTodayActionsFromApi();
}

async function loadAppDataFromApi() {
  await loadDashboardDataFromApi();
}

async function loadDashboardDataFromApi() {
  const dashboard = await dashboardApi.getDashboard(selectedTaskDate);
  state.dashboard = dashboard;
  state.tasks = (dashboard.todayTasks || []).map(taskFromApi);
  saveState();
}

async function loadTodayActionsFromApi() {
  todayActionsState = { status: "loading", data: null, error: null };
  render();
  try {
    const data = await todayApi.getActions(15);
    todayActionsState = { status: "ready", data, error: null };
    return data;
  } catch (error) {
    todayActionsState = { status: "error", data: null, error };
    return null;
  } finally {
    render();
  }
}

function renderAuth() {
  const isLoggedIn = Boolean(currentUser);
  document.getElementById("auth-shell").hidden = isLoggedIn;
  document.getElementById("app-shell").hidden = !isLoggedIn;
  document.querySelector(".mobile-bottom-nav").hidden = !isLoggedIn;
  if (!isLoggedIn) {
    document.getElementById("mobile-more-menu").hidden = true;
    document.getElementById("mobile-more-toggle").setAttribute("aria-expanded", "false");
  }
  const currentUserElement = document.getElementById("current-user");
  if (currentUserElement) {
    currentUserElement.textContent = isLoggedIn ? currentUser.name || currentUser.email : "";
    currentUserElement.title = isLoggedIn ? currentUser.email : "";
  }
}

function switchAuthMode(mode) {
  const isLogin = mode === "login";
  const loginTab = document.getElementById("show-login");
  const registerTab = document.getElementById("show-register");
  const loginForm = document.getElementById("login-form");
  const registerForm = document.getElementById("register-form");

  loginTab.classList.toggle("active", isLogin);
  loginTab.setAttribute("aria-selected", String(isLogin));
  loginTab.tabIndex = isLogin ? 0 : -1;
  registerTab.classList.toggle("active", !isLogin);
  registerTab.setAttribute("aria-selected", String(!isLogin));
  registerTab.tabIndex = isLogin ? -1 : 0;

  loginForm.classList.toggle("active", isLogin);
  loginForm.hidden = !isLogin;
  registerForm.classList.toggle("active", !isLogin);
  registerForm.hidden = isLogin;

  document.getElementById("auth-panel-title").textContent = isLogin
    ? "继续你的学习闭环"
    : "建立你的学习档案";
  document.getElementById("auth-panel-subtitle").textContent = isLogin
    ? "登录后读取目标、资料和复习进度"
    : "创建账号后，从第一条学习目标开始";
}

function clearAuthenticatedState() {
  currentUser = null;
  localStorage.removeItem(SESSION_HINT_STORAGE_KEY);
  resetLocalAppState();
}

async function exportAccountData() {
  try {
    const exported = await authApi.exportData();
    const blob = new Blob([JSON.stringify(exported, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "ai-agent-account-data.json";
    link.click();
    URL.revokeObjectURL(url);
    showSuccess("账号数据已从服务端导出");
  } catch (error) {
    showError(error);
  }
}

async function deleteAccountData() {
  const confirmed = window.confirm("删除账号会永久删除目标、资料、问答、任务和运行记录。确认继续吗？");
  if (!confirmed) return;

  try {
    await authApi.deleteAccount();
    clearAuthenticatedState();
    renderAuth();
    showSuccess("账号与服务端数据已删除");
  } catch (error) {
    showError(error);
  }
}

function markSessionHint() {
  localStorage.setItem(SESSION_HINT_STORAGE_KEY, "1");
}

function hasSessionHint() {
  return localStorage.getItem(SESSION_HINT_STORAGE_KEY) === "1";
}

function handleUnauthorizedSession() {
  if (!currentUser) return false;
  clearAuthenticatedState();
  renderAuth();
  return true;
}

function resetLocalAppState() {
  localStorage.removeItem(STORAGE_KEY);
  state = normalizeState(structuredClone(defaultState));
  selectedGoalId = "";
  activeGoalScopeId = "";
  activeCardIndex = 0;
  editingGoalId = "";
  editingMaterialId = "";
  pendingChatMaterialId = "";
  todayActionsState = { status: "idle", data: null, error: null };
}

function removeLegacyAuthState() {
  localStorage.removeItem("student-assistant-auth");
  for (let index = localStorage.length - 1; index >= 0; index -= 1) {
    const key = localStorage.key(index);
    if (key && key.startsWith(`${STORAGE_KEY}:`)) {
      localStorage.removeItem(key);
    }
  }
}

function loadState() {
  const raw = localStorage.getItem(getStateStorageKey());
  if (!raw) return normalizeState(structuredClone(defaultState));

  try {
    const normalized = normalizeState({ ...structuredClone(defaultState), ...JSON.parse(raw) });
    localStorage.setItem(getStateStorageKey(), JSON.stringify(normalized));
    return normalized;
  } catch {
    return normalizeState(structuredClone(defaultState));
  }
}

function getStateStorageKey() {
  return STORAGE_KEY;
}

function saveState() {
  localStorage.setItem(getStateStorageKey(), JSON.stringify(state));
}

async function loadMaterialDataFromApi() {
  const materials = await materialApi.listMaterials();
  const materialDetails = await Promise.all(
    materials.map(async (material) => {
      const [summary, flashcards, quizzes, chunks, qaRecords, quizAttempts] = await Promise.all([
        materialApi.getSummary(material.id),
        materialApi.listFlashcards(material.id),
        materialApi.listQuiz(material.id),
        materialApi.listChunks(material.id),
        materialApi.listQaRecords(material.id),
        materialApi.listQuizAttempts(material.id)
      ]);

      const normalizedMaterial = {
        ...material,
        summary: summary || undefined
      };
      normalizedMaterial.summary = normalizeSummary(normalizedMaterial);

      return {
        material: normalizedMaterial,
        flashcards,
        quizzes,
        chunks,
        qaRecords,
        quizAttempts
      };
    })
  );

  state.materials = materialDetails.map((item) => item.material).reverse();
  state.flashcards = materialDetails.flatMap((item) => item.flashcards);
  state.quizzes = materialDetails.flatMap((item) => item.quizzes);
  state.materialChunks = materialDetails.reduce((chunksByMaterial, item) => {
    chunksByMaterial[item.material.id] = item.chunks;
    return chunksByMaterial;
  }, {});
  state.materialQaRecords = materialDetails.reduce((recordsByMaterial, item) => {
    recordsByMaterial[item.material.id] = item.qaRecords;
    return recordsByMaterial;
  }, {});
  state.quizAttempts = materialDetails.reduce((attemptsByMaterial, item) => {
    attemptsByMaterial[item.material.id] = item.quizAttempts;
    return attemptsByMaterial;
  }, {});
  if (activeCardIndex >= state.flashcards.length) {
    activeCardIndex = 0;
  }
  state.loadedViews.materials = true;
  saveState();
}

function normalizeState(nextState) {
  const materialsByTitle = new Map();
  nextState.materialChunks = nextState.materialChunks || {};
  nextState.dashboard = nextState.dashboard || null;
  nextState.loadedViews = {
    goals: false,
    materials: false,
    agent: false,
    ...(nextState.loadedViews || {})
  };
  nextState.materialQaRecords = nextState.materialQaRecords || {};
  nextState.agentContext = nextState.agentContext || null;
  nextState.agentDecision = nextState.agentDecision || null;
  nextState.agentActionLogs = nextState.agentActionLogs || [];
  nextState.agentRuns = nextState.agentRuns || [];
  nextState.selectedAgentRunId = nextState.selectedAgentRunId || "";
  nextState.selectedAgentRun = nextState.selectedAgentRun || null;
  nextState.quizAttempts = nextState.quizAttempts || {};
  nextState.selectedGoalId = nextState.selectedGoalId || "";
  nextState.qaReviewDrafts = nextState.qaReviewDrafts || [];
  nextState.agentTaskDrafts = nextState.agentTaskDrafts || [];
  nextState.chunkSearch = nextState.chunkSearch || { query: "", results: [] };

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

  nextState.qaReviewDrafts = nextState.qaReviewDrafts.map((draft) => {
    const timestamp = draft.createdAt || new Date().toISOString();
    return {
      id: draft.id || makeId(),
      type: draft.type || "review-point",
      materialId: draft.materialId || "",
      qaRecordId: draft.qaRecordId || "",
      question: draft.question || "",
      front: draft.front || "",
      back: draft.back || "",
      point: draft.point || "",
      createdAt: timestamp
    };
  });

  nextState.agentTaskDrafts = nextState.agentTaskDrafts.map((draft) => {
    const timestamp = draft.createdAt || new Date().toISOString();
    return {
      id: draft.id || makeId(),
      goalId: draft.goalId || "",
      actionType: draft.actionType || "create_followup_tasks",
      agentActionLogId: draft.agentActionLogId || "",
      title: draft.title || "",
      reason: draft.reason || "",
      suggestedDays: Number(draft.suggestedDays || 3),
      tasks: Array.isArray(draft.tasks) ? draft.tasks : [],
      source: draft.source || "agent",
      createdAt: timestamp
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

function saveAndRender() {
  saveState();
  render();
}

async function switchView(name) {
  if (!views[name]) return false;
  if (initialDataLoadPromise) await initialDataLoadPromise;
  setActiveView(name);
  try {
    await ensureViewData(name);
    render();
    return true;
  } catch (error) {
    showError(error);
    return false;
  }
}

function setActiveView(name) {
  document.querySelectorAll(".nav-item[data-view]").forEach((item) => {
    const active = item.dataset.view === name;
    item.classList.toggle("active", active);
    if (active) item.setAttribute("aria-current", "page");
    else item.removeAttribute("aria-current");
  });
  document.querySelectorAll(".view").forEach((view) => {
    view.classList.toggle("active", view.id === `view-${name}`);
  });
  document.getElementById("page-title").textContent = views[name];
  const moreMenu = document.getElementById("mobile-more-menu");
  const moreToggle = document.getElementById("mobile-more-toggle");
  const isMoreView = ["study", "memory", "progress"].includes(name);
  moreMenu.hidden = true;
  moreToggle.setAttribute("aria-expanded", "false");
  moreToggle.classList.toggle("active", isMoreView);
  moreToggle.setAttribute("aria-label", isMoreView ? `更多导航，当前：${views[name]}` : "更多导航");
}

async function ensureViewData(name) {
  if (name === "today" && currentUser && todayActionsState.status !== "loading") {
    void loadTodayActionsFromApi();
  }
  if (["goals", "progress", "agent"].includes(name) && !state.loadedViews.goals) {
    await loadGoalDataFromApi();
  }
  if (["materials", "study", "memory", "progress"].includes(name) && !state.loadedViews.materials) {
    await loadMaterialDataFromApi();
  }
  if (name === "agent" && !state.loadedViews.agent) {
    await loadAgentRuntimeData(selectedGoalId || "");
    state.loadedViews.agent = true;
    saveState();
  }
}

function render() {
  renderMetrics();
  renderToday();
  renderGoalFormMode();
  renderMaterialFormMode();
  renderGoals();
  renderGoalDetail();
  renderMaterials();
  renderSummaries();
  renderChat();
  renderAgentWorkbench();
  renderAgentSampleState();
  renderFlashcard();
  renderReviewDrafts();
  renderQuizzes();
  renderProgress();
  renderGoalScopeBars();
}

function getCurrentGoalScope() {
  return state.goals.find((goal) => goal.id === activeGoalScopeId)
    || (state.selectedGoal?.id === activeGoalScopeId ? state.selectedGoal : null)
    || null;
}

function setGoalViewScope(goalId) {
  activeGoalScopeId = goalId || "";
  activeCardIndex = 0;
}

function clearGoalViewScope() {
  setGoalViewScope("");
}

function getScopedItems(items, goalIdForItem) {
  const list = Array.isArray(items) ? items : [];
  if (!activeGoalScopeId) return list;
  return list.filter((item) => goalIdForItem(item) === activeGoalScopeId);
}

function getScopedGoals() {
  return getScopedItems(state.goals, (goal) => goal.id);
}

function getScopedProgress() {
  return getScopedItems(state.progress, (progress) => progress.goalId);
}

function getScopedMaterials() {
  return getScopedItems(state.materials, (material) => material.goalId);
}

function getScopedFlashcards() {
  const materialGoalIds = new Map(state.materials.map((material) => [material.id, material.goalId]));
  return getScopedItems(state.flashcards, (flashcard) => materialGoalIds.get(flashcard.materialId));
}

function getScopedQuizzes() {
  const materialGoalIds = new Map(state.materials.map((material) => [material.id, material.goalId]));
  return getScopedItems(state.quizzes, (quiz) => materialGoalIds.get(quiz.materialId));
}

function getScopedQuizAttempts() {
  const materialIds = new Set(getScopedMaterials().map((material) => material.id));
  if (!activeGoalScopeId) return state.quizAttempts || {};
  return Object.fromEntries(
    Object.entries(state.quizAttempts || {}).filter(([materialId]) => materialIds.has(materialId))
  );
}

function renderGoalScopeBars() {
  const goal = getCurrentGoalScope();
  const label = goal ? `当前目标：${goal.name}` : "";
  ["materials-scope-note", "study-scope-note", "memory-scope-note", "progress-scope-note"].forEach((id) => {
    const bar = document.getElementById(id);
    if (!bar) return;
    bar.hidden = !label;
    const text = bar.querySelector("span");
    if (text) text.textContent = label;
  });
}
