import { expect, test } from "@playwright/test";

import {
  AuthBootstrapRunner,
  type AuthOutcome,
  type AuthRunDeps,
} from "../lib/auth-bootstrap";
import type {
  Organization,
  PlatformInfo,
  SuggestedProfileOut,
  User,
} from "../types";

const USER = {
  id: "user-1",
  organization_id: "org-1",
  email: "person@example.com",
  full_name: "Person",
} as User;

const ORG = {
  id: "org-1",
  name: "Acme",
} as Organization;

const PLATFORM = {
  name: "VCOS",
  version: "1.0.0",
  environment: "test",
  api_version: "v1",
  ai_provider: "none",
  features: { foundation: true, ai_foundation: true, redis: false },
} as PlatformInfo;

function httpError(status: number): Error {
  return Object.assign(new Error(`Request failed (${status})`), { status });
}

function abortable(signal: AbortSignal): Promise<never> {
  return new Promise((_, reject) => {
    if (signal.aborted) {
      reject(Object.assign(new Error("aborted"), { name: "AbortError" }));
      return;
    }
    signal.addEventListener("abort", () =>
      reject(Object.assign(new Error("aborted"), { name: "AbortError" })),
    );
  });
}

function deps(overrides: Partial<AuthRunDeps> = {}): AuthRunDeps {
  return {
    hasSession: () => true,
    fetchMe: async () => USER,
    fetchOrganization: async () => ORG,
    fetchPlatform: async () => PLATFORM,
    fetchExperienceProfile: async () =>
      ({ current_profile: "startup" }) as SuggestedProfileOut,
    retryDelayMs: 1,
    ...overrides,
  };
}

async function run(runner: AuthBootstrapRunner): Promise<AuthOutcome> {
  return runner.start().outcome;
}

test("does not hit the API when there is no session", async () => {
  let calls = 0;
  const outcome = await run(
    new AuthBootstrapRunner(
      deps({
        hasSession: () => false,
        fetchMe: async () => {
          calls += 1;
          return USER;
        },
      }),
    ),
  );
  expect(outcome).toEqual({ status: "unauthenticated", reason: "no_session" });
  expect(calls).toBe(0);
});

test("authenticates with identity and workspace, and tolerates optional failures", async () => {
  const outcome = await run(
    new AuthBootstrapRunner(
      deps({
        fetchPlatform: async () => {
          throw httpError(500);
        },
        fetchExperienceProfile: async () => {
          throw httpError(500);
        },
      }),
    ),
  );
  expect(outcome.status).toBe("authenticated");
  if (outcome.status !== "authenticated") return;
  expect(outcome.user.id).toBe("user-1");
  expect(outcome.organization.id).toBe("org-1");
  expect(outcome.platform).toBeNull();
  expect(outcome.experienceProfile).toBeNull();
});

test("falls back to the organization profile when the profile endpoint fails", async () => {
  const outcome = await run(
    new AuthBootstrapRunner(
      deps({
        fetchOrganization: async () =>
          ({ ...ORG, experience_profile: "growing" }) as Organization,
        fetchExperienceProfile: async () => {
          throw httpError(500);
        },
      }),
    ),
  );
  expect(outcome.status).toBe("authenticated");
  if (outcome.status !== "authenticated") return;
  expect(outcome.experienceProfile).toBe("growing");
});

test("maps a rejected identity to unauthenticated", async () => {
  const outcome = await run(
    new AuthBootstrapRunner(
      deps({
        fetchMe: async () => {
          throw httpError(401);
        },
      }),
    ),
  );
  expect(outcome).toEqual({ status: "unauthenticated", reason: "rejected" });
});

test("maps an inactive or missing workspace to organization_unavailable", async () => {
  for (const status of [403, 404]) {
    const outcome = await run(
      new AuthBootstrapRunner(
        deps({
          fetchOrganization: async () => {
            throw httpError(status);
          },
        }),
      ),
    );
    expect(outcome.status).toBe("organization_unavailable");
    if (outcome.status !== "organization_unavailable") continue;
    expect(outcome.user?.id).toBe("user-1");
  }
});

