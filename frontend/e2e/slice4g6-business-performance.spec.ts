import { expect, test, type APIRequestContext } from "@playwright/test";

const API = "http://127.0.0.1:8999/api/v1";
const BRAIN = `${API}/brain`;
const BIZ = `${BRAIN}/execution/business`;

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

async function defineMetric(
  request: APIRequestContext,
  auth: Record<string, string>,
  key: string,
  label: string,
  kind: string
) {
  const r = await request.post(`${BIZ}/metrics`, {
    headers: auth,
    data: { key, label, kind, direction: "up_is_good", unit: "usd", period_granularity: "monthly" },
  });
  expect(r.status(), await r.text()).toBe(200);
}

async function recordOutcome(
  request: APIRequestContext,
  auth: Record<string, string>,
  metricKey: string,
  value: number,
  source: string
) {
  const r = await request.post(`${BIZ}/outcomes`, {
    headers: auth,
    data: { metric_key: metricKey, value, source, unit: "usd", note: `observed ${value}` },
  });
  expect(r.status(), await r.text()).toBe(200);
}

async function commitTarget(
  request: APIRequestContext,
  auth: Record<string, string>,
  metricKey: string,
  targetValue: number,
  endAt: string
): Promise<string> {
  const r = await request.post(`${BIZ}/targets`, {
    headers: auth,
    data: {
      metric_key: metricKey,
      target_value: targetValue,
      end_at: endAt,
      period_label: "FY2026",
      belief: "plausible",
      unit: "usd",
      owner_label: "CEO Office",
      rationale: "Board committed growth target",
    },
  });
  expect(r.status(), await r.text()).toBe(200);
  return ((await r.json()) as { target_id: string }).target_id;
}

async function recordForecast(
  request: APIRequestContext,
  auth: Record<string, string>,
  metricKey: string
) {
  const r = await request.post(`${BIZ}/forecasts`, {
    headers: auth,
    data: {
      metric_key: metricKey,
      forecast_type: "base",
      horizon_label: "FY2026",
      low: 110000,
      midpoint: 150000,
      high: 200000,
      confidence: 0.8,
      basis: "pipeline growth",
    },
  });
  expect(r.status(), await r.text()).toBe(200);
}

async function recordDriver(
  request: APIRequestContext,
  auth: Record<string, string>,
  metricKey: string
) {
  const r = await request.post(`${BIZ}/drivers`, {
    headers: auth,
    data: {
      key: "customer-expansion",
      title: "Customer expansion",
      driver_type: "market",
      strength: "strong",
      direction: "toward",
      impact_shape: "attribute",
      metric_keys: [metricKey],
      description: "Expansion revenue from existing accounts",
    },
  });
  expect(r.status(), await r.text()).toBe(200);
}

