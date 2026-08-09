import { expect, test, type APIRequestContext, type BrowserContext, type Page } from "@playwright/test";

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

test("people & organization journey: structure, hierarchy, notifications, permissions", async ({ browser, request }) => {
  test.setTimeout(240_000);
  const t = ts();
  const founderEmail = `alice${t}@acme.com`;
  const bobEmail = `bob${t}@acme.com`;
  const charlieEmail = `charlie${t}@acme.com`;
  const bobName = `Bob W${t}`;
  const charlieName = `Charlie E${t}`;
  const password = "StrongPass123!";

  // 1. Founder registers the company.
  const founderCtx = await browser.newContext();
  const founder = await founderCtx.newPage();
  await registerOrg(founder, `Org Slice2 ${t}`, `s2-${t}`, founderEmail, "Alice", password);
  const founderToken = (await apiLogin(request, founderEmail, password)).access_token;

  // 2. Invite Bob as an employee via Settings -> Members.
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

  // 3. Bob accepts the invitation in a fresh context.
  const bobCtx = await browser.newContext();
  const bob = await bobCtx.newPage();
  await bob.goto(inviteUrl!);
  await bob.getByLabel("Your full name").fill(bobName);
  await bob.getByLabel("Password", { exact: true }).fill(password);
  await bob.getByLabel("Confirm password", { exact: true }).fill(password);
  await bob.getByRole("button", { name: "Accept invitation & continue" }).click();
  await bob.waitForURL("**/home", { timeout: 20_000 });

  // 4. Founder adds Charlie through the People directory UI.
  await founder.goto("/people");
  await expect(founder.getByRole("heading", { name: "People" })).toBeVisible();
  await founder.getByRole("button", { name: "Add employee" }).click();
  await founder.getByLabel("First name").fill("Charlie");
  await founder.getByLabel("Last name").fill(`E${t}`);
  await founder.getByLabel("Work email").fill(charlieEmail);
  await founder.getByLabel("Designation").fill("Engineering Lead");
  await founder.getByRole("button", { name: "Create employee" }).click();
  await founder.waitForURL("**/people/**", { timeout: 15_000 });
  await expect(founder.getByRole("heading", { level: 1, name: charlieName })).toBeVisible();

  // 5. Founder creates the Engineering department.
  await founder.goto("/departments");
  await expect(founder.getByRole("heading", { name: "Departments", exact: true })).toBeVisible();
  await founder.getByRole("button", { name: "Create department" }).first().click();
  await founder.getByLabel("Name").fill("Engineering");
  await founder.getByLabel("Code").fill(`eng${t.slice(0, 4)}`);
  await founder.getByRole("dialog").getByRole("button", { name: "Create department" }).click();
  await expect(founder.getByText("Engineering")).toBeVisible({ timeout: 15_000 });

  // 6. Founder creates the Backend team inside Engineering.
  await founder.goto("/teams");
  await expect(founder.getByRole("heading", { name: "Teams", exact: true })).toBeVisible();
  await founder.getByRole("button", { name: "Create team" }).first().click();
  await founder.getByLabel("Name").fill("Backend");
  await founder.getByLabel("Code").fill(`be${t.slice(0, 4)}`);
  await founder.getByLabel("Department").selectOption({ label: "Engineering" });
  await founder.getByRole("dialog").getByRole("button", { name: "Create team" }).click();
  await expect(founder.getByText("Backend")).toBeVisible({ timeout: 15_000 });

  // 7. Resolve employee ids; Bob reports to Charlie (API, no UI for manager changes).
  const employees = (await request.get(`${API}/employees`, {
    headers: { Authorization: `Bearer ${founderToken}` },
  })).json();
  const bobEmp = (await employees).find((e: { email: string }) => e.email === bobEmail);
  const charlieEmp = (await employees).find((e: { email: string }) => e.email === charlieEmail);
  expect(bobEmp).toBeTruthy();
  expect(charlieEmp).toBeTruthy();

  const assign = await request.patch(`${API}/employees/${bobEmp.id}`, {
    headers: { Authorization: `Bearer ${founderToken}` },
    data: { manager_id: charlieEmp.id },
  });
  expect(assign.status(), await assign.text()).toBe(200);

  // 8. A reporting cycle is rejected and the database is left unchanged.
  const cycle = await request.patch(`${API}/employees/${charlieEmp.id}`, {
    headers: { Authorization: `Bearer ${founderToken}` },
    data: { manager_id: bobEmp.id },
  });
  expect(cycle.status()).toBe(400);
  expect((await cycle.json()).detail).toMatch(/cycle/i);
  const bobAfter = await (await request.get(`${API}/employees/${bobEmp.id}`, {
    headers: { Authorization: `Bearer ${founderToken}` },
  })).json();
  expect(bobAfter.manager_id).toBe(charlieEmp.id);

  // 9. The org chart shows Bob under Charlie.
  await founder.goto("/organization");
  await expect(founder.getByRole("heading", { name: "Organization" })).toBeVisible();
  await founder.getByRole("button", { name: "Expand all" }).click();
  await expect(founder.getByText(charlieName).first()).toBeVisible({ timeout: 15_000 });
  await expect(founder.getByText(bobName).first()).toBeVisible({ timeout: 15_000 });

  // 10. Charlie's profile lists Bob as a direct report.
  await founder.goto(`/people/${charlieEmp.id}`);
  await expect(founder.getByText(bobName).first()).toBeVisible({ timeout: 15_000 });

  // 11. Bob was notified of the manager change (delivered by the background event worker).
  const bobToken = (await apiLogin(request, bobEmail, password)).access_token;
  await expect
    .poll(
      async () => {
        const res = await request.get(`${API}/notifications`, {
          headers: { Authorization: `Bearer ${bobToken}` },
        });
        const body = await res.json();
        return body.items.map((n: { title: string }) => n.title);
      },
      { timeout: 180_000, intervals: [5_000, 10_000, 15_000] },
    )
    .toContain("Manager changed");

  // 12. Bob (employee role) sees People/Departments/Teams but no manage actions.
  await bob.goto("/departments");
  await expect(bob.getByRole("heading", { name: "Departments" })).toBeVisible();
  await expect(bob.getByRole("button", { name: "Create department" })).not.toBeVisible();
  await bob.goto("/teams");
  await expect(bob.getByRole("heading", { name: "Teams", exact: true })).toBeVisible();
  await expect(bob.getByRole("button", { name: "Create team" })).not.toBeVisible();
  await bob.goto("/people");
  await expect(bob.getByRole("heading", { name: "People" })).toBeVisible();

  await bobCtx.close();
  await founderCtx.close();
});

