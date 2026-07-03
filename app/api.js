const API_BASE_URL = "http://127.0.0.1:8000/api";
const API_AUTH_STORAGE_KEY = "student-assistant-auth";

async function request(path, options = {}) {
  const userId = getCurrentApiUserId();
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(userId ? { "X-User-Id": userId } : {}),
      ...(options.headers || {})
    }
  });
  const result = await response.json();

  if (!response.ok) {
    throw new Error(result.detail || result.message || "请求失败");
  }

  return result.data;
}

function getCurrentApiUserId() {
  const raw = localStorage.getItem(API_AUTH_STORAGE_KEY);
  if (!raw) return "";

  try {
    const user = JSON.parse(raw);
    return user && user.id ? user.id : "";
  } catch {
    return "";
  }
}

const authApi = {
  register(payload) {
    return request("/auth/register", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  login(payload) {
    return request("/auth/login", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  }
};

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

const agentApi = {
  ask(payload) {
    return request("/agent/ask", {
      method: "POST",
      body: JSON.stringify(payload)
    });
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
  },

  generateChunks(materialId) {
    return request(`/materials/${materialId}/chunks`, {
      method: "POST"
    });
  },

  listChunks(materialId) {
    return request(`/materials/${materialId}/chunks`);
  },

  listQaRecords(materialId) {
    return request(`/materials/${materialId}/qa`);
  },

  searchChunks(query, limit = 5) {
    const params = new URLSearchParams({
      query,
      limit: String(limit)
    });
    return request(`/materials/search?${params.toString()}`);
  }
};
