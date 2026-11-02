import type {
  CompanyExperienceProfile,
  Organization,
  PlatformInfo,
  SuggestedProfileOut,
  User,
} from "../types";

export type AuthStatus =
  | "initializing"
  | "authenticated"
  | "unauthenticated"
  | "organization_unavailable"
  | "error";

export type AuthOutcome =
  | {
      status: "authenticated";
      user: User;
      organization: Organization;
      platform: PlatformInfo | null;
      experienceProfile: CompanyExperienceProfile | null;
    }
  | { status: "unauthenticated"; reason: "no_session" | "rejected" }
  | { status: "organization_unavailable"; message: string; user: User | null }
  | { status: "error"; message: string; retryable: boolean };

export interface AuthRunDeps {
  hasSession(): boolean;
  fetchMe(signal: AbortSignal): Promise<User>;
  fetchOrganization(signal: AbortSignal): Promise<Organization>;
  fetchExperienceProfile?(signal: AbortSignal): Promise<SuggestedProfileOut>;
  fetchPlatform?(signal: AbortSignal): Promise<PlatformInfo>;
  log?(event: string, detail?: Record<string, unknown>): void;
  timeoutMs?: number;
  maxAttempts?: number;
  retryDelayMs?: number;
  sleep?(ms: number): Promise<void>;
}

export interface AuthRunHandle {
  generation: number;
  outcome: Promise<AuthOutcome>;
}

const DEFAULT_TIMEOUT_MS = 25_000;
const DEFAULT_MAX_ATTEMPTS = 3;
const DEFAULT_RETRY_DELAY_MS = 500;
const OPTIONAL_TIMEOUT_MS = 2_500;

type FetchStage = "identity" | "organization";

class StageError extends Error {
  constructor(
    readonly stage: FetchStage,
    readonly cause: unknown,
    readonly partialUser: User | null,
  ) {
    super("Authentication request failed");
  }
}

class ShapeError extends Error {}
class TenantMismatchError extends Error {}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isUser(value: unknown): value is User {
  return (
    isRecord(value) &&
    typeof value.id === "string" &&
    typeof value.organization_id === "string" &&
    typeof value.email === "string"
  );
}

function isOrganization(value: unknown): value is Organization {
  return (
    isRecord(value) &&
    typeof value.id === "string" &&
    typeof value.name === "string"
  );
}

function httpStatus(error: unknown): number | null {
  const root = error instanceof StageError ? error.cause : error;
  if (isRecord(root) && typeof root.status === "number") return root.status;
  return null;
}

function isAbort(error: unknown): boolean {
  return isRecord(error) && error.name === "AbortError";
}

function isTransient(error: unknown): boolean {
  if (error instanceof ShapeError || error instanceof TenantMismatchError)
    return false;
  const status = httpStatus(error);
  if (status !== null) return status >= 500 || status === 408 || status === 429;
  return true;
}

function describeTransientFailure(timedOut: boolean): string {
  return timedOut
    ? "Opening your company took too long. Check your connection and try again."
    : "We couldn't reach your company workspace. Check your connection and try again.";
}

async function optionalFetch<T>(
  parent: AbortSignal,
  fn: ((signal: AbortSignal) => Promise<T>) | undefined,
): Promise<T | null> {
  if (!fn || parent.aborted) return null;
  const controller = new AbortController();
  const forwardAbort = () => controller.abort();
  parent.addEventListener("abort", forwardAbort, { once: true });
  const timer = setTimeout(() => controller.abort(), OPTIONAL_TIMEOUT_MS);
  try {
    return await fn(controller.signal);
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
    parent.removeEventListener("abort", forwardAbort);
  }
}

interface AttemptResult {
  user: User;
  organization: Organization;
  platform: PlatformInfo | null;
  experienceProfile: CompanyExperienceProfile | null;
}

async function runAttempt(
  deps: AuthRunDeps,
  signal: AbortSignal,
): Promise<AttemptResult> {
  const meStarted = Date.now();
  let user: User;
  try {
    user = await deps.fetchMe(signal);
    deps.log?.("me.ok", { ms: Date.now() - meStarted });
  } catch (error) {
    deps.log?.("me.fail", {
      ms: Date.now() - meStarted,
      status: httpStatus(error),
      aborted: isAbort(error),
    });
    throw new StageError("identity", error, null);
  }
  if (!isUser(user))
    throw new ShapeError("Your identity response was incomplete.");

  const orgStarted = Date.now();
  let organization: Organization;
  try {
    organization = await deps.fetchOrganization(signal);
    deps.log?.("organization.ok", { ms: Date.now() - orgStarted });
  } catch (error) {
    deps.log?.("organization.fail", {
      ms: Date.now() - orgStarted,
      status: httpStatus(error),
      aborted: isAbort(error),
    });
    throw new StageError("organization", error, user);
  }
  if (!isOrganization(organization)) {
    throw new ShapeError("Your company workspace response was incomplete.");
  }
  if (organization.id !== user.organization_id) {
    throw new TenantMismatchError(
      "Session organization does not match the loaded workspace.",
    );
  }

  const [experience, platform] = await Promise.all([
    optionalFetch(signal, deps.fetchExperienceProfile),
    optionalFetch(signal, deps.fetchPlatform),
  ]);

  const profile =
    experience && typeof experience.current_profile === "string"
      ? (experience.current_profile as CompanyExperienceProfile)
      : (organization.experience_profile ?? null);

  return {
    user,
    organization,
    platform: platform ?? null,
    experienceProfile: profile,
  };
}

