const fs = require("fs/promises");
const path = require("path");
const { test, expect } = require("@playwright/test");

const ROOT_DIR = path.resolve(__dirname, "../..");
const VIDEO_OUTPUT = path.join(ROOT_DIR, "docs", "videos", "v7-batch4-90s-demo.webm");

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

test("record the Batch 4 90-second portfolio walkthrough", async ({ browser }) => {
  test.setTimeout(150_000);
  const context = await browser.newContext({
    baseURL: "http://127.0.0.1:8019",
    viewport: { width: 1280, height: 720 },
    recordVideo: { dir: path.join(ROOT_DIR, "test-results", "batch4-demo-video"), size: { width: 1280, height: 720 } }
  });
  const page = await context.newPage();
  const video = page.video();
  try {
    await page.route("https://images.unsplash.com/**", (route) => route.fulfill({ status: 204, body: "" }));
    await page.goto("/");
    await page.waitForTimeout(6_000);
    await page.locator("#demo-login").click();
    await expect(page.locator("#toast")).toContainText("已进入独立演示环境");
    await page.waitForTimeout(8_000);

    await page.locator(".desktop-nav [data-view=goals]").click();
    await page.locator("#goal-form [name=name]").fill("90 秒演示目标");
    await page.locator("#goal-form [name=subject]").fill("检索评测");
    await page.locator("#goal-form [name=deadline]").fill("2026-12-31");
    await page.locator("#goal-submit-button").click();
    await expect(page.locator("#goal-list")).toContainText("90 秒演示目标");
    await page.waitForTimeout(10_000);

    await page.locator(".desktop-nav [data-view=materials]").click();
    await page.locator("#material-form [name=title]").fill("90 秒 PDF 资料");
    await page.locator("#material-form [name=type]").selectOption("upload");
    await page.locator("#material-form [name=file]").setInputFiles({
      name: "portfolio-evidence.pdf",
      mimeType: "application/pdf",
      buffer: createTextPdf("PDF citations preserve page evidence without persisting source bytes.")
    });
    await page.locator("#material-submit-button").click();
    await expect(page.locator("#material-list")).toContainText("90 秒 PDF 资料");
    await page.waitForTimeout(10_000);

    await page.locator(".desktop-nav [data-view=study]").click();
    await page.locator("#chat-form [name=question]").fill("当前资料的 PDF citation evidence 如何定位？");
    await page.locator("#chat-form button[type=submit]").click();
    await expect(page.locator(".message-reference-chunks")).toContainText("90 秒 PDF 资料");
    await page.waitForTimeout(20_000);

    await page.locator(".desktop-nav [data-view=agent]").click();
    await page.locator("#agent-goal-select").selectOption({ label: "完成一周 AI Agent 学习计划" });
    await expect(page.locator("#toast")).toContainText("学习目标已切换");
    const details = page.locator(".agent-run-details");
    if (!(await details.evaluate((node) => node.open))) await details.locator(":scope > summary").click();
    await expect(page.locator("#agent-current-action").getByRole("button", { name: "接受" })).toBeVisible();
    await page.waitForTimeout(12_000);
    await page.locator("#agent-current-action").getByRole("button", { name: "接受" }).click();
    await expect(page.locator("#toast")).toContainText("已确认当前步骤");
    await page.waitForTimeout(8_000);

    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator(".mobile-bottom-nav [data-view=materials]").click();
    await expect(page.locator("#material-list")).toBeVisible();
    await page.waitForTimeout(12_000);
  } finally {
    await context.close();
  }
  await fs.mkdir(path.dirname(VIDEO_OUTPUT), { recursive: true });
  await fs.copyFile(await video.path(), VIDEO_OUTPUT);
  const stats = await fs.stat(VIDEO_OUTPUT);
  expect(stats.size).toBeGreaterThan(10_000);
});
