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

test("workload & calendar: calendar feed merges events, meetings and task deadlines; team workload surfaces on analytics", async ({ browser, request }) => {
  test.setTimeout(360_000);
  const t = ts();
  const email = `wl${t}@acme.com`;
  const password = "StrongPass123!";

  // 1. Founder registers.
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await registerOrg(page, `Workload Co ${t}`, `wl-${t}`, email, "Ada", password);
  const token = (await apiLogin(request, email, password)).access_token;
  const auth = { Authorization: `Bearer ${token}` };

  // 2. A team is created and the founder joins it, so the analytics workload card has data.
  const team = await (await request.post(`${API}/teams`, {
    headers: auth,
    data: { name: "Platform", code: `pl${t.slice(0, 4)}` },
  })).json();
  const me = await (await request.get(`${API}/employees/me`, { headers: auth })).json();
  const join = await request.post(`${API}/teams/${team.id}/members`, {
    headers: auth,
    data: { employee_id: me.id },
  });
  expect(join.status(), await join.text()).toBe(201);

  // 3. A task due today is created via the API.
  const project = await (await request.post(`${API}/projects`, {
    headers: auth,
    data: { name: "Atlas", code: `at${t.slice(0, 4)}`, status: "active" },
  })).json();
  const today = new Date().toISOString().slice(0, 10);
  const task = await (await request.post(`${API}/tasks`, {
    headers: auth,
    data: { project_id: project.id, title: "Deliver weekly digest", priority: "medium", status: "todo", due_date: today },
  })).json();
  expect(task.id).toBeTruthy();

  // 4. A calendar event is created through the UI.
  await page.goto("/calendar");
  await expect(page.getByRole("heading", { name: "Calendar" })).toBeVisible({ timeout: 15_000 });
  await page.getByRole("button", { name: "New event" }).click();
  const dialog = page.locator('[role="dialog"]');
  await expect(dialog).toBeVisible({ timeout: 10_000 });
  await dialog.getByLabel("Title").fill("Weekly all hands");
  const now = new Date();
  const startLocal = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}T14:00`;
  await dialog.getByLabel("Start").fill(startLocal);
  await dialog.getByRole("button", { name: "Create event" }).click();
  await expect(page.getByText(/Event created/)).toBeVisible({ timeout: 10_000 });

  // 5. The merged feed shows both the event and the task deadline in the week view.
  const eventItem = page.locator("li", { hasText: "Weekly all hands" });
  const taskItem = page.locator("li", { hasText: "Deliver weekly digest" });
  await expect(eventItem).toBeVisible({ timeout: 10_000 });
  await expect(taskItem).toBeVisible({ timeout: 10_000 });
  await expect(eventItem.getByText("Event", { exact: true })).toBeVisible();
  await expect(taskItem.getByText("Task deadline", { exact: true })).toBeVisible();

  // 6. The source filter isolates task deadlines.
  await page.getByRole("button", { name: "Task deadline", exact: true }).click();
  await expect(taskItem).toBeVisible({ timeout: 10_000 });
  await expect(eventItem).toBeHidden();
  await page.getByRole("button", { name: "All", exact: true }).click();
  await expect(eventItem).toBeVisible({ timeout: 10_000 });

  // 7. The feed honors the range: an event outside the next 30 days does not appear.
  const future = new Date();
  future.setDate(future.getDate() + 45);
  const futureLocal = `${future.getFullYear()}-${String(future.getMonth() + 1).padStart(2, "0")}-${String(future.getDate()).padStart(2, "0")}T10:00`;
  await page.getByRole("button", { name: "New event" }).click();
  await dialog.getByLabel("Title").fill("Distant milestone");
  await dialog.getByLabel("Start").fill(futureLocal);
  await dialog.getByRole("button", { name: "Create event" }).click();
  await expect(page.getByText(/Event created/).first()).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText("Distant milestone")).toBeHidden();

  // 8. The analytics page surfaces team workload.
  await page.goto("/analytics");
  await expect(page.getByRole("heading", { name: "Executive Analytics" })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("Team workload", { exact: true })).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText("Platform")).toBeVisible({ timeout: 10_000 });
});
