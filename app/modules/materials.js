// materials module extracted from app.js.

let highlightedReviewDraftId = "";
let highlightedMaterialQaRecordId = "";
const quizAnswerDrafts = new Map();

function normalizeSummary(material) {
  const timestamp = material.createdAt || new Date().toISOString();
  if (material.type === "link") {
    return {
      materialId: material.id,
      overview: "仅保存链接，不解析网页正文。",
      keyPoints: [],
      difficulties: [],
      studyOrder: [],
      actionItems: [],
      aiMode: "link-only",
      createdAt: timestamp,
      updatedAt: material.updatedAt || timestamp
    };
  }
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
  const materials = getScopedMaterials();
  list.innerHTML = "";

  if (materials.length === 0) {
    list.appendChild(emptyNode(
      activeGoalScopeId ? "当前目标暂无资料" : "暂无资料",
      activeGoalScopeId ? "为当前学习目标添加资料后，会在这里继续整理。" : "粘贴一段文本、PDF 摘录或网页链接。"
    ));
    return;
  }

  materials.forEach((material) => {
    const item = document.createElement("article");
    item.className = "item summary-card";
    const summary = material.summary;
    const points = summary.keyPoints.map((point) => `<li>${escapeHtml(point)}</li>`).join("");
    const difficulties = summary.difficulties.map((point) => `<li>${escapeHtml(point)}</li>`).join("");
    const canEdit = ["text", "link"].includes(material.type);
    item.innerHTML = `
      <div class="item-head">
        <div>
          <h3>${escapeHtml(material.title)}</h3>
          <p>${escapeHtml(summary.overview)}</p>
        </div>
        <div class="item-actions">
          ${canEdit ? '<button class="ghost-button" data-action="edit" title="编辑资料">编辑</button>' : ""}
          <button class="ghost-button" data-action="delete" title="删除资料">×</button>
        </div>
      </div>
      <div class="tag-row">
        <span class="tag">${escapeHtml(getMaterialTypeLabel(material.type))}</span>
        <span class="tag">${summary.keyPoints.length} 个知识点</span>
        <span class="tag">${summary.aiMode}</span>
      </div>
      ${renderMaterialProcessingStatus(material)}
      <details class="material-detail">
        <summary>查看整理详情</summary>
        <strong>关键知识点</strong>
        <ul>${points}</ul>
        <strong>可能难点</strong>
        <ul>${difficulties}</ul>
      </details>
    `;
    item.querySelector('[data-action="edit"]')?.addEventListener("click", () => startMaterialEdit(material.id));
    item.querySelector('[data-action="delete"]').addEventListener("click", () => deleteMaterial(material.id));
    item.querySelectorAll('[data-action="retry-stage"]').forEach((button) => {
      button.addEventListener("click", () => retryMaterialProcessingStage(material.id, button.dataset.stage, button));
    });
    list.appendChild(item);
  });
}

const PROCESSING_STAGE_LABELS = {
  extraction: "提取",
  chunking: "切分",
  embedding: "向量化",
  summary: "总结",
  flashcards: "闪卡",
  quiz: "测试"
};

function renderMaterialProcessingStatus(material) {
  if (material.type === "link") {
    return '<p class="material-processing-note">仅保存链接，不解析网页正文。</p>';
  }
  const statuses = material.processingStatus || {};
  if (!Object.keys(statuses).length) return "";
  const stages = Object.entries(PROCESSING_STAGE_LABELS).map(([stage, label]) => {
    const current = statuses[stage] || { status: "pending", error: "" };
    const isFailed = current.status === "failed";
    return `
      <li class="processing-stage processing-stage-${escapeHtml(current.status)}">
        <span>${label}</span>
        <span>${getProcessingStatusLabel(current.status)}</span>
        ${isFailed ? `<button class="ghost-button" data-action="retry-stage" data-stage="${stage}" type="button">重试</button>` : ""}
        ${isFailed && current.error ? `<small>${escapeHtml(current.error)}</small>` : ""}
      </li>
    `;
  }).join("");
  return `<ul class="processing-stages" aria-label="资料处理状态">${stages}</ul>`;
}

