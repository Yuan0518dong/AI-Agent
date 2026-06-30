const STORAGE_KEY = "student-assistant-mvp";

const defaultState = {
  goals: [],
  materials: [],
  tasks: [],
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

document.getElementById("goal-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const data = new FormData(event.currentTarget);
  const goal = {
    id: makeId(),
    name: data.get("name").trim(),
    subject: data.get("subject").trim(),
    level: data.get("level"),
    deadline: data.get("deadline"),
    dailyMinutes: Number(data.get("dailyMinutes")),
    notes: data.get("notes").trim(),
    createdAt: new Date().toISOString()
  };

  state.goals.push(goal);
  generatePlanForGoal(goal);
  saveAndRender();
  event.currentTarget.reset();
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

document.getElementById("quick-plan").addEventListener("click", () => {
  state.goals.forEach(generatePlanForGoal);
  saveAndRender();
});

document.getElementById("generate-all-plans").addEventListener("click", () => {
  state.tasks = [];
  state.goals.forEach(generatePlanForGoal);
  saveAndRender();
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

render();

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
  renderGoals();
  renderMaterials();
  renderSummaries();
  renderChat();
  renderFlashcard();
  renderQuizzes();
  renderProgress();
}

function renderMetrics() {
  const completed = state.tasks.filter((task) => task.done).length;
  const rate = state.tasks.length ? Math.round((completed / state.tasks.length) * 100) : 0;
  document.getElementById("metric-goals").textContent = state.goals.length;
  document.getElementById("metric-tasks").textContent = state.tasks.length;
  document.getElementById("metric-rate").textContent = `${rate}%`;
  document.getElementById("metric-cards").textContent = state.flashcards.length;
}

function renderToday() {
  const list = document.getElementById("today-task-list");
  list.innerHTML = "";

  if (state.tasks.length === 0) {
    list.appendChild(emptyNode("还没有任务", "创建目标后会自动生成 7 天行动计划。"));
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
      item.querySelector("input").addEventListener("change", (event) => {
        task.done = event.currentTarget.checked;
        saveAndRender();
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
        <button class="ghost-button" title="删除目标">×</button>
      </div>
      <div class="tag-row">
        <span class="tag">${escapeHtml(goal.subject)}</span>
        <span class="tag">${escapeHtml(goal.level)}</span>
        <span class="tag">每天 ${goal.dailyMinutes} 分钟</span>
        <span class="tag">截止 ${escapeHtml(goal.deadline)}</span>
      </div>
    `;
    item.querySelector("button").addEventListener("click", () => deleteGoal(goal.id));
    list.appendChild(item);
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

  if (state.goals.length === 0) {
    list.appendChild(emptyNode("暂无进度", "创建目标并完成任务后会生成进度。"));
    return;
  }

  state.goals.forEach((goal) => {
    const tasks = state.tasks.filter((task) => task.goalId === goal.id);
    const done = tasks.filter((task) => task.done).length;
    const rate = tasks.length ? Math.round((done / tasks.length) * 100) : 0;
    const row = document.createElement("div");
    row.className = "progress-row";
    row.innerHTML = `
      <div class="progress-meta">
        <strong>${escapeHtml(goal.name)}</strong>
        <span>${rate}%</span>
      </div>
      <div class="bar"><span style="width:${rate}%"></span></div>
    `;
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

function deleteGoal(id) {
  if (!window.confirm("确认删除这个成长目标吗？")) return;
  state.goals = state.goals.filter((goal) => goal.id !== id);
  state.tasks = state.tasks.filter((task) => task.goalId !== id);
  saveAndRender();
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

