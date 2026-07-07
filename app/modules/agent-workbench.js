// Agent workbench module.

async function loadAgentContextFromApi(goalId = selectedGoalId || "") {
  state.agentContext = await agentApi.getContext(goalId);
  saveState();
  return state.agentContext;
}

async function loadAgentActionLogsFromApi(goalId = selectedGoalId || "") {
  state.agentActionLogs = await agentApi.listActionLogs(goalId, 20);
  saveState();
  return state.agentActionLogs;
}

async function generateAgentDecision(triggerButton = null, goalId = selectedGoalId || "") {
  setButtonLoading(triggerButton, true, "生成中");

  try {
    state.agentDecision = await agentApi.decide(goalId);
    await loadAgentActionLogsFromApi(goalId);
    saveState();
    renderAgentWorkbench();
    showSuccess("智能体建议已生成");
  } catch (error) {
    showError(error);
  } finally {
    setButtonLoading(triggerButton, false);
  }
}

async function refreshAgentContext(triggerButton = null, goalId = selectedGoalId || "") {
  setButtonLoading(triggerButton, true, "刷新中");

  try {
    await loadAgentContextFromApi(goalId);
    await loadAgentActionLogsFromApi(goalId);
    state.agentDecision = null;
    saveState();
    renderAgentWorkbench();
    showSuccess("智能体上下文已刷新");
  } catch (error) {
    showError(error);
  } finally {
    setButtonLoading(triggerButton, false);
  }
}

function renderAgentWorkbench() {
  const context = state.agentContext;
  const root = document.getElementById("agent-workbench");
  if (!root) return;

  if (!context) {
    root.innerHTML = "";
    root.appendChild(emptyNode("暂无智能体上下文", "刷新后会展示 Agent 当前能看到的学习状态。"));
    return;
  }

  renderAgentWorkbenchHeader(context);
  renderAgentDecisionPanel();
  renderAgentActionLogPanel();
  renderAgentObservationList(context);
  renderAgentTaskPanel(context);
  renderAgentMaterialPanel(context);
  renderAgentReviewPanel(context);
  renderAgentQuizPanel(context);
  renderAgentQaPanel(context);
}

async function recordAgentActionFeedback(actionIndex, status, triggerButton = null) {
  const decision = state.agentDecision;
  const action = decision?.proposedActions?.[actionIndex];
  if (!decision || !action) return;

  setButtonLoading(triggerButton, true, "记录中");
  try {
    await agentApi.createActionLog({
      goalId: decision.scope?.goalId || selectedGoalId || "",
      actionType: action.type,
      observation: decision.stateSummary || "",
      decision,
      proposedPayload: action,
      status
    });
    await loadAgentActionLogsFromApi(decision.scope?.goalId || selectedGoalId || "");
    renderAgentWorkbench();
    showSuccess("反馈已记录");
  } catch (error) {
    showError(error);
  } finally {
    setButtonLoading(triggerButton, false);
  }
}

async function executeAgentActionLog(log, triggerButton = null) {
  setButtonLoading(triggerButton, true, "记录中");

  try {
    const result = prepareAgentActionExecution(log);
    if (result.focusTaskDraftId && selectedGoalId) {
      await loadSelectedGoalFromApi(selectedGoalId);
    }
    await agentApi.updateActionLog(log.id, { status: "applied" });
    await loadAgentActionLogsFromApi(selectedGoalId || "");
    saveState();
    render();
    if (result.focusDraftId) {
      focusReviewDraft(result.focusDraftId);
    }
    if (result.focusTaskDraftId) {
      focusAgentTaskDraft(result.focusTaskDraftId);
    }
    showSuccess(result.message);
  } catch (error) {
    showError(error);
  } finally {
    setButtonLoading(triggerButton, false);
  }
}

function prepareAgentActionExecution(log) {
  const actionType = log.actionType || log.proposedPayload?.type || "";
  const result = runAgentActionDraft(log, actionType);
  const routes = {
    review_material: "materials",
    ask_for_more_material: "materials",
    create_flashcards: "memory",
    create_quiz: "memory",
    reschedule_tasks: "goals",
    create_followup_tasks: "goals",
    answer_only: "study"
  };
  switchView(routes[actionType] || "agent");
  return result || { message: "已进入处理页面并标记完成" };
}

