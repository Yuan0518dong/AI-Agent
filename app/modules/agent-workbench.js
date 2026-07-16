// Agent workbench module.

let currentDecisionMode = "hybrid";

function toggleAgentDecisionMode() {
  currentDecisionMode = currentDecisionMode === "rule-based" ? "hybrid" : "rule-based";
  const btn = document.getElementById("agent-mode-toggle-btn");
  if (btn) btn.textContent = getAgentModeToggleLabel();
}

function getAgentModeToggleLabel() {
  return currentDecisionMode === "rule-based" ? "改用智能模式" : "改用本地规则";
}

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

async function loadAgentRunsFromApi(goalId = selectedGoalId || "") {
  state.agentRuns = await agentApi.listRuns(goalId, 20);
  const selectedSummary = state.agentRuns.find((run) => run.id === state.selectedAgentRunId);
  if (!selectedSummary) {
    state.selectedAgentRunId = state.agentRuns[0]?.id || "";
    state.selectedAgentRun = null;
  }
  const activeSummary = state.agentRuns.find((run) => run.id === state.selectedAgentRunId);
  if (
    activeSummary
    && (!state.selectedAgentRun
      || state.selectedAgentRun.id !== activeSummary.id
      || state.selectedAgentRun.updatedAt !== activeSummary.updatedAt)
  ) {
    state.selectedAgentRun = await agentApi.getRun(activeSummary.id);
  }
  saveState();
  return state.agentRuns;
}

async function generateAgentDecision(triggerButton = null, goalId = selectedGoalId || "") {
  setButtonLoading(triggerButton, true, "生成中");

  try {
    state.agentDecision = await agentApi.decide(goalId, currentDecisionMode);
    await loadAgentActionLogsFromApi(goalId);
    await loadAgentRunsFromApi(goalId);
    saveState();
    renderAgentWorkbench();
    showSuccess("下一步建议已生成");
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
    await loadAgentRunsFromApi(goalId);
    state.agentDecision = null;
    saveState();
    renderAgentWorkbench();
    showSuccess("学习状态已刷新");
  } catch (error) {
    showError(error);
  } finally {
    setButtonLoading(triggerButton, false);
  }
}

async function selectAgentGoal(goalId, selectElement = null) {
  if (selectElement) selectElement.disabled = true;
  try {
    if (goalId) {
      await loadSelectedGoalFromApi(goalId);
    } else {
      clearSelectedGoal();
    }
    await loadAgentContextFromApi(goalId);
    await loadAgentActionLogsFromApi(goalId);
    await loadAgentRunsFromApi(goalId);
    state.agentDecision = null;
    saveState();
    render();
    showSuccess(goalId ? "学习目标已切换" : "已切换为全部目标概览");
  } catch (error) {
    showError(error);
  } finally {
    if (selectElement) selectElement.disabled = false;
  }
}

function renderAgentWorkbench() {
  const context = state.agentContext;
  const root = document.getElementById("agent-workbench");
  if (!root) return;

  if (!context) {
    root.innerHTML = "";
    root.appendChild(emptyNode("暂时无法读取学习状态", "刷新后会展示智能体当前读取到的目标、任务、资料和复习状态。"));
    return;
  }

  renderAgentWorkbenchHeader(context);
  renderAgentGoalSelect();
  renderAgentRunPanel();
  renderAgentDecisionPanel();
  renderAgentActionLogPanel();
  renderAgentObservationList(context);
  renderAgentTaskPanel(context);
  renderAgentMaterialPanel(context);
  renderAgentReviewPanel(context);
  renderAgentQuizPanel(context);
  renderAgentQaPanel(context);
}

async function startAgentRun(triggerButton = null) {
  if (!selectedGoalId) {
    showError(new Error("请先在“学习目标”中选择一个目标，再开始执行"));
    return;
  }
  const objectiveInput = document.getElementById("agent-run-objective");
  const stepInput = document.getElementById("agent-run-max-steps");
  const maxSteps = Math.min(8, Math.max(1, Number(stepInput?.value || 3)));
  if (stepInput) stepInput.value = String(maxSteps);
  setButtonLoading(triggerButton, true, "启动中");
  try {
    const run = await agentApi.createRun({
      goalId: selectedGoalId,
      objective: objectiveInput?.value.trim() || "推进当前学习目标的下一步行动。",
      decisionMode: currentDecisionMode,
      maxSteps
    });
    state.selectedAgentRunId = run.id;
    const executed = await agentApi.executeRun(run.id);
    await syncAgentRunState(executed);
    await refreshAgentContext(null, selectedGoalId);
    showSuccess("智能任务已开始执行");
  } catch (error) {
    showError(error);
  } finally {
    setButtonLoading(triggerButton, false);
  }
}

