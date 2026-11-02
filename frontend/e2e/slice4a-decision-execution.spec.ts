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

test("slice 4a: decision follow-up action converts to a task and implementing closes the loop", async ({
  browser,
  request,
}) => {
  test.setTimeout(420_000);
  const t = ts();
  const founderEmail = `ada4a${t}@acme.com`;
  const bobEmail = `bob4a${t}@acme.com`;
  const bobName = `Bob 4A${t}`;
  const password = "StrongPass123!";
  const decisionTitle = "Launch the enterprise portal";
  const actionText = "Build the onboarding flow";
  const contextText = "Reduce onboarding time for enterprise customers.";

  // 1. Founder registers and invites Bob.
  const founderCtx = await browser.newContext();
  const founder = await founderCtx.newPage();
  await registerOrg(
    founder,
    `Org 4A ${t}`,
    `t4a-${t}`,
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
  // The invite UI has a built-in recovery path (4s soft cap → recheck →
  // resend) for the occasionally dropped request; give it headroom.
  const inviteUrl = await founder
    .locator("code")
    .filter({ hasText: "http://localhost:3000/register?invite=" })
    .first()
    .textContent({ timeout: 30_000 });
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

  const employees = await (
    await request.get(`${API}/employees`, { headers: auth })
  ).json();
  const bobEmp = employees.find((e: { email: string }) => e.email === bobEmail);
  expect(bobEmp).toBeTruthy();

  // 2. Founder creates a project + goal via API, then records the decision from the UI.
  const project = await (
    await request.post(`${API}/projects`, {
      headers: auth,
      data: {
        name: "Portal 4A",
        code: `p4a${t.slice(0, 4)}`,
        status: "active",
      },
    })
  ).json();
  const goal = await (
    await request.post(`${API}/goals`, {
      headers: auth,
      data: {
        name: "Improve activation",
        scope: "project",
        project_id: project.id,
        status: "planned",
      },
    })
  ).json();

  await founder.goto("/decisions/new");
  await expect(
    founder.getByRole("heading", { name: "New decision" }),
  ).toBeVisible();
  await founder.getByLabel("Title").fill(decisionTitle);
  await founder
    .getByLabel("Description")
    .fill("Adopt a dedicated customer portal.");
  await founder.getByLabel("Context").fill(contextText);
  await founder.locator('select[name="status"]').selectOption("made");
  await founder.getByRole("button", { name: "Add action" }).click();
  await founder
    .getByPlaceholder("Action text (e.g. Build the onboarding flow)")
    .fill(actionText);
  await founder
    .locator("select")
    .filter({ has: founder.locator("option").filter({ hasText: /^Owner$/ }) })
    .selectOption({ label: bobName });
  await founder
    .locator("select")
    .filter({ has: founder.locator("option").filter({ hasText: /^Project$/ }) })
    .selectOption({ label: "Portal 4A" });
  await founder
    .locator("select")
    .filter({ has: founder.locator("option").filter({ hasText: /^Goal$/ }) })
    .selectOption({ label: "Improve activation" });
  await founder.getByPlaceholder("Due date").fill("2026-12-31");
  await founder.getByRole("button", { name: "Record decision" }).click();
  await founder.waitForURL(/\/decisions\/[0-9a-f]{32}$/, { timeout: 20_000 });
  await expect(founder.getByText("Follow-up actions")).toBeVisible();
  await expect(founder.getByText(actionText)).toBeVisible();
  await expect(founder.getByText("1 open")).toBeVisible();
  await expect(founder.getByText(bobName)).toBeVisible();

  const decisionId = founder.url().split("/").pop()!;

  // 3. Founder converts the action into a task.
  await founder.getByRole("button", { name: "Convert to task" }).click();
  await expect(
    founder.getByText("Action converted to a task and assigned to its owner"),
  ).toBeVisible({ timeout: 15_000 });
  await expect(
    founder.getByRole("link", { name: new RegExp(`${actionText} · todo`) }),
  ).toBeVisible({ timeout: 15_000 });
  await expect(founder.getByText("1 open")).toBeVisible();

  // 4. The task is tenanted, lineage-carrying and visible via the decision.
  const tasks = await (
    await request.get(`${API}/decisions/${decisionId}/tasks`, { headers: auth })
  ).json();
  expect(tasks).toHaveLength(1);
  const task = tasks[0];
  expect(task.decision_id).toBe(decisionId);
  expect(task.goal_id).toBe(goal.id);
  expect(task.project_id).toBe(project.id);
  expect(task.assignee_id).toBe(bobEmp.id);
  expect(task.decision.title).toBe(decisionTitle);
  expect(task.description).toContain(contextText);
  expect(task.tags).toContain("decision");

  const detail = await (
    await request.get(`${API}/tasks/${task.id}`, { headers: auth })
  ).json();
  expect(detail.decision.reason).toBeTruthy();

  // 5. Bob sees the task on his work list with the decision cited, and the Why card.
  await bob.goto("/my-work");
  await expect(bob.getByText(actionText)).toBeVisible({ timeout: 15_000 });
  await expect(
    bob.getByText(`· from decision "${decisionTitle}"`),
  ).toBeVisible();

  await bob.goto(`/tasks/${task.id}`);
  await expect(bob.getByRole("heading", { name: actionText })).toBeVisible({
    timeout: 15_000,
  });
  await expect(bob.getByText("Why this task exists")).toBeVisible();
  await expect(bob.getByRole("link", { name: decisionTitle })).toBeVisible();
  await expect(bob.getByText("Reason", { exact: true })).toBeVisible();
  await expect(
    bob.getByText("Adopt a dedicated customer portal."),
  ).toBeVisible();
  await expect(bob.getByText(contextText, { exact: true })).toBeVisible();
  await expect(bob.getByText("Goal", { exact: true })).toBeVisible();
  await expect(bob.getByText("Improve activation")).toBeVisible();

  // 6. Bob was notified about the assignment from the decision.
  const bobNotifs = await (
    await request.get(`${API}/notifications`, {
      headers: { Authorization: `Bearer ${bobToken}` },
    })
  ).json();
  expect(
    bobNotifs.items
      .map((n: { title: string }) => n.title)
      .filter((title: string) =>
        title.includes(`from decision '${decisionTitle}'`),
      ),
  ).toHaveLength(1);

  // 7. Completing the produced task auto-implements the decision.
  const done = await request.post(`${API}/tasks/${task.id}/transition`, {
    headers: auth,
    data: { status: "completed" },
  });
  expect(done.status(), await done.text()).toBe(200);
  await expect
    .poll(
      async () => {
        const res = await request.get(`${API}/decisions/${decisionId}`, {
          headers: auth,
        });
        return (await res.json()).status;
      },
      { timeout: 120_000, intervals: [5_000, 10_000] },
    )
    .toBe("implemented");

  // 8. The founder sees the completed action in the UI.
  await founder.goto(`/decisions/${decisionId}`);
  await expect(
    founder.getByRole("link", {
      name: new RegExp(`${actionText} · completed`),
    }),
  ).toBeVisible({ timeout: 15_000 });
  await expect(founder.getByText("0 open")).toBeVisible();
  await expect(founder.getByText("implemented", { exact: true })).toBeVisible();

  // 9. The loop is fully audited: decision.executed + decision.implemented events exist.
  const events = await (
    await request.get(`${API}/events`, { headers: auth })
  ).json();
  const decisionEvents = events.items
    .map((e: { name: string }) => e.name)
    .filter((n: string) => n.startsWith("decision."));
  expect(decisionEvents).toContain("decision.executed");
  expect(decisionEvents).toContain("decision.implemented");

  await bobCtx.close();
  await founderCtx.close();
});
