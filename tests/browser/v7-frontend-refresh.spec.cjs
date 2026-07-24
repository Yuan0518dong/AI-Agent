const { test, expect } = require("@playwright/test");
const AxeBuilder = require("@axe-core/playwright").default;


async function assertNoSeriousAccessibilityViolations(page) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  const serious = results.violations.filter((violation) => ["serious", "critical"].includes(violation.impact));
  expect(serious.flatMap((violation) => violation.nodes.map(
    (node) => `${violation.id} ${node.target.join(" ")}: ${node.failureSummary}`
  ))).toEqual([]);
}


async function assertNoDocumentOverflow(page) {
  const widths = await page.evaluate(() => ({
    viewport: window.innerWidth,
    document: document.documentElement.scrollWidth,
    body: document.body.scrollWidth
  }));
  expect(widths.document).toBeLessThanOrEqual(widths.viewport);
  expect(widths.body).toBeLessThanOrEqual(widths.viewport);
}


test("portfolio refresh keeps the auth portal and learning app accessible and responsive", async ({ page }) => {
  const pageErrors = [];
  const consoleErrors = [];
  const externalImageRequests = [];

  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("request", (request) => {
    if (request.resourceType() === "image" && !request.url().startsWith("http://127.0.0.1:8019")) {
      externalImageRequests.push(request.url());
    }
  });

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await expect(page.locator("#auth-shell")).toBeVisible();
  await expect(page.locator(".auth-hero-copy")).toContainText("让资料真正变成");
  await expect(page.locator("#show-login")).toHaveAttribute("aria-selected", "true");
  await expect(page.locator("#login-form")).toBeVisible();

  await page.locator("#show-login").focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.locator("#show-register")).toHaveAttribute("aria-selected", "true");
  await expect(page.locator("#register-form")).toBeVisible();
  await expect(page.locator("#auth-panel-title")).toHaveText("建立你的学习档案");

  await page.keyboard.press("ArrowLeft");
  await expect(page.locator("#show-login")).toHaveAttribute("aria-selected", "true");
  await expect(page.locator("#login-form")).toBeVisible();
  await assertNoDocumentOverflow(page);
  await assertNoSeriousAccessibilityViolations(page);
  expect(externalImageRequests).toEqual([]);

  await page.setViewportSize({ width: 390, height: 844 });
  await assertNoDocumentOverflow(page);
  await assertNoSeriousAccessibilityViolations(page);

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.locator("#demo-login").click();
  await expect(page.locator("#app-shell")).toBeVisible();
  await expect(page.locator("#view-today")).toHaveClass(/active/);
  await expect(page.locator(".desktop-nav [data-view=today]")).toHaveAttribute("aria-current", "page");

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator(".mobile-bottom-nav")).toBeVisible();
  await assertNoDocumentOverflow(page);
  await assertNoSeriousAccessibilityViolations(page);

  expect(pageErrors).toEqual([]);
  expect(consoleErrors).toEqual([]);
});

