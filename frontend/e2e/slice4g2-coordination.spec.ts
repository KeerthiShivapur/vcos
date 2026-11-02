import {
  expect,
  test,
  type APIRequestContext,
  type Page,
} from "@playwright/test";

const API = "http://127.0.0.1:8999/api/v1";
const BRAIN = `${API}/brain`;

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
      full_name: "Coord Founder",
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

async function hire(
  request: APIRequestContext,
  auth: Record<string, string>,
  email: string,
  first: string,
  last: string,
  teamId?: string,
): Promise<{ id: string; full_name: string }> {
  const data: Record<string, unknown> = {
    first_name: first,
    last_name: last,
    email,
  };
  if (teamId) data.team_id = teamId;
  const r = await request.post(`${API}/employees`, { headers: auth, data });
  expect(r.status(), await r.text()).toBe(201);
  return (await r.json()) as { id: string; full_name: string };
}

async function createProject(
  request: APIRequestContext,
  auth: Record<string, string>,
  name: string,
  code: string,
): Promise<{ id: string }> {
  const r = await request.post(`${API}/projects`, {
    headers: auth,
    data: { name, code, status: "draft" },
  });
  expect(r.status(), await r.text()).toBe(201);
  return (await r.json()) as { id: string };
}

async function startProject(
  request: APIRequestContext,
  auth: Record<string, string>,
  id: string,
) {
  const r = await request.post(`${API}/projects/${id}/lifecycle`, {
    headers: auth,
    data: { action: "start" },
  });
  expect(r.status(), await r.text()).toBe(200);
}

async function createTask(
  request: APIRequestContext,
  auth: Record<string, string>,
  projectId: string,
  title: string,
  assigneeId?: string,
  milestoneId?: string,
): Promise<{ id: string }> {
  const data: Record<string, unknown> = {
    title,
    project_id: projectId,
    status: "todo",
  };
  if (assigneeId) data.assignee_id = assigneeId;
  if (milestoneId) data.milestone_id = milestoneId;
  const r = await request.post(`${API}/tasks`, { headers: auth, data });
  expect(r.status(), await r.text()).toBe(201);
  return (await r.json()) as { id: string };
}

async function updateTask(
  request: APIRequestContext,
  auth: Record<string, string>,
  taskId: string,
  data: Record<string, unknown>,
) {
  const r = await request.patch(`${API}/tasks/${taskId}`, {
    headers: auth,
    data,
  });
  expect(r.status(), await r.text()).toBe(200);
}

async function addDependency(
  request: APIRequestContext,
  auth: Record<string, string>,
  taskId: string,
  on: string,
  kind = "blocking",
) {
  const r = await request.post(`${API}/tasks/${taskId}/dependencies`, {
    headers: auth,
    data: { depends_on_task_id: on, kind },
  });
  expect(r.status(), await r.text()).toBe(201);
}

async function transition(
  request: APIRequestContext,
  auth: Record<string, string>,
  taskId: string,
  status: string,
) {
  const r = await request.post(`${API}/tasks/${taskId}/transition`, {
    headers: auth,
    data: { status },
  });
  expect(r.status(), await r.text()).toBe(200);
}

async function addProjectMember(
  request: APIRequestContext,
  auth: Record<string, string>,
  projectId: string,
  employeeId: string,
) {
  const r = await request.post(`${API}/projects/${projectId}/members`, {
    headers: auth,
    data: { employee_id: employeeId },
  });
  expect(r.status(), await r.text()).toBe(201);
}