async function selectAgentRun(runId, triggerButton = null) {
  setButtonLoading(triggerButton, true, "读取中");
  try {
    state.selectedAgentRunId = runId;
    await syncAgentRunState(await agentApi.getRun(runId));
    renderAgentWorkbench();
  } catch (error) {
    showError(error);
  } finally {
    setButtonLoading(triggerButton, false);
  }
}

async function resumeAgentRun(runId, triggerButton = null) {
  setButtonLoading(triggerButton, true, "恢复中");
  try {
    await syncAgentRunState(await agentApi.executeRun(runId));
    await refreshAgentContext(null, selectedGoalId);
    showSuccess("智能任务已继续执行");
  } catch (error) {
    showError(error);
  } finally {
    setButtonLoading(triggerButton, false);
  }
}

async function respondToAgentConfirmation(run, status, triggerButton = null) {
  const waitingStep = [...(run.steps || [])].reverse().find((step) => step.status === "waiting_confirmation");
  if (!waitingStep?.actionLogId) {
    showError(new Error("当前智能任务没有需要确认的内容"));
    return;
  }
  setButtonLoading(triggerButton, true, status === "accepted" ? "确认中" : "拒绝中");
  try {
    await agentApi.updateActionLog(waitingStep.actionLogId, { status });
    await syncAgentRunState(await agentApi.executeRun(run.id));
    await refreshAgentContext(null, selectedGoalId);
    showSuccess(status === "accepted" ? "已确认并继续执行" : "已拒绝写入，任务将继续判断");
  } catch (error) {
    showError(error);
  } finally {
    setButtonLoading(triggerButton, false);
  }
}

async function closeAgentRun(runId, triggerButton = null) {
  setButtonLoading(triggerButton, true, "取消中");
  try {
    await syncAgentRunState(await agentApi.cancelRun(runId));
    await loadAgentRunsFromApi(selectedGoalId);
    renderAgentWorkbench();
    showSuccess("智能任务已取消");
  } catch (error) {
    showError(error);
  } finally {
    setButtonLoading(triggerButton, false);
  }
}

async function syncAgentRunState(run) {
  state.selectedAgentRunId = run.id;
  const index = (state.agentRuns || []).findIndex((item) => item.id === run.id);
  const summary = { ...run };
  delete summary.steps;
  delete summary.contextSnapshot;
  delete summary.decisionSnapshot;
  if (index >= 0) state.agentRuns[index] = summary;
  else state.agentRuns = [summary, ...(state.agentRuns || [])];
  state.selectedAgentRun = run;
  saveState();
  renderAgentWorkbench();
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
  return getAgentActionLabel(actionType);
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
    setSelectedGoalId(existingDraft.goalId);
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

  setSelectedGoalId(goal.id);
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
    body.appendChild(emptyNode("暂无学习建议", "点击“分析下一步”后，智能体会根据当前学习状态给出下一步安排。"));
    return;
  }

  mode.textContent = getAgentModeLabel(decision.mode);
  if (decision.requestedMode && decision.requestedMode !== decision.mode) {
    mode.textContent = `${getAgentModeLabel(decision.requestedMode)} → ${getAgentModeLabel(decision.mode)}`;
  }

  // 模式切换控制条
  const modeBar = document.createElement("div");
  modeBar.className = "agent-mode-bar";
  const toggleBtn = document.createElement("button");
  toggleBtn.id = "agent-mode-toggle-btn";
  toggleBtn.className = "ghost-button";
  toggleBtn.textContent = getAgentModeToggleLabel();
  toggleBtn.addEventListener("click", () => {
    toggleAgentDecisionMode();
  });
  modeBar.appendChild(toggleBtn);
  body.appendChild(modeBar);

  const summary = document.createElement("article");
  summary.className = "agent-decision-summary";
  summary.innerHTML = `
    <div>
      <span>下一步动作</span>
      <strong>${escapeHtml(getAgentActionLabel(decision.nextAction))}</strong>
    </div>
    <p>${escapeHtml(getAgentDecisionReason(decision))}</p>
    <p>${escapeHtml(getAgentStateSummary(decision))}</p>
  `;
  body.appendChild(summary);

  // Guard 评审面板：hybrid 模式或 decisionGuard 数据存在时展示
  if (decision.requestedMode === "hybrid" || decision.decisionGuard) {
    body.appendChild(agentDecisionGuardNode(decision));
  }

  body.appendChild(agentDecisionProblemsNode(decision.problems || []));
  body.appendChild(agentDecisionActionsNode(decision.proposedActions || []));
}

