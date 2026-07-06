// chat module extracted from app.js.

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
    materialId: message.materialId || "",
    qaRecordId: message.qaRecordId || "",
    basis: message.basis || "",
    suggestion: message.suggestion || "",
    references: message.references || [],
    relatedMaterialIds: message.relatedMaterialIds || [],
    isFromMaterial: message.isFromMaterial,
    confidence: message.confidence || "",
    mode: message.mode || "",
    nextAction: message.nextAction || "",
    requiresConfirmation: Boolean(message.requiresConfirmation),
    insufficiencyReason: message.insufficiencyReason || "",
    reviewDrafts: message.reviewDrafts || [],
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

function renderChat() {
  const log = document.getElementById("chat-log");
  log.innerHTML = "";
  getActiveConversation().messages.forEach((message) => {
    const node = document.createElement("div");
    node.className = `message ${message.role === "user" ? "user" : "agent"}`;
    node.appendChild(messageContentNode(message));

    if (message.role === "assistant") {
      node.appendChild(agentAnswerMetaNode(message));
    }

    log.appendChild(node);
  });
  log.scrollTop = log.scrollHeight;
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

function collectReferenceMaterialIds(references) {
  if (!Array.isArray(references)) return [];
  return [...new Set(references.map((reference) => reference.materialId).filter(Boolean))];
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

function messageContentNode(message) {
  const content = document.createElement("p");
  content.className = "message-content";
  content.textContent = message.content;
  return content;
}

function agentAnswerMetaNode(message) {
  const wrapper = document.createElement("div");
  wrapper.className = "message-answer-meta";

  if (message.confidence || message.mode) {
    const status = document.createElement("div");
    status.className = "message-status";
    const confidence = message.confidence || "unknown";
    status.innerHTML = `
      <span>${message.isFromMaterial === false ? "资料不足" : "基于资料"}</span>
      <span>confidence: ${escapeHtml(confidence)}</span>
      ${message.mode ? `<span>${escapeHtml(message.mode)}</span>` : ""}
    `;
    wrapper.appendChild(status);
  }

  if (message.basis) {
    wrapper.appendChild(answerDetailNode("回答依据", message.basis));
  }

  if (message.suggestion) {
    wrapper.appendChild(answerDetailNode("学习建议", message.suggestion));
  }

  if (message.nextAction) {
    wrapper.appendChild(answerDetailNode("下一步动作", getNextActionLabel(message.nextAction)));
  }

  if (message.insufficiencyReason) {
    wrapper.appendChild(answerDetailNode("资料不足原因", message.insufficiencyReason));
  }

  if (message.reviewDrafts && message.reviewDrafts.length) {
    wrapper.appendChild(answerDetailNode("待确认草稿", `已生成 ${message.reviewDrafts.length} 条，确认后再写入正式复习内容。`));
  }

  if (message.references && message.references.length) {
    wrapper.appendChild(referenceChunksNode(message.references));
  } else if (message.relatedMaterialIds.length) {
    wrapper.appendChild(referenceNode(message.relatedMaterialIds));
  }

  return wrapper;
}

function answerDetailNode(title, text) {
  const detail = document.createElement("div");
  detail.className = "message-detail";
  const label = document.createElement("strong");
  label.textContent = title;
  const body = document.createElement("p");
  body.textContent = text;
  detail.append(label, body);
  return detail;
}

function getNextActionLabel(action) {
  const labels = {
    answer_only: "先阅读回答，不生成复习内容",
    review_material: "回看资料并整理复习点",
    create_flashcards: "生成闪卡草稿，等待用户确认",
    create_quiz: "生成测试题草稿，等待用户确认",
    ask_for_more_material: "补充资料后再提问"
  };
  return labels[action] || action;
}

function referenceChunksNode(references) {
  const detail = document.createElement("details");
  detail.className = "message-reference-chunks";
  const summary = document.createElement("summary");
  summary.textContent = `来源片段 ${references.length} 条`;
  detail.appendChild(summary);

  references.forEach((reference) => {
    const item = document.createElement("article");
    item.className = "reference-chunk";
    item.innerHTML = `
      <div class="chunk-meta">
        <span>${escapeHtml(reference.materialTitle)}</span>
        <span>片段 ${Number(reference.chunkIndex) + 1} / score ${escapeHtml(reference.score)}</span>
      </div>
      <p>${escapeHtml(reference.content)}</p>
    `;
    detail.appendChild(item);
  });

  return detail;
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
