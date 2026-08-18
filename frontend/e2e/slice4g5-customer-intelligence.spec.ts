import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const API = "http://127.0.0.1:8999/api/v1";
const BRAIN = `${API}/brain`;
const CUST = `${BRAIN}/execution/customer`;
const STRATEGY = `${BRAIN}/execution/strategy`;

function ts(): string {
  return Date.now().toString().slice(-8);
}

async function apiRegister(ctx: APIRequestContext, name: string, slug: string, email: string) {
  const r = await ctx.post(`${API}/auth/register`, {
    data: {
      organization_name: name,
      organization_slug: slug,
      industry: "Software",
      country: "US",
      timezone: "UTC",
      currency: "USD",
      full_name: "Intel Founder",
      email,
      username: email.split("@")[0],
      password: "StrongPass123!",
    },
  });
  expect(r.status(), await r.text()).toBe(201);
}

async function apiLogin(ctx: APIRequestContext, email: string, password: string) {
  const r = await ctx.post(`${API}/auth/login`, { data: { email, password } });
  expect(r.status(), await r.text()).toBe(200);
  return (await r.json()) as { access_token: string };
}

async function dispatchAll(request: APIRequestContext, auth: Record<string, string>, limit = 500) {
  for (let round = 0; round < 12; round++) {
    const r = await request.post(`${API}/intelligence/events/process`, {
      headers: auth,
      params: { limit: String(limit) },
    });
    expect(r.status(), await r.text()).toBe(200);
    const body = (await r.json()) as { processed: number };
    if (body.processed === 0) return;
  }
}

async function createCustomer(
  request: APIRequestContext,
  auth: Record<string, string>,
  name: string
): Promise<string> {
  const r = await request.post(`${API}/customers`, {
    headers: auth,
    data: { company_name: name, status: "customer", segment: "enterprise", tier: "gold", industry: "Software" },
  });
  expect(r.status(), await r.text()).toBeGreaterThanOrEqual(200);
  expect(r.status(), await r.text()).toBeLessThan(300);
  return ((await r.json()) as { id: string }).id;
}

async function recordSignal(
  request: APIRequestContext,
  auth: Record<string, string>,
  customerId: string,
  summary: string,
  opts: { signal_type?: string; severity?: string; need?: string; source?: string } = {}
) {
  const r = await request.post(`${CUST}/signals`, {
    headers: auth,
    data: {
      customer_id: customerId,
      signal_type: opts.signal_type ?? "issue",
      severity: opts.severity ?? "high",
      summary,
      source: opts.source ?? "support",
      need: opts.need ?? "sso",
    },
  });
  expect(r.status(), await r.text()).toBe(200);
}

async function createProject(
  request: APIRequestContext,
  auth: Record<string, string>,
  name: string,
  code: string
): Promise<string> {
  const r = await request.post(`${API}/projects`, {
    headers: auth,
    data: { name, code, status: "active" },
  });
  expect(r.status(), await r.text()).toBe(201);
  return ((await r.json()) as { id: string }).id;
}

async function createGoal(request: APIRequestContext, auth: Record<string, string>, title: string): Promise<string> {
  const r = await request.post(`${STRATEGY}/goals`, {
    headers: auth,
    data: {
      title,
      kind: "revenue",
      priority: 1,
      metric_kind: "revenue",
      metric_unit: "pct",
      target_value: 25,
      current_value: 5,
      timeline_label: "FY2026",
    },
  });
  expect(r.status(), await r.text()).toBeGreaterThanOrEqual(200);
  expect(r.status(), await r.text()).toBeLessThan(300);
  return ((await r.json()) as { goal_id: string }).goal_id;
}

async function createObjective(
  request: APIRequestContext,
  auth: Record<string, string>,
  goalId: string,
  title: string
): Promise<string> {
  const r = await request.post(`${STRATEGY}/objectives`, {
    headers: auth,
    data: { goal_id: goalId, title, required_capabilities: ["sso"] },
  });
  expect(r.status(), await r.text()).toBeGreaterThanOrEqual(200);
  expect(r.status(), await r.text()).toBeLessThan(300);
  return ((await r.json()) as { objective_id: string }).objective_id;
}