function renderAgentRunPanel() {
  const count = document.getElementById("agent-run-count");
  const list = document.getElementById("agent-run-list");
  const detail = document.getElementById("agent-run-detail");
  if (!count || !list || !detail) return;

  const runs = state.agentRuns || [];
  count.textContent = `${runs.length} 条`;
  list.innerHTML = "";
  if (!runs.length) {
    list.appendChild(emptyNode("暂无智能任务", "选择学习目标并开始执行后，这里会保留每次任务记录。"));
  } else {
    runs.slice(0, 8).forEach((run) => {
      const item = document.createElement("button");
      item.type = "button";
      item.className = `agent-run-row ${run.id === state.selectedAgentRunId ? "active" : ""}`;
      item.innerHTML = `
        <span class="agent-run-status ${escapeHtml(run.status || "decided")}">${escapeHtml(agentRunStatusLabel(run.status))}</span>
        <strong>${escapeHtml(run.objective || "未命名学习行动")}</strong>
        <small>${run.currentStep || 0}/${run.maxSteps || 0} 步 · ${escapeHtml(formatDateTime(run.updatedAt))}</small>
      `;
      item.addEventListener("click", () => selectAgentRun(run.id, item));
      list.appendChild(item);
    });
  }

  detail.innerHTML = "";
  const run = state.selectedAgentRun;
  if (!run || run.id !== state.selectedAgentRunId) {
    detail.appendChild(emptyNode("选择一条智能任务", "可以查看每一步做了什么、执行结果以及停止原因。"));
    return;
  }
  detail.appendChild(agentRunSummaryNode(run));
  detail.appendChild(agentRunTimelineNode(run));
}

function agentRunSummaryNode(run) {
  const wrapper = document.createElement("section");
  wrapper.className = "agent-run-summary";
  const guard = run.decisionSnapshot?.decisionGuard || {};
  const provider = run.decisionSnapshot?.providerMetadata || {};
  const providerLabel = provider.provider
    ? `${getAgentProviderLabel(provider.provider)}${provider.model ? ` · ${provider.model}` : ""}`
    : "未记录";
  wrapper.innerHTML = `
    <div class="agent-card-head">
      <div>
        <span>当前智能任务</span>
        <strong>${escapeHtml(run.objective || "未命名学习行动")}</strong>
      </div>
      <span class="agent-run-status ${escapeHtml(run.status || "decided")}">${escapeHtml(agentRunStatusLabel(run.status))}</span>
    </div>
    <div class="agent-chip-row">
      <span>${escapeHtml(getAgentModeLabel(run.decisionMode))}</span>
      <span>${run.currentStep || 0}/${run.maxSteps || 0} 步</span>
      <span>停止原因：${escapeHtml(getAgentStopReasonLabel(run.stopReason))}</span>
      <span>安全检查：${escapeHtml(getAgentGuardStatusLabel(guard.status))}</span>
      <span>模型：${escapeHtml(providerLabel)}</span>
    </div>
    ${run.error ? `<p class="agent-run-error">${escapeHtml(localizeAgentText(run.error))}</p>` : ""}
    ${run.decisionSnapshot?.reflection ? `<p class="agent-run-reflection">${escapeHtml(localizeAgentText(run.decisionSnapshot.reflection))}</p>` : ""}
  `;
  const actions = document.createElement("div");
  actions.className = "agent-run-actions";
  if (run.status === "waiting_confirmation") {
    actions.appendChild(agentRunButton("确认写入并继续", "primary-button", (button) => respondToAgentConfirmation(run, "accepted", button)));
    actions.appendChild(agentRunButton("拒绝写入并继续", "ghost-button", (button) => respondToAgentConfirmation(run, "rejected", button)));
  } else if (!["completed", "failed", "max_steps", "cancelled", "closed"].includes(run.status)) {
    actions.appendChild(agentRunButton("继续执行", "primary-button", (button) => resumeAgentRun(run.id, button)));
    actions.appendChild(agentRunButton("取消任务", "ghost-button", (button) => closeAgentRun(run.id, button)));
  }
  if (actions.children.length) wrapper.appendChild(actions);
  return wrapper;
}

