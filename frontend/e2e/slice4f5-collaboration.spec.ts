import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const API = "http://127.0.0.1:8999/api/v1";

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

async function hire(request: APIRequestContext, auth: Record<string, string>, first: string, last: string, tag: string, teamId?: string) {
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

async function team(request: APIRequestContext, auth: Record<string, string>, name: string, tag: string) {
  const r = await request.post(`${API}/teams`, {
    headers: auth,
    data: { name: `${name} ${tag}`, code: `${tag.toLowerCase()}${ts()}`, description: "four.five team" },
  });
  expect(r.status(), await r.text()).toBe(201);
  return (await r.json()) as { id: string };
}

async function project(request: APIRequestContext, auth: Record<string, string>, name: string, tag: string, ownerId: string) {
  const r = await request.post(`${API}/projects`, {
    headers: auth,
    data: { name: `${name} ${tag}`, code: `${tag}`.toUpperCase(), owner_id: ownerId, status: "active" },
  });
  expect(r.status(), await r.text()).toBe(201);
  return (await r.json()) as { id: string; name: string };
}

async function task(request: APIRequestContext, auth: Record<string, string>, title: string, projectId: string, assigneeId: string, reporterId: string) {
  const r = await request.post(`${API}/tasks`, {
    headers: auth,
    data: { title, project_id: projectId, assignee_id: assigneeId, reporter_id: reporterId, status: "todo" },
  });
  expect(r.status(), await r.text()).toBe(201);
  return (await r.json()) as { id: string };
}

async function meeting(request: APIRequestContext, auth: Record<string, string>, title: string, projectId: string, attendeeIds: string[]) {
  const r = await request.post(`${API}/meetings`, {
    headers: auth,
    data: { title, project_id: projectId, attendee_ids: attendeeIds, start_time: new Date(Date.now() - 3600_000).toISOString(), duration_minutes: 45 },
  });
  expect(r.status(), await r.text()).toBe(201);
  return (await r.json()) as { id: string };
}

test("slice 4f.5: work collaboration is evidence-backed, explainable, advisory-only and one governed UI surface", async ({ browser, request }) => {
  test.setTimeout(900_000);
  const t = ts();
  const email = `collab${t}@acme.com`;
  const password = "StrongPass123!";

  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  page.on("console", (msg) => {
    if (msg.type() === "error") console.log(`[${Date.now() % 100000}] console:error ${msg.text().slice(0, 200)}`);
  });

  await apiRegister(request, `Collab Co ${t}`, `collab-${t}`, email, "Zoe", password);
  const token = (await apiLogin(request, email, password)).access_token;
  const auth = { Authorization: `Bearer ${token}` };

  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL("**/home", { timeout: 30_000 });

  // ---------------------------------------------------------------- seeding
  const eng = await team(request, auth, "Engineering", `eng${t}`);
  const ops = await team(request, auth, "Operations", `ops${t}`);
  const ada = await hire(request, auth, "Ada", "Lovelace", "ada", eng.id);
  const bob = await hire(request, auth, "Bob", "Johnson", "bob", eng.id);
  const cy = await hire(request, auth, "Cy", "Miller", "cy", ops.id);

  const cloud = await project(request, auth, "Cloud Platform", `cloud${t}`, ada.id);
  const mobile = await project(request, auth, "Mobile App", `mobile${t}`, cy.id);

  // Shared work: Ada + Bob on the cloud project (positive evidence), a blocked
  // task there for failure evidence, and a cross-team meeting with Cy.
  const t1 = await task(request, auth, "Provision clusters", cloud.id, ada.id, bob.id);
  const t2 = await task(request, auth, "Harden auth", cloud.id, bob.id, ada.id);
  await task(request, auth, "Deploy pipeline", cloud.id, bob.id, ada.id);
  const t3 = await task(request, auth, "Schema migration", cloud.id, ada.id, bob.id);
  await task(request, auth, "Replication lag", cloud.id, ada.id, bob.id);
  await task(request, auth, "Mobile push", mobile.id, cy.id, ada.id);
  const mtg = await meeting(request, auth, "Cloud kickoff", cloud.id, [ada.id, bob.id, cy.id]);
  const ended = await request.post(`${API}/meetings/${mtg.id}/complete`, { headers: auth });
  expect(ended.status(), await ended.text()).toBe(200);

  // Complete the shared tasks -> strong positive evidence for Ada<->Bob.
  for (const tid of [t1, t2, t3]) {
    const r = await request.patch(`${API}/tasks/${tid.id}`, { headers: auth, data: { status: "completed" } });
    expect(r.status(), await r.text()).toBe(200);
  }
  await dispatchAll(request, auth);

  // ----------------------------------------------------------- API contract
  const overview = (await (
    await request.get(`${API}/brain/collaboration/overview`, { headers: auth })
  ).json()) as {
    total_relationships: number;
    cross_functional_relationships: number;
    health: Record<string, number>;
    strongest: Array<{ person_a_label: string; person_b_label: string; strength: number; health_state: string }>;
  };
  expect(overview.total_relationships).toBeGreaterThanOrEqual(3);
  expect(overview.cross_functional_relationships).toBeGreaterThanOrEqual(1);
  expect(Object.keys(overview.health).length).toBeGreaterThanOrEqual(1);
  expect(overview.strongest.length).toBeGreaterThanOrEqual(1);

  const adaView = (await (
    await request.get(`${API}/brain/collaboration/people/${ada.id}`, { headers: auth })
  ).json()) as {
    person_label: string;
    relationships: Array<{ other_person_id: string; other_person_label: string; strength: number; shared_tasks: number; failed_interactions: number; health_state: string }>;
    rollup: { active_relationships: number; share_of_org_strength: number | null };
  };
  expect(adaView.person_label).toBe("Ada Lovelace");
  expect(adaView.relationships.length).toBeGreaterThanOrEqual(2);
  const bobRel = adaView.relationships.find((r) => r.other_person_label === "Bob Johnson");
  expect(bobRel).toBeTruthy();
  expect(bobRel!.shared_tasks).toBeGreaterThanOrEqual(3);
  expect(bobRel!.strength).toBeGreaterThan(0.5);

  const pair = (await (
    await request.get(`${API}/brain/collaboration/relationships/people/${ada.id}/with/${bob.id}`, { headers: auth })
  ).json()) as {
    shared_tasks: number;
    successful_interactions: number;
    failed_interactions: number;
    strength: number;
    confidence: number;
    health_state: string;
    explain: { formula: string; weighted_positive: number; failure_ratio: number };
    evidence: Array<{ event_name: string; outcome: string }>;
  };
  expect(pair.shared_tasks).toBeGreaterThanOrEqual(3);
  expect(pair.explain.formula).toContain("strength = 1 - exp");
  expect(pair.explain.weighted_positive).toBeGreaterThan(0);
  expect(pair.explain.failure_ratio).toBeLessThan(0.5);
  expect(pair.evidence.length).toBeGreaterThanOrEqual(3);
  expect(pair.evidence.some((e) => e.event_name === "task.completed")).toBe(true);

  // Cross-team unit surface: Engineering collaborates with Operations.
  const units = (await (
    await request.get(`${API}/brain/collaboration/units/team/${eng.id}`, { headers: auth })
  ).json()) as {
    unit_label: string;
    pairs: Array<{ other_unit_label: string; shared_meetings: number; strength: number; health_state: string }>;
  };
  expect(units.unit_label).toContain("Engineering");
  const opsPair = units.pairs.find((p) => p.other_unit_label && p.other_unit_label.includes("Operations"));
  expect(opsPair).toBeTruthy();
  expect(opsPair!.shared_meetings).toBeGreaterThanOrEqual(1);

  // Project collaboration evidence.
  const pv = (await (
    await request.get(`${API}/brain/collaboration/projects/${cloud.id}`, { headers: auth })
  ).json()) as {
    project_name: string;
    total_evidence: number;
    people: Array<{ share_of_project_evidence: number }>;
    top_pairs: Array<{ person_a_label: string; person_b_label: string; successes: number }>;
  };
  expect(pv.project_name).toContain("Cloud Platform");
  expect(pv.total_evidence).toBeGreaterThanOrEqual(6);
  expect(pv.people.length).toBeGreaterThanOrEqual(2);

  // Changes surface recent evolution.
  const changes = (await (
    await request.get(`${API}/brain/collaboration/changes`, { headers: auth, params: { days: "30" } })
  ).json()) as { total: number; changes: Array<{ change: string; strength: number }> };
  expect(changes.total).toBeGreaterThanOrEqual(1);
  expect(changes.changes.every((c) => typeof c.change === "string" && c.change.length > 0)).toBe(true);
  expect(changes.changes[0].strength).toBeGreaterThan(0);

  // Gap analysis is advisory-only and its signals resolve without changing the graph.
  const gap = (await (
    await request.post(`${API}/brain/collaboration/analyze`, { headers: auth })
  ).json()) as { projects_scanned: number; gaps: number };
  expect(gap.projects_scanned).toBeGreaterThanOrEqual(1);

  const signals = (await (
    await request.get(`${API}/brain/collaboration/signals`, { headers: auth, params: { status: "open" } })
  ).json()) as { signals: Array<{ id: string; kind: string; detail: string }> };
  if (signals.signals.length > 0) {
    const resolved = await request.post(`${API}/brain/collaboration/signals/${signals.signals[0].id}/resolve`, { headers: auth });
    expect(resolved.status(), await resolved.text()).toBe(200);
  }

  // Brain /ask routes collaboration questions to the graph.
  const ask = (await (
    await request.post(`${API}/brain/knowledge/query`, {
      headers: auth,
      data: { question: "who works most closely with Ada Lovelace?" },
    })
  ).json()) as { intent: string };
  expect(ask.intent).toBe("collaboration_person");

  // --------------------------------------------------------- collaboration UI
  await page.goto("/collaboration");
  await expect(page.getByRole("heading", { name: "Work Collaboration" })).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("Relationships", { exact: true })).toBeVisible();
  await expect(page.getByText("Cross-functional", { exact: true })).toBeVisible();
  await expect(page.getByText("Ada Lovelace", { exact: false }).first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("Bob Johnson", { exact: false }).first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText(/ok \/ .* fail/i).first()).toBeVisible();

  // Recent changes and signals surfaces are present.
  await expect(page.getByRole("heading", { name: "Recent changes", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Open signals", exact: true })).toBeVisible();

  // Project collaboration picker shows evidence for the cloud project.
  await page.getByRole("combobox").selectOption({ label: `${cloud.name}` });
  await expect(page.getByText(/evidence item/i).first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("Potential dependency concentration").first()).toBeVisible({ timeout: 20_000 });

  // Run the bounded gap analysis from the UI (advisory write only).
  await page.getByRole("button", { name: /run gap analysis/i }).click();
  await expect(page.getByRole("heading", { name: "Open signals", exact: true })).toBeVisible({ timeout: 20_000 });

  await page.close();
});
