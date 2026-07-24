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
