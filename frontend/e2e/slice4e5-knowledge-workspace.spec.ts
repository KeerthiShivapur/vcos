import {
  expect,
  test,
  type APIRequestContext,
  type Page,
} from "@playwright/test";

const API = "http://localhost:8999/api/v1";

function ts(): string {
  return Date.now().toString().slice(-8);
}

async function apiLogin(
  ctx: APIRequestContext,
  email: string,
  password: string,
) {
  const r = await ctx.post(`${API}/auth/login`, { data: { email, password } });
  expect(r.status(), await r.text()).toBe(200);
  return (await r.json()) as { access_token: string };
}

async function registerOrg(
  page: Page,
  name: string,
  slug: string,
  email: string,
  fullName: string,
  password: string,
) {
  await page.goto("/register");
  await page.getByLabel("Company name").fill(name);
  await page.getByLabel("Company slug (unique address)").fill(slug);
  await page.getByLabel("Industry").fill("Software");
  await page.getByLabel("Country").fill("United States");
  await page
    .getByLabel("Your full name (founder / administrator)")
    .fill(fullName);
  await page.getByLabel("Work email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByLabel("Confirm password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Register organization" }).click();
  await page.waitForURL("**/home", { timeout: 20_000 });
}

async function dispatchAll(
  request: APIRequestContext,
  auth: Record<string, string>,
  limit = 500,
) {
  for (let round = 0; round < 10; round++) {
    const r = await request.post(`${API}/intelligence/events/process`, {
      headers: auth,
      params: { limit: String(limit) },
    });
    expect(r.status(), await r.text()).toBe(200);
    const body = (await r.json()) as { processed: number };
    if (body.processed === 0) return;
  }
}

/** Seed an equal-authority budget conflict -> contradiction insights, a
 * conflict recommendation, and the "migration" knowledge topic. */
async function seedBudgetConflict(
  request: APIRequestContext,
  auth: Record<string, string>,
) {
  const me = (await (
    await request.get(`${API}/employees/me`, { headers: auth })
  ).json()) as {
    id: string;
  };
  const conv = await (
    await request.post(`${API}/conversations`, {
      headers: auth,
      data: { type: "channel", title: "budget", member_ids: [me.id] },
    })
  ).json();
  for (const content of [
    "The migration budget is 5 lakh.",
    "The migration budget is 10 lakh.",
  ]) {
    const sent = await request.post(
      `${API}/conversations/${conv.id}/messages`,
      {
        headers: auth,
        data: { content },
      },
    );
    expect(sent.status(), await sent.text()).toBe(201);
  }
  await dispatchAll(request, auth);
}

interface Insight {
  id: string;
  kind: string;
  title: string;
  status: string;
  topic_name: string | null;
  confidence: number;
}

async function insights(
  request: APIRequestContext,
  auth: Record<string, string>,
): Promise<Insight[]> {
  const r = await request.get(`${API}/brain/knowledge/insights`, {
    headers: auth,
    params: { limit: "100" },
  });
  expect(r.status(), await r.text()).toBe(200);
  return ((await r.json()) as { insights: Insight[] }).insights;
}

test("slice 4e.5: the knowledge operating layer works end-to-end from evidence to command, in the workspace UI", async ({
  browser,
  request,
}) => {
  test.setTimeout(900_000);
  const t = ts();
  const email = `kops${t}@acme.com`;
  const password = "StrongPass123!";

  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  page.on("console", (msg) => {
    if (msg.type() === "error")
      console.log(
        `[${Date.now() % 100000}] console:error ${msg.text().slice(0, 200)}`,
      );
  });
  page.on("requestfailed", (req) =>
    console.log(
      `[${Date.now() % 100000}] REQ-FAIL ${req.method()} ${req.url().slice(0, 90)} :: ${req.failure()?.errorText}`,
    ),
  );

  await registerOrg(page, `KOps Co ${t}`, `kops-${t}`, email, "Iris", password);
  const token = (await apiLogin(request, email, password)).access_token;
  const auth = { Authorization: `Bearer ${token}` };

  // ---------------------------------------------------------------- seeding
  // Two equal-authority messages contradict -> contradiction + decision_required
  // insights, a conflict recommendation, and the canonical topic "migration".
  await seedBudgetConflict(request, auth);

  // ---------------------------------------------------------------- API
  const materialized = await insights(request, auth);
  const contradiction = materialized.find((i) => i.kind === "contradiction");
  expect(
    contradiction,
    "the equal-authority budget conflict becomes a contradiction insight",
  ).toBeTruthy();
  expect(contradiction!.status).toBe("active");
  const decision = materialized.find((i) => i.kind === "decision_required");
  expect(
    decision,
    "an active contradiction with no open decision requires leadership",
  ).toBeTruthy();
  expect(contradiction!.topic_name).toBe("migration");

  // Exact-once: a second read returns the same rows.
  const again = await insights(request, auth);
  expect(again.map((i) => i.id).sort()).toEqual(
    materialized.map((i) => i.id).sort(),
  );

  // Recommendations: the conflict is persisted as a recommendation.
  const recRes = await request.get(`${API}/brain/knowledge/recommendations`, {
    headers: auth,
    params: { limit: "50" },
  });
  expect(recRes.status(), await recRes.text()).toBe(200);
  const recs = (await recRes.json()) as {
    recommendations: Array<{
      id: string;
      kind: string;
      lifecycle: string;
      status: string;
    }>;
  };
  const conflict = recs.recommendations.find((r) => r.kind === "conflict");
  expect(
    conflict,
    "the budget conflict materializes a recommendation",
  ).toBeTruthy();
  expect(conflict!.lifecycle).toBe("detected");

  // Temporal: evolution chain retains both versions.
  const evolutionRes = await request.get(
    `${API}/brain/knowledge/topics/migration/evolution`,
    { headers: auth },
  );
  expect(evolutionRes.status(), await evolutionRes.text()).toBe(200);
  const evolution = (await evolutionRes.json()) as {
    topic: { name: string };
    total: number;
    steps: Array<{ statement: string; supersedes: string | null }>;
  };
  expect(evolution.topic.name).toBe("migration");
  expect(evolution.total).toBeGreaterThanOrEqual(2);
  expect(evolution.steps.some((s) => s.supersedes !== null)).toBe(true);

  // Propagation: the topic's sources are reachable.
  const propRes = await request.get(
    `${API}/brain/knowledge/topics/migration/propagation`,
    { headers: auth, params: { depth: "3" } },
  );
  expect(propRes.status(), await propRes.text()).toBe(200);
  expect(
    ((await propRes.json()) as { total: number }).total,
  ).toBeGreaterThanOrEqual(2);

  // Health center + coverage + brief all serve.
  const healthRes = await request.get(`${API}/brain/knowledge/health-center`, {
    headers: auth,
  });
  expect(healthRes.status(), await healthRes.text()).toBe(200);
  const health = (await healthRes.json()) as {
    score: number;
    drill_down: { contradictions: number; total_topics: number };
  };
  expect(health.score).toBeGreaterThanOrEqual(0);
  expect(health.score).toBeLessThanOrEqual(100);
  expect(health.drill_down.contradictions).toBeGreaterThanOrEqual(1);
  expect(health.drill_down.total_topics).toBeGreaterThanOrEqual(1);

  const covRes = await request.get(`${API}/brain/knowledge/coverage`, {
    headers: auth,
  });
  expect(covRes.status(), await covRes.text()).toBe(200);
  expect(((await covRes.json()) as { total: number }).total).toBeGreaterThan(0);

  const briefRes = await request.get(`${API}/brain/knowledge/brief`, {
    headers: auth,
    params: { since_hours: "72" },
  });
  expect(briefRes.status(), await briefRes.text()).toBe(200);
  const brief = (await briefRes.json()) as {
    counts: Record<string, number>;
    attention: unknown[];
  };
  for (const key of [
    "significant_changes",
    "emerging_risks",
    "major_knowledge_gaps",
    "decisions_potentially_affected",
    "projects_impacted",
  ]) {
    expect(typeof brief.counts[key]).toBe("number");
  }
  expect(Array.isArray(brief.attention)).toBe(true);

  // Universal query intents.
  const affectedQ = await (
    await request.post(`${API}/brain/knowledge/query`, {
      headers: auth,
      data: {
        question: "which projects are affected by the migration budget change?",
      },
    })
  ).json();
  expect(affectedQ.intent).toBe("affected");
  expect(affectedQ.total).toBeGreaterThanOrEqual(1);

  const worryQ = await (
    await request.post(`${API}/brain/knowledge/query`, {
      headers: auth,
      data: { question: "should we worry about the migration budget?" },
    })
  ).json();
  expect(worryQ.intent).toBe("worry");

  // ---------------------------------------------------------------- UI
  // 1) Overview + Ask: brief, health score, and a grounded routed answer.
  await page.goto("/knowledge/workspace");
  await expect(page.getByText("Ask the company what you know")).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.getByText("Executive knowledge brief")).toBeVisible({
    timeout: 30_000,
  });
  await expect(
    page.getByText("Knowledge health", { exact: false }).first(),
  ).toBeVisible({ timeout: 10_000 });

  await page
    .getByPlaceholder(/Ask anything about the company's knowledge/)
    .fill("which projects are affected by the migration budget change?");
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  await expect(
    page.getByText("What a change to this knowledge would reach"),
  ).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/depth 0/).first()).toBeVisible({
    timeout: 10_000,
  });

  // 2) Changes · Insights · Gaps: the supersession is visible, the insight
  //    detail opens, and the acknowledge lifecycle is audited.
  await page.goto("/knowledge/workspace/changes");
  await expect(page.getByText(/What changed · last 7 days/)).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByText("migration").first()).toBeVisible({
    timeout: 15_000,
  });
  await expect(page.getByText(/understanding superseded/).first()).toBeVisible({
    timeout: 15_000,
  });

  await page.getByRole("button", { name: "Insights", exact: true }).click();
  await expect(page.getByText("Universal knowledge insights")).toBeVisible({
    timeout: 20_000,
  });
  await expect(
    page.getByText("Contradiction", { exact: false }).first(),
  ).toBeVisible({ timeout: 20_000 });
  await page
    .getByRole("button")
    .filter({ hasText: "Contradiction" })
    .filter({ hasText: "migration" })
    .first()
    .click();
  await expect(page.getByText("Evidence lineage").first()).toBeVisible({
    timeout: 15_000,
  });
  await expect(page.getByText(/Audit trail/).first()).toBeVisible({
    timeout: 10_000,
  });
  await page.getByRole("button", { name: "Acknowledge", exact: true }).click();
  await expect(
    page.getByText("acknowledged", { exact: true }).first(),
  ).toBeVisible({ timeout: 20_000 });

  // 3) Command Center: the full lifecycle review -> accept -> convert ->
  //    execute -> verify, landing a real task in the governed operating layer.
  await page.goto("/knowledge/workspace/recommendations");
  await expect(page.getByText("Command Center").first()).toBeVisible({
    timeout: 20_000,
  });
  await expect(
    page.getByText("Conflict", { exact: false }).first(),
  ).toBeVisible({ timeout: 30_000 });
  const reviewButton = page.getByRole("button", { name: "Review" });
  await reviewButton.first().click();
  await expect(page.getByText("Reviewed", { exact: true }).first()).toBeVisible(
    { timeout: 20_000 },
  );
  await page.getByRole("button", { name: "Accept" }).first().click();
  await expect(page.getByText("Accepted", { exact: true }).first()).toBeVisible(
    { timeout: 20_000 },
  );
  await page.getByRole("button", { name: "Convert" }).first().click();
  await expect(
    page.getByText("Converted", { exact: true }).first(),
  ).toBeVisible({ timeout: 20_000 });
  await page.getByRole("button", { name: "Execute" }).first().click();
  await expect(page.getByText("Executed", { exact: true }).first()).toBeVisible(
    { timeout: 20_000 },
  );
  await page
    .getByPlaceholder("Verification note (required)")
    .fill("verified through the command center");
  await page.getByRole("button", { name: "Verify" }).click();
  // Resolved rows leave the command center with an explicit notice.
  await expect(page.getByText(/^Verified — /).first()).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.getByText("No active recommendations").first()).toBeVisible(
    { timeout: 20_000 },
  );

  // The convert created a real governed task.
  const tasksRes = await request.get(`${API}/tasks`, {
    headers: auth,
    params: { status: "backlog" },
  });
  expect(tasksRes.status(), await tasksRes.text()).toBe(200);
  const tasks = (await tasksRes.json()) as Array<{ id: string; title: string }>;
  const created = tasks.find((task) => task.title.startsWith("[Knowledge]"));
  expect(
    created,
    "the recommendation converts into a governed task",
  ).toBeTruthy();

  // 4) Impact Analysis: topic explorer resolves "migration" and traces it.
  await page.goto("/knowledge/workspace/impact");
  await expect(page.getByText("Impact analysis").first()).toBeVisible({
    timeout: 20_000,
  });
  await page
    .getByPlaceholder(/Search the company's knowledge topics/)
    .fill("migration");
  await page.getByRole("button", { name: "Find topic" }).click();
  await expect(
    page.getByRole("button", { name: /migration/ }).first(),
  ).toBeVisible({ timeout: 20_000 });
  await page
    .getByRole("button", { name: /migration/ })
    .first()
    .click();
  await expect(page.getByText("What a change reaches")).toBeVisible({
    timeout: 30_000,
  });
  await expect(
    page.getByRole("heading", { name: "How the understanding evolved" }),
  ).toBeVisible({ timeout: 15_000 });

  // 5) Evolution Timeline: the supersession chain and the state picker.
  await page.goto("/knowledge/workspace/timeline");
  await expect(page.getByText("Evolution timeline").first()).toBeVisible({
    timeout: 20_000,
  });
  await page.getByPlaceholder(/Search topics/).fill("migration");
  await page.getByRole("button", { name: "Find topic" }).click();
  await expect(
    page.getByText("migration", { exact: true }).first(),
  ).toBeVisible({ timeout: 20_000 });
  await page.getByText("migration", { exact: true }).first().click();
  await expect(page.getByText("What was true then")).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.getByText(/· \d+ versions?/).first()).toBeVisible({
    timeout: 20_000,
  });
  await expect(
    page.getByText(/each step shows what superseded what/).first(),
  ).toBeVisible({ timeout: 15_000 });

  // 6) Health Center: score, seven bars, per-area coverage.
  await page.goto("/knowledge/workspace/health");
  await expect(
    page.getByRole("heading", { name: "Health score" }).first(),
  ).toBeVisible({ timeout: 30_000 });
  await expect(
    page.getByRole("heading", { name: "The seven bars" }),
  ).toBeVisible({ timeout: 15_000 });
  await expect(
    page.getByRole("heading", { name: "Coverage by business area" }),
  ).toBeVisible({ timeout: 15_000 });
});
