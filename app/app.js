const STORAGE_KEY = "student-assistant-mvp";
const defaultState = {
  goals: [],
  materials: [],
  tasks: [],
  progress: [],
  materialChunks: {},
  materialQaRecords: {},
  chunkSearch: {
    query: "",
    results: []
  },
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

var state = loadState();
var activeCardIndex = 0;
var editingGoalId = "";
var editingMaterialId = "";
var selectedGoalId = "";
var selectedTaskDate = todayString();

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

document.getElementById("material-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const submitButton = document.getElementById("material-submit-button");
  const data = new FormData(event.currentTarget);
  const content = data.get("content").trim();
  const type = data.get("type");
  const payload = {
    goalId: selectedGoalId || "",
    title: data.get("title").trim(),
    type,
    content: type === "text" ? content : "",
    url: type === "link" ? content : ""
  };

  setButtonLoading(submitButton, true, "保存中");

  try {
    const material = editingMaterialId
      ? await materialApi.updateMaterial(editingMaterialId, payload)
      : await materialApi.createMaterial(payload);

    await materialApi.summarizeMaterial(material.id);
    await materialApi.generateFlashcards(material.id);
    await materialApi.generateQuiz(material.id);
    editingMaterialId = "";
    await loadMaterialDataFromApi();
    render();
    form.reset();
    showSuccess("资料已保存，并完成摘要、闪卡和测试题");
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
    createdAt: timestamp
  });
  saveAndRender();
  setButtonLoading(submitButton, true, "发送中");

  try {
    const answer = await agentApi.ask({
      question,
      goalId: selectedGoalId || undefined,
      materialId: getActiveMaterialIdForQuestion(),
      limit: 3
    });
    const relatedMaterialIds = collectReferenceMaterialIds(answer.references);
    conversation.messages.push({
      id: makeId(),
      role: "assistant",
      content: answer.answer,
      basis: answer.basis,
      suggestion: answer.suggestion,
      references: answer.references || [],
      relatedMaterialIds,
      isFromMaterial: answer.isFromMaterial,
      confidence: answer.confidence,
      mode: answer.mode,
      createdAt: new Date().toISOString()
    });
    conversation.relatedMaterialIds = mergeUniqueIds(conversation.relatedMaterialIds, relatedMaterialIds);
    conversation.updatedAt = new Date().toISOString();
    saveAndRender();
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
    await loadMaterialDataFromApi();
  } catch (error) {
    showError(error);
  } finally {
    render();
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

async function loadMaterialDataFromApi() {
  const materials = await materialApi.listMaterials();
  const materialDetails = await Promise.all(
    materials.map(async (material) => {
      const [summary, flashcards, quizzes, chunks, qaRecords] = await Promise.all([
        materialApi.getSummary(material.id),
        materialApi.listFlashcards(material.id),
        materialApi.listQuiz(material.id),
        materialApi.listChunks(material.id),
        materialApi.listQaRecords(material.id)
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
        qaRecords
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
  if (activeCardIndex >= state.flashcards.length) {
    activeCardIndex = 0;
  }
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

function normalizeState(nextState) {
  const materialsByTitle = new Map();
  nextState.materialChunks = nextState.materialChunks || {};
  nextState.materialQaRecords = nextState.materialQaRecords || {};
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

function getActiveMaterialIdForQuestion() {
  const conversation = getActiveConversation();
  if (conversation.relatedMaterialIds.length) {
    return conversation.relatedMaterialIds[conversation.relatedMaterialIds.length - 1];
  }
  return undefined;
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
  renderMaterialFormMode();
  renderGoals();
  renderGoalDetail();
  renderMaterials();
  renderSummaries();
  renderChat();
  renderFlashcard();
  renderQuizzes();
  renderProgress();
}
