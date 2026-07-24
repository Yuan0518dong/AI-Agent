const { test, expect } = require("@playwright/test");
const AxeBuilder = require("@axe-core/playwright").default;

const GOAL_NAME = "CLOSE-02 黄金流程目标";
const MATERIAL_TITLE = "CLOSE-02 间隔重复资料";

async function apiData(page, path) {
  const response = await page.request.get(path);
  expect(response.ok(), `${path} returned ${response.status()}`).toBeTruthy();
  return (await response.json()).data;
}

async function assertNoSeriousAccessibilityViolations(page) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  const serious = results.violations.filter((violation) => ["serious", "critical"].includes(violation.impact));
  expect(serious.flatMap((violation) => violation.nodes.map(
    (node) => `${violation.id} ${node.target.join(" ")}: ${node.failureSummary}`
  ))).toEqual([]);
}

async function createIsolatedAccount(page) {
  await page.locator("#show-register").click();
  await page.locator("#register-form [name=name]").fill("Golden Flow Browser");
  await page.locator("#register-form [name=email]").fill(`close02-${Date.now()}@example.com`);
  await page.locator("#register-form [name=password]").fill("close02-password");
  await page.locator("#register-form [name=confirmPassword]").fill("close02-password");
  await page.locator("#register-submit").click();
  await expect(page.locator("#app-shell")).toBeVisible();
}

async function selectGoldenFlashcard(page, flashcardId, cardCount) {
  for (let index = 0; index < cardCount; index += 1) {
    if (await page.locator("#flashcard").getAttribute("data-flashcard-id") === flashcardId) return;
    await page.locator("#shuffle-cards").click();
  }
  expect(await page.locator("#flashcard").getAttribute("data-flashcard-id")).toBe(flashcardId);
}

