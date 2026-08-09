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

test("approvals & risks: task-linked approval request → decide in the approvals center; risk register lifecycle", async ({ browser, request }) => {
  test.setTimeout(360_000);
  const t = ts();
  const email = `apr${t}@acme.com`;
  const password = "StrongPass123!";

  // 1. Founder registers; an approver employee is created via API.
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await registerOrg(page, `Approval Co ${t}`, `ap-${t}`, email, "Ada", password);
  const token = (await apiLogin(request, email, password)).access_token;
  const auth = { Authorization: `Bearer ${token}` };

  const approver = await (await request.post(`${API}/employees`, {
    headers: auth,
    data: { first_name: "Dana", last_name: "Decider", email: `dana${t}@acme.com` },
  })).json();
  expect(approver.id).toBeTruthy();

  const project = await (await request.post(`${API}/projects`, {
    headers: auth,
    data: { name: "Apollo", code: `ap${t.slice(0, 4)}`, status: "active" },
  })).json();
  const task = await (await request.post(`${API}/tasks`, {
    headers: auth,
    data: { project_id: project.id, title: "Ship release notes", priority: "high", status: "in_progress" },
  })).json();

  // 2. Request approval from the task detail page.
  await page.goto(`/tasks/${task.id}`);
  await expect(page.getByRole("heading", { name: "Ship release notes" })).toBeVisible({ timeout: 15_000 });
  await page.getByRole("button", { name: "Request approval" }).click();
  const dialog = page.locator('[role="dialog"]');
  await expect(dialog).toBeVisible({ timeout: 10_000 });
  await dialog.getByLabel("Approval type").selectOption("task");
  await dialog.getByLabel("Title").fill("Approve: Ship release notes");
  await dialog.getByLabel("Approver", { exact: true }).selectOption({ label: "Dana Decider" });
  await dialog.getByLabel("Priority").selectOption("high");
  await dialog.getByRole("button", { name: "Request approval", exact: true }).click();
  await expect(page.getByText(/Approval requested/)).toBeVisible({ timeout: 10_000 });

  // 3. The approval is pending, linked to the task, and the notification links to /approvals.
  const list = await (await request.get(`${API}/approvals`, { headers: auth })).json();
  const linked = list.find((a: { entity_type: string; entity_id: string; title: string }) =>
    a.entity_type === "task" && a.entity_id === task.id && a.title === "Approve: Ship release notes");
  expect(linked).toBeTruthy();
  expect(linked.status).toBe("pending");
  expect(linked.approver_id).toBe(approver.id);

  // 4. Approvals center: stats show a pending request; decide it with a note.
  await page.goto("/approvals");
  await expect(page.getByRole("heading", { name: "Approvals" })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("Approve: Ship release notes")).toBeVisible({ timeout: 10_000 });
  await page.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(page.getByText("Decide: Approve: Ship release notes")).toBeVisible({ timeout: 10_000 });
  await page.locator('[role="dialog"]').getByLabel("Decision note").fill("Ship it");
  await page.locator('[role="dialog"]').getByRole("button", { name: "Approve", exact: true }).click();
  await expect(page.getByText(/approved/i).first()).toBeVisible({ timeout: 10_000 });
  const decided = await (await request.get(`${API}/approvals/${linked.id}`, { headers: auth })).json();
  expect(decided.status).toBe("approved");
  expect(decided.decision_note).toBe("Ship it");

  // 5. A second request from the approvals center is rejected.
  await page.getByRole("button", { name: "Request approval" }).click();
  const dialog2 = page.locator('[role="dialog"]');
  await expect(dialog2).toBeVisible({ timeout: 10_000 });
  await dialog2.getByLabel("Approval type").selectOption({ label: "Budget" });
  await dialog2.getByLabel("Title").fill("Marketing budget");
  await dialog2.getByLabel("Approver", { exact: true }).selectOption({ label: "Dana Decider" });
  await dialog2.getByRole("button", { name: "Request approval", exact: true }).click();
  await expect(page.getByText("Marketing budget")).toBeVisible({ timeout: 10_000 });
  await page.getByRole("button", { name: "Reject", exact: true }).click();
  await expect(page.getByText("Decide: Marketing budget")).toBeVisible({ timeout: 10_000 });
  await page.locator('[role="dialog"]').getByLabel("Decision note").fill("No budget");
  await page.locator('[role="dialog"]').getByRole("button", { name: "Reject", exact: true }).click();
  await expect(page.getByText(/rejected/i).first()).toBeVisible({ timeout: 10_000 });

  // 6. The status tab filters work.
  await page.getByRole("button", { name: "Rejected", exact: true }).click();
  await expect(page.getByText("Marketing budget", { exact: true })).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText("Approve: Ship release notes", { exact: true })).not.toBeVisible();

  // 7. Risk register: log, escalate, close, delete.
  await page.getByRole("link", { name: "Risks", exact: true }).click();
  await expect(page).toHaveURL("http://localhost:3000/risks", { timeout: 10_000 });
  await expect(page.getByRole("heading", { name: "Risk Register" })).toBeVisible({ timeout: 15_000 });
  await page.getByRole("button", { name: "Log risk" }).click();
  const rDialog = page.locator('[role="dialog"]');
  await expect(rDialog).toBeVisible({ timeout: 10_000 });
  await rDialog.getByLabel("Risk project").selectOption({ label: "Apollo" });
  await rDialog.getByLabel("Title").fill("Vendor late delivery");
  await rDialog.getByLabel("Probability").fill("4");
  await rDialog.getByLabel("Impact").fill("3");
  await rDialog.getByLabel("Risk owner").selectOption({ label: "Dana Decider" });
  await rDialog.getByLabel("Mitigation plan").fill("Weekly sync");
  await rDialog.getByRole("button", { name: "Log risk", exact: true }).click();
  await expect(page.getByText(/Risk logged/)).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText("Vendor late delivery")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText(/P4 × I3 = 12/)).toBeVisible();
  await expect(page.getByText("High", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Weekly sync")).toBeVisible();

  // 8. Escalate impact to 5 → score 20, critical.
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await page.getByLabel("Impact").fill("5");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText(/P4 × I5 = 20/)).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText("Critical", { exact: true }).first()).toBeVisible();

  // 9. Close the risk; the open-risk stat drops; delete removes it.
  await page.getByRole("button", { name: "Close", exact: true }).click();
  await expect(page.getByText("Vendor late delivery closed")).toBeVisible({ timeout: 10_000 });
  const riskRow = page.getByText("Vendor late delivery").first();
  await page.getByRole("button", { name: "Delete Vendor late delivery" }).click();
  await expect(page.locator('[role="dialog"]').getByRole("heading", { name: "Delete risk" })).toBeVisible({ timeout: 10_000 });
  await page.locator('[role="dialog"]').getByRole("button", { name: "Delete risk", exact: true }).click();
  await expect(page.getByText(/Risk deleted/)).toBeVisible({ timeout: 10_000 });
  await expect(riskRow).not.toBeVisible({ timeout: 10_000 });
  await expect(page.getByText("No risks match")).toBeVisible();
});