export class AuthBootstrapRunner {
  private generation = 0;
  private active: {
    generation: number;
    controller: AbortController;
    outcome: Promise<AuthOutcome>;
  } | null = null;

  constructor(private readonly deps: AuthRunDeps) {}

  isCurrent(generation: number): boolean {
    return generation === this.generation;
  }

  start(): AuthRunHandle {
    if (this.active) {
      return {
        generation: this.active.generation,
        outcome: this.active.outcome,
      };
    }
    const generation = ++this.generation;
    const controller = new AbortController();
    const outcome = this.run(generation, controller).finally(() => {
      if (this.active?.generation === generation) this.active = null;
    });
    this.active = { generation, controller, outcome };
    return { generation, outcome };
  }

  restart(): AuthRunHandle {
    this.cancel();
    return this.start();
  }

  cancel(): void {
    this.generation += 1;
    this.active?.controller.abort();
    this.active = null;
  }

  private async run(
    generation: number,
    controller: AbortController,
  ): Promise<AuthOutcome> {
    const timeoutMs = this.deps.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    const maxAttempts = Math.max(
      1,
      this.deps.maxAttempts ?? DEFAULT_MAX_ATTEMPTS,
    );
    const retryDelayMs = this.deps.retryDelayMs ?? DEFAULT_RETRY_DELAY_MS;
    const sleep =
      this.deps.sleep ??
      ((ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms)));
    const deadline = Date.now() + timeoutMs;

    this.deps.log?.("bootstrap.start", { generation, timeoutMs, maxAttempts });

    if (!this.deps.hasSession()) {
      this.deps.log?.("bootstrap.end", {
        generation,
        status: "unauthenticated",
        reason: "no_session",
      });
      return { status: "unauthenticated", reason: "no_session" };
    }

    let lastTimedOut = false;

    for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
      if (controller.signal.aborted) {
        return {
          status: "error",
          message: "Authentication check was cancelled.",
          retryable: true,
        };
      }
      const remaining = deadline - Date.now();
      if (remaining <= 0) {
        lastTimedOut = true;
        break;
      }

      const attemptController = new AbortController();
      const forwardAbort = () => attemptController.abort();
      controller.signal.addEventListener("abort", forwardAbort, { once: true });
      let timedOut = false;
      const timer = setTimeout(() => {
        timedOut = true;
        attemptController.abort();
      }, remaining);

      try {
        const result = await runAttempt(this.deps, attemptController.signal);
        this.deps.log?.("bootstrap.end", {
          generation,
          status: "authenticated",
          attempt,
        });
        return { status: "authenticated", ...result };
      } catch (error) {
        lastTimedOut = timedOut;
        const stage = error instanceof StageError ? error.stage : null;
        const status = httpStatus(error);
        this.deps.log?.("bootstrap.attempt_failed", {
          generation,
          attempt,
          stage,
          status,
          timedOut,
          aborted: isAbort(error),
        });

        if (controller.signal.aborted) {
          return {
            status: "error",
            message: "Authentication check was cancelled.",
            retryable: true,
          };
        }
        if (status === 401) {
          this.deps.log?.("bootstrap.end", {
            generation,
            status: "unauthenticated",
            reason: "rejected",
          });
          return { status: "unauthenticated", reason: "rejected" };
        }
        if (stage === "organization" && (status === 403 || status === 404)) {
          this.deps.log?.("bootstrap.end", {
            generation,
            status: "organization_unavailable",
            statusCode: status,
          });
          return {
            status: "organization_unavailable",
            message:
              "Your account is not linked to an active company workspace.",
            user: error instanceof StageError ? error.partialUser : null,
          };
        }
        if (error instanceof TenantMismatchError) {
          return {
            status: "error",
            message:
              "Your session does not match the company workspace. Sign in again.",
            retryable: false,
          };
        }
        if (error instanceof ShapeError) {
          return { status: "error", message: error.message, retryable: false };
        }
        if (!isTransient(error) && !timedOut) {
          return {
            status: "error",
            message:
              error instanceof Error && error.message
                ? error.message
                : "Unable to open your company workspace.",
            retryable: false,
          };
        }
        if (attempt >= maxAttempts) break;

        const wait = Math.min(
          retryDelayMs * attempt,
          Math.max(0, deadline - Date.now()),
        );
        if (wait <= 0) break;
        await sleep(wait);
      } finally {
        clearTimeout(timer);
        controller.signal.removeEventListener("abort", forwardAbort);
      }
    }

    if (Date.now() >= deadline) lastTimedOut = true;
    this.deps.log?.("bootstrap.end", {
      generation,
      status: "error",
      timedOut: lastTimedOut,
    });
    return {
      status: "error",
      message: describeTransientFailure(lastTimedOut),
      retryable: true,
    };
  }
}
