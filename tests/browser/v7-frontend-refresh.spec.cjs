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
