"use client";

import { Suspense, useEffect, useState, useCallback, useRef } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  Building2,
  Check,
  ChevronRight,
  Cloud,
  Key,
  MessageSquare,
  Plus,
  Shield,
  Sparkles,
  Ticket,
  Truck,
  Users,
  UserPlus,
  Zap,
  X,
  AlertCircle,
  Loader2,
  Clock,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  RotateCcw,
} from "lucide-react";

import { api } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { Stepper } from "@/components/ui/Stepper";
import { formatDate } from "@/lib/utils";
import { toastError, toastSuccess } from "@/components/ui/Toaster";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Progress } from "@/components/ui/Progress";
import { Tabs } from "@/components/ui/Tabs";

type OnboardingStep =
  | "welcome"
  | "profile"
  | "company"
  | "team"
  | "integrations"
  | "provisioning"
  | "complete";

interface ProvisioningStepProgress {
  step: string;
  state: "not_started" | "pending" | "running" | "completed" | "failed";
  name: string;
  description: string;
  required: boolean;
  recoverable: boolean;
  started_at?: string;
  completed_at?: string;
  error?: string;
}

interface ProvisioningProgress {
  provisioning_id: string;
  state: string;
  current_step: string;
  current_step_name: string;
  steps: ProvisioningStepProgress[];
  current_phase: string;
  provisioning_progress: number;
  error?: string;
  completed_count: number;
  failed_count: number;
  running_count: number;
  total_steps: number;
}

interface OnboardingState {
  step: OnboardingStep;
  profile: {
    full_name: string;
    job_title: string;
    phone: string;
    timezone: string;
  };
  company: {
    name: string;
    industry: string;
    size: string;
    timezone: string;
  };
  team: {
    members: Array<{ email: string; name: string; role: string }>;
  };
  integrations: string[];
  completedSteps: OnboardingStep[];
  provisioningId: string | null;
  provisioningProgress: ProvisioningProgress | null;
  provisioningPolling: boolean;
}

const STEPS: OnboardingStep[] = [
  "welcome",
  "profile",
  "company",
  "team",
  "integrations",
  "provisioning",
  "complete",
];

const STEP_LABELS: Record<OnboardingStep, string> = {
  welcome: "Welcome",
  profile: "Profile",
  company: "Company",
  team: "Team",
  integrations: "Integrations",
  provisioning: "Provisioning",
  complete: "Complete",
};

const PROVISIONING_STORAGE_KEY = "vcos_onboarding_provisioning";

function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 100);
}

function StepCard({
  icon,
  title,
  description,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
}) {
  return (
    <div className="p-4 rounded-xl border border-line bg-canvas/50 text-center">
      <div className="mb-2 flex justify-center">{icon}</div>
      <h4 className="font-medium text-ink">{title}</h4>
      <p className="mt-1 text-sm text-muted">{description}</p>
    </div>
  );
}

