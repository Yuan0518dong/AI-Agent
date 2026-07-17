const API_BASE_URL = "/api";

class ApiError extends Error {
  constructor({ status = 0, type = "request_failed", message = "请求失败", fieldErrors = null, requestId = "", retryAfter = null }) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.type = type;
    this.fieldErrors = fieldErrors;
    this.requestId = requestId;
    this.retryAfter = retryAfter;
  }
}

async function request(path, options = {}) {
  const { headers: requestHeaders, ...fetchOptions } = options;
  const headers = new Headers(requestHeaders || {});

  if (typeof fetchOptions.body === "string" && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  let response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...fetchOptions,
      credentials: "same-origin",
      headers
    });
  } catch (error) {
    throw new ApiError({
      type: "network_error",
      message: "无法连接服务，请检查网络后重试。"
    });
  }

  const result = await readResponseBody(response);
  if (!response.ok || (result && typeof result === "object" && result.code !== undefined && result.code !== 0)) {
    throw createApiError(response, result);
  }

  return result && typeof result === "object" && Object.prototype.hasOwnProperty.call(result, "data")
    ? result.data
    : result;
}

async function readResponseBody(response) {
  const text = await response.text();
  if (!text) return null;

  try {
    return JSON.parse(text);
  } catch {
    return { message: "服务返回了无法识别的响应。" };
  }
}

function createApiError(response, payload) {
  const payloadObject = asRecord(payload) || {};
  const detail = asRecord(payloadObject.error) || asRecord(payloadObject.detail) || payloadObject;
  const fallbackDetail = typeof payloadObject.detail === "string" ? payloadObject.detail : "";
  const fieldErrors = detail.fieldErrors || detail.fields || payloadObject.fieldErrors || payloadObject.fields || (Array.isArray(payloadObject.detail) ? payloadObject.detail : null);
  const retryAfter = parseRetryAfter(response.headers.get("Retry-After"))
    ?? parseRetryAfter(detail.retryAfter ?? detail.retryAfterSeconds ?? payloadObject.retryAfter ?? payloadObject.retryAfterSeconds);

  return new ApiError({
    status: response.status,
    type: detail.type || detail.errorType || payloadObject.type || payloadObject.errorType || "request_failed",
    message: detail.userMessage || detail.message || payloadObject.userMessage || payloadObject.message || fallbackDetail || "请求失败",
    fieldErrors,
    requestId: detail.requestId || payloadObject.requestId || response.headers.get("X-Request-Id") || "",
    retryAfter
  });
}

function asRecord(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : null;
}

function parseRetryAfter(value) {
  if (value === null || value === undefined || value === "") return null;

  const seconds = Number(value);
  if (Number.isFinite(seconds) && seconds >= 0) {
    return Math.ceil(seconds);
  }

  const retryAt = Date.parse(value);
  if (Number.isNaN(retryAt)) return null;
  return Math.max(0, Math.ceil((retryAt - Date.now()) / 1000));
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
  },

  demo() {
    return request("/auth/demo", {
      method: "POST"
    });
  },

  me() {
    return request("/auth/me");
  },

  logout() {
    return request("/auth/logout", {
      method: "POST"
    });
  },

  exportData() {
    return request("/auth/export");
  },

  deleteAccount() {
    return request("/auth/account", {
      method: "DELETE",
      body: JSON.stringify({ confirmation: "DELETE" })
    });
  }
};

const dashboardApi = {
  getDashboard(date = "") {
    const query = date ? `?date=${encodeURIComponent(date)}` : "";
    return request(`/dashboard${query}`);
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
  },

  getContext(goalId = "") {
    const query = goalId ? `?goalId=${encodeURIComponent(goalId)}` : "";
    return request(`/agent/context${query}`);
  },

    decide(goalId = "", decisionMode = "hybrid") {
      const params = new URLSearchParams({ decisionMode });
      if (goalId) {
        params.set("goalId", goalId);
      }
      return request(`/agent/decide?${params.toString()}`, {
        method: "POST"
      });
    },

    listTools() {
      return request("/agent/tools");
    },
  
    listActionLogs(goalId = "", limit = 20) {
    const params = new URLSearchParams({ limit: String(limit) });
    if (goalId) {
      params.set("goalId", goalId);
    }
    return request(`/agent/action-logs?${params.toString()}`);
  },

  createActionLog(payload) {
    return request("/agent/action-logs", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  updateActionLog(logId, payload) {
    return request(`/agent/action-logs/${logId}`, {
      method: "PATCH",
      body: JSON.stringify(payload)
    });
  },

  createRun(payload) {
    return request("/agent/runs", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  listRuns(goalId = "", limit = 20) {
    const params = new URLSearchParams({ limit: String(limit) });
    if (goalId) {
      params.set("goalId", goalId);
    }
    return request(`/agent/runs?${params.toString()}`);
  },

  getRun(runId) {
    return request(`/agent/runs/${runId}`);
  },

  executeRun(runId, maxSteps = null) {
    return request(`/agent/runs/${runId}/execute`, {
      method: "POST",
      body: JSON.stringify(maxSteps ? { maxSteps } : {})
    });
  },

  advanceRun(runId) {
    return request(`/agent/runs/${runId}/advance`, {
      method: "POST",
      body: "{}"
    });
  },

  updateRun(runId, status) {
    return request(`/agent/runs/${runId}`, {
      method: "PATCH",
      body: JSON.stringify({ status })
    });
  },

  cancelRun(runId) {
    return request(`/agent/runs/${runId}/cancel`, {
      method: "POST",
      body: "{}"
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

  uploadMaterial(formData) {
    return request("/materials/upload", {
      method: "POST",
      body: formData
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

  createFlashcard(materialId, payload) {
    return request(`/materials/${materialId}/flashcards/custom`, {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  updateFlashcard(materialId, flashcardId, payload) {
    return request(`/materials/${materialId}/flashcards/${flashcardId}`, {
      method: "PATCH",
      body: JSON.stringify(payload)
    });
  },

  listQuiz(materialId) {
    return request(`/materials/${materialId}/quiz`);
  },

  generateQuiz(materialId, count = 5) {
    return request(`/materials/${materialId}/quiz?count=${encodeURIComponent(String(count))}`, {
      method: "POST"
    });
  },

  listQuizAttempts(materialId) {
    return request(`/materials/${materialId}/quiz/attempts`);
  },

  submitQuizAnswer(materialId, quizId, answer) {
    return request(`/materials/${materialId}/quiz/${quizId}/answer`, {
      method: "POST",
      body: JSON.stringify({ answer })
    });
  },

  generateChunks(materialId) {
    return request(`/materials/${materialId}/chunks`, {
      method: "POST"
    });
  },

  retryProcessingStage(materialId, stage) {
    return request(`/materials/${materialId}/processing/${encodeURIComponent(stage)}/retry`, {
      method: "POST",
      body: "{}"
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
