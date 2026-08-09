"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { useRouter } from "next/navigation";

import {
  api,
  apiUrl,
  ApiError,
  isAuthenticated,
  logout as apiLogout,
  tokenStore,
} from "@/lib/api";
import type { Organization, PlatformInfo, User } from "@/types";

interface AuthContextValue {
  user: User | null;
  organization: Organization | null;
  platform: PlatformInfo | null;
  loading: boolean;
  ready: boolean;
  authFailed: boolean;
  refreshProfile: () => Promise<void>;
  logout: (allDevices?: boolean) => Promise<void>;
  can: (permission: string) => boolean;
  updateUser: (user: User) => void;
  updateOrganization: (org: Organization) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

// A browser request drop can persist for the whole lifetime of a page (the
// network stack to the API host stays wedged for 10s+ while the shell sits on
// the spinner). In-page retries alone cannot beat that window, so the
// bootstrap escalates to a full page reload — a fresh document and network
// stack. sessionStorage keeps the counter across reloads to cap the loop.
const BOOT_RELOAD_KEY = "vcos.bootReloads";
const MAX_BOOT_RELOADS = 2;

function bootReloads(): number {
  if (typeof window === "undefined") return 0;
  return Number(window.sessionStorage.getItem(BOOT_RELOAD_KEY) || 0);
}
function markBootReload(): void {
  window.sessionStorage.setItem(BOOT_RELOAD_KEY, String(bootReloads() + 1));
}
function resetBootReloads(): void {
  window.sessionStorage.removeItem(BOOT_RELOAD_KEY);
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [organization, setOrganization] = useState<Organization | null>(null);
  const [platform, setPlatform] = useState<PlatformInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [authFailed, setAuthFailed] = useState(false);

  // Single-flight: React StrictMode double-mounts effects in dev, which would
  // otherwise fire two concurrent bootstrap trios (6 parallel requests). Under
  // load the browser cancels one trio before sending; a Promise.all reject in
  // that case used to wipe a perfectly valid session (tokenStore.clear()) and
  // leave the app shell stuck on "Opening your company" forever.
  let profilePromise: Promise<void> | null = null;

  // Sequential critical path: each request fires alone so a browser burst can
  // only drop one of them, and /auth/me then /organizations/me are both
  // required — a drop of either throws so the bootstrap effect retries.
  // /platform is best-effort and never blocks the shell.
  const refreshProfile = useCallback(async () => {
    if (!profilePromise) {
      profilePromise = (async () => {
        const me = await api<User>("/auth/me");
        setUser(me);
        tokenStore.setUser(me);
        const org = await api<Organization>("/organizations/me");
        setOrganization(org);
        tokenStore.setOrg(org);
        try {
          const info = await api<PlatformInfo>("/platform", { auth: false });
          setPlatform(info);
        } catch {
          /* best-effort */
        }
      })();
    }
    try {
      await profilePromise;
    } finally {
      profilePromise = null;
    }
  }, []);

  useEffect(() => {
    let active = true;
    (async () => {
      if (!isAuthenticated()) {
        if (active) setLoading(false);
        return;
      }
      // Transient failures (browser-cancelled or hung requests during
      // navigation bursts) are retried in the background. The shell keeps
      // showing the spinner instead of redirecting to /login with a perfectly
      // valid session — only a genuine 401 marks the session dead. After
      // several consecutive drops the network stack to the API host is likely
      // wedged for this page, so escalate to a full reload.
      let transientFailures = 0;
      while (active) {
        try {
          await refreshProfile();
          resetBootReloads();
          if (active) setLoading(false);
          return;
        } catch (err) {
          if (err instanceof ApiError && err.status === 401) {
            tokenStore.clear();
            if (active) {
              setLoading(false);
              setAuthFailed(true);
            }
            return;
          }
          transientFailures += 1;
          if (transientFailures >= 3 && bootReloads() < MAX_BOOT_RELOADS) {
            markBootReload();
            window.location.reload();
            return;
          }
          await new Promise((resolve) => setTimeout(resolve, 400));
        }
      }
    })();
    return () => {
      active = false;
    };
  }, [refreshProfile]);

  const logout = useCallback(
    async (allDevices = false) => {
      try {
        await apiLogout(allDevices);
      } finally {
        setUser(null);
        setOrganization(null);
        router.replace("/login");
      }
    },
    [router]
  );

  const can = useCallback(
    (permission: string) => {
      if (!user) return false;
      if (!Array.isArray(user.permissions) || user.permissions.length === 0) {
        return user.role === "ceo" || user.role === "admin";
      }
      return user.permissions.includes(permission);
    },
    [user]
  );

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      organization,
      platform,
      loading,
      ready: Boolean(user && organization),
      authFailed,
      refreshProfile,
      logout,
      can,
      updateUser: setUser,
      updateOrganization: setOrganization,
    }),
    [user, organization, platform, loading, authFailed, refreshProfile, logout, can]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider");
  return context;
}

export { apiUrl };
