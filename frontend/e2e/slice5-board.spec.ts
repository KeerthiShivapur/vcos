import { expect, test, type APIRequestContext, type BrowserContext, type Locator, type Page } from "@playwright/test";

const API = "http://localhost:8999/api/v1";

function ts(): string {
  return Date.now().toString().slice(-8);
}

async function dragCard(page: Page, source: Locator, target: Locator) {
  const dt = await page.evaluateHandle(() => new DataTransfer());
  await source.evaluate((node, data) => {
    node.dispatchEvent(new DragEvent("dragstart", { bubbles: true, cancelable: true, dataTransfer: data as DataTransfer }));
  }, dt);
  await target.evaluate((node, data) => {
    node.dispatchEvent(new DragEvent("dragover", { bubbles: true, cancelable: true, dataTransfer: data as DataTransfer }));
  }, dt);
  await target.evaluate((node, data) => {
    node.dispatchEvent(new DragEvent("drop", { bubbles: true, cancelable: true, dataTransfer: data as DataTransfer }));
  }, dt);
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

test("work board: drag-and-drop transitions, dependency guard, project + sprint filters", async ({ browser, request }) => {
  test.setTimeout(360_000);
  const t = ts();
  const email = `board${t}@acme.com`;
  const password = "StrongPass123!";

  // 1. Founder registers.
  const ctx: BrowserContext = await browser.newContext();
  const page = await ctx.newPage();
  await registerOrg(page, `Board Co ${t}`, `bd-${t}`, email, "Ada", password);
  const token = (await apiLogin(request, email, password)).access_token;
  const auth = { Authorization: `Bearer ${token}` };

  // 2. Seed project, sprint, tasks and a dependency via API.
  const project = await (await request.post(`${API}/projects`, {
    headers: auth,
    data: { name: "Nova", code: `nv${t.slice(0, 4)}`, status: "active" },
  })).json();
  const sprint = await (await request.post(`${API}/sprints`, {
    headers: auth,
    data: { project_id: project.id, name: "Sprint One", start_date: "2026-08-01", end_date: "2026-08-14" },
  })).json();
  const t1 = await (await request.post(`${API}/tasks`, {
    headers: auth,
    data: { project_id: project.id, sprint_id: sprint.id, title: "Design login screen", priority: "high", status: "backlog" },
  })).json();
  const t2 = await (await request.post(`${API}/tasks`, {
    headers: auth,
    data: { project_id: project.id, sprint_id: sprint.id, title: "Implement auth", priority: "critical", status: "in_progress" },
  })).json();
  await (await request.post(`${API}/tasks`, {
    headers: auth,
    data: { project_id: project.id, title: "Ship changelog", priority: "low", status: "completed" },
  })).json();
  const t4 = await (await request.post(`${API}/tasks`, {
    headers: auth,
    data: { project_id: project.id, title: "Release v2", priority: "medium", status: "backlog" },
  })).json();
  const t5 = await (await request.post(`${API}/tasks`, {
    headers: auth,
    data: { project_id: project.id, title: "Approve release", priority: "medium", status: "todo" },
  })).json();
  await request.post(`${API}/tasks/${t4.id}/dependencies`, {
    headers: auth,
    data: { depends_on_task_id: t5.id, kind: "blocking" },
  });

  // 3. Open the board, filter to the project, and verify columns.
  await page.goto("/board");
  await expect(page.getByRole("heading", { name: "Work board" })).toBeVisible({ timeout: 15_000 });
  await page.getByLabel("Project").selectOption({ label: "Nova" });
  const backlog = page.locator('[data-status="backlog"]');
  const inProgress = page.locator('[data-status="in_progress"]');
  const completed = page.locator('[data-status="completed"]');
  await expect(backlog.getByText("Design login screen")).toBeVisible({ timeout: 15_000 });
  await expect(backlog.getByText("Release v2")).toBeVisible();
  await expect(inProgress.getByText("Implement auth")).toBeVisible();
  await expect(completed.getByText("Ship changelog")).toBeVisible();
  await expect(backlog.getByText("1 blocker")).toBeVisible();

  // 4. Drag "Design login screen" from backlog to in_progress.
  await dragCard(page, backlog.getByText("Design login screen"), inProgress);
  await expect(page.getByText(/Design login screen → In Progress/)).toBeVisible({ timeout: 10_000 });
  const t1After = await (await request.get(`${API}/tasks/${t1.id}`, { headers: auth })).json();
  expect(t1After.status).toBe("in_progress");

  // 5. Dependency guard: "Release v2" cannot move while "Approve release" is open.
  await dragCard(page, backlog.getByText("Release v2"), inProgress);
  await expect(page.getByText(/unsatisfied dependencies/i)).toBeVisible({ timeout: 10_000 });
  const t4After = await (await request.get(`${API}/tasks/${t4.id}`, { headers: auth })).json();
  expect(t4After.status).toBe("backlog");

  // 6. Move "Implement auth" to completed.
  await dragCard(page, inProgress.getByText("Implement auth"), completed);
  await expect(page.getByText(/Implement auth → Completed/)).toBeVisible({ timeout: 10_000 });
  const t2After = await (await request.get(`${API}/tasks/${t2.id}`, { headers: auth })).json();
  expect(t2After.status).toBe("completed");

  // 7. Sprint filter narrows the board to sprint tasks.
  await page.getByLabel("Sprint").selectOption({ label: "Sprint One" });
  await expect(page.getByText("Ship changelog")).not.toBeVisible({ timeout: 10_000 });
  await expect(page.getByText("Release v2")).not.toBeVisible();
  await expect(page.getByRole("link", { name: "Design login screen" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Implement auth" })).toBeVisible();

  // 8. Rollups: the sprint reflects the completed task (1/2 done → 50%).
  const sprintAfter = await (await request.get(`${API}/sprints/${sprint.id}`, { headers: auth })).json();
  expect(sprintAfter.tasks_count).toBe(2);
  expect(sprintAfter.progress).toBe(50);

  // 9. The board is reachable from the sidebar under Work.
  await page.getByRole("link", { name: "Board", exact: true }).click();
  await expect(page).toHaveURL("http://localhost:3000/board", { timeout: 10_000 });
});
