const { test, expect } = require("@playwright/test");


test("Batch 3 upload ingestion, grounded citations, refusal, and responsive status", async ({ page }) => {
  const pageErrors = [];
  const consoleErrors = [];
  const failedRequests = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("requestfailed", (request) => {
    failedRequests.push(`${request.url()} :: ${request.failure()?.errorText || "unknown"}`);
  });
  await page.route("https://images.unsplash.com/**", (route) => route.fulfill({ status: 204, body: "" }));

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await page.locator("#demo-login").click();
  await expect(page.locator("#app-shell")).toBeVisible();

  await page.locator(".desktop-nav [data-view=materials]").click();
  await page.locator("#material-form [name=title]").fill("Batch 3 检索资料");
  await page.locator("#material-form [name=type]").selectOption("upload");
  await expect(page.locator("#material-file-field")).toBeVisible();
  await page.locator("#material-form [name=file]").setInputFiles({
    name: "batch3-retrieval.md",
    mimeType: "text/markdown",
    buffer: Buffer.from(
      "# 检索设计\n\n混合检索结合关键词和向量检索，并使用 RRF 排序。\n\n## 证据边界\n\n没有充分资料引用时必须明确回答资料不足。"
    )
  });
  await page.locator("#material-submit-button").click();
  await expect(page.locator("#material-list")).toContainText("Batch 3 检索资料");
  await expect(page.locator("#material-list")).toContainText("提取");
  await expect(page.locator("#material-list")).toContainText("向量化");
  await expect(page.locator("#material-list")).toContainText("完成");
  await page.screenshot({ path: "docs/images/v7-batch3-desktop-ingestion.png", fullPage: true });

  await page.locator(".desktop-nav [data-view=study]").click();
  await page.locator("#chat-form [name=question]").fill("混合检索如何排序？");
  await page.locator("#chat-form button[type=submit]").click();
  await expect(page.locator(".message-reference-chunks")).toContainText("检索设计");
  await expect(page.locator(".message-reference-chunks")).toContainText("hybrid");
  await expect(page.locator(".message-reference-chunks")).toContainText("score");

  await page.locator("#chat-form [name=question]").fill("量子纠缠的贝尔不等式是什么？");
  await page.locator("#chat-form button[type=submit]").click();
  await expect(page.locator("#chat-log")).toContainText("资料不足");

  await page.locator(".desktop-nav [data-view=materials]").click();
  await page.locator("#material-form [name=type]").selectOption("link");
  await expect(page.locator("#material-link-note")).toBeVisible();
  await expect(page.locator("#material-link-note")).toContainText("仅保存链接，不解析网页正文");

  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator(".mobile-bottom-nav [data-view=materials]").click();
  await expect(page.locator("#material-list")).toContainText("Batch 3 检索资料");
  const widths = await page.evaluate(() => ({
    viewport: window.innerWidth,
    document: document.documentElement.scrollWidth,
    body: document.body.scrollWidth
  }));
  expect(widths.document).toBeLessThanOrEqual(widths.viewport);
  expect(widths.body).toBeLessThanOrEqual(widths.viewport);
  await page.screenshot({ path: "docs/images/v7-batch3-mobile-ingestion.png", fullPage: true });

  expect(pageErrors).toEqual([]);
  const unexpectedConsoleErrors = consoleErrors.filter(
    (message) => !message.includes("status of 401 (Unauthorized)")
  );
  expect(unexpectedConsoleErrors, failedRequests.join("\n")).toEqual([]);
});
