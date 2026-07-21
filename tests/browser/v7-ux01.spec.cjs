const { test, expect } = require("@playwright/test");

const ORIGINAL_GOAL = "完成一周 AI Agent 学习计划";
const SECOND_GOAL = "UX-01 范围隔离目标";
const SECOND_MATERIAL = "UX-01 其他目标资料";

function readStoredState(page) {
  return page.evaluate(() => JSON.parse(localStorage.getItem("student-assistant-mvp") || "{}"));
}

async function reloadAfterDashboard(page) {
  const dashboardLoaded = page.waitForResponse((response) => {
    return response.url().includes("/api/dashboard") && response.request().method() === "GET" && response.ok();
  });
  await page.reload();
  await dashboardLoaded;
}

async function openLearningSpaceAfterReload(page, selectedGoalId = "") {
  const paths = ["/api/goals", "/api/tasks/today", "/api/progress", "/api/dashboard"];
  if (selectedGoalId) {
    paths.push(`/api/goals/${selectedGoalId}`, `/api/goals/${selectedGoalId}/tasks`, `/api/progress/${selectedGoalId}`);
  }
  const responses = paths.map((path) => page.waitForResponse((response) => {
    return new URL(response.url()).pathname === path && response.request().method() === "GET" && response.ok();
  }));
  await page.locator(".desktop-nav [data-view=goals]").click();
  await Promise.all(responses);
}

async function returnToLearningSpace(page) {
  await page.locator(".desktop-nav [data-view=goals]").click();
  await expect(page.locator("#view-goals")).toHaveClass(/active/);
  await expect(page.locator("#workspace-shortcuts")).toBeVisible();
}

