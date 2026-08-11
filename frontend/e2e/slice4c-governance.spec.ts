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

async function inviteMember(request: APIRequestContext, auth: Record<string, string>, email: string, fullName: string) {
  const r = await request.post(`${API}/users/invite`, {
    headers: auth,
    data: { email, full_name: fullName, role: "employee" },
  });
  expect(r.status(), await r.text()).toBe(201);
  const { token } = (await r.json()) as { token: string };
  const reg = await request.post(`${API}/auth/register/invite`, {
    data: { token, email, full_name: fullName, password: "StrongPass123!" },
  });
  expect(reg.status(), await reg.text()).toBe(201);
  return (await reg.json()) as { access_token: string; user: { id: string } };
}

test("governance: scope tree, scoped role assignment, delegation, approval policy and effective permissions", async ({ browser, request }) => {
  test.setTimeout(480_000);
  const t = ts();
  const email = `gov${t}@acme.com`;
  const password = "StrongPass123!";

  // 1. Founder registers; a member is invited via API.
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  page.on("console", (msg) => {
    if (msg.type() === "error") console.log(`[${Date.now() % 100000}] console:error ${msg.text().slice(0, 200)}`);
  });
  page.on("requestfailed", (req) =>
    console.log(`[${Date.now() % 100000}] REQ-FAIL ${req.method()} ${req.url().slice(0, 90)} :: ${req.failure()?.errorText}`)
  );
  page.on("response", (res) => {
    if (res.url().includes("8999")) console.log(`[${Date.now() % 100000}] RESP ${res.status()} ${res.url().replace(API, "").slice(0, 60)}`);
  });
  await registerOrg(page, `Govern Co ${t}`, `gov-${t}`, email, "Ada", password);
  const token = (await apiLogin(request, email, password)).access_token;
  const auth = { Authorization: `Bearer ${token}` };
  const member = await inviteMember(request, auth, `emp${t}@acme.com`, "Emp Gov");

  // 2. Governance hub loads with the stat cards.
  await page.goto("/governance");
  await expect(page.getByRole("heading", { name: "Governance", exact: true })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("Approval policies", { exact: true })).toBeVisible();

  // 3. Create a department scope and a team scope beneath it.
  await page.getByRole("button", { name: "New scope" }).click();
  let dialog = page.locator('[role="dialog"]');
  await expect(dialog).toBeVisible({ timeout: 10_000 });
  await dialog.getByLabel("Name").fill("Engineering");
  await dialog.getByLabel("Type").selectOption("department");
  await dialog.getByRole("button", { name: "Create scope", exact: true }).click();
  await expect(page.getByText(/Scope created/)).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText("Engineering", { exact: true }).first()).toBeVisible({ timeout: 10_000 });

  await page.getByRole("button", { name: "New scope" }).click();
  dialog = page.locator('[role="dialog"]');
  await expect(dialog).toBeVisible({ timeout: 10_000 });
  await dialog.getByLabel("Name").fill("Backend");
  await dialog.getByLabel("Type").selectOption("team");
  await dialog.getByLabel("Parent scope").selectOption({ label: "Engineering" }, { timeout: 60_000 });
  await dialog.getByRole("button", { name: "Create scope", exact: true }).click();
  await expect(page.getByText(/Scope created/)).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText("Engineering / Backend")).toBeVisible({ timeout: 10_000 });

  // 4. Assign the manager role to the member at the Backend scope.
  await page.getByRole("button", { name: "Scoped Roles" }).click();
  await page.getByRole("button", { name: "Assign role" }).click();
  dialog = page.locator('[role="dialog"]');
  await expect(dialog).toBeVisible({ timeout: 10_000 });
  await dialog.getByLabel("Member").selectOption({ label: "Emp Gov" });
  await dialog.getByLabel("Role").selectOption({ label: "manager — Manager" });
  await dialog.getByLabel("Scope").selectOption({ label: "Backend" });
  await dialog.getByRole("button", { name: "Assign role", exact: true }).click();
  await expect(page.getByText(/Role assigned/)).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText("Emp Gov", { exact: true }).first()).toBeVisible({ timeout: 10_000 });

  // 5. The backend confirms the scoped authority (downward flow, no sibling leakage).
  const scopes = (await (await request.get(`${API}/governance/scopes`, { headers: auth })).json()) as {
    id: string;
    name: string;
    scope_type: string;
  }[];
  const backend = scopes.find((s) => s.name === "Backend")!;
  expect(backend).toBeTruthy();
  const eff = (await (
    await request.get(`${API}/governance/effective-permissions`, {
      headers: auth,
      params: { user_id: member.user.id, scope_id: backend.id },
    })
  ).json()) as { permissions: string[] };
  expect(eff.permissions).toContain("projects:manage");
  const orgEff = (await (
    await request.get(`${API}/governance/effective-permissions`, {
      headers: auth,
      params: { user_id: member.user.id },
    })
  ).json()) as { permissions: string[] };
  expect(orgEff.permissions).not.toContain("projects:manage");

  // 6. Delegate projects:manage to the member and verify it works end-to-end.
  await page.getByRole("button", { name: "Delegations" }).click();
  await page.getByRole("button", { name: "Delegate authority" }).click();
  dialog = page.locator('[role="dialog"]');
  await expect(dialog).toBeVisible({ timeout: 10_000 });
  await dialog.getByLabel("Delegate").selectOption({ label: "Emp Gov" });
  await dialog.getByLabel("Permission").selectOption("projects:manage");
  await dialog.getByLabel("Reason").fill("Temporary ownership");
  await dialog.getByRole("button", { name: "Delegate authority", exact: true }).click();
  await expect(page.getByText(/Authority delegated/)).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText("Temporary ownership")).toBeVisible({ timeout: 10_000 });

  const memberToken = (await apiLogin(request, `emp${t}@acme.com`, password)).access_token;
  const memberAuth = { Authorization: `Bearer ${memberToken}` };
  const created = await request.post(`${API}/projects`, {
    headers: memberAuth,
    data: { name: "Delegated project", status: "active" },
  });
  expect(created.status(), await created.text()).toBe(201);

  // 7. Revocation takes effect immediately (bounded, targeted revocation).
  const grants = (await (await request.get(`${API}/governance/delegations`, { headers: auth })).json()) as { id: string; permission_code: string; granted_to_user: string }[];
  const grant = grants.find((g) => g.permission_code === "projects:manage" && g.granted_to_user === member.user.id)!;
  expect(grant).toBeTruthy();
  const revoked = await request.post(`${API}/governance/delegations/${grant.id}/revoke`, { headers: auth });
  expect(revoked.status()).toBe(200);
  const tooLate = await request.post(`${API}/projects`, {
    headers: memberAuth,
    data: { name: "Too late", status: "active" },
  });
  expect(tooLate.status(), await tooLate.text()).toBe(403);

  // 8. Approval policy created in the UI gates decisions.
  await page.getByRole("button", { name: "Approval Policies" }).click();
  await page.getByRole("button", { name: "New policy" }).click();
  dialog = page.locator('[role="dialog"]');
  await expect(dialog).toBeVisible({ timeout: 10_000 });
  await dialog.getByLabel("Name").fill("Release gate");
  await dialog.getByLabel("Required permission").fill("approvals:manage");
  await dialog.getByLabel("Approval type").fill("release");
  await dialog.getByRole("button", { name: "Create policy", exact: true }).click();
  await expect(page.getByText(/Approval policy created/)).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText("Release gate", { exact: true })).toBeVisible({ timeout: 10_000 });

  const policies = (await (await request.get(`${API}/governance/policies`, { headers: auth })).json()) as { id: string; name: string; required_permission: string }[];
  const policy = policies.find((p) => p.name === "Release gate")!;
  const approval = (await (
    await request.post(`${API}/approvals`, {
      headers: auth,
      data: { approval_type: "release", title: "Ship 4C", policy_id: policy.id },
    })
  ).json()) as { id: string };
  const denied = await request.post(`${API}/approvals/${approval.id}/decide`, {
    headers: memberAuth,
    data: { decision: "approved" },
  });
  expect(denied.status(), await denied.text()).toBe(403);

  // 9. Effective permissions evaluation in the UI.
  await page.getByRole("button", { name: "Effective Permissions" }).click();
  await page.getByLabel("Member").selectOption({ label: "Emp Gov" });
  await page.getByLabel("Scope context").selectOption({ label: "Backend" });
  await page.getByRole("button", { name: "Evaluate", exact: true }).click();
  await expect(page.getByText("projects:manage").first()).toBeVisible({ timeout: 10_000 });

  // 10. An employee without governance:read never sees the surface.
  const empCtx = await browser.newContext();
  const empPage = await empCtx.newPage();
  await empPage.goto("/login");
  await empPage.getByLabel("Email").fill(`emp${t}@acme.com`);
  await empPage.getByLabel("Password", { exact: true }).fill(password);
  await empPage.getByRole("button", { name: /sign in/i }).click();
  await empPage.waitForURL("**/home", { timeout: 20_000 });
  await expect(empPage.getByRole("link", { name: "Governance" })).not.toBeVisible({ timeout: 10_000 });
  await empCtx.close();
});