function runAgentActionDraft(log, actionType) {
  if (actionType === "create_flashcards" || actionType === "create_quiz") {
    const draft = createAgentReviewDraft(log, actionType);
    if (draft) {
      return {
        message: "已生成复盘草稿，确认后再加入正式闪卡",
        focusDraftId: draft.id
      };
    }
    return { message: "已进入记忆页，请先选择资料或完成一次测试" };
  }

  if (actionType === "ask_for_more_material") {
    prefillMaterialFormFromAgent(log);
    return { message: "已预填补充资料草稿，请确认后保存" };
  }

  if (actionType === "create_followup_tasks" || actionType === "reschedule_tasks") {
    const draft = createAgentTaskDraft(log, actionType);
    if (draft) {
      return {
        message: "已生成任务草稿，确认后再写入正式任务",
        focusTaskDraftId: draft.id
      };
    }
    return { message: "已进入目标页，请先选择目标再生成任务草稿" };
  }

  if (actionType === "review_material") {
    return { message: "已进入资料页，请先处理资料或复习队列" };
  }

  return null;
}

function createAgentReviewDraft(log, actionType) {
  const material = findAgentDraftMaterial(log);
  if (!material) return null;

  const timestamp = new Date().toISOString();
  const draftKey = `${log.id}:${actionType}`;
  const existingDraft = (state.qaReviewDrafts || []).find((draft) => draft.agentActionLogId === log.id);
  if (existingDraft) {
    highlightedReviewDraftId = existingDraft.id;
    return existingDraft;
  }

  const draft = {
    id: makeId(),
    type: "flashcard",
    materialId: material.id,
    qaRecordId: "",
    agentActionLogId: log.id,
    agentDraftKey: draftKey,
    question: getAgentDraftQuestion(log, actionType),
    front: getAgentDraftFront(log, material, actionType),
    back: getAgentDraftBack(log, material, actionType),
    source: "agent",
    createdAt: timestamp
  };

  highlightedReviewDraftId = draft.id;
  state.qaReviewDrafts.unshift(draft);
  return draft;
}

function findAgentDraftMaterial(log) {
  const payload = log.proposedPayload?.payload || {};
  const context = state.agentContext || {};
  const ids = [
    ...(payload.materialIds || []),
    ...(context.quiz?.weakAttempts || []).map((attempt) => attempt.materialId),
    ...(context.review?.materialsNeedingReview || []).map((material) => material.materialId),
    ...(context.qa?.insufficiencies || []).map((record) => record.materialId)
  ].filter(Boolean);

  for (const id of ids) {
    const material = state.materials.find((item) => item.id === id);
    if (material) return material;
  }

  if (selectedGoalId) {
    const material = state.materials.find((item) => item.goalId === selectedGoalId);
    if (material) return material;
  }
  return state.materials[0] || null;
}

function getAgentDraftQuestion(log, actionType) {
  const payload = log.proposedPayload?.payload || {};
  if (actionType === "create_quiz") {
    return "根据薄弱测试结果生成一个复习问题。";
  }
  if (payload.weakAttemptCount) {
    return `针对 ${payload.weakAttemptCount} 个薄弱测试结果生成复习卡片。`;
  }
  return log.proposedPayload?.label || getAgentActionLabel(actionType);
}

function getAgentDraftFront(log, material, actionType) {
  if (actionType === "create_quiz") {
    return `请复盘《${material.title}》最近测试中的薄弱点`;
  }
  return `请解释《${material.title}》中当前最需要复习的薄弱点`;
}

function getAgentDraftBack(log, material, actionType) {
  const weakAttempt = (state.agentContext?.quiz?.weakAttempts || []).find((attempt) => {
    return attempt.materialId === material.id;
  });
  if (weakAttempt) {
    return weakAttempt.suggestion || weakAttempt.feedback || "回到资料和测试反馈，重新复述错误原因。";
  }

  const summary = material.summary || {};
  const keyPoint = (summary.difficulties || summary.keyPoints || [])[0];
  if (keyPoint) {
    return `先复述：${keyPoint}。再回到原资料补一个例子。`;
  }
  return log.proposedPayload?.description || "回到资料重新整理一个可复述的知识点。";
}

