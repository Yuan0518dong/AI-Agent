const { test, expect } = require("@playwright/test");


test("Batch 2 interactive runtime, responsive navigation, and account data flow", async ({ page }) => {
  const pageErrors = [];
  const consoleErrors = [];
  const initialApiPaths = [];
  let recordInitialRequests = false;

  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("request", (request) => {
    if (!recordInitialRequests || !request.url().includes("/api/")) return;
    initialApiPaths.push(new URL(request.url()).pathname);
  });

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await page.getByRole("button", { name: "注册" }).click();
  await page.locator("#register-form [name=name]").fill("Batch 2 Browser");
  await page.locator("#register-form [name=email]").fill(`batch2-${Date.now()}@example.com`);
  await page.locator("#register-form [name=password]").fill("batch2-password");
  await page.locator("#register-form [name=confirmPassword]").fill("batch2-password");
  recordInitialRequests = true;
  await page.locator("#register-submit").click();

  await expect(page.locator("#app-shell")).toBeVisible();
  await expect(page.locator("#getting-started")).toBeVisible();
  await expect(page.locator("#dashboard-content")).toBeHidden();
  await expect.poll(() => initialApiPaths).toContain("/api/dashboard");
  expect(initialApiPaths).not.toContain("/api/materials");
  expect(initialApiPaths).not.toContain("/api/agent/runs");

  await page.getByRole("button", { name: "创建目标" }).click();
  await page.locator("#goal-form [name=name]").fill("完成 Batch 2 验收");
  await page.locator("#goal-form [name=subject]").fill("软件工程");
  await page.locator("#goal-form [name=deadline]").fill("2026-08-31");
  await page.locator("#goal-form [name=notes]").fill("验证递进式 Agent 任务体验。");
  await page.locator("#goal-submit-button").click();
  await expect(page.locator("#goal-list")).toContainText("完成 Batch 2 验收");

  await page.locator(".desktop-nav [data-view=materials]").click();
  await page.locator("#material-form [name=title]").fill("Batch 2 运行资料");
  await page.locator("#material-form [name=content]").fill("逐步执行的智能任务需要先检查资料、创建草稿并等待确认。");
  await page.locator("#material-submit-button").click();
  await expect(page.locator("#material-list")).toContainText("Batch 2 运行资料");

  await page.locator(".desktop-nav [data-view=agent]").click();
  await expect(page.locator("#agent-run-objective")).toBeVisible();
  await expect(page.locator(".agent-run-details")).not.toHaveAttribute("open", "");
  await expect(page.locator("#agent-goal-select")).toHaveValue(/.+/);
  await page.getByRole("button", { name: "生成待确认任务" }).click();
  await page.locator("#agent-run-start").click();
  await page.locator(".agent-run-details > summary").click();
  await expect(page.locator("#agent-run-detail")).toContainText("执行下一步");
  await page.getByRole("button", { name: "执行下一步" }).click();
  await expect(page.locator("#agent-run-detail")).toContainText("执行下一步");
  await page.getByRole("button", { name: "执行下一步" }).click();
  await expect(page.locator("#agent-run-detail")).toContainText("已完成");

  await page.locator("#logout-button").click();
  await expect(page.locator("#auth-shell")).toBeVisible();
  await page.locator("#demo-login").click();
  await expect(page.locator("#app-shell")).toBeVisible();
  await page.locator(".desktop-nav [data-view=agent]").click();
  await expect(page.locator("#agent-run-count")).toHaveText("1 条");
  if (!(await page.locator(".agent-run-details").evaluate((details) => details.open))) {
    await page.locator(".agent-run-details > summary").click();
  }
  await expect(page.getByRole("button", { name: "确认写入并继续" })).toBeVisible();
  await page.getByRole("button", { name: "确认写入并继续" }).click();
  await expect(page.locator("#agent-run-detail")).toContainText("等待下一步");
  await expect(page.locator("#toast")).toContainText("已确认当前步骤");
  await page.getByRole("button", { name: "取消任务" }).click();
  await expect(page.locator("#agent-run-detail")).toContainText("已取消");
  await expect(page.locator("#toast")).toContainText("智能任务已取消");
  await page.screenshot({ path: "docs/images/v7-batch2-desktop-runtime.png", fullPage: true });

  const views = ["today", "goals", "materials", "agent", "study", "memory", "progress"];
  for (const viewport of [{ width: 1440, height: 900 }, { width: 768, height: 900 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport);
    for (const view of views) {
      if (viewport.width <= 767 && ["study", "memory", "progress"].includes(view)) {
        await page.locator("#mobile-more-toggle").click();
        await page.locator(`#mobile-more-menu [data-view=${view}]`).click();
      } else {
        const selector = viewport.width <= 767
          ? `.mobile-bottom-nav [data-view=${view}]`
          : `.desktop-nav [data-view=${view}]`;
        await page.locator(selector).click();
      }
      await expect(page.locator(`#view-${view}`)).toHaveClass(/active/);
      const widths = await page.evaluate(() => ({
        viewport: window.innerWidth,
        document: document.documentElement.scrollWidth,
        body: document.body.scrollWidth
      }));
      expect(widths.document).toBeLessThanOrEqual(widths.viewport);
      expect(widths.body).toBeLessThanOrEqual(widths.viewport);
    }
  }

  await expect(page.locator(".mobile-bottom-nav")).toBeVisible();
  await page.locator("#mobile-more-toggle").click();
  await expect(page.locator("#mobile-more-menu")).toContainText("问答");
  await expect(page.locator("#mobile-more-menu")).toContainText("复习");
  await expect(page.locator("#mobile-more-menu")).toContainText("进度");
  const downloadPromise = page.waitForEvent("download");
  await page.locator("#mobile-export-data").click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("ai-agent-account-data.json");
  await page.screenshot({ path: "docs/images/v7-batch2-mobile-navigation.png", fullPage: true });

  page.once("dialog", (dialog) => dialog.accept());
  await page.locator("#mobile-reset-data").click();
  await expect(page.locator("#auth-shell")).toBeVisible();
  expect(pageErrors).toEqual([]);
  const unexpectedConsoleErrors = consoleErrors.filter(
    (message) => !message.includes("status of 401 (Unauthorized)")
  );
  expect(unexpectedConsoleErrors).toEqual([]);
});
