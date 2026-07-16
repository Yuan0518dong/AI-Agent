// utils module extracted from app.js.

function showError(error) {
  const status = Number(error?.status || 0);

  if (status === 401) {
    const sessionEnded = typeof handleUnauthorizedSession === "function" && handleUnauthorizedSession();
    showToast(sessionEnded ? "登录状态已失效，请重新登录。" : "邮箱或密码不正确，请重试。", "error");
    return;
  }

  if (status === 403) {
    showToast("当前操作未被允许，请刷新页面后重试。", "error");
    return;
  }

  if (status === 429) {
    const retryAfter = Number(error?.retryAfter);
    const waitMessage = Number.isFinite(retryAfter) && retryAfter > 0
      ? `请求过于频繁，请在 ${retryAfter} 秒后重试。`
      : "请求过于频繁，请稍后重试。";
    showToast(waitMessage, "error");
    return;
  }

  console.error(error);
  showToast(error?.message || "操作失败，请确认服务连接后重试。", "error");
}

function showSuccess(message) {
  showToast(message, "success");
}

function showToast(message, type = "success") {
  const toast = document.getElementById("toast");
  toast.textContent = message;
  toast.className = `toast show ${type}`;
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => {
    toast.className = "toast";
  }, 2400);
}

function setButtonLoading(button, loading, loadingText = "处理中") {
  if (!button) return;

  if (loading) {
    button.dataset.originalText = button.textContent;
    button.textContent = loadingText;
    button.disabled = true;
    return;
  }

  button.textContent = button.dataset.originalText || button.textContent;
  button.disabled = false;
  delete button.dataset.originalText;
}

function emptyNode(title, body) {
  const template = document.getElementById("empty-template");
  const node = template.content.firstElementChild.cloneNode(true);
  node.querySelector("strong").textContent = title;
  node.querySelector("p").textContent = body;
  return node;
}

function splitSentences(text) {
  return text
    .replace(/\s+/g, " ")
    .split(/[。！？!?；;\n]/)
    .map((item) => item.trim())
    .filter((item) => item.length > 2);
}

function daysUntil(dateString) {
  const end = new Date(dateString);
  const today = new Date();
  const diff = end.getTime() - today.getTime();
  return Math.ceil(diff / 86400000);
}

function offsetDate(days) {
  const date = new Date();
  date.setDate(date.getDate() + days);
  return date.toISOString().slice(0, 10);
}

function todayString() {
  const date = new Date();
  date.setMinutes(date.getMinutes() - date.getTimezoneOffset());
  return date.toISOString().slice(0, 10);
}

function getRemainingDays(dateString) {
  if (!dateString) return "-";
  return Math.max(0, daysUntil(dateString));
}

function formatDateTime(value) {
  if (!value) return "";
  return new Date(value).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  });
}

function makeId() {
  return crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function normalizeArray(value, fallback) {
  return Array.isArray(value) && value.length ? value : fallback;
}