function createAgentTaskDraft(log, actionType) {
  const goal = findAgentDraftGoal(log);
  if (!goal) return null;

  const existingDraft = (state.agentTaskDrafts || []).find((draft) => {
    return draft.agentActionLogId === log.id;
  });
  if (existingDraft) {
    selectedGoalId = existingDraft.goalId;
    return existingDraft;
  }

  const overdueTasks = getAgentOverdueTasks(goal.id);
  const suggestedDays = actionType === "reschedule_tasks"
    ? Math.max(3, Math.min(7, overdueTasks.length || 3))
    : getPlanDays("goal-plan-days");
  const draft = {
    id: makeId(),
    goalId: goal.id,
    actionType,
    agentActionLogId: log.id,
    title: actionType === "reschedule_tasks" ? "重排逾期任务草稿" : "生成后续任务草稿",
    reason: log.proposedPayload?.description || log.observation || "",
    suggestedDays,
    tasks: buildAgentTaskDraftItems(goal, actionType, overdueTasks, suggestedDays),
    source: "agent",
    createdAt: new Date().toISOString()
  };

  selectedGoalId = goal.id;
  state.agentTaskDrafts.unshift(draft);
  return draft;
}

function findAgentDraftGoal(log) {
  const payload = log.proposedPayload?.payload || {};
  const ids = [
    ...(payload.goalIds || []),
    ...getAgentTaskGoalIds(payload.taskIds || []),
    selectedGoalId
  ].filter(Boolean);

  for (const id of ids) {
    const goal = state.goals.find((item) => item.id === id);
    if (goal) return goal;
  }
  return state.selectedGoal || state.goals[0] || null;
}

function getAgentTaskGoalIds(taskIds) {
  if (!taskIds.length) return [];
  const groups = state.agentContext?.tasks || [];
  return groups
    .filter((group) => {
      return [...(group.overdueItems || []), ...(group.nextOpen || [])].some((task) => {
        return taskIds.includes(task.id);
      });
    })
    .map((group) => group.goalId);
}

function getAgentOverdueTasks(goalId) {
  const group = (state.agentContext?.tasks || []).find((item) => item.goalId === goalId);
  return group?.overdueItems || [];
}

function buildAgentTaskDraftItems(goal, actionType, overdueTasks, suggestedDays) {
  if (actionType === "reschedule_tasks" && overdueTasks.length) {
    return overdueTasks.slice(0, suggestedDays).map((task, index) => ({
      title: task.title,
      detail: task.detail || "降低任务粒度后重新安排。",
      date: offsetDate(index),
      sourceTaskId: task.id
    }));
  }

  const topics = collectTopics(goal).slice(0, suggestedDays);
  return Array.from({ length: suggestedDays }, (_, index) => {
    const topic = topics[index % topics.length] || goal.subject || "核心知识点";
    return {
      title: `第 ${index + 1} 天：学习 ${topic}`,
      detail: `${goal.dailyMinutes || 60} 分钟学习，完成 1 次复述和 1 次检查。`,
      date: offsetDate(index)
    };
  });
}

function renderAgentDecisionPanel() {
  const decision = state.agentDecision;
  const body = document.getElementById("agent-decision-body");
  const mode = document.getElementById("agent-decision-mode");
  if (!body || !mode) return;

  body.innerHTML = "";
  if (!decision) {
    mode.textContent = "未生成";
    body.appendChild(emptyNode("暂无智能体建议", "点击“生成建议”后，Agent 会基于当前上下文输出下一步动作草案。"));
    return;
  }

  mode.textContent = decision.mode || "rule-based";

  const summary = document.createElement("article");
  summary.className = "agent-decision-summary";
  summary.innerHTML = `
    <div>
      <span>下一步动作</span>
      <strong>${escapeHtml(getAgentActionLabel(decision.nextAction))}</strong>
    </div>
    <p>${escapeHtml(decision.reason || "")}</p>
    <p>${escapeHtml(decision.stateSummary || "")}</p>
  `;
  body.appendChild(summary);

  body.appendChild(agentDecisionProblemsNode(decision.problems || []));
  body.appendChild(agentDecisionActionsNode(decision.proposedActions || []));
}

