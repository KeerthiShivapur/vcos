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
  refreshProfile: () => Promise<void>;
  logout: (allDevices?: boolean) => Promise<void>;
  can: (permission: string) => boolean;
  updateUser: (user: User) => void;
  updateOrganization: (org: Organization) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [organization, setOrganization] = useState<Organization | null>(null);
  const [platform, setPlatform] = useState<PlatformInfo | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshProfile = useCallback(async () => {
    const [me, org, info] = await Promise.all([
      api<User>("/auth/me"),
      api<Organization>("/organizations/me"),
      api<PlatformInfo>("/platform", { auth: false }),
    ]);
    setUser(me);
    setOrganization(org);
    setPlatform(info);
    tokenStore.setUser(me);
    tokenStore.setOrg(org);
  }, []);

  useEffect(() => {
    let active = true;
    (async () => {
      if (!isAuthenticated()) {
        if (active) setLoading(false);
        return;
      }
      try {
        await refreshProfile();
      } catch {
        tokenStore.clear();
      } finally {
        if (active) setLoading(false);
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
      refreshProfile,
      logout,
      can,
      updateUser: setUser,
      updateOrganization: setOrganization,
    }),
    [user, organization, platform, loading, refreshProfile, logout, can]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider");
  return context;
}

export { apiUrl };
