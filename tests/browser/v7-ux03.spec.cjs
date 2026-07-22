const { test, expect } = require("@playwright/test");
const AxeBuilder = require("@axe-core/playwright").default;

const ORIGINAL_GOAL = "完成一周 AI Agent 学习计划";

async function waitForTodayActions(page) {
  await expect(page.locator("#today-actions-count")).not.toHaveText("加载中", { timeout: 15_000 });
  await expect(page.locator("#today-actions-count")).not.toHaveText("读取失败", { timeout: 15_000 });
}

async function openToday(page) {
  const actionResponse = page.waitForResponse((response) => {
    return new URL(response.url()).pathname === "/api/today/actions"
      && response.request().method() === "GET"
      && response.ok();
  });
  await page.locator(".desktop-nav [data-view=today]").click();
  await actionResponse;
  await waitForTodayActions(page);
}

async function assertNoSeriousAccessibilityViolations(page) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  const serious = results.violations.filter((violation) => ["serious", "critical"].includes(violation.impact));
  expect(serious.flatMap((violation) => violation.nodes.map(
    (node) => `${violation.id} ${node.target.join(" ")}: ${node.failureSummary}`
  ))).toEqual([]);
}

function actionOpenButton(page, label) {
  return page.locator(".today-action-item").filter({ hasText: label }).first().getByRole("button", { name: "查看" });
}

test("UX-03 keeps Dashboard independent when Today Actions fails and retries without Agent Context", async ({ page }) => {
  const startupRequests = [];
  const pageErrors = [];
  const consoleErrors = [];
  let recordStartup = true;
  let failOnce = true;

  page.on("request", (request) => {
    if (!recordStartup || !request.url().includes("/api/")) return;
    startupRequests.push({ method: request.method(), path: new URL(request.url()).pathname });
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  await page.route("**/api/today/actions**", async (route) => {
    if (!failOnce) return route.continue();
    failOnce = false;
    return route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ code: 1, error: { type: "today_actions_unavailable", message: "temporary failure" } })
    });
  });

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await page.locator("#demo-login").click();
  await expect(page.locator("#view-today")).toHaveClass(/active/);
  await expect(page.locator("#dashboard-content")).toBeVisible();
  await expect(page.locator("#today-actions-count")).toHaveText("读取失败");
  await expect(page.locator("#today-actions-list")).toContainText("不会影响上方 Dashboard");
  recordStartup = false;

  const forbiddenStartupPaths = startupRequests.filter((request) => [
    "/api/agent/context",
    "/api/agent/decide",
    "/api/agent/ask"
  ].includes(request.path) || request.path.startsWith("/api/agent/runs"));
  expect(forbiddenStartupPaths).toEqual([]);
  expect(startupRequests.some((request) => request.path === "/api/dashboard" && request.method === "GET")).toBeTruthy();
  expect(startupRequests.some((request) => request.path === "/api/today/actions" && request.method === "GET")).toBeTruthy();

  await page.getByRole("button", { name: "重试" }).click();
  await waitForTodayActions(page);
  await expect(page.locator("#dashboard-content")).toBeVisible();

  expect(pageErrors).toEqual([]);
  expect(consoleErrors.filter((message) => {
    return !message.includes("status of 401 (Unauthorized)")
      && !message.includes("status of 503 (Service Unavailable)");
  })).toEqual([]);
});

