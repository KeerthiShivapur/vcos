"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type {
  NavigationGroup,
  CompanyExperienceProfile,
  AdaptiveNavigationGroupOut,
  AdaptiveModuleOut,
} from "@/types";
import { useAuth } from "@/hooks/useAuth";

export interface AdaptiveExperienceData {
  navigationGroups: NavigationGroup[];
  visibleModules: string[];
  adaptiveGroups: AdaptiveNavigationGroupOut[];
  adaptiveModules: AdaptiveModuleOut[];
  profile: CompanyExperienceProfile;
  dashboardLayout: string;
  navigationDensity: string;
  progressiveDisclosure: boolean;
  showAdvancedFeatures: boolean;
  featureFlags: Record<string, boolean>;
  companyBrainInsights: {
    overview: Record<string, unknown>;
    recentChanges: Array<Record<string, unknown>>;
    changeCount: number;
  };
  digitalTwinOverlay: {
    healthScore: number;
    capacityUtilization: number;
    bottlenecks: string[];
    activeScenarios: number;
  };
  recommendedActions: Array<{
    type: string;
    label: string;
    action: string;
    target: string;
    priority: number;
    source: string;
  }>;
  contextFingerprint: string;
}

export function useAdaptiveNavigation() {
  const { organization, experienceProfile, loading: authLoading } = useAuth();
  const [navigationGroups, setNavigationGroups] = useState<NavigationGroup[]>(
    [],
  );
  const [visibleModules, setVisibleModules] = useState<string[]>([]);
  const [adaptiveGroups, setAdaptiveGroups] = useState<
    AdaptiveNavigationGroupOut[]
  >([]);
  const [adaptiveModules, setAdaptiveModules] = useState<AdaptiveModuleOut[]>(
    [],
  );
  const [profile, setProfile] = useState<CompanyExperienceProfile | null>(null);
  const [dashboardLayout, setDashboardLayout] = useState<string>("startup");
  const [navigationDensity, setNavigationDensity] =
    useState<string>("comfortable");
  const [progressiveDisclosure, setProgressiveDisclosure] =
    useState<boolean>(true);
  const [showAdvancedFeatures, setShowAdvancedFeatures] =
    useState<boolean>(false);
  const [featureFlags, setFeatureFlags] = useState<Record<string, boolean>>({});
  const [companyBrainInsights, setCompanyBrainInsights] = useState<
    AdaptiveExperienceData["companyBrainInsights"]
  >({
    overview: {},
    recentChanges: [],
    changeCount: 0,
  });
  const [digitalTwinOverlay, setDigitalTwinOverlay] = useState<
    AdaptiveExperienceData["digitalTwinOverlay"]
  >({
    healthScore: 0,
    capacityUtilization: 0,
    bottlenecks: [],
    activeScenarios: 0,
  });
  const [recommendedActions, setRecommendedActions] = useState<
    AdaptiveExperienceData["recommendedActions"]
  >([]);
  const [contextFingerprint, setContextFingerprint] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    const fetchAdaptiveExperience = async () => {
      if (!organization?.id || authLoading) return;

      try {
        setLoading(true);
        const data = await api<AdaptiveExperienceData>(
          "/company-experience/adaptive",
        );
        if (active) {
          // Convert adaptive groups to legacy NavigationGroup format for backward compatibility
          const legacyGroups: NavigationGroup[] = data.adaptiveGroups.map(
            (g) => ({
              key: g.key,
              label: g.label,
              items: g.modules.map((m) => m.key),
            }),
          );

          setNavigationGroups(legacyGroups);
          setVisibleModules(data.visibleModules);
          setAdaptiveGroups(data.adaptiveGroups);
          setAdaptiveModules(data.adaptiveModules.flat());
          setProfile(data.profile);
          setDashboardLayout(data.dashboardLayout);
          setNavigationDensity(data.navigationDensity);
          setProgressiveDisclosure(data.progressiveDisclosure);
          setShowAdvancedFeatures(data.showAdvancedFeatures);
          setFeatureFlags(data.featureFlags);
          setCompanyBrainInsights(data.companyBrainInsights);
          setDigitalTwinOverlay(data.digitalTwinOverlay);
          setRecommendedActions(data.recommendedActions);
          setContextFingerprint(data.contextFingerprint);
          setError(null);
        }
      } catch (err) {
        if (active) {
          setError(
            err instanceof Error
              ? err.message
              : "Failed to fetch adaptive experience",
          );
          // Fallback to default navigation based on experience profile
          setNavigationGroups(getDefaultNavigation(experienceProfile));
          setVisibleModules(getDefaultVisibleModules(experienceProfile));
        }
      } finally {
        if (active) setLoading(false);
      }
    };

    fetchAdaptiveExperience();

    return () => {
      active = false;
    };
  }, [organization?.id, experienceProfile, authLoading]);

  return {
    navigationGroups,
    visibleModules,
    adaptiveGroups,
    adaptiveModules,
    profile,
    dashboardLayout,
    navigationDensity,
    progressiveDisclosure,
    showAdvancedFeatures,
    featureFlags,
    companyBrainInsights,
    digitalTwinOverlay,
    recommendedActions,
    contextFingerprint,
    loading,
    error,
  };
}

