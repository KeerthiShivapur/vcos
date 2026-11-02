import {
  expect,
  test,
  type APIRequestContext,
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

test("command center shows real decision, authorization, risk and state data", async ({
  browser,
  request,
}) => {
  test.setTimeout(360_000);
  const suffix = ts();
  const password = "Password123!";
  const email = `cc-a-${suffix}@example.com`;
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await registerOrg(
    page,
    `CC Org A ${suffix}`,
    `cc-org-a-${suffix}`,
    email,
    "CC Founder",
    password,
  );
  const token = (await apiLogin(request, email, password)).access_token;
  const auth = { Authorization: `Bearer ${token}` };

  const decisionTitle = `CC decision ${suffix}`;
  const dRes = await request.post(`${API}/decisions`, {
    headers: auth,
    data: {
      title: decisionTitle,
      description: "Command Center e2e",
      status: "proposed",
    },
  });
  expect(dRes.status(), await dRes.text()).toBe(201);
  const decision = (await dRes.json()) as { id: string };

  const approvalTitle = `Authorize ${suffix}`;
  const aRes = await request.post(`${API}/approvals`, {
    headers: auth,
    data: {
      approval_type: "decision",
      title: approvalTitle,
      entity_type: "decision",
      entity_id: decision.id,
    },
  });
  expect(aRes.status(), await aRes.text()).toBe(201);

  const riskTitle = `CC risk ${suffix}`;
  const rRes = await request.post(`${API}/risks`, {
    headers: auth,
    data: { title: riskTitle, probability: 4, impact: 4, status: "identified" },
  });
  expect(rRes.status(), await rRes.text()).toBe(201);

  await page.goto("/command-center");
  await expect(
    page.getByRole("heading", { name: "Command Center" }),
  ).toBeVisible({ timeout: 20_000 });
  await expect(
    page.getByRole("heading", { name: "Decision Inbox" }),
  ).toBeVisible();

  // Decision Inbox: the real decision, its state, and the authorization state sourced separately.
  await expect(page.getByRole("link", { name: decisionTitle })).toBeVisible({
    timeout: 20_000,
  });
  await expect(
    page.getByText("Proposed", { exact: true }).first(),
  ).toBeVisible();
  await expect(page.getByText(/Authorization:\s*pending/)).toBeVisible();
  // A recorded decision must not be shown as approved: no approval has been decided.
  await expect(page.getByText("Approved", { exact: true })).toHaveCount(0);
  // Pending authorizations list carries the real linked approval.
  await expect(page.getByText(approvalTitle).first()).toBeVisible();

  // Company State: verified administrative facts from the canonical summary.
  await expect(page.getByText("Members", { exact: true })).toBeVisible();
  await expect(page.getByText("Active users", { exact: true })).toBeVisible();

  // Risk & Integrity: the real risk appears as recorded.
  await expect(page.getByText(riskTitle).first()).toBeVisible({
    timeout: 20_000,
  });

  // Timeline section is present even when a fresh company has few events.
  await expect(
    page.getByRole("heading", { name: "Company Timeline" }),
  ).toBeVisible();

  // Tenant isolation: a second organization must never see org A records.
  const ctx2 = await browser.newContext();
  const page2 = await ctx2.newPage();
  const email2 = `cc-b-${suffix}@example.com`;
  await registerOrg(
    page2,
    `CC Org B ${suffix}`,
    `cc-org-b-${suffix}`,
    email2,
    "CC Founder B",
    password,
  );
  await page2.goto("/command-center");
  await expect(
    page2.getByRole("heading", { name: "Command Center" }),
  ).toBeVisible({ timeout: 20_000 });
  await expect(page2.getByText(riskTitle)).toHaveCount(0);
  await expect(page2.getByRole("link", { name: decisionTitle })).toHaveCount(0);
});
