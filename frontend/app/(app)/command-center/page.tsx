"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { History, Inbox, Lock } from "lucide-react";

import {
  api,
  getOrganizationTimeline,
  integrityFindings,
  listApprovals,
  listDecisions,
  listRisks,
  type ExecutiveTimelineEntry,
  type IntegrityFinding,
} from "@/lib/api";
import { roleCan, PERMISSIONS } from "@/lib/permissions";
import type { Approval, DashboardSummary, Decision, Risk } from "@/types";
import { useAuth } from "@/hooks/useAuth";
import { GovernedAIWork } from "@/components/command-center/GovernedAIWork";
import { PageHeader, StatCard } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Badge, statusTone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { formatDate, titleCase } from "@/lib/utils";

interface BrainDimension {
  label?: string;
  state?: string;
  headline?: string;
}

interface BrainAttentionItem {
  priority?: number;
  kind?: string;
  title?: string;
  why?: string;
}

interface BrainCompanyState {
  advisory_only?: boolean;
  generated_at?: string;
  dimensions?: Record<string, BrainDimension>;
  attention?: BrainAttentionItem[];
}

interface SectionState<T> {
  loading: boolean;
  error: string | null;
  data: T | null;
  loadedAt: string | null;
}

function useSection<T>(load: () => Promise<T>, deps: unknown[]) {
  const [state, setState] = useState<SectionState<T>>({
    loading: true,
    error: null,
    data: null,
    loadedAt: null,
  });

  const run = useCallback(async () => {
    setState((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const data = await load();
      setState({
        loading: false,
        error: null,
        data,
        loadedAt: new Date().toISOString(),
      });
    } catch (err) {
      setState({
        loading: false,
        error: err instanceof Error ? err.message : "Request failed",
        data: null,
        loadedAt: null,
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    run();
  }, [run]);

  return { ...state, reload: run };
}

function SectionBody<T>({
  state,
  label,
  children,
}: {
  state: SectionState<T> & { reload: () => void };
  label: string;
  children: (data: T) => React.ReactNode;
}) {
  if (state.error) {
    return (
      <ErrorState
        title={`Could not load ${label}`}
        message={state.error}
        onRetry={state.reload}
      />
    );
  }
  if (state.loading) {
    return (
      <div className="flex justify-center py-10">
        <Spinner label={`Loading ${label}`} />
      </div>
    );
  }
  if (!state.data) {
    return (
      <EmptyState
        title={`No ${label} available`}
        description="Nothing was returned for your permissions."
      />
    );
  }
  return <>{children(state.data)}</>;
}

function PermissionNote({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-2 rounded-lg border border-line bg-canvas p-4 text-sm text-muted">
      <Lock className="mt-0.5 h-4 w-4 shrink-0" />
      <p>{children}</p>
    </div>
  );
}

function Freshness({ loadedAt }: { loadedAt: string | null }) {
  if (!loadedAt) return null;
  return (
    <p className="mt-3 text-xs text-faint">Data as of {formatDate(loadedAt)}</p>
  );
}

function PartialWarning({
  errors,
  onRetry,
}: {
  errors: string[];
  onRetry: () => void;
}) {
  if (errors.length === 0) return null;
  return (
    <div className="mb-3 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-warning/40 bg-warning/10 p-2 text-xs text-ink">
      <span>Partial data: {errors.join("; ")}</span>
      <Button variant="ghost" size="sm" onClick={onRetry}>
        Retry
      </Button>
    </div>
  );
}

const AUTHORIZATION_ORDER = ["pending", "approved", "rejected", "cancelled"];

function authorizationFor(
  approvals: Approval[],
  decision: Decision,
): Approval | null {
  const linked = approvals.filter(
    (a) => a.entity_type === "decision" && a.entity_id === decision.id,
  );
  if (linked.length === 0) return null;
  return [...linked].sort(
    (a, b) =>
      AUTHORIZATION_ORDER.indexOf(a.status) -
      AUTHORIZATION_ORDER.indexOf(b.status),
  )[0];
}

function authorizationTone(
  status: string,
): "warning" | "success" | "danger" | "neutral" {
  if (status === "pending") return "warning";
  if (status === "approved") return "success";
  if (status === "rejected") return "danger";
  return "neutral";
}

function dimensionTone(
  state: string | undefined,
): "success" | "warning" | "danger" | "neutral" {
  if (state === "healthy") return "success";
  if (state === "concerned" || state === "warning") return "warning";
  if (state === "critical") return "danger";
  return "neutral";
}

function severityTone(
  severity: string | null | undefined,
): "danger" | "warning" | "neutral" {
  if (severity === "critical" || severity === "high") return "danger";
  if (severity === "medium") return "warning";
  return "neutral";
}

export default function CommandCenterPage() {
  return (
    <Suspense fallback={null}>
      <CommandCenterContent />
    </Suspense>
  );
}

function CommandCenterContent() {
  const { user } = useAuth();
  const [nonce, setNonce] = useState(0);

  const canKnowledge = roleCan(user?.role, PERMISSIONS.KNOWLEDGE_READ);
  const canApprovals = roleCan(user?.role, PERMISSIONS.APPROVALS_READ);
  const canDashboard = roleCan(user?.role, PERMISSIONS.DASHBOARD_READ);
  const canBrain = roleCan(user?.role, PERMISSIONS.BRAIN_READ);
  const canRisks = roleCan(user?.role, PERMISSIONS.RISKS_READ);
  const canExecutive = roleCan(user?.role, PERMISSIONS.EXECUTIVE_VIEW);
  const inboxEnabled = canKnowledge || canApprovals;
  const companyStateEnabled = canDashboard || canBrain;

  const inbox = useSection(async () => {
    if (!inboxEnabled)
      return { decisions: [] as Decision[], approvals: [] as Approval[] };
    const [decisions, approvals] = await Promise.all([
      canKnowledge
        ? listDecisions({ limit: 200 })
        : Promise.resolve([] as Decision[]),
      canApprovals ? listApprovals({}) : Promise.resolve([] as Approval[]),
    ]);
    return { decisions, approvals };
  }, [nonce, canKnowledge, canApprovals, inboxEnabled]);

  const companyState = useSection(async () => {
    if (!companyStateEnabled) {
      return {
        summary: null as DashboardSummary | null,
        brain: null as BrainCompanyState | null,
        partialErrors: [] as string[],
      };
    }
    const [summaryRes, brainRes] = await Promise.allSettled([
      canDashboard
        ? api<DashboardSummary>("/dashboard/summary")
        : Promise.resolve(null as DashboardSummary | null),
      canBrain
        ? api<BrainCompanyState>("/brain/execution/company/state")
        : Promise.resolve(null as BrainCompanyState | null),
    ]);
    const partialErrors: string[] = [];
    const summary = summaryRes.status === "fulfilled" ? summaryRes.value : null;
    const brain = brainRes.status === "fulfilled" ? brainRes.value : null;
    if (summaryRes.status === "rejected")
      partialErrors.push("company summary failed");
    if (brainRes.status === "rejected")
      partialErrors.push("operating engine state failed");
    if (!summary && !brain) {
      throw new Error(
        partialErrors.join("; ") || "Both company state sources failed",
      );
    }
    return { summary, brain, partialErrors };
  }, [nonce, canDashboard, canBrain, companyStateEnabled]);

  const riskIntegrity = useSection(async () => {
    const [risksRes, findingsRes] = await Promise.allSettled([
      canRisks ? listRisks({}) : Promise.resolve([] as Risk[]),
      integrityFindings({ limit: 100 }),
    ]);
    const partialErrors: string[] = [];
    const risks = risksRes.status === "fulfilled" ? risksRes.value : [];
    const findings =
      findingsRes.status === "fulfilled" ? findingsRes.value : [];
    if (risksRes.status === "rejected")
      partialErrors.push("risk register failed");
    if (findingsRes.status === "rejected")
      partialErrors.push("integrity findings failed");
    if (risksRes.status === "rejected" && findingsRes.status === "rejected") {
      throw new Error(partialErrors.join("; "));
    }
    return { risks, findings, partialErrors };
  }, [nonce, canRisks]);

  const timeline = useSection(async () => {
    if (!canExecutive)
      return { total: 0, entries: [] as ExecutiveTimelineEntry[] };
    return getOrganizationTimeline(60);
  }, [nonce, canExecutive]);

  const refreshAll = () => setNonce((n) => n + 1);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Command Center"
        description="One evidence-backed picture of the company: decisions awaiting attention, current operating state, integrity findings, and the company timeline."
        actions={
          <Button variant="secondary" onClick={refreshAll}>
            Refresh
          </Button>
        }
      />

      <div className="grid gap-6 lg:grid-cols-2">
        <section aria-label="Decision Inbox">
          <Card
            title="Decision Inbox"
            subtitle="Decisions awaiting attention. A recorded decision is not an authorization, and an approval is never inferred from the existence of a decision."
          >
            {!inboxEnabled ? (
              <PermissionNote>
                You do not have permission to read decisions or approvals. Ask
                an administrator for knowledge:read or approvals:read access.
              </PermissionNote>
            ) : (
              <SectionBody state={inbox} label="decision inbox">
                {({ decisions, approvals }) => {
                  const attention = decisions
                    .filter(
                      (d) => d.status === "proposed" || d.status === "made",
                    )
                    .slice(0, 8);
                  const pending = approvals
                    .filter((a) => a.status === "pending")
                    .slice(0, 5);
                  return (
                    <div className="space-y-4">
                      {attention.length === 0 ? (
                        <EmptyState
                          icon={Inbox}
                          title="No decisions awaiting attention"
                          description="Proposed or made decisions will appear here."
                        />
                      ) : (
                        <ul className="space-y-2">
                          {attention.map((d) => {
                            const authorization = authorizationFor(
                              approvals,
                              d,
                            );
                            return (
                              <li
                                key={d.id}
                                className="rounded-lg border border-line bg-surface p-3"
                              >
                                <div className="flex items-start justify-between gap-3">
                                  <div className="min-w-0">
                                    <Link
                                      href={`/decisions/${d.id}`}
                                      className="text-sm font-medium text-ink hover:text-brand"
                                    >
                                      {d.title}
                                    </Link>
                                    <p className="mt-1 text-xs text-muted">
                                      {d.decision_maker_name ??
                                        "No decision maker on record"}
                                      {" · "}
                                      updated {formatDate(d.updated_at)}
                                    </p>
                                  </div>
                                  <Badge tone={statusTone(d.status)}>
                                    {titleCase(d.status)}
                                  </Badge>
                                </div>
                                <p className="mt-2 text-xs text-faint">
                                  Authorization:{" "}
                                  {authorization ? (
                                    <span className="font-medium text-ink">
                                      {authorization.status} —{" "}
                                      {authorization.title}
                                    </span>
                                  ) : (
                                    <span>none on record</span>
                                  )}
                                </p>
                              </li>
                            );
                          })}
                        </ul>
                      )}

                      {canApprovals && (
                        <div>
                          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-faint">
                            Pending authorizations
                          </p>
                          {pending.length === 0 ? (
                            <p className="text-xs text-muted">
                              No pending approvals.
                            </p>
                          ) : (
                            <ul className="space-y-1.5">
                              {pending.map((a) => (
                                <li
                                  key={a.id}
                                  className="flex items-center justify-between gap-3 rounded-md border border-line bg-canvas px-3 py-2"
                                >
                                  <div className="min-w-0">
                                    <Link
                                      href="/approvals"
                                      className="truncate text-xs font-medium text-ink hover:text-brand"
                                    >
                                      {a.title}
                                    </Link>
                                    <p className="text-[11px] text-faint">
                                      {titleCase(a.approval_type)}
                                      {a.requester_name
                                        ? ` · requested by ${a.requester_name}`
                                        : ""}
                                      {a.due_at
                                        ? ` · due ${formatDate(a.due_at)}`
                                        : ""}
                                    </p>
                                  </div>
                                  <Badge tone={authorizationTone(a.status)}>
                                    {titleCase(a.status)}
                                  </Badge>
                                </li>
                              ))}
                            </ul>
                          )}
                        </div>
                      )}
                      <Freshness loadedAt={inbox.loadedAt} />
                    </div>
                  );
                }}
              </SectionBody>
            )}
          </Card>
        </section>

        <section aria-label="Company State">
          <Card
            title="Company State"
            subtitle="Current state from canonical services. Verified administrative facts are separated from advisory operating-engine assessments."
          >
            {!companyStateEnabled ? (
              <PermissionNote>
                You do not have permission to read company state. Ask an
                administrator for dashboard:read or brain:read access.
              </PermissionNote>
            ) : (
              <SectionBody state={companyState} label="company state">
                {({ summary, brain, partialErrors }) => (
                  <div>
                    <PartialWarning
                      errors={partialErrors}
                      onRetry={companyState.reload}
                    />
                    {summary && (
                      <div className="grid gap-3 sm:grid-cols-2">
                        <StatCard
                          label="Members"
                          value={summary.total_users}
                          hint="verified roster count"
                        />
                        <StatCard
                          label="Active users"
                          value={summary.active_users}
                          hint="verified"
                        />
                        <StatCard
                          label="Active sessions"
                          value={summary.active_sessions}
                          hint="verified"
                        />
                        <StatCard
                          label="Unread notifications"
                          value={summary.unread_notifications}
                          hint="verified"
                        />
                      </div>
                    )}
                    {brain && (
                      <div className={summary ? "mt-4" : ""}>
                        <div className="mb-2 flex items-center justify-between gap-2">
                          <p className="text-xs font-semibold uppercase tracking-wide text-faint">
                            Operating picture
                          </p>
                          {brain.advisory_only && (
                            <Badge tone="neutral">Advisory</Badge>
                          )}
                        </div>
                        {brain.dimensions && (
                          <div className="grid gap-2 sm:grid-cols-2">
                            {Object.entries(brain.dimensions).map(
                              ([key, dim]) => (
                                <div
                                  key={key}
                                  className="rounded-lg border border-line bg-surface p-3"
                                >
                                  <div className="flex items-center justify-between gap-2">
                                    <p className="text-sm font-medium text-ink">
                                      {dim.label ?? titleCase(key)}
                                    </p>
                                    <Badge tone={dimensionTone(dim.state)}>
                                      {dim.state
                                        ? titleCase(dim.state)
                                        : "unknown"}
                                    </Badge>
                                  </div>
                                  {dim.headline && (
                                    <p className="mt-1 text-xs text-muted">
                                      {dim.headline}
                                    </p>
                                  )}
                                </div>
                              ),
                            )}
                          </div>
                        )}
                        {brain.attention && brain.attention.length > 0 && (
                          <div className="mt-3">
                            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-faint">
                              What to pay attention to
                            </p>
                            <ul className="space-y-1.5">
                              {brain.attention.map((item, index) => (
                                <li
                                  key={`${item.kind}-${index}`}
                                  className="text-xs text-muted"
                                >
                                  <span className="font-medium text-ink">
                                    {item.title ?? "Attention item"}
                                  </span>
                                  {item.why ? ` — ${item.why}` : ""}
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}
                        <p className="mt-3 text-xs text-faint">
                          Engine picture generated{" "}
                          {formatDate(brain.generated_at)}. These are advisory
                          assessments, not verified outcomes.
                        </p>
                      </div>
                    )}
                    <Freshness loadedAt={companyState.loadedAt} />
                  </div>
                )}
              </SectionBody>
            )}
          </Card>
        </section>

        <section aria-label="Risk and Integrity">
          <Card
            title="Risk & Integrity"
            subtitle="Recorded risks and canonical integrity findings. Findings are shown as recorded; nothing is resolved or reclassified implicitly."
          >
            <SectionBody state={riskIntegrity} label="risk and integrity data">
              {({ risks, findings, partialErrors }) => (
                <div>
                  <PartialWarning
                    errors={partialErrors}
                    onRetry={riskIntegrity.reload}
                  />
                  <div>
                    <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-faint">
                      Open risks
                    </p>
                    {!canRisks ? (
                      <PermissionNote>
                        You do not have permission to read the risk register
                        (risks:read).
                      </PermissionNote>
                    ) : risks.length === 0 ? (
                      <p className="text-xs text-muted">No risks on record.</p>
                    ) : (
                      <ul className="space-y-1.5">
                        {[...risks]
                          .sort(
                            (a, b) => (b.risk_score ?? 0) - (a.risk_score ?? 0),
                          )
                          .slice(0, 6)
                          .map((r) => (
                            <li
                              key={r.id}
                              className="flex items-center justify-between gap-3 rounded-md border border-line bg-canvas px-3 py-2"
                            >
                              <div className="min-w-0">
                                <Link
                                  href="/risks"
                                  className="truncate text-xs font-medium text-ink hover:text-brand"
                                >
                                  {r.title}
                                </Link>
                                <p className="text-[11px] text-faint">
                                  {titleCase(r.status)}
                                  {r.owner_name ? ` · ${r.owner_name}` : ""}
                                  {r.due_at
                                    ? ` · due ${formatDate(r.due_at)}`
                                    : ""}
                                </p>
                              </div>
                              <Badge tone={severityTone(r.severity)}>
                                {r.severity
                                  ? titleCase(r.severity)
                                  : `score ${r.risk_score}`}
                              </Badge>
                            </li>
                          ))}
                      </ul>
                    )}
                  </div>
                  <div className="mt-4">
                    <div className="mb-2 flex items-center justify-between gap-2">
                      <p className="text-xs font-semibold uppercase tracking-wide text-faint">
                        Integrity findings
                      </p>
                      <Link
                        href="/truth-center?tab=integrity"
                        className="text-xs text-brand hover:underline"
                      >
                        Open Truth Center
                      </Link>
                    </div>
                    {findings.length === 0 ? (
                      <p className="text-xs text-muted">
                        No integrity findings reported.
                      </p>
                    ) : (
                      <ul className="space-y-1.5">
                        {findings.slice(0, 6).map((f: IntegrityFinding) => (
                          <li
                            key={f.id}
                            className="rounded-md border border-line bg-canvas px-3 py-2"
                          >
                            <div className="flex items-start justify-between gap-3">
                              <p className="min-w-0 truncate text-xs font-medium text-ink">
                                {f.title}
                              </p>
                              <Badge tone={severityTone(f.severity)}>
                                {titleCase(f.severity)}
                              </Badge>
                            </div>
                            <p className="mt-1 text-[11px] text-faint">
                              {f.status} · {f.epistemic_classification} ·{" "}
                              {f.source_subsystem}
                              {f.detected_at
                                ? ` · detected ${formatDate(f.detected_at)}`
                                : ""}
                            </p>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                  <Freshness loadedAt={riskIntegrity.loadedAt} />
                </div>
              )}
            </SectionBody>
          </Card>
        </section>

        <section aria-label="Company Timeline">
          <Card
            title="Company Timeline"
            subtitle="Merged company events in occurred-time order. An event being recorded does not prove the claimed business outcome occurred."
          >
            {!canExecutive ? (
              <PermissionNote>
                You do not have permission to read the executive timeline. Ask
                an administrator for executive:view access.
              </PermissionNote>
            ) : (
              <SectionBody state={timeline} label="company timeline">
                {({ entries }) => (
                  <div>
                    {entries.length === 0 ? (
                      <EmptyState
                        icon={History}
                        title="No timeline events yet"
                        description="Decisions, approvals, projects, and documents will appear here as the company operates."
                      />
                    ) : (
                      <ul>
                        {entries.map((e, index) => (
                          <li
                            key={`${e.source}-${e.kind}-${index}`}
                            className="flex items-start gap-3 border-b border-line py-2 last:border-0"
                          >
                            <Badge tone="neutral">{e.source}</Badge>
                            <div className="min-w-0 flex-1">
                              <p className="truncate text-sm text-ink">
                                {e.title}
                              </p>
                              <p className="mt-0.5 text-xs text-faint">
                                {titleCase(e.kind)}
                                {e.occurred_at
                                  ? ` · occurred ${formatDate(e.occurred_at)}`
                                  : " · time not recorded"}
                              </p>
                            </div>
                          </li>
                        ))}
                      </ul>
                    )}
                    <Freshness loadedAt={timeline.loadedAt} />
                  </div>
                )}
              </SectionBody>
            )}
          </Card>
        </section>
      </div>

      <section aria-label="Governed AI Work">
        <GovernedAIWork />
      </section>
    </div>
  );
}
