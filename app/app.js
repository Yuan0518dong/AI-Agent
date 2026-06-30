const STORAGE_KEY = "student-assistant-mvp";

const defaultState = {
  goals: [],
  materials: [],
  tasks: [],
  flashcards: [],
  quizzes: [],
  chat: [
    {
      role: "agent",
      text: "你好，我会根据你的目标和资料帮你学习。先创建一个成长目标，或添加一份资料。"
    }
  ]
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
  const summary = summarizeContent(content);
  const material = {
    id: makeId(),
    title: data.get("title").trim(),
    type: data.get("type"),
    content,
    summary,
    createdAt: new Date().toISOString()
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
  state.chat.push({ role: "user", text: question });
  state.chat.push({ role: "agent", text: answerQuestion(question) });
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
  Object.assign(state, structuredClone(defaultState));
  activeCardIndex = 0;
  saveAndRender();
});

render();

function loadState() {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return structuredClone(defaultState);

  try {
    return { ...structuredClone(defaultState), ...JSON.parse(raw) };
  } catch {
    return structuredClone(defaultState);
  }
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
    item.innerHTML = `
      <div class="item-head">
        <div>
          <h3>${escapeHtml(material.title)}</h3>
          <p>${escapeHtml(material.summary.overview)}</p>
        </div>
        <button class="ghost-button" title="删除资料">×</button>
      </div>
      <div class="tag-row">
        <span class="tag">${escapeHtml(material.type)}</span>
        <span class="tag">${material.summary.keyPoints.length} 个知识点</span>
      </div>
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
    const points = material.summary.keyPoints.map((point) => `<li>${escapeHtml(point)}</li>`).join("");
    item.innerHTML = `
      <h3>${escapeHtml(material.title)}</h3>
      <p>${escapeHtml(material.summary.overview)}</p>
      <ul>${points}</ul>
    `;
    list.appendChild(item);
  });
}

function renderChat() {
  const log = document.getElementById("chat-log");
  log.innerHTML = "";
  state.chat.forEach((message) => {
    const node = document.createElement("div");
    node.className = `message ${message.role}`;
    node.textContent = message.text;
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
    <span>${escapeHtml(flashcard.source)}</span>
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

function summarizeContent(content) {
  const sentences = splitSentences(content);
  const keyPoints = sentences.slice(0, 6).map((text) => text.slice(0, 60));
  return {
    overview: sentences.slice(0, 2).join("。").slice(0, 140) || "这份资料已保存，可用于成长问答和记忆训练。",
    keyPoints: keyPoints.length ? keyPoints : ["提炼资料中的核心概念", "复习关键定义和例子"]
  };
}

function createMemoryItems(material) {
  material.summary.keyPoints.forEach((point) => {
    state.flashcards.push({
      id: makeId(),
      source: material.title,
      front: `请解释：${point}`,
      back: `围绕“${point}”进行复述，并补充一个例子。`,
      status: "new"
    });
    state.quizzes.push({
      id: makeId(),
      question: `简答：${point} 的核心含义是什么？`,
      answer: `先说明定义，再结合资料中的例子解释。`
    });
  });
}

function answerQuestion(question) {
  const text = question.toLowerCase();
  const allPoints = state.materials.flatMap((item) => item.summary.keyPoints);
  const matched = allPoints.find((point) => text.includes(point.slice(0, 4).toLowerCase()));
  const fallback = allPoints.slice(0, 3).join("；");

  if (matched) {
    return `可以。这个问题和“${matched}”有关。建议你先用一句话说出定义，再写一个例子，最后做一道题确认自己是否掌握。`;
  }

  if (fallback) {
    return `我根据当前资料先抓到这些重点：${fallback}。你可以继续追问其中一个点，我会帮你拆成定义、例子和记忆方法。`;
  }

  return "现在还没有可参考的资料。你可以先添加一份成长资料，我再基于资料帮你解释和出题。";
}

function deleteGoal(id) {
  if (!window.confirm("确认删除这个成长目标吗？")) return;
  state.goals = state.goals.filter((goal) => goal.id !== id);
  state.tasks = state.tasks.filter((task) => task.goalId !== id);
  saveAndRender();
}

function deleteMaterial(id) {
  if (!window.confirm("确认删除这份资料吗？")) return;
  const material = state.materials.find((item) => item.id === id);
  state.materials = state.materials.filter((item) => item.id !== id);
  if (material) {
    state.flashcards = state.flashcards.filter((card) => card.source !== material.title);
    state.quizzes = state.quizzes.filter((quiz) => !quiz.question.includes(material.title));
  }
  activeCardIndex = 0;
  saveAndRender();
}

function rateCard(status) {
  const card = state.flashcards[activeCardIndex];
  if (!card) return;
  card.status = status;
  activeCardIndex = state.flashcards.length ? (activeCardIndex + 1) % state.flashcards.length : 0;
  saveAndRender();
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

