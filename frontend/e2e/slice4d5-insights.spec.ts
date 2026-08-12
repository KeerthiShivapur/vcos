import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const API = "http://localhost:8999/api/v1";

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

interface InsightRow {
  id: string;
  insight_type: string;
  domain: string;
  severity: string;
  title: string;
  claim: string | null;
  summary: string | null;
  confidence: number;
  status: string;
  scope_id: string | null;
  scope_type: string;
  auth_project_id: string | null;
  supporting_pattern_ids: string[];
  supporting_memory_ids: string[];
  affected_entities: Array<{ type: string; id: string; title?: string }>;
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

async function runPatternWorker(request: APIRequestContext, auth: Record<string, string>) {
  const r = await request.post(`${API}/intelligence/workers/pattern/run`, { headers: auth });
  expect(r.status(), await r.text()).toBe(200);
  return (await r.json()) as { processed: number };
}

async function runInsightWorker(request: APIRequestContext, auth: Record<string, string>) {
  const r = await request.post(`${API}/intelligence/workers/insight/run`, { headers: auth });
  expect(r.status(), await r.text()).toBe(200);
  return (await r.json()) as { processed: number };
}

async function insightsList(
  request: APIRequestContext,
  auth: Record<string, string>,
  params: Record<string, string> = {}
): Promise<InsightRow[]> {
  const r = await request.get(`${API}/brain/insights`, { headers: auth, params: { limit: "200", ...params } });
  expect(r.status(), await r.text()).toBe(200);
  return (await r.json()).insights;
}

async function waitForInsight(
  request: APIRequestContext,
  auth: Record<string, string>,
  check: (insights: InsightRow[]) => boolean
): Promise<InsightRow[]> {
  for (let attempt = 0; attempt < 8; attempt++) {
    await dispatchAll(request, auth);
    await runPatternWorker(request, auth);
    await dispatchAll(request, auth);
    await runInsightWorker(request, auth);
    const insights = await insightsList(request, auth);
    if (check(insights)) return insights;
    await new Promise((resolve) => setTimeout(resolve, 3_000));
  }
  return insightsList(request, auth);
}

test("slice 4d.5: company insight composes from patterns with evidence, survives governance, and surfaces in the UI", async ({ browser, request }) => {
  test.setTimeout(600_000);
  const t = ts();
  const email = `ins${t}@acme.com`;
  const password = "StrongPass123!";

  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  page.on("console", (msg) => {
    if (msg.type() === "error") console.log(`[${Date.now() % 100000}] console:error ${msg.text().slice(0, 200)}`);
  });
  page.on("requestfailed", (req) =>
    console.log(`[${Date.now() % 100000}] REQ-FAIL ${req.method()} ${req.url().slice(0, 90)} :: ${req.failure()?.errorText}`)
  );

  await registerOrg(page, `Insight Co ${t}`, `ins-${t}`, email, "Iris", password);
  const token = (await apiLogin(request, email, password)).access_token;
  const auth = { Authorization: `Bearer ${token}` };

  // Seed a governance-scoped project and block three tasks — the resulting
  // repeated_delay pattern must compose into an execution_bottleneck insight.
  const project = await (await request.post(`${API}/projects`, {
    headers: auth,
    data: { name: "Helios Delivery", description: "Slice 4D.5 anchor", status: "active" },
  })).json();
  const scope = await (await request.post(`${API}/governance/scopes`, {
    headers: auth,
    data: { name: "Helios Scope", scope_type: "project", entity_id: project.id },
  })).json();
  const titles = ["Checkout API", "Billing export", "Mobile push"];
  for (const title of titles) {
    const task = await (await request.post(`${API}/tasks`, {
      headers: auth,
      data: { title, project_id: project.id, status: "todo" },
    })).json();
    const blocked = await request.post(`${API}/tasks/${task.id}/transition`, {
      headers: auth,
      data: { status: "blocked" },
    });
    expect(blocked.status(), await blocked.text()).toBe(200);
  }

  // 1) Change-driven composition: patterns form, pattern.* events enqueue
  //    insight.evaluate jobs, and the insight worker recomposes the insight.
  const formed = await waitForInsight(request, auth, (insights) =>
    insights.some((i) => i.insight_type === "execution_bottleneck" && i.auth_project_id === project.id)
  );
  const insight = formed.find((i) => i.insight_type === "execution_bottleneck" && i.auth_project_id === project.id)!;
  expect(insight.domain).toBe("execution");
  expect(insight.title).toContain("execution bottlenecks");
  expect(insight.claim).toBeTruthy();
  expect(insight.summary).toBeTruthy();
  expect(insight.confidence).toBeGreaterThanOrEqual(0);
  expect(insight.confidence).toBeLessThanOrEqual(1);
  expect(insight.status).toBe("active");
  expect(insight.severity).toBe("warning");
  expect(insight.scope_type).toBe("project");
  expect(insight.scope_id).toBe(scope.id);
  expect(insight.auth_project_id).toBe(project.id);
  expect(insight.supporting_pattern_ids.length).toBeGreaterThanOrEqual(1);
  expect(insight.affected_entities.some((e) => e.type === "project" && e.id === project.id)).toBe(true);

  // 2) Compositional confidence explains itself.
  const detailRes = await request.get(`${API}/brain/insights/${insight.id}`, { headers: auth });
  expect(detailRes.status(), await detailRes.text()).toBe(200);
  const detail = (await detailRes.json()) as InsightRow & {
    confidence_components: Record<string, number | Record<string, number>>;
    evidence: Array<Record<string, unknown>>;
  };
  expect(detail.confidence_components).toBeTruthy();
  for (const key of ["occurrence_strength", "evidence_completeness", "pattern_confidence", "memory_corroboration", "recency"]) {
    expect(key in detail.confidence_components).toBe(true);
  }
  expect(detail.evidence.length).toBeGreaterThanOrEqual(1);
  expect(detail.evidence.some((item) => item.type === "pattern")).toBe(true);

  // 3) Evidence lineage resolves every feeding event (pattern.* events).
  const evidenceRes = await request.get(`${API}/brain/insights/${insight.id}/evidence`, { headers: auth });
  expect(evidenceRes.status(), await evidenceRes.text()).toBe(200);
  const evidence = (await evidenceRes.json()) as { evidence: Array<Record<string, unknown>>; supporting_pattern_ids: string[] };
  expect(evidence.supporting_pattern_ids.length).toBeGreaterThanOrEqual(1);
  expect(evidence.evidence.length).toBeGreaterThanOrEqual(1);

  // 4) Recompose history shows the feeding events.
  const historyRes = await request.get(`${API}/brain/insights/${insight.id}/history`, { headers: auth });
  expect(historyRes.status(), await historyRes.text()).toBe(200);
  const history = (await historyRes.json()) as {
    history: Array<{ event_id: string; event_name: string }>;
    status: string;
  };
  expect(history.history.length).toBeGreaterThanOrEqual(1);
  expect(history.status).toBe("active");
  expect(history.history.every((item) => item.event_name === "pattern.detected" || item.event_name === "pattern.updated" || item.event_name === "pattern.confirmed" || item.event_name === "pattern.faded" || item.event_name === "pattern.resolved")).toBe(true);

  // 5) Related links endpoint contract.
  const relatedRes = await request.get(`${API}/brain/insights/${insight.id}/related`, { headers: auth });
  expect(relatedRes.status(), await relatedRes.text()).toBe(200);
  expect(Array.isArray((await relatedRes.json()).related)).toBe(true);

  // 6) Governance: a project-scoped brain:read-only reader sees this insight;
  //    a hidden project's insight is a 404 for them.
  const hiddenProject = await (await request.post(`${API}/projects`, {
    headers: auth,
    data: { name: "Hidden Ops", description: "out of scope", status: "active" },
  })).json();
  await request.post(`${API}/governance/scopes`, {
    headers: auth,
    data: { name: "Hidden Scope", scope_type: "project", entity_id: hiddenProject.id },
  });
  for (const title of ["A", "B", "C"]) {
    const task = await (await request.post(`${API}/tasks`, {
      headers: auth,
      data: { title: `Hidden ${title}`, project_id: hiddenProject.id, status: "todo" },
    })).json();
    await request.post(`${API}/tasks/${task.id}/transition`, { headers: auth, data: { status: "blocked" } });
  }
  const withHidden = await waitForInsight(request, auth, (insights) =>
    insights.some((i) => i.insight_type === "execution_bottleneck" && i.auth_project_id === hiddenProject.id)
  );
  const hiddenInsight = withHidden.find((i) => i.insight_type === "execution_bottleneck" && i.auth_project_id === hiddenProject.id)!;

  const invite = await request.post(`${API}/users/invite`, {
    headers: auth,
    data: { email: `emp${t}@acme.com`, full_name: "Scoped Mgr", role: "manager" },
  });
  expect(invite.status(), await invite.text()).toBe(201);
  const joined = await request.post(`${API}/auth/register/invite`, {
    data: { token: (await invite.json()).token, full_name: "Scoped Mgr", password },
  });
  expect(joined.status(), await joined.text()).toBe(201);
  const joinedUser = await joined.json();
  const scopedAuth = { Authorization: `Bearer ${joinedUser.access_token}` };
  const roles = await (await request.get(`${API}/roles`, { headers: auth })).json();
  const managerRole = roles.find((r: { code: string }) => r.code === "manager");
  const assignment = await request.post(`${API}/governance/assignments`, {
    headers: auth,
    data: { user_id: joinedUser.user.id, role_id: managerRole.id, scope_id: scope.id },
  });
  expect(assignment.status(), await assignment.text()).toBe(201);
  const assigned = await (await request.get(`${API}/governance/assignments`, {
    headers: auth,
    params: { user_id: joinedUser.user.id },
  })).json();
  const orgWideAssign = assigned.find((a: { scope_id: string | null }) => a.scope_id === null);
  expect(orgWideAssign).toBeTruthy();
  await request.delete(`${API}/governance/assignments/${orgWideAssign.id}`, { headers: auth });
  const delegated = await request.post(`${API}/governance/delegations`, {
    headers: auth,
    data: { granted_to_user: joinedUser.user.id, permission_code: "brain:read", reason: "4d.5 e2e" },
  });
  expect(delegated.status(), await delegated.text()).toBe(201);

  const scopedInsights = await insightsList(request, scopedAuth);
  const scopedIds = scopedInsights.map((i) => i.id);
  expect(scopedIds).toContain(insight.id);
  expect(scopedIds).not.toContain(hiddenInsight.id);
  const hiddenGet = await request.get(`${API}/brain/insights/${hiddenInsight.id}`, { headers: scopedAuth });
  expect(hiddenGet.status()).toBe(404);

  // 7) Tenant isolation: a rival org sees nothing of this org's insights.
  const rivalEmail = `rival${t}@acme.com`;
  const reg = await request.post(`${API}/auth/register`, {
    data: {
      organization_name: `Rival Co ${t}`,
      organization_slug: `rival-${t}`,
      industry: "Software",
      country: "United States",
      full_name: "Riva",
      email: rivalEmail,
      password,
    },
  });
  expect(reg.status(), await reg.text()).toBe(201);
  const rivalAuth = { Authorization: `Bearer ${(await reg.json()).access_token}` };
  const rivalInsights = await insightsList(request, rivalAuth);
  expect(rivalInsights.map((i) => i.id)).not.toContain(insight.id);

  // 8) Exactly-once replay: re-draining and re-running never duplicates
  //    evidence, history or insight rows.
  const beforeList = await insightsList(request, auth);
  const before = new Map(beforeList.map((i) => [i.id, i.supporting_pattern_ids.length]));
  const historyBefore = (await request.get(`${API}/brain/insights/${insight.id}/history`, { headers: auth })).json();
  for (let i = 0; i < 3; i++) {
    await dispatchAll(request, auth);
    await runPatternWorker(request, auth);
    await dispatchAll(request, auth);
    await runInsightWorker(request, auth);
  }
  const afterList = await insightsList(request, auth);
  const after = new Map(afterList.map((i) => [i.id, i.supporting_pattern_ids.length]));
  const historyAfter = (await request.get(`${API}/brain/insights/${insight.id}/history`, { headers: auth })).json();
  expect(after.get(insight.id)).toBe(before.get(insight.id));
  expect((await historyAfter).history.length).toBe((await historyBefore).history.length);

  // 9) Worker + scheduler: the insight worker is registered @ 120s and
  //    runs on demand.
  const workers = await (await request.get(`${API}/intelligence/workers`, { headers: auth })).json();
  const insightWorker = workers.find((w: { name: string }) => w.name === "insight");
  expect(insightWorker).toBeTruthy();
  expect(insightWorker.interval_seconds).toBe(120);
  expect(insightWorker.run_on_demand).toBe(true);

  // 10) Reasoning answers surface insight claims.
  const answer = await request.post(`${API}/brain/answer`, {
    headers: auth,
    data: { question: "what is happening in this organization right now?" },
  });
  expect(answer.status(), await answer.text()).toBe(200);
  const answerBody = (await answer.json()) as { claims: Array<{ kind?: string; evidence?: Array<{ url?: string }> }> };
  const insightClaims = answerBody.claims.filter((c) => c.kind === "insight");
  expect(insightClaims.length).toBeGreaterThanOrEqual(1);
  expect(insightClaims[0].evidence?.[0]?.url).toContain("/brain/insights/");

  // 11) UI: the Company Insights tab surfaces the active insight with
  //     evidence, confidence explanation and recompose history.
  await page.goto("/intelligence");
  await expect(page.getByRole("heading", { name: "Background Intelligence" })).toBeVisible({ timeout: 15_000 });
  await page.getByRole("button", { name: /Company Insights/ }).click();
  await expect(page.getByText("Helios Delivery shows execution bottlenecks", { exact: false }).first()).toBeVisible({ timeout: 25_000 });
  await page.getByText("Helios Delivery shows execution bottlenecks", { exact: false }).first().click();
  await expect(page.getByText("Confidence — why this score", { exact: false })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("Why VCOS believes this", { exact: false })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("Recompose history", { exact: false })).toBeVisible({ timeout: 15_000 });
});