"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Home,
  LayoutGrid,
  ListTodo,
  Sun,
  Building2,
  Sparkles,
  Brain,
  Users,
  FolderKanban,
  Target,
  TrendingUp,
  FileText,
  CheckCircle2,
  AlertTriangle,
  Users as UsersIcon2,
  Plus,
  Search,
  Zap,
  DollarSign,
  HeartPulse,
  Target as TargetIcon,
  FileText as FileTextIcon,
  AlertTriangle as AlertTriangleIcon,
  Users as UsersIcon,
  DollarSign as DollarSignIcon,
  HeartPulse as HeartPulseIcon,
  ArrowRight,
  Zap as ZapIcon,
  Users as UsersIcon3,
  Building2 as Building2Icon,
  Sparkles as SparklesIcon,
  ChevronDown,
  ChevronUp,
  Loader2,
  Bell,
  Clock,
  BarChart2,
  Shield,
  Briefcase,
  Settings,
  Menu,
  X,
  RefreshCw,
  Activity,
  UserPlus,
} from "lucide-react";

import {
  api,
  getAdaptiveExperience,
  AdaptiveExperienceOut,
  RecommendedActionOut,
} from "@/lib/api";
import { DashboardSummary } from "@/types";
import { useAuth } from "@/hooks/useAuth";
import { useFetch } from "@/hooks/useFetch";
import { PageHeader, StatCard } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { Progress } from "@/components/ui/Progress";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { formatDate } from "@/lib/utils";
import { toastError, toastSuccess } from "@/components/ui/Toaster";

const ICON_MAP: Record<string, React.ComponentType<{ className?: string }>> = {
  Home,
  LayoutGrid,
  ListTodo,
  Sun,
  Building2,
  Sparkles,
  Brain,
  Users,
  FolderKanban,
  Target,
  TrendingUp,
  FileText,
  CheckCircle2,
  AlertTriangle,
  UsersIcon2,
  Plus,
  Search,
  Zap,
  DollarSign,
  HeartPulse,
  TargetIcon,
  FileTextIcon,
  AlertTriangleIcon,
  UsersIcon,
  DollarSignIcon,
  HeartPulseIcon,
  ZapIcon,
  UsersIcon3,
  Building2Icon,
  SparklesIcon,
  Bell,
  Clock,
  BarChart2,
  Shield,
  Briefcase,
  Settings,
};

const PROFILE_LABELS: Record<string, string> = {
  startup: "Startup",
  growing: "Growing",
  mid_market: "Mid-Market",
  large_enterprise: "Large Enterprise",
  global_enterprise: "Global Enterprise",
};

const PROFILE_DESCRIPTIONS: Record<string, string> = {
  startup: "Focused workspace for small teams",
  growing: "Expanded operational visibility",
  mid_market: "Cross-department coordination",
  large_enterprise: "Governed enterprise operations",
  global_enterprise: "Global multi-entity governance",
};

const PROFILE_BADGE_TONES: Record<
  string,
  "success" | "warning" | "danger" | "brand" | "neutral"
> = {
  startup: "success",
  growing: "brand",
  mid_market: "warning",
  large_enterprise: "danger",
  global_enterprise: "neutral",
};

interface AdaptiveHomePageState {
  loading: boolean;
  error: string | null;
  experience: AdaptiveExperienceOut | null;
}

function ModuleCard({
  module,
  onClick,
  badgeCount,
  badgeLabel,
}: {
  module: AdaptiveExperienceOut["navigation_groups"][0]["modules"][0];
  onClick: () => void;
  badgeCount?: number;
  badgeLabel?: string;
}) {
  const Icon = ICON_MAP[module.icon] || Home;

  return (
    <button
      onClick={onClick}
      className="flex flex-col gap-3 p-4 rounded-xl border border-line bg-canvas/50 hover:bg-brand/5 transition-colors text-left h-full"
    >
      <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-brand/10 text-brand">
        <Icon className="h-6 w-6" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between">
          <h3 className="font-medium text-ink truncate">{module.label}</h3>
          {badgeCount && badgeCount > 0 && (
            <Badge tone="brand" className="text-[10px]">
              {badgeLabel || badgeCount}
            </Badge>
          )}
        </div>
        <p className="mt-1 text-[12px] text-muted truncate">
          {module.description}
        </p>
        {module.progressive_disclosure && (
          <Badge tone="neutral" className="text-[10px] mt-2">
            Advanced
          </Badge>
        )}
      </div>
    </button>
  );
}

