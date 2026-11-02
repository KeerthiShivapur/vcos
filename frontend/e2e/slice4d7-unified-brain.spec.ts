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

async function ensureInsight(
  request: APIRequestContext,
  auth: Record<string, string>,
  projectId: string,
): Promise<InsightRow> {
  let insight: InsightRow | undefined;
  for (let attempt = 0; attempt < 10 && !insight; attempt++) {
    await driveFullStackLive(request, auth);
    const list = await insightsList(request, auth);
    insight = list.find(
      (i) =>
        i.insight_type === "execution_bottleneck" &&
        i.auth_project_id === projectId,
    );
    if (!insight) await new Promise((resolve) => setTimeout(resolve, 3_000));
  }
  expect(
    insight,
    "execution_bottleneck insight must form from the blocked project",
  ).toBeTruthy();
  return insight!;
}

interface BrainAnswerBody {
  summary: string;
  confidence: number;
  answered_at: string;
  scope: { org_wide: boolean };
  claims: Array<{
    claim: string;
    confidence: number;
    evidence: Array<{ type: string; id: string; url: string; title: string }>;
  }>;
  conversation?: { id: string; turn: number };
  persona?: {
    org_wide: boolean;
    visible_project_count: number;
    visible_scope_count: number;
  };
  timeline?: Array<{
    kind: string;
    id: string;
    title: string;
    url: string;
    occurred_at?: string | null;
  }>;
  recommended_next_questions?: string[];
  reasoning_chain?: Array<{
    step: number;
    label: string;
    claim: string;
    confidence: number;
  }>;
  related_patterns?: Array<{ id: string; title: string; url: string }>;
  related_memories?: Array<{ id: string; title: string; url: string }>;
  related_insights?: Array<{ id: string; title: string; url: string }>;
  what_changed?: {
    since: string;
    days: number;
    org_wide: boolean;
    categories: Array<{
      category: string;
      count: number;
      items?: Array<{ id: string; title: string; url: string }>;
    }>;
  };
  metrics?: {
    timeline_entries?: number;
    reasoning_chain_steps?: number;
    recommended_next_questions?: number;
  };
}

const QUESTION =
  "why is the Helios Delivery project behind on the approval policy review?";