function getProcessingStatusLabel(status) {
  const labels = {
    pending: "等待",
    processing: "处理中",
    completed: "完成",
    failed: "失败"
  };
  return labels[status] || status || "等待";
}

async function retryMaterialProcessingStage(materialId, stage, button) {
  setButtonLoading(button, true, "重试中");
  try {
    await materialApi.retryProcessingStage(materialId, stage);
    await loadMaterialDataFromApi();
    render();
    showSuccess(`${PROCESSING_STAGE_LABELS[stage] || stage} 阶段已重试`);
  } catch (error) {
    showError(error);
  } finally {
    setButtonLoading(button, false);
  }
}

function renderSummaries() {
  const list = document.getElementById("summary-list");
  const searchResults = document.getElementById("chunk-search-results");
  const materials = getScopedMaterials();
  list.innerHTML = "";
  renderChunkSearchResults(searchResults);

  if (materials.length === 0) {
    list.appendChild(emptyNode(
      activeGoalScopeId ? "当前目标暂无资料" : "等待资料",
      activeGoalScopeId ? "为当前学习目标添加资料后，整理结果会显示在这里。" : "资料整理结果会显示在这里。"
    ));
    return;
  }

  materials.forEach((material) => {
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
          <h4>来源片段</h4>
          <div class="inline-actions">
            <button class="ghost-button" data-action="generate-chunks" data-material-id="${escapeHtml(material.id)}" type="button">生成片段</button>
          </div>
        </div>
        ${renderMaterialChunks(chunks)}
      </div>
      <div class="qa-panel">
        <div class="qa-panel-head">
          <div>
            <h4>关联问答记录</h4>
            <span>${(state.materialQaRecords[material.id] || []).length} 条记录</span>
          </div>
          <button class="ghost-button" data-action="ask-ai" data-material-id="${escapeHtml(material.id)}" type="button">围绕此资料提问</button>
        </div>
        ${renderMaterialQaRecords(state.materialQaRecords[material.id] || [])}
      </div>
    `;
    item.querySelectorAll('[data-action="ask-ai"]').forEach((button) => button.addEventListener("click", (event) => {
      prefillQuestionFromMaterial(event.currentTarget.dataset.materialId);
    }));
    item.querySelector('[data-action="generate-chunks"]').addEventListener("click", (event) => {
      generateChunksForMaterial(event.currentTarget.dataset.materialId, event.currentTarget);
    });
    item.querySelectorAll('[data-action="qa-agent-draft"], [data-action="qa-flashcard-draft"], [data-action="qa-review-point"]').forEach((button) => {
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
            <span>${escapeHtml(formatChunkLocation(chunk))}</span>
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
            <span>${escapeHtml(formatChunkLocation(chunk))} · ${escapeHtml(chunk.searchMode || "keyword")} · score ${chunk.score}</span>
          </div>
          <p>${escapeHtml(chunk.content)}</p>
        </article>
      `).join("")}
    </div>
  `;
}

function renderMaterialQaRecords(records) {
  if (!records.length) {
    return '<p class="muted-text">暂无关联问答记录。点击上方按钮会把这份资料带入左侧成长问答。</p>';
  }

  return `
    <div class="qa-list">
      ${records.slice().reverse().map((record) => `
        <article class="qa-item ${record.isFromMaterial === false ? "qa-item-insufficient" : ""} ${record.id === highlightedMaterialQaRecordId ? "qa-item-active" : ""}" data-qa-record-id="${escapeHtml(record.id)}">
          <div class="qa-question">${escapeHtml(record.question)}</div>
          <p>${escapeHtml(record.answer)}</p>
          <div class="qa-meta">
            <span>${record.isFromMaterial === false ? "资料不足" : "基于资料"}</span>
            <span>${escapeHtml(record.confidence || "unknown")}</span>
            <span>${escapeHtml(record.sourceTitle || "未匹配资料")}</span>
          </div>
          ${record.basis ? `<div class="qa-detail"><strong>依据</strong><span>${escapeHtml(record.basis)}</span></div>` : ""}
          ${record.suggestion ? `<div class="qa-detail"><strong>建议</strong><span>${escapeHtml(record.suggestion)}</span></div>` : ""}
          ${record.nextAction ? `<div class="qa-next-action"><strong>智能体建议</strong><span>${escapeHtml(getMaterialNextActionLabel(record.nextAction))}</span></div>` : ""}
          ${record.insufficiencyReason ? `<div class="qa-detail"><strong>资料不足原因</strong><span>${escapeHtml(record.insufficiencyReason)}</span></div>` : ""}
          ${record.reviewDrafts && record.reviewDrafts.length ? `<div class="qa-detail"><strong>待确认草稿</strong><span>智能体已生成 ${record.reviewDrafts.length} 条，确认后再写入正式复习内容。</span></div>` : ""}
          <div class="qa-actions">
            ${record.reviewDrafts && record.reviewDrafts.length ? `
              <button
                class="primary-button"
                data-action="qa-agent-draft"
                data-material-id="${escapeHtml(record.materialId || "")}"
                data-record-id="${escapeHtml(record.id)}"
                type="button"
              >采纳智能体草稿</button>
            ` : ""}
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

  const action = button.dataset.action;
  const preferredAgentDraft = action === "qa-agent-draft" ? getPreferredAgentReviewDraft(record) : null;
  if (action === "qa-agent-draft" && !preferredAgentDraft) {
    showError(new Error("这条问答没有可采纳的智能体草稿"));
    return;
  }

  const type = resolveQaDraftType(action, preferredAgentDraft);
  const existingDraft = state.qaReviewDrafts.find((draft) => {
    return draft.type === type && draft.qaRecordId === record.id;
  });

  if (existingDraft) {
    if (action === "qa-agent-draft") {
      highlightedReviewDraftId = existingDraft.id;
      saveAndRender();
      switchView("memory");
      focusReviewDraft(existingDraft.id);
      showSuccess("这条问答已有对应草稿，已定位到复盘草稿区");
      return;
    }
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
    source: action === "qa-agent-draft" ? "agent" : "manual",
    createdAt: timestamp
  };

  if (type === "flashcard") {
    const agentDraft = preferredAgentDraft || getAgentReviewDraft(record, "flashcard");
    draft.front = agentDraft && agentDraft.front ? agentDraft.front : `请解释：${record.question}`;
    draft.back = agentDraft && agentDraft.back ? agentDraft.back : compactDraftText(record.answer, 220);
  } else {
    const agentDraft = preferredAgentDraft || getAgentReviewDraft(record, "review_point");
    draft.point = agentDraft && agentDraft.point
      ? agentDraft.point
      : record.suggestion || record.basis || `回到资料重新复述：${record.question}`;
  }

  highlightedReviewDraftId = draft.id;
  state.qaReviewDrafts.unshift(draft);
  saveAndRender();
  if (action === "qa-agent-draft") {
    switchView("memory");
    focusReviewDraft(draft.id);
    showSuccess("已采纳智能体草稿，已放入复盘草稿区");
    return;
  }
  showSuccess(type === "flashcard" ? "已生成闪卡草稿" : "已记录复习点");
}

function findQaRecord(materialId, recordId) {
  return (state.materialQaRecords[materialId] || []).find((record) => record.id === recordId);
}

function syncMaterialQaRecordFromAgentAnswer(answer, question) {
  if (!answer || !answer.materialId || !answer.id) return;

  const record = {
    id: answer.id,
    materialId: answer.materialId,
    goalId: answer.goalId || "",
    question: answer.question || question,
    answer: answer.answer,
    basis: answer.basis || "",
    suggestion: answer.suggestion || "",
    sourceTitle: answer.sourceTitle || "",
    isFromMaterial: answer.isFromMaterial,
    confidence: answer.confidence || "",
    mode: answer.mode || "",
    nextAction: answer.nextAction || "",
    requiresConfirmation: Boolean(answer.requiresConfirmation),
    insufficiencyReason: answer.insufficiencyReason || "",
    reviewDrafts: answer.reviewDrafts || [],
    createdAt: answer.createdAt || new Date().toISOString()
  };

  const records = state.materialQaRecords[answer.materialId] || [];
  const index = records.findIndex((item) => item.id === answer.id);
  if (index >= 0) {
    records[index] = record;
  } else {
    records.push(record);
  }
  state.materialQaRecords[answer.materialId] = records;
  highlightedMaterialQaRecordId = answer.id;
}

function focusMaterialQaRecord(recordId) {
  if (!recordId) return;
  requestAnimationFrame(() => {
    const qaNode = Array.from(document.querySelectorAll("[data-qa-record-id]")).find((item) => {
      return item.dataset.qaRecordId === recordId;
    });
    if (qaNode) {
      qaNode.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  });
}

function getAgentReviewDraft(record, type) {
  return (record.reviewDrafts || []).find((draft) => draft.type === type);
}

function getPreferredAgentReviewDraft(record) {
  return getAgentReviewDraft(record, "flashcard")
    || getAgentReviewDraft(record, "review_point")
    || (record.reviewDrafts || [])[0];
}

function resolveQaDraftType(action, agentDraft) {
  if (action === "qa-flashcard-draft") return "flashcard";
  if (action === "qa-review-point") return "review-point";
  if (agentDraft && agentDraft.type === "flashcard") return "flashcard";
  return "review-point";
}

function getMaterialNextActionLabel(action) {
  const labels = {
    answer_only: "先阅读回答，不生成复习内容",
    review_material: "回看资料并整理复习点",
    create_flashcards: "生成闪卡草稿，等待用户确认",
    create_quiz: "生成测试题草稿，等待用户确认",
    ask_for_more_material: "补充资料后再提问"
  };
  return labels[action] || action;
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
    list.appendChild(emptyNode("暂无复盘草稿", "可以从关联问答记录生成闪卡草稿或复习点。"));
    return;
  }

  list.innerHTML = drafts.slice(0, 6).map((draft) => {
    const isHighlighted = draft.id === highlightedReviewDraftId;
    return `
    <article class="review-draft-item${isHighlighted ? " review-draft-item-active" : ""}" data-review-draft-id="${escapeHtml(draft.id)}">
      <div class="review-draft-head">
        <div class="tag-row">
          <span class="tag">${draft.type === "flashcard" ? "闪卡草稿" : "复习点"}</span>
          <span class="tag">${draft.source === "agent" ? "智能体草稿" : "手动草稿"}</span>
          <span class="tag">${escapeHtml(getMaterialTitle(draft.materialId))}</span>
          ${isHighlighted ? `<span class="tag tag-accent">当前草稿</span>` : ""}
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
        ? `<h3>${escapeHtml(draft.front)}</h3><p>${escapeHtml(draft.back)}</p><p>来源问题：${escapeHtml(draft.question)}</p>`
        : `<h3>${escapeHtml(draft.point)}</h3><p>来源问题：${escapeHtml(draft.question)}</p>`}
      <div class="review-draft-actions">
        <button
          class="primary-button"
          data-action="add-review-draft-to-flashcards"
          data-draft-id="${escapeHtml(draft.id)}"
          type="button"
        >加入闪卡</button>
      </div>
    </article>
  `;
  }).join("");

  list.querySelectorAll('[data-action="delete-review-draft"]').forEach((button) => {
    button.addEventListener("click", deleteReviewDraft);
  });
  list.querySelectorAll('[data-action="add-review-draft-to-flashcards"]').forEach((button) => {
    button.addEventListener("click", addReviewDraftToFlashcards);
  });
}

function deleteReviewDraft(event) {
  const draftId = event.currentTarget.dataset.draftId;
  state.qaReviewDrafts = state.qaReviewDrafts.filter((draft) => draft.id !== draftId);
  if (highlightedReviewDraftId === draftId) {
    highlightedReviewDraftId = "";
  }
  saveAndRender();
  showSuccess("复盘草稿已删除");
}

function focusReviewDraft(draftId) {
  requestAnimationFrame(() => {
    const draftNode = Array.from(document.querySelectorAll("[data-review-draft-id]")).find((item) => {
      return item.dataset.reviewDraftId === draftId;
    });
    if (draftNode) {
      draftNode.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  });
}

async function addReviewDraftToFlashcards(event) {
  const button = event.currentTarget;
  const draftId = button.dataset.draftId;
  const draft = (state.qaReviewDrafts || []).find((item) => item.id === draftId);

  if (!draft) {
    showError(new Error("没有找到这条复盘草稿"));
    return;
  }

  const material = state.materials.find((item) => item.id === draft.materialId);
  if (!material) {
    showError(new Error("这条草稿缺少关联资料，暂时不能加入闪卡"));
    return;
  }

  setButtonLoading(button, true, "加入中");

  try {
    const flashcard = await materialApi.createFlashcard(draft.materialId, getDraftFlashcardPayload(draft));
    state.flashcards.push(flashcard);
    state.qaReviewDrafts = state.qaReviewDrafts.filter((item) => item.id !== draft.id);
    await loadAgentContextFromApi();
    activeCardIndex = Math.max(0, state.flashcards.length - 1);
    saveAndRender();
    showSuccess("已加入闪卡复习");
  } catch (error) {
    showError(error);
  } finally {
    setButtonLoading(button, false);
  }
}

function getDraftFlashcardPayload(draft) {
  if (draft.type === "flashcard") {
    return {
      front: draft.front,
      back: draft.back
    };
  }

  return {
    front: `请复习：${draft.question}`,
    back: draft.point
  };
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
    setSelectedGoalId(material.goalId);
  }
  pendingChatMaterialId = material.id;

  const input = document.querySelector('#chat-form input[name="question"]');
  input.value = `请基于《${material.title}》解释这份资料的核心内容，并给我下一步复习建议。`;
  switchView("study");
  input.focus();
  input.select();
  showSuccess("已将资料带入左侧成长问答");
}

function formatChunkLocation(chunk) {
  if (chunk.pageNumber) return `第 ${chunk.pageNumber} 页`;
  if (chunk.headingPath) return chunk.headingPath;
  if (Number.isInteger(chunk.paragraphIndex)) return `段落 ${chunk.paragraphIndex + 1}`;
  return `片段 ${Number(chunk.chunkIndex || 0) + 1}`;
}

function prefillMaterialFormFromAgent(log) {
  editingMaterialId = "";
  renderMaterialFormMode();

  const form = document.getElementById("material-form");
  if (!form) return;

  const title = getAgentMaterialDraftTitle(log);
  form.elements.title.value = title;
  form.elements.type.value = "text";
  form.elements.content.value = getAgentMaterialDraftContent(log);
  switchView("materials");
  form.scrollIntoView({ behavior: "smooth", block: "start" });
  form.elements.content.focus();
  form.elements.content.select();
}

function getAgentMaterialDraftTitle(log) {
  const insufficiency = getAgentInsufficiencyRecord(log);
  if (insufficiency?.materialTitle) {
    return `补充资料：${insufficiency.materialTitle}`;
  }
  return "补充资料：待完善来源";
}

function getAgentMaterialDraftContent(log) {
  const insufficiency = getAgentInsufficiencyRecord(log);
  const lines = [
    "智能体建议补充资料：",
    log.proposedPayload?.description || log.observation || "当前资料不足以支撑后续学习判断。",
    ""
  ];

  if (insufficiency?.question) {
    lines.push(`待补充问题：${insufficiency.question}`);
  }
  if (insufficiency?.insufficiencyReason) {
    lines.push(`资料不足原因：${insufficiency.insufficiencyReason}`);
  }
  lines.push("", "请在这里粘贴新的资料正文或来源摘录，再保存并整理。");
  return lines.join("\n");
}

function getAgentInsufficiencyRecord(log) {
  const payload = log.proposedPayload?.payload || {};
  const materialIds = payload.materialIds || [];
  const records = state.agentContext?.qa?.insufficiencies || [];
  if (!materialIds.length) {
    return records[0] || null;
  }
  return records.find((record) => materialIds.includes(record.materialId)) || records[0] || null;
}

function prefillAgentSampleQuestion(sampleKey) {
  const material = getAgentSampleMaterial();
  if (!material) {
    showError(new Error("请先添加一份资料，再进行智能体验收"));
    return;
  }

  if (material.goalId) {
    setSelectedGoalId(material.goalId);
  }
  pendingChatMaterialId = material.id;

  const input = document.querySelector('#chat-form input[name="question"]');
  input.value = buildAgentSampleQuestion(sampleKey, material);
  switchView("study");
  input.focus();
  input.select();
  renderAgentSampleState();
  showSuccess(`已基于《${material.title}》填入验收问题`);
}

function renderAgentSampleState() {
  const badge = document.getElementById("agent-sample-material");
  if (!badge) return;

  const material = getAgentSampleMaterial();
  if (!material) {
    badge.textContent = "未绑定资料";
    badge.title = "";
    return;
  }

  badge.textContent = `当前：${material.title}`;
  badge.title = material.title;
}

function getAgentSampleMaterial() {
  if (pendingChatMaterialId) {
    const pendingMaterial = state.materials.find((item) => item.id === pendingChatMaterialId);
    if (pendingMaterial) return pendingMaterial;
  }

  if (selectedGoalId) {
    const goalMaterial = state.materials.find((item) => item.goalId === selectedGoalId);
    if (goalMaterial) return goalMaterial;
  }

  return state.materials[0] || null;
}

function buildAgentSampleQuestion(sampleKey, material) {
  const title = material.title;
  const samples = {
    evidence: `请只根据《${title}》回答：这份资料里最重要的概念、人物、意象或知识点是什么？请说明依据。`,
    review: `请基于《${title}》解释这份资料的核心内容，并给我下一步复习建议。`,
    insufficient: `请只根据《${title}》回答：Transformer 的多头注意力公式是什么？如果资料没有依据，请说明资料不足。`
  };
  return samples[sampleKey] || samples.review;
}

function renderFlashcard() {
  const card = document.getElementById("flashcard");
  const count = document.getElementById("flashcard-count");
  const flashcards = getScopedFlashcards();
  if (activeCardIndex >= flashcards.length) activeCardIndex = 0;
  const flashcard = flashcards[activeCardIndex];

  if (count) {
    count.textContent = flashcards.length
      ? `第 ${activeCardIndex + 1} / ${flashcards.length} 张`
      : "0 张";
  }

  if (!flashcard) {
    card.removeAttribute("data-flashcard-id");
    card.innerHTML = "<span>暂无闪卡</span><strong>添加资料后会自动生成记忆卡片</strong>";
    return;
  }

  card.dataset.flashcardId = flashcard.id;

  card.innerHTML = `
    <div class="flashcard-meta">
      <span>${escapeHtml(getMaterialTitle(flashcard.materialId))}</span>
      <span>${escapeHtml(getFlashcardStatusLabel(flashcard.status))}</span>
    </div>
    <strong>${escapeHtml(flashcard.front)}</strong>
    <p>${escapeHtml(flashcard.back)}</p>
  `;
}

function renderQuizzes() {
  const list = document.getElementById("quiz-list");
  const quizzes = getScopedQuizzes();
  captureQuizAnswerDrafts(list);
  list.innerHTML = "";

  if (quizzes.length === 0) {
    list.appendChild(emptyNode(
      activeGoalScopeId ? "当前目标暂无测试题" : "暂无测试题",
      activeGoalScopeId ? "当前目标有资料后，会在这里显示测试题。" : "添加资料后会自动生成测试题。"
    ));
    return;
  }

  quizzes.slice(0, 8).forEach((quiz) => {
    const item = document.createElement("article");
    item.className = "item";
    item.dataset.quizId = quiz.id;
    const attempts = state.quizAttempts?.[quiz.materialId] || [];
    const latestAttempt = attempts.find((attempt) => attempt.quizId === quiz.id);
    const answerValue = getQuizAnswerValue(quiz.materialId, quiz.id, latestAttempt);
    const options = quiz.options && quiz.options.length
      ? `<div class="quiz-options">${quiz.options.map((option) => `<span class="tag">${escapeHtml(option)}</span>`).join("")}</div>`
      : "";
    item.innerHTML = `
      <h3>${escapeHtml(quiz.question)}</h3>
      ${options}
      <form class="quiz-answer-form" data-material-id="${escapeHtml(quiz.materialId)}" data-quiz-id="${escapeHtml(quiz.id)}">
        <textarea name="answer" rows="3" required placeholder="写下你的答案，再让 AI 批改"></textarea>
        <button class="primary-button" type="submit">提交批改</button>
      </form>
      ${latestAttempt ? `
        <div class="quiz-feedback ${latestAttempt.isCorrect ? "correct" : "review"}">
          <strong>${latestAttempt.isCorrect ? "回答较好" : "需要复习"} · ${latestAttempt.score} 分</strong>
          <p><strong>你的答案：</strong>${escapeHtml(latestAttempt.userAnswer || "")}</p>
          <p>${escapeHtml(latestAttempt.feedback)}</p>
          <p>${escapeHtml(latestAttempt.suggestion)}</p>
          <span class="tag">${escapeHtml(latestAttempt.mode || "mock")}</span>
        </div>
      ` : ""}
      <details class="quiz-reference">
        <summary>查看参考答案</summary>
        <p>参考答案：${escapeHtml(quiz.answer)}</p>
        <p>解释：${escapeHtml(quiz.explanation)}</p>
      </details>
      <div class="tag-row">
        <span class="tag">${escapeHtml(getMaterialTitle(quiz.materialId))}</span>
        <span class="tag">${escapeHtml(quiz.type)}</span>
      </div>
    `;
    const form = item.querySelector(".quiz-answer-form");
    const answerField = form.elements.answer;
    answerField.value = answerValue;
    answerField.addEventListener("input", () => {
      quizAnswerDrafts.set(getQuizAnswerDraftKey(quiz.materialId, quiz.id), answerField.value);
    });
    form.addEventListener("submit", submitQuizAnswer);
    list.appendChild(item);
  });
}

function captureQuizAnswerDrafts(list) {
  list.querySelectorAll(".quiz-answer-form").forEach((form) => {
    const answerField = form.elements.answer;
    if (!answerField) return;
    quizAnswerDrafts.set(
      getQuizAnswerDraftKey(form.dataset.materialId, form.dataset.quizId),
      answerField.value
    );
  });
}

function getQuizAnswerValue(materialId, quizId, latestAttempt) {
  const key = getQuizAnswerDraftKey(materialId, quizId);
  if (quizAnswerDrafts.has(key)) {
    return quizAnswerDrafts.get(key);
  }
  return latestAttempt?.userAnswer || "";
}

function getQuizAnswerDraftKey(materialId, quizId) {
  return `${materialId}:${quizId}`;
}

async function submitQuizAnswer(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector("button[type='submit']");
  const materialId = form.dataset.materialId;
  const quizId = form.dataset.quizId;
  const answer = new FormData(form).get("answer").trim();
  if (!answer) return;
  quizAnswerDrafts.set(getQuizAnswerDraftKey(materialId, quizId), answer);

  setButtonLoading(button, true, "批改中");

  try {
    await materialApi.submitQuizAnswer(materialId, quizId, answer);
    state.quizAttempts[materialId] = await materialApi.listQuizAttempts(materialId);
    saveState();
    renderQuizzes();
    showSuccess("AI 批改完成");
  } catch (error) {
    showError(error);
  } finally {
    setButtonLoading(button, false);
  }
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
  material.summary.keyPoints.forEach((point, index) => {
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
      type: index % 3 === 1 ? "application" : index % 3 === 2 ? "boundary" : "short",
      options: [],
      question: getLocalQuizQuestion(point, index),
      answer: getLocalQuizAnswer(point, index),
      explanation: getLocalQuizExplanation(material.title, point, index),
      createdAt: timestamp,
      updatedAt: timestamp
    });
  });
}

function getLocalQuizQuestion(point, index) {
  if (index % 3 === 1) {
    return `如果把“${point}”用到你的学习或项目里，第一步应该怎么做？`;
  }
  if (index % 3 === 2) {
    return `判断并说明理由：学习“${point}”时，只记住结论就够了，不需要回到资料依据。`;
  }
  return `用自己的话解释：${point}`;
}

function getLocalQuizAnswer(point, index) {
  if (index % 3 === 1) {
    return `先找到资料中支撑“${point}”的依据，再把它转成一个可执行的小动作或复习问题。`;
  }
  if (index % 3 === 2) {
    return "不对。需要回到资料依据核对来源，否则容易把自己的猜测当成资料结论。";
  }
  return `答案应围绕“${point}”展开，并能说出它在资料中的作用或结论。`;
}

function getLocalQuizExplanation(title, point, index) {
  if (index % 3 === 1) {
    return `这道题检查能不能把《${title}》中的“${point}”转成真实学习行动。`;
  }
  if (index % 3 === 2) {
    return "这道题检查资料依据意识，也对应第三版智能体的资料不足判断规则。";
  }
  return `这道题检查你是否真正理解了《${title}》中的关键点，而不是只记住原句。`;
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
  updateMaterialInputMode();
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
    submitButton.textContent = "保存并整理";
    cancelButton.hidden = true;
  }
  updateMaterialInputMode();
}

async function deleteMaterial(id) {
  if (!window.confirm("确认删除这份资料吗？")) return;

  try {
    await materialApi.deleteMaterial(id);
    if (editingMaterialId === id) {
      cancelMaterialEdit();
    }
    await loadMaterialDataFromApi();
    await loadAgentContextFromApi();
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

async function rateCard(status) {
  const flashcards = getScopedFlashcards();
  const card = flashcards[activeCardIndex];
  if (!card) return;

  try {
    const updatedCard = card.materialId && card.id
      ? await materialApi.updateFlashcard(card.materialId, card.id, { status })
      : { ...card, status, updatedAt: new Date().toISOString() };

    state.flashcards = state.flashcards.map((item) => item.id === card.id ? updatedCard : item);
    await loadAgentContextFromApi();
    activeCardIndex = flashcards.length ? (activeCardIndex + 1) % flashcards.length : 0;
    saveAndRender();
    showSuccess(status === "known" ? "已标记为掌握" : "已加入复习队列");
  } catch (error) {
    showError(error);
  }
}

function getMaterialTitle(materialId) {
  const material = state.materials.find((item) => item.id === materialId);
  return material ? material.title : "未关联资料";
}

function getFlashcardStatusLabel(status) {
  const labels = {
    new: "新卡",
    known: "已掌握",
    review: "需复习"
  };
  return labels[status] || "新卡";
}

function getMaterialTypeLabel(type) {
  const labels = {
    text: "文本",
    link: "网页链接",
    pdf: "PDF",
    markdown: "Markdown",
    txt: "TXT"
  };
  return labels[type] || type || "资料";
}