test("FE-01 design tokens expose semantic surfaces and focus styles", async ({ page }, testInfo) => {
  const pageErrors = [];
  const consoleErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await expect(page.locator("#auth-shell")).toBeVisible();

  const tokens = await page.evaluate(() => {
    const styles = getComputedStyle(document.documentElement);
    const read = (name) => styles.getPropertyValue(name).trim();
    return {
      bg: read("--bg"),
      surface: read("--surface"),
      text: read("--text"),
      textMuted: read("--text-muted"),
      border: read("--border"),
      primary: read("--primary"),
      success: read("--success"),
      warning: read("--warning"),
      danger: read("--danger"),
      focusRing: read("--focus-ring"),
      radiusMd: read("--radius-md"),
      mint: read("--mint")
    };
  });

  expect(tokens.bg).toBeTruthy();
  expect(tokens.surface.toLowerCase()).toMatch(/#fff|#ffffff|rgb\(255,\s*255,\s*255\)/i);
  expect(tokens.text).toBeTruthy();
  expect(tokens.textMuted).toBeTruthy();
  expect(tokens.border).toBeTruthy();
  expect(tokens.primary).toBeTruthy();
  expect(tokens.success).toBeTruthy();
  expect(tokens.warning).toBeTruthy();
  expect(tokens.danger).toBeTruthy();
  expect(tokens.focusRing).toBeTruthy();
  expect(tokens.radiusMd).toBe("8px");
  expect(tokens.mint.toLowerCase()).toBe("#0f766e");

  const demoButton = page.locator("#demo-login");
  await demoButton.focus();
  const focusOutline = await demoButton.evaluate((el) => getComputedStyle(el).outlineStyle);
  expect(focusOutline).not.toBe("none");

  await page.locator("#auth-shell").screenshot({
    path: "docs/images/fe01-auth-portal-desktop.png"
  });

  await demoButton.click();
  await expect(page.locator("#app-shell")).toBeVisible();
  await expect(page.locator("#view-today")).toHaveClass(/active/);

  const primaryButton = page.locator(".primary-button:visible").first();
  await expect(primaryButton).toBeVisible();
  const primaryStyles = await primaryButton.evaluate((el) => {
    const s = getComputedStyle(el);
    return {
      color: s.color,
      backgroundImage: s.backgroundImage,
      minHeight: s.minHeight,
      borderRadius: s.borderRadius
    };
  });
  expect(primaryStyles.backgroundImage).toMatch(/linear-gradient/i);
  expect(Number.parseFloat(primaryStyles.minHeight)).toBeGreaterThanOrEqual(36);

  await primaryButton.focus();
  const primaryOutline = await primaryButton.evaluate((el) => getComputedStyle(el).outlineStyle);
  expect(primaryOutline).not.toBe("none");

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator(".mobile-bottom-nav")).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "docs/images/fe01-today-mobile.png"
  });
  await assertNoDocumentOverflow(page);
  await assertNoSeriousAccessibilityViolations(page);

  expect(pageErrors).toEqual([]);
  expect(consoleErrors).toEqual([]);
});

test("FE-02 keeps authentication feedback actionable and preserves form state", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await page.screenshot({ path: "docs/images/fe02-login-desktop.png" });

  await page.locator("#show-login").focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.locator("#register-form")).toBeVisible();
  await expect(page.locator("#show-register")).toBeFocused();
  await page.locator("#show-login").click();
  await expect(page.locator("#login-email")).toBeFocused();
  await page.locator("#show-register").click();
  await expect(page.locator("#register-name")).toBeFocused();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: "docs/images/fe02-register-mobile.png" });

  await page.locator("#show-login").click();
  await page.locator("#login-email").fill("learner@example.com");
  await page.locator("#login-password").fill("not-the-password");
  await page.route("**/api/auth/login", (route) => route.fulfill({
    status: 401,
    contentType: "application/json",
    body: JSON.stringify({ detail: { message: "invalid credentials" } })
  }));
  await page.locator("#login-submit").click();

  await expect(page.locator("#auth-feedback")).toBeVisible();
  await expect(page.locator("#auth-feedback")).toContainText("邮箱或密码不正确");
  await expect(page.locator("#login-email")).toHaveValue("learner@example.com");
  await expect(page.locator("#login-password")).toHaveValue("not-the-password");
  await expect(page.locator("#login-submit")).toBeEnabled();
  await expect(page.locator("#login-email")).toHaveAttribute("aria-describedby", "auth-feedback");

  await page.unroute("**/api/auth/login");
  await page.route("**/api/auth/demo", (route) => route.abort("failed"));
  await page.locator("#demo-login").click();
  await expect(page.locator("#auth-feedback")).toContainText("无法连接本地服务");
  await expect(page.locator("#demo-login")).toBeEnabled();
  await page.screenshot({ path: "docs/images/fe02-demo-error-mobile.png" });
});

