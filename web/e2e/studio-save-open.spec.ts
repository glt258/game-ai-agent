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
  await page.getByLabel("Family").selectOption("support");
  await page.getByLabel("Offline example").selectOption("character_support_skill_v1");
  await page.getByLabel("Execution mode").selectOption("offline");
  await page.getByRole("button", {name: "Run pipeline"}).click();
  await expect(page.getByRole("button", {name: "Attach to Character"})).toBeEnabled();
  await page.getByRole("button", {name: "Attach to Character"}).click();
  await expect(page.getByTestId("character-kit-summary")).toContainText("1 association");

  await page.getByRole("button", {name: "Save Character"}).click();
  await expect(page.getByRole("button", {name: "Saved"})).toBeVisible();

  await page.goto("/saved-characters");
  await expect(page.getByRole("heading", {name: "Saved Characters"})).toBeVisible();
  await page.getByRole("link", {name: "Open"}).click();
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