async function createInitiative(
  request: APIRequestContext,
  auth: Record<string, string>,
  objectiveId: string
): Promise<string> {
  const r = await request.post(`${STRATEGY}/initiatives`, {
    headers: auth,
    data: { objective_id: objectiveId, title: "SSO initiative", required_capabilities: ["sso"] },
  });
  expect(r.status(), await r.text()).toBeGreaterThanOrEqual(200);
  expect(r.status(), await r.text()).toBeLessThan(300);
  return ((await r.json()) as { initiative_id: string }).initiative_id;
}

async function linkInitiative(
  request: APIRequestContext,
  auth: Record<string, string>,
  initiativeId: string,
  projectId: string
) {
  const r = await request.post(`${STRATEGY}/initiatives/${initiativeId}/link`, {
    headers: auth,
    data: { project_id: projectId },
  });
  expect(r.status(), await r.text()).toBeGreaterThanOrEqual(200);
  expect(r.status(), await r.text()).toBeLessThan(300);
}

async function createCommitment(
  request: APIRequestContext,
  auth: Record<string, string>,
  customerId: string,
  summary: string,
  expectedAt: string,
  projectId?: string
): Promise<string> {
  const r = await request.post(`${CUST}/commitments`, {
    headers: auth,
    data: {
      customer_id: customerId,
      summary,
      expected_at: expectedAt,
      project_id: projectId,
      capability: "sso",
      owner_label: "Platform Team",
    },
  });
  expect(r.status(), await r.text()).toBe(200);
  return ((await r.json()) as { commitment_id: string }).commitment_id;
}

async function recordOutcome(
  request: APIRequestContext,
  auth: Record<string, string>,
  customerId: string,
  actual: number
) {
  const r = await request.post(`${CUST}/outcomes`, {
    headers: auth,
    data: {
      customer_id: customerId,
      metric_kind: "login_success_rate",
      baseline: 82,
      target: 99,
      actual,
      unit: "pct",
      period_label: "2026-Q3",
    },
  });
  expect(r.status(), await r.text()).toBe(200);
}

async function deliverCommitment(
  request: APIRequestContext,
  auth: Record<string, string>,
  commitmentId: string
) {
  const r = await request.post(`${CUST}/commitments/${commitmentId}/deliver`, {
    headers: auth,
    data: {},
  });
  expect(r.status(), await r.text()).toBe(200);
}

