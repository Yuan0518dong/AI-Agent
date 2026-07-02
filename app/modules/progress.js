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

function renderProgress() {
  const list = document.getElementById("progress-list");
  list.innerHTML = "";

  if (state.progress.length === 0) {
    list.appendChild(emptyNode("暂无进度", "创建目标并完成任务后会生成进度。"));
    return;
  }

  [...state.progress]
    .sort((a, b) => b.completionRate - a.completionRate)
    .forEach((progress) => {
    const goal = state.goals.find((item) => item.id === progress.goalId);
    const remaining = goal ? getRemainingDays(goal.deadline) : "-";
    const row = document.createElement("div");
    row.className = "progress-row";
    row.innerHTML = `
      <div class="progress-meta">
        <strong>${escapeHtml(progress.goalName)}</strong>
        <span>${progress.completionRate}%</span>
      </div>
      <div class="bar"><span style="width:${progress.completionRate}%"></span></div>
      <p>${progress.completedTasks}/${progress.totalTasks} 个任务已完成，今日 ${progress.todayCompleted}/${progress.todayTotal}</p>
      <div class="tag-row">
        <span class="tag">剩余 ${remaining} 天</span>
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
