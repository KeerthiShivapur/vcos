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

interface TaskDepBlock {
  projectId: string;
  blockerIds: string[];
  blockedTaskIds: string[];
}

async function dependencyBlockedTask(
  request: APIRequestContext,
  auth: Record<string, string>,
  projectId: string,
): Promise<TaskDepBlock> {
  const blocker = await (
    await request.post(`${API}/tasks`, {
      headers: auth,
      data: { title: `Blocker ${ts()}`, project_id: projectId, status: "todo" },
    })
  ).json();
  const dependent = await (
    await request.post(`${API}/tasks`, {
      headers: auth,
      data: {
        title: `Blocked task ${ts()}`,
        project_id: projectId,
        status: "todo",
      },
    })
  ).json();
  const dep = await request.post(`${API}/tasks/${dependent.id}/dependencies`, {
    headers: auth,
    data: { depends_on_task_id: blocker.id, kind: "finish_to_start" },
  });
  expect(dep.status(), await dep.text()).toBe(201);
  const transitioned = await request.post(
    `${API}/tasks/${dependent.id}/transition`,
    {
      headers: auth,
      data: { status: "blocked" },
    },
  );
  expect(transitioned.status(), await transitioned.text()).toBe(200);
  return {
    projectId,
    blockerIds: [blocker.id],
    blockedTaskIds: [dependent.id],
  };
}