test("slice 4g.6: the business performance tab surfaces health, targets, forecasts, drivers and the behind-target chain", async ({
  browser,
  request,
}) => {
  test.setTimeout(900_000);

  const email = `g6${ts()}@intel.co`;
  const password = "StrongPass123!";
  const t = ts();

  await apiRegister(request, `Intel Co ${t}`, `intel4g6-${t}`, email);
  const token = (await apiLogin(request, email, password)).access_token;
  const auth = { Authorization: `Bearer ${token}` };

  // ------------------------------------------------------------ seed evidence
  await defineMetric(request, auth, "recurring-revenue", "Recurring Revenue", "revenue");
  await recordOutcome(request, auth, "recurring-revenue", 80000, "financial");
  await recordOutcome(request, auth, "recurring-revenue", 100000, "financial");
  await dispatchAll(request, auth);
  await commitTarget(
    request,
    auth,
    "recurring-revenue",
    300000,
    new Date(Date.now() + 90 * 86400000).toISOString()
  );
  await recordForecast(request, auth, "recurring-revenue");
  await recordDriver(request, auth, "recurring-revenue");
  await dispatchAll(request, auth);

  // ----------------------------------------------------------- API contract
  const metrics = (await (await request.get(`${BIZ}/metrics`, { headers: auth })).json()) as {
    total: number;
    metrics: Array<{ key: string; current: number | null; trend: string; kind: string }>;
  };
  expect(metrics.total).toBe(1);
  const revenue = metrics.metrics.find((m) => m.key === "recurring-revenue");
  expect(revenue).toBeTruthy();
  expect(revenue!.current).toBe(100000);
  expect(revenue!.trend).toBe("improving");
  expect(revenue!.kind).toBe("revenue");

  const targets = (await (await request.get(`${BIZ}/targets`, { headers: auth })).json()) as {
    targets: Array<{ target_id: string; metric_key: string; status: string; current: number | null; gap: number | null }>;
  };
  const committed = targets.targets.find((tt) => tt.metric_key === "recurring-revenue");
  expect(committed).toBeTruthy();
  expect(["slipped", "at_risk"]).toContain(committed!.status);
  expect(committed!.current).toBe(100000);
  const targetId = committed!.target_id;

  const performance = (await (
    await request.get(`${BIZ}/performance`, { headers: auth })
  ).json()) as {
    health: { score: number; dimensions: Array<{ key: string; state: string; reasons: string[] }> };
    metrics: { trajectories: Array<{ trend: string }> };
    advisory_only: boolean;
  };
  expect(performance.advisory_only).toBe(true);
  expect(performance.health.dimensions.some((d) => d.key === "financial")).toBe(true);
  expect(performance.metrics.trajectories.length).toBeGreaterThan(0);

  const behind = (await (
    await request.get(`${BIZ}/behind-target`, { headers: auth })
  ).json()) as {
    target: { metric_label: string; status: string; gap: number | null };
    drivers: Array<{ title: string; kind: string }>;
    what_to_do: Array<{ kind: string; action: string }>;
  };
  expect(behind.target.metric_label).toBe("Recurring Revenue");
  expect(behind.target.gap).toBe(200000);
  expect(behind.drivers.some((d) => d.title === "Customer expansion" && d.kind === "linked_to")).toBe(true);
  expect(behind.what_to_do.some((w) => w.kind === "close_gap")).toBe(true);

  const forecasts = (await (await request.get(`${BIZ}/forecasts`, { headers: auth })).json()) as {
    forecasts: Array<{ forecast_type: string; midpoint: number | null; confidence: number | null }>;
  };
  const base = forecasts.forecasts.find((f) => f.forecast_type === "base");
  expect(base).toBeTruthy();
  expect(base!.midpoint).toBe(150000);

  const recommendations = (await (
    await request.get(`${BIZ}/recommendations`, { headers: auth })
  ).json()) as { total: number; recommendations: Array<{ kind: string; title: string }> };
  expect(recommendations.total).toBeGreaterThanOrEqual(1);

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
  await page.getByRole("button", { name: /^Business Performance/ }).click();

  // the tab surfaces stat cards and the core ledgers.
  await expect(page.getByText("Health score", { exact: true })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("Metrics tracked", { exact: true })).toBeVisible();
  await expect(page.getByText("Targets at risk", { exact: true })).toBeVisible();
  await expect(page.getByText("Active drivers", { exact: true })).toBeVisible();

  await expect(page.getByText(/Performance health/).first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("financial", { exact: true }).first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("Recurring Revenue", { exact: true }).first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("improving", { exact: true }).first()).toBeVisible({ timeout: 20_000 });

  await expect(page.getByText(/Why are we behind target/).first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("What to do", { exact: true })).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("Customer expansion", { exact: true }).first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("linked to", { exact: true }).first()).toBeVisible({ timeout: 20_000 });

  await expect(page.getByText("projected", { exact: true }).first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText(/Advisory only/).first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("slipped", { exact: true }).first()).toBeVisible({ timeout: 20_000 });

  await page.close();
  await ctx.close();
});