test("CLOSE-02 keeps the goal-to-today golden learning loop confirmable and reproducible", async ({ page }) => {
  const pageErrors = [];
  const consoleErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await createIsolatedAccount(page);

  await page.locator(".desktop-nav [data-view=goals]").click();
  await page.locator("#goal-form [name=name]").fill(GOAL_NAME);
  await page.locator("#goal-form [name=subject]").fill("间隔重复");
  await page.locator("#goal-form [name=deadline]").fill("2026-12-31");
  await page.locator("#goal-form [name=notes]").fill("验证目标、资料、错题和复习写入的一条可解释路径。");
  await page.locator("#goal-submit-button").click();
  await expect(page.locator("#goal-detail")).toContainText(GOAL_NAME);

  await page.locator("#goal-shortcuts [data-goal-destination=materials]").click();
  await page.locator("#material-form [name=title]").fill(MATERIAL_TITLE);
  await page.locator("#material-form [name=content]").fill(
    "FSRS 根据用户的评级调整下一次复习时间。间隔重复通过回忆和反馈识别薄弱点。"
  );
  await page.locator("#material-submit-button").click();
  await expect(page.locator("#material-list")).toContainText(MATERIAL_TITLE);
  await expect(page.locator("#material-list")).toContainText("2 个知识点");

  const materials = await apiData(page, "/api/materials");
  const material = materials.find((item) => item.title === MATERIAL_TITLE);
  expect(material).toBeTruthy();
  const initialCards = await apiData(page, `/api/materials/${material.id}/flashcards`);
  expect(initialCards).toHaveLength(2);

  await page.locator(".desktop-nav [data-view=study]").click();
  await page.locator(`#summary-list [data-action=generate-chunks][data-material-id="${material.id}"]`).click();
  await expect(page.locator("#toast")).toContainText("学习片段已生成");
  expect(await apiData(page, `/api/materials/${material.id}/chunks`)).not.toHaveLength(0);
  await page.locator("#chat-form [name=question]").fill("资料中 FSRS 如何影响下一次复习时间？");
  await page.locator("#chat-form button[type=submit]").click();
  await expect(page.locator(".message-reference-chunks")).toContainText(MATERIAL_TITLE);

  await page.locator(".desktop-nav [data-view=memory]").click();
  const quizForm = page.locator(".quiz-answer-form").first();
  await expect(quizForm).toBeVisible();
  await quizForm.locator("textarea[name=answer]").fill("香蕉");
  await quizForm.getByRole("button", { name: "提交批改" }).click();
  await expect(page.locator("#quiz-list .quiz-feedback.review")).toBeVisible();
  const attempts = await apiData(page, `/api/materials/${material.id}/quiz/attempts`);
  expect(attempts).toHaveLength(1);
  expect(attempts[0].isCorrect).toBe(false);

  const todayAfterWrongAnswer = await apiData(page, "/api/today/actions");
  expect(todayAfterWrongAnswer.items).toEqual(expect.arrayContaining([
    expect.objectContaining({ kind: "weak_point", target: expect.objectContaining({ materialId: material.id }) })
  ]));

  await page.locator(".desktop-nav [data-view=agent]").click();
  await page.locator("#agent-goal-select").selectOption({ label: GOAL_NAME });
  await page.locator("#agent-run-objective").fill("根据本次错题生成待确认复习草稿。" );
  await page.locator("#agent-run-start").click();
  await expect(page.locator("#toast")).toContainText("已完成第一步");
  await expect(page.locator("#agent-run-detail")).toContainText("生成复习草稿");
  await expect(page.locator("#agent-current-action").getByRole("button", { name: "执行下一步" })).toBeVisible();

  const cardsBeforeConfirmation = await apiData(page, `/api/materials/${material.id}/flashcards`);
  expect(cardsBeforeConfirmation.map((card) => card.id)).toEqual(initialCards.map((card) => card.id));
  await page.locator("#agent-current-action").getByRole("button", { name: "执行下一步" }).click();
  await expect(page.locator("#agent-current-action").getByRole("button", { name: "接受" })).toBeVisible();
  const cardsWhileWaiting = await apiData(page, `/api/materials/${material.id}/flashcards`);
  expect(cardsWhileWaiting.map((card) => card.id)).toEqual(initialCards.map((card) => card.id));

  const todayWithPendingDraft = await apiData(page, "/api/today/actions");
  expect(todayWithPendingDraft.items).toEqual(expect.arrayContaining([
    expect.objectContaining({ kind: "pending_confirmation" })
  ]));

  await page.locator("#agent-current-action").getByRole("button", { name: "接受" }).click();
  await expect(page.locator("#toast")).toContainText("已确认当前步骤");
  const cardsAfterConfirmation = await apiData(page, `/api/materials/${material.id}/flashcards`);
  expect(cardsAfterConfirmation).toHaveLength(initialCards.length + 1);
  const formalCard = cardsAfterConfirmation.find((card) => !initialCards.some((initial) => initial.id === card.id));
  expect(formalCard).toEqual(expect.objectContaining({
    materialId: material.id,
    reviewCount: 0,
    lastRating: null
  }));

  const todayWithFormalCard = await apiData(page, "/api/today/actions");
  expect(todayWithFormalCard.items).toEqual(expect.arrayContaining([
    expect.objectContaining({ kind: "due_flashcard", id: formalCard.id })
  ]));

  await page.locator(".desktop-nav [data-view=memory]").click();
  await selectGoldenFlashcard(page, formalCard.id, cardsAfterConfirmation.length);

  const fsrsReviewResponse = page.waitForResponse((response) => {
    return new URL(response.url()).pathname === `/api/materials/${material.id}/flashcards/${formalCard.id}`
      && response.request().method() === "PATCH" && response.ok();
  });
  await page.locator("#card-known").click();
  const fsrsReview = (await fsrsReviewResponse).json();
  expect((await fsrsReview).data).toEqual(expect.objectContaining({
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
  await page.locator(".mobile-bottom-nav [data-view=today]").click();
  await expect(page.locator("#today-actions-count")).not.toHaveText("加载中");
  const widths = await page.evaluate(() => ({
    viewport: window.innerWidth,
    document: document.documentElement.scrollWidth,
    body: document.body.scrollWidth
  }));
  expect(widths.document).toBeLessThanOrEqual(widths.viewport);
  expect(widths.body).toBeLessThanOrEqual(widths.viewport);
  await assertNoSeriousAccessibilityViolations(page);
  await page.screenshot({ path: "docs/images/close02-golden-flow-mobile.png", fullPage: true });

  expect(pageErrors).toEqual([]);
  expect(consoleErrors.filter((message) => !message.includes("status of 401 (Unauthorized)"))).toEqual([]);
});