test("retries transient identity failures and then authenticates", async () => {
  let attempts = 0;
  const outcome = await run(
    new AuthBootstrapRunner(
      deps({
        maxAttempts: 3,
        fetchMe: async () => {
          attempts += 1;
          if (attempts < 2) throw httpError(503);
          return USER;
        },
      }),
    ),
  );
  expect(outcome.status).toBe("authenticated");
  expect(attempts).toBe(2);
});

test("returns a retryable error after persistent server failures", async () => {
  const outcome = await run(
    new AuthBootstrapRunner(
      deps({
        maxAttempts: 2,
        fetchMe: async () => {
          throw httpError(500);
        },
      }),
    ),
  );
  expect(outcome.status).toBe("error");
  if (outcome.status !== "error") return;
  expect(outcome.retryable).toBe(true);
});

test("never marks ready when the workspace payload is incomplete", async () => {
  const outcome = await run(
    new AuthBootstrapRunner(
      deps({
        fetchOrganization: async () => ({ id: "org-1" }) as Organization,
      }),
    ),
  );
  expect(outcome.status).toBe("error");
  if (outcome.status !== "error") return;
  expect(outcome.retryable).toBe(false);
});

test("refuses a workspace that does not match the signed-in identity", async () => {
  const outcome = await run(
    new AuthBootstrapRunner(
      deps({
        fetchOrganization: async () =>
          ({ ...ORG, id: "org-other" }) as Organization,
      }),
    ),
  );
  expect(outcome.status).toBe("error");
  if (outcome.status !== "error") return;
  expect(outcome.retryable).toBe(false);
});

test("times out instead of hanging forever", async () => {
  const outcome = await run(
    new AuthBootstrapRunner(
      deps({
        timeoutMs: 50,
        fetchMe: (signal) => abortable(signal),
      }),
    ),
  );
  expect(outcome.status).toBe("error");
  if (outcome.status !== "error") return;
  expect(outcome.retryable).toBe(true);
});

test("accepts a slow response that still arrives before the deadline", async () => {
  const outcome = await run(
    new AuthBootstrapRunner(
      deps({
        timeoutMs: 500,
        fetchMe: (signal) =>
          new Promise((resolve, reject) => {
            const timer = setTimeout(() => resolve(USER), 40);
            signal.addEventListener("abort", () => {
              clearTimeout(timer);
              reject(
                Object.assign(new Error("aborted"), { name: "AbortError" }),
              );
            });
          }),
      }),
    ),
  );
  expect(outcome.status).toBe("authenticated");
});

test("shares one in-flight run between concurrent starts", async () => {
  let meCalls = 0;
  const runner = new AuthBootstrapRunner(
    deps({
      fetchMe: async () => {
        meCalls += 1;
        await new Promise((resolve) => setTimeout(resolve, 10));
        return USER;
      },
    }),
  );
  const first = runner.start();
  const second = runner.start();
  expect(second.generation).toBe(first.generation);
  const [a, b] = await Promise.all([first.outcome, second.outcome]);
  expect(a.status).toBe("authenticated");
  expect(b.status).toBe("authenticated");
  expect(meCalls).toBe(1);
});

test("cancellation makes the old generation stale", async () => {
  const runner = new AuthBootstrapRunner(
    deps({
      fetchMe: (signal) => abortable(signal),
    }),
  );
  const handle = runner.start();
  expect(runner.isCurrent(handle.generation)).toBe(true);
  runner.cancel();
  expect(runner.isCurrent(handle.generation)).toBe(false);
  const outcome = await handle.outcome;
  expect(outcome.status).toBe("error");
});

test("restart after cancellation performs a fresh run", async () => {
  let calls = 0;
  const runner = new AuthBootstrapRunner(
    deps({
      fetchMe: async () => {
        calls += 1;
        return USER;
      },
    }),
  );
  const first = runner.start();
  runner.cancel();
  await first.outcome;
  const second = runner.restart();
  expect(second.generation).not.toBe(first.generation);
  const outcome = await second.outcome;
  expect(outcome.status).toBe("authenticated");
  expect(runner.isCurrent(second.generation)).toBe(true);
  expect(calls).toBe(2);
});
