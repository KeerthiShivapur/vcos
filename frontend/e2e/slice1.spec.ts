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

async function inviteByApi(ctx: APIRequestContext, token: string, email: string, role: string) {
  const r = await ctx.post(`${API}/users/invite`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { email, full_name: email.split("@")[0], role },
  });
  expect(r.status(), await r.text()).toBe(201);
  return (await r.json()) as { token: string; invitation: { id: string } };
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

test("founder journey: register, invite, accept, RBAC visibility", async ({ browser, request }) => {
  const t = ts();
  const orgName = `Acme Startup ${t}`;
  const slug = `acme-${t}`;
  const aliceEmail = `alice${t}@acme.com`;
  const bobEmail = `bob${t}@acme.com`;
  const password = "StrongPass123!";

  // 1. Founder registers the company.
  const aliceCtx = await browser.newContext();
  const alice = await aliceCtx.newPage();
  await registerOrg(alice, orgName, slug, aliceEmail, "Alice Founder", password);

  // Dashboard loads for the founder.
  await expect(alice.getByText(/good (morning|afternoon|evening), alice/i)).toBeVisible({ timeout: 15_000 });

  // 2. Alice opens Settings -> Members and invites Bob as employee.
  await alice.goto("/settings?tab=members");
  await expect(alice.getByRole("heading", { name: "Settings" })).toBeVisible();
  await alice.getByRole("button", { name: /invite/i }).click();
  await alice.getByLabel("Email").fill(bobEmail);
  await alice.getByLabel("Full name (optional)").fill("Bob Worker");
  await alice.getByRole("button", { name: "Send invitation" }).click();

  // Dev-mode email transport: the invite URL is shown in the result modal.
  const inviteUrl = await alice
    .locator("code")
    .filter({ hasText: "http://localhost:3000/register?invite=" })
    .first()
    .textContent({ timeout: 10_000 });
  expect(inviteUrl).toContain("/register?invite=");
  await alice.getByRole("button", { name: "Done" }).click();

  // 3. Bob opens the invite link in a fresh browser context and joins.
  const bobCtx = await browser.newContext();
  const bob = await bobCtx.newPage();
  await bob.goto(inviteUrl!);
  await bob.getByLabel("Your full name").fill("Bob Worker");
  await bob.getByLabel("Password", { exact: true }).fill(password);
  await bob.getByLabel("Confirm password", { exact: true }).fill(password);
  await bob.getByRole("button", { name: "Accept invitation & continue" }).click();
  await bob.waitForURL("**/home", { timeout: 20_000 });

  // 4. Bob cannot see admin surfaces: only the Organization tab remains.
  await bob.goto("/settings?tab=members");
  await expect(bob.getByRole("heading", { name: "Settings" })).toBeVisible();
  await expect(bob.getByRole("button", { name: "Members", exact: true })).not.toBeVisible();
  await expect(bob.getByRole("button", { name: "Roles", exact: true })).not.toBeVisible();
  await expect(bob.getByRole("button", { name: "Audit log", exact: true })).not.toBeVisible();
  await expect(bob.getByRole("button", { name: "Organization", exact: true })).toBeVisible();

  // Server-side guard: Bob cannot hit the invite API.
  const bobToken = await apiLogin(request, bobEmail, password);
  const blocked = await request.post(`${API}/users/invite`, {
    headers: { Authorization: `Bearer ${bobToken.access_token}` },
    data: { email: `x${t}@acme.com`, role: "employee" },
  });
  expect(blocked.status()).toBe(403);

  // 5. Alice sees Bob in the member directory.
  await alice.goto("/settings?tab=members");
  await expect(alice.locator("table").getByText(bobEmail)).toBeVisible({ timeout: 15_000 });

  await bobCtx.close();
  await aliceCtx.close();
});

test("hr role sees Members but not Roles; cannot invite admin", async ({ browser, request }) => {
  const t = ts();

  // Setup org + HR member via API (faster than driving the UI for setup).
  const reg = await request.post(`${API}/auth/register`, {
    data: {
      organization_name: `Hr Org ${t}`,
      organization_slug: `hr-${t}`,
      industry: "Software",
      country: "US",
      timezone: "UTC",
      currency: "USD",
      full_name: "Alice Boss",
      email: `hrboss${t}@acme.com`,
      password: "StrongPass123!",
    },
  });
  expect(reg.status(), await reg.text()).toBe(201);
  const boss = (await reg.json()) as { access_token: string; user: { id: string } };

  const hrInvite = await inviteByApi(request, boss.access_token, `dana${t}@acme.com`, "hr");
  const accept = await request.post(`${API}/auth/register/invite`, {
    data: { token: hrInvite.token, email: `dana${t}@acme.com`, full_name: "Dana Hr", password: "StrongPass123!" },
  });
  expect(accept.status(), await accept.text()).toBe(201);

  // HR can see Members, but not Roles or Audit.
  const danaCtx = await browser.newContext();
  const dana = await danaCtx.newPage();
  await dana.goto("/login");
  await dana.getByLabel("Email").fill(`dana${t}@acme.com`);
  await dana.getByLabel("Password", { exact: true }).fill("StrongPass123!");
  await dana.getByRole("button", { name: /sign in/i }).click();
  await dana.waitForURL("**/home", { timeout: 20_000 });
  await dana.goto("/settings?tab=members");
  await expect(dana.getByRole("heading", { name: "Settings" })).toBeVisible();
  await expect(dana.getByRole("button", { name: "Members", exact: true })).toBeVisible();
  await expect(dana.getByRole("button", { name: "Roles", exact: true })).not.toBeVisible();
  await expect(dana.getByRole("button", { name: "Audit log", exact: true })).toBeVisible();

  // Server-side policy: HR cannot invite an admin.
  const danaToken = await apiLogin(request, `dana${t}@acme.com`, "StrongPass123!");
  const blocked = await request.post(`${API}/users/invite`, {
    headers: { Authorization: `Bearer ${danaToken.access_token}` },
    data: { email: `adminx${t}@acme.com`, role: "admin" },
  });
  expect(blocked.status()).toBe(403);

  // But HR CAN invite an employee.
  const ok = await request.post(`${API}/users/invite`, {
    headers: { Authorization: `Bearer ${danaToken.access_token}` },
    data: { email: `emp${t}@acme.com`, role: "employee" },
  });
  expect(ok.status(), await ok.text()).toBe(201);

  // CEO can invite an admin.
  const okAdmin = await request.post(`${API}/users/invite`, {
    headers: { Authorization: `Bearer ${boss.access_token}` },
    data: { email: `admin2${t}@acme.com`, role: "admin" },
  });
  expect(okAdmin.status(), await okAdmin.text()).toBe(201);

  await danaCtx.close();
});