function agentRunTimelineNode(run) {
  const wrapper = document.createElement("section");
  wrapper.className = "agent-run-timeline";
  wrapper.innerHTML = "<h3>执行过程</h3>";
  const steps = run.steps || [];
  if (!steps.length) {
    wrapper.appendChild(emptyNode("尚未开始执行", "智能任务开始后，这里会按顺序显示每一步的处理结果。"));
    return wrapper;
  }
  steps.forEach((step) => {
    const item = document.createElement("article");
    item.className = `agent-step ${step.status || "running"}`;
    const decision = step.decisionSnapshot || {};
    const guard = decision.decisionGuard || {};
    const guardInterventions = (guard.interventions || []).map(agentGuardInterventionLabel).join("、");
    const actionLogStatus = agentActionLogStatusForStep(step);
    item.innerHTML = `
      <div class="agent-step-rail"><span>${step.stepIndex || "?"}</span></div>
      <div class="agent-step-main">
        <div class="agent-card-head">
          <div>
            <strong>${escapeHtml(getAgentToolLabel(step.toolName))}</strong>
            <p>${escapeHtml(agentRunStatusLabel(step.status))} · ${escapeHtml(formatDateTime(step.createdAt))} · ${escapeHtml(formatAgentDuration(step.createdAt, step.updatedAt))}</p>
          </div>
          <span>${escapeHtml(getAgentRiskLabel(step.actionSnapshot?.riskLevel || "low"))}</span>
        </div>
        <div class="agent-chip-row">
          <span>${escapeHtml(getAgentModeLabel(decision.mode))}</span>
          <span>${escapeHtml(getAgentActionLabel(step.actionSnapshot?.type || decision.nextAction))}</span>
          <span>安全检查：${escapeHtml(getAgentGuardStatusLabel(guard.status))}</span>
          <span>执行记录：${escapeHtml(actionLogStatus)}</span>
        </div>
        ${decision.reason ? `<p class="agent-step-reason">判断依据：${escapeHtml(getAgentStepReason(step))}</p>` : ""}
        ${guardInterventions ? `<p class="agent-step-guard">安全处理：${escapeHtml(guardInterventions)}</p>` : ""}
        ${decision.fallbackReason ? `<p class="agent-step-guard">模式说明：${escapeHtml(localizeAgentText(decision.fallbackReason))}</p>` : ""}
        ${step.error ? `<p class="agent-run-error">${escapeHtml(localizeAgentText(step.error))}</p>` : ""}
        ${agentStepObservation(step)}
        ${agentStepDetails(step)}
      </div>
    `;
    wrapper.appendChild(item);
  });
  return wrapper;
}

function agentStepObservation(step) {
  const observation = step.toolOutput?.observation || "";
  if (!observation) return "";
  return `<p class="agent-step-observation">执行结果：${escapeHtml(localizeAgentText(observation))}</p>`;
}

function agentStepDetails(step) {
  const blocks = [
    ["工具输入", step.toolInput],
    ["工具输出", step.toolOutput],
    ["动作", step.actionSnapshot],
    ["决策详情", step.decisionSnapshot],
    ["学习状态摘要", step.contextSnapshot?.summary || step.contextSnapshot?.scope || {}]
  ].map(([label, value]) => `
    <section>
      <h4>${escapeHtml(label)}</h4>
      <pre>${escapeHtml(formatAgentJson(value))}</pre>
    </section>
  `).join("");
  return `<details class="agent-step-details"><summary>查看技术详情（供排查使用）</summary>${blocks}</details>`;
}

function agentRunButton(label, className, onClick) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = className;
  button.textContent = label;
  button.addEventListener("click", () => onClick(button));
  return button;
}

function agentRunStatusLabel(status) {
  const labels = { decided: "已决策", running: "执行中", waiting_confirmation: "等待确认", completed: "已完成", failed: "失败", max_steps: "达到步数上限", cancelled: "已取消", closed: "已停止" };
  return labels[status] || "未知状态";
}

function agentActionLogStatusForStep(step) {
  if (!step.actionLogId) return "自动执行";
  const actionLog = (state.agentActionLogs || []).find((item) => item.id === step.actionLogId);
  return actionLog ? getAgentFeedbackLabel(actionLog.status) : "待同步";
}

function agentGuardInterventionLabel(intervention) {
  const type = typeof intervention === "string" ? intervention : intervention?.type;
  const labels = {
    force_confirmation: "强制确认",
    reject_unknown_action: "拒绝未知动作",
    reject_invalid_payload: "拒绝非法参数",
    reject_out_of_scope: "拒绝越权范围",
    fallback_to_rule_based: "使用本地规则"
  };
  const label = labels[type] || "已调整模型建议";
  const reason = typeof intervention === "object" ? localizeAgentText(intervention.reason || "") : "";
  return reason ? `${label}：${reason}` : label;
}

function formatAgentDuration(createdAt, updatedAt) {
  const startedAt = Date.parse(createdAt || "");
  const finishedAt = Date.parse(updatedAt || createdAt || "");
  if (!Number.isFinite(startedAt) || !Number.isFinite(finishedAt)) return "耗时未知";
  const durationMs = Math.max(0, finishedAt - startedAt);
  if (durationMs < 1000) return "耗时 <1 秒";
  if (durationMs < 60_000) return `耗时 ${(durationMs / 1000).toFixed(1)} 秒`;
  return `耗时 ${Math.floor(durationMs / 60_000)} 分 ${Math.round((durationMs % 60_000) / 1000)} 秒`;
}

function formatAgentJson(value) {
  try {
    return JSON.stringify(redactAgentValue(value), null, 2) ?? "无";
  } catch {
    return "无法展示该详情";
  }
}

