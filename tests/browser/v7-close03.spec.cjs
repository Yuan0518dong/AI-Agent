const path = require("path");
const { test, expect } = require("@playwright/test");

let accountSequence = 0;
const evidencePath = (name) => path.resolve(__dirname, "../..", "docs", "images", name);

async function apiData(page, requestPath) {
  const response = await page.request.get(requestPath);
  expect(response.ok(), `${requestPath} returned ${response.status()}`).toBeTruthy();
  return (await response.json()).data;
}

async function registerRoleAccount(page, role) {
  accountSequence += 1;
  await page.getByRole("button", { name: "注册" }).click();
  await page.locator("#register-form [name=name]").fill(role);
  await page.locator("#register-form [name=email]").fill(`close03-${Date.now()}-${accountSequence}@example.com`);
  await page.locator("#register-form [name=password]").fill("close03-password");
  await page.locator("#register-form [name=confirmPassword]").fill("close03-password");
  await page.locator("#register-submit").click();
  await expect(page.locator("#app-shell")).toBeVisible();
}

async function createGoalAndMaterial(page, suffix) {
  const goalName = `CLOSE-03 ${suffix}目标`;
  const materialTitle = `CLOSE-03 ${suffix}资料`;
  await page.locator(".desktop-nav [data-view=goals]").click();
  await page.locator("#goal-form [name=name]").fill(goalName);
  await page.locator("#goal-form [name=subject]").fill("学习闭环验收");
  await page.locator("#goal-form [name=deadline]").fill("2026-12-31");
  await page.locator("#goal-form [name=notes]").fill("固定角色验收夹具。");
  await page.locator("#goal-submit-button").click();
  await expect(page.locator("#goal-detail")).toContainText(goalName);

  await page.locator(".desktop-nav [data-view=materials]").click();
  await page.locator("#material-form [name=title]").fill(materialTitle);
  await page.locator("#material-form [name=content]").fill(
    "FSRS 依据学习者评级安排下一次复习。错误作答应触发可确认的复习草稿。"
  );
  await page.locator("#material-submit-button").click();
  await expect(page.locator("#material-list")).toContainText(materialTitle);

  const materials = await apiData(page, "/api/materials");
  const material = materials.find((item) => item.title === materialTitle);
  expect(material).toBeTruthy();
  return { goalName, material };
}

async function createWrongAnswerAndWaitForConfirmation(page, goalName) {
  await page.locator(".desktop-nav [data-view=memory]").click();
  const quizForm = page.locator(".quiz-answer-form").first();
  await expect(quizForm).toBeVisible();
  await quizForm.locator("textarea[name=answer]").fill("香蕉");
  await quizForm.getByRole("button", { name: "提交批改" }).click();
  await expect(page.locator("#quiz-list .quiz-feedback.review")).toBeVisible();

  await page.locator(".desktop-nav [data-view=agent]").click();
  await page.locator("#agent-goal-select").selectOption({ label: goalName });
  await page.locator("#agent-run-objective").fill("根据本次错题生成待确认复习草稿。" );
  await page.locator("#agent-run-start").click();
  await expect(page.locator("#toast")).toContainText("已完成第一步");
  await page.locator("#agent-current-action").getByRole("button", { name: "执行下一步" }).click();
  await expect(page.locator("#agent-current-action").getByRole("button", { name: "接受" })).toBeVisible();
}

async function selectFlashcard(page, flashcardId, cardCount) {
  for (let index = 0; index < cardCount; index += 1) {
    if (await page.locator("#flashcard").getAttribute("data-flashcard-id") === flashcardId) return;
    await page.locator("#shuffle-cards").click();
  }
  expect(await page.locator("#flashcard").getAttribute("data-flashcard-id")).toBe(flashcardId);
}