test("slice 4d.7: the unified brain surface keeps follow-ups anchored, composes timeline/reasoning/next-questions, and hides the hidden from scoped callers", async ({
  browser,
  request,
}) => {
  test.setTimeout(900_000);
  const t = ts();
  const email = `brain7${t}@acme.com`;
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
    `brain7-${t}`,
    email,
    "Iris",
    password,
  );
  const token = (await apiLogin(request, email, password)).access_token;
  const auth = { Authorization: `Bearer ${token}` };

  // ---------------------------------------------------------------- seeding
  const project = await (
    await request.post(`${API}/projects`, {
      headers: auth,
      data: {
        name: "Helios Delivery",
        description: "Slice 4D.7 anchor",
        status: "active",
      },
    })
  ).json();
  const scope = await (
    await request.post(`${API}/governance/scopes`, {
      headers: auth,
      data: {
        name: "Helios Scope",
        scope_type: "project",
        entity_id: project.id,
      },
    })
  ).json();
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
  await ensureInsight(request, auth, project.id);

  // ---------------------------------------------------------------- 4D.7 contract
  // 1) The unified answer carries the 4D.7 surface: persona, timeline,
  //    next questions, reasoning chain and related projections for a why question.
  const conv = await (
    await request.post(`${API}/brain/conversations`, {
      headers: auth,
      data: {},
    })
  ).json();
  expect(conv.id).toBeTruthy();
  const answerRes = await request.post(`${API}/brain/answer`, {
    headers: auth,
    data: {
      question: QUESTION,
      entity_type: "project",
      entity_id: project.id,
      conversation_id: conv.id,
    },
  });
  expect(answerRes.status(), await answerRes.text()).toBe(200);
  const answer = (await answerRes.json()) as BrainAnswerBody;
  expect(answer.conversation?.id).toBe(conv.id);
  expect(answer.conversation?.turn).toBe(1);
  expect(answer.persona?.org_wide).toBe(true);
  expect(answer.timeline?.length).toBeGreaterThanOrEqual(1);
  for (const entry of answer.timeline ?? []) {
    expect(entry.id).toBeTruthy();
    expect(entry.url).toBeTruthy();
  }
  expect(answer.recommended_next_questions?.length).toBeGreaterThanOrEqual(1);
  expect(answer.reasoning_chain?.length).toBeGreaterThanOrEqual(1);
  expect(answer.reasoning_chain![0].step).toBe(1);
  for (const projection of [
    "related_patterns",
    "related_memories",
    "related_insights",
  ] as const) {
    for (const item of answer[projection] ?? []) {
      expect(item.url).toBeTruthy();
    }
  }
  expect(answer.metrics?.timeline_entries).toBe(answer.timeline?.length);

  // 1b) Determinism: same question (no conversation, unchanged state) composes
  //     the same summary + next questions as the anchored answer.
  const again = (await (
    await request.post(`${API}/brain/answer`, {
      headers: auth,
      data: {
        question: QUESTION,
        entity_type: "project",
        entity_id: project.id,
      },
    })
  ).json()) as BrainAnswerBody;
  expect(again.summary).toBe(answer.summary);
  expect("conversation" in again).toBe(false);
  expect(again.recommended_next_questions).toEqual(
    answer.recommended_next_questions,
  );

  // 2) A follow-up WITHOUT the entity inherits the conversation anchor —
  //    the brain keeps answering about Helios Delivery.
  const followup = (await (
    await request.post(`${API}/brain/answer`, {
      headers: auth,
      data: { question: "has this happened before?", conversation_id: conv.id },
    })
  ).json()) as BrainAnswerBody;
  expect(followup.conversation?.turn).toBe(2);
  const followupProjectRefs = followup.claims.flatMap((c) =>
    c.evidence.filter((e) => e.type === "project").map((e) => e.id),
  );
  expect(followupProjectRefs).toContain(project.id);

  // 3) The conversation records both turns with the inherited anchor.
  const detail = await request.get(`${API}/brain/conversations/${conv.id}`, {
    headers: auth,
  });
  expect(detail.status(), await detail.text()).toBe(200);
  const convDetail = await detail.json();
  expect(convDetail.turn_count).toBe(2);
  expect(convDetail.last_anchor_id).toBe(project.id);
  expect(convDetail.turns.length).toBe(2);
  expect(convDetail.turns[1].anchor_id).toBe(project.id);

  // 4) The unified timeline endpoint composes real rows across sources and is bounded.
  const timelineRes = await request.get(`${API}/brain/timeline/unified`, {
    headers: auth,
    params: { entity_type: "project", entity_id: project.id, limit: "50" },
  });
  expect(timelineRes.status(), await timelineRes.text()).toBe(200);
  const timeline = (await timelineRes.json()) as {
    timeline: Array<{ kind: string; id: string; url: string }>;
    count: number;
    entity: { type: string; id: string };
    scope: { org_wide: boolean };
  };
  expect(timeline.entity.id).toBe(project.id);
  expect(timeline.count).toBeLessThanOrEqual(50);
  expect(timeline.timeline.length).toBeGreaterThanOrEqual(2);
  const kinds = new Set(timeline.timeline.map((e) => e.kind));
  expect(kinds.size).toBeGreaterThanOrEqual(2);
  for (const entry of timeline.timeline) {
    const probe = await request.get(
      entry.url.startsWith("http") ? entry.url : `${API}${entry.url}`,
      { headers: auth },
    );
    expect(probe.status(), `${entry.url} must resolve`).not.toBe(404);
  }
  // Unanchored: company-wide, still bounded.
  const globalTimeline = (await (
    await request.get(`${API}/brain/timeline/unified`, {
      headers: auth,
      params: { limit: "100" },
    })
  ).json()) as { count: number };
  expect(globalTimeline.count).toBeLessThanOrEqual(50);

  // 5) What changed is persona-aware and carries bounded categories.
  const changedRes = await request.get(`${API}/brain/what-changed`, {
    headers: auth,
    params: { days: "7" },
  });
  expect(changedRes.status(), await changedRes.text()).toBe(200);
  const changed = (await changedRes.json()) as BrainAnswerBody["what_changed"];
  expect(changed?.org_wide).toBe(true);
  expect(changed?.categories.length).toBeGreaterThanOrEqual(1);
  expect(changed?.categories.length).toBeLessThanOrEqual(6);

  // 6) Conversations are owner-scoped: another org member gets a 404 even
  //    listing them, and cannot answer into this one.
  const joined = await request.post(`${API}/users/invite`, {
    headers: auth,
    data: {
      email: `scoped7${t}@acme.com`,
      full_name: "Scoped Mgr",
      role: "manager",
    },
  });
  expect(joined.status(), await joined.text()).toBe(201);
  const scopedJoined = await request.post(`${API}/auth/register/invite`, {
    data: {
      token: (await joined.json()).token,
      full_name: "Scoped Mgr",
      password,
    },
  });
  expect(scopedJoined.status(), await scopedJoined.text()).toBe(201);
  const scopedUser = await scopedJoined.json();
  const scopedAuth = { Authorization: `Bearer ${scopedUser.access_token}` };
  const roles = await (
    await request.get(`${API}/roles`, { headers: auth })
  ).json();
  const managerRole = roles.find((r: { code: string }) => r.code === "manager");
  const assignment = await request.post(`${API}/governance/assignments`, {
    headers: auth,
    data: {
      user_id: scopedUser.user.id,
      role_id: managerRole.id,
      scope_id: scope.id,
    },
  });
  expect(assignment.status(), await assignment.text()).toBe(201);
  const assigned = await (
    await request.get(`${API}/governance/assignments`, {
      headers: auth,
      params: { user_id: scopedUser.user.id },
    })
  ).json();
  const orgWideAssign = assigned.find(
    (a: { scope_id: string | null }) => a.scope_id === null,
  );
  expect(orgWideAssign).toBeTruthy();
  await request.delete(`${API}/governance/assignments/${orgWideAssign.id}`, {
    headers: auth,
  });
  await request.post(`${API}/governance/delegations`, {
    headers: auth,
    data: {
      granted_to_user: scopedUser.user.id,
      permission_code: "brain:read",
      reason: "4d.7 e2e",
    },
  });

  const otherConv = await request.get(`${API}/brain/conversations/${conv.id}`, {
    headers: scopedAuth,
  });
  expect(otherConv.status()).toBe(404);
  const othersListed = await request.get(`${API}/brain/conversations`, {
    headers: scopedAuth,
  });
  expect((await othersListed.json()).conversations.length).toBe(0);
  const otherAnswer = await request.post(`${API}/brain/answer`, {
    headers: scopedAuth,
    data: { question: "who owns this?", conversation_id: conv.id },
  });
  expect(otherAnswer.status()).toBe(404);

  // 7) The scoped caller sees a scoped persona and no hidden-project rows
  //    in the timeline, and the hidden project's timeline is a 404.
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
  const scopedTimeline = (await (
    await request.get(`${API}/brain/timeline/unified`, {
      headers: scopedAuth,
      params: { limit: "50" },
    })
  ).json()) as {
    timeline: Array<{ id: string; url: string }>;
    scope: { org_wide: boolean };
  };
  expect(scopedTimeline.scope.org_wide).toBe(false);
  expect(
    scopedTimeline.timeline.some((entry) => entry.url.includes(hidden.id)),
  ).toBe(false);
  const hiddenTimeline = await request.get(`${API}/brain/timeline/unified`, {
    headers: scopedAuth,
    params: { entity_type: "project", entity_id: hidden.id },
  });
  expect(hiddenTimeline.status()).toBe(404);

  // 8) Tenant isolation of the conversation surface.
  const rivalEmail = `rival7${t}@acme.com`;
  const reg = await request.post(`${API}/auth/register`, {
    data: {
      organization_name: `Rival Co ${t}`,
      organization_slug: `rival7-${t}`,
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
  expect(
    (
      await request.get(`${API}/brain/conversations/${conv.id}`, {
        headers: rivalAuth,
      })
    ).status(),
  ).toBe(404);
  const rivalChanged = (await (
    await request.get(`${API}/brain/what-changed`, { headers: rivalAuth })
  ).json()) as BrainAnswerBody["what_changed"];
  expect(JSON.stringify(rivalChanged)).not.toContain("Helios");
  expect(
    JSON.stringify(
      (await (
        await request.get(`${API}/brain/timeline/unified`, {
          headers: rivalAuth,
        })
      ).json()) as object,
    ),
  ).not.toContain("Helios");

  // ---------------------------------------------------------------- UI
  // 9) The unified surface works in the UI: ask, follow up via a next
  //     question, browse the timeline tab and the what-changed tab.
  await page.goto("/intelligence");
  await expect(
    page.getByRole("heading", { name: "Background Intelligence" }),
  ).toBeVisible({ timeout: 15_000 });
  await page.getByRole("button", { name: /Company Brain/ }).click();
  await expect(page.getByText(/Unified company brain/)).toBeVisible({
    timeout: 20_000,
  });
  await page.getByPlaceholder(/Ask the company brain/).fill(QUESTION);
  await page
    .getByRole("button", { name: "Ask the brain", exact: true })
    .last()
    .click();
  await expect(
    page.getByText(/Helios Delivery/, { exact: false }).first(),
  ).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText(/What has happened/)).toBeVisible({
    timeout: 15_000,
  });
  await expect(page.getByText(/Keep asking/)).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText(/Why the brain thinks so/)).toBeVisible({
    timeout: 15_000,
  });
  await expect(page.getByText(/Anchored to this entity/)).toBeVisible({
    timeout: 15_000,
  });
  await expect(page.getByText(/view org-wide \(/)).toBeVisible({
    timeout: 15_000,
  });
  // Click the first recommended next question chip: the follow-up inherits the anchor.
  const nextChip = page
    .getByText(/Keep asking/)
    .locator("..")
    .locator("button")
    .first();
  const nextLabel = (await nextChip.textContent()) ?? "";
  await nextChip.click();
  await expect(
    page.getByText(nextLabel.trim(), { exact: false }).first(),
  ).toBeVisible({ timeout: 60_000 });
  // Timeline tab.
  await page.getByRole("button", { name: "Company timeline" }).click();
  await expect(
    page.getByText(/Unified company timeline|Timeline —/),
  ).toBeVisible({ timeout: 20_000 });
  await page
    .getByRole("button", { name: "Load timeline" })
    .click()
    .catch(() => {});
  // What changed tab.
  await page.getByRole("button", { name: "What changed", exact: true }).click();
  await expect(page.getByRole("heading", { name: /What changed/ })).toBeVisible(
    { timeout: 20_000 },
  );
  await page
    .getByRole("button", { name: "Load digest" })
    .click()
    .catch(() => {});
});
