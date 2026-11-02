import {
  expect,
  test,
  type APIRequestContext,
  type BrowserContext,
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

test("project execution: epics, sprint planning, sprint lifecycle, rollups, project lifecycle, delete rules", async ({
  browser,
  request,
}) => {
  test.setTimeout(360_000);
  const t = ts();
  const email = `ops${t}@acme.com`;
  const password = "StrongPass123!";

  // 1. Founder registers.
  const ctx: BrowserContext = await browser.newContext();
  const page = await ctx.newPage();
  await registerOrg(page, `Ops Corp ${t}`, `op-${t}`, email, "Ada", password);
  const token = (await apiLogin(request, email, password)).access_token;
  const auth = { Authorization: `Bearer ${token}` };

  // 2. Seed project, epic, tasks and a planned sprint via API.
  const project = await (
    await request.post(`${API}/projects`, {
      headers: auth,
      data: {
        name: "Orbit",
        code: `or${t.slice(0, 4)}`,
        status: "active",
        description: "Project execution demo",
      },
    })
  ).json();
  const epic = await (
    await request.post(`${API}/epics`, {
      headers: auth,
      data: {
        project_id: project.id,
        name: "Core platform",
        description: "Foundational platform work",
        priority: "high",
      },
    })
  ).json();
  const taskA = await (
    await request.post(`${API}/tasks`, {
      headers: auth,
      data: {
        project_id: project.id,
        title: "Fix payment bug",
        priority: "high",
        status: "backlog",
      },
    })
  ).json();
  const taskB = await (
    await request.post(`${API}/tasks`, {
      headers: auth,
      data: {
        project_id: project.id,
        title: "Write API docs",
        priority: "medium",
        status: "backlog",
      },
    })
  ).json();
  const sprint = await (
    await request.post(`${API}/sprints`, {
      headers: auth,
      data: {
        project_id: project.id,
        name: "Sprint Alpha",
        goal: "Ship the fixes",
        start_date: "2026-08-01",
        end_date: "2026-08-14",
      },
    })
  ).json();

  // 3. Project page: Structure tab — epic lifecycle buttons.
  // Page-load fetches can take ~20s worst case (a dropped request is retried
  // once with a 10s cap per attempt), so allow 30s for the first render.
  await page.goto(`/projects/${project.id}`);
  await expect(page.getByRole("heading", { name: "Orbit" })).toBeVisible({
    timeout: 30_000,
  });
  await page.getByRole("button", { name: /Structure/ }).click();
  await expect(page.getByText("Core platform")).toBeVisible();
  await page
    .getByRole("button", { name: "Start", exact: true })
    .first()
    .click();
  await expect(page.getByText("Epic started")).toBeVisible({ timeout: 10_000 });
  const epicAfterStart = await (
    await request.get(`${API}/epics/${epic.id}`, { headers: auth })
  ).json();
  expect(epicAfterStart.status).toBe("in_progress");

  // 4. Sprint planning: assign both backlog tasks to the sprint via the UI, then start it.
  // Each Add moves the task out of the backlog, so wait for the Add-button
  // count to drop before clicking again (avoids double-clicking one task).
  const sprintCard = page
    .locator(".rounded-xl.border")
    .filter({ hasText: "Sprint Alpha" })
    .last();
  const addButtons = sprintCard.getByRole("button", {
    name: "Add",
    exact: true,
  });
  await expect(sprintCard.getByText("planned")).toBeVisible();
  await sprintCard.getByRole("button", { name: "Plan tasks" }).click();
  await expect(addButtons).toHaveCount(2);
  await addButtons.first().click();
  await expect(addButtons).toHaveCount(1);
  await expect(sprintCard.getByText("Fix payment bug")).toBeVisible({
    timeout: 10_000,
  });
  await addButtons.first().click();
  await expect(addButtons).toHaveCount(0);
  await expect(sprintCard.getByText("Write API docs")).toBeVisible({
    timeout: 10_000,
  });
  await sprintCard.getByRole("button", { name: "Start", exact: true }).click();
  await expect(sprintCard.getByText("active")).toBeVisible({ timeout: 10_000 });

  const sprintAfterPlan = await (
    await request.get(`${API}/sprints/${sprint.id}`, { headers: auth })
  ).json();
  expect(sprintAfterPlan.status).toBe("active");
  expect(sprintAfterPlan.tasks_count).toBe(2);

  // 5. Complete a task via API → sprint progress rolls up and the UI reflects it.
  await request.patch(`${API}/tasks/${taskA.id}`, {
    headers: auth,
    data: { status: "completed" },
  });
  await page.reload();
  await expect(page.getByRole("button", { name: /Structure/ })).toBeVisible({
    timeout: 30_000,
  });
  await page.getByRole("button", { name: /Structure/ }).click();
  await expect(sprintCard.getByText(/1\/2 tasks done/)).toBeVisible({
    timeout: 10_000,
  });
  const sprintAfterDone = await (
    await request.get(`${API}/sprints/${sprint.id}`, { headers: auth })
  ).json();
  expect(sprintAfterDone.progress).toBe(50);

  // 6. Complete the sprint → unfinished tasks return to the backlog.
  await sprintCard
    .getByRole("button", { name: "Complete", exact: true })
    .click();
  await expect(sprintCard.getByText("completed")).toBeVisible({
    timeout: 10_000,
  });
  await expect(sprintCard.getByText(/1\/1 tasks done/)).toBeVisible();
  await expect(sprintCard.getByText("Write API docs")).not.toBeVisible();
  const allTasks = await (
    await request.get(`${API}/tasks?project_id=${project.id}`, {
      headers: auth,
    })
  ).json();
  const taskBAfter = allTasks.find((x: { id: string }) => x.id === taskB.id);
  expect(taskBAfter.sprint_id).toBeNull();
  const taskAAfter = allTasks.find((x: { id: string }) => x.id === taskA.id);
  expect(taskAAfter.sprint_id).toBe(sprint.id);

  // 7. Project lifecycle via header buttons: complete → archive → delete rules.
  await page
    .getByRole("button", { name: "Complete", exact: true })
    .first()
    .click();
  await expect(page.getByText("Project complete")).toBeVisible({
    timeout: 10_000,
  });
  const projectCompleted = await (
    await request.get(`${API}/projects/${project.id}`, { headers: auth })
  ).json();
  expect(projectCompleted.status).toBe("completed");

  await page.getByRole("button", { name: "Archive", exact: true }).click();
  await expect(page.getByText("Project archive")).toBeVisible({
    timeout: 10_000,
  });
  const projectArchived = await (
    await request.get(`${API}/projects/${project.id}`, { headers: auth })
  ).json();
  expect(projectArchived.status).toBe("archived");
  await expect(
    page.getByRole("button", { name: "Delete", exact: true }),
  ).toBeVisible();

  // 8. Draft projects can be deleted (archive/completed ones cannot).
  const draft = await (
    await request.post(`${API}/projects`, {
      headers: auth,
      data: { name: "Disposable", code: `dp${t.slice(0, 4)}`, status: "draft" },
    })
  ).json();
  await page.goto(`/projects/${draft.id}`);
  await expect(page.getByRole("heading", { name: "Disposable" })).toBeVisible({
    timeout: 30_000,
  });
  await expect(
    page.getByRole("button", { name: "Start", exact: true }),
  ).toBeVisible();
  page.once("dialog", (d) => d.accept());
  await page.getByRole("button", { name: "Delete", exact: true }).click();
  await page.waitForURL("**/projects", { timeout: 15_000 });
  const gone = await request.get(`${API}/projects/${draft.id}`, {
    headers: auth,
  });
  expect(gone.status()).toBe(404);

  // 9. Timeline shows lifecycle events.
  await page.goto(`/projects/${project.id}`);
  await expect(page.getByText(/Sprint started: Sprint Alpha/)).toBeVisible({
    timeout: 15_000,
  });
  await expect(page.getByText(/Sprint completed: Sprint Alpha/)).toBeVisible();
});