test("CLOSE-03 first-use role can find the cited learning path", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await registerRoleAccount(page, "首次使用者");
  await expect(page.locator("#getting-started")).toBeVisible();
  const { material } = await createGoalAndMaterial(page, "首次使用");

  await page.locator(".desktop-nav [data-view=study]").click();
  await page.locator(`#summary-list [data-action=generate-chunks][data-material-id="${material.id}"]`).click();
  await expect(page.locator("#toast")).toContainText("学习片段已生成");
  await page.locator("#chat-form [name=question]").fill("资料中 FSRS 的安排依据是什么？");
  await page.locator("#chat-form button[type=submit]").click();
  await expect(page.locator(".message-reference-chunks")).toContainText(material.title);
  await page.screenshot({ path: evidencePath("close03-first-use-role.png"), fullPage: true });
});

test("CLOSE-03 weak-answer role completes confirmation, FSRS, and Today changes", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await registerRoleAccount(page, "错题学习者");
  const { goalName, material } = await createGoalAndMaterial(page, "错题学习");
  const initialCards = await apiData(page, `/api/materials/${material.id}/flashcards`);
  await createWrongAnswerAndWaitForConfirmation(page, goalName);

  await page.locator("#agent-current-action").getByRole("button", { name: "接受" }).click();
  await expect(page.locator("#toast")).toContainText("已确认当前步骤");
  const cardsAfterConfirmation = await apiData(page, `/api/materials/${material.id}/flashcards`);
  expect(cardsAfterConfirmation).toHaveLength(initialCards.length + 1);
  const formalCard = cardsAfterConfirmation.find((card) => !initialCards.some((initial) => initial.id === card.id));
  expect(formalCard).toEqual(expect.objectContaining({ reviewCount: 0, lastRating: null }));

  await page.locator(".desktop-nav [data-view=memory]").click();
  await selectFlashcard(page, formalCard.id, cardsAfterConfirmation.length);
  await page.locator("#card-known").click();
  const ratedCard = (await apiData(page, `/api/materials/${material.id}/flashcards`)).find((card) => card.id === formalCard.id);
  expect(ratedCard).toEqual(expect.objectContaining({ reviewCount: 1, lastRating: "good", status: "known" }));
  const today = await apiData(page, "/api/today/actions");
  expect(today.items).not.toEqual(expect.arrayContaining([
    expect.objectContaining({ kind: "due_flashcard", id: formalCard.id })
  ]));
  await page.screenshot({ path: evidencePath("close03-weak-answer-role.png"), fullPage: true });
});

test("CLOSE-03 high-risk role can defer, reject, and cancel without formal writes", async ({ page }) => {
  const materialWrites = [];
  let recordWrites = false;
  page.on("request", (request) => {
    if (!recordWrites || !request.url().includes("/api/materials")) return;
    if (!["GET", "HEAD", "OPTIONS"].includes(request.method())) materialWrites.push(request.method());
  });

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await registerRoleAccount(page, "高风险确认学习者");
  const { goalName, material } = await createGoalAndMaterial(page, "高风险确认");
  const cardsBefore = await apiData(page, `/api/materials/${material.id}/flashcards`);
  await createWrongAnswerAndWaitForConfirmation(page, goalName);
  await expect(page.locator("#agent-current-action")).toContainText("安全检查");

  recordWrites = true;
  await page.locator("#agent-current-action").getByRole("button", { name: "暂不处理" }).click();
  expect(materialWrites).toEqual([]);
  await page.locator("#agent-current-action").getByRole("button", { name: "继续查看" }).click();
  await page.locator("#agent-current-action").getByRole("button", { name: "拒绝" }).click();
  await expect(page.locator("#toast")).toContainText("已拒绝写入");
  const cardsAfterReject = await apiData(page, `/api/materials/${material.id}/flashcards`);
  expect(cardsAfterReject.map((card) => card.id)).toEqual(cardsBefore.map((card) => card.id));
  expect(materialWrites).toEqual([]);

  await page.locator("#agent-current-action").getByRole("button", { name: "取消任务" }).click();
  await expect(page.locator("#toast")).toContainText("智能任务已取消");
  await expect(page.locator("#agent-run-detail")).toContainText("已取消");
  await page.screenshot({ path: evidencePath("close03-high-risk-role.png"), fullPage: true });
});
