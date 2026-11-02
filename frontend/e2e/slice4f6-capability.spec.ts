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
  teamId?: string,
) {
  const r = await request.post(`${API}/employees`, {
    headers: auth,
    data: {
      first_name: first,
      last_name: last,
      email: `${tag}${ts()}@acme.com`,
      designation: "Engineer",
      team_id: teamId,
    },
  });
  expect(r.status(), await r.text()).toBe(201);
  return (await r.json()) as { id: string };
}

async function team(
  request: APIRequestContext,
  auth: Record<string, string>,
  name: string,
  tag: string,
) {
  const r = await request.post(`${API}/teams`, {
    headers: auth,
    data: {
      name: `${name} ${tag}`,
      code: `${tag.toLowerCase()}${ts()}`,
      description: "four.six team",
    },
  });
  expect(r.status(), await r.text()).toBe(201);
  return (await r.json()) as { id: string };
}

async function project(
  request: APIRequestContext,
  auth: Record<string, string>,
  name: string,
  tag: string,
  ownerId: string,
) {
  const r = await request.post(`${API}/projects`, {
    headers: auth,
    data: {
      name: `${name} ${tag}`,
      code: `${tag}`.toUpperCase(),
      owner_id: ownerId,
      status: "active",
    },
  });
  expect(r.status(), await r.text()).toBe(201);
  return (await r.json()) as { id: string; name: string };
}

async function task(
  request: APIRequestContext,
  auth: Record<string, string>,
  title: string,
  projectId: string | null,
  assigneeId: string,
  reporterId: string,
) {
  const data: Record<string, unknown> = {
    title,
    assignee_id: assigneeId,
    reporter_id: reporterId,
    status: "todo",
  };
  if (projectId) data.project_id = projectId;
  const r = await request.post(`${API}/tasks`, { headers: auth, data });
  expect(r.status(), await r.text()).toBe(201);
  return (await r.json()) as { id: string };
}

async function complete(
  request: APIRequestContext,
  auth: Record<string, string>,
  taskId: string,
) {
  const r = await request.patch(`${API}/tasks/${taskId}`, {
    headers: auth,
    data: { status: "completed" },
  });
  expect(r.status(), await r.text()).toBe(200);
}

