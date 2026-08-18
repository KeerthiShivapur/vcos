import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const API = "http://127.0.0.1:8999/api/v1";

function ts(): string {
  return Date.now().toString().slice(-8);
}

function daysAgo(n: number): string {
  return new Date(Date.now() - n * 86_400_000).toISOString().slice(0, 10);
}

async function apiRegister(ctx: APIRequestContext, name: string, slug: string, email: string, password: string) {
  const r = await ctx.post(`${API}/auth/register`, {
    data: {
      organization_name: name,
      organization_slug: slug,
      industry: "Software",
      country: "US",
      full_name: "Zoe",
      email,
      password,
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

async function createProject(
  request: APIRequestContext,
  auth: Record<string, string>,
  name: string,
  code: string
): Promise<{ id: string }> {
  const r = await request.post(`${API}/projects`, {
    headers: auth,
    data: { name, code, status: "draft" },
  });
  expect(r.status(), await r.text()).toBe(201);
  return (await r.json()) as { id: string };
}

async function startProject(request: APIRequestContext, auth: Record<string, string>, id: string) {
  const r = await request.post(`${API}/projects/${id}/lifecycle`, { headers: auth, data: { action: "start" } });
  expect(r.status(), await r.text()).toBe(200);
}

async function createTask(
  request: APIRequestContext,
  auth: Record<string, string>,
  projectId: string,
  title: string,
  extra: Record<string, unknown> = {}
): Promise<{ id: string }> {
  const r = await request.post(`${API}/tasks`, {
    headers: auth,
    data: { title, project_id: projectId, status: "todo", ...extra },
  });
  expect(r.status(), await r.text()).toBe(201);
  return (await r.json()) as { id: string };
}

async function addDependency(
  request: APIRequestContext,
  auth: Record<string, string>,
  taskId: string,
  on: string,
  kind = "finish_to_start"
) {
  const r = await request.post(`${API}/tasks/${taskId}/dependencies`, {
    headers: auth,
    data: { depends_on_task_id: on, kind },
  });
  expect(r.status(), await r.text()).toBe(201);
}

async function transition(request: APIRequestContext, auth: Record<string, string>, taskId: string, status: string) {
  const r = await request.post(`${API}/tasks/${taskId}/transition`, { headers: auth, data: { status } });
  expect(r.status(), await r.text()).toBe(200);
}

test("slice 4g.1: the execution command center is one governed UI over the canonical execution record", async ({
  browser,
  request,
}) => {
  test.setTimeout(900_000);
  const t = ts();
  const email = `exec${t}@acme.com`;
  const password = "StrongPass123!";

  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  page.on("console", (msg) => {
    if (msg.type() === "error") console.log(`[${Date.now() % 100000}] console:error ${msg.text().slice(0, 200)}`);
  });

  await apiRegister(request, `Execution Co ${t}`, `exec-${t}`, email, password);
  const token = (await apiLogin(request, email, password)).access_token;
  const auth = { Authorization: `Bearer ${token}` };

  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL("**/home", { timeout: 30_000 });

  // ---------------------------------------------------------------- seeding
  const project = await createProject(request, auth, "E2E Atlas Launch", `atl${t.slice(-4)}`);
  await startProject(request, auth, project.id);
  const a = await createTask(request, auth, project.id, "A: spec the launch", { estimate_hours: 4 });
  const b = await createTask(request, auth, project.id, "B: build the payload", {
    estimate_hours: 2,
    due_date: daysAgo(3),
  });
  const c = await createTask(request, auth, project.id, "C: launch the atlas", { estimate_hours: 3 });
  await addDependency(request, auth, b.id, a.id);
  await addDependency(request, auth, c.id, b.id);
  await addDependency(request, auth, c.id, a.id, "blocking");
  await transition(request, auth, c.id, "blocked");
  await dispatchAll(request, auth);

  // ----------------------------------------------------------- API contract
  // 1. the command center surfaces the project with health + one explain.
  const command = (await (
    await request.get(`${API}/brain/execution/command`, { headers: auth })
  ).json()) as {
    total_projects: number;
    projects: Array<{
      name: string;
      health_status: string;
      health_score: number;
      primary_cause: string | null;
      explain: string;
      counts: { critical_overdue_tasks: number; blocked_tasks: number };
    }>;
  };
  expect(command.total_projects).toBe(1);
  expect(command.projects[0].name).toBe("E2E Atlas Launch");
  expect(["at_risk", "critical"]).toContain(command.projects[0].health_status);
  expect(command.projects[0].health_score).toBeLessThan(80);
  expect(command.projects[0].primary_cause).toBe("Timeline pressure");
  expect(command.projects[0].explain).toContain("critical-path task(s) past due");
  expect(command.projects[0].counts.critical_overdue_tasks).toBe(1);
  expect(command.projects[0].counts.blocked_tasks).toBe(1);

  // 2. the critical path is the real CPM over the task graph.
  const detail = (await (
    await request.get(`${API}/brain/execution/projects/${project.id}`, { headers: auth })
  ).json()) as {
    critical_path: {
      total_hours: number;
      projected_finish_hours: number;
      min_slack: number;
      critical_task_ids: string[];
    };
    blockers: Array<{ task_id: string; title: string; chain_depth: number; chain: Array<{ title: string }> }>;
  };
  expect(detail.critical_path.total_hours).toBe(9);
  expect(detail.critical_path.projected_finish_hours).toBe(9);
  expect(detail.critical_path.min_slack).toBe(0);
  expect(detail.critical_path.critical_task_ids.sort()).toEqual([a.id, b.id, c.id].sort());
  expect(detail.blockers).toHaveLength(1);
  expect(detail.blockers[0].chain[detail.blockers[0].chain.length - 1].title).toBe("A: spec the launch");
  const deepDepth = detail.blockers[0].chain_depth;
  expect([1, 2]).toContain(deepDepth);

  // 3. next-first prioritization always answers "what should we do next?".
  const next = (await (
    await request.get(`${API}/brain/execution/next`, { headers: auth })
  ).json()) as { total: number; items: Array<{ kind: string; project_name: string }> };
  expect(next.total).toBeGreaterThanOrEqual(2);
  expect(next.items[0].kind).toBe("critical");
  expect(next.items[0].project_name).toBe("E2E Atlas Launch");
  expect(next.items.map((i) => i.kind)).toContain("blocked");

  // 4. the mandatory outcome record never rewrites the project.
  const outcome = (await (
    await request.post(`${API}/brain/execution/projects/${project.id}/outcome`, {
      headers: auth,
      data: {
        status: "partial",
        planned_outcome: "Ship the atlas payload",
        actual_outcome: "Ship the probe only",
        assessment: "Blocked by the dependency chain",
      },
    })
  ).json()) as { status: string; assessment: string };
  expect(outcome.status).toBe("partial");
  expect(outcome.assessment).toBe("Blocked by the dependency chain");
  const after = (await (
    await request.get(`${API}/brain/execution/projects/${project.id}`, { headers: auth })
  ).json()) as { status: string; outcome: { status: string } };
  expect(after.status).toBe("active");
  expect(after.outcome.status).toBe("partial");

  // ---------------------------------------------------------------- UI check
  await page.goto("/execution");
  await expect(page.getByRole("heading", { name: "Execution Command Center" })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("Execution Center", { exact: true })).toBeVisible({ timeout: 20_000 });

  // the command center rows surface health, explain and the primary cause.
  await expect(page.getByText(/E2E Atlas Launch/).first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("Timeline pressure", { exact: true }).first()).toBeVisible();
  await expect(page.getByText(/critical-path task\(s\) past due/i).first()).toBeVisible();
  await expect(page.getByText(/critical past due/i).first()).toBeVisible();

  // the next-first list prioritizes the overdue critical-path work.
  await expect(page.getByText(/Complete 'B: build the payload' on the critical path/i)).toBeVisible(
    { timeout: 20_000 }
  );
  await expect(page.getByText(/It is past due and drives the projected finish of E2E Atlas Launch/)).toBeVisible();

  // open the execution record: critical path, blocker chains, history.
  await page.getByRole("button", { name: /E2E Atlas Launch/ }).first().click();
  await expect(page.getByText("E2E Atlas Launch · execution record")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/min slack 0h/i)).toBeVisible();
  await expect(page.getByText("A: spec the launch", { exact: true }).first()).toBeVisible();
  await expect(page.getByText(/1 critical-path task\(s\) past due/i).first()).toBeVisible();
  await expect(page.getByText(/What changed over time ·/i)).toBeVisible();

  // the recorded outcome is visible and the project stayed untouched.
  await expect(page.getByText("outcome: partial", { exact: true })).toBeVisible();

  // ask the brain from the command center and see the execution answer.
  await page.getByPlaceholder(/is the atlas launch on track/i).fill("is the E2E Atlas Launch project on track?");
  await page.getByRole("button", { name: /ask/i }).click();
  await expect(page.getByText("execution", { exact: true }).first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/critical-path task\(s\) past due/i).first()).toBeVisible();
  await expect(page.getByText(/min slack 0h/i).first()).toBeVisible();

  await page.close();
});