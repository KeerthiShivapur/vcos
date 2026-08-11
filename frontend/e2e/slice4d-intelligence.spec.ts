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

test("slice 4d: company brain answers with governance-scoped, evidence-backed claims", async ({ browser, request }) => {
  test.setTimeout(480_000);
  const t = ts();
  const email = `brain${t}@acme.com`;
  const password = "StrongPass123!";

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

  await registerOrg(page, `Brain Co ${t}`, `brain-${t}`, email, "Ada", password);
  const token = (await apiLogin(request, email, password)).access_token;
  const auth = { Authorization: `Bearer ${token}` };

  // Seed evidence: project + task + a conversation the owner belongs to.
  const projectRes = await request.post(`${API}/projects`, {
    headers: auth,
    data: { name: "Cloud Migration", description: "Slice 4D evidence", status: "active" },
  });
  expect(projectRes.status(), await projectRes.text()).toBe(201);
  const proj = await projectRes.json();
  expect(proj.id).toBeTruthy();
  const task = await (
    await request.post(`${API}/tasks`, {
      headers: auth,
      data: { project_id: proj.id, title: "Cutover to the new platform", status: "in_progress" },
    })
  ).json();
  expect(task.id).toBeTruthy();

  const me = await (await request.get(`${API}/employees/me`, { headers: auth })).json();
  const conversation = await (
    await request.post(`${API}/conversations`, {
      headers: auth,
      data: { type: "channel", title: "aurora-launch", member_ids: [me.id] },
    })
  ).json();
  expect(conversation.id).toBeTruthy();
  const sent = await request.post(`${API}/conversations/${conversation.id}/messages`, {
    headers: auth,
    data: { content: "Aurora goes live with the Cloud Migration platform next week" },
  });
  expect(sent.status(), await sent.text()).toBe(201);

  // API-level: the canonical answer contract + authorization difference.
  const answer = await (
    await request.post(`${API}/brain/answer`, {
      headers: auth,
      data: { question: "What is the status of the Cloud Migration project and its tasks?" },
    })
  ).json();
  expect(Array.isArray(answer.claims)).toBe(true);
  expect(answer.claims.length).toBeGreaterThan(0);
  const cited = answer.claims.flatMap((c: { evidence: { id: string; type: string }[] }) => c.evidence);
  expect(cited.some((e: { id: string }) => e.id === proj.id)).toBe(true);

  const messagingAnswer = await (
    await request.post(`${API}/brain/answer`, {
      headers: auth,
      data: { question: "What was decided and discussed about the Aurora platform?" },
    })
  ).json();
  expect(
    messagingAnswer.claims.some((c: { evidence: { type: string }[] }) =>
      c.evidence.some((e: { type: string }) => e.type === "message")
    )
  ).toBe(true);

  const outsider = await inviteMember(request, auth, `emp${t}@acme.com`, "Emp Brain");
  const outsiderAnswer = await (
    await request.post(`${API}/brain/answer`, {
      headers: { Authorization: `Bearer ${outsider.access_token}` },
      data: { question: "What was decided and discussed about the Aurora platform?" },
    })
  ).json();
  expect(
    outsiderAnswer.claims.some((c: { evidence: { type: string }[] }) =>
      c.evidence.some((e: { type: string }) => e.type === "message")
    )
  ).toBe(false);

  // Relationship traversal is bounded and connected.
  const syncRes = await request.post(`${API}/brain/graph/relationships/sync`, {
    headers: auth,
    data: { mode: "entity" },
  });
  expect(syncRes.status(), await syncRes.text()).toBe(200);
  const sync = await syncRes.json();
  expect(sync.synced).toBeGreaterThan(0);
  const traverse = await (
    await request.get(
      `${API}/brain/graph/relationships/traverse?node_type=task&node_id=${task.id}&max_depth=3`,
      { headers: auth }
    )
  ).json();
  const nodeKeys = traverse.nodes.map((n: { type: string; id: string }) => `${n.type}:${n.id}`);
  expect(nodeKeys).toContain(`project:${proj.id}`);
  expect(traverse.limits.max_nodes).toBe(64);

  // UI: the Company Brain tab answers with evidence chips.
  await page.goto("/intelligence");
  await expect(page.getByRole("heading", { name: "Background Intelligence" })).toBeVisible({ timeout: 15_000 });
  await page.getByText("Company Brain", { exact: true }).click();

  const textarea = page.locator("textarea[placeholder*='Ask the company brain']");
  await expect(textarea).toBeVisible({ timeout: 15_000 });
  await textarea.fill("What is the status of the Cloud Migration project and its tasks?");
  await page.getByRole("button", { name: "Ask the brain" }).click();

  await expect(page.getByText("Answer", { exact: true })).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("Cloud Migration", { exact: false }).first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("confidence", { exact: false }).first()).toBeVisible({ timeout: 20_000 });
  await expect(page.locator("a[href*='/projects/']").first()).toBeVisible({ timeout: 20_000 });
});
