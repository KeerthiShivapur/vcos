"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useRouter } from "next/navigation";

import {
  api,
  apiUrl,
  isAuthenticated,
  logout as apiLogout,
  tokenStore,
} from "@/lib/api";
import {
  AuthBootstrapRunner,
  type AuthOutcome,
  type AuthStatus,
} from "@/lib/auth-bootstrap";
import type {
  Organization,
  PlatformInfo,
  User,
  CompanyExperienceProfile,
  SuggestedProfileOut,
} from "@/types";

interface AuthContextValue {
  user: User | null;
  organization: Organization | null;
  platform: PlatformInfo | null;
  loading: boolean;
  ready: boolean;
  status: AuthStatus;
  authFailed: boolean;
  authError: string | null;
  refreshProfile: () => Promise<AuthStatus>;
  retry: () => Promise<void>;
  logout: (allDevices?: boolean) => Promise<void>;
  can: (permission: string) => boolean;
  updateUser: (user: User) => void;
  updateOrganization: (org: Organization) => void;
  experienceProfile: CompanyExperienceProfile | null;
  setExperienceProfile: (profile: CompanyExperienceProfile) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const AUTH_DEBUG_ENABLED =
  process.env.NODE_ENV !== "production" ||
  process.env.NEXT_PUBLIC_AUTH_DEBUG === "1";

function authLog(event: string, detail?: Record<string, unknown>): void {
  if (!AUTH_DEBUG_ENABLED) return;
  console.debug(`[auth] ${event}`, detail ?? {});
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [organization, setOrganization] = useState<Organization | null>(null);
  const [platform, setPlatform] = useState<PlatformInfo | null>(null);
  const [experienceProfile, setExperienceProfile] =
    useState<CompanyExperienceProfile | null>(null);
  const [status, setStatus] = useState<AuthStatus>("initializing");
  const [authFailed, setAuthFailed] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const statusRef = useRef<AuthStatus>("initializing");

  const updateStatus = useCallback((next: AuthStatus) => {
    statusRef.current = next;
    setStatus(next);
  }, []);

  const runner = useMemo(
    () =>
      new AuthBootstrapRunner({
        hasSession: () => isAuthenticated(),
        fetchMe: (signal) => api<User>("/auth/me", { signal }),
        fetchOrganization: (signal) =>
          api<Organization>("/organizations/me", { signal }),
        fetchExperienceProfile: (signal) =>
          api<SuggestedProfileOut>("/company-experience/profile", { signal }),
        fetchPlatform: (signal) =>
          api<PlatformInfo>("/platform", { auth: false, signal }),
        log: authLog,
      }),
    [],
  );

  const applyOutcome = useCallback(
    (outcome: AuthOutcome) => {
      authLog("state.apply", { status: outcome.status });
      switch (outcome.status) {
        case "authenticated":
          tokenStore.setUser(outcome.user);
          tokenStore.setOrg(outcome.organization);
          setUser(outcome.user);
          setOrganization(outcome.organization);
          setPlatform(outcome.platform);
          setExperienceProfile(outcome.experienceProfile);
          setAuthError(null);
          setAuthFailed(false);
          updateStatus("authenticated");
          break;
        case "unauthenticated":
          tokenStore.clear();
          setUser(null);
          setOrganization(null);
          setPlatform(null);
          setExperienceProfile(null);
          setAuthError(null);
          setAuthFailed(outcome.reason === "rejected");
          updateStatus("unauthenticated");
          break;
        case "organization_unavailable":
          setUser(outcome.user);
          setOrganization(null);
          setPlatform(null);
          setExperienceProfile(null);
          setAuthFailed(false);
          setAuthError(outcome.message);
          updateStatus("organization_unavailable");
          break;
        case "error":
          if (statusRef.current === "authenticated") {
            authLog("refresh.error", { message: outcome.message });
            return;
          }
          setAuthFailed(false);
          setAuthError(outcome.message);
          updateStatus("error");
          break;
      }
    },
    [updateStatus],
  );

  useEffect(() => {
    let disposed = false;
    const handle = runner.start();
    handle.outcome.then((outcome) => {
      if (disposed || !runner.isCurrent(handle.generation)) return;
      applyOutcome(outcome);
    });
    return () => {
      disposed = true;
      runner.cancel();
    };
  }, [runner, applyOutcome]);

  const refreshProfile = useCallback(async (): Promise<AuthStatus> => {
    const handle = runner.restart();
    const outcome = await handle.outcome;
    if (!runner.isCurrent(handle.generation)) return statusRef.current;
    applyOutcome(outcome);
    return outcome.status;
  }, [runner, applyOutcome]);

  const retry = useCallback(async () => {
    authLog("bootstrap.retry");
    setAuthError(null);
    updateStatus("initializing");
    await refreshProfile();
  }, [refreshProfile, updateStatus]);

  const logout = useCallback(
    async (allDevices = false) => {
      runner.cancel();
      try {
        await apiLogout(allDevices);
      } finally {
        tokenStore.clear();
        setUser(null);
        setOrganization(null);
        setPlatform(null);
        setExperienceProfile(null);
        setAuthFailed(false);
        setAuthError(null);
        updateStatus("unauthenticated");
        router.replace("/login");
      }
    },
    [router, runner, updateStatus],
  );

  const can = useCallback(
    (permission: string) => {
      if (!user) return false;
      if (!Array.isArray(user.permissions) || user.permissions.length === 0) {
        return user.role === "ceo" || user.role === "admin";
      }
      return user.permissions.includes(permission);
    },
    [user],
  );

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      organization,
      platform,
      loading: status === "initializing",
      ready: status === "authenticated",
      status,
      authFailed,
      authError,
      refreshProfile,
      retry,
      logout,
      can,
      updateUser: setUser,
      updateOrganization: setOrganization,
      experienceProfile,
      setExperienceProfile,
    }),
    [
      user,
      organization,
      platform,
      status,
      authFailed,
      authError,
      refreshProfile,
      retry,
      logout,
      can,
      experienceProfile,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider");
  return context;
}

export { apiUrl };