test("FE-03 puts the current goal before Today actions for a demo learner", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await page.locator("#demo-login").click();
  await expect(page.locator("#view-today .today-focus-panel")).toBeVisible();
  await expect.poll(() => page.locator("#dashboard-content").evaluate((container) => {
    const order = [...container.children].map((child) => [...child.classList]);
    const focusIndex = order.findIndex((classes) => classes.includes("today-focus-panel"));
    const summaryIndex = order.findIndex((classes) => classes.includes("summary-grid"));
    const dashboardIndex = order.findIndex((classes) => classes.includes("today-dashboard"));
    return focusIndex > summaryIndex && focusIndex < dashboardIndex;
  })).toBe(true);
  await page.screenshot({ path: "docs/images/fe03-today-demo-desktop.png" });
});

test("FE-04 keeps goals, materials, and cited answers in one learning workspace", async ({ page }) => {
  const pageErrors = [];
  const consoleErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await page.locator("#demo-login").click();

  for (const [view, heading] of [["goals", "学习目标"], ["materials", "成长资料"], ["study", "成长问答"]]) {
    await page.locator(`.desktop-nav [data-view=${view}]`).click();
    await expect(page.locator(`#view-${view} .workspace-intro h2`)).toHaveText(heading);
    await expect(page.locator(`#${view}-workspace-current-goal`)).toContainText("当前目标：");
  }

  await page.locator(".desktop-nav [data-view=goals]").click();
  await page.locator("#goal-list .item").first().getByRole("button", { name: "详情" }).click();
  await expect(page.locator("#goal-detail")).not.toBeEmpty();
  await expect(page.locator("#goals-workspace-current-goal")).not.toContainText("未选择");
  await page.screenshot({ path: "docs/images/fe04-goals-desktop.png" });

  await page.locator(".desktop-nav [data-view=materials]").click();
  await page.locator("#material-form [name=title]").fill("FE-04 检索资料");
  await page.locator("#material-form [name=type]").selectOption("upload");
  await page.locator("#material-form [name=file]").setInputFiles({
    name: "fe04.md", mimeType: "text/markdown", buffer: Buffer.from("# 检索设计\n\n问题：混合检索如何排序？\n答案：混合检索结合关键词和向量检索，并使用 RRF 排序。\n\n## 证据边界\n\n没有充分资料引用时必须明确回答资料不足。")
  });
  await page.locator("#material-submit-button").click();
  await expect(page.locator("#material-list")).toContainText("完成");
  await page.screenshot({ path: "docs/images/fe04-material-complete.png" });

  await page.locator(".desktop-nav [data-view=study]").click();
  await expect(page.locator("#summary-list .summary-card").filter({ hasText: "FE-04 检索资料" })).toBeVisible();
  await page.locator("#summary-list .summary-card").filter({ hasText: "FE-04 检索资料" }).getByRole("button", { name: "围绕此资料提问" }).click();
  await expect(page.locator("#chat-form [name=question]")).toBeFocused();
  await page.locator("#chat-form [name=question]").fill("混合检索如何排序？");
  await page.locator("#chat-form button[type=submit]").click();
  await expect(page.locator(".message-reference-chunks")).toBeVisible();
  await page.screenshot({ path: "docs/images/fe04-cited-answer.png" });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator("#chat-form [name=question]").fill("量子纠缠的贝尔不等式是什么？");
  await page.locator("#chat-form button[type=submit]").click();
  const latestAgentMessage = page.locator("#chat-log .message.agent").last();
  await expect(latestAgentMessage).toContainText("当前资料不足以直接回答这个问题");
  await expect(latestAgentMessage).toContainText("grounded-refusal");
  await expect(latestAgentMessage.locator(".message-reference-chunks")).toHaveCount(0);
  await expect(page.locator(".message-reference-chunks")).toHaveCount(1);
  await page.screenshot({ path: "docs/images/fe04-insufficient-mobile.png", fullPage: true });

  expect(pageErrors).toEqual([]);
  expect(consoleErrors).toEqual([]);
});
