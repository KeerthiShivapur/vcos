import { expect, test, type APIRequestContext } from "@playwright/test";

const API = "http://127.0.0.1:8999/api/v1";
const BRAIN = `${API}/brain`;
const COMPANY = `${BRAIN}/execution/company`;
const BUS = `${BRAIN}/execution/business`;
const CAP = `${BRAIN}/execution/capacity`;
const STRATEGY = `${BRAIN}/execution/strategy`;
const PROJECTS = `${API}/projects`;
const CUSTOMERS = `${API}/customers`;

function ts(): string {
  return Date.now().toString().slice(-8);
}

async function apiRegister(
  ctx: APIRequestContext,
  name: string,
  slug: string,
  email: string,
) {
  const r = await ctx.post(`${API}/auth/register`, {
    data: {
      organization_name: name,
      organization_slug: slug,
      industry: "Software",
      country: "US",
      timezone: "UTC",
      currency: "USD",
      full_name: "Operating Founder",
      email,
      username: email.split("@")[0],
      password: "StrongPass123!",
    },
  });
  expect(r.status(), await r.text()).toBe(201);
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

async function dispatchAll(
  request: APIRequestContext,
  auth: Record<string, string>,
  limit = 500,
) {
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

async function seedGoal(
  request: APIRequestContext,
  auth: Record<string, string>,
): Promise<string> {
  const r = await request.post(`${STRATEGY}/goals`, {
    headers: auth,
    data: {
      title: "Grow recurring revenue",
      kind: "revenue",
      priority: 1,
      metric_kind: "recurring_revenue",
      metric_unit: "usd",
      target_value: 500000,
      current_value: 100000,
      timeline_label: "FY2026",
    },
  });
  expect(r.status(), await r.text()).toBe(200);
  return ((await r.json()) as { goal_id: string }).goal_id;
}

async function seedProject(
  request: APIRequestContext,
  auth: Record<string, string>,
): Promise<string> {
  const r = await request.post(`${PROJECTS}`, {
    headers: auth,
    data: {
      name: "Flagship Platform",
      description: "4g7 anchor",
      status: "active",
    },
  });
  expect(r.status(), await r.text()).toBe(201);
  return ((await r.json()) as { id: string }).id;
}

async function seedDemand(
  request: APIRequestContext,
  auth: Record<string, string>,
  projectId: string,
  units: number,
) {
  const start = new Date();
  const end = new Date(Date.now() + 30 * 86400000);
  const r = await request.post(`${CAP}/demands`, {
    headers: auth,
    data: {
      project_id: projectId,
      capability: "platform_eng",
      units,
      window_start: start.toISOString().slice(0, 10),
      window_end: end.toISOString().slice(0, 10),
      proficiency: "high",
    },
  });
  expect(r.status(), await r.text()).toBe(200);
}

async function seedMetricOutcomesTarget(
  request: APIRequestContext,
  auth: Record<string, string>,
) {
  let r = await request.post(`${BUS}/metrics`, {
    headers: auth,
    data: {
      key: "recurring_revenue",
      kind: "revenue",
      direction: "up_is_good",
      unit: "usd",
    },
  });
  expect(r.status(), await r.text()).toBe(200);
  await dispatchAll(request, auth);
  for (const [value, daysAgo] of [
    [40000, 120],
    [60000, 60],
  ] as const) {
    r = await request.post(`${BUS}/outcomes`, {
      headers: auth,
      data: {
        metric_key: "recurring_revenue",
        value,
        observed_at: new Date(Date.now() - daysAgo * 86400000).toISOString(),
        source: "financial",
      },
    });
    expect(r.status(), await r.text()).toBe(200);
  }
  r = await request.post(`${BUS}/targets`, {
    headers: auth,
    data: {
      metric_key: "recurring_revenue",
      target_value: 200000,
      end_date: new Date(Date.now() + 200 * 86400000)
        .toISOString()
        .slice(0, 10),
      owner_label: "CFO",
    },
  });
  expect(r.status(), await r.text()).toBe(200);
  await dispatchAll(request, auth);
}

async function seedCustomerCommitment(
  request: APIRequestContext,
  auth: Record<string, string>,
  projectId: string,
): Promise<string> {
  let r = await request.post(`${CUSTOMERS}`, {
    headers: auth,
    data: {
      company_name: "Northstar Enterprises",
      status: "customer",
      segment: "enterprise",
      tier: "key",
      email: "northstar@cust.test.co",
    },
  });
  expect(r.status(), await r.text()).toBe(200);
  const customerId = ((await r.json()) as { id: string }).id;
  r = await request.post(`${BRAIN}/execution/customer/commitments`, {
    headers: auth,
    data: {
      customer_id: customerId,
      project_id: projectId,
      summary: "Ship the Q3 enterprise release",
      expected_at: new Date(Date.now() + 45 * 86400000)
        .toISOString()
        .slice(0, 10),
      status: "pending",
    },
  });
  expect(r.status(), await r.text()).toBe(200);
  return customerId;
}

test("slice 4g.7: the company tab composes state, health, attention, recommendations, what-if and memory", async ({
  browser,
  request,
}) => {
  test.setTimeout(900_000);

  const email = `g7${ts()}@oper.co`;
  const password = "StrongPass123!";
  const t = ts();

  await apiRegister(request, `Operating Co ${t}`, `oper4g7-${t}`, email);
  const token = (await apiLogin(request, email, password)).access_token;
  const auth = { Authorization: `Bearer ${token}` };

  await seedGoal(request, auth);
  const projectId = await seedProject(request, auth);
  await seedDemand(request, auth, projectId, 4);
  await seedMetricOutcomesTarget(request, auth);
  await dispatchAll(request, auth);

  const customerId = await seedCustomerCommitment(request, auth, projectId);
  await dispatchAll(request, auth);

  // ----------------------------------------------------------- API contract
  const state = (await (
    await request.get(`${COMPANY}/state`, { headers: auth })
  ).json()) as {
    advisory_only: boolean;
    dimensions: Record<string, { state?: string; headline?: string }>;
    attention: unknown[];
  };
  expect(state.advisory_only).toBe(true);
  expect(Object.keys(state.dimensions).sort()).toEqual([
    "capacity",
    "coordination",
    "customers",
    "execution",
    "financial",
    "knowledge",
    "people",
    "strategy",
  ]);
  expect(state.attention.length).toBeGreaterThan(0);
  expect(state.attention.length).toBeLessThanOrEqual(5);

  const health = (await (
    await request.get(`${COMPANY}/health`, { headers: auth })
  ).json()) as {
    advisory_only: boolean;
    company_score: number;
    company_state: string;
    domains: Array<{ key: string; score: number; state: string }>;
    primary_constraint: {
      domain?: string;
      label?: string;
      interventions?: string[];
    } | null;
    history: unknown[];
  };
  expect(health.advisory_only).toBe(true);
  expect(health.domains.length).toBe(8);
  expect(health.company_score).toBeGreaterThan(0);
  expect(health.primary_constraint).toBeTruthy();
  expect(["capacity", "strategy"]).toContain(health.primary_constraint!.domain);
  expect(health.history.length).toBeGreaterThanOrEqual(1);

  const recommendations = (await (
    await request.get(`${COMPANY}/recommendations`, { headers: auth })
  ).json()) as {
    advisory_only: boolean;
    total: number;
    recommendations: Array<{
      key: string;
      source: string;
      title: string;
      confidence: string;
    }>;
  };
  expect(recommendations.advisory_only).toBe(true);
  expect(recommendations.total).toBeGreaterThanOrEqual(1);
  expect(
    recommendations.recommendations.some((r) => r.source === "capacity"),
  ).toBe(true);

  const whatIfDelay = (await (
    await request.post(`${COMPANY}/what-if`, {
      headers: auth,
      data: {
        scenario_type: "delay",
        payload: { project_id: projectId, days: 21 },
      },
    })
  ).json()) as {
    not_a_prediction: boolean;
    scenario_type: string;
    consequences: Array<{ label: string }>;
    note: string;
  };
  expect(whatIfDelay.not_a_prediction).toBe(true);
  expect(whatIfDelay.scenario_type).toBe("delay");
  expect(
    whatIfDelay.consequences.some((c) => c.label.includes("delayed 21 days")),
  ).toBe(true);

  const whatIfHire = (await (
    await request.post(`${COMPANY}/what-if`, {
      headers: auth,
      data: {
        scenario_type: "hire",
        payload: { capability: "platform_eng", people: 2, ramp_days: 30 },
      },
    })
  ).json()) as { consequences: Array<{ label: string }> };
  expect(
    whatIfHire.consequences.some((c) => c.label.includes("hire 2 people")),
  ).toBe(true);

  const whatIfUnknown = (await (
    await request.post(`${COMPANY}/what-if`, {
      headers: auth,
      data: { scenario_type: "moon", payload: {} },
    })
  ).json()) as { note: string };
  expect(whatIfUnknown.note).toContain("reallocate | delay | hire");

  await seedDemand(request, auth, projectId, 2);
  let r = await request.post(`${BUS}/outcomes`, {
    headers: auth,
    data: {
      metric_key: "recurring_revenue",
      value: 120000,
      observed_at: new Date(Date.now() - 60 * 86400000).toISOString(),
      source: "financial",
    },
  });
  expect(r.status(), await r.text()).toBe(200);
  await dispatchAll(request, auth);
  const changes = (await (
    await request.get(`${COMPANY}/changes`, { headers: auth })
  ).json()) as {
    window: string;
    company_score_before?: number;
    company_score_after?: number;
    changes: Array<{ kind: string; domain?: string }>;
  };
  expect(changes.window).not.toBe("insufficient_history");
  expect(changes.changes.length).toBeGreaterThan(0);
  expect(changes.changes.some((c) => c.domain === "financial")).toBe(true);

  const decision = (await (
    await request.post(`${COMPANY}/decisions`, {
      headers: auth,
      data: {
        kind: "hire",
        title: "Hire two platform engineers",
        recommendation_key: "capacity:01",
        rationale: "platform_eng is the company bottleneck",
        impact_label: "gap 4 units",
        expected_improvement: "clear the platform constraint",
        confidence: 0.8,
        owner_label: "Technical Leadership",
      },
    })
  ).json()) as { decision_id: string };
  await dispatchAll(request, auth);
  let execR = await request.post(
    `${COMPANY}/decisions/${decision.decision_id}/execute`,
    {
      headers: auth,
      data: {},
    },
  );
  expect(execR.status(), await execR.text()).toBe(200);
  await dispatchAll(request, auth);
  r = await request.post(
    `${COMPANY}/decisions/${decision.decision_id}/outcome`,
    {
      headers: auth,
      data: {
        outcome_kind: "successful",
        effectiveness: 0.9,
        evidence: ["two engineers onboarded; constraint cleared"],
        lesson: "hiring the capability bottleneck pays off first",
      },
    },
  );
  expect(r.status(), await r.text()).toBe(200);
  await dispatchAll(request, auth);

  const memory = (await (
    await request.get(`${COMPANY}/memory`, { headers: auth })
  ).json()) as {
    total_decisions: number;
    decisions: Array<{ decision_id: string; state: string }>;
    learnings: Array<{ lesson?: string }>;
  };
  expect(memory.total_decisions).toBe(1);
  expect(memory.decisions[0].decision_id).toBe(decision.decision_id);
  expect(memory.decisions[0].state).toBe("outcome_recorded");
  expect(memory.learnings.length).toBeGreaterThanOrEqual(1);

  const impact = (await (
    await request.get(`${COMPANY}/impact`, {
      headers: auth,
      params: { subject_type: "project", subject_id: projectId },
    })
  ).json()) as {
    subject_type: string;
    chain: Array<{ step: string }>;
    consequence_summary: string;
  };
  expect(impact.subject_type).toBe("project");
  expect(impact.chain[0].step).toBe("execution");
  expect(impact.chain.some((s) => s.step === "customers")).toBe(true);
  expect(impact.consequence_summary).toBeTruthy();

  const impactCust = (await (
    await request.get(`${COMPANY}/impact`, {
      headers: auth,
      params: { subject_type: "customer", subject_id: customerId },
    })
  ).json()) as { subject_type: string; chain: Array<{ step: string }> };
  expect(impactCust.subject_type).toBe("customer");
  expect(impactCust.chain[0].step).toBe("customers");

  // ---------------------------------------------------------------- UI check
  await request.get("/login");
  await request.get("/_next/static/chunks/app-pages-internals.js");
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL("**/home", { timeout: 30_000 });

  await page.goto("/execution");
  await expect(
    page.getByRole("heading", { name: "Execution Command Center" }),
  ).toBeVisible({
    timeout: 30_000,
  });
  await page.getByRole("button", { name: /^Company/ }).click();

  await expect(page.getByText("Company score", { exact: true })).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByText("Company state", { exact: true })).toBeVisible();
  await expect(
    page.getByText("Domains at risk", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Attention items", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Recommendations", { exact: true }).first(),
  ).toBeVisible();

  await expect(page.getByText(/Universal company state/).first()).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByText(/Company health/).first()).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByText("strategy", { exact: true }).first()).toBeVisible(
    { timeout: 20_000 },
  );
  await expect(page.getByText(/What changed/).first()).toBeVisible({
    timeout: 20_000,
  });

  await expect(page.getByText(/Attention ·/).first()).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.getByText(/What-if/).first()).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.getByText("delay", { exact: true }).first()).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.getByText(/Run what-if/).first()).toBeVisible({
    timeout: 20_000,
  });

  await expect(
    page.getByText("platform_eng", { exact: true }).first(),
  ).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.getByText(/Company memory/).first()).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.getByText(/Advisory only/).first()).toBeVisible({
    timeout: 20_000,
  });

  await page.close();
  await ctx.close();
});