function redactAgentValue(value, key = "") {
  if (/api[_-]?key|authorization|token|password|secret/i.test(key)) return "[redacted]";
  if (Array.isArray(value)) return value.map((item) => redactAgentValue(item));
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([name, item]) => [name, redactAgentValue(item, name)]));
  }
  if (typeof value === "string") {
    const redacted = value
      .replace(/\bBearer\s+[A-Za-z0-9._~+/=-]+/gi, "Bearer [redacted]")
      .replace(/\b(api[_ -]?key|authorization|token|password|secret)\b\s*[:=]\s*([^\s,;]+)/gi, "$1=[redacted]");
    return redacted.length > 800 ? `${redacted.slice(0, 800)}...` : redacted;
  }
  return value;
}

function agentDecisionGuardNode(decision) {
  const guard = decision.decisionGuard || {};
  const status = guard.status || (decision.fallbackReason ? "fallback" : "accepted");
  const interventions = guard.interventions || [];

  const STATUS_LABELS = { accepted: "已通过", sanitized: "已修正", fallback: "已使用备用方案" };
  const INTERVENTION_LABELS = {
    force_confirmation: "强制确认要求",
    reject_unknown_action: "拒绝未知动作",
    fallback_to_rule_based: "使用本地规则"
  };

  const wrapper = document.createElement("div");
  wrapper.className = "agent-decision-section agent-guard-section";
  wrapper.innerHTML = `<h3>安全检查 <span class="agent-guard-badge ${status}">${STATUS_LABELS[status] || getAgentGuardStatusLabel(status)}</span></h3>`;

  if (decision.fallbackReason) {
    const reason = document.createElement("p");
    reason.className = "agent-guard-reason";
    reason.textContent = `模式说明：${localizeAgentText(decision.fallbackReason)}`;
    wrapper.appendChild(reason);
  }

  if (interventions.length > 0) {
    interventions.forEach((iv) => {
      const item = document.createElement("article");
      item.className = "agent-decision-problem medium";
      item.innerHTML = `
        <div class="agent-card-head">
          <strong>${escapeHtml(INTERVENTION_LABELS[iv.type] || agentGuardInterventionLabel(iv.type))}</strong>
          <span>${escapeHtml(getAgentActionLabel(iv.actionType || iv.action))}</span>
        </div>
        <p>${escapeHtml(localizeAgentText(iv.reason || ""))}</p>
      `;
      wrapper.appendChild(item);
    });
  } else if (status === "accepted") {
    const ok = document.createElement("p");
    ok.className = "agent-guard-ok";
    ok.textContent = "模型输出合规，所有动作已通过评审，无需修正。";
    wrapper.appendChild(ok);
  }

  return wrapper;
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
        <span>${escapeHtml(getAgentSeverityLabel(problem.severity))}</span>
      </div>
      <p>${escapeHtml(getAgentProblemMessage(problem))}</p>
      ${problem.evidence ? `<p>相关内容：${escapeHtml(problem.evidence)}</p>` : ""}
    `;
    wrapper.appendChild(item);
  });
  return wrapper;
}

function agentDecisionActionsNode(actions) {
  const wrapper = document.createElement("div");
  wrapper.className = "agent-decision-section";
  wrapper.innerHTML = `<h3>建议的下一步</h3>`;

  if (!actions.length) {
    wrapper.appendChild(emptyNode("暂无待处理建议", "当前学习状态暂时不需要额外处理。"));
    return wrapper;
  }

  actions.forEach((action, index) => {
    const item = document.createElement("article");
    item.className = `agent-action-card ${action.requiresConfirmation ? "confirm" : ""}`;
    item.innerHTML = `
      <div class="agent-card-head">
        <strong>${escapeHtml(getAgentActionLabel(action.type))}</strong>
        <span>${action.requiresConfirmation ? "需确认" : "只读建议"}</span>
      </div>
      <p>${escapeHtml(getAgentActionDescription(action))}</p>
      <div class="agent-chip-row">
        <span>处理方式：${escapeHtml(getAgentToolLabel(action.toolName || action.type))}</span>
        <span>${escapeHtml(getAgentRiskLabel(action.riskLevel))}</span>
        <span>${action.draftOnly ? "先生成草稿" : "可直接处理"}</span>
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
      <p>${escapeHtml(getAgentActionDescription(log.proposedPayload || log))}</p>
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
  const selectedGoal = state.goals.find((goal) => goal.id === selectedGoalId);
  document.getElementById("agent-context-updated").textContent = context.generatedAt
    ? `更新于 ${formatDateTime(context.generatedAt)}`
    : "未刷新";
  document.getElementById("agent-scope-label").textContent = selectedGoal?.name || "全部目标概览";
  document.getElementById("agent-goal-total").textContent = summary.goalCount || 0;
  document.getElementById("agent-task-open-total").textContent = summary.taskOpen || 0;
  document.getElementById("agent-material-total").textContent = summary.materialTotal || 0;
  document.getElementById("agent-review-total").textContent = summary.flashcardTotal || 0;
}