function agentDecisionProblemsNode(problems) {
  const wrapper = document.createElement("div");
  wrapper.className = "agent-decision-section";
  wrapper.innerHTML = `<h3>发现的问题</h3>`;

  if (!problems.length) {
    wrapper.appendChild(emptyNode("暂无明显问题", "当前上下文没有触发高优先级问题。"));
    return wrapper;
  }

  problems.forEach((problem) => {
    const item = document.createElement("article");
    item.className = `agent-decision-problem ${problem.severity || "medium"}`;
    item.innerHTML = `
      <div class="agent-card-head">
        <strong>${escapeHtml(getAgentProblemLabel(problem.type))}</strong>
        <span>${escapeHtml(problem.severity || "medium")}</span>
      </div>
      <p>${escapeHtml(problem.message || "")}</p>
      ${problem.evidence ? `<p>${escapeHtml(problem.evidence)}</p>` : ""}
    `;
    wrapper.appendChild(item);
  });
  return wrapper;
}

function agentDecisionActionsNode(actions) {
  const wrapper = document.createElement("div");
  wrapper.className = "agent-decision-section";
  wrapper.innerHTML = `<h3>待确认动作</h3>`;

  if (!actions.length) {
    wrapper.appendChild(emptyNode("暂无动作草案", "Agent 暂未生成需要处理的动作。"));
    return wrapper;
  }

  actions.forEach((action, index) => {
    const item = document.createElement("article");
    item.className = `agent-action-card ${action.requiresConfirmation ? "confirm" : ""}`;
    item.innerHTML = `
      <div class="agent-card-head">
        <strong>${escapeHtml(action.label || getAgentActionLabel(action.type))}</strong>
        <span>${action.requiresConfirmation ? "需确认" : "只读建议"}</span>
      </div>
      <p>${escapeHtml(action.description || "")}</p>
      <div class="agent-chip-row">
        <span>${escapeHtml(getAgentActionLabel(action.type))}</span>
        <span>${escapeHtml(action.status || "proposed")}</span>
      </div>
      <div class="agent-action-feedback">
        <button class="ghost-button" data-feedback="accepted" type="button">采纳</button>
        <button class="ghost-button" data-feedback="rejected" type="button">忽略</button>
        <button class="ghost-button" data-feedback="later" type="button">稍后</button>
      </div>
    `;
    item.querySelectorAll("[data-feedback]").forEach((button) => {
      button.addEventListener("click", () => {
        recordAgentActionFeedback(index, button.dataset.feedback, button);
      });
    });
    wrapper.appendChild(item);
  });
  return wrapper;
}

function renderAgentActionLogPanel() {
  const count = document.getElementById("agent-action-log-count");
  const list = document.getElementById("agent-action-log-list");
  if (!count || !list) return;

  const logs = state.agentActionLogs || [];
  count.textContent = `${logs.length} 条`;
  list.innerHTML = "";

  if (!logs.length) {
    list.appendChild(emptyNode("暂无反馈记录", "采纳、忽略或稍后处理建议后，会在这里留下记录。"));
    return;
  }

  logs.slice(0, 5).forEach((log) => {
    const item = document.createElement("article");
    item.className = `agent-action-log-item ${log.status}`;
    item.innerHTML = `
      <div class="agent-card-head">
        <strong>${escapeHtml(getAgentActionLabel(log.actionType))}</strong>
        <span>${escapeHtml(getAgentFeedbackLabel(log.status))}</span>
      </div>
      <p>${escapeHtml(log.proposedPayload?.description || log.observation || "")}</p>
      <small>${escapeHtml(formatDateTime(log.createdAt))}</small>
      ${renderAgentExecutionHint(log)}
      ${log.status === "applied" ? "" : `
        <div class="agent-action-feedback">
          <button class="ghost-button" data-apply-log="${escapeHtml(log.id)}" type="button">执行并标记</button>
        </div>
      `}
    `;
    const applyButton = item.querySelector("[data-apply-log]");
    if (applyButton) {
      applyButton.addEventListener("click", () => {
        executeAgentActionLog(log, applyButton);
      });
    }
    list.appendChild(item);
  });
}

function renderAgentExecutionHint(log) {
  const actionType = log.actionType || log.proposedPayload?.type || "";
  const labels = {
    create_flashcards: "执行后会先生成复盘草稿，不直接写入正式闪卡。",
    create_quiz: "执行后会先生成复盘草稿，不直接改测试题库。",
    ask_for_more_material: "执行后会预填资料表单，保存前仍需用户确认。",
    create_followup_tasks: "执行后只进入目标页，任务生成仍需用户确认。",
    reschedule_tasks: "执行后只进入目标页，重排任务仍需用户确认。"
  };
  const label = labels[actionType];
  return label ? `<small>${escapeHtml(label)}</small>` : "";
}

