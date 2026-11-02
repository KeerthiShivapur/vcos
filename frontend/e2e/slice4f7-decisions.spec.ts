import {
  expect,
  test,
  type APIRequestContext,
  type Page,
} from "@playwright/test";

const API = "http://127.0.0.1:8999/api/v1";

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

async function apiRegister(
  ctx: APIRequestContext,
  name: string,
  slug: string,
  email: string,
  fullName: string,
  password: string,
) {
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

async function dispatchAll(
  request: APIRequestContext,
  auth: Record<string, string>,
  limit = 500,
) {
  for (let round = 0; round < 12; round++) {
    const r = await request.post(`${API}/intelligence/events/process`, {
      headers: auth,
      params: { limit: String(limit) },
    });
    expect(r.status(), await r.text()).toBe(200);
    const body = (await r.json()) as { processed: number };
    if (body.processed === 0) return;
  }
}

async function hire(
  request: APIRequestContext,
  auth: Record<string, string>,
  first: string,
  last: string,
  tag: string,
) {
  const r = await request.post(`${API}/employees`, {
    headers: auth,
    data: {
      first_name: first,
      last_name: last,
      email: `${tag}${ts()}@acme.com`,
      designation: "Engineer",
    },
  });
  expect(r.status(), await r.text()).toBe(201);
  return (await r.json()) as { id: string };
}

async function completeTask(
  request: APIRequestContext,
  auth: Record<string, string>,
  assigneeId: string,
  title: string,
) {
  const created = await request.post(`${API}/tasks`, {
    headers: auth,
    data: { title, assignee_id: assigneeId, status: "todo" },
  });
  expect(created.status(), await created.text()).toBe(201);
  const task = (await created.json()) as { id: string };
  const done = await request.patch(`${API}/tasks/${task.id}`, {
    headers: auth,
    data: { status: "completed" },
  });
  expect(done.status(), await done.text()).toBe(200);
}

test("slice 4f.7: people decisions are evidence-backed, explainable, human-governed and one governed UI surface", async ({
  browser,
  request,
}) => {
  test.setTimeout(900_000);
  const t = ts();
  const email = `decisions${t}@acme.com`;
  const password = "StrongPass123!";

  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  page.on("console", (msg) => {
    if (msg.type() === "error")
      console.log(
        `[${Date.now() % 100000}] console:error ${msg.text().slice(0, 200)}`,
      );
  });

  await apiRegister(
    request,
    `Decision Co ${t}`,
    `decs-${t}`,
    email,
    "Zoe",
    password,
  );
  const token = (await apiLogin(request, email, password)).access_token;
  const auth = { Authorization: `Bearer ${token}` };

  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL("**/home", { timeout: 30_000 });

  // ---------------------------------------------------------------- seeding
  const ada = await hire(request, auth, "Ada", "Lovelace", "ada");
  const bob = await hire(request, auth, "Bob", "Johnson", "bob");
  const carol = await hire(request, auth, "Carol", "Shaw", "carol");

  for (let i = 0; i < 7; i++)
    await completeTask(
      request,
      auth,
      ada.id,
      `Deploy the kubernetes cluster hard ${i}`,
    );
  for (let i = 0; i < 3; i++)
    await completeTask(
      request,
      auth,
      bob.id,
      `Kubernetes rollout and monitoring ${i}`,
    );
  await completeTask(request, auth, carol.id, "Kubernetes support rotation");
  await dispatchAll(request, auth);

  // ----------------------------------------------------------- API contract
  // 1. who should own? evidence-backed recommendation with provenance.
  const who = (await (
    await request.post(`${API}/brain/knowledge/query`, {
      headers: auth,
      data: { question: "who should own the kubernetes platform?" },
    })
  ).json()) as {
    intent: string;
    recommendation: {
      person_id: string | null;
      person_label: string | null;
      confidence: number;
      rationale: string;
    };
    provenance: { chain?: string[] };
  };
  expect(who.intent).toBe("people_decision");
  expect(who.recommendation.person_label).toBe("Ada Lovelace");
  expect(who.recommendation.rationale.toLowerCase()).toContain(
    "trusted evidence",
  );
  expect(who.provenance.chain?.length).toBeGreaterThanOrEqual(1);

  // 2. honest negatives: why not Bob?
  const whyNot = (await (
    await request.post(`${API}/brain/knowledge/query`, {
      headers: auth,
      data: { question: "why not Bob Johnson?" },
    })
  ).json()) as { kind: string; person: { name: string }; answer: string };
  expect(whyNot.kind).toBe("why_not");
  expect(whyNot.person.name).toBe("Bob Johnson");
  expect(whyNot.answer).toContain("is not recommended because");

  // 3. alternatives with trade-offs.
  const alts = (await (
    await request.post(`${API}/brain/knowledge/query`, {
      headers: auth,
      data: { question: "what are the alternatives for kubernetes?" },
    })
  ).json()) as { kind: string; answer: string };
  expect(alts.kind).toBe("alternatives");
  expect(alts.answer).toContain("Primary: Ada Lovelace");
  expect(alts.answer).toContain("Alternative 1:");

  // 4. the governed decisional object: reasoned immediately, humans decide.
  const created = (await (
    await request.post(`${API}/brain/decisions`, {
      headers: auth,
      data: {
        decision_type: "staffing",
        objective: "Who should staff the kubernetes delivery for six months?",
        requirements: ["kubernetes"],
        context_type: "org",
      },
    })
  ).json()) as {
    id: string;
    lifecycle: string;
    risk_tier: string;
    recommendation: { person_id: string | null; person_label: string | null };
    candidates: Array<{ role: string; person_label: string }>;
  };
  expect(created.lifecycle).toBe("recommended");
  expect(created.risk_tier).toBe("medium");
  expect(created.recommendation.person_id).toBeTruthy();
  expect(created.recommendation.person_label).toBe("Ada Lovelace");
  expect(created.candidates.length).toBeGreaterThanOrEqual(2);

  // 5. the append-only human-governed lifecycle with a recorded outcome.
  const lifecycle = ["review", "approve", "execute", "verify"];
  for (const action of lifecycle) {
    const r = await request.post(
      `${API}/brain/decisions/${created.id}/lifecycle`,
      {
        headers: auth,
        data: { action },
      },
    );
    expect(r.status(), await r.text()).toBe(200);
  }
  const outcome = (await (
    await request.post(`${API}/brain/decisions/${created.id}/outcome`, {
      headers: auth,
      data: { status: "successful", note: "delivery landed stable" },
    })
  ).json()) as {
    lifecycle: string;
    outcome: { status: string };
    audit: Array<{ action: string }>;
  };
  expect(outcome.lifecycle).toBe("outcome");
  expect(outcome.outcome.status).toBe("successful");
  expect(outcome.audit.map((a) => a.action)).toEqual([
    "detected",
    "evaluated",
    "recommended",
    "review",
    "approve",
    "execute",
    "verify",
    "outcome",
  ]);

  // 6. HIGH-tier people decisions are REFUSED by design.
  const refused = await request.post(`${API}/brain/decisions`, {
    headers: auth,
    data: {
      decision_type: "succession",
      objective: "Should we promote Ada to director?",
      requirements: ["kubernetes"],
      risk_tier: "high",
    },
  });
  expect(refused.status()).toBe(400);
  expect((await refused.json()).detail.toLowerCase()).toContain(
    "human governance",
  );

  // ------------------------------------------------------- people decision UI
  await page.goto("/people-decisions");
  await expect(
    page.getByRole("heading", { name: "People Decision Center" }),
  ).toBeVisible({ timeout: 20_000 });
  await expect(
    page.getByText("Decisions", { exact: true }).first(),
  ).toBeVisible();
  await expect(
    page.getByText("Awaiting human review", { exact: true }),
  ).toBeVisible();

  // Ask the brain and get the evidence-backed answer surfaced.
  await page
    .getByPlaceholder(/who should own the kubernetes platform/i)
    .fill("who should own the kubernetes platform?");
  await page.getByRole("button", { name: /ask/i }).click();
  await expect(
    page.getByText(/recommended: ada lovelace/i).first(),
  ).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/provenance/i).first()).toBeVisible();

  // Create a governed decision and see it reasoned over immediately.
  const uiObjective =
    "Who should own the kubernetes platform for the next quarter?";
  await page
    .getByPlaceholder(/objective — who should do what/i)
    .fill(uiObjective);
  await page.getByPlaceholder(/required capabilities/i).fill("kubernetes");
  await page.getByRole("button", { name: /reason now/i }).click();
  await expect(page.getByText(uiObjective, { exact: true })).toBeVisible({
    timeout: 30_000,
  });
  await expect(
    page.getByText("recommended", { exact: true }).first(),
  ).toBeVisible();
  await expect(
    page.getByText("Ada Lovelace", { exact: true }).first(),
  ).toBeVisible();

  // Walk the decision through its human-governed lifecycle from the UI.
  const row = page.getByText(uiObjective, { exact: true });
  await row.first().click();
  await expect(page.getByText(/candidates ·/i)).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.getByText(/governance trail/i)).toBeVisible();
  await page.getByRole("button", { name: /^review$/ }).click();
  await expect(page.getByText("reviewed", { exact: true }).first()).toBeVisible(
    { timeout: 20_000 },
  );
  await page.getByRole("button", { name: /^approve$/ }).click();
  await expect(page.getByText("approved", { exact: true }).first()).toBeVisible(
    { timeout: 20_000 },
  );
  await page.getByRole("button", { name: /^execute$/ }).click();
  await page.getByRole("button", { name: /^verify$/ }).click();
  await expect(page.getByText("verified", { exact: true }).first()).toBeVisible(
    { timeout: 20_000 },
  );
  await page.getByRole("button", { name: /record successful/i }).click();
  await expect(
    page.getByText("outcome: successful", { exact: true }),
  ).toBeVisible({ timeout: 20_000 });

  await page.close();
});