function getDefaultNavigation(
  profile: CompanyExperienceProfile | null,
): NavigationGroup[] {
  const baseGroups: NavigationGroup[] = [
    {
      key: "workspace",
      label: "Workspace",
      items: ["home", "workspace", "my-work", "my-day"],
    },
    {
      key: "ai",
      label: "AI",
      items: ["ai", "company-brain"],
    },
  ];

  if (!profile || profile === "startup") {
    return baseGroups;
  }

  if (profile === "growing" || profile === "mid_market") {
    return [
      ...baseGroups,
      {
        key: "people",
        label: "People",
        items: ["people", "departments", "teams", "roles"],
      },
      {
        key: "work",
        label: "Work",
        items: ["projects", "tasks", "goals", "approvals"],
      },
      {
        key: "knowledge",
        label: "Knowledge",
        items: ["knowledge", "wiki", "documents", "decisions"],
      },
    ];
  }

  if (profile === "large_enterprise") {
    return [
      ...baseGroups,
      {
        key: "people",
        label: "People",
        items: ["people", "departments", "teams", "roles"],
      },
      {
        key: "work",
        label: "Work",
        items: ["projects", "tasks", "goals", "approvals"],
      },
      {
        key: "customers",
        label: "Customers",
        items: ["customers", "crm", "contracts"],
      },
      {
        key: "finance",
        label: "Finance",
        items: ["finance", "budgets", "expenses", "procurement"],
      },
      {
        key: "hr",
        label: "HR",
        items: ["hr", "hiring", "performance", "learning", "payroll"],
      },
      {
        key: "intelligence",
        label: "Intelligence",
        items: ["brain", "insights", "patterns", "twin"],
      },
      {
        key: "knowledge",
        label: "Knowledge",
        items: ["knowledge", "wiki", "documents", "decisions"],
      },
      {
        key: "governance",
        label: "Governance",
        items: ["governance", "approvals", "decisions", "compliance"],
      },
    ];
  }

  // global_enterprise
  return [
    ...baseGroups,
    {
      key: "people",
      label: "People",
      items: ["people", "departments", "teams", "roles"],
    },
    {
      key: "work",
      label: "Work",
      items: ["projects", "tasks", "goals", "approvals"],
    },
    {
      key: "customers",
      label: "Customers",
      items: ["customers", "crm", "contracts"],
    },
    {
      key: "finance",
      label: "Finance",
      items: ["finance", "budgets", "expenses", "procurement"],
    },
    {
      key: "hr",
      label: "HR",
      items: ["hr", "hiring", "performance", "learning", "payroll"],
    },
    {
      key: "intelligence",
      label: "Intelligence",
      items: ["brain", "insights", "patterns", "twin"],
    },
    {
      key: "knowledge",
      label: "Knowledge",
      items: ["knowledge", "wiki", "documents", "decisions"],
    },
    {
      key: "governance",
      label: "Governance",
      items: ["governance", "approvals", "decisions", "compliance"],
    },
    {
      key: "platform",
      label: "Platform",
      items: ["enterprise", "integrations", "api", "security", "compliance"],
    },
    {
      key: "admin",
      label: "Admin",
      items: ["settings", "users", "roles", "audit", "feature-flags"],
    },
  ];
}

function getDefaultVisibleModules(
  profile: CompanyExperienceProfile | null,
): string[] {
  if (!profile || profile === "startup") {
    return ["home", "workspace", "my-work", "my-day", "company-home", "ai"];
  }

  if (profile === "growing" || profile === "mid_market") {
    return [
      "home",
      "workspace",
      "my-work",
      "my-day",
      "company-home",
      "ai",
      "projects",
      "tasks",
      "goals",
      "departments",
      "teams",
      "people",
      "decisions",
      "approvals",
      "knowledge",
      "wiki",
      "documents",
    ];
  }

  // large_enterprise and global_enterprise
  return ["all"];
}
