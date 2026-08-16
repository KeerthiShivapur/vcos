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

async function hire(request: APIRequestContext, auth: Record<string, string>, first: string, last: string, tag: string) {
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

async function project(request: APIRequestContext, auth: Record<string, string>, name: string, tag: string, ownerId: string) {
  const r = await request.post(`${API}/projects`, {
    headers: auth,
    data: { name: `${name} ${tag}`, code: `${tag}`.toUpperCase(), owner_id: ownerId },
  });
  expect(r.status(), await r.text()).toBe(201);
  return (await r.json()) as { id: string; name: string };
}

test("slice 4f.4: ownership is declared, temporal, advisory-only and one UI surface; history is never lost", async ({ browser, request }) => {
  test.setTimeout(900_000);
  const t = ts();
  const email = `owner${t}@acme.com`;
  const password = "StrongPass123!";

  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  page.on("console", (msg) => {
    if (msg.type() === "error") console.log(`[${Date.now() % 100000}] console:error ${msg.text().slice(0, 200)}`);
  });

  await apiRegister(request, `Owner Co ${t}`, `owner-${t}`, email, "Vera", password);
  const token = (await apiLogin(request, email, password)).access_token;
  const auth = { Authorization: `Bearer ${token}` };

  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL("**/home", { timeout: 30_000 });

  // ------------------------------------------------------------------ seeding
  const ada = await hire(request, auth, "Ada", "Draper", "ada");
  const bob = await hire(request, auth, "Bob", "Wright", "bob");
  const cy = await hire(request, auth, "Cy", "Mellon", "cy");
  const dee = await hire(request, auth, "Dee", "Hart", "dee");

  const ledger = await project(request, auth, "Ledger Service", `ledger${t}`, ada.id);
  const billing = await project(request, auth, "Billing Core", `billing${t}`, bob.id);
  const checkout = await project(request, auth, "Checkout Flow", `checkout${t}`, bob.id);
  const payments = await project(request, auth, "Payments Platform", `payments${t}`, ada.id);
  const sync = await project(request, auth, "Data Sync", `sync${t}`, dee.id);

  // Declared ownership arrives through the event bridge (project.created)
  // and the brain surface refreshes/asserts it - same window, no duplicate.
  const assign = async (obj: { id: string; name: string }, ownerId: string) => {
    const r = await request.post(`${API}/brain/ownership/assign`, {
      headers: auth,
      data: {
        object_type: "project",
        object_id: obj.id,
        object_name: obj.name,
        responsibility_type: "primary",
        owner_id: ownerId,
      },
    });
    expect(r.status(), await r.text()).toBe(200);
    return (await r.json()) as { relationship: { id: string; owner_label: string } };
  };
  await assign(ledger, ada.id);
  await assign(billing, bob.id);
  await assign(checkout, bob.id);
  await assign(payments, ada.id);
  await assign(sync, dee.id);

  const backup = await request.post(`${API}/brain/ownership/backup`, {
    headers: auth,
    data: { object_type: "project", object_id: payments.id, backup_owner_id: cy.id },
  });
  expect(backup.status(), await backup.text()).toBe(200);

  await dispatchAll(request, auth);

  // ----------------------------------------------------------- API contract
  const obj = (await (
    await request.get(`${API}/brain/ownership/objects/project/${payments.id}`, { headers: auth })
  ).json()) as {
    primary: { owner_label: string; backup_owner_label: string; responsibility_type: string };
    signals: unknown[];
  };
  expect(obj.primary.owner_label).toBe("Ada Draper");
  expect(obj.primary.backup_owner_label).toBe("Cy Mellon");
  expect(obj.primary.responsibility_type).toBe("primary");

  // Transfer: the old window closes at the boundary, the new one begins there.
  const transfer = await request.post(`${API}/brain/ownership/transfer`, {
    headers: auth,
    data: { object_type: "project", object_id: payments.id, to_owner_id: bob.id },
  });
  expect(transfer.status(), await transfer.text()).toBe(200);
  const transferred = (await transfer.json()) as { transferred: boolean; change: { action: string } };
  expect(transferred.transferred).toBe(true);
  expect(transferred.change.action).toBe("transferred");

  const now = await (
    await request.get(`${API}/brain/ownership/objects/project/${payments.id}`, { headers: auth })
  ).json();
  expect((now as { primary: { owner_label: string } }).primary.owner_label).toBe("Bob Wright");

  // Backup is window-bound: re-declare it on the new tenure.
  const backup2 = await request.post(`${API}/brain/ownership/backup`, {
    headers: auth,
    data: { object_type: "project", object_id: payments.id, backup_owner_id: cy.id },
  });
  expect(backup2.status(), await backup2.text()).toBe(200);

  // Temporal reconstruction: as-of a moment before the first window began,
  // no one owned it at all.
  const before = (await (
    await request.get(`${API}/brain/ownership/objects/project/${payments.id}/as-of`, {
      headers: auth,
      params: { at: "2025-01-01T00:00:00Z" },
    })
  ).json()) as { primary: { owner_label: string } | null };
  expect(before.primary?.owner_label ?? null).toBe(null);

  const history = (await (
    await request.get(`${API}/brain/ownership/objects/project/${payments.id}/history`, { headers: auth })
  ).json()) as { events: Array<{ action: string }> };
  const actions = history.events.map((e) => e.action);
  expect(actions).toContain("assigned");
  expect(actions).toContain("transferred");

  // Arc a gap: Dee is archived (a different event than offboarding) so her
  // window stays open with an inactive owner; analysis surfaces it advisory.
  const archive = await request.post(`${API}/employees/${dee.id}/archive`, {
    headers: auth,
    data: { reason: "left the company" },
  });
  expect(archive.status(), await archive.text()).toBe(200);

  const analysis = (await (
    await request.post(`${API}/brain/ownership/analyze`, { headers: auth, params: { limit: "200" } })
  ).json()) as { scanned: number; gap: number; single_point: number; mismatch: number };
  expect(analysis.scanned).toBeGreaterThanOrEqual(4);
  expect(analysis.gap).toBe(1);
  expect(analysis.single_point).toBe(2);
  expect(analysis.mismatch).toBe(0);

  const signals = (await (
    await request.get(`${API}/brain/ownership/signals`, {
      headers: auth,
      params: { status: "open" },
    })
  ).json()) as { signals: Array<{ kind: string; severity: string; detail: string; id: string }> };
  expect(signals.signals.length).toBe(3);
  const gapSignal = signals.signals.find((s) => s.kind === "gap");
  expect(gapSignal).toBeTruthy();
  expect(gapSignal!.severity).toBe("critical");
  expect(gapSignal!.detail).toContain("no longer an active employee");
  const sp = signals.signals.filter((s) => s.kind === "single_point");
  expect(sp.length).toBe(2);
  expect(sp.every((s) => s.severity === "warning")).toBe(true);
  expect(sp.every((s) => s.detail.includes("no backup"))).toBe(true);

  // Resolve the gap advisory (management decides; nothing auto-changed).
  const decided = await request.post(`${API}/brain/ownership/signals/${gapSignal!.id}/resolve`, {
    headers: auth,
  });
  expect(decided.status(), await decided.text()).toBe(200);

  const coverage = await request.post(`${API}/brain/ownership/coverage-check`, {
    headers: auth,
    data: { objects: [{ object_type: "project", object_id: sync.id, object_name: sync.name }] },
  });
  expect(coverage.status(), await coverage.text()).toBe(200);
  expect(((await coverage.json()) as { unassigned_total: number }).unassigned_total).toBe(0);

  // ------------------------------------------------------------- profile UI
  await page.goto(`/people/${bob.id}`);
  await expect(page.getByRole("heading", { name: "Bob Wright" }).first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByRole("heading", { name: "Responsibilities" })).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("Ledger Service", { exact: false })).not.toBeVisible();

  // Bob owns billing, checkout and (after the transfer) payments.
  await expect(page.getByText("Billing Core", { exact: false }).first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("Checkout Flow", { exact: false }).first()).toBeVisible();
  await expect(page.getByText("Payments Platform", { exact: false }).first()).toBeVisible();
  await expect(page.getByText("since", { exact: false }).first()).toBeVisible();

  // Cy holds a backup role only - surfaced explicitly.
  await page.goto(`/people/${cy.id}`);
  await expect(page.getByRole("heading", { name: "Cy Mellon" }).first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("Backup owner for 1 active responsibility.")).toBeVisible({ timeout: 20_000 });

  // ------------------------------------------------------------ ownership UI
  await page.goto("/ownership");
  await expect(page.getByRole("heading", { name: "Ownership & responsibility" })).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("Active responsibilities", { exact: true })).toBeVisible();
  const openSignalsStat = page.locator("div.card.flex").filter({
    has: page.getByText("Open signals", { exact: true }),
  });
  await expect(openSignalsStat).toBeVisible();
  await expect(openSignalsStat.getByText("2", { exact: true })).toBeVisible({ timeout: 20_000 });

  // Advisory preview is read-only.
  await page.getByRole("button", { name: /preview advisory/i }).click();
  await expect(page.getByText(/would scan/i).first()).toBeVisible({ timeout: 20_000 });

  // Re-running the bounded batch is idempotent for still-open signals, but a
// resolved gap whose cause never changed is honestly re-surfaced.
  await page.getByRole("button", { name: /run bounded batch/i }).click();
  await expect(page.getByText(/batch written/i).first()).toBeVisible({ timeout: 20_000 });

  // Advisory copy: the two single-point signals + the re-surfaced gap.
  await expect(page.getByText("Single point", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Single point", { exact: true })).toHaveCount(2);
  await expect(page.getByText("Uncovered gap", { exact: true })).toHaveCount(1);
  await expect(page.getByText(/single-person dependency risk/i).first()).toBeVisible();

  // Acknowledge the re-surfaced gap (acknowledging ≠ fixing; the cause is
  // still there, so the advisory is re-created - the honest surface never
  // hides a live gap).
  const gapItem = page
    .getByRole("listitem")
    .filter({ has: page.getByText("Uncovered gap", { exact: true }) });
  await gapItem.getByRole("button", { name: "Acknowledge" }).click();
  await expect(page.getByText("Uncovered gap", { exact: true })).toHaveCount(0);
  await expect(openSignalsStat.getByText("2", { exact: true })).toBeVisible({ timeout: 20_000 });

  // Acknowledge one single-point advisory; it leaves the list.
  await page
    .getByRole("listitem")
    .filter({ has: page.getByText("Single point", { exact: true }) })
    .first()
    .getByRole("button", { name: "Acknowledge" })
    .click();
  await expect(page.getByText("Single point", { exact: true })).toHaveCount(1);
  await expect(openSignalsStat.getByText("1", { exact: true })).toBeVisible({ timeout: 20_000 });

  // ------------------------------------------------------- brain ask reasoning
  const responsibility = (await (
    await request.post(`${API}/brain/knowledge/query`, {
      headers: auth,
      data: { question: `who is responsible for the Payments Platform?` },
    })
  ).json()) as { intent: string; kind: string; answer: string };
  expect(responsibility.intent).toBe("responsibility");
  expect(responsibility.kind).toBe("ownership");
  expect(responsibility.answer).toContain("Bob Wright is responsible for");

  const continuity = (await (
    await request.post(`${API}/brain/knowledge/query`, {
      headers: auth,
      data: { question: `who takes over the Payments Platform if the owner is unavailable?` },
    })
  ).json()) as { intent: string; answer: string };
  expect(continuity.intent).toBe("continuity");
  expect(continuity.answer).toContain("Cy Mellon steps in as backup");

  await page.close();
});