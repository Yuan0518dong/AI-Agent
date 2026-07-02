// materials module extracted from app.js.

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
        <div class="item-actions">
          <button class="ghost-button" data-action="edit" title="编辑资料">编辑</button>
          <button class="ghost-button" data-action="delete" title="删除资料">×</button>
        </div>
      </div>
      <div class="tag-row">
        <span class="tag">${escapeHtml(getMaterialTypeLabel(material.type))}</span>
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
    item.querySelector('[data-action="edit"]').addEventListener("click", () => startMaterialEdit(material.id));
    item.querySelector('[data-action="delete"]').addEventListener("click", () => deleteMaterial(material.id));
    list.appendChild(item);
  });
}

function renderSummaries() {
  const list = document.getElementById("summary-list");
  const searchResults = document.getElementById("chunk-search-results");
  list.innerHTML = "";
  renderChunkSearchResults(searchResults);

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
    const chunks = state.materialChunks[material.id] || [];
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
      <div class="chunk-panel">
        <div class="chunk-panel-head">
          <h4>学习片段</h4>
          <button class="ghost-button" data-action="generate-chunks" data-material-id="${escapeHtml(material.id)}" type="button">生成片段</button>
        </div>
        ${renderMaterialChunks(chunks)}
      </div>
    `;
    item.querySelector('[data-action="generate-chunks"]').addEventListener("click", (event) => {
      generateChunksForMaterial(event.currentTarget.dataset.materialId, event.currentTarget);
    });
    list.appendChild(item);
  });
}

function renderMaterialChunks(chunks) {
  if (!chunks.length) {
    return '<p class="muted-text">还没有生成学习片段。</p>';
  }

  return `
    <div class="chunk-list">
      ${chunks.slice(0, 4).map((chunk) => `
        <article class="chunk-item">
          <div class="chunk-meta">
            <span>片段 ${chunk.chunkIndex + 1}</span>
            <span>${chunk.keywords.map((keyword) => escapeHtml(keyword)).join(" / ")}</span>
          </div>
          <p>${escapeHtml(chunk.content)}</p>
        </article>
      `).join("")}
    </div>
  `;
}

function renderChunkSearchResults(container) {
  if (!container) return;

  const search = state.chunkSearch || { query: "", results: [] };
  if (!search.query) {
    container.innerHTML = "";
    return;
  }

  if (!search.results.length) {
    container.innerHTML = `
      <div class="chunk-search-empty">
        <strong>未找到相关片段</strong>
        <p>关键词：${escapeHtml(search.query)}</p>
      </div>
    `;
    return;
  }

  container.innerHTML = `
    <div class="chunk-search-head">
      <strong>搜索结果：${escapeHtml(search.query)}</strong>
      <span>${search.results.length} 条</span>
    </div>
    <div class="chunk-list">
      ${search.results.map((chunk) => `
        <article class="chunk-item">
          <div class="chunk-meta">
            <span>${escapeHtml(chunk.materialTitle)}</span>
            <span>score ${chunk.score}</span>
          </div>
          <p>${escapeHtml(chunk.content)}</p>
        </article>
      `).join("")}
    </div>
  `;
}

async function generateChunksForMaterial(materialId, button) {
  setButtonLoading(button, true, "生成中");

  try {
    const chunks = await materialApi.generateChunks(materialId);
    state.materialChunks[materialId] = chunks;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    renderSummaries();
    showSuccess(chunks.length ? "学习片段已生成" : "资料内容不足，暂无片段");
  } catch (error) {
    showError(error);
  } finally {
    setButtonLoading(button, false);
  }
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

function startMaterialEdit(id) {
  const material = state.materials.find((item) => item.id === id);
  if (!material) return;

  editingMaterialId = id;
  fillMaterialForm(material);
  renderMaterialFormMode();
  switchView("materials");
  document.getElementById("material-form").scrollIntoView({ behavior: "smooth", block: "start" });
}

function cancelMaterialEdit() {
  editingMaterialId = "";
  document.getElementById("material-form").reset();
  renderMaterialFormMode();
}

function fillMaterialForm(material) {
  const form = document.getElementById("material-form");
  form.elements.title.value = material.title || "";
  form.elements.type.value = material.type || "text";
  form.elements.content.value = material.type === "link" ? material.url || material.content || "" : material.content || "";
}

function renderMaterialFormMode() {
  const title = document.getElementById("material-form-title");
  const submitButton = document.getElementById("material-submit-button");
  const cancelButton = document.getElementById("cancel-material-edit");

  if (editingMaterialId) {
    title.textContent = "编辑成长资料";
    submitButton.textContent = "保存修改";
    cancelButton.hidden = false;
  } else {
    title.textContent = "添加成长资料";
    submitButton.textContent = "▣ 保存并整理";
    cancelButton.hidden = true;
  }
}

async function deleteMaterial(id) {
  if (!window.confirm("确认删除这份资料吗？")) return;

  try {
    await materialApi.deleteMaterial(id);
    if (editingMaterialId === id) {
      cancelMaterialEdit();
    }
    await loadMaterialDataFromApi();
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
    showSuccess("资料已删除");
  } catch (error) {
    showError(error);
  }
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

function getMaterialTypeLabel(type) {
  const labels = {
    text: "文本",
    link: "网页链接"
  };
  return labels[type] || type || "资料";
}
