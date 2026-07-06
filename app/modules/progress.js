// progress module extracted from app.js.

function renderMetrics() {
  const total = state.progress.reduce((sum, item) => sum + item.totalTasks, 0);
  const completed = state.progress.reduce((sum, item) => sum + item.completedTasks, 0);
  const rate = total ? Math.round((completed / total) * 100) : 0;
  document.getElementById("metric-goals").textContent = state.goals.length;
  document.getElementById("metric-tasks").textContent = state.tasks.length;
  document.getElementById("metric-rate").textContent = `${rate}%`;
  document.getElementById("metric-cards").textContent = state.flashcards.length;
}

function getProgressStats() {
  const totalTasks = state.progress.reduce((sum, item) => sum + item.totalTasks, 0);
  const completedTasks = state.progress.reduce((sum, item) => sum + item.completedTasks, 0);
  const completionRate = totalTasks ? Math.round((completedTasks / totalTasks) * 100) : 0;
  const reviewCards = state.flashcards.filter((card) => card.status !== "known");
  const quizAttempts = Object.values(state.quizAttempts || {}).flat();
  const attemptedQuizIds = new Set(quizAttempts.map((attempt) => attempt.quizId));
  const unattemptedQuizTotal = Math.max(0, state.quizzes.length - attemptedQuizIds.size);
  const quizCoverage = state.quizzes.length ? Math.round((attemptedQuizIds.size / state.quizzes.length) * 100) : 0;
  const atRiskGoals = state.progress.filter((progress) => isGoalAtRisk(progress));

  return {
    totalTasks,
    completedTasks,
    completionRate,
    reviewCards,
    quizAttempts,
    attemptedQuizIds,
    quizCoverage,
    unattemptedQuizTotal,
    atRiskGoals
  };
}

function isGoalAtRisk(progress) {
  const goal = state.goals.find((item) => item.id === progress.goalId);
  if (!goal || progress.totalTasks === 0) return false;

  const remaining = getRemainingDays(goal.deadline);
  return remaining <= 3 && progress.completionRate < 70;
}

function getProgressStatus(progress) {
  if (progress.totalTasks === 0) return { label: "未规划", level: "neutral" };
  if (progress.completionRate >= 100) return { label: "已完成", level: "good" };
  if (isGoalAtRisk(progress)) return { label: "有风险", level: "risk" };
  return { label: "进行中", level: "active" };
}

function buildProgressAdvice(stats) {
  const advice = [];

  if (state.goals.length === 0) {
    advice.push({
      type: "start",
      title: "先创建一个学习目标",
      text: "进度页会根据目标、任务、打卡、闪卡和测试题自动生成复盘建议。",
      action: "去建目标",
      view: "goals"
    });
    return advice;
  }

  if (stats.atRiskGoals.length > 0) {
    const names = stats.atRiskGoals.slice(0, 2).map((item) => item.goalName).join("、");
    advice.push({
      type: "risk",
      title: "有目标接近截止日期",
      text: `${names} 的剩余时间较少但完成率偏低，下一阶段需要提高这些目标的任务优先级。`,
      action: "查看目标",
      view: "goals"
    });
  }

  if (stats.totalTasks > 0 && stats.completionRate < 50) {
    advice.push({
      type: "task",
      title: "整体任务推进偏慢",
      text: `当前总完成率 ${stats.completionRate}%，建议缩小目标范围或重新生成更可执行的短周期计划。`,
      action: "调整目标",
      view: "goals"
    });
  }

  if (stats.reviewCards.length >= 5) {
    advice.push({
      type: "review",
      title: "复习队列压力偏高",
      text: `当前有 ${stats.reviewCards.length} 张未掌握或新闪卡，说明知识点沉淀压力偏高，下一阶段要增加复习比例。`,
      action: "去复习",
      view: "memory"
    });
  }

  if (stats.unattemptedQuizTotal > 0) {
    advice.push({
      type: "quiz",
      title: "测试覆盖还不充分",
      text: `还有 ${stats.unattemptedQuizTotal} 道测试题未作答，建议用测试结果判断哪些资料需要重新学习。`,
      action: "去测试",
      view: "memory"
    });
  }

  if (advice.length === 0) {
    advice.push({
      type: "good",
      title: "当前学习节奏稳定",
      text: "目标完成、复习压力和测试覆盖没有明显异常，可以继续按当前节奏推进。",
      action: "查看今日",
      view: "today"
    });
  }

  return advice.slice(0, 4);
}

