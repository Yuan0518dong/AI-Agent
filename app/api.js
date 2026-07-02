const API_BASE_URL = "http://127.0.0.1:8000/api";

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    }
  });
  const result = await response.json();

  if (!response.ok) {
    throw new Error(result.detail || result.message || "请求失败");
  }

  return result.data;
}

const goalApi = {
  listGoals() {
    return request("/goals");
  },

  createGoal(payload) {
    return request("/goals", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  getGoal(goalId) {
    return request(`/goals/${goalId}`);
  },

  updateGoal(goalId, payload) {
    return request(`/goals/${goalId}`, {
      method: "PUT",
      body: JSON.stringify(payload)
    });
  },

  deleteGoal(goalId) {
    return request(`/goals/${goalId}`, {
      method: "DELETE"
    });
  },

  generatePlan(goalId, days) {
    return request(`/goals/${goalId}/plans`, {
      method: "POST",
      body: JSON.stringify({
        days,
        regenerate: true
      })
    });
  },

  listGoalTasks(goalId) {
    return request(`/goals/${goalId}/tasks`);
  },

  listTodayTasks(date) {
    const query = date ? `?date=${encodeURIComponent(date)}` : "";
    return request(`/tasks/today${query}`);
  },

  checkinTask(taskId, done) {
    return request(`/tasks/${taskId}/checkin`, {
      method: "POST",
      body: JSON.stringify({ done })
    });
  },

  listProgress() {
    return request("/progress");
  },

  getGoalProgress(goalId) {
    return request(`/progress/${goalId}`);
  }
};

const materialApi = {
  listMaterials(goalId = "") {
    const query = goalId ? `?goalId=${encodeURIComponent(goalId)}` : "";
    return request(`/materials${query}`);
  },

  createMaterial(payload) {
    return request("/materials", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  updateMaterial(materialId, payload) {
    return request(`/materials/${materialId}`, {
      method: "PUT",
      body: JSON.stringify(payload)
    });
  },

  deleteMaterial(materialId) {
    return request(`/materials/${materialId}`, {
      method: "DELETE"
    });
  },

  summarizeMaterial(materialId) {
    return request(`/materials/${materialId}/summarize`, {
      method: "POST"
    });
  },

  getSummary(materialId) {
    return request(`/materials/${materialId}/summary`);
  },

  listFlashcards(materialId) {
    return request(`/materials/${materialId}/flashcards`);
  },

  generateFlashcards(materialId) {
    return request(`/materials/${materialId}/flashcards`, {
      method: "POST"
    });
  },

  listQuiz(materialId) {
    return request(`/materials/${materialId}/quiz`);
  },

  generateQuiz(materialId) {
    return request(`/materials/${materialId}/quiz`, {
      method: "POST"
    });
  }
};
