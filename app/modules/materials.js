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
    item.className = "item summary-card";
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
    item.className = "item summary-card";
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
          <div class="inline-actions">
            <button class="ghost-button" data-action="ask-ai" data-material-id="${escapeHtml(material.id)}" type="button">问 AI</button>
            <button class="ghost-button" data-action="generate-chunks" data-material-id="${escapeHtml(material.id)}" type="button">生成片段</button>
          </div>
        </div>
        ${renderMaterialChunks(chunks)}
      </div>
      <div class="qa-panel">
        <div class="qa-panel-head">
          <h4>资料问答</h4>
          <span>${(state.materialQaRecords[material.id] || []).length} 条记录</span>
        </div>
        <form class="material-qa-form" data-material-id="${escapeHtml(material.id)}">
          <input name="question" required placeholder="围绕这份资料提问" />
          <button class="ghost-button" type="submit">问 AI</button>
        </form>
        ${renderMaterialQaRecords(state.materialQaRecords[material.id] || [])}
      </div>
    `;
    item.querySelector('[data-action="ask-ai"]').addEventListener("click", (event) => {
      prefillQuestionFromMaterial(event.currentTarget.dataset.materialId);
    });
    item.querySelector('[data-action="generate-chunks"]').addEventListener("click", (event) => {
      generateChunksForMaterial(event.currentTarget.dataset.materialId, event.currentTarget);
    });
    item.querySelector(".material-qa-form").addEventListener("submit", askMaterialQuestion);
    item.querySelectorAll('[data-action="qa-flashcard-draft"], [data-action="qa-review-point"]').forEach((button) => {
      button.addEventListener("click", createReviewDraftFromQa);
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

function renderMaterialQaRecords(records) {
  if (!records.length) {
    return '<p class="muted-text">还没有围绕这份资料提问。</p>';
  }

  return `
    <div class="qa-list">
      ${records.slice().reverse().map((record) => `
        <article class="qa-item">
          <div class="qa-question">${escapeHtml(record.question)}</div>
          <p>${escapeHtml(record.answer)}</p>
          <div class="qa-meta">
            <span>${record.isFromMaterial === false ? "资料不足" : "基于资料"}</span>
            <span>${escapeHtml(record.confidence || "unknown")}</span>
            <span>${escapeHtml(record.sourceTitle || "未匹配资料")}</span>
          </div>
          ${record.basis ? `<div class="qa-detail"><strong>依据</strong><span>${escapeHtml(record.basis)}</span></div>` : ""}
          ${record.suggestion ? `<div class="qa-detail"><strong>建议</strong><span>${escapeHtml(record.suggestion)}</span></div>` : ""}
          <div class="qa-actions">
            <button
              class="ghost-button"
              data-action="qa-flashcard-draft"
              data-material-id="${escapeHtml(record.materialId || "")}"
              data-record-id="${escapeHtml(record.id)}"
              type="button"
            >转闪卡草稿</button>
            <button
              class="ghost-button"
              data-action="qa-review-point"
              data-material-id="${escapeHtml(record.materialId || "")}"
              data-record-id="${escapeHtml(record.id)}"
              type="button"
            >记复习点</button>
          </div>
        </article>
      `).join("")}
    </div>
  `;
}

function createReviewDraftFromQa(event) {
  const button = event.currentTarget;
  const materialId = button.dataset.materialId;
  const recordId = button.dataset.recordId;
  const record = findQaRecord(materialId, recordId);

  if (!record) {
    showError(new Error("没有找到这条问答记录"));
    return;
  }

  const type = button.dataset.action === "qa-flashcard-draft" ? "flashcard" : "review-point";
  const exists = state.qaReviewDrafts.some((draft) => {
    return draft.type === type && draft.qaRecordId === record.id;
  });

  if (exists) {
    showSuccess(type === "flashcard" ? "这条问答已有闪卡草稿" : "这条问答已有复习点");
    return;
  }

  const timestamp = new Date().toISOString();
  const draft = {
    id: makeId(),
    type,
    materialId,
    qaRecordId: record.id,
    question: record.question,
    createdAt: timestamp
  };

  if (type === "flashcard") {
    draft.front = `请解释：${record.question}`;
    draft.back = compactDraftText(record.answer, 220);
  } else {
    draft.point = record.suggestion || record.basis || `回到资料重新复述：${record.question}`;
  }

  state.qaReviewDrafts.unshift(draft);
  saveAndRender();
  showSuccess(type === "flashcard" ? "已生成闪卡草稿" : "已记录复习点");
}

function findQaRecord(materialId, recordId) {
  return (state.materialQaRecords[materialId] || []).find((record) => record.id === recordId);
}

function compactDraftText(text, maxLength) {
  const normalized = String(text || "").replace(/\s+/g, " ").trim();
  if (normalized.length <= maxLength) return normalized;
  return `${normalized.slice(0, maxLength)}...`;
}

function renderReviewDrafts() {
  const list = document.getElementById("review-draft-list");
  const count = document.getElementById("review-draft-count");
  if (!list) return;

  const drafts = state.qaReviewDrafts || [];
  if (count) {
    count.textContent = `${drafts.length} 条`;
  }

  list.innerHTML = "";
  if (!drafts.length) {
    list.appendChild(emptyNode("暂无复盘草稿", "可以从资料问答记录生成闪卡草稿或复习点。"));
    return;
  }

  list.innerHTML = drafts.slice(0, 6).map((draft) => `
    <article class="review-draft-item">
      <div class="review-draft-head">
        <div class="tag-row">
          <span class="tag">${draft.type === "flashcard" ? "闪卡草稿" : "复习点"}</span>
          <span class="tag">${escapeHtml(getMaterialTitle(draft.materialId))}</span>
        </div>
        <button
          class="ghost-button"
          data-action="delete-review-draft"
          data-draft-id="${escapeHtml(draft.id)}"
          type="button"
          title="删除草稿"
        >×</button>
      </div>
      ${draft.type === "flashcard"
        ? `<h3>${escapeHtml(draft.front)}</h3><p>${escapeHtml(draft.back)}</p>`
        : `<h3>${escapeHtml(draft.point)}</h3><p>来源问题：${escapeHtml(draft.question)}</p>`}
    </article>
  `).join("");

  list.querySelectorAll('[data-action="delete-review-draft"]').forEach((button) => {
    button.addEventListener("click", deleteReviewDraft);
  });
}

function deleteReviewDraft(event) {
  const draftId = event.currentTarget.dataset.draftId;
  state.qaReviewDrafts = state.qaReviewDrafts.filter((draft) => draft.id !== draftId);
  saveAndRender();
  showSuccess("复盘草稿已删除");
}

async function askMaterialQuestion(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const materialId = form.dataset.materialId;
  const material = state.materials.find((item) => item.id === materialId);
  const question = new FormData(form).get("question").trim();
  const button = form.querySelector("button[type='submit']");

  if (!material || !question) return;

  setButtonLoading(button, true, "提问中");

  try {
    await agentApi.ask({
      question,
      materialId,
      goalId: material.goalId || selectedGoalId || undefined,
      limit: 3
    });
    state.materialQaRecords[materialId] = await materialApi.listQaRecords(materialId);
    saveState();
    form.reset();
    renderSummaries();
    showSuccess("问答记录已保存");
  } catch (error) {
    showError(error);
  } finally {
    setButtonLoading(button, false);
  }
}

async function generateChunksForMaterial(materialId, button) {
  setButtonLoading(button, true, "生成中");

  try {
    const chunks = await materialApi.generateChunks(materialId);
    state.materialChunks[materialId] = chunks;
    saveState();
    renderSummaries();
    showSuccess(chunks.length ? "学习片段已生成" : "资料内容不足，暂无片段");
  } catch (error) {
    showError(error);
  } finally {
    setButtonLoading(button, false);
  }
}

function prefillQuestionFromMaterial(materialId) {
  const material = state.materials.find((item) => item.id === materialId);
  if (!material) return;

  if (material.goalId) {
    selectedGoalId = material.goalId;
  }
  pendingChatMaterialId = material.id;

  const input = document.querySelector('#chat-form input[name="question"]');
  input.value = `请基于《${material.title}》解释这份资料的核心内容，并给我下一步复习建议。`;
  switchView("study");
  input.focus();
  input.select();
  showSuccess("已带入资料问题，确认后发送");
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
    state.qaReviewDrafts = state.qaReviewDrafts.filter((draft) => draft.materialId !== id);
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