function NavigationGroup({
  group,
  onModuleClick,
}: {
  group: AdaptiveExperienceOut["navigation_groups"][0];
  onModuleClick: (
    module: AdaptiveExperienceOut["navigation_groups"][0]["modules"][0],
  ) => void;
}) {
  const [collapsed, setCollapsed] = useState(group.default_collapsed);

  if (!group.collapsible) {
    return (
      <div className="space-y-3">
        {group.modules.map((module) => (
          <ModuleCard
            key={module.key}
            module={module}
            onClick={() => onModuleClick(module)}
          />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="flex items-center justify-between w-full px-4 py-2 rounded-lg bg-brand/5 text-brand font-medium hover:bg-brand/10 transition-colors"
      >
        <span className="flex items-center gap-2">
          {collapsed ? (
            <ChevronDown className="h-4 w-4" />
          ) : (
            <ChevronUp className="h-4 w-4" />
          )}
          {group.label}
        </span>
        <span className="text-[12px] text-muted">
          {group.modules.length} modules
        </span>
      </button>
      {!collapsed && (
        <div className="space-y-2 ml-4 border-l border-line pl-3">
          {group.modules.map((module) => (
            <ModuleCard
              key={module.key}
              module={module}
              onClick={() => onModuleClick(module)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function QuickActionButton({
  action,
  onClick,
}: {
  action: RecommendedActionOut;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-3 p-4 rounded-xl border border-line bg-canvas/50 hover:bg-brand/5 transition-colors text-left"
    >
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-brand/10 text-brand">
        <Sparkles className="h-5 w-5" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="font-medium text-ink truncate">{action.label}</p>
        <p className="text-[12px] text-muted truncate">{action.target}</p>
      </div>
      <ArrowRight className="h-5 w-5 text-muted" />
    </button>
  );
}

function ProfileBadge({ profile }: { profile: string }) {
  return (
    <Badge tone={PROFILE_BADGE_TONES[profile] || "neutral"}>
      {PROFILE_LABELS[profile] || profile}
    </Badge>
  );
}

export function AdaptiveHomePage() {
  const router = useRouter();
  const { user, loading: authLoading } = useAuth();
  const ready = !authLoading;
  const [state, setState] = useState<AdaptiveHomePageState>({
    loading: true,
    error: null,
    experience: null,
  });
  const [selectedModule, setSelectedModule] = useState<
    AdaptiveExperienceOut["navigation_groups"][0]["modules"][0] | null
  >(null);

  // Define callbacks before early returns to avoid conditional hook calls
  const loadExperience = useCallback(async () => {
    if (!ready || !user?.organization_id) return;
    try {
      setState((prev) => ({ ...prev, loading: true, error: null }));
      const experience = await getAdaptiveExperience();
      setState({ loading: false, error: null, experience });
    } catch (err) {
      setState({
        loading: false,
        error:
          err instanceof Error
            ? err.message
            : "Failed to load adaptive experience",
        experience: null,
      });
    }
  }, [ready, user?.organization_id]);

  const handleModuleClick = useCallback(
    (module: AdaptiveExperienceOut["navigation_groups"][0]["modules"][0]) => {
      setSelectedModule(module);
      router.push(`/${module.key}`);
    },
    [router],
  );

  const handleQuickAction = useCallback(
    (action: RecommendedActionOut) => {
      if (action.action.startsWith("/")) {
        router.push(action.action);
      } else {
        console.log("Action:", action.action);
      }
    },
    [router],
  );

  // Also load dashboard summary for stats
  const { data: dashboard, loading: dashboardLoading } =
    useFetch<DashboardSummary>(
      ready && user?.organization_id ? "/dashboard/summary" : "",
    );

  const getModuleBadge = useCallback(
    (moduleKey: string) => {
      if (!dashboard) return { count: 0, label: undefined };
      switch (moduleKey) {
        case "notifications":
          return {
            count: dashboard.unread_notifications || 0,
            label: "unread",
          };
        case "invitations":
          return {
            count: dashboard.pending_invitations || 0,
            label: "pending",
          };
        default:
          return { count: 0, label: undefined };
      }
    },
    [dashboard],
  );

  useEffect(() => {
    loadExperience();
  }, [loadExperience]);

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner label="Loading..." />
      </div>
    );
  }

  if (state.loading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="h-8 bg-line rounded w-1/4" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-24 bg-line rounded" />
          ))}
        </div>
        <div className="grid gap-4 lg:grid-cols-3">
          <div className="h-64 bg-line rounded lg:col-span-2" />
          <div className="h-64 bg-line rounded" />
        </div>
      </div>
    );
  }

  if (state.error) {
    return (
      <ErrorState
        title="Could not load adaptive experience"
        message={state.error}
        onRetry={loadExperience}
      />
    );
  }

  if (!state.experience) {
    return (
      <EmptyState
        icon={Sparkles}
        title="No experience configuration"
        description="Your company's adaptive experience is being initialized."
      />
    );
  }

  const { experience } = state;
  const profile = experience.profile;

  return (
    <div className="space-y-6">
      {/* Profile Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight text-ink">
              {user?.organization_id ? `Organization ${user.organization_id}` : "VCOS"}
            </h1>
            <ProfileBadge profile={profile} />
          </div>
          <p className="mt-1 text-sm text-muted">
            {PROFILE_DESCRIPTIONS[profile] || "Adaptive experience"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            onClick={loadExperience}
            disabled={state.loading}
          >
            <RefreshCw
              className={`h-4 w-4 ${state.loading ? "animate-spin" : ""}`}
            />
            Refresh
          </Button>
        </div>
      </div>

      {/* Stats Row */}
      {dashboard && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-7">
          <StatCard
            label="Total Users"
            value={dashboard.total_users}
            icon={Users}
          />
          <StatCard
            label="Active Users"
            value={dashboard.active_users}
            icon={Users}
          />
          <StatCard
            label="My Open Tasks"
            value={dashboard.my_tasks_open_count}
            icon={ListTodo}
          />
          <StatCard
            label="Pending Decisions"
            value={dashboard.pending_decisions_count}
            icon={FileText}
          />
          <StatCard
            label="Pending Approvals"
            value={dashboard.pending_approvals_count}
            icon={CheckCircle2}
          />
          <StatCard
            label="Pending Invitations"
            value={dashboard.pending_invitations}
            icon={UserPlus}
          />
          <StatCard
            label="Active Sessions"
            value={dashboard.active_sessions}
            icon={Activity}
          />
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
        {/* Main Content */}
        <div className="space-y-6 lg:col-span-1">
          {/* Navigation & Modules */}
          <Card>
            <div className="border-b border-line px-5 py-4">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold text-ink">
                  Your Workspace
                </h2>
                <Badge
                  tone={experience.progressive_disclosure ? "brand" : "neutral"}
                >
                  {experience.progressive_disclosure
                    ? "Progressive Disclosure"
                    : "Full Navigation"}
                </Badge>
              </div>
            </div>
            <div className="p-5 space-y-4">
              {experience.navigation_groups.map((group) => (
                <NavigationGroup
                  key={group.key}
                  group={group}
                  onModuleClick={handleModuleClick}
                />
              ))}
            </div>
          </Card>

          {/* Quick Actions */}
          {experience.recommended_actions.length > 0 && (
            <Card>
              <div className="flex items-center justify-between border-b border-line px-5 py-4">
                <h2 className="text-sm font-semibold text-ink">
                  Recommended for You
                </h2>
                <span className="text-[12px] text-muted">
                  {experience.recommended_actions.length} actions
                </span>
              </div>
              <div className="grid gap-3 p-5 sm:grid-cols-2">
                {experience.recommended_actions
                  .slice(0, 6)
                  .map((action, idx) => (
                    <QuickActionButton
                      key={idx}
                      action={action}
                      onClick={() => handleQuickAction(action)}
                    />
                  ))}
              </div>
            </Card>
          )}

          {/* Company Brain Insights */}
          {experience.company_brain_insights.change_count > 0 && (
            <Card>
              <div className="flex items-center justify-between border-b border-line px-5 py-4">
                <h2 className="text-sm font-semibold text-ink flex items-center gap-2">
                  <Brain className="h-4 w-4 text-brand" /> Company Brain
                </h2>
                <Badge tone="neutral">
                  {experience.company_brain_insights.change_count} changes
                </Badge>
              </div>
              <div className="p-5">
                {experience.company_brain_insights.recent_changes.length > 0 ? (
                  <ul className="divide-y divide-line">
                    {experience.company_brain_insights.recent_changes
                      .slice(0, 5)
                      .map((change, idx) => (
                        <li key={idx} className="py-3">
                          <p className="font-medium text-ink">
                            {change.title || change.type || "Activity"}
                          </p>
                          <p className="text-sm text-muted">
                            {change.description || JSON.stringify(change)}
                          </p>
                          <p className="text-[12px] text-faint mt-1">
                            {formatDate(change.occurred_at || change.timestamp)}
                          </p>
                        </li>
                      ))}
                  </ul>
                ) : (
                  <p className="text-sm text-muted">No recent activity</p>
                )}
              </div>
            </Card>
          )}

          {/* Digital Twin Overlay */}
          {(experience.digital_twin_overlay.health_score > 0 ||
            experience.digital_twin_overlay.bottlenecks.length > 0) && (
            <Card>
              <div className="flex items-center justify-between border-b border-line px-5 py-4">
                <h2 className="text-sm font-semibold text-ink flex items-center gap-2">
                  <BarChart2 className="h-4 w-4 text-brand" /> Digital Twin
                </h2>
                <div className="flex items-center gap-2">
                  <Progress
                    value={Math.round(
                      experience.digital_twin_overlay.health_score * 100,
                    )}
                    className="w-32 h-2"
                  />
                  <span className="text-sm font-mono text-brand">
                    {Math.round(
                      experience.digital_twin_overlay.health_score * 100,
                    )}
                    %
                  </span>
                </div>
              </div>
              <div className="p-5 space-y-4">
                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <p className="text-sm text-muted">Health Score</p>
                    <p className="text-2xl font-bold text-ink">
                      {Math.round(
                        experience.digital_twin_overlay.health_score * 100,
                      )}
                      %
                    </p>
                  </div>
                  <div>
                    <p className="text-sm text-muted">Capacity Utilization</p>
                    <p className="text-2xl font-bold text-ink">
                      {Math.round(
                        experience.digital_twin_overlay.capacity_utilization *
                          100,
                      )}
                      %
                    </p>
                  </div>
                </div>
                {experience.digital_twin_overlay.bottlenecks.length > 0 && (
                  <div>
                    <p className="text-sm font-semibold text-ink mb-2">
                      Bottlenecks
                    </p>
                    <ul className="space-y-1">
                      {experience.digital_twin_overlay.bottlenecks
                        .slice(0, 3)
                        .map((bottleneck, idx) => (
                          <li
                            key={idx}
                            className="flex items-center gap-2 text-sm text-warning"
                          >
                            <AlertTriangle className="h-3.5 w-3.5" />
                            {bottleneck}
                          </li>
                        ))}
                    </ul>
                  </div>
                )}
                {experience.digital_twin_overlay.active_scenarios > 0 && (
                  <div>
                    <p className="text-sm font-semibold text-ink mb-2">
                      Active Scenarios
                    </p>
                    <Badge tone="brand">
                      {experience.digital_twin_overlay.active_scenarios} running
                    </Badge>
                  </div>
                )}
              </div>
            </Card>
          )}
        </div>

        {/* Sidebar */}
        <div className="space-y-6 lg:col-span-1">
          {/* Profile Info */}
          <Card>
            <div className="p-5 space-y-4">
              <div className="flex items-center gap-3">
                <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-brand/10 text-brand">
                  <Sparkles className="h-6 w-6" />
                </div>
                <div>
                  <h3 className="font-semibold text-ink">Experience Profile</h3>
                  <p className="text-sm text-muted">
                    {PROFILE_DESCRIPTIONS[profile]}
                  </p>
                </div>
              </div>
              <ProfileBadge profile={profile} />
              <div className="pt-2 border-t border-line space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-muted">Layout</span>
                  <span className="font-medium capitalize">
                    {experience.dashboard_layout}
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-muted">Navigation</span>
                  <span className="font-medium capitalize">
                    {experience.navigation_density}
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-muted">Advanced Features</span>
                  <span className="font-medium">
                    {experience.show_advanced_features ? "Enabled" : "Disabled"}
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-muted">Progressive Disclosure</span>
                  <span className="font-medium">
                    {experience.progressive_disclosure ? "On" : "Off"}
                  </span>
                </div>
              </div>
              <Button
                variant="secondary"
                className="w-full mt-2"
                onClick={() => router.push("/settings?tab=organization")}
              >
                <Settings className="h-4 w-4 mr-2" /> Configure Experience
              </Button>
            </div>
          </Card>

          {/* Visible Modules Quick Access */}
          <Card>
            <div className="border-b border-line px-5 py-4">
              <h2 className="text-sm font-semibold text-ink">
                Available Modules
              </h2>
            </div>
            <div className="p-5 space-y-2 max-h-[400px] overflow-y-auto">
              {experience.visible_modules.map((moduleKey) => {
                const moduleDef = experience.navigation_groups
                  .flatMap((g) => g.modules)
                  .find((m) => m.key === moduleKey);
                if (!moduleDef) return null;
                const badge = getModuleBadge(moduleKey);
                return (
                  <ModuleCard
                    key={moduleKey}
                    module={moduleDef}
                    onClick={() => handleModuleClick(moduleDef)}
                    badgeCount={badge.count}
                    badgeLabel={badge.label}
                  />
                );
              })}
            </div>
          </Card>

          {/* Feature Flags */}
          {Object.keys(experience.feature_flags).length > 0 && (
            <Card>
              <div className="border-b border-line px-5 py-4">
                <h2 className="text-sm font-semibold text-ink">
                  Feature Flags
                </h2>
              </div>
              <div className="p-5 space-y-2">
                {Object.entries(experience.feature_flags).map(
                  ([key, enabled]) => (
                    <div
                      key={key}
                      className="flex items-center justify-between"
                    >
                      <span className="text-sm text-ink capitalize">
                        {key.replace(/_/g, " ")}
                      </span>
                      <Badge tone={enabled ? "success" : "neutral"}>
                        {enabled ? "On" : "Off"}
                      </Badge>
                    </div>
                  ),
                )}
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
