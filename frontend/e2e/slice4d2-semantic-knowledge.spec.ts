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

async function dispatchEvents(
  request: APIRequestContext,
  auth: Record<string, string>,
  limit = 100,
) {
  const r = await request.post(`${API}/intelligence/events/process`, {
    headers: auth,
    params: { limit: String(limit) },
  });
  expect(r.status(), await r.text()).toBe(200);
  return (await r.json()) as { processed: number };
}

const BASES: Record<string, string> = {
  document: "documents",
  wiki: "wiki",
  policy: "policies",
  sop: "sops",
  template: "templates",
};

async function createPublished(
  request: APIRequestContext,
  auth: Record<string, string>,
  kind: string,
  payload: Record<string, unknown>,
) {
  const base = BASES[kind];
  const created = await request.post(`${API}/${base}`, {
    headers: auth,
    data: payload,
  });
  expect(created.status(), await created.text()).toBe(201);
  const entity = await created.json();
  expect(entity.id).toBeTruthy();
  const published = await request.post(`${API}/${base}/${entity.id}/publish`, {
    headers: auth,
  });
  expect(published.status(), await published.text()).toBe(200);
  return entity;
}

test("slice 4d.2: semantic knowledge search is provider-offline, governed, and change-driven", async ({
  browser,
  request,
}) => {
  test.setTimeout(480_000);
  const t = ts();
  const email = `know${t}@acme.com`;
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
  page.on("response", (res) => {
    if (res.url().includes("8999"))
      console.log(
        `[${Date.now() % 100000}] RESP ${res.status()} ${res.url().replace(API, "").slice(0, 60)}`,
      );
  });

  await registerOrg(
    page,
    `Knowledge Co ${t}`,
    `know-${t}`,
    email,
    "Ada",
    password,
  );
  const token = (await apiLogin(request, email, password)).access_token;
  const auth = { Authorization: `Bearer ${token}` };

  // Seed: project + scope anchor, project-anchored document, org-wide
  // document, approved policy, published wiki page.
  const proj = (
    await request.post(`${API}/projects`, {
      headers: auth,
      data: {
        name: "Nebula",
        description: "Slice 4D.2 anchor",
        status: "active",
      },
    })
  ).json();
  const scope = (
    await request.post(`${API}/governance/scopes`, {
      headers: auth,
      data: {
        name: "Nebula Scope",
        scope_type: "project",
        entity_id: (await proj).id,
      },
    })
  ).json();

  const refund = await createPublished(request, auth, "document", {
    title: "Refund Policy",
    content:
      "Refunds are approved by finance after the customer request is verified against the contract terms. " +
      "Escalations go to the approval workflow. " +
      "Refund Policy refunds finance approval workflow escalation contract verification. ".repeat(
        8,
      ),
  });
  const anchored = await createPublished(request, auth, "document", {
    title: "Scoped Finance Doc",
    content:
      "Expense policy details visible only inside the Nebula project scope. " +
      "Expense policy Nebula project anchored finance details. ".repeat(8),
    project_id: (await proj).id,
  });
  const policy = await (
    await request.post(`${API}/policies`, {
      headers: auth,
      data: {
        title: "Expense Policy",
        content:
          "All expenses above one thousand dollars require manager approval before reimbursement. " +
          "Expense Policy approval reimbursement manager threshold. ".repeat(8),
      },
    })
  ).json();
  const submitted = await request.post(
    `${API}/policies/${(await policy).id}/submit`,
    { headers: auth },
  );
  expect(submitted.status(), await submitted.text()).toBe(200);
  const approved = await request.post(
    `${API}/policies/${(await policy).id}/approve`,
    { headers: auth },
  );
  expect(approved.status(), await approved.text()).toBe(200);
  const wiki = await createPublished(request, auth, "wiki", {
    title: "Onboarding Runbook",
    content:
      "New hires follow the equipment request and system access onboarding steps. " +
      "Onboarding Runbook equipment system access new hires. ".repeat(8),
  });

  // Change-driven indexing: drain the durable event bus into the vector index.
  // The scheduler may already have dispatched these events, so a 0 here only
  // means the queue is empty; the search assertions below are authoritative.
  const first = await dispatchEvents(request, auth);
  expect(first.processed).toBeGreaterThanOrEqual(0);

  const search = async (question: string, kinds?: string[], headers = auth) => {
    const r = await request.post(`${API}/brain/knowledge/search`, {
      headers,
      data: { question, kinds },
    });
    expect(r.status(), await r.text()).toBe(200);
    return (await r.json()) as {
      query: string;
      results: Array<Record<string, unknown>>;
      total: number;
      provider: string | null;
      truncated: boolean;
    };
  };

  const waitForIndex = async (
    question: string,
    kinds: string[],
    headers = auth,
  ) => {
    for (let attempt = 0; attempt < 6; attempt++) {
      await dispatchEvents(request, headers);
      const result = await search(question, kinds, headers);
      if (result.results.length > 0) return result;
      await new Promise((resolve) => setTimeout(resolve, 3_000));
    }
    return search(question, kinds, headers);
  };

  // 1) Hybrid retrieval: the best source surfaces first with explicit score
  //    fields, provider name and evidence lineage — never embeddings/confidence.
  const doc = await waitForIndex("how does the refund approval workflow work", [
    "document",
  ]);
  expect(doc.provider).toBe("deterministic");
  expect(doc.results.length).toBeGreaterThan(0);
  const top = doc.results[0];
  expect(top.source_type).toBe("document");
  expect(top.source_id).toBe(refund.id);
  expect(top.title).toBe("Refund Policy");
  expect(top.url).toContain(`/documents/${refund.id}`);
  expect(top.semantic_score).toBeGreaterThanOrEqual(0);
  expect(top.lexical_score).toBeGreaterThanOrEqual(0);
  expect(top.retrieval_score).toBeGreaterThanOrEqual(
    top.semantic_score as number,
  );
  expect(top.scope).toBe("org");
  expect(top.provider).toBe("deterministic");
  expect(top.updated_at).toBeTruthy();
  expect(top.indexed_at).toBeTruthy();
  expect("embedding" in top).toBe(false);
  expect("confidence" in top).toBe(false);

  // 2) All knowledge kinds are indexed: policy + wiki surface under their kind.
  const policyHit = await waitForIndex(
    "manager approval above one thousand dollars",
    ["policy"],
  );
  expect(policyHit.results.some((r) => r.source_id === policy.id)).toBe(true);
  const wikiHit = await waitForIndex("equipment request for new hires", [
    "wiki",
  ]);
  expect(wikiHit.results.some((r) => r.source_id === wiki.id)).toBe(true);

  // 3) Tenant isolation: a completely separate org sees none of these rows.
  const otherEmail = `rival${t}@acme.com`;
  const reg = await request.post(`${API}/auth/register`, {
    data: {
      organization_name: `Rival Co ${t}`,
      organization_slug: `rival-${t}`,
      industry: "Software",
      country: "United States",
      full_name: "Riva",
      email: otherEmail,
      password,
    },
  });
  expect(reg.status(), await reg.text()).toBe(201);
  const rivalAuth = {
    Authorization: `Bearer ${(await reg.json()).access_token}`,
  };
  const tenant = await search(
    "how does the refund approval workflow work",
    undefined,
    rivalAuth,
  );
  expect(tenant.results).toEqual([]);

  // 4) Governance isolation: a scoped-only manager with delegated brain:read
  //    sees ONLY the project-anchored knowledge.
  const invite = await request.post(`${API}/users/invite`, {
    headers: auth,
    data: {
      email: `emp${t}@acme.com`,
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
  expect(managerRole).toBeTruthy();
  const assignment = await request.post(`${API}/governance/assignments`, {
    headers: auth,
    data: {
      user_id: joinedUser.user.id,
      role_id: managerRole.id,
      scope_id: (await scope).id,
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
  const removed = await request.delete(
    `${API}/governance/assignments/${orgWideAssign.id}`,
    { headers: auth },
  );
  expect(removed.status(), await removed.text()).toBe(200);
  const delegated = await request.post(`${API}/governance/delegations`, {
    headers: auth,
    data: {
      granted_to_user: joinedUser.user.id,
      permission_code: "brain:read",
      reason: "4d.2 e2e",
    },
  });
  expect(delegated.status(), await delegated.text()).toBe(201);

  const scopedHit = await search(
    "expense policy details",
    undefined,
    scopedAuth,
  );
  const visibleIds = scopedHit.results.map((r) => r.source_id);
  expect(visibleIds).toContain(anchored.id);
  expect(visibleIds).not.toContain(refund.id);
  expect(visibleIds).not.toContain(policy.id);
  expect(scopedHit.results[0].scope).toBe("project");

  // 5) Deletes remove vectors: a removed document stops surfacing.
  const throwaway = await createPublished(request, auth, "document", {
    title: "Deprecated Note",
    content:
      "This obsolete content must never resurface once removed. " +
      "Deprecated obsolete remove resurface note. ".repeat(8),
  });
  await dispatchEvents(request, auth);
  const beforeDelete = await search("obsolete deprecated note resurface");
  expect(beforeDelete.results.some((r) => r.source_id === throwaway.id)).toBe(
    true,
  );
  const deleted = await request.delete(`${API}/documents/${throwaway.id}`, {
    headers: auth,
  });
  expect(deleted.status(), await deleted.text()).toBe(200);
  await dispatchEvents(request, auth);
  const afterDelete = await search("obsolete deprecated note resurface");
  expect(afterDelete.results.some((r) => r.source_id === throwaway.id)).toBe(
    false,
  );

  // 6) UI: the Semantic Knowledge tab renders results with score badges.
  await page.goto("/intelligence");
  await expect(
    page.getByRole("heading", { name: "Background Intelligence" }),
  ).toBeVisible({ timeout: 15_000 });
  await page.getByText("Semantic Knowledge", { exact: true }).click();
  const textarea = page.locator(
    "textarea[placeholder*='refund approval workflow']",
  );
  await expect(textarea).toBeVisible({ timeout: 15_000 });
  await textarea.fill("how does the refund approval workflow work");
  await page.getByRole("button", { name: "Search knowledge" }).click();
  await expect(page.getByText("Refund Policy", { exact: true })).toBeVisible({
    timeout: 20_000,
  });
  await expect(
    page.getByText("deterministic", { exact: false }).first(),
  ).toBeVisible({ timeout: 20_000 });
  await expect(
    page.getByText("retrieval", { exact: false }).first(),
  ).toBeVisible({ timeout: 20_000 });
  await expect(page.locator("a[href*='/documents/']").first()).toBeVisible({
    timeout: 20_000,
  });
});