test("UX-01 keeps workspace shortcuts inside the selected goal and revalidates saved selection", async ({ page }) => {
  const apiRequests = [];
  const pageErrors = [];
  const consoleErrors = [];
  let recordWorkspaceRequests = false;

  page.on("request", (request) => {
    if (!recordWorkspaceRequests || !request.url().includes("/api/")) return;
    apiRequests.push({ method: request.method(), path: new URL(request.url()).pathname });
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await page.locator("#demo-login").click();
  await page.locator(".desktop-nav [data-view=goals]").click();
  await expect(page.locator("#page-title")).toHaveText("学习空间");
  await expect(page.locator("#goal-detail")).toContainText(ORIGINAL_GOAL);
  await expect(page.locator("#workspace-shortcuts [data-workspace-destination]")).toHaveCount(5);

  await page.locator("#goal-form [name=name]").fill(SECOND_GOAL);
  await page.locator("#goal-form [name=subject]").fill("范围隔离");
  await page.locator("#goal-form [name=deadline]").fill("2026-12-31");
  await page.locator("#goal-form [name=notes]").fill("验证学习空间只展示当前目标的数据。");
  await page.locator("#goal-submit-button").click();
  await expect(page.locator("#goal-detail")).toContainText(SECOND_GOAL);

  await page.locator(".desktop-nav [data-view=materials]").click();
  await page.locator("#material-form [name=title]").fill(SECOND_MATERIAL);
  await page.locator("#material-form [name=content]").fill("这份资料只能在第二个学习目标的范围内出现。");
  await page.locator("#material-submit-button").click();
  await expect(page.locator("#material-list")).toContainText(SECOND_MATERIAL);

  await page.locator(".desktop-nav [data-view=goals]").click();
  const originalGoalRow = page.locator("#goal-list .item").filter({ hasText: ORIGINAL_GOAL });
  await originalGoalRow.getByRole("button", { name: "详情" }).click();
  await expect(page.locator("#goal-detail")).toContainText(ORIGINAL_GOAL);
  const selectedGoalId = (await readStoredState(page)).selectedGoalId;
  expect(selectedGoalId).toBeTruthy();

  recordWorkspaceRequests = true;
  const shortcuts = page.locator("#workspace-shortcuts");

  await shortcuts.locator("[data-workspace-destination=materials]").click();
  await expect(page.locator("#view-materials")).toHaveClass(/active/);
  await expect(page.locator("#materials-scope-note")).toHaveText(`当前学习空间：${ORIGINAL_GOAL}`);
  await expect(page.locator("#material-list")).toContainText("Agent Runtime 演示资料");
  await expect(page.locator("#material-list")).not.toContainText(SECOND_MATERIAL);
  await expect(page.locator("#material-list")).toBeFocused();

  await returnToLearningSpace(page);
  await shortcuts.locator("[data-workspace-destination=study]").click();
  await expect(page.locator("#view-study")).toHaveClass(/active/);
  await expect(page.locator("#study-scope-note")).toHaveText(`当前学习空间：${ORIGINAL_GOAL}`);
  await expect(page.locator('#chat-form input[name="question"]')).toBeFocused();

  await returnToLearningSpace(page);
  await shortcuts.locator("[data-workspace-destination=quiz]").click();
  await expect(page.locator("#view-memory")).toHaveClass(/active/);
  await expect(page.locator("#memory-scope-note")).toHaveText(`当前学习空间：${ORIGINAL_GOAL}`);
  await expect(page.locator("#quiz-list")).toBeFocused();

  await returnToLearningSpace(page);
  await shortcuts.locator("[data-workspace-destination=review]").click();
  await expect(page.locator("#flashcard")).toBeFocused();

  await returnToLearningSpace(page);
  await shortcuts.locator("[data-workspace-destination=progress]").click();
  await expect(page.locator("#view-progress")).toHaveClass(/active/);
  await expect(page.locator("#progress-scope-note")).toHaveText(`当前学习空间：${ORIGINAL_GOAL}`);
  await expect(page.locator("#progress-overview")).toBeFocused();

  expect(apiRequests.every((request) => request.method === "GET"), JSON.stringify(apiRequests)).toBeTruthy();
  expect(apiRequests.map((request) => request.path)).not.toContain("/api/agent/decide");
  expect(apiRequests.some((request) => request.path.includes("/agent/runs") && request.method !== "GET")).toBeFalsy();

  await reloadAfterDashboard(page);
  await openLearningSpaceAfterReload(page, selectedGoalId);
  await expect(page.locator("#goal-detail")).toContainText(ORIGINAL_GOAL);
  expect((await readStoredState(page)).selectedGoalId).toBe(selectedGoalId);

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator("#workspace-shortcuts [data-workspace-destination]")).toHaveCount(5);
  const mobileWidths = await page.evaluate(() => ({
    viewport: window.innerWidth,
    document: document.documentElement.scrollWidth,
    body: document.body.scrollWidth
  }));
  expect(mobileWidths.document).toBeLessThanOrEqual(mobileWidths.viewport);
  expect(mobileWidths.body).toBeLessThanOrEqual(mobileWidths.viewport);
  await page.screenshot({ path: "docs/images/ux01-learning-space-mobile.png", fullPage: true });
  await page.setViewportSize({ width: 1440, height: 900 });

  await page.evaluate(() => {
    const key = "student-assistant-mvp";
    const state = JSON.parse(localStorage.getItem(key) || "{}");
    state.selectedGoalId = "missing-goal";
    localStorage.setItem(key, JSON.stringify(state));
  });
  await reloadAfterDashboard(page);
  await openLearningSpaceAfterReload(page);
  await expect(page.locator("#goal-detail")).toContainText("选择一个学习目标");
  await expect(page.locator("#workspace-shortcuts")).toHaveCount(0);
  expect((await readStoredState(page)).selectedGoalId).toBe("");

  expect(pageErrors).toEqual([]);
  const unexpectedConsoleErrors = consoleErrors.filter((message) => !message.includes("status of 401 (Unauthorized)"));
  expect(unexpectedConsoleErrors).toEqual([]);
});