function renderAgentWorkbenchHeader(context) {
  const summary = context.summary || {};
  document.getElementById("agent-context-updated").textContent = context.generatedAt
    ? `更新于 ${formatDateTime(context.generatedAt)}`
    : "未刷新";
  document.getElementById("agent-scope-label").textContent = context.scope?.goalId
    ? "当前目标"
    : "全部目标";
  document.getElementById("agent-goal-total").textContent = summary.goalCount || 0;
  document.getElementById("agent-task-open-total").textContent = summary.taskOpen || 0;
  document.getElementById("agent-material-total").textContent = summary.materialTotal || 0;
  document.getElementById("agent-review-total").textContent = summary.flashcardTotal || 0;
}

function renderAgentObservationList(context) {
  const list = document.getElementById("agent-observation-list");
  list.innerHTML = "";

  const observations = context.summary?.observations || [];
  if (!observations.length) {
    list.appendChild(emptyNode("暂无观察", "AgentContext 暂未返回观察摘要。"));
    return;
  }

  observations.forEach((text) => {
    const item = document.createElement("article");
    item.className = "agent-observation-item";
    item.innerHTML = `
      <span aria-hidden="true">!</span>
      <p>${escapeHtml(text)}</p>
    `;
    list.appendChild(item);
  });
}

function renderAgentTaskPanel(context) {
  const list = document.getElementById("agent-task-list");
  list.innerHTML = "";

  const taskGroups = context.tasks || [];
  if (!taskGroups.length) {
    list.appendChild(emptyNode("暂无任务状态", "创建目标并生成计划后，Agent 会读取任务进度。"));
    return;
  }

  taskGroups.forEach((group) => {
    const item = document.createElement("article");
    item.className = `agent-context-card ${group.overdue ? "risk" : ""}`;
    item.innerHTML = `
      <div class="agent-card-head">
        <div>
          <strong>${escapeHtml(group.goalName)}</strong>
          <p>${group.completed}/${group.total} 已完成，${group.open} 项未完成</p>
        </div>
        <span>${group.overdue} 逾期</span>
      </div>
      ${agentMiniList(group.overdueItems, "逾期任务")}
      ${agentMiniList(group.nextOpen, "下一批任务")}
    `;
    list.appendChild(item);
  });
}

function renderAgentMaterialPanel(context) {
  const list = document.getElementById("agent-material-list");
  list.innerHTML = "";

  const materials = context.materials || [];
  if (!materials.length) {
    list.appendChild(emptyNode("暂无资料状态", "添加资料后，Agent 会读取摘要、片段和关联问答。"));
    return;
  }

  materials.slice(0, 6).forEach((material) => {
    const missing = !material.hasSummary || material.chunkCount === 0;
    const item = document.createElement("article");
    item.className = `agent-context-card ${missing ? "warning" : ""}`;
    item.innerHTML = `
      <div class="agent-card-head">
        <div>
          <strong>${escapeHtml(material.title)}</strong>
          <p>${escapeHtml(material.contentPreview || "暂无内容预览")}</p>
        </div>
        <span>${material.chunkCount} 片段</span>
      </div>
      <div class="agent-chip-row">
        <span>${material.hasSummary ? "已总结" : "缺少总结"}</span>
        <span>${material.qaCount} 条问答</span>
        <span>${material.flashcardStats?.total || 0} 张闪卡</span>
        <span>${material.quizStats?.questionCount || 0} 道测试</span>
      </div>
    `;
    list.appendChild(item);
  });
}