function renderAgentGoalSelect() {
  const select = document.getElementById("agent-goal-select");
  if (!select) return;

  select.innerHTML = "";
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = state.goals.length ? "请选择学习目标" : "请先创建学习目标";
  select.appendChild(placeholder);

  state.goals.forEach((goal) => {
    const option = document.createElement("option");
    option.value = goal.id;
    option.textContent = goal.name;
    select.appendChild(option);
  });
  select.value = selectedGoalId || "";
}

function renderAgentObservationList(context) {
  const list = document.getElementById("agent-observation-list");
  list.innerHTML = "";

  const observations = context.summary?.observations || [];
  if (!observations.length) {
    list.appendChild(emptyNode("暂无学习提醒", "当前学习状态暂时没有需要特别提醒的内容。"));
    return;
  }

  observations.forEach((text) => {
    const item = document.createElement("article");
    item.className = "agent-observation-item";
    item.innerHTML = `
      <span aria-hidden="true">!</span>
      <p>${escapeHtml(localizeAgentText(text))}</p>
    `;
    list.appendChild(item);
  });
}

function renderAgentTaskPanel(context) {
  const list = document.getElementById("agent-task-list");
  list.innerHTML = "";

  const taskGroups = context.tasks || [];
  if (!taskGroups.length) {
    list.appendChild(emptyNode("暂无任务状态", "创建目标并生成计划后，智能体会读取任务进度。"));
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
    list.appendChild(emptyNode("暂无资料状态", "添加资料后，智能体会读取摘要、片段和关联问答。"));
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
    list.appendChild(emptyNode("暂无资料不足记录", "当智能体判断资料无法支撑回答时，会在这里提示补充资料。"));
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
    answer_with_sources: "根据资料回答问题",
    search_materials: "检索相关资料",
    review_material: "复习或整理资料",
    create_flashcards: "生成复习卡片",
    create_review_draft: "生成复习草稿",
    create_quiz: "生成测试题",
    reschedule_tasks: "重排任务",
    create_followup_tasks: "生成后续任务",
    create_task_draft: "生成任务草稿",
    apply_confirmed_draft: "写入已确认内容",
    ask_for_more_material: "补充资料",
    suggest_material_gap: "建议补充资料"
  };
  return labels[action] || "其他学习操作";
}

function getAgentRiskLabel(riskLevel) {
  const labels = {
    low: "低风险",
    medium: "中风险",
    high: "高风险"
  };
  return labels[riskLevel] || "未分级";
}

function getAgentSeverityLabel(severity) {
  const labels = {
    low: "一般提醒",
    medium: "需要关注",
    high: "优先处理"
  };
  return labels[severity] || "需要关注";
}

function getAgentProblemLabel(type) {
  const labels = {
    missing_goal: "缺少学习目标",
    proposed_drafts: "草稿等待确认",
    overdue_tasks: "任务进度滞后",
    missing_chunks: "资料缺少片段",
    missing_summary: "资料缺少总结",
    material_insufficiency: "资料不足",
    weak_quiz_attempts: "测试薄弱点",
    review_queue: "复习队列待处理",
    missing_tasks: "缺少行动任务"
  };
  return labels[type] || "学习状态提醒";
}

function getAgentFeedbackLabel(status) {
  const labels = {
    proposed: "已建议",
    accepted: "已采纳",
    rejected: "已忽略",
    later: "稍后处理",
    applied: "已执行"
  };
  return labels[status] || "已记录";
}

function getAgentModeLabel(mode) {
  const labels = {
    hybrid: "智能模式",
    "llm-json": "真实模型",
    "rule-based": "本地规则",
    mock: "本地模拟"
  };
  return labels[mode] || "本地规则";
}

function getAgentProviderLabel(provider) {
  const labels = {
    mock: "本地模拟",
    "openai-compatible": "真实模型",
    openai: "真实模型"
  };
  return labels[provider] || (provider ? "已配置模型" : "未记录");
}

function getAgentGuardStatusLabel(status) {
  const labels = {
    accepted: "已通过",
    sanitized: "已修正",
    fallback: "已使用备用方案"
  };
  return labels[status] || "未触发";
}

