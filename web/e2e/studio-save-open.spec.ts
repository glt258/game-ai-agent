import {expect, test} from "@playwright/test";

test("offline Studio save/open preserves Character Skill and Kit", async ({page}) => {
  await page.goto("/studio");
  await page.getByRole("button", {name: "加载示例需求"}).click();
  await page.getByRole("button", {name: "生成角色"}).click();
  await expect(page.getByText("角色方案已生成")).toBeVisible();

  await page.getByRole("button", {name: "编辑"}).click();
  await page.locator("#draft-name").fill("编辑后的辅助角色");
  await page.getByRole("button", {name: "检查修改"}).click();
  await page.getByText("查看生成与检查明细").click();
  await expect(page.getByText("修改后的方案检查通过")).toBeVisible();

  await page.getByRole("tab", {name: "技能设计"}).click();
  await expect(page.getByTestId("character-kit-summary")).toContainText("当前有 0 个技能关联");
  await page.getByRole("button", {name: "设计技能"}).click();
  await page.getByLabel("技能定位").selectOption("support");
  await page.getByLabel("技能设计需求").getByText("高级设置", {exact: true}).click();
  await page.getByLabel("离线示例").selectOption("character_support_skill_v1");
  await page.getByRole("region", {name: "技能设计需求"}).getByLabel("生成方式").selectOption("offline");
  await page.getByRole("button", {name: "生成技能"}).click();
  await expect(page.getByRole("button", {name: "绑定到角色"})).toBeEnabled();
  await page.getByRole("button", {name: "绑定到角色"}).click();
  await expect(page.getByTestId("character-kit-summary")).toContainText("当前有 1 个技能关联");

  await page.getByRole("button", {name: "保存角色"}).click();
  await expect(page.getByRole("button", {name: "已保存"})).toBeVisible();

  await page.goto("/saved-characters");
  await expect(page.getByRole("heading", {name: "Saved Characters"})).toBeVisible();
  await page.getByRole("article").filter({hasText: "编辑后的辅助角色"}).first().getByRole("link", {name: "Open"}).click();
  await expect(page).toHaveURL(/\/studio\?character=/);
  await expect(page.getByText("角色方案已生成")).toBeVisible();
  await page.getByRole("tab", {name: "技能设计"}).click();
  await expect(page.getByTestId("character-kit-summary")).toContainText("当前有 1 个技能关联");

  await page.getByRole("tab", {name: "角色方案"}).click();
  await page.getByRole("button", {name: "编辑"}).click();
  await page.locator("#draft-occupation").fill("现场协调员");
  await page.getByRole("button", {name: "保存角色"}).click();
  await expect(page.getByRole("button", {name: "已保存"})).toBeVisible();
});

test("offline Character Studio shows the Chinese planner result and technical details", async ({page}) => {
  await page.goto("/studio");
  await page.getByRole("button", {name: "加载示例需求"}).click();
  await page.getByRole("button", {name: "生成角色"}).click();
  await expect(page.getByTestId("character-planner-view")).toBeVisible();
  await expect(page.getByTestId("character-planner-view")).toContainText("性格");
  await expect(page.getByTestId("character-planner-view")).toContainText("核心玩法");
  await expect(page.getByTestId("character-planner-view")).toContainText("设计检查");
  await page.getByRole("tab", {name: "设计检查"}).click();
  await expect(page.getByTestId("character-design-checks")).toBeVisible();
  await page.getByRole("tab", {name: "技术详情"}).click();
  await expect(page.getByTestId("character-technical-details")).toContainText("CharacterDraft 原始数据");
  await expect(page.getByTestId("character-technical-details")).toContainText("draft_id");
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

test("live Character Studio submits and polls a bounded fake job", async ({page}) => {
  const offline = await page.request.post("/api/characters/generate", {
    data: {brief: "设计一名辅助角色。", request_id: "e2e_live_fixture"},
  });
  expect(offline.ok()).toBeTruthy();
  const result = await offline.json();
  let pollCount = 0;
  await page.route(/\/api\/characters\/generate\/jobs(?:\/.*)?$/, async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({status: 202, contentType: "application/json", body: JSON.stringify({
        schema_version: "web-live-skill-job/0.1",
        job_id: "e2e-character-job",
        kind: "character_generation",
        status: "PENDING",
        provider: "local_fake",
        model: "fixture-character-model",
        poll_after_ms: 250,
      })});
      return;
    }
    pollCount += 1;
    await route.fulfill({status: 200, contentType: "application/json", body: JSON.stringify({
      schema_version: "web-live-skill-job/0.1",
      job_id: "e2e-character-job",
      kind: "character_generation",
      status: "SUCCEEDED",
      provider: "local_fake",
      model: "fixture-character-model",
      elapsed_ms: 18,
      result,
      error: null,
    })});
  });

  await page.goto("/studio");
  await page.getByRole("button", {name: "加载示例需求"}).click();
  await page.getByLabel("生成方式").selectOption("live");
  await page.getByRole("button", {name: "生成角色"}).click();
  await expect(page.getByTestId("character-planner-view")).toBeVisible();
  await expect(page.getByText("角色方案已生成")).toBeVisible();
  expect(pollCount).toBeGreaterThanOrEqual(1);
});

