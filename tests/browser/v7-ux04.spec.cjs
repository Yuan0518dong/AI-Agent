const { test, expect } = require("@playwright/test");
const AxeBuilder = require("@axe-core/playwright").default;

const ORIGINAL_GOAL = "完成一周 AI Agent 学习计划";

test("UX-04 keeps the current agent action readable without generating a Decision or advancing on load", async ({ page }) => {
  const pageErrors = [];
  const consoleErrors = [];
  const agentLoadRequests = [];
  const deferredWrites = [];
  let recordAgentLoad = false;
  let recordDeferredWrites = false;

  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("request", (request) => {
    if (!request.url().includes("/api/")) return;
    const event = { method: request.method(), path: new URL(request.url()).pathname };
    if (recordAgentLoad) agentLoadRequests.push(event);
    if (recordDeferredWrites && !["GET", "HEAD", "OPTIONS"].includes(event.method)) {
      deferredWrites.push(`${event.method} ${event.path}`);
    }
  });

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await page.locator("#demo-login").click();

  await page.locator(".desktop-nav [data-view=memory]").click();
  const quizForm = page.locator(".quiz-answer-form").first();
  await expect(quizForm).toBeVisible();
  await quizForm.locator("textarea[name=answer]").fill("香蕉");
  await quizForm.getByRole("button", { name: "提交批改" }).click();
  await expect(page.locator("#toast")).toContainText("AI 批改完成");

  recordAgentLoad = true;
  await page.locator(".desktop-nav [data-view=agent]").click();
  await expect(page.locator("#view-agent")).toHaveClass(/active/);
  await expect(page.locator("#agent-current-action")).toBeVisible();
  await expect(page.locator(".agent-run-details")).not.toHaveAttribute("open", "");
  await expect(page.locator("#agent-goal-select")).toHaveValue(/.+/);
  recordAgentLoad = false;

  expect(agentLoadRequests.some((request) => request.path === "/api/agent/decide")).toBeFalsy();
  expect(agentLoadRequests.some((request) => {
    return request.path.startsWith("/api/agent/runs") && request.method !== "GET";
  })).toBeFalsy();

  await page.locator("#agent-goal-select").selectOption({ label: ORIGINAL_GOAL });
  await expect(page.locator("#toast")).toContainText("学习目标已切换");

  await page.locator("#agent-run-objective").fill("基于当前错题生成复习闪卡草稿。");
  await page.locator("#agent-run-start").click();
  const currentAction = page.locator("#agent-current-action");
  await expect(currentAction).toContainText("当前行动");
  await expect(currentAction).toContainText("为什么现在做");
  await expect(currentAction).toContainText("学习依据");
  await expect(currentAction).toContainText("运行状态");
  await expect(currentAction).toContainText("模式：");
  await expect(currentAction).toContainText("安全检查：");
  await expect(page.locator(".agent-run-details")).not.toHaveAttribute("open", "");

  await currentAction.getByRole("button", { name: "执行下一步" }).click();
  await expect(currentAction).toContainText("等待确认");
  await expect(currentAction).toContainText("等待你确认");
  await expect(currentAction.locator("[data-current-confirmation]")).toHaveCount(2);
  await expect(currentAction.locator("[data-current-confirmation=accepted]")).toHaveText("接受");
  await expect(currentAction.locator("[data-current-confirmation=rejected]")).toHaveText("拒绝");
  await expect(currentAction.getByRole("button", { name: "暂不处理" })).toBeVisible();

  recordDeferredWrites = true;
  await currentAction.getByRole("button", { name: "暂不处理" }).click();
  await expect(currentAction).toContainText("已暂时收起当前提醒");
  expect(deferredWrites).toEqual([]);
  recordDeferredWrites = false;

  await currentAction.getByRole("button", { name: "继续查看" }).click();
  await expect(currentAction).toContainText("等待你确认");
  await page.screenshot({ path: "docs/images/ux04-agent-current-action-desktop.png", fullPage: true });

  await page.setViewportSize({ width: 390, height: 844 });
  const widths = await page.evaluate(() => ({
    viewport: window.innerWidth,
    document: document.documentElement.scrollWidth,
    body: document.body.scrollWidth
  }));
  expect(widths.document).toBeLessThanOrEqual(widths.viewport);
  expect(widths.body).toBeLessThanOrEqual(widths.viewport);
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  const serious = results.violations.filter((violation) => ["serious", "critical"].includes(violation.impact));
  expect(serious.flatMap((violation) => violation.nodes.map(
    (node) => `${violation.id} ${node.target.join(" ")}: ${node.failureSummary}`
  ))).toEqual([]);
  await page.screenshot({ path: "docs/images/ux04-agent-current-action-mobile.png", fullPage: true });

  expect(pageErrors).toEqual([]);
  expect(consoleErrors.filter((message) => !message.includes("status of 401 (Unauthorized)"))).toEqual([]);
});
