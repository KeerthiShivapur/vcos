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

test("governed AI worker: real research, approval-gated action, tenant isolation", async ({
  browser,
  request,
}) => {
  test.setTimeout(300_000);
  const suffix = ts();
  const password = "Password123!";
  const email = `gw-a-${suffix}@example.com`;
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await registerOrg(
    page,
    `GW Org A ${suffix}`,
    `gw-org-a-${suffix}`,
    email,
    "GW Founder",
    password,
  );
  const token = (await apiLogin(request, email, password)).access_token;
  const auth = { Authorization: `Bearer ${token}` };

  const projectName = `GW Project ${suffix}`;
  const pRes = await request.post(`${API}/projects`, {
    headers: auth,
    data: { name: projectName },
  });
  expect(pRes.status(), await pRes.text()).toBe(201);

  await page.goto("/command-center");
  await expect(
    page.getByRole("heading", { name: "Command Center" }),
  ).toBeVisible({ timeout: 20_000 });
  await expect(
    page.getByRole("heading", { name: "Governed AI Work" }),
  ).toBeVisible({ timeout: 20_000 });

  const researchTitle = `Research ${suffix}`;
  const instruction =
    "Summarize the current project state and what deserves attention.";

  await page.getByLabel("Task title").fill(researchTitle);
  await page.getByLabel("Scope").selectOption({ label: projectName });
  await page.getByLabel("Instruction").fill(instruction);
  await page.getByRole("button", { name: "Create & run" }).click();

  // The run opens the detail for the analysis that just executed.
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible({ timeout: 30_000 });
  await expect(
    dialog.getByText("Observed facts (canonical services)"),
  ).toBeVisible({ timeout: 30_000 });
  await expect(dialog.getByText(/status/).first()).toBeVisible();
  // Honest degradation: with no external model configured, the result carries
  // only canonical facts and an explicit uncertainty — never fake reasoning.
  await expect(dialog.getByText(/No AI model was available/)).toBeVisible();
  // A research task must not fabricate an authorization.
  await expect(dialog.getByText(/Authorization:/)).toHaveCount(0);
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);

  // Recommendation task: proposal + pending approval, no automatic action.
  const recTitle = `Recommendation ${suffix}`;
  const recInstruction =
    "Propose the single most important next step for this project.";
  await page.getByLabel("Task title").fill(recTitle);
  await page.getByLabel("Task kind").selectOption("recommendation");
  await page.getByLabel("Scope").selectOption({ label: projectName });
  await page.getByLabel("Instruction").fill(recInstruction);
  await page.getByRole("button", { name: "Create & run" }).click();

  await expect(dialog).toBeVisible({ timeout: 30_000 });
  await expect(
    dialog.getByText("Awaiting approval", { exact: false }).first(),
  ).toBeVisible({ timeout: 30_000 });
  await expect(dialog.getByText("Governance")).toBeVisible();
  await expect(dialog.getByText(/Proposed decision:/)).toBeVisible();
  await expect(dialog.getByText(/Authorization:/)).toBeVisible();
  await page.keyboard.press("Escape");

  // Card list: the recommendation shows awaiting approval and links to /approvals.
  const recCard = page.locator("li", { hasText: recTitle }).first();
  await expect(recCard.getByText("Awaiting approval")).toBeVisible({
    timeout: 20_000,
  });
  await expect(
    page.getByRole("button", { name: "Execute approved action" }),
  ).toHaveCount(0);

  // The pending approval exists and is real; decide it as the founder.
  const listRes = await request.get(`${API}/approvals`, { headers: auth });
  expect(listRes.status(), await listRes.text()).toBe(200);
  const approvals = (await listRes.json()) as {
    id: string;
    title: string;
    status: string;
  }[];
  const pending = approvals.find(
    (a) => a.title.startsWith("Authorize action:") && a.status === "pending",
  );
  expect(
    pending,
    `pending governed-worker approval not found in ${JSON.stringify(approvals)}`,
  ).toBeTruthy();

  // Execute must be blocked while the authorization is still pending.
  const execBefore = await request.post(
    `${API}/governed-worker/actions/${"x"}/execute`,
    { headers: auth },
  );
  expect(execBefore.status()).toBe(404);

  const decide = await request.post(`${API}/approvals/${pending!.id}/decide`, {
    headers: auth,
    data: { decision: "approved", note: "e2e authorization" },
  });
  expect(decide.status(), await decide.text()).toBe(200);

  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Governed AI Work" }),
  ).toBeVisible({ timeout: 20_000 });
  const recCard2 = page.locator("li", { hasText: recTitle }).first();
  await expect(recCard2.getByText("Ready to execute")).toBeVisible({
    timeout: 20_000,
  });

  await recCard2
    .getByRole("button", { name: "Execute approved action" })
    .click();
  await expect(dialog).toBeVisible({ timeout: 30_000 });
  await expect(dialog.getByText(/Executed action created task/)).toBeVisible({
    timeout: 30_000,
  });
  await page.keyboard.press("Escape");

  // The executed action created a real task in the canonical task system.
  const tasksRes = await request.get(`${API}/tasks`, { headers: auth });
  expect(tasksRes.status(), await tasksRes.text()).toBe(200);
  const tasksBody = await tasksRes.json();
  const taskList = Array.isArray(tasksBody)
    ? tasksBody
    : (tasksBody.items ?? []);
  expect(
    taskList.some((t: { title: string }) => t.title.includes("Follow-up:")),
    `follow-up task not found in ${JSON.stringify(taskList).slice(0, 500)}`,
  ).toBe(true);

  // Tenant isolation: org B sees none of org A's governed work.
  const ctx2 = await browser.newContext();
  const page2 = await ctx2.newPage();
  const email2 = `gw-b-${suffix}@example.com`;
  await registerOrg(
    page2,
    `GW Org B ${suffix}`,
    `gw-org-b-${suffix}`,
    email2,
    "GW Founder B",
    password,
  );
  await page2.goto("/command-center");
  await expect(
    page2.getByRole("heading", { name: "Governed AI Work" }),
  ).toBeVisible({ timeout: 20_000 });
  await expect(page2.getByText(researchTitle)).toHaveCount(0);
  await expect(page2.getByText(recTitle)).toHaveCount(0);
  await expect(page2.getByText("No governed AI tasks yet")).toBeVisible();
});
