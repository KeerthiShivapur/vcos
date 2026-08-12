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

interface PatternRow {
  id: string;
  pattern_type: string;
  pattern_key: string;
  family: string;
  title: string;
  status: string;
  count: number;
  occurrence_count: number;
  confidence: number;
  scope_id: string | null;
  scope_type: string;
  auth_project_id: string | null;
  supporting_event_ids: string[];
  source_events?: string[];
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

async function patternsList(
  request: APIRequestContext,
  auth: Record<string, string>,
  params: Record<string, string> = {}
): Promise<PatternRow[]> {
  const r = await request.get(`${API}/brain/patterns`, { headers: auth, params: { limit: "200", ...params } });
  expect(r.status(), await r.text()).toBe(200);
  return (await r.json()).patterns;
}

async function waitForPattern(
  request: APIRequestContext,
  auth: Record<string, string>,
  check: (patterns: PatternRow[]) => boolean
): Promise<PatternRow[]> {
  for (let attempt = 0; attempt < 8; attempt++) {
    await dispatchAll(request, auth);
    await runPatternWorker(request, auth);
    const patterns = await patternsList(request, auth);
    if (check(patterns)) return patterns;
    await new Promise((resolve) => setTimeout(resolve, 3_000));
  }
  return patternsList(request, auth);
}

test("slice 4d.4: repeated delay pattern forms with evidence, survives governance, and surfaces in the UI", async ({ browser, request }) => {
  test.setTimeout(600_000);
  const t = ts();
  const email = `pat${t}@acme.com`;
  const password = "StrongPass123!";

  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  page.on("console", (msg) => {
    if (msg.type() === "error") console.log(`[${Date.now() % 100000}] console:error ${msg.text().slice(0, 200)}`);
  });
  page.on("requestfailed", (req) =>
    console.log(`[${Date.now() % 100000}] REQ-FAIL ${req.method()} ${req.url().slice(0, 90)} :: ${req.failure()?.errorText}`)
  );

  await registerOrg(page, `Pattern Co ${t}`, `pat-${t}`, email, "Pico", password);
  const token = (await apiLogin(request, email, password)).access_token;
  const auth = { Authorization: `Bearer ${token}` };

  // Seed a governance-scoped project and block three tasks in it — three
  // task.transitioned events to "blocked" must form one repeated_delay pattern.
  const project = await (await request.post(`${API}/projects`, {
    headers: auth,
    data: { name: "Helios Delivery", description: "Slice 4D.4 anchor", status: "active" },
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

  // 1) Change-driven formation: enqueue pattern.evaluate jobs via the event
  //    bus, drain them with the pattern worker, and wait for the pattern.
  const formed = await waitForPattern(request, auth, (patterns) =>
    patterns.some((p) => p.pattern_type === "repeated_delay" && p.auth_project_id === project.id)
  );
  const pattern = formed.find((p) => p.pattern_type === "repeated_delay" && p.auth_project_id === project.id)!;
  expect(pattern.family).toBe("execution");
  expect(pattern.title).toContain("Repeated delays");
  expect(pattern.count).toBeGreaterThanOrEqual(2);
  expect(pattern.occurrence_count).toBe(pattern.count);
  expect(["candidate", "emerging"]).toContain(pattern.status);
  expect(pattern.confidence).toBeGreaterThanOrEqual(0.4);
  expect(pattern.scope_type).toBe("project");
  expect(pattern.auth_project_id).toBe(project.id);
  expect(pattern.supporting_event_ids.length).toBe(pattern.count);

  // 2) Evidence lineage: every supporting event is a task.transitioned.
  const evidenceRes = await request.get(`${API}/brain/patterns/${pattern.id}/evidence`, { headers: auth });
  expect(evidenceRes.status(), await evidenceRes.text()).toBe(200);
  const evidence = (await evidenceRes.json()) as {
    evidence: Array<Record<string, unknown>>;
    supporting_memories: unknown[];
    source_events: string[];
  };
  expect(evidence.source_events.length).toBe(pattern.count);
  expect(evidence.evidence.length).toBe(pattern.count);
  expect(evidence.evidence.every((item) => item.title === "task.transitioned")).toBe(true);

  // 3) Occurrence history resolves every contributing event.
  const historyRes = await request.get(`${API}/brain/patterns/${pattern.id}/history`, { headers: auth });
  expect(historyRes.status(), await historyRes.text()).toBe(200);
  const history = (await historyRes.json()) as { history: Array<{ event_id: string; event_name: string }>; occurrence_count: number };
  expect(history.history.length).toBe(pattern.count);
  expect(history.occurrence_count).toBe(pattern.count);
  expect(history.history.every((item) => item.event_name === "task.transitioned")).toBe(true);

  // 4) Related links endpoint contract.
  const relatedRes = await request.get(`${API}/brain/patterns/${pattern.id}/related`, { headers: auth });
  expect(relatedRes.status(), await relatedRes.text()).toBe(200);
  expect(Array.isArray((await relatedRes.json()).related)).toBe(true);

  // 5) Legacy surface: phase 9 pattern list still surfaces lifecycle patterns.
  const legacy = await request.get(`${API}/intelligence/patterns`, { headers: auth, params: { status: "open", limit: "200" } });
  expect(legacy.status(), await legacy.text()).toBe(200);
  const legacyIds = (await legacy.json()).map((p: PatternRow) => p.id);
  expect(legacyIds).toContain(pattern.id);

  // 6) One occurrence is never a pattern: a second project with a single
  //    blocked task must not produce an observable pattern.
  const soloProject = await (await request.post(`${API}/projects`, {
    headers: auth,
    data: { name: "Solo Effort", description: "single blocked task", status: "active" },
  })).json();
  await request.post(`${API}/governance/scopes`, {
    headers: auth,
    data: { name: "Solo Scope", scope_type: "project", entity_id: soloProject.id },
  });
  const soloTask = await (await request.post(`${API}/tasks`, {
    headers: auth,
    data: { title: "Lone delivery", project_id: soloProject.id, status: "todo" },
  })).json();
  await request.post(`${API}/tasks/${soloTask.id}/transition`, { headers: auth, data: { status: "blocked" } });
  await waitForPattern(request, auth, (patterns) =>
    patterns.some((p) => p.auth_project_id === soloProject.id)
  );
  const soloPatterns = await patternsList(request, auth, { pattern_type: "repeated_delay" });
  expect(soloPatterns.some((p) => p.auth_project_id === soloProject.id)).toBe(false);

  // 7) Governance: a project-scoped brain:read-only reader sees this pattern;
  //    a hidden project's pattern is a 404 for them.
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
  const withHidden = await waitForPattern(request, auth, (patterns) =>
    patterns.some((p) => p.auth_project_id === hiddenProject.id)
  );
  const hiddenPattern = withHidden.find((p) => p.auth_project_id === hiddenProject.id)!;

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
    data: { granted_to_user: joinedUser.user.id, permission_code: "brain:read", reason: "4d.4 e2e" },
  });
  expect(delegated.status(), await delegated.text()).toBe(201);

  const scopedPatterns = await patternsList(request, scopedAuth);
  const scopedIds = scopedPatterns.map((p) => p.id);
  expect(scopedIds).toContain(pattern.id);
  expect(scopedIds).not.toContain(hiddenPattern.id);
  const hiddenGet = await request.get(`${API}/brain/patterns/${hiddenPattern.id}`, { headers: scopedAuth });
  expect(hiddenGet.status()).toBe(404);

  // 8) Tenant isolation: a rival org sees nothing of this org's patterns.
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
  const rivalPatterns = await patternsList(request, rivalAuth);
  expect(rivalPatterns.map((p) => p.id)).not.toContain(pattern.id);

  // 9) Exactly-once replay: re-draining and re-running never duplicates
  //    occurrences or changes the pattern.
  const beforeList = await patternsList(request, auth);
  const before = new Map(beforeList.map((p) => [p.id, p.count]));
  const historyBefore = (await request.get(`${API}/brain/patterns/${pattern.id}/history`, { headers: auth })).json();
  for (let i = 0; i < 3; i++) {
    await dispatchAll(request, auth);
    await runPatternWorker(request, auth);
  }
  const afterList = await patternsList(request, auth);
  const after = new Map(afterList.map((p) => [p.id, p.count]));
  const historyAfter = (await request.get(`${API}/brain/patterns/${pattern.id}/history`, { headers: auth })).json();
  expect(after.get(pattern.id)).toBe(before.get(pattern.id));
  expect((await historyAfter).history.length).toBe((await historyBefore).history.length);

  // 10) Worker + scheduler: the pattern worker is registered @ 120s and
  //     runs on demand.
  const workers = await (await request.get(`${API}/intelligence/workers`, { headers: auth })).json();
  const patternWorker = workers.find((w: { name: string }) => w.name === "pattern");
  expect(patternWorker).toBeTruthy();
  expect(patternWorker.interval_seconds).toBe(120);
  expect(patternWorker.run_on_demand).toBe(true);

  // 11) UI: the Pattern Intelligence tab surfaces the active pattern with
  //     evidence and a brain:manage lifecycle action.
  await page.goto("/intelligence");
  await expect(page.getByRole("heading", { name: "Background Intelligence" })).toBeVisible({ timeout: 15_000 });
  await page.getByRole("button", { name: /Pattern Intelligence/ }).click();
  await expect(page.getByText("Repeated delays: Helios Delivery", { exact: false }).first()).toBeVisible({ timeout: 20_000 });
  await page.getByText("Repeated delays: Helios Delivery", { exact: false }).first().click();
  await expect(page.getByText("Why VCOS believes this", { exact: false })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("Occurrence history", { exact: false })).toBeVisible({ timeout: 15_000 });
  await page.getByRole("button", { name: "Acknowledge" }).click();
  await expect(page.getByText("Pattern marked acknowledged", { exact: true })).toBeVisible({ timeout: 15_000 });

  // 12) Human lifecycle: the UI acknowledge persisted via the new API.
  const ack = await request.patch(`${API}/brain/patterns/${pattern.id}`, {
    headers: auth,
    data: { status: "acknowledged" },
  });
  expect(ack.status(), await ack.text()).toBe(200);
  expect((await ack.json()).status).toBe("acknowledged");
  const acked = await request.get(`${API}/brain/patterns`, { headers: auth, params: { status: "acknowledged" } });
  expect(acked.status(), await acked.text()).toBe(200);
  expect((await acked.json()).patterns.map((p: PatternRow) => p.id)).toContain(pattern.id);
});