function TeamMembersList({
  members,
  onChange,
}: {
  members: Array<{ email: string; name: string; role: string }>;
  onChange: (
    members: Array<{ email: string; name: string; role: string }>,
  ) => void;
}) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState("employee");

  const addMember = () => {
    if (!email) return;
    onChange([...members, { email, name, role }]);
    setEmail("");
    setName("");
    setRole("employee");
  };

  const removeMember = (index: number) => {
    onChange(members.filter((_, i) => i !== index));
  };

  return (
    <div className="space-y-4">
      <div className="space-y-3">
        <Input
          label="Email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="teammate@company.com"
          required
        />
        <Input
          label="Name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Grace Hopper"
        />
        <select
          className="input"
          value={role}
          onChange={(e) => setRole(e.target.value)}
        >
          <option value="employee">Employee</option>
          <option value="manager">Manager</option>
          <option value="admin">Admin</option>
        </select>
      </div>
      <Button onClick={addMember} disabled={!email} className="w-full">
        Add Member
      </Button>

      {members.length > 0 && (
        <ul className="divide-y divide-line mt-6">
          {members.map((member, index) => (
            <li key={index} className="flex items-center gap-3 px-5 py-3">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand/10 text-brand text-[12px] font-semibold">
                {member.name.slice(0, 1).toUpperCase()}
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium text-ink">
                  {member.name || "Unnamed"}
                </p>
                <p className="truncate text-[12px] text-muted">
                  {member.email} \u00b7 {member.role}
                </p>
              </div>
              <button
                onClick={() => removeMember(index)}
                className="text-danger hover:underline text-sm"
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function IntegrationCard({
  name,
  description,
  icon,
  connected,
  onToggle,
}: {
  name: string;
  description: string;
  icon: React.ReactNode;
  connected: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className={`flex items-center gap-3 p-4 rounded-xl border transition-colors ${
        connected
          ? "border-brand/50 bg-brand/5"
          : "border-line hover:bg-brand/5"
      }`}
    >
      <div
        className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-lg ${
          connected ? "bg-brand/10 text-brand" : "bg-canvas text-muted"
        }`}
      >
        {icon}
      </div>
      <div className="min-w-0 flex-1">
        <p className="font-medium text-ink">{name}</p>
        <p className="text-[12px] text-muted truncate">{description}</p>
      </div>
      <div className="flex items-center gap-2">
        {connected && <Badge tone="success">Connected</Badge>}
        <button
          type="button"
          onClick={onToggle}
          className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
            connected
              ? "bg-brand/10 text-brand hover:bg-brand/20"
              : "bg-brand text-white hover:bg-brand-strong"
          }`}
        >
          {connected ? "Disconnect" : "Connect"}
        </button>
      </div>
    </button>
  );
}

function ProvisioningStepRow({ step }: { step: ProvisioningStepProgress }) {
  const getStateIcon = () => {
    switch (step.state) {
      case "completed":
        return <CheckCircle2 className="h-4 w-4 text-success" />;
      case "running":
        return <Loader2 className="h-4 w-4 text-brand animate-spin" />;
      case "failed":
        return <AlertCircle className="h-4 w-4 text-danger" />;
      case "pending":
        return <Clock className="h-4 w-4 text-warning" />;
      default:
        return <Clock className="h-4 w-4 text-muted" />;
    }
  };

  const getStateBadge = () => {
    switch (step.state) {
      case "completed":
        return <Badge tone="success">Completed</Badge>;
      case "running":
        return <Badge tone="warning">Running</Badge>;
      case "failed":
        return <Badge tone="danger">Failed</Badge>;
      case "pending":
        return <Badge tone="warning">Pending</Badge>;
      default:
        return <Badge tone="neutral">Not Started</Badge>;
    }
  };

  return (
    <div className="flex items-center gap-3 p-3 rounded-lg border border-line bg-canvas/50">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-brand/10 text-brand">
        {getStateIcon()}
      </div>
      <div className="min-w-0 flex-1">
        <p className="font-medium text-ink truncate">{step.name}</p>
        <p className="text-[12px] text-muted truncate">{step.description}</p>
        {step.error && (
          <p className="text-[11px] text-danger truncate mt-1">
            Error: {step.error}
          </p>
        )}
        {step.state === "failed" && step.recoverable && (
          <div className="mt-2 flex items-center gap-2">
            <AlertTriangle className="h-3 w-3 text-warning" />
            <span className="text-[11px] text-warning">
              This step can be retried
            </span>
          </div>
        )}
      </div>
      {getStateBadge()}
    </div>
  );
}

function OnboardingContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const inviteToken = searchParams.get("invite") ?? "";
  const isInvite = Boolean(inviteToken);
  const { user, organization, loading: authLoading, refreshAuth } = useAuth();

  const [state, setState] = useState<OnboardingState>(() => {
    // Initialize from localStorage for refresh recovery
    if (typeof window !== "undefined") {
      try {
        const stored = localStorage.getItem(PROVISIONING_STORAGE_KEY);
        if (stored) {
          const parsed = JSON.parse(stored);
          if (parsed.provisioningId && parsed.step === "provisioning") {
            return {
              step: "provisioning",
              profile: {
                full_name: "",
                job_title: "",
                phone: "",
                timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
              },
              company: {
                name: "",
                industry: "",
                size: "1-10",
                timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
              },
              team: { members: [] },
              integrations: [],
              completedSteps: [
                "welcome",
                "profile",
                "company",
                "team",
                "integrations",
              ],
              provisioningId: parsed.provisioningId,
              provisioningProgress: null,
              provisioningPolling: false,
            };
          }
        }
      } catch (e) {
        console.warn("Failed to restore onboarding state:", e);
      }
    }
    return {
      step: "welcome",
      profile: {
        full_name: "",
        job_title: "",
        phone: "",
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      },
      company: {
        name: "",
        industry: "",
        size: "1-10",
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      },
      team: { members: [] },
      integrations: [],
      completedSteps: [],
      provisioningId: null,
      provisioningProgress: null,
      provisioningPolling: false,
    };
  });

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [onboardingStatus, setOnboardingStatus] = useState<{
    onboarding_completed: boolean;
    provisioning_state?: string;
    provisioning_progress?: number;
    current_phase?: string;
    completed_steps?: string[];
  } | null>(null);
  const [statusLoading, setStatusLoading] = useState(true);

  const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const isPollingRef = useRef(false);
  const provisioningIdRef = useRef<string | null>(null);

  useEffect(() => {
    provisioningIdRef.current = state.provisioningId;
  }, [state.provisioningId]);

  // Restore provisioning state on mount
  useEffect(() => {
    if (state.provisioningId && state.step === "provisioning") {
      // Fetch current progress immediately
      fetchProvisioningProgress();
      // Start polling
      startPolling();
    }
  }, []);

  // Save provisioning ID to localStorage when it changes
  useEffect(() => {
    if (typeof window !== "undefined" && state.provisioningId) {
      try {
        localStorage.setItem(
          PROVISIONING_STORAGE_KEY,
          JSON.stringify({
            provisioningId: state.provisioningId,
            step: state.step,
            timestamp: Date.now(),
          }),
        );
      } catch (e) {
        console.warn("Failed to save provisioning state:", e);
      }
    }
  }, [state.provisioningId, state.step]);

  // Clear localStorage when provisioning completes
  useEffect(() => {
    if (
      state.provisioningProgress?.state === "ready" ||
      state.provisioningProgress?.state === "READY"
    ) {
      if (typeof window !== "undefined") {
        localStorage.removeItem(PROVISIONING_STORAGE_KEY);
      }
    }
  }, [state.provisioningProgress?.state]);

  // Check onboarding status
  useEffect(() => {
    if (authLoading || !organization?.id) return;

    const checkStatus = async () => {
      try {
        setStatusLoading(true);
        const status = await api<{
          onboarding_completed: boolean;
          provisioning_state?: string;
          provisioning_progress?: number;
          current_phase?: string;
          completed_steps?: string[];
        }>("/onboarding/status");
        setOnboardingStatus(status);
      } catch (err) {
        console.error("Failed to check onboarding status:", err);
      } finally {
        setStatusLoading(false);
      }
    };

    checkStatus();
  }, [authLoading, organization?.id]);

  const fetchProvisioningProgress = useCallback(async () => {
    const provisioningId = provisioningIdRef.current;
    if (!provisioningId) return;

    try {
      const progress = await api<ProvisioningProgress>(
        `/onboarding/provisioning/${provisioningId}/progress`,
      );

      setState((prev) => ({
        ...prev,
        provisioningProgress: progress,
      }));

      // Check for terminal states
      if (progress.state === "ready" || progress.state === "READY") {
        stopPolling();
        setState((prev) => ({
          ...prev,
          step: "complete",
          completedSteps: [...prev.completedSteps, "provisioning"],
          provisioningPolling: false,
        }));
        toastSuccess("Provisioning complete! Welcome to VCOS.");
      } else if (
        progress.state === "FAILED" ||
        progress.state === "SUSPENDED" ||
        progress.state === "DEACTIVATED" ||
        progress.state === "failed" ||
        progress.state === "suspended" ||
        progress.state === "deactivated"
      ) {
        stopPolling();
        setError(
          progress.error || `Provisioning ${progress.state.toLowerCase()}`,
        );
      }
    } catch (err) {
      if (err instanceof Error && err.message.includes("404")) {
        // Provisioning not found, stop polling
        stopPolling();
        return;
      }
      console.error("Provisioning poll error:", err);
    }
  }, []);

  const startPolling = useCallback(() => {
    if (pollingIntervalRef.current || isPollingRef.current) return;
    isPollingRef.current = true;
    pollingIntervalRef.current = setInterval(() => {
      fetchProvisioningProgress();
    }, 5000);
    fetchProvisioningProgress();
  }, [fetchProvisioningProgress]);

  const stopPolling = useCallback(() => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
    }
    isPollingRef.current = false;
    setState((prev) => ({ ...prev, provisioningPolling: false }));
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
      }
    };
  }, []);

  const isFirstVisit = authLoading || !user;
  const onboardingComplete =
    onboardingStatus?.onboarding_completed ??
    state.completedSteps.includes("complete");

  useEffect(() => {
    if (authLoading) return;
    if (onboardingComplete) {
      router.replace("/home");
    }
  }, [authLoading, onboardingComplete, router]);

  if (isFirstVisit || onboardingComplete) {
    return null;
  }

  if (statusLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner label="Loading onboarding..." />
      </div>
    );
  }

  const currentStepIndex = STEPS.indexOf(state.step);
  const isFirstStep = currentStepIndex === 0;
  const isLastStep = currentStepIndex === STEPS.length - 1;

  const nextStep = () => {
    if (currentStepIndex < STEPS.length - 1) {
      setState((prev) => ({
        ...prev,
        step: STEPS[currentStepIndex + 1],
        completedSteps: [...prev.completedSteps, prev.step],
      }));
    }
  };

  const prevStep = () => {
    if (currentStepIndex > 0) {
      setState((prev) => ({
        ...prev,
        step: STEPS[currentStepIndex - 1],
        completedSteps: prev.completedSteps.filter((s) => s !== prev.step),
      }));
    }
  };

  const handleProfileSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api("/users/me", {
        method: "PATCH",
        body: state.profile,
      });
      toastSuccess("Profile saved");
      nextStep();
    } catch (err) {
      toastError(
        "Failed to save profile",
        err instanceof Error ? err.message : undefined,
      );
    }
  };

  const handleCompanySubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api("/organizations/me", {
        method: "PATCH",
        body: state.company,
      });
      toastSuccess("Company saved");
      nextStep();
    } catch (err) {
      toastError(
        "Failed to save company",
        err instanceof Error ? err.message : undefined,
      );
    }
  };

  const handleTeamSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    for (const member of state.team.members) {
      if (member.email) {
        try {
          await api("/users/invite", {
            method: "POST",
            body: {
              email: member.email,
              full_name: member.name,
              role: member.role,
            },
          });
        } catch (err) {
          console.error("Failed to invite", member.email, err);
        }
      }
    }
    toastSuccess("Invitations sent");
    nextStep();
  };

  const handleIntegrationsSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await handleComplete();
  };

  const handleComplete = async () => {
    try {
      setLoading(true);
      const provResult = await api<{
        success: boolean;
        provisioning_id: string;
        message: string;
      }>("/onboarding/provisioning/start", { method: "POST" });
      if (!provResult.success) {
        throw new Error(provResult.message || "Failed to start provisioning");
      }

      const newProvisioningId = provResult.provisioning_id;
      provisioningIdRef.current = newProvisioningId;
      setState((prev) => ({
        ...prev,
        provisioningId: newProvisioningId,
        provisioningPolling: true,
        step: "provisioning",
        completedSteps: [...prev.completedSteps, "integrations"],
      }));

      startPolling();
    } catch (err) {
      toastError(
        "Failed to complete onboarding",
        err instanceof Error ? err.message : undefined,
      );
    } finally {
      setLoading(false);
    }
  };

  const handleRetryProvisioning = async () => {
    if (!state.provisioningProgress) return;
    try {
      setLoading(true);
      // Retry failed steps
      for (const step of state.provisioningProgress.steps) {
        if (step.state === "failed" && step.recoverable) {
          await api(
            `/onboarding/provisioning/${state.provisioningId}/retry/${step.step}`,
            { method: "POST" },
          );
        }
      }
      // Restart polling
      startPolling();
      toastSuccess("Retrying failed steps...");
    } catch (err) {
      toastError(
        "Failed to retry provisioning",
        err instanceof Error ? err.message : undefined,
      );
    } finally {
      setLoading(false);
    }
  };

  const renderStep = () => {
    switch (state.step) {
      case "welcome":
        return (
          <div className="text-center py-12">
            <div className="mx-auto mb-8 flex h-20 w-20 items-center justify-center rounded-2xl bg-brand text-white shadow-popper">
              <Sparkles className="h-10 w-10" />
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-ink">
              Welcome to VCOS
            </h1>
            <p className="mt-2 max-w-md mx-auto text-muted">
              Your company\u0027s operating system. Let\u0027s get you set up in
              a few minutes.
            </p>
            <div className="mt-8 grid gap-4 sm:grid-cols-3">
              <StepCard
                icon={<Truck className="h-6 w-6" />}
                title="Company Setup"
                description="Configure your organization"
              />
              <StepCard
                icon={<Users className="h-6 w-6" />}
                title="Invite Team"
                description="Add your first team members"
              />
              <StepCard
                icon={<Zap className="h-6 w-6" />}
                title="Connect Tools"
                description="Link your favorite tools"
              />
            </div>
          </div>
        );
      case "profile":
        return (
          <form onSubmit={handleProfileSubmit} className="space-y-6">
            <h3 className="text-lg font-semibold text-ink">
              Your Professional Profile
            </h3>
            <p className="text-muted">
              This information helps your team collaborate with you.
            </p>
            <div className="grid gap-4 sm:grid-cols-2">
              <Input
                label="Full Name"
                value={state.profile.full_name}
                onChange={(e) =>
                  setState((s) => ({
                    ...s,
                    profile: { ...s.profile, full_name: e.target.value },
                  }))
                }
                placeholder="Ada Lovelace"
                required
              />
              <Input
                label="Job Title"
                value={state.profile.job_title}
                onChange={(e) =>
                  setState((s) => ({
                    ...s,
                    profile: { ...s.profile, job_title: e.target.value },
                  }))
                }
                placeholder="Founder & CEO"
              />
              <Input
                label="Phone"
                type="tel"
                value={state.profile.phone}
                onChange={(e) =>
                  setState((s) => ({
                    ...s,
                    profile: { ...s.profile, phone: e.target.value },
                  }))
                }
                placeholder="+1 (555) 123-4567"
              />
              <Input
                label="Timezone"
                value={state.profile.timezone}
                onChange={(e) =>
                  setState((s) => ({
                    ...s,
                    profile: { ...s.profile, timezone: e.target.value },
                  }))
                }
              />
            </div>
            <div className="flex justify-end pt-4">
              <Button type="submit" className="w-full sm:w-auto">
                Continue
              </Button>
            </div>
          </form>
        );
      case "company":
        return (
          <form onSubmit={handleCompanySubmit} className="space-y-6">
            <h3 className="text-lg font-semibold text-ink">Company Details</h3>
            <p className="text-muted">
              This information appears on your company workspace.
            </p>
            <div className="grid gap-4 sm:grid-cols-2">
              <Input
                name="company-name"
                label="Company Name"
                value={state.company.name}
                onChange={(e) =>
                  setState((s) => ({
                    ...s,
                    company: { ...s.company, name: e.target.value },
                  }))
                }
                placeholder="Acme Corp"
                required
              />
              <Input
                label="Industry"
                value={state.company.industry}
                onChange={(e) =>
                  setState((s) => ({
                    ...s,
                    company: { ...s.company, industry: e.target.value },
                  }))
                }
                placeholder="Technology"
              />
              <Input
                label="Timezone"
                value={state.company.timezone}
                onChange={(e) =>
                  setState((s) => ({
                    ...s,
                    company: { ...s.company, timezone: e.target.value },
                  }))
                }
              />
              <select
                className="input"
                value={state.company.size}
                onChange={(e) =>
                  setState((s) => ({
                    ...s,
                    company: { ...s.company, size: e.target.value },
                  }))
                }
              >
                <option value="1-10">1-10 employees</option>
                <option value="11-50">11-50 employees</option>
                <option value="51-200">51-200 employees</option>
                <option value="201-500">201-500 employees</option>
                <option value="501-1000">501-1000 employees</option>
                <option value="1000+">1000+ employees</option>
              </select>
            </div>
            <div className="flex justify-end pt-4">
              <Button type="submit" className="w-full sm:w-auto">
                Continue
              </Button>
            </div>
          </form>
        );
      case "team":
        return (
          <div className="space-y-6">
            <div>
              <h3 className="text-lg font-semibold text-ink">
                Invite Your Team
              </h3>
              <p className="text-muted">
                Add your first team members. They\u0027ll receive an email
                invitation.
              </p>
            </div>
            <TeamMembersList
              members={state.team.members}
              onChange={(members) =>
                setState((s) => ({ ...s, team: { ...s.team, members } }))
              }
            />
            <div className="flex justify-end pt-4">
              <Button onClick={handleTeamSubmit} className="w-full sm:w-auto">
                Continue
              </Button>
            </div>
          </div>
        );
      case "integrations":
        return (
          <form onSubmit={handleIntegrationsSubmit} className="space-y-6">
            <h3 className="text-lg font-semibold text-ink">
              Connect Your Tools
            </h3>
            <p className="text-muted">
              Connect the tools your team already uses. You can add more later.
            </p>
            <IntegrationCard
              name="GitHub"
              description="Sync repositories, issues, and pull requests"
              icon={<Zap className="h-6 w-6" />}
              connected={state.integrations.includes("github")}
              onToggle={() =>
                setState((s) => ({
                  ...s,
                  integrations: s.integrations.includes("github")
                    ? s.integrations.filter((i) => i !== "github")
                    : [...s.integrations, "github"],
                }))
              }
            />
            <IntegrationCard
              name="Slack"
              description="Send notifications and updates to channels"
              icon={<MessageSquare className="h-6 w-6" />}
              connected={state.integrations.includes("slack")}
              onToggle={() =>
                setState((s) => ({
                  ...s,
                  integrations: s.integrations.includes("slack")
                    ? s.integrations.filter((i) => i !== "slack")
                    : [...s.integrations, "slack"],
                }))
              }
            />
            <IntegrationCard
              name="Google Workspace"
              description="Sync calendar, docs, and drive"
              icon={<Zap className="h-6 w-6" />}
              connected={state.integrations.includes("google")}
              onToggle={() =>
                setState((s) => ({
                  ...s,
                  integrations: s.integrations.includes("google")
                    ? s.integrations.filter((i) => i !== "google")
                    : [...s.integrations, "google"],
                }))
              }
            />
            <IntegrationCard
              name="Microsoft 365 / Entra ID"
              description="Sync users, groups, and identity from Microsoft Entra ID"
              icon={<Cloud className="h-6 w-6" />}
              connected={state.integrations.includes("microsoft365")}
              onToggle={() =>
                setState((s) => ({
                  ...s,
                  integrations: s.integrations.includes("microsoft365")
                    ? s.integrations.filter((i) => i !== "microsoft365")
                    : [...s.integrations, "microsoft365"],
                }))
              }
            />
            <IntegrationCard
              name="Okta"
              description="Sync users and groups from Okta identity provider"
              icon={<Shield className="h-6 w-6" />}
              connected={state.integrations.includes("okta")}
              onToggle={() =>
                setState((s) => ({
                  ...s,
                  integrations: s.integrations.includes("okta")
                    ? s.integrations.filter((i) => i !== "okta")
                    : [...s.integrations, "okta"],
                }))
              }
            />
            <IntegrationCard
              name="Jira"
              description="Sync projects, issues, and boards from Jira"
              icon={<Ticket className="h-6 w-6" />}
              connected={state.integrations.includes("jira")}
              onToggle={() =>
                setState((s) => ({
                  ...s,
                  integrations: s.integrations.includes("jira")
                    ? s.integrations.filter((i) => i !== "jira")
                    : [...s.integrations, "jira"],
                }))
              }
            />
            <div className="flex justify-end pt-4">
              <Button type="submit" className="w-full sm:w-auto">
                Continue
              </Button>
            </div>
          </form>
        );
      case "provisioning":
        return (
          <div className="space-y-6">
            <Card>
              <div className="flex items-center justify-between border-b border-line px-5 py-4">
                <h2 className="text-sm font-semibold text-ink">
                  Provisioning Progress
                </h2>
                <Badge
                  tone={
                    state.provisioningProgress?.state === "ready" ||
                    state.provisioningProgress?.state === "READY"
                      ? "success"
                      : state.provisioningProgress?.state === "FAILED" ||
                          state.provisioningProgress?.state === "failed"
                        ? "danger"
                        : "warning"
                  }
                >
                  {state.provisioningProgress?.state ?? "Initializing..."}
                </Badge>
              </div>
              <div className="p-5">
                {state.provisioningProgress && (
                  <div className="space-y-4">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="font-medium text-ink">Current Phase</p>
                        <p className="text-sm text-muted">
                          {state.provisioningProgress.current_phase}
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <Progress
                          value={
                            state.provisioningProgress.provisioning_progress
                          }
                          className="w-48 h-2"
                        />
                        <span className="text-sm font-mono text-brand">
                          {state.provisioningProgress.provisioning_progress}%
                        </span>
                      </div>
                    </div>
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="font-medium text-ink">Current Step</p>
                        <p className="text-sm text-muted">
                          {state.provisioningProgress.current_step_name}
                        </p>
                      </div>
                      <div className="flex items-center gap-2 text-sm text-muted">
                        <span>
                          {state.provisioningProgress.completed_count}/
                          {state.provisioningProgress.total_steps} completed
                        </span>
                        {state.provisioningProgress.failed_count > 0 && (
                          <Badge tone="danger">
                            {state.provisioningProgress.failed_count} failed
                          </Badge>
                        )}
                        {state.provisioningProgress.running_count > 0 && (
                          <Badge tone="warning">
                            {state.provisioningProgress.running_count} running
                          </Badge>
                        )}
                      </div>
                    </div>
                    {state.provisioningProgress.error && (
                      <div className="p-3 rounded-lg bg-danger/10 border border-danger/30 text-danger text-sm">
                        Error: {state.provisioningProgress.error}
                      </div>
                    )}
                    <div className="mt-4">
                      <h3 className="text-sm font-semibold text-ink mb-2">
                        Provisioning Steps (15 Steps)
                      </h3>
                      <div className="space-y-2 max-h-[500px] overflow-y-auto pr-2">
                        {state.provisioningProgress.steps.map((step, idx) => (
                          <ProvisioningStepRow key={idx} step={step} />
                        ))}
                      </div>
                    </div>
                    {state.provisioningProgress.failed_count > 0 && (
                      <div className="mt-4 flex items-center gap-2">
                        <Button
                          variant="secondary"
                          onClick={handleRetryProvisioning}
                          disabled={loading}
                        >
                          <RotateCcw className="h-4 w-4 mr-2" /> Retry Failed
                          Steps
                        </Button>
                        <span className="text-sm text-muted">
                          Failed steps marked as recoverable can be retried
                        </span>
                      </div>
                    )}
                    {state.provisioningPolling && (
                      <div className="mt-4 flex items-center gap-2 text-sm text-muted">
                        <Loader2 className="h-4 w-4 animate-spin text-brand" />
                        <span>Polling for updates every 5 seconds...</span>
                      </div>
                    )}
                  </div>
                )}
                {!state.provisioningProgress && (
                  <div className="flex flex-col items-center justify-center py-10">
                    <Loader2 className="h-10 w-10 text-brand animate-spin" />
                    <p className="mt-4 text-muted">
                      Loading provisioning progress...
                    </p>
                  </div>
                )}
              </div>
            </Card>
          </div>
        );
      case "complete":
        return (
          <div className="text-center py-12">
            <div className="mx-auto mb-8 flex h-20 w-20 items-center justify-center rounded-2xl bg-brand text-white shadow-popper">
              <Check className="h-10 w-10" />
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-ink">
              You\u0027re All Set!
            </h1>
            <p className="mt-2 max-w-md mx-auto text-muted">
              Your VCOS workspace is ready. Your team has been invited, and your
              tools are connected.
            </p>
            <div className="mt-8 flex justify-center gap-3">
              <Link href="/home">
                <Button className="w-full sm:w-auto">
                  <Zap className="h-4 w-4 mr-2" /> Go to Workspace
                </Button>
              </Link>
              <Link href="/settings">
                <Button variant="secondary" className="w-full sm:w-auto">
                  Settings
                </Button>
              </Link>
            </div>
          </div>
        );
      default:
        return null;
    }
  };

  return (
    <div className="min-h-screen bg-canvas">
      <div className="max-w-3xl mx-auto px-4 py-10">
        <Stepper
          steps={STEPS.map((s) => STEP_LABELS[s])}
          currentStep={STEPS.indexOf(state.step)}
          completedSteps={state.completedSteps.map((s) => STEPS.indexOf(s))}
          className="mb-8"
        />

        <Card className="overflow-hidden">
          <div className="border-b border-line px-6 py-4">
            <h2 className="text-lg font-semibold text-ink">
              {STEP_LABELS[state.step]}
            </h2>
            <p className="mt-1 text-sm text-muted">
              Step {STEPS.indexOf(state.step) + 1} of {STEPS.length}
            </p>
          </div>
          <div className="p-6">{renderStep()}</div>
        </Card>

        <div className="mt-6 flex justify-between">
          <Button
            variant="ghost"
            onClick={prevStep}
            disabled={state.step === "welcome"}
          >
            Back
          </Button>
          <Button
            onClick={state.step === "provisioning" ? undefined : nextStep}
            disabled={loading || state.step === "provisioning"}
          >
            {state.step === "complete"
              ? "Finish"
              : state.step === "provisioning"
                ? "Provisioning..."
                : "Continue"}
          </Button>
        </div>

        {error && (
          <div className="mb-4 rounded-lg border border-danger/30 bg-danger/10 px-3 py-2.5 text-[13px] text-danger">
            {error}
            <button
              onClick={() => setError(null)}
              className="ml-2 text-faint hover:text-ink"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export default OnboardingContent;
