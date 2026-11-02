"use client";

import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import { api, clearTokens, tokenStore } from '@/lib/api';

interface User {
  id: string;
  email: string;
  full_name: string;
  avatar_url?: string;
  avatar_color?: string;
  organization_id: string;
  role: string;
  permissions: string[];
  job_title?: string;
  phone?: string;
  timezone?: string;
  created_at?: string;
}

interface OrganizationContext {
  id: string;
  name: string;
  slug: string;
  industry?: string | null;
  description?: string | null;
  country?: string | null;
  timezone?: string | null;
  language?: string | null;
  currency?: string | null;
  domain?: string | null;
  brand_primary_color?: string | null;
}

interface AuthContextType {
  user: User | null;
  organization: OrganizationContext | null;
  accessToken: string | null;
  refreshToken: string | null;
  loading: boolean;
  ready: boolean;
  error: string | null;
  login: (email: string, password: string) => Promise<void>;
  register: (data: { email: string; password: string; full_name: string; organization_name: string; organization_slug: string }) => Promise<void>;
  logout: () => Promise<void>;
  refreshAuth: () => Promise<void>;
  refreshProfile: () => Promise<void>;
  clearError: () => void;
  retry: () => Promise<void>;
  hasRole: (role: string) => boolean;
  can: (permission: string) => boolean;
  updateOrganization: (org: OrganizationContext) => void;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  const refreshAuth = useCallback(async () => {
    const refresh = localStorage.getItem('refresh_token');
    if (!refresh) return;

    try {
      const data = await api<{ access_token: string; refresh_token: string }>('/auth/refresh', {
        method: 'POST',
        body: { refresh_token: refresh },
      });

      localStorage.setItem('access_token', data.access_token);
      localStorage.setItem('refresh_token', data.refresh_token);
      setAccessToken(data.access_token);
      setRefreshToken(data.refresh_token);
      
      // Fetch user info
      const userData = await api<{ user: User }>('/auth/me');
      localStorage.setItem('user', JSON.stringify(userData.user));
      setUser(userData.user);
      if (userData.user.organization_id) {
        setOrganization({
          id: userData.user.organization_id,
          name: userData.user.full_name,
          slug: userData.user.organization_id,
        });
      }
    } catch (error) {
      console.error('Token refresh failed:', error);
      logout();
    }
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    setError(null);
    const data = await api<{ access_token: string; refresh_token: string }>('/auth/login', {
      method: 'POST',
      body: { email, password },
    });

    localStorage.setItem('access_token', data.access_token);
    localStorage.setItem('refresh_token', data.refresh_token);
    setAccessToken(data.access_token);
    setRefreshToken(data.refresh_token);

    // Fetch user info
    const userData = await api<{ user: User }>('/auth/me');
    localStorage.setItem('user', JSON.stringify(userData.user));
    setUser(userData.user);
    if (userData.user.organization_id) {
      setOrganization({
        id: userData.user.organization_id,
        name: userData.user.full_name,
        slug: userData.user.organization_id,
      });
    }
  }, []);

  const register = useCallback(async (data: { email: string; password: string; full_name: string; organization_name: string; organization_slug: string }) => {
    setError(null);
    const result = await api<{ access_token: string; refresh_token: string }>('/auth/register', {
      method: 'POST',
      body: data,
    });

    localStorage.setItem('access_token', result.access_token);
    localStorage.setItem('refresh_token', result.refresh_token);
    setAccessToken(result.access_token);
    setRefreshToken(result.refresh_token);

    // Fetch user info
    const userData = await api<{ user: User }>('/auth/me');
    localStorage.setItem('user', JSON.stringify(userData.user));
    setUser(userData.user);
    if (userData.user.organization_id) {
      setOrganization({
        id: userData.user.organization_id,
        name: userData.user.full_name,
        slug: userData.user.organization_id,
      });
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      await api('/auth/logout', { method: 'POST' });
    } catch (error) {
      console.error('Logout error:', error);
    } finally {
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      localStorage.removeItem('user');
      clearTokens();
      setAccessToken(null);
      setRefreshToken(null);
      setUser(null);
      setOrganization(null);
    }
  }, []);

  // Initialize auth on mount
  useEffect(() => {
    const initAuth = async () => {
      const token = localStorage.getItem('access_token');
      const refresh = localStorage.getItem('refresh_token');
      const userStr = localStorage.getItem('user');

      if (token) {
        setAccessToken(token);
        if (refresh) setRefreshToken(refresh);
        if (userStr) {
          try {
            const userData = JSON.parse(userStr);
            setUser(userData);
            if (userData.organization_id) {
              setOrganization({
                id: userData.organization_id,
                name: userData.full_name,
                slug: userData.organization_id,
              });
            }
          } catch {
            localStorage.removeItem('user');
          }
        }
      }
      setLoading(false);
    };

    initAuth();
  }, []);

  const hasRole = useCallback((role: string) => {
    return user?.role === role;
  }, [user]);

  const can = useCallback((permission: string) => {
    return user?.permissions?.includes(permission) ?? false;
  }, [user]);

  const [organization, setOrganization] = useState<{
    id: string;
    name: string;
    slug: string;
    industry?: string;
    description?: string;
    country?: string;
    timezone?: string;
    language?: string;
    currency?: string;
    domain?: string;
    brand_primary_color?: string;
  } | null>(null);

  const ready = !loading;

  const updateOrganization = useCallback((org: { id: string; name: string; slug: string }) => {
    setOrganization(org);
  }, []);

  const value = {
    user,
    organization,
    accessToken,
    refreshToken,
    loading,
    ready,
    error,
    login,
    register,
    logout,
    refreshAuth,
    refreshProfile: refreshAuth,
    clearError,
    retry: refreshAuth,
    hasRole,
    can,
    updateOrganization,
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}