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

async function apiRegister(ctx: APIRequestContext, name: string, slug: string, email: string, fullName: string, password: string) {
  const r = await ctx.post(`${API}/auth/register`, {
    data: {
      organization_name: name,
      organization_slug: slug,
      industry: "Software",
      country: "US",
      full_name: fullName,
      email,
      password,
    },
  });
  expect(r.status(), await r.text()).toBe(201);
}

async function dispatchAll(request: APIRequestContext, auth: Record<string, string>, limit = 500) {
  for (let round = 0; round < 10; round++) {
    const r = await request.post(`${API}/intelligence/events/process`, {
      headers: auth,
      params: { limit: String(limit) },
    });
    expect(r.status(), await r.text()).toBe(200);
    const body = (await r.json()) as { processed: number };
    if (body.processed === 0) return;
  }
}

interface TrustBody {
  trust: boolean;
  person_name: string;
  skill_name: string;
  lifecycle: string;
  confidence: number;
  successful_count: number;
  failed_count: number;
  distinct_lineages: number;
  corroborated_kinds: number;
  freshness: string;
  evidence_total: number;
  contradictions: Array<{ outcome: string; expired: boolean }>;
  recent_evidence: Array<{ source_type: string; source_id: string; outcome: string }>;
}

test("slice 4f.3: task outcomes leave a governed, explainable trust trail that the profile UI surfaces", async ({ browser, request }) => {
  test.setTimeout(900_000);
  const t = ts();
  const email = `trust${t}@acme.com`;
  const password = "StrongPass123!";

  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  page.on("console", (msg) => {
    if (msg.type() === "error") console.log(`[${Date.now() % 100000}] console:error ${msg.text().slice(0, 200)}`);
  });

  await apiRegister(request, `Trust Co ${t}`, `trust-${t}`, email, "Vera", password);
  const token = (await apiLogin(request, email, password)).access_token;
  const auth = { Authorization: `Bearer ${token}` };

  // The app shell rides on a session cookie; log the browser in through the
  // real /login UI so the page context carries the session.
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL("**/home", { timeout: 30_000 });

  // ------------------------------------------------------------------ seeding
  const employee = await (
    await request.post(`${API}/employees`, {
      headers: auth,
      data: {
        first_name: "Py",
        last_name: "Dev",
        email: `pydev${t}@acme.com`,
        designation: "Platform Engineer",
      },
    })
  ).json();

  // Five independent python task completions = one lineage each.
  for (let i = 0; i < 5; i++) {
    const task = await request.post(`${API}/tasks`, {
      headers: auth,
      data: {
        title: `Build the python telemetry pipeline ${i}`,
        assignee_id: employee.id,
      },
    });
    const done = await request.post(`${API}/tasks/${(await task.json()).id}/transition`, {
      headers: auth,
      data: { status: "completed" },
    });
    expect(done.status(), await done.text()).toBe(200);
  }

  // One negative signal on a DIFFERENT action: an approval rejection (the
  // rejected claim is attributed to the requester = our python expert).
  const rejected = await request.post(`${API}/approvals`, {
    headers: auth,
    data: { title: `python toolchain upgrade ${t}`, requester_id: employee.id },
  });
  expect(rejected.status(), await rejected.text()).toBe(201);
  const approvalId = (await rejected.json()).id;
  const rejectCall = await request.post(`${API}/approvals/${approvalId}/decide`, {
    headers: auth,
    data: { decision: "rejected", note: "insufficient review" },
  });
  expect(rejectCall.status(), await rejectCall.text()).toBe(200);

  await dispatchAll(request, auth);

  // ----------------------------------------------------------- API contract
  const search = await (
    await request.get(`${API}/brain/expertise/search`, {
      headers: auth,
      params: { q: "python" },
    })
  ).json();
  const me = (search.experts as Array<{ person_id: string; name: string; successful_count: number; failed_count: number; confidence: number; lifecycle: string }>).find(
    (e) => e.person_id === employee.id
  );
  expect(me, "the python expert must be discoverable with trust facets").toBeTruthy();
  expect(me!.successful_count).toBeGreaterThanOrEqual(5);
  expect(me!.failed_count).toBeGreaterThanOrEqual(1);

  const skillId = (me as unknown as { skill_id: string }).skill_id;
  const trust = (await (
    await request.get(`${API}/brain/people/${employee.id}/expertise/${skillId}/trust`, {
      headers: auth,
    })
  ).json()) as TrustBody;
  expect(trust.trust).toBe(true);
  expect(trust.person_name).toBe("Py Dev");
  expect(trust.successful_count).toBeGreaterThanOrEqual(5);
  expect(trust.failed_count).toBeGreaterThanOrEqual(1);
  expect(trust.distinct_lineages).toBeGreaterThanOrEqual(4);
  expect(trust.corroborated_kinds).toBeGreaterThanOrEqual(1);
  expect(trust.freshness).toMatch(/^(active|recent)$/);
  expect(trust.contradictions.length).toBeGreaterThanOrEqual(1);
  expect(trust.recent_evidence.some((r) => r.source_type === "task")).toBe(true);

  // ------------------------------------------------------------- profile UI
  await page.goto(`/people/${employee.id}`);
  await expect(page.getByRole("heading", { name: "Py Dev" }).first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("Skills & expertise")).toBeVisible();

  await page.getByRole("button", { name: "Why we trust it" }).first().click();
  await expect(page.getByText(/strong.*confidence/i).first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText(/successful \/ .* failed outcome/i).first()).toBeVisible();
  await expect(page.locator("button", { hasText: "task:" }).first()).toBeVisible({ timeout: 20_000 });

  // The contradictions stay visible: a rejected action is never hidden.
  await expect(page.getByText(/failed or expired item/i).first()).toBeVisible();

  // Drill into one evidence item.
  await page.locator("button", { hasText: "task:" }).first().click();
  await expect(page.getByText("Evidence detail")).toBeVisible();

  // ----------------------------------------------------- why/trust reasoning
  const answer = await (
    await request.post(`${API}/brain/knowledge/query`, {
      headers: auth,
      data: { question: `why does Py Dev know Python?` },
    })
  ).json();
  expect(answer.intent).toBe("expertise_trust");
  expect(answer.kind).toBe("trust_profile");
  expect(answer.answers.length).toBeGreaterThan(0);
  expect(answer.answer).toContain("lineage");

  await page.close();
});