test("people & organization: audit trail for org changes", async ({ request }) => {
  const t = ts();
  const reg = await request.post(`${API}/auth/register`, {
    data: {
      organization_name: `Audit Org ${t}`,
      organization_slug: `audit-${t}`,
      industry: "Software",
      country: "US",
      timezone: "UTC",
      currency: "USD",
      full_name: "Ada Owner",
      email: `auditboss${t}@acme.com`,
      password: "StrongPass123!",
    },
  });
  expect(reg.status(), await reg.text()).toBe(201);
  const boss = (await reg.json()) as { access_token: string };
  const auth = { Authorization: `Bearer ${boss.access_token}` };

  const dept = await (await request.post(`${API}/departments`, {
    headers: auth,
    data: { name: "Engineering", code: `eng${t.slice(0, 4)}` },
  })).json();
  const emp = await (await request.post(`${API}/employees`, {
    headers: auth,
    data: { first_name: "Dana", email: `dana${t}@acme.com`, designation: "Engineer" },
  })).json();
  const me = await (await request.get(`${API}/employees`, { headers: auth })).json();
  const ada = me.find((e: { email: string }) => e.email === `auditboss${t}@acme.com`);

  const moved = await request.patch(`${API}/employees/${emp.id}`, {
    headers: auth,
    data: { manager_id: ada.id, department_id: dept.id, designation: "Senior Engineer" },
  });
  expect(moved.status(), await moved.text()).toBe(200);

  const audit = await (await request.get(`${API}/audit`, { headers: auth })).json();
  const actions = new Set(audit.items.map((e: { action: string }) => e.action));
  expect(actions.has("department.created")).toBe(true);
  expect(actions.has("employee.created")).toBe(true);
  expect(actions.has("manager.changed")).toBe(true);
  expect(actions.has("employee.transferred")).toBe(true);
  expect(actions.has("employee.promoted")).toBe(true);
});