function renderAgentReviewPanel(context) {
  const review = context.review || {};
  document.getElementById("agent-review-new").textContent = review.new || 0;
  document.getElementById("agent-review-review").textContent = review.review || 0;
  document.getElementById("agent-review-known").textContent = review.known || 0;

  const list = document.getElementById("agent-review-list");
  list.innerHTML = "";
  const needingReview = review.materialsNeedingReview || [];
  if (!needingReview.length) {
    list.appendChild(emptyNode("暂无待复习资料", "闪卡状态会在这里汇总。"));
    return;
  }

  needingReview.slice(0, 5).forEach((material) => {
    const item = document.createElement("article");
    item.className = "agent-context-card";
    item.innerHTML = `
      <div class="agent-card-head">
        <strong>${escapeHtml(material.title)}</strong>
        <span>${material.reviewCount} 需复习</span>
      </div>
      <p>${material.newCount} 张新卡，建议先完成一轮快速回忆。</p>
    `;
    list.appendChild(item);
  });
}

function renderAgentQuizPanel(context) {
  const quiz = context.quiz || {};
  document.getElementById("agent-quiz-total").textContent = quiz.questionTotal || 0;
  document.getElementById("agent-quiz-attempts").textContent = quiz.attemptTotal || 0;
  document.getElementById("agent-quiz-weak").textContent = quiz.weakAttemptCount || 0;

  const list = document.getElementById("agent-quiz-list");
  list.innerHTML = "";
  const weakAttempts = quiz.weakAttempts || [];
  if (!weakAttempts.length) {
    list.appendChild(emptyNode("暂无测试薄弱点", "提交测试答案后，低分或错误会在这里出现。"));
    return;
  }

  weakAttempts.slice(0, 5).forEach((attempt) => {
    const item = document.createElement("article");
    item.className = "agent-context-card warning";
    item.innerHTML = `
      <div class="agent-card-head">
        <strong>${escapeHtml(attempt.title)}</strong>
        <span>${attempt.score} 分</span>
      </div>
      <p>${escapeHtml(attempt.suggestion || attempt.feedback || "建议回到资料重新复习。")}</p>
    `;
    list.appendChild(item);
  });
}

function renderAgentQaPanel(context) {
  const qa = context.qa || {};
  document.getElementById("agent-qa-recent").textContent = qa.recentCount || 0;
  document.getElementById("agent-qa-insufficient").textContent = qa.insufficiencyCount || 0;

  const list = document.getElementById("agent-qa-list");
  list.innerHTML = "";
  const insufficiencies = qa.insufficiencies || [];
  if (!insufficiencies.length) {
    list.appendChild(emptyNode("暂无资料不足记录", "当 Agent 判断资料无法支撑回答时，会在这里提示补资料。"));
    return;
  }

  insufficiencies.slice(0, 5).forEach((record) => {
    const item = document.createElement("article");
    item.className = "agent-context-card risk";
    item.innerHTML = `
      <div class="agent-card-head">
        <strong>${escapeHtml(record.materialTitle)}</strong>
        <span>资料不足</span>
      </div>
      <p>${escapeHtml(record.question)}</p>
      <p>${escapeHtml(record.insufficiencyReason || "需要补充更相关的资料。")}</p>
    `;
    list.appendChild(item);
  });
}

function agentMiniList(items, title) {
  if (!items || !items.length) return "";
  return `
    <div class="agent-mini-list">
      <span>${escapeHtml(title)}</span>
      ${items.slice(0, 3).map((item) => `<p>${escapeHtml(item.title)} · ${escapeHtml(item.date)}</p>`).join("")}
    </div>
  `;
}

function getAgentActionLabel(action) {
  const labels = {
    answer_only: "继续当前节奏",
    review_material: "复习或整理资料",
    create_flashcards: "生成复习卡片",
    create_quiz: "生成测试题",
    reschedule_tasks: "重排任务",
    create_followup_tasks: "生成后续任务",
    ask_for_more_material: "补充资料"
  };
  return labels[action] || action || "未知动作";
}

function getAgentProblemLabel(type) {
  const labels = {
    missing_goal: "缺少学习目标",
    overdue_tasks: "任务进度滞后",
    missing_chunks: "资料缺少片段",
    missing_summary: "资料缺少总结",
    material_insufficiency: "资料不足",
    weak_quiz_attempts: "测试薄弱点",
    review_queue: "复习队列待处理",
    missing_tasks: "缺少行动任务"
  };
  return labels[type] || type || "学习问题";
}

function getAgentFeedbackLabel(status) {
  const labels = {
    proposed: "已建议",
    accepted: "已采纳",
    rejected: "已忽略",
    later: "稍后处理",
    applied: "已执行"
  };
  return labels[status] || status || "已记录";
}