function getAgentStopReasonLabel(reason) {
  const labels = {
    completed: "任务完成",
    max_steps: "已达到执行步骤上限",
    no_progress: "没有新的可执行内容",
    waiting_confirmation: "等待用户确认",
    tool_error: "执行工具时出现异常",
    tool_timeout_read_retry_exhausted: "读取超时，重试后仍未完成",
    tool_timeout_write_no_retry: "写入超时，已停止避免重复写入",
    context_readback_error: "写入后读取最新学习状态失败",
    decision_readback_error: "写入后生成下一步判断失败",
    cancelled: "用户已取消"
  };
  return labels[reason] || (reason ? "任务已停止" : "进行中");
}

function getAgentToolLabel(toolName) {
  const labels = {
    answer_only: "完成当前学习建议",
    answer_with_sources: "根据资料回答问题",
    search_materials: "检索相关资料",
    review_material: "检查学习资料",
    create_review_draft: "生成复习草稿",
    create_task_draft: "生成任务草稿",
    apply_confirmed_draft: "写入已确认内容",
    suggest_material_gap: "整理资料补充建议"
  };
  return labels[toolName] || "其他学习处理";
}

function getAgentProblemMessage(problem) {
  const count = Number(String(problem.message || "").match(/\d+/)?.[0] || 0);
  const messages = {
    missing_goal: "还没有学习目标，智能体暂时无法制定下一步计划。",
    proposed_drafts: `有 ${count || 1} 份草稿等待你确认，确认后才会写入正式学习内容。`,
    overdue_tasks: `有 ${count} 项任务已经逾期，建议先调整任务安排。`,
    missing_chunks: `有 ${count} 份资料还不能被检索，需要先完成资料整理。`,
    missing_summary: `有 ${count} 份资料还没有生成总结。`,
    material_insufficiency: `有 ${count} 个问题缺少足够的资料依据。`,
    weak_quiz_attempts: `检测到 ${count} 次薄弱测试记录，建议针对错题进行复习。`,
    review_queue: `有 ${count} 张闪卡等待复习。`,
    missing_tasks: "已经创建学习目标，但还没有可执行任务。"
  };
  return messages[problem.type] || localizeAgentText(problem.message || "当前学习状态需要关注。");
}

function getAgentActionDescription(action) {
  const type = action.type || action.actionType || "";
  const descriptions = {
    answer_only: "当前没有需要优先处理的问题，可以继续今天的学习安排。",
    answer_with_sources: "从已有资料中查找依据并回答当前问题。",
    search_materials: "从当前目标关联的资料中查找相关内容。",
    review_material: "检查资料是否已经完成总结和检索处理，并进入复习。",
    create_flashcards: "根据测试薄弱点生成复习草稿，确认后再加入正式闪卡。",
    create_review_draft: "根据测试薄弱点生成复习草稿，等待你确认。",
    create_quiz: "根据当前资料生成测试题，用于检查掌握情况。",
    reschedule_tasks: "把逾期任务调整为更小、更容易完成的学习步骤。",
    create_followup_tasks: "根据学习目标生成后续行动任务。",
    create_task_draft: "根据学习目标生成任务草稿，等待你确认。",
    apply_confirmed_draft: "把你确认过的草稿写入正式任务或复习内容。",
    ask_for_more_material: "当前资料不足以支撑回答，需要先补充相关资料。",
    suggest_material_gap: "整理当前缺少的资料方向，方便继续补充。"
  };
  return descriptions[type] || localizeAgentText(action.description || action.observation || "按当前建议继续处理。");
}

function getAgentDecisionReason(decision) {
  const primaryProblem = (decision.problems || [])[0];
  if (primaryProblem) {
    return `当前优先处理“${getAgentProblemLabel(primaryProblem.type)}”。${getAgentProblemMessage(primaryProblem)}`;
  }
  if (containsChinese(decision.reason)) {
    return decision.reason;
  }
  return "当前没有高优先级问题，可以继续现有学习安排。";
}

function getAgentStepReason(step) {
  const decision = step.decisionSnapshot || {};
  const executedAction = step.actionSnapshot?.type;
  if (executedAction && decision.nextAction && executedAction !== decision.nextAction) {
    return `为避免重复处理，当前步骤改为“${getAgentActionLabel(executedAction)}”。`;
  }
  return getAgentDecisionReason(decision);
}

function getAgentStateSummary(decision) {
  if (containsChinese(decision.stateSummary)) return decision.stateSummary;
  const match = String(decision.stateSummary || "").match(
    /(\d+) goal\(s\), (\d+) open task\(s\), (\d+) material\(s\), (\d+) flashcard\(s\), (\d+) weak quiz attempt\(s\)/
  );
  if (match) {
    return `${match[1]} 个目标，${match[2]} 项未完成任务，${match[3]} 份资料，${match[4]} 张闪卡，${match[5]} 次薄弱测试记录。`;
  }
  const summary = state.agentContext?.summary || {};
  return `${summary.goalCount || 0} 个目标，${summary.taskOpen || 0} 项未完成任务，${summary.materialTotal || 0} 份资料，${summary.flashcardTotal || 0} 张闪卡。`;
}