test("live Character Studio explains a typed provider failure without leaking details", async ({page}) => {
  await page.route(/\/api\/characters\/generate\/jobs(?:\/.*)?$/, async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({status: 202, contentType: "application/json", body: JSON.stringify({
        schema_version: "web-live-skill-job/0.1",
        job_id: "e2e-character-provider-failure",
        kind: "character_generation",
        status: "PENDING",
        provider: "opencode_go",
        model: "deepseek-v4-flash",
        poll_after_ms: 250,
      })});
      return;
    }
    await route.fulfill({status: 200, contentType: "application/json", body: JSON.stringify({
      schema_version: "web-live-skill-job/0.1",
      job_id: "e2e-character-provider-failure",
      kind: "character_generation",
      status: "FAILED",
      provider: "opencode_go",
      model: "deepseek-v4-flash",
      elapsed_ms: 2875,
      result: null,
      error: {
        code: "PROVIDER_FAILURE",
        message: "模型服务调用失败，请稍后重试。",
        stage: "generation_provider_invocation",
        retryable: false,
        details: {
          provider: "opencode_go",
          model: "deepseek-v4-flash",
          provider_status_code: null,
          provider_retryable: null,
          attempt_count: 1,
          retry_count: 0,
        },
        audit: {
          stage: "generation_provider_invocation",
          model_invocations: [{
            provider: "opencode_go",
            model: "deepseek-v4-flash",
            turn_number: 1,
            outcome: "provider",
            latency_ms: 2875,
            retry_count: 0,
            finish_reason: null,
            tool_call_count: 0,
            usage: null,
            purpose: "generation",
            provider_status_code: null,
            provider_retryable: null,
            provider_request_id: "req-f3-safe",
            upstream_status: 400,
            upstream_error_type: "invalid_request_error",
            upstream_error_code: "unsupported_tool_schema",
            upstream_error_param: "tools",
            attempts: [{
              attempt_number: 1,
              outcome: "provider",
              latency_ms: 2875,
              error_code: "provider",
              provider_request_id: "req-f3-safe",
              upstream_status: 400,
              upstream_error_type: "invalid_request_error",
              upstream_error_code: "unsupported_tool_schema",
              upstream_error_param: "tools",
              finish_reason: null,
              usage: null,
            }],
          }],
        },
      },
    })});
  });

  await page.goto("/studio");
  await page.getByRole("button", {name: "加载示例需求"}).click();
  await page.getByLabel("生成方式").selectOption("live");
  await page.getByRole("button", {name: "生成角色"}).click();

  await expect(page.getByText("模型服务调用失败，请稍后重试。")).toBeVisible();
  const diagnostics = page.getByTestId("character-failure-diagnostics");
  await diagnostics.locator("summary").click();
  await expect(diagnostics).toContainText("PROVIDER_FAILURE");
  await expect(diagnostics).toContainText("generation_provider_invocation");
  await expect(diagnostics).toContainText("opencode_go / deepseek-v4-flash");
  await expect(diagnostics).toContainText("1 / 0");
  await expect(diagnostics).toContainText("400");
  await expect(diagnostics).toContainText("invalid_request_error");
  await expect(diagnostics).toContainText("unsupported_tool_schema");
  await expect(diagnostics).toContainText("tools");
  await expect(diagnostics).toContainText("req-f3-safe");
});
