"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";

export interface EntitlementData {
  key: string;
  entitlement_type: "limit" | "boolean" | "tier";
  value: string | null;
  numeric_value: number | null;
  boolean_value: boolean | null;
  source: string;
  override_reason: string | null;
  override_by: string | null;
  override_expires_at: string | null;
  effective_from: string;
  effective_to: string | null;
}

export interface EntitlementCheckResult {
  allowed: boolean;
  reason: string | null;
  entitlement: EntitlementData | null;
  current: number | null;
  required: number | null;
  limit: number | null;
  usage: number | null;
  percentage: number | null;
  remaining: number | null;
}

export function useEntitlements() {
  const { organization } = useAuth();
  const [entitlements, setEntitlements] = useState<
    Record<string, EntitlementData>
  >({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    const fetchEntitlements = async () => {
      if (!organization?.id) return;

      try {
        setLoading(true);
        const data = await api<Record<string, EntitlementData>>(
          "/commercial/entitlements",
        );
        if (active) {
          setEntitlements(data);
          setError(null);
        }
      } catch (err) {
        if (active) {
          setError(
            err instanceof Error ? err.message : "Failed to fetch entitlements",
          );
        }
      } finally {
        if (active) setLoading(false);
      }
    };

    fetchEntitlements();

    return () => {
      active = false;
    };
  }, [organization?.id]);

  const checkEntitlement = async (
    key: string,
    required: any = true,
  ): Promise<EntitlementCheckResult> => {
    if (!organization?.id) {
      return {
        allowed: false,
        reason: "No organization",
        entitlement: null,
        current: null,
        required: null,
        limit: null,
        usage: null,
        percentage: null,
        remaining: null,
      };
    }

    try {
      const result = await api<EntitlementCheckResult>(
        "/commercial/entitlements/check",
        {
          method: "POST",
          body: { key, required },
        },
      );
      return result;
    } catch (err) {
      return {
        allowed: false,
        reason: err instanceof Error ? err.message : "Check failed",
        entitlement: null,
        current: null,
        required: null,
        limit: null,
        usage: null,
        percentage: null,
        remaining: null,
      };
    }
  };

  const checkLimit = async (
    key: string,
    currentUsage: number,
  ): Promise<EntitlementCheckResult> => {
    if (!organization?.id) {
      return {
        allowed: false,
        reason: "No organization",
        entitlement: null,
        current: null,
        required: null,
        limit: null,
        usage: null,
        percentage: null,
        remaining: null,
      };
    }

    try {
      const result = await api<EntitlementCheckResult>(
        "/commercial/entitlements/limit-check",
        {
          method: "POST",
          body: { key, current_usage: currentUsage },
        },
      );
      return result;
    } catch (err) {
      return {
        allowed: false,
        reason: err instanceof Error ? err.message : "Check failed",
        entitlement: null,
        current: null,
        required: null,
        limit: null,
        usage: null,
        percentage: null,
        remaining: null,
      };
    }
  };

  const getEntitlement = (key: string): EntitlementData | null => {
    return entitlements[key] || null;
  };

  const hasEntitlement = (key: string): boolean => {
    const ent = entitlements[key];
    if (!ent) return false;

    if (ent.entitlement_type === "boolean") {
      return ent.boolean_value === true;
    }
    if (ent.entitlement_type === "limit") {
      return (ent.numeric_value ?? 0) > 0;
    }
    if (ent.entitlement_type === "tier") {
      return ent.value !== null;
    }
    return true;
  };

  const getEntitlementLimit = (key: string): number | null => {
    const ent = entitlements[key];
    if (!ent || ent.entitlement_type !== "limit") return null;
    return ent.numeric_value;
  };

  const getEntitlementValue = <T,>(key: string): T | null => {
    const ent = entitlements[key];
    if (!ent) return null;

    if (ent.entitlement_type === "boolean") {
      return ent.boolean_value as T;
    }
    if (ent.entitlement_type === "limit") {
      return ent.numeric_value as T;
    }
    if (ent.entitlement_type === "tier") {
      return ent.value as T;
    }
    return null;
  };

  return {
    entitlements,
    loading,
    error,
    checkEntitlement,
    checkLimit,
    getEntitlement,
    hasEntitlement,
    getEntitlementLimit,
    getEntitlementValue,
  };
}

/**
 * Component that conditionally renders children based on entitlement check.
 *
 * Usage:
 * <EntitlementGate entitlementKey="projects:max" required={5} fallback={<div>Upgrade to create more projects</div>}>
 *   <CreateProjectButton />
 * </EntitlementGate>
 */
export function EntitlementGate({
  entitlementKey,
  required = true,
  children,
  fallback = null,
  loadingFallback = null,
}: {
  entitlementKey: string;
  required?: any;
  children: React.ReactNode;
  fallback?: React.ReactNode;
  loadingFallback?: React.ReactNode;
}) {
  const { hasEntitlement, loading, checkEntitlement } = useEntitlements();
  const [allowed, setAllowed] = useState<boolean | null>(null);

  useEffect(() => {
    let active = true;

    if (!loading) {
      const has = hasEntitlement(entitlementKey);
      if (active) setAllowed(has);
    } else {
      // Async check for complex required values
      checkEntitlement(entitlementKey, required).then((result) => {
        if (active) setAllowed(result.allowed);
      });
    }

    return () => {
      active = false;
    };
  }, [entitlementKey, required, loading, hasEntitlement, checkEntitlement]);

  if (loading && allowed === null) {
    return (
      loadingFallback ?? (
        <div className="animate-pulse h-8 w-32 bg-muted rounded" />
      )
    );
  }

  if (allowed === false) {
    return fallback ?? null;
  }

  return <>{children}</>;
}

/**
 * Hook for checking a specific entitlement limit with real-time updates.
 */
export function useEntitlementLimit(key: string, currentUsage: number) {
  const { checkLimit, loading } = useEntitlements();
  const [result, setResult] = useState<EntitlementCheckResult | null>(null);

  useEffect(() => {
    let active = true;

    if (currentUsage >= 0) {
      checkLimit(key, currentUsage).then((r) => {
        if (active) setResult(r);
      });
    }

    return () => {
      active = false;
    };
  }, [key, currentUsage, checkLimit]);

  return { result, loading };
}
