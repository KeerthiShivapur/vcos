import {
  expect,
  test,
  type APIRequestContext,
  type Browser,
  type BrowserContext,
} from "@playwright/test";

const API = "http://localhost:8999/api/v1";
const ACCESS_KEY = "vcos.access_token";
const REFRESH_KEY = "vcos.refresh_token";

function unique(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
}

interface Session {
  access_token: string;
  refresh_token: string;
}

async function registerCompany(
  request: APIRequestContext,
): Promise<{
  session: Session;
  email: string;
  password: string;
  orgName: string;
}> {
  const suffix = unique();
  const email = `authinit${suffix}@example.com`;
  const password = "StrongPass123!";
  const orgName = `Auth Init ${suffix}`;
  const response = await request.post(`${API}/auth/register`, {
    data: {
      organization_name: orgName,
      organization_slug: `auth-init-${suffix}`,
      industry: "Software",
      country: "US",
      full_name: "Auth Init",
      email,
      password,
    },
  });
  expect(response.status(), await response.text()).toBe(201);
  const body = (await response.json()) as Session;
  return { session: body, email, password, orgName };
}

async function contextWithSession(
  browser: Browser,
  session: Session,
): Promise<BrowserContext> {
  const context = await browser.newContext();
  await context.addInitScript(
    ({ access, refresh, accessKey, refreshKey }) => {
      localStorage.setItem(accessKey, access);
      localStorage.setItem(refreshKey, refresh);
    },
    {
      access: session.access_token,
      refresh: session.refresh_token,
      accessKey: ACCESS_KEY,
      refreshKey: REFRESH_KEY,
    },
  );
  return context;
}

test("anonymous company route redirects to sign in instead of spinning forever", async ({
  page,
}) => {
  await page.goto("/home");
  await page.waitForURL(/\/login(\?|$)/, { timeout: 20_000 });
  await expect(
    page.getByRole("heading", { name: /sign in to your company/i }),
  ).toBeVisible();
  const refresh = await page.evaluate(
    (key) => localStorage.getItem(key),
    REFRESH_KEY,
  );
  expect(refresh).toBeNull();
});

test("a valid session reaches the authorized company workspace", async ({
  browser,
  request,
}) => {
  const { session, orgName } = await registerCompany(request);
  const context = await contextWithSession(browser, session);
  const page = await context.newPage();

  const meResponses: number[] = [];
  page.on("response", (response) => {
    if (response.url().includes("/api/v1/auth/me"))
      meResponses.push(response.status());
  });

  await page.goto("/home");
  await expect(page.getByText("Opening your company")).toHaveCount(0, {
    timeout: 25_000,
  });
  await expect(page.getByText(orgName).first()).toBeVisible({
    timeout: 25_000,
  });
  await expect(page).toHaveURL(/\/home$/);
  expect(meResponses.length).toBeGreaterThan(0);
  expect(meResponses.every((status) => status === 200)).toBe(true);
  await context.close();
});

test("an expired session is cleared and redirected to sign in", async ({
  browser,
  request,
}) => {
  const { session } = await registerCompany(request);
  const context = await contextWithSession(browser, session);
  await context.route("**/api/v1/auth/me", (route) =>
    route.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Not authenticated" }),
    }),
  );
  await context.route("**/api/v1/auth/refresh", (route) =>
    route.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Session expired" }),
    }),
  );
  const page = await context.newPage();
  await page.goto("/home");
  await page.waitForURL(/\/login(\?|$)/, { timeout: 20_000 });
  const tokens = await page.evaluate(
    ([accessKey, refreshKey]) => ({
      access: localStorage.getItem(accessKey),
      refresh: localStorage.getItem(refreshKey),
    }),
    [ACCESS_KEY, REFRESH_KEY],
  );
  expect(tokens.access).toBeNull();
  expect(tokens.refresh).toBeNull();
  await context.close();
});

test("persistent identity failures end in a retryable error state and recover", async ({
  browser,
  request,
}) => {
  const { session, orgName } = await registerCompany(request);
  const context = await contextWithSession(browser, session);
  let failing = true;
  await context.route("**/api/v1/auth/me", (route) => {
    if (failing) {
      return route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Boom" }),
      });
    }
    return route.continue();
  });
  const page = await context.newPage();
  await page.goto("/home");
  await expect(
    page.getByRole("heading", { name: /we couldn't open your company/i }),
  ).toBeVisible({
    timeout: 25_000,
  });
  await expect(page.getByText("Opening your company")).toHaveCount(0);

  failing = false;
  await page.getByRole("button", { name: /try again/i }).click();
  await expect(page.getByText(orgName).first()).toBeVisible({
    timeout: 25_000,
  });
  await context.close();
});

test("an inactive or missing organization shows a workspace state, not a spinner", async ({
  browser,
  request,
}) => {
  const { session } = await registerCompany(request);
  const context = await contextWithSession(browser, session);
  await context.route("**/api/v1/organizations/me", (route) =>
    route.fulfill({
      status: 403,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Organization is not active" }),
    }),
  );
  const page = await context.newPage();
  await page.goto("/home");
  await expect(
    page.getByRole("heading", { name: /company workspace unavailable/i }),
  ).toBeVisible({
    timeout: 25_000,
  });
  await expect(page.getByText("Opening your company")).toHaveCount(0);
  await context.close();
});

test("a failing platform endpoint never blocks the workspace", async ({
  browser,
  request,
}) => {
  const { session, orgName } = await registerCompany(request);
  const context = await contextWithSession(browser, session);
  await context.route("**/api/v1/platform", (route) =>
    route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Platform unavailable" }),
    }),
  );
  const page = await context.newPage();
  await page.goto("/home");
  await expect(page.getByText(orgName).first()).toBeVisible({
    timeout: 25_000,
  });
  await expect(page.getByText("Opening your company")).toHaveCount(0);
  await context.close();
});

test("slow identity and organization responses still settle into the workspace", async ({
  browser,
  request,
}) => {
  const { session, orgName } = await registerCompany(request);
  const context = await contextWithSession(browser, session);
  const slow = async (route: import("@playwright/test").Route) => {
    await new Promise((resolve) => setTimeout(resolve, 1500));
    await route.continue().catch(() => undefined);
  };
  await context.route("**/api/v1/auth/me", slow);
  await context.route("**/api/v1/organizations/me", slow);
  const page = await context.newPage();
  await page.goto("/home");
  await expect(page.getByText(orgName).first()).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByText("Opening your company")).toHaveCount(0);
  await context.close();
});

test("signing in through the real login form reaches the workspace", async ({
  browser,
  request,
}) => {
  const { email, password, orgName } = await registerCompany(request);
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL("**/home", { timeout: 30_000 });
  await expect(page.getByText(orgName).first()).toBeVisible({
    timeout: 25_000,
  });
  await expect(page.getByText("Opening your company")).toHaveCount(0);
  await context.close();
});
