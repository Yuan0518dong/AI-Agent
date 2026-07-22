const { test, expect } = require("@playwright/test");
const AxeBuilder = require("@axe-core/playwright").default;

function createTextPdf(text) {
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
    `<< /Length ${text.length + 33} >>\nstream\nBT /F1 12 Tf 72 720 Td (${text}) Tj ET\nendstream`,
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
  ];
  let pdf = "%PDF-1.4\n";
  const offsets = [0];
  objects.forEach((object, index) => {
    offsets.push(Buffer.byteLength(pdf, "latin1"));
    pdf += `${index + 1} 0 obj\n${object}\nendobj\n`;
  });
  const xrefOffset = Buffer.byteLength(pdf, "latin1");
  pdf += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  for (const offset of offsets.slice(1)) pdf += `${String(offset).padStart(10, "0")} 00000 n \n`;
  pdf += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF`;
  return Buffer.from(pdf, "latin1");
}

async function assertNoSeriousAccessibilityViolations(page) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  const serious = results.violations.filter((violation) => ["serious", "critical"].includes(violation.impact));
  expect(serious.flatMap((violation) => violation.nodes.map(
    (node) => `${violation.id} ${node.target.join(" ")}: ${node.failureSummary}`
  ))).toEqual([]);
}

test("Batch 4 portfolio flow covers demo, goal, PDF, cited QA, confirmation, rejection, cancellation, and mobile", async ({ page }) => {
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
  await expect(page.locator("#toast")).toContainText("已进入独立演示环境");
  await expect(page.locator("#view-today")).toHaveClass(/active/);

  await page.locator(".desktop-nav [data-view=goals]").click();
  await expect(page.locator("#view-goals")).toHaveClass(/active/);
  await page.locator("#goal-form [name=name]").fill("Batch 4 浏览器验收目标");
  await page.locator("#goal-form [name=subject]").fill("检索评测");
  await page.locator("#goal-form [name=deadline]").fill("2026-12-31");
  await page.locator("#goal-form [name=notes]").fill("验证公开演示中的可控 Agent 主路径。");
  await page.locator("#goal-submit-button").click();
  await expect(page.locator("#goal-list")).toContainText("Batch 4 浏览器验收目标");

  await page.locator(".desktop-nav [data-view=materials]").click();
  await page.locator("#material-form [name=title]").fill("Batch 4 PDF 资料");
  await page.locator("#material-form [name=type]").selectOption("upload");
  await page.locator("#material-form [name=file]").setInputFiles({
    name: "batch4-evidence.pdf",
    mimeType: "application/pdf",
    buffer: createTextPdf("PDF citation evidence uses page numbers and does not persist source bytes.")
  });
  await page.locator("#material-submit-button").click();
  await expect(page.locator("#material-list")).toContainText("Batch 4 PDF 资料");
  await expect(page.locator("#material-list")).toContainText("完成");

  await page.locator(".desktop-nav [data-view=study]").click();
  await page.locator("#chat-form [name=question]").fill("当前资料的 PDF citation evidence 如何定位？");
  await page.locator("#chat-form button[type=submit]").click();
  await expect(page.locator(".message-reference-chunks")).toContainText("Batch 4 PDF 资料");
  await expect(page.locator(".message-reference-chunks")).toContainText("page");

  await page.locator(".desktop-nav [data-view=agent]").click();
  await expect(page.locator("#view-agent")).toHaveClass(/active/);
  await page.locator("#agent-goal-select").selectOption({ label: "完成一周 AI Agent 学习计划" });
  await expect(page.locator("#toast")).toContainText("学习目标已切换");
  await expect(page.locator("#agent-run-count")).toHaveText("1 条");
  const details = page.locator(".agent-run-details");
  if (!(await details.evaluate((node) => node.open))) await details.locator(":scope > summary").click();
  await expect(page.locator("#agent-current-action").getByRole("button", { name: "接受" })).toBeVisible();
  await page.locator("#agent-current-action").getByRole("button", { name: "接受" }).click();
  await expect(page.locator("#toast")).toContainText("已确认当前步骤");
  await page.locator("#agent-current-action").getByRole("button", { name: "取消任务" }).click();
  await expect(page.locator("#agent-run-detail")).toContainText("已取消");

  await page.locator("#logout-button").click();
  await expect(page.locator("#auth-shell")).toBeVisible();
  await page.locator("#demo-login").click();
  await expect(page.locator("#toast")).toContainText("已进入独立演示环境");
  await expect(page.locator("#view-today")).toHaveClass(/active/);
  await page.locator(".desktop-nav [data-view=agent]").click();
  await page.locator("#agent-goal-select").selectOption({ label: "完成一周 AI Agent 学习计划" });
  await expect(page.locator("#toast")).toContainText("学习目标已切换");
  await expect(page.locator("#agent-run-count")).toHaveText("1 条");
  const secondDetails = page.locator(".agent-run-details");
  if (!(await secondDetails.evaluate((node) => node.open))) await secondDetails.locator(":scope > summary").click();
  await expect(page.locator("#agent-current-action").getByRole("button", { name: "拒绝" })).toBeVisible();
  await page.locator("#agent-current-action").getByRole("button", { name: "拒绝" }).click();
  await expect(page.locator("#toast")).toContainText("已拒绝写入");

  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator(".mobile-bottom-nav [data-view=materials]").click();
  await expect(page.locator("#material-list")).toBeVisible();
  const widths = await page.evaluate(() => ({
    viewport: window.innerWidth,
    document: document.documentElement.scrollWidth,
    body: document.body.scrollWidth
  }));
  expect(widths.document).toBeLessThanOrEqual(widths.viewport);
  expect(widths.body).toBeLessThanOrEqual(widths.viewport);
  await assertNoSeriousAccessibilityViolations(page);
  await page.screenshot({ path: "docs/images/v7-batch4-mobile-e2e.png", fullPage: true });

  expect(pageErrors).toEqual([]);
  const unexpectedConsoleErrors = consoleErrors.filter((message) => !message.includes("status of 401 (Unauthorized)"));
  expect(unexpectedConsoleErrors, failedRequests.join("\n")).toEqual([]);
});
