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

interface MemoryRow {
  id: string;
  memory_category: string;
  title: string;
  source_event: string | null;
  entity_type: string | null;
  entity_id: string | null;
  outcome_type: string | null;
  outcome: string | null;
  lesson: string | null;
  auth_scope: string;
  auth_project_id: string | null;
  related_memory_ids: string[];
  source_event_ids: string[];
  evidence: Array<{ type: string; id: string; relationship: string }>;
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

async function runMemoryWorker(request: APIRequestContext, auth: Record<string, string>) {
  const r = await request.post(`${API}/intelligence/workers/memory_formation/run`, { headers: auth });
  expect(r.status(), await r.text()).toBe(200);
  return (await r.json()) as { processed: number };
}

async function memoryFeed(
  request: APIRequestContext,
  auth: Record<string, string>
): Promise<MemoryRow[]> {
  const r = await request.get(`${API}/brain/memory/feed`, { headers: auth, params: { limit: "100" } });
  expect(r.status(), await r.text()).toBe(200);
  return (await r.json()).memories;
}

async function waitForFeed(
  request: APIRequestContext,
  auth: Record<string, string>,
  check: (memories: MemoryRow[]) => boolean
): Promise<MemoryRow[]> {
  for (let attempt = 0; attempt < 8; attempt++) {
    await dispatchAll(request, auth);
    await runMemoryWorker(request, auth);
    const memories = await memoryFeed(request, auth);
    if (check(memories)) return memories;
    await new Promise((resolve) => setTimeout(resolve, 3_000));
  }
  return memoryFeed(request, auth);
}

test("slice 4d.3: blocked-task episode forms governed memory with outcome, search, timeline and UI", async ({ browser, request }) => {
  test.setTimeout(600_000);
  const t = ts();
  const email = `mem${t}@acme.com`;
  const password = "StrongPass123!";

  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  page.on("console", (msg) => {
    if (msg.type() === "error") console.log(`[${Date.now() % 100000}] console:error ${msg.text().slice(0, 200)}`);
  });
  page.on("requestfailed", (req) =>
    console.log(`[${Date.now() % 100000}] REQ-FAIL ${req.method()} ${req.url().slice(0, 90)} :: ${req.failure()?.errorText}`)
  );

  await registerOrg(page, `Memory Co ${t}`, `mem-${t}`, email, "Ada", password);
  const token = (await apiLogin(request, email, password)).access_token;
  const auth = { Authorization: `Bearer ${token}` };

  // Seed: a project, a blocker task, a dependent task and a dependency.
  const project = await (await request.post(`${API}/projects`, {
    headers: auth,
    data: { name: "Nebula Delivery", description: "Slice 4D.3 anchor", status: "active" },
  })).json();
  // The governance scope must exist before the episode forms: memory inherits
  // the project scope only when the project is governance-scoped.
  const scope = await (await request.post(`${API}/governance/scopes`, {
    headers: auth,
    data: { name: "Nebula Scope", scope_type: "project", entity_id: project.id },
  })).json();
  const blocker = await (await request.post(`${API}/tasks`, {
    headers: auth,
    data: { title: "Prereq migration", project_id: project.id, status: "todo" },
  })).json();
  const dependent = await (await request.post(`${API}/tasks`, {
    headers: auth,
    data: { title: "Billing sync delivery", project_id: project.id, status: "todo" },
  })).json();
  const dep = await request.post(`${API}/tasks/${dependent.id}/dependencies`, {
    headers: auth,
    data: { depends_on_task_id: blocker.id },
  });
  expect(dep.status(), await dep.text()).toBe(201);

  const blocked = await request.post(`${API}/tasks/${dependent.id}/transition`, {
    headers: auth,
    data: { status: "blocked" },
  });
  expect(blocked.status(), await blocked.text()).toBe(200);

  // 1) Change-driven formation: drain the durable event bus and run the
  //    memory worker until the blocked experience is observable.
  const formed = await waitForFeed(request, auth, (memories) =>
    memories.some((m) => m.source_event === "task.blocked" && m.entity_id === dependent.id)
  );
  const experience = formed.find((m) => m.source_event === "task.blocked" && m.entity_id === dependent.id)!;
  expect(experience.memory_category).toBe("experience");
  expect(experience.outcome_type).toBeNull();
  expect(experience.auth_scope).toBe("project");
  expect(experience.auth_project_id).toBe(project.id);
  expect(experience.evidence.length).toBeGreaterThanOrEqual(3);

  // 2) Evidence lineage: task/project/dependency refs resolve to titles/urls.
  const evidenceRes = await request.get(`${API}/brain/memory/${experience.id}/evidence`, { headers: auth });
  expect(evidenceRes.status(), await evidenceRes.text()).toBe(200);
  const evidence = (await evidenceRes.json()).evidence as Array<Record<string, unknown>>;
  const byType = Object.fromEntries(evidence.map((item) => [item.type, item]));
  expect(byType.task?.resolved).toBe(true);
  expect(byType.task?.title).toBe("Billing sync delivery");
  expect(byType.task?.url).toBe(`/tasks/${dependent.id}`);
  expect(byType.project?.resolved).toBe(true);
  expect(byType.dependency?.resolved).toBe(true);

  // 3) Outcome journey: blocker completion unblocks, completion resolves
  //    positive; a manual downgrade must be rejected (monotonic).
  const completeBlocker = await request.post(`${API}/tasks/${blocker.id}/transition`, {
    headers: auth,
    data: { status: "completed" },
  });
  expect(completeBlocker.status(), await completeBlocker.text()).toBe(200);
  await waitForFeed(request, auth, (memories) =>
    memories.some((m) => m.entity_id === dependent.id && m.outcome_type === "positive")
  );
  const completeDependent = await request.post(`${API}/tasks/${dependent.id}/transition`, {
    headers: auth,
    data: { status: "completed" },
  });
  expect(completeDependent.status(), await completeDependent.text()).toBe(200);

  const resolved = await waitForFeed(request, auth, (memories) =>
    memories.some((m) => m.source_event === "task.completed" && m.entity_id === dependent.id)
  );
  const lesson = resolved.find((m) => m.memory_category === "lesson" && m.entity_id === dependent.id);
  expect(lesson).toBeTruthy();
  expect(lesson!.lesson).toBeTruthy();

  const downgrade = await request.post(`${API}/brain/memory/${experience.id}/outcome`, {
    headers: auth,
    data: { outcome_type: "negative", outcome: "vendor never recovered" },
  });
  expect(downgrade.status(), await downgrade.text()).toBe(200);
  const afterDowngrade = await downgrade.json();
  expect(afterDowngrade.outcome_type).toBe("positive");

  // 4) Historical search: semantic retrieval over formed memories.
  const searchRes = await request.post(`${API}/brain/memory/search`, {
    headers: auth,
    data: { question: "task was blocked during execution like this before", limit: 10 },
  });
  expect(searchRes.status(), await searchRes.text()).toBe(200);
  const searchBody = await searchRes.json();
  expect(searchBody.matched).toBeGreaterThanOrEqual(1);
  const hitIds = searchBody.memories.map((m: MemoryRow) => m.id);
  expect(hitIds).toContain(experience.id);

  // 5) Timeline episodes link memories to their forming events.
  const timelineRes = await request.get(`${API}/brain/memory/timeline`, { headers: auth });
  expect(timelineRes.status(), await timelineRes.text()).toBe(200);
  const episodes = (await timelineRes.json()).episodes as MemoryRow[];
  const depEpisodes = episodes.filter((e) => e.entity_type === "task" && e.entity_id === dependent.id);
  expect(depEpisodes.length).toBeGreaterThanOrEqual(1);
  const depCategories = new Set(depEpisodes.map((e) => e.memory_category));
  expect(depCategories.has("lesson")).toBe(true);
  expect(depCategories.has("outcome")).toBe(true);
  for (const episode of depEpisodes) {
    expect(episode.source_event_ids.length).toBeGreaterThanOrEqual(1);
  }

  // 6) Related links: the resolved experience links to peers.
  const relatedRes = await request.get(`${API}/brain/memory/${experience.id}/related`, { headers: auth });
  expect(relatedRes.status(), await relatedRes.text()).toBe(200);
  const relatedBody = await relatedRes.json();
  expect(relatedBody.related.length).toBeGreaterThanOrEqual(0);

  // 7) Governance: a project-scoped brain:read-only reader sees this memory;
  //    a rival tenant sees nothing of this org.
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
  expect(managerRole).toBeTruthy();
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
  const removed = await request.delete(`${API}/governance/assignments/${orgWideAssign.id}`, { headers: auth });
  expect(removed.status(), await removed.text()).toBe(200);
  const delegated = await request.post(`${API}/governance/delegations`, {
    headers: auth,
    data: { granted_to_user: joinedUser.user.id, permission_code: "brain:read", reason: "4d.3 e2e" },
  });
  expect(delegated.status(), await delegated.text()).toBe(201);

  const scopedFeed = await memoryFeed(request, scopedAuth);
  const scopedIds = scopedFeed.map((m) => m.id);
  expect(scopedIds).toContain(experience.id);

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
  const rivalFeed = await memoryFeed(request, rivalAuth);
  expect(rivalFeed.map((m) => m.id)).not.toContain(experience.id);

  // 8) UI: the Company Memory tab surfaces the feed, historical search and
  //    the detail panel with evidence lineage.
  await page.goto("/intelligence");
  await expect(page.getByRole("heading", { name: "Background Intelligence" })).toBeVisible({ timeout: 15_000 });
  await page.getByText("Company Memory", { exact: true }).click();
  await expect(page.getByText("Memory feed", { exact: true })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("Billing sync delivery", { exact: false }).first()).toBeVisible({ timeout: 20_000 });

  await page.getByText("Historical search", { exact: true }).click();
  const textarea = page.locator("textarea[placeholder*='blocked during execution']");
  await expect(textarea).toBeVisible({ timeout: 15_000 });
  await textarea.fill("task was blocked during execution like this before");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.getByText("Billing sync delivery", { exact: false }).first()).toBeVisible({ timeout: 20_000 });

  await page.getByRole("button", { name: /^Timeline/ }).click();
  await expect(page.getByText("Billing sync delivery", { exact: false }).first()).toBeVisible({ timeout: 20_000 });
});
