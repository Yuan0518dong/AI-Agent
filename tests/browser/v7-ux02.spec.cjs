const { test, expect } = require("@playwright/test");
const AxeBuilder = require("@axe-core/playwright").default;

const DESKTOP_NAV = [
  ["today", "今日"],
  ["goals", "学习目标"],
  ["materials", "资料"],
  ["study", "问答"],
  ["agent", "智能助手"],
  ["memory", "复习"],
  ["progress", "进度"]
];

test("UX-02 keeps desktop and mobile navigation copy, selection, and ARIA in sync", async ({ page }) => {
  const pageErrors = [];
  const consoleErrors = [];
  const navigationWrites = [];
  let recordNavigationWrites = false;

  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("request", (request) => {
    if (!recordNavigationWrites || !request.url().includes("/api/")) return;
    if (!["GET", "HEAD", "OPTIONS"].includes(request.method())) {
      navigationWrites.push(`${request.method()} ${new URL(request.url()).pathname}`);
    }
  });

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await page.locator("#demo-login").click();
  recordNavigationWrites = true;

  for (const [view, label] of DESKTOP_NAV) {
    const item = page.locator(`.desktop-nav [data-view=${view}]`);
    await expect(item).toContainText(label);
    await item.click();
    await expect(page.locator(`#view-${view}`)).toHaveClass(/active/);
    await expect(item).toHaveClass(/active/);
    await expect(item).toHaveAttribute("aria-current", "page");
    const inactiveItemsHaveCurrent = await page.locator(`.desktop-nav .nav-item:not([data-view=${view}])`).evaluateAll(
      (items) => items.some((candidate) => candidate.getAttribute("aria-current") === "page")
    );
    expect(inactiveItemsHaveCurrent).toBeFalsy();
  }
  await page.screenshot({ path: "docs/images/ux02-desktop-navigation.png", fullPage: true });

  await page.setViewportSize({ width: 390, height: 844 });
  const mobileNav = page.locator(".mobile-bottom-nav");
  await expect(mobileNav).toBeVisible();
  for (const [view, label] of DESKTOP_NAV.slice(0, 3)) {
    await expect(mobileNav.locator(`[data-view=${view}]`)).toContainText(label === "学习目标" ? "目标" : label);
  }
  await expect(mobileNav.locator("[data-view=agent]")).toContainText("智能助手");

  const moreToggle = page.locator("#mobile-more-toggle");
  await expect(moreToggle).toHaveAttribute("aria-controls", "mobile-more-menu");
  await expect(moreToggle).toHaveAttribute("aria-expanded", "false");
  await moreToggle.click();
  await expect(moreToggle).toHaveAttribute("aria-expanded", "true");
  const moreMenu = page.locator("#mobile-more-menu");
  await expect(moreMenu).toBeVisible();
  await expect(moreMenu).toHaveAttribute("aria-label", "更多导航");
  await expect(moreMenu).toContainText("问答");
  await expect(moreMenu).toContainText("复习");
  await expect(moreMenu).toContainText("进度");
  await expect(moreMenu).toContainText("导出数据");
  await expect(moreMenu).toContainText("删除账号");

  await moreMenu.locator("[data-view=study]").click();
  await expect(page.locator("#view-study")).toHaveClass(/active/);
  await expect(moreMenu).toBeHidden();
  await expect(moreToggle).toBeFocused();
  await expect(moreToggle).toHaveClass(/active/);
  await expect(moreToggle).toHaveAttribute("aria-label", "更多导航，当前：成长问答");
  await expect(moreMenu.locator("[data-view=study]")).toHaveAttribute("aria-current", "page");

  await moreToggle.click();
  await moreMenu.locator("[data-view=memory]").press("Escape");
  await expect(moreMenu).toBeHidden();
  await expect(moreToggle).toHaveAttribute("aria-expanded", "false");
  await expect(moreToggle).toBeFocused();

  recordNavigationWrites = false;
  expect(navigationWrites).toEqual([]);
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
  await page.screenshot({ path: "docs/images/ux02-mobile-navigation.png", fullPage: true });

  expect(pageErrors).toEqual([]);
  expect(consoleErrors.filter((message) => !message.includes("status of 401 (Unauthorized)"))).toEqual([]);
});