async function dispatchAll(
  request: APIRequestContext,
  auth: Record<string, string>,
  limit = 500,
) {
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

async function runWorker(
  request: APIRequestContext,
  auth: Record<string, string>,
  name: string,
) {
  const r = await request.post(`${API}/intelligence/workers/${name}/run`, {
    headers: auth,
  });
  expect(r.status(), await r.text()).toBe(200);
  return (await r.json()) as { processed: number };
}

async function driveFullStackLive(
  request: APIRequestContext,
  auth: Record<string, string>,
) {
  await dispatchAll(request, auth);
  await runWorker(request, auth, "pattern");
  await dispatchAll(request, auth);
  await runWorker(request, auth, "memory_formation");
  await dispatchAll(request, auth);
  await runWorker(request, auth, "insight");
  await dispatchAll(request, auth);
  await runWorker(request, auth, "indexing");
  await dispatchAll(request, auth);
}

interface InsightRow {
  id: string;
  insight_type: string;
  auth_project_id: string | null;
  title: string;
}

async function insightsList(
  request: APIRequestContext,
  auth: Record<string, string>,
): Promise<InsightRow[]> {
  const r = await request.get(`${API}/brain/insights`, {
    headers: auth,
    params: { limit: "200" },
  });
  expect(r.status(), await r.text()).toBe(200);
  return (await r.json()).insights;
}

interface BrainAnswerBody {
  summary: string;
  confidence: number;
  claims: Array<{
    claim: string;
    confidence: number;
    kind: string;
    evidence: Array<{ type: string; id: string; url: string; title: string }>;
  }>;
  related_entities: Array<{ type: string; id: string; title: string }>;
  patterns: Array<{ id: string; title: string; url: string }>;
  insights: Array<{ id: string; title: string; url: string }>;
  memories: Array<{ id: string; title: string; url: string }>;
  knowledge: Array<{ id: string; title: string; url: string }>;
  sources_consulted: string[];
  scope: { org_wide: boolean };
  answered_at: string;
  metrics?: {
    brain_query_duration_ms: number;
    answer_claim_count: number;
    evidence_count: number;
  };
}

const QUESTION =
  "why is the Helios Delivery project behind on the approval policy review?";

test("slice 4d.6: the unified company brain composes every intelligence source with evidence, respects governance, and surfaces in the UI", async ({
  browser,
  request,
}) => {
  test.setTimeout(900_000);
  const t = ts();
  const email = `brain${t}@acme.com`;
  const password = "StrongPass123!";

  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  page.on("console", (msg) => {
    if (msg.type() === "error")
      console.log(
        `[${Date.now() % 100000}] console:error ${msg.text().slice(0, 200)}`,
      );
  });
  page.on("requestfailed", (req) =>
    console.log(
      `[${Date.now() % 100000}] REQ-FAIL ${req.method()} ${req.url().slice(0, 90)} :: ${req.failure()?.errorText}`,
    ),
  );

  await registerOrg(
    page,
    `Brain Co ${t}`,
    `brain-${t}`,
    email,
    "Iris",
    password,
  );
  const token = (await apiLogin(request, email, password)).access_token;
  const auth = { Authorization: `Bearer ${token}` };

  // ---------------------------------------------------------------- seeding
  // Canonical anchor: a project stalled behind an open blocker, so task.blocked
  // events feed memory formation, pattern and insight pipelines identically.
  const project = await (
    await request.post(`${API}/projects`, {
      headers: auth,
      data: {
        name: "Helios Delivery",
        description: "Slice 4D.6 anchor",
        status: "active",
      },
    })
  ).json();
  await request.post(`${API}/governance/scopes`, {
    headers: auth,
    data: {
      name: "Helios Scope",
      scope_type: "project",
      entity_id: project.id,
    },
  });
  for (let i = 0; i < 3; i++)
    await dependencyBlockedTask(request, auth, project.id);
  await request.post(`${API}/decisions`, {
    headers: auth,
    data: {
      title: `approve finance approval ${t}`,
      project_id: project.id,
      description: "pending",
    },
  });

  // A governed memory already known to the company.
  const memory = await request.post(`${API}/brain/memory`, {
    headers: auth,
    data: {
      memory_type: "institutional",
      title: "Previous approval delay",
      content: "An approval delay blocked similar work in the past.",
      importance: "medium",
      entity_type: "project",
      entity_id: project.id,
    },
  });
  expect(memory.status(), await memory.text()).toBe(200);

  // Published, indexed policy knowledge on this project.
  const document = await (
    await request.post(`${API}/documents`, {
      headers: auth,
      data: {
        title: "Approval policy for enterprise accounts",
        content:
          "All project approvals require a formal decision record. The finance approval workflow must be reviewed before launch approval is granted. This approval policy is company policy.",
        project_id: project.id,
      },
    })
  ).json();
  await request.post(`${API}/documents/${document.id}/publish`, {
    headers: auth,
  });

  // Run the canonical background pipeline until the project-anchored insight exists.
  let insight: InsightRow | undefined;
  for (let attempt = 0; attempt < 10 && !insight; attempt++) {
    await driveFullStackLive(request, auth);
    const list = await insightsList(request, auth);
    insight = list.find(
      (i) =>
        i.insight_type === "execution_bottleneck" &&
        i.auth_project_id === project.id,
    );
    if (!insight) await new Promise((resolve) => setTimeout(resolve, 3_000));
  }
  expect(
    insight,
    "execution_bottleneck insight must form from the blocked project",
  ).toBeTruthy();

  // Sync the org graph relationships (the same call the tab's sync button makes)
  // so the evidence drawer can surface graph neighbors for the project.
  const graphSync = await request.post(
    `${API}/brain/graph/relationships/sync`,
    {
      headers: auth,
      data: {},
    },
  );
  expect(graphSync.status(), await graphSync.text()).toBe(200);
  const graphSyncBody = (await graphSync.json()) as { synced: number };
  expect(graphSyncBody.synced).toBeGreaterThan(0);

  // ---------------------------------------------------------------- answer
  // 1) The unified answer composes all four producers for one anchor.
  const answerRes = await request.post(`${API}/brain/answer`, {
    headers: auth,
    data: { question: QUESTION },
  });
  expect(answerRes.status(), await answerRes.text()).toBe(200);
  const answer = (await answerRes.json()) as BrainAnswerBody;
  expect(answer.summary.length).toBeGreaterThan(0);
  expect(answer.confidence).toBeGreaterThanOrEqual(0);
  expect(answer.confidence).toBeLessThanOrEqual(1);
  expect(answer.answered_at).toBeTruthy();
  expect(answer.scope.org_wide).toBe(true);
  expect(answer.claims.length).toBeGreaterThanOrEqual(1);
  for (const claim of answer.claims) {
    expect(claim.confidence).toBeGreaterThanOrEqual(0);
    expect(claim.confidence).toBeLessThanOrEqual(1);
  }
  expect(answer.patterns.length).toBeGreaterThanOrEqual(1);
  expect(answer.insights.length).toBeGreaterThanOrEqual(1);
  expect(answer.memories.length).toBeGreaterThanOrEqual(1);
  expect(answer.knowledge.length).toBeGreaterThanOrEqual(1);
  expect(
    answer.related_entities.some(
      (e) => e.type === "project" && e.id === project.id,
    ),
  ).toBe(true);
  expect(answer.sources_consulted).toEqual(
    expect.arrayContaining([
      "context",
      "patterns",
      "insights",
      "memory",
      "knowledge",
    ]),
  );
  expect(answer.metrics?.brain_query_duration_ms).toBeGreaterThanOrEqual(0);
  // The blocking stall is the operative truth the brain must state.
  expect(answer.summary).toContain("Helios Delivery");

  // 2) Evidence drawer: the project opens into cross-source evidence + graph neighbors.
  const drawerRes = await request.get(
    `${API}/brain/evidence/project/${project.id}`,
    {
      headers: auth,
      params: { link_limit: "5" },
    },
  );
  expect(drawerRes.status(), await drawerRes.text()).toBe(200);
  const drawer = (await drawerRes.json()) as {
    source: { type: string; id: string; title: string; url: string };
    evidence: Array<{
      type: string;
      id: string;
      url: string;
      relationship: string;
    }>;
    related_entities: Array<{
      type: string;
      id: string;
      title: string;
      relation: string;
    }>;
  };
  expect(drawer.source.type).toBe("project");
  expect(drawer.source.id).toBe(project.id);
  expect(drawer.evidence.length).toBeGreaterThanOrEqual(1);
  expect(drawer.related_entities.length).toBeGreaterThanOrEqual(1);

  // 3) Related is bounded and flagged when truncated.
  const relatedRes = await request.get(
    `${API}/brain/related/project/${project.id}`,
    {
      headers: auth,
      params: { limit: "5" },
    },
  );
  expect(relatedRes.status(), await relatedRes.text()).toBe(200);
  const related = (await relatedRes.json()) as {
    related: unknown[];
    truncated: boolean;
  };
  expect(related.related.length).toBeGreaterThanOrEqual(1);
  expect(related.related.length).toBeLessThanOrEqual(5);
  expect(typeof related.truncated).toBe("boolean");

  // 4) Overview composes bounded attention and observes the same intelligence.
  const overviewRes = await request.get(`${API}/brain/overview`, {
    headers: auth,
  });
  expect(overviewRes.status(), await overviewRes.text()).toBe(200);
  const overview = (await overviewRes.json()) as {
    attention: Array<{
      source: string;
      id: string;
      title: string;
      url: string;
      confidence: number;
    }>;
    recent_intelligence: {
      insights: { count: number };
      patterns: { count: number };
      memories: { count: number };
    };
    scope: { org_wide: boolean };
  };
  expect(overview.attention.length).toBeGreaterThanOrEqual(1);
  expect(overview.attention.some((a) => a.url.includes(insight!.id))).toBe(
    true,
  );
  expect(overview.recent_intelligence.insights.count).toBeGreaterThanOrEqual(1);
  expect(overview.scope.org_wide).toBe(true);
  const overviewAgain = (await (
    await request.get(`${API}/brain/overview`, { headers: auth })
  ).json()) as {
    attention: Array<{ id: string }>;
  };
  expect(overviewAgain.attention.map((a) => a.id)).toEqual(
    overview.attention.map((a) => a.id),
  );

  // ---------------------------------------------------------------- determinism
  // 5) Reads never mutate: the same question composes the same summary.
  const again = (await (
    await request.post(`${API}/brain/answer`, {
      headers: auth,
      data: { question: QUESTION },
    })
  ).json()) as BrainAnswerBody;
  expect(again.summary).toBe(answer.summary);
  expect(again.confidence).toBe(answer.confidence);

  // ---------------------------------------------------------------- governance
  // 6) A scoped brain:read-only reader receives the scoped answer, and
  //    evidence outside their scope is a 404 — never filtered after composition.
  const invite = await request.post(`${API}/users/invite`, {
    headers: auth,
    data: {
      email: `scoped${t}@acme.com`,
      full_name: "Scoped Mgr",
      role: "manager",
    },
  });
  expect(invite.status(), await invite.text()).toBe(201);
  const joined = await request.post(`${API}/auth/register/invite`, {
    data: {
      token: (await invite.json()).token,
      full_name: "Scoped Mgr",
      password,
    },
  });
  expect(joined.status(), await joined.text()).toBe(201);
  const joinedUser = await joined.json();
  const scopedAuth = { Authorization: `Bearer ${joinedUser.access_token}` };
  const roles = await (
    await request.get(`${API}/roles`, { headers: auth })
  ).json();
  const managerRole = roles.find((r: { code: string }) => r.code === "manager");
  const assignment = await request.post(`${API}/governance/assignments`, {
    headers: auth,
    data: {
      user_id: joinedUser.user.id,
      role_id: managerRole.id,
      scope_id: (
        await (
          await request.get(`${API}/governance/scopes`, { headers: auth })
        ).json()
      ).find((s: { name: string }) => s.name === "Helios Scope").id,
    },
  });
  expect(assignment.status(), await assignment.text()).toBe(201);
  const assigned = await (
    await request.get(`${API}/governance/assignments`, {
      headers: auth,
      params: { user_id: joinedUser.user.id },
    })
  ).json();
  const orgWideAssign = assigned.find(
    (a: { scope_id: string | null }) => a.scope_id === null,
  );
  expect(orgWideAssign).toBeTruthy();
  await request.delete(`${API}/governance/assignments/${orgWideAssign.id}`, {
    headers: auth,
  });
  const delegated = await request.post(`${API}/governance/delegations`, {
    headers: auth,
    data: {
      granted_to_user: joinedUser.user.id,
      permission_code: "brain:read",
      reason: "4d.6 e2e",
    },
  });
  expect(delegated.status(), await delegated.text()).toBe(201);

  const scopedAnswer = (await (
    await request.post(`${API}/brain/answer`, {
      headers: scopedAuth,
      data: { question: QUESTION },
    })
  ).json()) as BrainAnswerBody;
  expect(scopedAnswer.scope.org_wide).toBe(false);
  expect(scopedAnswer.confidence).toBeGreaterThanOrEqual(0);
  // The scoped answer may drop the org-wide insight, but never fabricate one.
  for (const claim of scopedAnswer.claims) {
    for (const evidence of claim.evidence) {
      const probe = await request.get(
        evidence.url.startsWith("http")
          ? evidence.url
          : `${API}${evidence.url}`,
        { headers: scopedAuth },
      );
      expect(
        probe.status(),
        `${evidence.url} must resolve under scope`,
      ).not.toBe(404);
    }
  }

  // A second project outside the reader's scope: their drawer is a 404.
  const hidden = await (
    await request.post(`${API}/projects`, {
      headers: auth,
      data: {
        name: "Hidden Vault",
        description: "out of scope",
        status: "active",
      },
    })
  ).json();
  await request.post(`${API}/brain/memory`, {
    headers: auth,
    data: {
      memory_type: "institutional",
      title: "Hidden payout plan",
      content: "Confidential payout plan for the hidden vault.",
      importance: "high",
      entity_type: "project",
      entity_id: hidden.id,
    },
  });
  const hiddenProbe = await request.get(
    `${API}/brain/evidence/project/${hidden.id}`,
    { headers: scopedAuth },
  );
  expect(hiddenProbe.status()).toBe(404);

  // ---------------------------------------------------------------- tenant isolation
  // 7) A rival org's brain never answers with this org's company intelligence.
  const rivalEmail = `rival${t}@acme.com`;
  const reg = await request.post(`${API}/auth/register`, {
    data: {
      organization_name: `Rival Co ${t}`,
      organization_slug: `rival-${t}`,
      industry: "Software",
      country: "United States",
      full_name: "Riva",
      email: rivalEmail,
      password,
    },
  });
  expect(reg.status(), await reg.text()).toBe(201);
  const rivalAuth = {
    Authorization: `Bearer ${(await reg.json()).access_token}`,
  };
  const rivalAnswer = (await (
    await request.post(`${API}/brain/answer`, {
      headers: rivalAuth,
      data: { question: "what is happening in your company right now?" },
    })
  ).json()) as BrainAnswerBody;
  expect(rivalAnswer.summary).not.toContain("Helios");

  // ---------------------------------------------------------------- UI
  // 8) The Company Brain tab composes the same answer with overview, evidence
  //    drawer and a governed explanation.
  await page.goto("/intelligence");
  await expect(
    page.getByRole("heading", { name: "Background Intelligence" }),
  ).toBeVisible({ timeout: 15_000 });
  await page.getByRole("button", { name: /Company Brain/ }).click();
  await expect(page.getByText("What needs attention")).toBeVisible({
    timeout: 20_000,
  });
  await page.getByPlaceholder(/Ask the company brain/).fill(QUESTION);
  await page.getByRole("button", { name: "Ask the brain" }).click();
  await expect(
    page.getByText(/Helios Delivery/, { exact: false }).first(),
  ).toBeVisible({ timeout: 30_000 });
  await expect(
    page.getByText(/\d+% confidence/, { exact: false }).first(),
  ).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText(/Composed from/)).toBeVisible({
    timeout: 10_000,
  });
  for (const label of ["Patterns", "Insights", "Memory", "Knowledge"]) {
    await expect(page.getByText(label, { exact: true }).first()).toBeVisible({
      timeout: 10_000,
    });
  }
  await expect(page.getByText(/Why this answer reached you/)).toBeVisible({
    timeout: 10_000,
  });
  await expect(page.getByText(/Recent intelligence/)).toBeVisible({
    timeout: 10_000,
  });
  await page
    .getByText(/Related entities/)
    .locator("..")
    .locator("button")
    .first()
    .click();
  await expect(
    page.getByText("Open source", { exact: false }).first(),
  ).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText(/Graph neighbors/)).toBeVisible({
    timeout: 10_000,
  });
});