test("UX-03 routes all five Today Action categories without automatic writes", async ({ page }) => {
  const pageErrors = [];
  const consoleErrors = [];
  const actionWrites = [];
  let recordActionWrites = false;

  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("request", (request) => {
    if (!recordActionWrites || !request.url().includes("/api/")) return;
    if (!["GET", "HEAD", "OPTIONS"].includes(request.method())) {
      actionWrites.push(`${request.method()} ${new URL(request.url()).pathname}`);
    }
  });

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await page.locator("#demo-login").click();
  await waitForTodayActions(page);

  await page.locator(".desktop-nav [data-view=goals]").click();
  await page.locator("#goal-form [name=name]").fill("UX-03 今日任务夹具");
  await page.locator("#goal-form [name=subject]").fill("行动路由");
  await page.locator("#goal-form [name=deadline]").fill("2026-12-31");
  await page.locator("#goal-form [name=notes]").fill("为 Today Actions 生成今天的任务。" );
  await page.locator("#goal-submit-button").click();
  await expect(page.locator("#goal-list")).toContainText("UX-03 今日任务夹具");

  await page.locator(".desktop-nav [data-view=memory]").click();
  const quizForm = page.locator(".quiz-answer-form").first();
  await expect(quizForm).toBeVisible();
  await quizForm.locator("textarea[name=answer]").fill("香蕉");
  await quizForm.getByRole("button", { name: "提交批改" }).click();
  await expect(page.locator("#toast")).toContainText("AI 批改完成");

  await page.locator(".desktop-nav [data-view=agent]").click();
  await page.locator("#agent-goal-select").selectOption({ label: ORIGINAL_GOAL });
  await expect(page.locator("#toast")).toContainText("学习目标已切换");
  await page.locator("#agent-run-objective").fill("基于当前错题生成复习闪卡草稿。" );
  await page.locator("#agent-run-start").click();
  await expect(page.locator("#toast")).toContainText("已完成第一步");
  const details = page.locator(".agent-run-details");
  if (!(await details.evaluate((node) => node.open))) await details.locator(":scope > summary").click();
  await page.locator("#agent-current-action").getByRole("button", { name: "执行下一步" }).click();
  await expect(page.locator("#agent-run-detail")).toContainText("等待确认");

  await openToday(page);
  await expect(page.locator(".today-action-item").filter({ hasText: "逾期任务" })).toHaveCount(3);
  await expect(page.locator(".today-action-item").filter({ hasText: "今日任务" })).toHaveCount(1);
  await expect(page.locator(".today-action-item").filter({ hasText: "到期闪卡" })).toHaveCount(2);
  await expect(page.locator(".today-action-item").filter({ hasText: "待巩固薄弱点" })).toHaveCount(1);
  await expect(page.locator(".today-action-item").filter({ hasText: "待处理助手确认" })).toHaveCount(1);

  recordActionWrites = true;
  await actionOpenButton(page, "逾期任务").click();
  await expect(page.locator("#view-goals")).toHaveClass(/active/);
  await expect(page.locator("#goal-detail [data-task-id][tabindex='-1']")).toBeFocused();
  recordActionWrites = false;
  await openToday(page);

  recordActionWrites = true;
  await actionOpenButton(page, "今日任务").click();
  await expect(page.locator("#view-goals")).toHaveClass(/active/);
  await expect(page.locator("#goal-detail [data-task-id][tabindex='-1']")).toBeFocused();
  recordActionWrites = false;
  await openToday(page);

  recordActionWrites = true;
  await actionOpenButton(page, "到期闪卡").click();
  await expect(page.locator("#view-memory")).toHaveClass(/active/);
  await expect(page.locator("#flashcard")).toHaveAttribute("data-flashcard-id", /flashcard_/);
  await expect(page.locator("#flashcard")).toBeFocused();
  recordActionWrites = false;
  await openToday(page);

  recordActionWrites = true;
  await actionOpenButton(page, "待巩固薄弱点").click();
  await expect(page.locator("#view-memory")).toHaveClass(/active/);
  await expect(page.locator("[data-quiz-id]").filter({ has: page.locator("textarea") }).first()).toBeFocused();
  recordActionWrites = false;
  await openToday(page);

  recordActionWrites = true;
  await actionOpenButton(page, "待处理助手确认").click();
  await expect(page.locator("#view-agent")).toHaveClass(/active/);
  await expect(page.locator(".agent-run-row.active")).toBeFocused();
  recordActionWrites = false;

  expect(actionWrites).toEqual([]);
  await openToday(page);
  await page.setViewportSize({ width: 390, height: 844 });
  const widths = await page.evaluate(() => ({
    viewport: window.innerWidth,
    document: document.documentElement.scrollWidth,
    body: document.body.scrollWidth
  }));
  expect(widths.document).toBeLessThanOrEqual(widths.viewport);
  expect(widths.body).toBeLessThanOrEqual(widths.viewport);
  await assertNoSeriousAccessibilityViolations(page);
  await page.screenshot({ path: "docs/images/ux03-today-actions-mobile.png", fullPage: true });

  expect(pageErrors).toEqual([]);
  expect(consoleErrors.filter((message) => !message.includes("status of 401 (Unauthorized)"))).toEqual([]);
});
