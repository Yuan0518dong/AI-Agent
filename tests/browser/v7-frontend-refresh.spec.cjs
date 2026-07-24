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

async function apiData(page, path) {
  return page.evaluate(async (requestPath) => {
    const response = await fetch(requestPath);
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || `Request failed: ${response.status}`);
    return payload.data;
  }, path);
}

async function listFlashcardsForMaterials(page) {
  const materials = await apiData(page, "/api/materials");
  const cardsByMaterial = await Promise.all(materials.map(async (material) => ({
    materialId: material.id,
    cards: await apiData(page, `/api/materials/${material.id}/flashcards`)
  })));
  return cardsByMaterial.flatMap(({ materialId, cards }) => cards.map((card) => ({ ...card, materialId })));
}

async function selectFlashcard(page, flashcardId, cardCount) {
  for (let index = 0; index < cardCount; index += 1) {
    if (await page.locator("#flashcard").getAttribute("data-flashcard-id") === flashcardId) return;
    await page.locator("#shuffle-cards").click();
  }
  expect(await page.locator("#flashcard").getAttribute("data-flashcard-id")).toBe(flashcardId);
}

async function openResponsiveView(page, view, viewportWidth) {
  if (viewportWidth <= 767) {
    if (["today", "goals", "materials", "agent"].includes(view)) {
      await page.locator(`.mobile-bottom-nav [data-view=${view}]`).click();
    } else {
      await page.locator("#mobile-more-toggle").click();
      await page.locator(`#mobile-more-menu [data-view=${view}]`).click();
    }
  } else {
    await page.locator(`.desktop-nav [data-view=${view}]`).click();
  }
  await expect(page.locator(`#view-${view}`)).toHaveClass(/active/);
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

test("FE-05 makes confirmation, review state, and progress changes explainable", async ({ page }) => {
  const pageErrors = [];
  const consoleErrors = [];
  const rejectedFormalWrites = [];
  const acceptedConfirmationRequests = [];
  let observeRejectedFormalWrites = false;
  let observeAcceptedConfirmation = false;
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("request", (request) => {
    const path = new URL(request.url()).pathname;
    if (observeRejectedFormalWrites && !["GET", "HEAD", "OPTIONS"].includes(request.method()) && /\/(goals|materials|flashcards|tasks|quiz)/.test(path)) {
      rejectedFormalWrites.push(`${request.method()} ${path}`);
    }
    if (observeAcceptedConfirmation && !["GET", "HEAD", "OPTIONS"].includes(request.method()) && /^\/api\/agent\/(action-logs\/[^/]+|runs\/[^/]+\/advance)$/.test(path)) {
      acceptedConfirmationRequests.push({ method: request.method(), path, body: request.postData() });
    }
  });

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await page.locator("#demo-login").click();

  await page.locator(".desktop-nav [data-view=memory]").click();
  await expect(page.locator("#flashcard")).toHaveAttribute("data-flashcard-id", /.+/);
  await page.screenshot({ path: "docs/images/fe05-flashcard-before.png" });
  await page.locator("#card-review").click();
  await expect(page.locator("#toast")).toContainText("已加入复习队列");
  await expect(page.locator("#flashcard-status-note")).toContainText("FSRS 队列与 Today 会在最终状态返回后同步");
  await page.screenshot({ path: "docs/images/fe05-flashcard-after.png" });
  const quizForm = page.locator(".quiz-answer-form").first();
  await quizForm.locator("textarea[name=answer]").fill("错误答案");
  await quizForm.getByRole("button", { name: "提交批改" }).click();
  await expect(page.locator("#toast")).toContainText("AI 批改完成");

  await page.locator(".desktop-nav [data-view=agent]").click();
  await page.locator("#agent-goal-select").selectOption({ label: "完成一周 AI Agent 学习计划" });
  await page.locator("#agent-run-objective").fill("基于当前错题生成复习闪卡草稿。");
  await page.locator("#agent-run-start").click();
  const currentAction = page.locator("#agent-current-action");
  await currentAction.getByRole("button", { name: "执行下一步" }).click();
  await expect(currentAction.locator(".agent-confirmation-boundary")).toContainText("尚未写入正式任务、资料或复习数据");
  await expect(currentAction.getByRole("button", { name: "接受" })).toBeVisible();
  await expect(currentAction.getByRole("button", { name: "拒绝" })).toBeVisible();
  await page.screenshot({ path: "docs/images/fe05-agent-waiting-desktop.png" });

  const details = page.locator(".agent-run-details");
  if (!(await details.evaluate((node) => node.open))) await details.locator(":scope > summary").click();
  await expect(page.locator("#agent-run-detail")).toContainText("执行过程");
  await page.screenshot({ path: "docs/images/fe05-agent-run-details-desktop.png", fullPage: true });

  observeRejectedFormalWrites = true;
  await currentAction.getByRole("button", { name: "拒绝" }).click();
  await expect(page.locator("#toast")).toContainText("已拒绝写入");
  observeRejectedFormalWrites = false;
  expect(rejectedFormalWrites).toEqual([]);

  const cardsBeforeAcceptance = await listFlashcardsForMaterials(page);
  await page.locator("#agent-run-objective").fill("根据当前错题生成第二份待确认复习闪卡草稿。");
  await page.locator("#agent-run-start").click();
  await expect(page.locator("#toast")).toContainText("已完成第一步");
  await currentAction.getByRole("button", { name: "执行下一步" }).click();
  await expect(currentAction.getByRole("button", { name: "接受" })).toBeVisible();
  observeAcceptedConfirmation = true;
  await currentAction.getByRole("button", { name: "接受" }).click();
  await expect(page.locator("#toast")).toContainText("已确认当前步骤");
  observeAcceptedConfirmation = false;
  expect(acceptedConfirmationRequests.filter((request) => request.method === "PATCH" && /\/action-logs\//.test(request.path))).toEqual([
    expect.objectContaining({ body: '{"status":"accepted"}' })
  ]);
  expect(acceptedConfirmationRequests.filter((request) => request.method === "POST" && /\/advance$/.test(request.path))).toHaveLength(1);

  await expect.poll(() => listFlashcardsForMaterials(page)).toHaveLength(cardsBeforeAcceptance.length + 1);
  const cardsAfterAcceptance = await listFlashcardsForMaterials(page);
  const formalCard = cardsAfterAcceptance.find((card) => !cardsBeforeAcceptance.some((before) => before.id === card.id));
  expect(formalCard).toEqual(expect.objectContaining({ reviewCount: 0, lastRating: null }));

  await page.locator(".desktop-nav [data-view=memory]").click();
  await selectFlashcard(page, formalCard.id, cardsAfterAcceptance.length);
  const reviewResponse = page.waitForResponse((response) => {
    const path = new URL(response.url()).pathname;
    return path === `/api/materials/${formalCard.materialId}/flashcards/${formalCard.id}`
      && response.request().method() === "PATCH" && response.ok();
  });
  await page.locator("#card-known").click();
  const reviewPayload = await (await reviewResponse).json();
  expect(reviewPayload.data).toEqual(expect.objectContaining({
    id: formalCard.id,
    reviewCount: 1,
    lastRating: "good",
    status: "known"
  }));
  const todayAfterRating = await apiData(page, "/api/today/actions");
  expect(todayAfterRating.items).not.toEqual(expect.arrayContaining([
    expect.objectContaining({ kind: "due_flashcard", id: formalCard.id })
  ]));

  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator("#mobile-more-toggle").click();
  await page.locator("#mobile-more-menu [data-view=progress]").click();
  await expect(page.locator("#progress-state-note")).toContainText("已汇总");
  await assertNoDocumentOverflow(page);
  await page.screenshot({ path: "docs/images/fe05-progress-mobile.png", fullPage: true });

  expect(pageErrors).toEqual([]);
  expect(consoleErrors).toEqual([]);
});

test("FE-06 keeps loading, failure recovery, keyboard navigation, and responsive views reliable", async ({ page }, testInfo) => {
  const pageErrors = [];
  const consoleErrors = [];
  const reviewWrites = [];
  let releaseTodayRequest;
  let holdTodayRequest = true;
  let failReviewOnce = true;

  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("request", (request) => {
    const path = new URL(request.url()).pathname;
    if (request.method() === "PATCH" && /\/api\/materials\/[^/]+\/flashcards\/[^/]+$/.test(path)) {
      reviewWrites.push(path);
    }
  });
  await page.addInitScript(() => {
    const signals = { longTasks: [], layoutShifts: [] };
    window.__fe06PerformanceSignals = signals;
    if (!("PerformanceObserver" in window)) return;
    try {
      new PerformanceObserver((entries) => {
        entries.getEntries().forEach((entry) => signals.longTasks.push(entry.duration));
      }).observe({ type: "longtask", buffered: true });
    } catch {
      // Browsers without Long Tasks support still expose the request-level checks below.
    }
    try {
      new PerformanceObserver((entries) => {
        entries.getEntries().forEach((entry) => {
          if (!entry.hadRecentInput) {
            signals.layoutShifts.push({
              value: entry.value,
              sources: (entry.sources || []).map((source) => source.node?.id || source.node?.className || source.node?.tagName || "unknown")
            });
          }
        });
      }).observe({ type: "layout-shift", buffered: true });
    } catch {
      // Layout Shift is optional in browser engines used by the local test matrix.
    }
  });
  await page.route("**/api/today/actions**", async (route) => {
    if (holdTodayRequest) await new Promise((resolve) => { releaseTodayRequest = resolve; });
    await route.continue();
  });
  await page.route("**/api/materials/*/flashcards/*", async (route) => {
    if (!failReviewOnce || route.request().method() !== "PATCH") return route.continue();
    failReviewOnce = false;
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: { message: "评分服务暂时不可用，请重试。" } })
    });
  });

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await page.locator("#show-login").focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.locator("#show-register")).toBeFocused();
  await page.keyboard.press("ArrowLeft");
  await expect(page.locator("#show-login")).toBeFocused();
  await page.locator("#demo-login").focus();
  await page.keyboard.press("Enter");
  await expect(page.locator("#app-shell")).toBeVisible();
  await expect(page.locator("#today-actions-list")).toHaveAttribute("aria-busy", "true");
  await expect(page.locator("#today-actions-list .is-loading-surface")).toHaveAttribute("role", "status");
  await expect(page.locator("#today-actions-list .is-loading-surface")).toHaveAttribute("aria-busy", "true");
  await page.screenshot({ path: testInfo.outputPath("fe06-loading-desktop.png") });

  releaseTodayRequest();
  holdTodayRequest = false;
  await expect(page.locator("#today-actions-count")).not.toHaveText("加载中");
  await expect(page.locator("#today-actions-list")).toHaveAttribute("aria-busy", "false");
  const initialPerformance = await page.evaluate(() => {
    const apiPaths = performance.getEntriesByType("resource")
      .map((entry) => new URL(entry.name).pathname)
      .filter((path) => path.startsWith("/api/"));
    return {
      dashboardRequests: apiPaths.filter((path) => path === "/api/dashboard").length,
      todayActionRequests: apiPaths.filter((path) => path === "/api/today/actions").length,
      longTasks: window.__fe06PerformanceSignals?.longTasks || [],
      layoutShifts: window.__fe06PerformanceSignals?.layoutShifts || []
    };
  });
  expect(initialPerformance.dashboardRequests).toBe(1);
  expect(initialPerformance.todayActionRequests).toBe(1);
  expect(initialPerformance.longTasks.filter((duration) => duration >= 200)).toEqual([]);
  const layoutShift = initialPerformance.layoutShifts.reduce((sum, entry) => sum + entry.value, 0);
  expect(layoutShift, JSON.stringify(initialPerformance.layoutShifts)).toBeLessThanOrEqual(0.1);

  await openResponsiveView(page, "memory", 1440);
  await expect(page.locator("#flashcard")).toHaveAttribute("data-flashcard-id", /.+/);
  const reviewButton = page.locator("#card-review");
  await reviewButton.click();
  await expect(page.locator("#app-feedback")).toBeVisible();
  await expect(page.locator("#app-feedback-message")).toContainText("评分服务暂时不可用");
  await expect(reviewButton).toBeEnabled();
  await expect(reviewButton).not.toHaveAttribute("aria-busy");
  expect(reviewWrites).toHaveLength(1);
  await page.screenshot({ path: testInfo.outputPath("fe06-recoverable-error-desktop.png") });
  await page.locator("#app-feedback-dismiss").click();
  await expect(page.locator("#app-feedback")).toBeHidden();
  await reviewButton.click();
  await expect(page.locator("#toast")).toContainText("已加入复习队列");
  expect(reviewWrites).toHaveLength(2);

  for (const viewport of [
    { width: 390, height: 844 },
    { width: 768, height: 1024 },
    { width: 1440, height: 900 }
  ]) {
    await page.setViewportSize(viewport);
    for (const view of ["today", "goals", "materials", "study", "agent", "memory", "progress"]) {
      await openResponsiveView(page, view, viewport.width);
      await assertNoDocumentOverflow(page);
    }
    if (viewport.width === 768) {
      const navBounds = await page.locator(".desktop-nav .nav-item").evaluateAll((items) => items.map((item) => {
        const rect = item.getBoundingClientRect();
        return { left: rect.left, right: rect.right, width: rect.width, viewport: window.innerWidth };
      }));
      navBounds.forEach((bounds) => {
        expect(bounds.width).toBeGreaterThan(0);
        expect(bounds.left).toBeGreaterThanOrEqual(0);
        expect(bounds.right).toBeLessThanOrEqual(bounds.viewport);
      });
    }
    await page.screenshot({ path: testInfo.outputPath(`fe06-${viewport.width}x${viewport.height}.png`) });
  }

  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator("#mobile-more-toggle").focus();
  await page.keyboard.press("Enter");
  await expect(page.locator("#mobile-more-menu")).toBeVisible();
  await page.locator("#mobile-more-menu [data-view=study]").focus();
  await page.keyboard.press("Escape");
  await expect(page.locator("#mobile-more-menu")).toBeHidden();
  await expect(page.locator("#mobile-more-toggle")).toBeFocused();
  await assertNoSeriousAccessibilityViolations(page);

  await page.setViewportSize({ width: 1440, height: 900 });
  for (const view of ["today", "agent", "memory"]) {
    await openResponsiveView(page, view, 1440);
    await assertNoSeriousAccessibilityViolations(page);
  }
  await page.emulateMedia({ reducedMotion: "reduce" });
  const motion = await page.locator("#toast").evaluate((node) => getComputedStyle(node).transitionDuration);
  expect(Number.parseFloat(motion)).toBeLessThanOrEqual(0.01);

  expect(pageErrors).toEqual([]);
  expect(consoleErrors.filter((message) => !message.includes("status of 503 (Service Unavailable)"))).toEqual([]);
});