test("slice 4f.6: capability center is evidence-backed, capacity-explicit, explainable, advisory-only and one governed UI surface", async ({
  browser,
  request,
}) => {
  test.setTimeout(900_000);
  const t = ts();
  const email = `caps${t}@acme.com`;
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
    `Cap Co ${t}`,
    `caps-${t}`,
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
  const eng = await team(request, auth, "Engineering", `eng${t}`);
  const ada = await hire(request, auth, "Ada", "Lovelace", "ada", eng.id);
  const bob = await hire(request, auth, "Bob", "Johnson", "bob", eng.id);

  const cloud = await project(
    request,
    auth,
    "Cloud Platform",
    `cloud${t}`,
    ada.id,
  );

  // Ada carries the Kubernetes evidence on an ACTIVE project (demand +
  // committed capacity); Bob adds a second expert without project demand.
  const seeded: { id: string }[] = [];
  for (let i = 0; i < 5; i++) {
    seeded.push(
      await task(
        request,
        auth,
        `Deploy kubernetes clusters round ${i}`,
        cloud.id,
        ada.id,
        bob.id,
      ),
    );
  }
  const side = await task(
    request,
    auth,
    "Kubernetes monitoring health checks",
    null,
    bob.id,
    ada.id,
  );
  for (const tk of [...seeded, side]) await complete(request, auth, tk.id);
  await dispatchAll(request, auth);

  // ----------------------------------------------------------- API contract
  const overview = (await (
    await request.get(`${API}/brain/capabilities/overview`, { headers: auth })
  ).json()) as {
    total: number;
    by_state: Record<string, number>;
    capabilities: Array<{
      skill_id: string;
      name: string;
      lifecycle: string;
      expert_count: number;
      evidence_count: number;
      capacity_state: string;
      capacity_potential: number;
      capacity_committed: number;
      capacity_reserved: number;
      capacity_available: number;
      demand_count: number;
      concentration_share: number;
      explain: string;
    }>;
  };
  expect(overview.total).toBeGreaterThanOrEqual(1);
  expect(Object.keys(overview.by_state).length).toBeGreaterThanOrEqual(1);
  const kube = overview.capabilities.find((c) => c.name === "Kubernetes");
  expect(
    kube,
    JSON.stringify(overview.capabilities.map((c) => c.name)),
  ).toBeTruthy();
  expect(kube!.lifecycle).toBe("established");
  expect(kube!.expert_count).toBeGreaterThanOrEqual(2);
  expect(kube!.evidence_count).toBeGreaterThanOrEqual(6);
  // capacity = potential - committed - reserved, and no fake hours.
  expect(kube!.capacity_available).toBe(
    kube!.capacity_potential -
      kube!.capacity_committed -
      kube!.capacity_reserved,
  );
  expect(kube!.demand_count).toBeGreaterThanOrEqual(1);
  expect(kube!.explain).toBeTruthy();
  // three experts … no: two experts with a heavy top share -> concentration advisory.
  expect(kube!.concentration_share).toBeGreaterThanOrEqual(0.6);

  // Detail surface explains every number and never hides factors.
  const detail = (await (
    await request.get(`${API}/brain/capabilities/${kube!.skill_id}`, {
      headers: auth,
    })
  ).json()) as {
    name: string;
    explain: string;
    factors: Record<string, number | string | boolean>;
    experts: Array<{
      person_id: string;
      name: string;
      score: number;
      evidence_count: number;
    }>;
    capacity: {
      available: number;
      committed: number;
      potential: number;
      reserved: number;
    };
    demand: { count: number };
    projects: Array<{ project_name: string }>;
    adjacent: Array<{ name: string }>;
  };
  expect(detail.name).toBe("Kubernetes");
  expect(detail.explain).toBeTruthy();
  expect(detail.factors).toBeTruthy();
  expect(detail.factors.experts).toBeGreaterThanOrEqual(2);
  expect(detail.experts.map((e) => e.name).sort()).toEqual(
    ["Ada Lovelace", "Bob Johnson"].sort(),
  );
  expect(detail.capacity.available).toBe(
    detail.capacity.potential -
      detail.capacity.committed -
      detail.capacity.reserved,
  );
  expect(detail.demand.count).toBeGreaterThanOrEqual(1);
  expect(detail.projects.length).toBeGreaterThanOrEqual(1);

  // Advisory signals from evidence: concentration risk is raised …
  const signals = (await (
    await request.get(`${API}/brain/capabilities/signals`, { headers: auth })
  ).json()) as {
    total: number;
    signals: Array<{
      signal_id: string;
      kind: string;
      skill_name: string;
      severity: string;
      status: string;
    }>;
  };
  const concentration = signals.signals.find(
    (s) => s.kind === "concentration" && s.skill_name === "Kubernetes",
  );
  expect(concentration, JSON.stringify(signals.signals)).toBeTruthy();
  expect(concentration!.status).toBe("open");

  // … and acknowledging is explicit and persistent (never auto-resolved).
  const acked = (await (
    await request.patch(
      `${API}/brain/capabilities/signals/${concentration!.signal_id}/acknowledge`,
      { headers: auth },
    )
  ).json()) as { status: string };
  expect(acked.status).toBe("acknowledged");

  // CEO readiness: deterministic, evidence-backed verdict.
  const initiative = (await (
    await request.post(`${API}/brain/capabilities/initiative`, {
      headers: auth,
      data: {
        question: "we are being asked to build a kubernetes delivery platform",
      },
    })
  ).json()) as {
    answer: string;
    total: number;
    answers: Array<{
      skill_name: string;
      readiness: string;
      lifecycle: string;
    }>;
  };
  expect(initiative.total).toBeGreaterThanOrEqual(1);
  const kubeAnswer = initiative.answers.find(
    (a) => a.skill_name === "Kubernetes",
  );
  expect(kubeAnswer).toBeTruthy();
  expect(kubeAnswer!.readiness).toBe("ready");
  expect(initiative.answer).toContain("required capabilities");

  // The Company Brain routes capability questions to this surface.
  const ask = (await (
    await request.post(`${API}/brain/knowledge/query`, {
      headers: auth,
      data: { question: "what are we really good at?" },
    })
  ).json()) as { intent: string };
  expect(["capability_strength", "expertise"]).toContain(ask.intent);

  // ---------------------------------------------------------- capability UI
  await page.goto("/capabilities");
  await expect(
    page.getByRole("heading", { name: "Capability Center" }),
  ).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("Capabilities", { exact: true })).toBeVisible();
  await expect(
    page.getByText("Strong / strategic", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("In demand", { exact: true })).toBeVisible();
  await expect(
    page.getByText("Open signals", { exact: true }).first(),
  ).toBeVisible();

  // Lifecycle distribution lists the evidence-backed state.
  await expect(
    page.getByText("established", { exact: true }).first(),
  ).toBeVisible({ timeout: 20_000 });

  // The CEO readiness question runs from the page and answers deterministically.
  await page
    .getByPlaceholder(/we are being asked to build/i)
    .fill("we are being asked to build a kubernetes delivery platform");
  await page.getByRole("button", { name: /analyze/i }).click();
  await expect(page.getByText(/required capabilities/).first()).toBeVisible({
    timeout: 20_000,
  });

  // Open signals surface the concentration finding and acknowledge it from the UI.
  await expect(
    page.getByRole("heading", { name: /open signals/i }),
  ).toBeVisible();
  await expect(
    page.getByText("concentration", { exact: true }).first(),
  ).toBeVisible({ timeout: 20_000 });
  const ackButton = page.getByRole("button", { name: /acknowledge/i });
  await expect(ackButton.first()).toBeVisible();
  await ackButton.first().click();
  await expect(page.getByText("concentration", { exact: true })).toHaveCount(
    0,
    { timeout: 20_000 },
  );

  // Clicking a capability opens its evidence-backed detail: experts, the
  // explicit capacity model and the deterministic factors.
  await page
    .getByRole("button", { name: /Kubernetes/ })
    .first()
    .click();
  await expect(page.getByText("Capacity model", { exact: true })).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.getByText("Ada Lovelace", { exact: true })).toBeVisible();
  await expect(page.getByText("Bob Johnson", { exact: true })).toBeVisible();
  await expect(page.getByText(/why we believe this/i)).toBeVisible();

  await page.close();
});
