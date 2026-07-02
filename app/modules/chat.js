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