test("slice 4g.2: the coordination center is one governed UI over dependency intelligence", async ({
  browser,
  request,
}) => {
  test.setTimeout(900_000);
  const t = ts();
  const email = `g2${t}@coord.co`;
  const password = "StrongPass123!";

  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  page.on("console", (msg) => {
    if (msg.type() === "error")
      console.log(
        `[${Date.now() % 100000}] console:error ${msg.text().slice(0, 200)}`,
      );
  });

  await apiRegister(request, `Coord Co ${t}`, `coord4g2-${t}`, email);
  const token = (await apiLogin(request, email, password)).access_token;
  const auth = { Authorization: `Bearer ${token}` };

  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL("**/home", { timeout: 30_000 });

  // ---------------------------------------------------------------- seeding
  const alice = await hire(request, auth, `g2a${t}@coord.co`, "Alice", "One");
  const bob = await hire(request, auth, `g2b${t}@coord.co`, "Bob", "Two");
  const iris = await hire(request, auth, `g2c${t}@coord.co`, "Iris", "Three");
  await dispatchAll(request, auth);

  const p1 = await createProject(
    request,
    auth,
    "E2E Apollo Launch",
    `apl${t.slice(-4)}`,
  );
  const phx = await createProject(
    request,
    auth,
    "E2E Phoenix",
    `phx${t.slice(-4)}`,
  );
  await startProject(request, auth, p1.id);
  await startProject(request, auth, phx.id);

  // a real ownership transition opens a measured handoff on the ledger.
  const handoffTask = await createTask(
    request,
    auth,
    p1.id,
    "Spec the launch",
    alice.id,
  );
  await dispatchAll(request, auth);
  await updateTask(request, auth, handoffTask.id, { assignee_id: bob.id });
  await dispatchAll(request, auth);

  // shared-capacity contention on the same constrained capability.
  for (const pid of [p1.id, phx.id]) {
    await createTask(
      request,
      auth,
      pid,
      "Machine learning model serving setup",
      iris.id,
    );
    const done = await createTask(
      request,
      auth,
      pid,
      "Machine learning model serving setup",
      iris.id,
    );
    await transition(request, auth, done.id, "completed");
    await addProjectMember(request, auth, pid, iris.id);
  }
  await dispatchAll(request, auth);

  // coordination gap: two teams on one project with no collaboration evidence.
  const team1 = (await (
    await request.post(`${API}/teams`, {
      headers: auth,
      data: { name: "Platform", code: `plat${t.slice(-4)}` },
    })
  ).json()) as { id: string };
  const team2 = (await (
    await request.post(`${API}/teams`, {
      headers: auth,
      data: { name: "Growth", code: `grow${t.slice(-4)}` },
    })
  ).json()) as { id: string };
  const jill = await hire(
    request,
    auth,
    `g2d${t}@coord.co`,
    "Jill",
    "One",
    team1.id,
  );
  const jon = await hire(
    request,
    auth,
    `g2e${t}@coord.co`,
    "Jon",
    "Two",
    team2.id,
  );
  await addProjectMember(request, auth, p1.id, jill.id);
  await addProjectMember(request, auth, p1.id, jon.id);
  await dispatchAll(request, auth);

  // blocked critical paths: propagation on Apollo, then a critical conflict.
  const m = (await request
    .post(`${API}/milestones`, {
      headers: auth,
      data: { project_id: p1.id, name: "GA", status: "pending" },
    })
    .then((r) => r.json())) as { id: string };
  const a1 = await createTask(request, auth, p1.id, "Prep the payload", bob.id);
  const b1 = await createTask(
    request,
    auth,
    p1.id,
    "Blocked core work",
    bob.id,
    m.id,
  );
  await addDependency(request, auth, b1.id, a1.id);
  await transition(request, auth, b1.id, "blocked");
  await dispatchAll(request, auth);

  const a2 = await createTask(
    request,
    auth,
    phx.id,
    "Prep the payload",
    iris.id,
  );
  const b2 = await createTask(
    request,
    auth,
    phx.id,
    "Blocked core work",
    iris.id,
  );
  await addDependency(request, auth, b2.id, a2.id);
  await transition(request, auth, b2.id, "blocked");
  await dispatchAll(request, auth);

  // ----------------------------------------------------------- API contract
  const center = (await (
    await request.get(`${BRAIN}/execution/coordination/center`, {
      headers: auth,
    })
  ).json()) as {
    total_incidents: number;
    counts: {
      shared_capacity: number;
      coordination_gap: number;
      propagation_risk: number;
      critical_conflict: number;
    };
    incidents: Array<{
      incident_id: string;
      kind: string;
      severity: string;
      title: string;
      confidence: number;
      evidence: string[];
    }>;
    handoffs: { pending: number; avg_duration_hours: number | null };
    recommendations: Array<{ kind: string; why: string[]; confidence: number }>;
    projects_affected: Array<{ name: string; incident_count: number }>;
  };
  expect(center.total_incidents).toBeGreaterThanOrEqual(4);
  expect(center.counts.shared_capacity).toBeGreaterThanOrEqual(1);
  expect(center.counts.coordination_gap).toBeGreaterThanOrEqual(1);
  expect(center.counts.propagation_risk).toBeGreaterThanOrEqual(1);
  expect(center.counts.critical_conflict).toBeGreaterThanOrEqual(1);
  const conflict = center.incidents.find((i) => i.kind === "critical_conflict");
  expect(conflict).toBeTruthy();
  expect(conflict!.severity).toBe("critical");
  expect(conflict!.confidence).toBeGreaterThan(0);
  expect(conflict!.evidence.length).toBeGreaterThan(0);
  expect(center.recommendations[0].kind).toBe("critical_conflict");
  expect(center.recommendations[0].why.length).toBeGreaterThan(0);
  expect(center.handoffs.pending).toBeGreaterThanOrEqual(1);
  expect(
    center.projects_affected.some((p) => p.name === "E2E Apollo Launch"),
  ).toBe(true);

  // the per-project coordination record is bounded: options + boundaries.
  const detail = (await (
    await request.get(`${BRAIN}/execution/coordination/projects/${p1.id}`, {
      headers: auth,
    })
  ).json()) as {
    name: string;
    handoffs: {
      pending: Array<{ from_owner: string; to_owner: string }>;
      recent_completed: unknown[];
    };
    propagation: unknown[];
    alternatives: unknown[];
    what_if: {
      options: Array<{ kind: string; boundary: string }>;
      boundary: string;
    };
  };
  expect(detail.name).toBe("E2E Apollo Launch");
  expect(
    detail.handoffs.pending.some(
      (h) => h.from_owner.includes("Alice") && h.to_owner.includes("Bob"),
    ),
  ).toBe(true);
  expect(detail.propagation.length).toBeGreaterThan(0);
  expect(Array.isArray(detail.alternatives)).toBe(true);
  expect(detail.what_if.boundary).toContain(
    "bounded options for humans to evaluate",
  );
  expect(detail.what_if.options.length).toBeGreaterThan(0);
  for (const option of detail.what_if.options) {
    expect(["delay", "reassign", "knowledge"]).toContain(option.kind);
    expect(option.boundary.length).toBeGreaterThan(0);
  }

  // ---------------------------------------------------------------- UI check
  await page.goto("/execution");
  await expect(
    page.getByRole("heading", { name: "Execution Command Center" }),
  ).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: /^Coordination/ }).click();

  // the coordination center surfaces counts, findings and evidence.
  await expect(page.getByText("Open findings", { exact: true })).toBeVisible({
    timeout: 30_000,
  });
  await expect(
    page.getByText("critical_conflict", { exact: true }).first(),
  ).toBeVisible({ timeout: 20_000 });
  await expect(
    page.getByText("coordination_gap", { exact: true }).first(),
  ).toBeVisible();
  await expect(
    page.getByText("shared_capacity", { exact: true }).first(),
  ).toBeVisible();
  await expect(
    page.getByText("propagation_risk", { exact: true }).first(),
  ).toBeVisible();
  await expect(page.getByText(conflict!.title)).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.getByText(/propagates:/i).first()).toBeVisible();
  await expect(page.getByText(/Recommended focus/).first()).toBeVisible();
  await expect(page.getByText("Handoff ledger", { exact: true })).toBeVisible();
  await expect(
    page.getByText("Pending handoffs", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Advisory only", { exact: true })).toBeVisible();

  // open the project coordination record: ledger, propagation, what-if.
  await page
    .getByRole("button", { name: /E2E Apollo Launch/ })
    .first()
    .click();
  await expect(
    page.getByText("E2E Apollo Launch · coordination record"),
  ).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/Alice One/).first()).toBeVisible({
    timeout: 20_000,
  });
  await expect(
    page.getByText("Propagation history", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("What if we change course?", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText(/Shift dates by \d+ days/i)).toBeVisible({
    timeout: 20_000,
  });
  await expect(
    page.getByText(/bounded options for humans to evaluate/i),
  ).toBeVisible();
  await page.getByRole("button", { name: "Close coordination record" }).click();

  // a human resolves the critical conflict from the UI; it stays resolved.
  const conflictCard = page.locator("li", { hasText: conflict!.title }).first();
  await conflictCard
    .getByPlaceholder("resolve note")
    .fill("E2E standup agreement");
  await conflictCard.getByRole("button", { name: /resolve/i }).click();
  await expect(conflictCard).toHaveCount(0, { timeout: 30_000 });
  const after = (await (
    await request.get(`${BRAIN}/execution/coordination/center`, {
      headers: auth,
    })
  ).json()) as { incidents: Array<{ incident_id: string; kind: string }> };
  expect(
    after.incidents.some((i) => i.incident_id === conflict!.incident_id),
  ).toBe(false);
  expect(after.incidents.some((i) => i.kind === "critical_conflict")).toBe(
    true,
  );

  await page.close();
});
