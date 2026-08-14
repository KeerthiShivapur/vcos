import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const API = "http://localhost:8999/api/v1";
const ACTIONS = `${API}/brain/knowledge/actions`;

function ts(): string {
  return Date.now().toString().slice(-8);
}

async function apiLogin(ctx: APIRequestContext, email: string, password: string) {
  const r = await ctx.post(`${API}/auth/login`, { data: { email, password } });
  expect(r.status(), await r.text()).toBe(200);
  return (await r.json()) as { access_token: string };
}

async function registerOrg(page: Page, name: string, slug: string, email: string, fullName: string, password: string) {
  await page.goto("/register");
  await page.getByLabel("Company name").fill(name);
  await page.getByLabel("Company slug (unique address)").fill(slug);
  await page.getByLabel("Industry").fill("Software");
  await page.getByLabel("Country").fill("United States");
  await page.getByLabel("Your full name (founder / administrator)").fill(fullName);
  await page.getByLabel("Work email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByLabel("Confirm password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Register organization" }).click();
  await page.waitForURL("**/home", { timeout: 20_000 });
}

async function dispatchAll(request: APIRequestContext, auth: Record<string, string>, limit = 500) {
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

async function seedBudgetConflict(request: APIRequestContext, auth: Record<string, string>) {
  const me = (await (await request.get(`${API}/employees/me`, { headers: auth })).json()) as {
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
    const sent = await request.post(`${API}/conversations/${conv.id}/messages`, {
      headers: auth,
      data: { content },
    });
    expect(sent.status(), await sent.text()).toBe(201);
  }
  await dispatchAll(request, auth);
}

async function conflictRecommendation(request: APIRequestContext, auth: Record<string, string>) {
  const deadline = Date.now() + 300_000;
  while (Date.now() < deadline) {
    const r = await request.get(`${API}/brain/knowledge/recommendations`, {
      headers: auth,
      params: { limit: "50" },
    });
    expect(r.status(), await r.text()).toBe(200);
    const body = (await r.json()) as {
      recommendations: Array<{ id: string; kind: string }>;
    };
    const conflict = body.recommendations.find((rec) => rec.kind === "conflict");
    if (conflict) return conflict;
    await dispatchAll(request, auth, 500);
    await new Promise((resolve) => setTimeout(resolve, 3_000));
  }
  throw new Error("the equal-authority budget conflict never materialized a recommendation");
}

async function propose(request: APIRequestContext, auth: Record<string, string>, body: Record<string, unknown>) {
  const r = await request.post(ACTIONS, { headers: auth, data: body });
  expect(r.status(), await r.text()).toBe(201);
  return (await r.json()) as { id: string; state: string };
}

async function transition(request: APIRequestContext, auth: Record<string, string>, actionId: string, transition: string, body: Record<string, unknown> = {}) {
  const r = await request.post(`${ACTIONS}/${actionId}/transition`, {
    headers: auth,
    data: { transition, ...body },
  });
  expect(r.status(), await r.text()).toBe(200);
  return (await r.json()) as { state: string };
}

test("slice 4e.6: knowledge becomes governed company action, executed, verified and measured — in the Action Center UI", async ({ browser, request }) => {
  test.setTimeout(900_000);
  const t = ts();
  const email = `kact${t}@acme.com`;
  const password = "StrongPass123!";

  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  page.on("console", (msg) => {
    if (msg.type() === "error") console.log(`[${Date.now() % 100000}] console:error ${msg.text().slice(0, 200)}`);
  });
  page.on("requestfailed", (req) =>
    console.log(`[${Date.now() % 100000}] REQ-FAIL ${req.method()} ${req.url().slice(0, 90)} :: ${req.failure()?.errorText}`)
  );

  await registerOrg(page, `KAct Co ${t}`, `kact-${t}`, email, "Iris", password);
  const token = (await apiLogin(request, email, password)).access_token;
  const auth = { Authorization: `Bearer ${token}` };

  // ---------------------------------------------------------------- seeding
  await seedBudgetConflict(request, auth);
  const rec = await conflictRecommendation(request, auth);

  // ---------------------------------------------------------------- API
  // 1) Proposal with lineage: medium risk -> governed awaiting_approval.
  const proposed = await propose(request, auth, {
    action_type: "task",
    title: "Escalate the budget conflict",
    risk: "medium",
    source_recommendation_id: rec.id,
  });
  expect(proposed.state).toBe("awaiting_approval");

  // 2) Exact-once: replay dedups to the same action.
  const replayed = await request.post(ACTIONS, {
    headers: auth,
    data: {
      action_type: "task",
      title: "Escalate the budget conflict",
      risk: "medium",
      source_recommendation_id: rec.id,
    },
  });
  expect(replayed.status(), await replayed.text()).toBe(201);
  expect((await replayed.json()).deduplicated).toBe(true);

  // 3) Approve -> the action materializes a real task in the operating layer.
  const ready = await transition(request, auth, proposed.id, "approve", { note: "approved by lead" });
  expect(ready.state).toBe("ready");

  // 4) Run the lifecycle to verified with an audited trail.
  await transition(request, auth, proposed.id, "assign", { assignee_id: "opsteam" });
  await transition(request, auth, proposed.id, "start", { note: "go" });
  await transition(request, auth, proposed.id, "complete", { note: "done" });
  const verified = await transition(request, auth, proposed.id, "verify", { note: "verified" });
  expect(verified.state).toBe("verified");

  const detail = (await (await request.get(`${ACTIONS}/${proposed.id}`, { headers: auth })).json()) as {
    state: string;
    source_recommendation_id: string;
    events: Array<{ event: string }>;
    outcome: unknown;
    dependencies: unknown[];
  };
  expect(detail.source_recommendation_id).toBe(rec.id);
  expect(detail.events[0].event).toBe("action.verified");
  expect(detail.events.some((e) => e.event === "action.created")).toBe(true);

  // 5) Outcome intelligence: the loop back into company intelligence.
  const outcome = await request.post(`${ACTIONS}/${proposed.id}/outcome`, {
    headers: auth,
    data: { outcome_type: "success", verdict: "conflict resolved", effectiveness: 0.9 },
  });
  expect(outcome.status(), await outcome.text()).toBe(200);
  const intel = (await (await request.get(`${ACTIONS}/outcome-intelligence`, { headers: auth })).json()) as {
    total: number;
    success_rate: number;
  };
  expect(intel.total).toBeGreaterThanOrEqual(1);
  expect(intel.success_rate).toBeGreaterThan(0);

  // 6) Overdue action escalates through the idempotent evaluate pass.
  const overdue = await propose(request, auth, {
    action_type: "task",
    title: "Overdue rollout review",
    risk: "low",
  });
  await transition(request, auth, overdue.id, "start", { note: "go", due_at: "2000-01-01T00:00:00Z" });
  const evaluated = await (
    await request.post(`${ACTIONS}/evaluate`, { headers: auth, data: {} })
  ).json() as { escalated: number };
  expect(evaluated.escalated).toBeGreaterThanOrEqual(1);

  // 7) NL intents route deterministically through the universal query.
  for (const [question, intent] of [
    ["what needs my attention", "attention"],
    ["what is blocked", "blocked"],
    ["which actions are overdue", "overdue"],
    ["show my actions", "actions"],
  ]) {
    const resp = (await (
      await request.post(`${API}/brain/knowledge/query`, { headers: auth, data: { question } })
    ).json()) as { intent: string };
    expect(resp.intent, question).toBe(intent);
  }

  // 8) Tenant isolation: a rival org sees nothing.
  const rival = await (
    await request.post(`${API}/auth/register`, {
      data: {
        organization_name: `Rival ${t}`,
        organization_slug: `riv-${t}`,
        industry: "Software",
        country: "US",
        timezone: "UTC",
        currency: "USD",
        full_name: "Riv",
        email: `riv${t}@rival.com`,
        username: `riv${t}`,
        password,
      },
    })
  ).json() as { access_token: string };
  const rivalHeaders = { Authorization: `Bearer ${rival.access_token}` };
  const rivalCenter = (await (
    await request.get(ACTIONS, { headers: rivalHeaders })
  ).json()) as { total: number };
  expect(rivalCenter.total).toBe(0);

  // ---------------------------------------------------------------- UI
  // 9) The Company Action Center: stats, filters, propose, and the governed
  //    lifecycle with an immutable audit trail.
  await page.goto("/knowledge/workspace/actions");
  await expect(page.getByText("One governed surface for every company action").first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("Open actions", { exact: true })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("Overdue rollout review").first()).toBeVisible({ timeout: 20_000 });

  // Attention filter surfaces only actionable items.
  await page.getByRole("combobox").first().selectOption({ label: "Needs attention" });
  await expect(page.getByText("Overdue rollout review").first()).toBeVisible({ timeout: 15_000 });

  // Propose a low-risk action from the UI — it auto-approves to ready.
  await page.getByRole("button", { name: "Propose action" }).click();
  await page.getByPlaceholder("Title — e.g. Escalate the budget conflict").fill("Publish the migration decision summary");
  await page.getByPlaceholder("Why now? (source problem — optionally leave empty to inherit from a recommendation)").fill("the settled budget stance needs a written record");
  await page.getByRole("combobox").filter({ hasText: /low risk/ }).selectOption({ label: "low risk · auto-approves" });
  await page.getByRole("button", { name: "Propose", exact: true }).click();
  await expect(page.getByText(/Action proposed: Ready/).first()).toBeVisible({ timeout: 30_000 });

  // The new low-risk action is ready (no attention flags), so reset the
  // filtered view before asserting it in the list.
  await page.getByRole("combobox").first().selectOption({ label: "All views" });
  await expect(page.getByText("Publish the migration decision summary").first()).toBeVisible({ timeout: 20_000 });

  // The detail drawer shows the audit trail with the immutable events.
  await page.getByRole("button", { name: "Details" }).first().click();
  await expect(page.getByText("Audit trail (immutable)").first()).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("action.created", { exact: false }).first()).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText("action.ready", { exact: false }).first()).toBeVisible({ timeout: 10_000 });

  // 10) The Ask surface routes the same action intents.
  await page.goto("/knowledge/workspace");
  await expect(page.getByText("Ask the company what you know")).toBeVisible({ timeout: 20_000 });
  await page.getByPlaceholder(/Ask anything about the company's knowledge/).fill("what needs my attention?");
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  await expect(page.getByText("Needs attention").first()).toBeVisible({ timeout: 30_000 });
});