function renderProgressOverview(stats) {
  const rate = Math.min(100, Math.max(0, stats.completionRate));
  document.getElementById("progress-overall-rate").textContent = `${rate}%`;
  document.getElementById("progress-overall-bar").style.width = `${rate}%`;
  document.getElementById("progress-overall-text").textContent = stats.totalTasks
    ? `${stats.completedTasks} / ${stats.totalTasks} 个任务已完成`
    : "创建目标并生成计划后会开始统计。";
  document.getElementById("progress-task-total").textContent = `${stats.completedTasks}/${stats.totalTasks}`;
  document.getElementById("progress-task-text").textContent = stats.totalTasks
    ? `剩余 ${stats.totalTasks - stats.completedTasks} 项任务`
    : "暂无任务";
  document.getElementById("progress-risk-total").textContent = stats.atRiskGoals.length;
  document.getElementById("progress-risk-text").textContent = stats.atRiskGoals.length
    ? "临近截止且完成率偏低"
    : "暂无明显风险";
  document.getElementById("progress-quiz-total").textContent = `${stats.quizCoverage}%`;
  document.getElementById("progress-quiz-text").textContent = state.quizzes.length
    ? `${stats.attemptedQuizIds.size} / ${state.quizzes.length} 道已作答`
    : "暂无测试题";
  document.getElementById("progress-risk-count").textContent = `${stats.atRiskGoals.length} 条风险`;
  document.getElementById("progress-goal-count").textContent = `${state.goals.length} 个目标`;
}

function renderProgressAdvice(stats) {
  const list = document.getElementById("progress-advice-list");
  list.innerHTML = "";

  buildProgressAdvice(stats).forEach((item) => {
    const node = document.createElement("article");
    node.className = `progress-advice-item ${item.type}`;
    node.innerHTML = `
      <div>
        <strong>${escapeHtml(item.title)}</strong>
        <p>${escapeHtml(item.text)}</p>
      </div>
      <button class="ghost-button" type="button">${escapeHtml(item.action)}</button>
    `;
    node.querySelector("button").addEventListener("click", () => switchView(item.view));
    list.appendChild(node);
  });
}

function renderProgressGoals() {
  const list = document.getElementById("progress-list");
  list.innerHTML = "";

  [...state.progress]
    .sort((a, b) => b.completionRate - a.completionRate)
    .forEach((progress) => {
    const goal = state.goals.find((item) => item.id === progress.goalId);
    const remaining = goal ? getRemainingDays(goal.deadline) : "-";
    const status = getProgressStatus(progress);
    const row = document.createElement("div");
    row.className = `progress-row ${status.level}`;
    row.innerHTML = `
      <div class="progress-meta">
        <div>
          <strong>${escapeHtml(progress.goalName)}</strong>
          <p>${goal ? `${escapeHtml(goal.subject)} | 截止 ${escapeHtml(goal.deadline)}` : "目标详情不可用"}</p>
        </div>
        <span>${escapeHtml(status.label)}</span>
      </div>
      <div class="bar"><span style="width:${progress.completionRate}%"></span></div>
      <div class="progress-row-stats">
        <div><span>总进度</span><strong>${progress.completionRate}%</strong></div>
        <div><span>任务</span><strong>${progress.completedTasks}/${progress.totalTasks}</strong></div>
        <div><span>剩余</span><strong>${remaining} 天</strong></div>
        <div><span>节奏</span><strong>${progress.totalTasks ? status.label : "待规划"}</strong></div>
      </div>
      <div class="tag-row">
        <span class="tag">剩余 ${remaining} 天</span>
        ${goal ? `<span class="tag">每天 ${goal.dailyMinutes} 分钟</span>` : ""}
      </div>
      <div class="inline-actions">
        <button class="ghost-button" data-goal-id="${escapeHtml(progress.goalId)}">查看详情</button>
      </div>
    `;
    row.querySelector("button").addEventListener("click", () => {
      selectGoal(progress.goalId);
      switchView("goals");
    });
    list.appendChild(row);
  });
}

function renderProgress() {
  const stats = getProgressStats();
  renderProgressOverview(stats);
  renderProgressAdvice(stats);
  renderProgressGoals();

  const list = document.getElementById("progress-list");
  if (state.progress.length === 0) {
    list.innerHTML = "";
    list.appendChild(emptyNode("暂无进度", "创建目标并完成任务后会生成进度。"));
  }
}