test("slice 4g.5: the customer intelligence tab surfaces health, themes, coverage, gaps and propagation", async ({
  browser,
  request,
}) => {
  test.setTimeout(900_000);

  const email = `g5${ts()}@intel.co`;
  const password = "StrongPass123!";
  const t = ts();

  // unique org through the public API, then the UI as the same founder.
  await apiRegister(request, `Intel Co ${t}`, `intel4g5-${t}`, email);
  const token = (await apiLogin(request, email, password)).access_token;
  const auth = { Authorization: `Bearer ${token}` };

  // ------------------------------------------------------------ seed evidence
  const nova = await createCustomer(request, auth, "Nova Labs");
  const beta = await createCustomer(request, auth, "Beta Corp");
  const gamma = await createCustomer(request, auth, "Gamma Tech");
  const delta = await createCustomer(request, auth, "Delta LLC");
  await dispatchAll(request, auth);

  // three high-severity Nova issues + two medium enterprise requests on sso
  // (an open gap for mobile: three requests, no active initiative).
  await recordSignal(request, auth, nova, "SSO login is broken for our users (outage 0)", { severity: "high", need: "sso" });
  await recordSignal(request, auth, nova, "SSO login is broken for our users (outage 1)", { severity: "high", need: "sso" });
  await recordSignal(request, auth, nova, "SSO login is broken for our users (outage 2)", { severity: "high", need: "sso" });
  await recordSignal(request, auth, beta, "Enterprise SSO support please (Beta)", { signal_type: "request", severity: "medium", need: "sso", source: "crm" });
  await recordSignal(request, auth, gamma, "Enterprise SSO support please (Gamma)", { signal_type: "request", severity: "medium", need: "sso", source: "crm" });
  await recordSignal(request, auth, beta, "Mobile app onboarding please (Beta)", { signal_type: "request", severity: "medium", need: "mobile", source: "crm" });
  await recordSignal(request, auth, gamma, "Mobile app onboarding please (Gamma)", { signal_type: "request", severity: "medium", need: "mobile", source: "crm" });
  await recordSignal(request, auth, delta, "Mobile app onboarding please (Delta)", { signal_type: "request", severity: "medium", need: "mobile", source: "crm" });
  await dispatchAll(request, auth);

  // execution coverage: SSO Rollout Project under a goal -> covers sso only.
  const projectId = await createProject(request, auth, "SSO Rollout Project", `sso${t.slice(-4)}`);
  const g1 = await createGoal(request, auth, "Enterprise SSO security");
  const obj = await createObjective(request, auth, g1, "Enterprise SSO hardening");
  const init = await createInitiative(request, auth, obj);
  await linkInitiative(request, auth, init, projectId);
  await dispatchAll(request, auth);

  // one delivered commitment + one overdue commitment -> risk propagation.
  const deliveredId = await createCommitment(
    request,
    auth,
    nova,
    "SSO migration complete",
    new Date(Date.now() - 10 * 86400000).toISOString(),
    projectId
  );
  const overdueId = await createCommitment(
    request,
    auth,
    nova,
    "Enterprise SSO GA",
    new Date(Date.now() - 2 * 86400000).toISOString(),
    projectId
  );
  await deliverCommitment(request, auth, deliveredId);
  await recordOutcome(request, auth, nova, 97);
  await dispatchAll(request, auth);

  // ----------------------------------------------------------- API contract
  const health = (await (
    await request.get(`${CUST}/health`, { headers: auth })
  ).json()) as {
    at_risk: number;
    health: Array<{ customer_id: string; customer: string; state: string; score: number; reasons: string[] }>;
  };
  expect(health.at_risk).toBeGreaterThanOrEqual(1);
  const novaHealth = health.health.find((h) => h.customer_id === nova);
  expect(novaHealth).toBeTruthy();
  expect(["at_risk", "concerned"]).toContain(novaHealth!.state);
  expect(novaHealth!.reasons.length).toBeGreaterThan(0);

  const themes = (await (await request.get(`${CUST}/themes`, { headers: auth })).json()) as {
    themes: Array<{ key: string; occurrences: number; open: number; evidence: unknown[] }>;
  };
  const ssoTheme = themes.themes.find((th) => th.key === "sso");
  expect(ssoTheme).toBeTruthy();
  expect(ssoTheme!.occurrences).toBe(5);
  expect(ssoTheme!.open).toBe(5);
  expect(ssoTheme!.evidence.length).toBeGreaterThan(0);

  const coverage = (await (await request.get(`${CUST}/coverage`, { headers: auth })).json()) as {
    coverage_pct: number;
    themes: Array<{ key: string; coverage_pct: number; covered: boolean; addressing_projects: Array<{ name: string }> }>;
  };
  const ssoCoverage = coverage.themes.find((th) => th.key === "sso");
  expect(ssoCoverage).toBeTruthy();
  expect(ssoCoverage!.coverage_pct).toBe(100);
  expect(ssoCoverage!.addressing_projects.some((p) => p.name === "SSO Rollout Project")).toBe(true);
  const mobileCoverage = coverage.themes.find((th) => th.key === "mobile");
  expect(mobileCoverage).toBeTruthy();
  expect(mobileCoverage!.covered).toBe(false);

  const gaps = (await (await request.get(`${CUST}/gaps`, { headers: auth })).json()) as {
    gaps: Array<{ key: string; impact: string; why: string[] }>;
  };
  expect(gaps.gaps.some((g) => g.key === "mobile")).toBe(true);
  expect(gaps.gaps.find((g) => g.key === "mobile")!.why.length).toBeGreaterThan(0);

  const opportunities = (await (
    await request.get(`${CUST}/opportunities`, { headers: auth })
  ).json()) as {
    opportunities: Array<{ key: string; signals: number; decision_linkage: { requires_decision: boolean; note: string } }>;
  };
  const ssoOpp = opportunities.opportunities.find((o) => o.key === "sso");
  expect(ssoOpp).toBeTruthy();
  expect(ssoOpp!.signals).toBe(2);
  expect(ssoOpp!.decision_linkage.requires_decision).toBe(false);
  const mobileOpp = opportunities.opportunities.find((o) => o.key === "mobile");
  expect(mobileOpp).toBeTruthy();
  expect(mobileOpp!.signals).toBe(3);
  expect(mobileOpp!.decision_linkage.requires_decision).toBe(true);

  const risk = (await (await request.get(`${CUST}/risk`, { headers: auth })).json()) as {
    at_risk_customers: Array<{ customer_id: string; state: string }>;
    commitments_at_risk: Array<{ commitment_id: string; project: string; goals: Array<{ goal: string }> }>;
    propagation_note: string;
  };
  expect(risk.at_risk_customers.some((r) => r.customer_id === nova)).toBe(true);
  const overdue = risk.commitments_at_risk.find((c) => c.commitment_id === overdueId);
  expect(overdue).toBeTruthy();
  expect(overdue!.project).toBe("SSO Rollout Project");
  expect(overdue!.goals.some((g) => g.goal === "Enterprise SSO security")).toBe(true);
  expect(risk.propagation_note.length).toBeGreaterThan(0);

  // ---------------------------------------------------------------- UI check
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL("**/home", { timeout: 30_000 });

  await page.goto("/execution");
  await expect(page.getByRole("heading", { name: "Execution Command Center" })).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: /^Customer Intelligence/ }).click();

  // the tab surfaces stat cards and the core ledgers.
  await expect(page.getByText("At-risk customers", { exact: true })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("Need coverage", { exact: true })).toBeVisible();
  await expect(page.getByText("Nova Labs", { exact: true }).first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("sso", { exact: true }).first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("mobile", { exact: true }).first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("SSO Rollout Project", { exact: true }).first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("Enterprise SSO security", { exact: true }).first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText(/requires a human decision/i).first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText(/baseline 82 → actual 97/).first()).toBeVisible({ timeout: 20_000 });

  // the command center ties health to the signal timeline.
  await page.getByRole("button", { name: "Nova Labs" }).first().click();
  await expect(page.getByText(/Command center · Nova Labs/)).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("Health trail", { exact: true })).toBeVisible();
  await expect(page.getByText("Signal timeline", { exact: true })).toBeVisible();
  await expect(page.getByText("SSO login is broken for our users (outage 0)", { exact: true })).toBeVisible({ timeout: 20_000 });

  // a human resolves one open signal from the UI; it stays resolved.
  await page.getByRole("button", { name: /Resolve SSO login is broken for our users \(outage 0\)/ }).first().click();
  await expect(page.getByText(/Command center · Nova Labs/)).toBeVisible({ timeout: 20_000 });
  await expect(page.getByRole("button", { name: /Resolve SSO login is broken/ })).toHaveCount(2, { timeout: 20_000 });

  const after = (await (
    await request.get(`${CUST}/signals`, { headers: auth, params: { need: "sso", severity: "high" } })
  ).json()) as { signals: Array<{ title: string; status: string }> };
  const resolved = after.signals.find((s) => s.title === "SSO login is broken for our users (outage 0)");
  expect(resolved).toBeTruthy();
  expect(["resolved", "closed"]).toContain(resolved!.status);

  await page.close();
  await ctx.close();
});