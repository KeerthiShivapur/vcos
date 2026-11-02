import {
  expect,
  test,
  type APIRequestContext,
  type BrowserContext,
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

test("slice 4b: messaging loop — realtime delivery, edit, reaction, delete, search", async ({
  browser,
  request,
}) => {
  test.setTimeout(480_000);
  const t = ts();
  const founderEmail = `ada4b${t}@acme.com`;
  const bobEmail = `bob4b${t}@acme.com`;
  const bobName = `Bob 4B${t}`;
  const password = "StrongPass123!";
  const firstMessage = "The unicorn deployment is ready";
  const editedMessage = "The unicorn deployment is green";
  const secondMessage = "Ship it tomorrow";

  // 1. Founder registers, invites Bob, Bob accepts.
  const founderCtx = await browser.newContext();
  const founder = await founderCtx.newPage();
  await registerOrg(
    founder,
    `Org 4B ${t}`,
    `t4b-${t}`,
    founderEmail,
    "Ada",
    password,
  );
  const founderToken = (await apiLogin(request, founderEmail, password))
    .access_token;
  const auth = { Authorization: `Bearer ${founderToken}` };

  await founder.goto("/settings?tab=members");
  await founder.getByRole("button", { name: /invite/i }).click();
  await founder.getByLabel("Email").fill(bobEmail);
  await founder.getByLabel("Full name (optional)").fill(bobName);
  await founder.getByRole("button", { name: "Send invitation" }).click();
  const inviteUrl = await founder
    .locator("code")
    .filter({ hasText: "http://localhost:3000/register?invite=" })
    .first()
    .textContent({ timeout: 10_000 });
  expect(inviteUrl).toContain("/register?invite=");
  await founder.getByRole("button", { name: "Done" }).click();

  const bobCtx = await browser.newContext();
  const bob = await bobCtx.newPage();
  await bob.goto(inviteUrl!);
  await bob.getByLabel("Your full name").fill(bobName);
  await bob.getByLabel("Password", { exact: true }).fill(password);
  await bob.getByLabel("Confirm password", { exact: true }).fill(password);
  await bob
    .getByRole("button", { name: "Accept invitation & continue" })
    .click();
  await bob.waitForURL("**/home", { timeout: 20_000 });

  // 2. Bob parks on Messages before the conversation exists (proves live list update).
  await bob.goto("/messages");
  await expect(bob.getByRole("heading", { name: "Messages" })).toBeVisible({
    timeout: 15_000,
  });

  // 3. Founder opens Messages and starts a DM with Bob from the UI.
  await founder.goto("/messages");
  await expect(founder.getByRole("heading", { name: "Messages" })).toBeVisible({
    timeout: 15_000,
  });
  await founder.getByRole("button", { name: new RegExp(bobName) }).click();
  await expect(founder.getByText("No messages yet")).toBeVisible({
    timeout: 15_000,
  });

  // Bob's list picks the new DM up (live push or the 30s polling fallback).
  await expect(bob.getByRole("button", { name: /Direct message/ })).toBeVisible(
    { timeout: 60_000 },
  );
  await bob.getByRole("button", { name: /Direct message/ }).click();
  await expect(bob.getByText("No messages yet")).toBeVisible({
    timeout: 15_000,
  });

  // 4. Founder sends a message — appears instantly on his tab (optimistic).
  await founder.getByPlaceholder("Type a message…").fill(firstMessage);
  await founder.getByPlaceholder("Type a message…").press("Enter");
  await expect(founder.getByText(firstMessage)).toBeVisible({
    timeout: 15_000,
  });

  // 5. Bob receives it without any interaction (realtime, or the 30s fallback).
  await expect(bob.getByText(firstMessage)).toBeVisible({ timeout: 60_000 });
  await expect(bob.getByText("Ada").first()).toBeVisible({ timeout: 10_000 });

  // 6. Founder edits the message — both tabs converge.
  await founder.getByTitle("Edit").click();
  await founder.getByPlaceholder("Edit message…").fill(editedMessage);
  await founder.getByRole("button", { name: "Save" }).click();
  await expect(founder.getByText(editedMessage)).toBeVisible({
    timeout: 15_000,
  });
  await expect(founder.getByText("(edited)")).toBeVisible({ timeout: 10_000 });
  await expect(bob.getByText(editedMessage)).toBeVisible({ timeout: 60_000 });
  await expect(bob.getByText("(edited)")).toBeVisible({ timeout: 10_000 });

  // 7. Founder reacts — Bob's copy of the bubble shows the reaction count.
  await founder.getByTitle("React").click();
  await expect(
    founder.getByTitle("React").getByText("1", { exact: true }),
  ).toBeVisible({ timeout: 15_000 });
  await expect(
    bob.getByTitle("React").getByText("1", { exact: true }),
  ).toBeVisible({ timeout: 60_000 });

  // 8. Founder sends a second message, then deletes it — Bob sees the tombstone.
  await founder.getByPlaceholder("Type a message…").fill(secondMessage);
  await founder.getByPlaceholder("Type a message…").press("Enter");
  await expect(bob.getByText(secondMessage)).toBeVisible({ timeout: 60_000 });
  founder.once("dialog", (dialog) => void dialog.accept());
  await founder.getByTitle("Delete").last().click();
  await expect(founder.getByText("Deleted message")).toBeVisible({
    timeout: 15_000,
  });
  await expect(bob.getByText("Deleted message")).toBeVisible({
    timeout: 60_000,
  });

  // 9. The conversation is indexed in universal search (message kind, member-scoped).
  const search = await (
    await request.get(`${API}/search`, {
      headers: auth,
      params: { q: "unicorn" },
    })
  ).json();
  const messageHit = search.results.find(
    (r: { type: string }) => r.type === "message",
  );
  expect(messageHit).toBeTruthy();
  expect(String(messageHit.metadata.conversation_id)).toBeTruthy();

  // Bob's search returns the same message; an outsider org sees nothing.
  const bobToken = (await apiLogin(request, bobEmail, password)).access_token;
  const bobSearch = await (
    await request.get(`${API}/search`, {
      headers: { Authorization: `Bearer ${bobToken}` },
      params: { q: "unicorn" },
    })
  ).json();
  expect(
    bobSearch.results.some((r: { type: string }) => r.type === "message"),
  ).toBe(true);

  const outsiderCtx = await browser.newContext();
  const outsider = await outsiderCtx.newPage();
  await registerOrg(
    outsider,
    `Org 4Bx ${t}`,
    `t4bx-${t}`,
    `x4b${t}@acme.com`,
    "Xavier",
    password,
  );
  const outsiderToken = (await apiLogin(request, `x4b${t}@acme.com`, password))
    .access_token;
  const outsiderSearch = await (
    await request.get(`${API}/search`, {
      headers: { Authorization: `Bearer ${outsiderToken}` },
      params: { q: "unicorn" },
    })
  ).json();
  expect(
    outsiderSearch.results.some((r: { type: string }) => r.type === "message"),
  ).toBe(false);

  // 10. The whole loop is audited on the event bus.
  const events = await (
    await request.get(`${API}/events`, { headers: auth })
  ).json();
  const names = events.items.map((e: { name: string }) => e.name);
  for (const expected of [
    "messaging.conversation_created",
    "messaging.message_sent",
    "messaging.message_updated",
    "messaging.message_reaction_added",
    "messaging.message_deleted",
  ]) {
    expect(names).toContain(expected);
  }

  await outsiderCtx.close();
  await bobCtx.close();
  await founderCtx.close();
});