function localizeAgentText(value) {
  const text = String(value || "").trim();
  if (!text || containsChinese(text)) return text;

  const direct = {
    "LLM decision provider is unavailable.": "当前未连接真实模型，已自动使用本地规则继续完成。",
    "Tool risk policy requires user confirmation before execution.": "该操作会写入正式学习记录，执行前必须由你确认。",
    "Flashcards are waiting for review.": "有闪卡正在等待复习。",
    "Recent quiz attempts show weak points.": "最近的测试结果显示存在薄弱知识点。",
    "Some questions were marked as material-insufficient.": "部分问题缺少足够的资料依据。",
    "Learning context is ready for the next Agent decision.": "当前学习状态已经准备好，可以生成下一步建议。",
    "The Agent found no further executable action and completed the run.": "当前没有更多需要执行的操作，本次智能任务已完成。"
  };
  if (direct[text]) return direct[text];

  let match = text.match(/^(\d+) open task\(s\) are overdue\.$/);
  if (match) return `有 ${match[1]} 项未完成任务已经逾期。`;
  match = text.match(/^(\d+) material\(s\) have no chunks yet\.$/);
  if (match) return `有 ${match[1]} 份资料还没有完成检索处理。`;
  match = text.match(/^(\d+) material\(s\) have no summary yet\.$/);
  if (match) return `有 ${match[1]} 份资料还没有生成总结。`;
  match = text.match(/^(\d+) draft\(s\) await confirmation\.$/);
  if (match) return `有 ${match[1]} 份草稿等待确认。`;
  match = text.match(/^Persisted (\d+) (review|task) draft(?:s)?\.$/);
  if (match) return `已生成 ${match[1]} 份${match[2] === "review" ? "复习" : "任务"}草稿。`;
  match = text.match(/^Reused (\d+) (review|task) draft(?:s)?\.$/);
  if (match) return `已找到 ${match[1]} 份现有${match[2] === "review" ? "复习" : "任务"}草稿，没有重复生成。`;
  match = text.match(/^Persisted (\d+) (review|task) draft(?:s)?; reused (\d+)\.$/);
  if (match) return `已生成 ${match[1]} 份${match[2] === "review" ? "复习" : "任务"}草稿，并沿用 ${match[3]} 份现有草稿。`;
  match = text.match(/^(Applied|Reused) (\d+) confirmed draft\(s\) to (\d+) formal records?\.$/);
  if (match) return `${match[1] === "Reused" ? "已确认现有写入结果" : "已完成正式写入"}：${match[2]} 份草稿对应 ${match[3]} 条正式学习记录。`;
  match = text.match(/^Inspected (\d+) material\(s\); generated chunks for (\d+) and summaries for (\d+)\.$/);
  if (match) return `已检查 ${match[1]} 份资料；新增 ${match[2]} 份检索内容和 ${match[3]} 份资料总结。`;
  match = text.match(/^Generated a grounded answer with (\d+) reference\(s\); confidence is (.+)\.$/);
  if (match) return `已根据 ${match[1]} 条资料依据生成回答。`;
  match = text.match(/^Retrieved (\d+) material reference\(s\) for query '.*' using .* retrieval\.$/);
  if (match) return `已检索到 ${match[1]} 条相关资料依据。`;
  match = text.match(/^Prepared a source-gap suggestion from (\d+) insufficient answer\(s\)\.$/);
  if (match) return `已根据 ${match[1]} 条资料不足记录整理补充建议。`;
  match = text.match(/^Run completed after (\d+) persisted step\(s\)\./);
  if (match) return `智能任务已完成，共执行 ${match[1]} 个步骤。`;
  match = text.match(/^Run stopped at the step budget after (\d+) persisted step\(s\)\./);
  if (match) return `智能任务已达到步骤上限，共执行 ${match[1]} 个步骤。`;
  match = text.match(/^Run was cancelled after (\d+) persisted step\(s\)\./);
  if (match) return `智能任务已取消，取消前执行了 ${match[1]} 个步骤。`;
  match = text.match(/^Run stopped with no new executable action after (\d+) persisted step\(s\)\./);
  if (match) return `没有发现新的可执行内容，本次智能任务已结束，共执行 ${match[1]} 个步骤。`;
  if (/^LLM decision provider failed/.test(text)) {
    return "真实模型连接失败，已自动使用本地规则继续完成。";
  }
  if (/^Run failed/.test(text)) {
    return "智能任务执行失败，请查看技术详情定位原因。";
  }
  return "系统已记录一条技术信息，可在下方技术详情中查看。";
}

function containsChinese(value) {
  return /[\u3400-\u9fff]/.test(String(value || ""));
}
