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

test("task execution: assignee runs the work — edit, subtasks, comments, attachments, dependencies, activity", async ({
  browser,
  request,
}) => {
  test.setTimeout(360_000);
  const t = ts();
  const founderEmail = `ada${t}@acme.com`;
  const bobEmail = `bob${t}@acme.com`;
  const bobName = `Bob W${t}`;
  const password = "StrongPass123!";

  // 1. Founder registers and invites Bob (employee role).
  const founderCtx = await browser.newContext();
  const founder = await founderCtx.newPage();
  await registerOrg(
    founder,
    `Org Tasks ${t}`,
    `tk-${t}`,
    founderEmail,
    "Ada",
    password,
  );
  const founderToken = (await apiLogin(request, founderEmail, password))
    .access_token;
  const auth = { Authorization: `Bearer ${founderToken}` };

  await founder.goto("/settings?tab=members");
  await founder.getByRole("button", { name: /invite/i }).click();
  await founder.getByLabel("Email").fill(bobEmail);
  await founder.getByLabel("Full name (optional)").fill(bobName);
  await founder.getByRole("button", { name: "Send invitation" }).click();
  const inviteUrl = await founder
    .locator("code")
    .filter({ hasText: "http://localhost:3000/register?invite=" })
    .first()
    .textContent({ timeout: 10_000 });
  expect(inviteUrl).toContain("/register?invite=");
  await founder.getByRole("button", { name: "Done" }).click();

  const bobCtx = await browser.newContext();
  const bob = await bobCtx.newPage();
  await bob.goto(inviteUrl!);
  await bob.getByLabel("Your full name").fill(bobName);
  await bob.getByLabel("Password", { exact: true }).fill(password);
  await bob.getByLabel("Confirm password", { exact: true }).fill(password);
  await bob
    .getByRole("button", { name: "Accept invitation & continue" })
    .click();
  await bob.waitForURL("**/home", { timeout: 20_000 });
  const bobToken = (await apiLogin(request, bobEmail, password)).access_token;
  const bobAuth = { Authorization: `Bearer ${bobToken}` };

  const employees = await (
    await request.get(`${API}/employees`, { headers: auth })
  ).json();
  const bobEmp = employees.find((e: { email: string }) => e.email === bobEmail);
  expect(bobEmp).toBeTruthy();

  // 2. Founder sets up a project and the dependency graph via API.
  const project = await (
    await request.post(`${API}/projects`, {
      headers: auth,
      data: {
        name: "TaskOps",
        code: `to${t.slice(0, 4)}`,
        status: "active",
        description: "Work execution demo",
      },
    })
  ).json();
  const mainTask = await (
    await request.post(`${API}/tasks`, {
      headers: auth,
      data: {
        project_id: project.id,
        title: "Build checkout flow",
        description: "Design and ship the payment flow.",
        priority: "high",
        tags: ["urgent"],
        assignee_id: bobEmp.id,
        status: "backlog",
      },
    })
  ).json();
  const gateTask = await (
    await request.post(`${API}/tasks`, {
      headers: auth,
      data: {
        project_id: project.id,
        title: "Approve payment provider",
        priority: "medium",
        status: "backlog",
      },
    })
  ).json();
  const dep = await request.post(`${API}/tasks/${mainTask.id}/dependencies`, {
    headers: auth,
    data: { depends_on_task_id: gateTask.id, kind: "finish_to_start" },
  });
  expect(dep.status(), await dep.text()).toBe(201);

  // 3. Bob opens the tasks list — label badge and label filter work.
  await bob.goto("/tasks");
  await expect(bob.getByRole("heading", { name: "Tasks" })).toBeVisible();
  await expect(bob.getByText("Build checkout flow")).toBeVisible({
    timeout: 15_000,
  });
  await expect(bob.getByRole("table").getByText("urgent")).toBeVisible();
  await bob.getByLabel("Label").selectOption({ label: "urgent" });
  await expect(bob.getByText("Build checkout flow")).toBeVisible({
    timeout: 15_000,
  });

  // 4. Bob opens his task — blocked by the pending dependency.
  await bob.getByText("Build checkout flow").first().click();
  await expect(
    bob.getByRole("heading", { name: "Build checkout flow" }),
  ).toBeVisible({ timeout: 15_000 });
  await expect(bob.getByText(/blocked by:/i)).toBeVisible();
  await expect(
    bob.getByRole("link", { name: "Approve payment provider" }).first(),
  ).toBeVisible();

  // 5. Bob edits his own task (title, priority, due date, labels).
  await bob.getByRole("button", { name: "Edit" }).click();
  await bob.getByLabel("Title").fill("Build checkout flow (v2)");
  await bob.getByLabel("Priority").selectOption({ label: "critical" });
  await bob.getByLabel("Due date").fill("2026-12-31");
  await bob.getByLabel("Labels (comma separated)").fill("urgent, sales");
  await bob.getByRole("button", { name: "Save changes" }).click();
  await expect(bob.getByText("Task updated")).toBeVisible({ timeout: 10_000 });
  await expect(
    bob.getByRole("heading", { name: "Build checkout flow (v2)" }),
  ).toBeVisible();
  await expect(bob.getByText("sales")).toBeVisible();

  // 6. Bob comments and mentions the founder — the founder is notified.
  await bob
    .getByPlaceholder("Write a comment…")
    .fill(`@${founderEmail} please review the API design`);
  await bob.getByRole("button", { name: "Comment", exact: true }).click();
  await expect(bob.getByRole("main").getByText("Comment added")).toBeVisible({
    timeout: 10_000,
  });
  await expect(bob.getByText("please review the API design")).toBeVisible();
  await expect
    .poll(
      async () => {
        const res = await request.get(`${API}/notifications`, {
          headers: auth,
        });
        const body = await res.json();
        return body.items.map((n: { title: string }) => n.title);
      },
      { timeout: 180_000, intervals: [5_000, 10_000, 15_000] },
    )
    .toContain(`You were mentioned in: Build checkout flow (v2)`);

  // 7. Bob attaches a document to the task.
  await bob
    .getByPlaceholder("File name (e.g. spec.pdf)")
    .fill("checkout-spec.pdf");
  await bob
    .getByPlaceholder("https://…")
    .fill("https://example.com/checkout-spec.pdf");
  await bob.getByRole("button", { name: "Attach" }).click();
  await expect(bob.getByRole("main").getByText("Attachment added")).toBeVisible(
    { timeout: 10_000 },
  );
  await expect(
    bob.getByRole("link", { name: "checkout-spec.pdf" }),
  ).toBeVisible();

  // 8. Bob breaks the work into subtasks — parent progress follows.
  await bob.getByPlaceholder("New subtask…").fill("Design the API contract");
  await bob.getByRole("button", { name: "Add", exact: true }).click();
  await expect(bob.getByText("Subtask added")).toBeVisible({ timeout: 10_000 });
  await expect(bob.getByText("Design the API contract")).toBeVisible();
  await expect(bob.getByText("0/1 complete")).toBeVisible();
  await bob.getByTitle("Toggle done").click();
  await expect(bob.getByText("1/1 complete")).toBeVisible({ timeout: 10_000 });

  // 9. Bob walks the status ladder, then hits the blocked state on purpose.
  await bob.getByRole("button", { name: "Mark In Progress" }).click();
  await expect(bob.getByText(/Moved to in_progress/)).toBeVisible({
    timeout: 10_000,
  });
  await bob.getByRole("button", { name: "Mark Blocked" }).click();
  await expect(bob.getByText("blocked", { exact: true })).toBeVisible({
    timeout: 10_000,
  });

  // 10. Bob cannot edit an unassigned task (403 enforced).
  const forbidden = await request.patch(`${API}/tasks/${gateTask.id}`, {
    headers: bobAuth,
    data: { title: "hijacked" },
  });
  expect(forbidden.status()).toBe(403);

  // 11. Founder completes the gate — the dependency worker unblocks Bob's task.
  const complete = await request.post(
    `${API}/tasks/${gateTask.id}/transition`,
    {
      headers: auth,
      data: { status: "completed" },
    },
  );
  expect(complete.status(), await complete.text()).toBe(200);
  await expect
    .poll(
      async () => {
        const res = await request.get(`${API}/tasks/${mainTask.id}`, {
          headers: auth,
        });
        return (await res.json()).status;
      },
      { timeout: 120_000, intervals: [5_000, 10_000] },
    )
    .toBe("todo");
  await expect
    .poll(
      async () => {
        const res = await request.get(`${API}/notifications`, {
          headers: bobAuth,
        });
        const body = await res.json();
        return body.items.map((n: { title: string }) => n.title);
      },
      { timeout: 180_000, intervals: [5_000, 10_000, 15_000] },
    )
    .toContain(`Task unblocked: Build checkout flow (v2)`);

  // 12. Bob finishes the task from the UI; the banner is gone.
  await bob.goto(`/tasks/${mainTask.id}`);
  await expect(
    bob.getByRole("heading", { name: "Build checkout flow (v2)" }),
  ).toBeVisible();
  await expect(bob.getByText(/blocked by:/i)).not.toBeVisible();
  await bob.getByRole("button", { name: "Mark In Progress" }).click();
  await expect(bob.getByText(/Moved to in_progress/)).toBeVisible({
    timeout: 10_000,
  });
  await bob.getByRole("button", { name: "Mark Review" }).click();
  await bob.getByRole("button", { name: "Mark Completed" }).click();
  await expect(bob.getByText("Moved to completed")).toBeVisible({
    timeout: 10_000,
  });

  // 13. Activity history preserves the full execution trail.
  await expect(bob.getByText("Task completed")).toBeVisible();
  await expect(bob.getByText("Status changed").first()).toBeVisible();
  await expect(bob.getByText("Comment added")).toBeVisible();
  await expect(bob.getByText("Attachment added")).toBeVisible();
  await expect(bob.getByText("Task updated")).toBeVisible();

  // 14. Founder sees the finished task in the list.
  await founder.goto("/tasks");
  await expect(founder.getByText("Build checkout flow (v2)")).toBeVisible({
    timeout: 15_000,
  });
  await expect(
    founder
      .locator("tr", { hasText: "Build checkout flow (v2)" })
      .getByText("completed"),
  ).toBeVisible();

  await bobCtx.close();
  await founderCtx.close();
});
