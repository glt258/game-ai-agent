import {expect, test} from "@playwright/test";

test("offline Studio save/open preserves Character Skill and Kit", async ({page}) => {
  await page.goto("/studio");
  await page.getByRole("button", {name: "Load example brief"}).click();
  await page.getByRole("button", {name: "Generate"}).click();
  await expect(page.getByText("Completed candidate")).toBeVisible();

  await page.getByRole("button", {name: "Edit"}).click();
  await page.locator("#draft-name").fill("Edited support character");
  await page.getByRole("button", {name: "Validate Changes"}).click();
  await expect(page.getByText("EDITED DRAFT VALIDATION PASSED")).toBeVisible();

  await page.getByRole("tab", {name: "Skills"}).click();
  await expect(page.getByTestId("character-kit-summary")).toContainText("0 associations");
  await page.getByRole("button", {name: "Design Skill"}).click();
  await page.getByLabel("技能定位").selectOption("support");
  await page.getByText("高级设置", {exact: true}).click();
  await page.getByLabel("离线示例").selectOption("character_support_skill_v1");
  await page.getByLabel("生成方式").selectOption("offline");
  await page.getByRole("button", {name: "生成技能"}).click();
  await expect(page.getByRole("button", {name: "绑定到角色"})).toBeEnabled();
  await page.getByRole("button", {name: "绑定到角色"}).click();
  await expect(page.getByTestId("character-kit-summary")).toContainText("1 association");

  await page.getByRole("button", {name: "Save Character"}).click();
  await expect(page.getByRole("button", {name: "Saved"})).toBeVisible();

  await page.goto("/saved-characters");
  await expect(page.getByRole("heading", {name: "Saved Characters"})).toBeVisible();
  await page.getByRole("article").filter({hasText: "Edited support character"}).first().getByRole("link", {name: "Open"}).click();
  await expect(page).toHaveURL(/\/studio\?character=/);
  await expect(page.getByText("Completed candidate")).toBeVisible();
  await page.getByRole("tab", {name: "Skills"}).click();
  await expect(page.getByTestId("character-kit-summary")).toContainText("1 association");

  await page.getByRole("tab", {name: "Character"}).click();
  await page.getByRole("button", {name: "Edit"}).click();
  await page.locator("#draft-occupation").fill("Field coordinator");
  await page.getByRole("button", {name: "Save Character"}).click();
  await expect(page.getByRole("button", {name: "Saved"})).toBeVisible();
});

test("offline Skill Playground shows the Chinese planner result and technical details", async ({page}) => {
  const consoleErrors: string[] = [];
  page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
  await page.goto("/skills");
  await expect(page.getByRole("heading", {name: "技能设计台"})).toBeVisible();
  await page.getByText("高级设置", {exact: true}).click();
  await page.getByLabel("离线示例").selectOption("generalization_sub_dps_v1");
  await page.getByRole("button", {name: "生成技能"}).click();
  await expect(page.getByRole("heading", {name: "Echo Volley"})).toBeVisible();
  await expect(page.getByTestId("planner-summary")).toContainText("副输出");
  await expect(page.getByTestId("planner-summary")).toContainText("完成行动");
  await expect(page.getByTestId("planner-summary")).toContainText("发动追加攻击");
  await expect(page.getByTestId("planner-summary")).toContainText("敌方");
  await expect(page.getByTestId("planner-summary")).toContainText("设计检查通过");
  await page.getByRole("tab", {name: "技术详情"}).click();
  await expect(page.getByTestId("planner-technical-details")).toContainText("Semantic IR");
  await expect(page.getByTestId("planner-technical-details")).toContainText("SkillKit");
  expect(consoleErrors).toEqual([]);
});

test("offline Skill Playground explains a business failure in planner language", async ({page}) => {
  await page.goto("/skills");
  await page.getByText("高级设置", {exact: true}).click();
  await page.getByLabel("技能定位").selectOption("sub_dps");
  await page.getByLabel("技能类型 / 模式").selectOption("active");
  await page.getByLabel("离线示例").selectOption("generalization_defense_v1");
  await page.getByRole("button", {name: "生成技能"}).click();
  await expect(page.getByRole("heading", {name: "Guardian Intercept"})).toBeVisible();
  await page.getByRole("tab", {name: "设计检查"}).click();
  await expect(page.getByTestId("planner-checks")).toContainText("设计检查未通过");
  await expect(page.getByTestId("planner-checks")).toContainText("缺少核心机制");
  await expect(page.getByTestId("planner-checks")).toContainText("战斗定位与技能效果不匹配");
  await expect(page.getByTestId("planner-checks")).toContainText("需要重新生成");
});
