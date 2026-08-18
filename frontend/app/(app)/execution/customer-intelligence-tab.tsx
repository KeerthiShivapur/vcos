"use client";

import {
  Activity,
  AlertTriangle,
  ArrowUpRight,
  CheckCircle2,
  CircleDashed,
  Clock,
  HeartPulse,
  Info,
  Loader2,
  MapPin,
  ShieldAlert,
  Target,
  TrendingUp,
  Users,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { StatCard } from "@/components/ui/PageHeader";
import { useAuth } from "@/hooks/useAuth";
import {
  deliverCustomerCommitment,
  getCustomerIntelligenceCenter,
  getCustomerIntelligenceCommitments,
  getCustomerIntelligenceCoverage,
  getCustomerIntelligenceGaps,
  getCustomerIntelligenceHealth,
  getCustomerIntelligenceKnowledge,
  getCustomerIntelligenceOpportunities,
  getCustomerIntelligenceOutcomes,
  getCustomerIntelligenceRisk,
  getCustomerIntelligenceSignals,
  getCustomerIntelligenceThemes,
  processPendingEvents,
  resolveCustomerSignal,
  type CustomerIntelligenceCenterResponse,
  type CustomerIntelligenceGapsResponse,
  type CustomerIntelligenceHealthResponse,
  type CustomerIntelligenceRiskResponse,
} from "@/lib/api";
import { PERMISSIONS } from "@/lib/permissions";
import { timeAgo } from "@/lib/utils";

const STATE_TONE: Record<string, "success" | "warning" | "danger" | "neutral" | "brand"> = {
  healthy: "success",
  concerned: "warning",
  at_risk: "danger",
} as const;

const STATUS_TONE: Record<string, "success" | "warning" | "danger" | "neutral" | "brand"> = {
  delivered: "success",
  pending: "brand",
  at_risk: "danger",
  slipped: "danger",
  closed: "neutral",
  resolved: "success",
  open: "warning",
} as const;

const SEVERITY_TONE: Record<string, "danger" | "warning" | "neutral"> = {
  high: "danger",
  critical: "danger",
  medium: "warning",
  low: "neutral",
  info: "neutral",
} as const;

const IMPACT_TONE: Record<string, "danger" | "warning" | "neutral"> = {
  high: "danger",
  medium: "warning",
  low: "neutral",
} as const;

export function CustomerIntelligenceTab() {
  const { can } = useAuth();
  const canManage = can(PERMISSIONS.PROJECTS_MANAGE);

  const [health, setHealth] = useState<CustomerIntelligenceHealthResponse | null>(null);
  const [risk, setRisk] = useState<CustomerIntelligenceRiskResponse | null>(null);
  const [coverage, setCoverage] = useState<{ coverage_pct: number; themes: { key: string; label?: string; occurrences: number; customers: number; open: number; high_severity: number; coverage_pct: number; covered: boolean; addressing_projects: { id: string; name: string }[] }[] } | null>(null);
  const [gaps, setGaps] = useState<CustomerIntelligenceGapsResponse | null>(null);
  const [themes, setThemes] = useState<{ advisory_only: boolean; themes: { key: string; label?: string; occurrences: number; customers: number; open: number; high_severity: number; evidence: { customer: string; summary: string; occurred_at: string; severity: string }[] }[] } | null>(null);
  const [signals, setSignals] = useState<{ total: number; signals: { signal_id: string; customer: string; title: string; severity: string; status: string; occurred_at: string }[] } | null>(null);
  const [commitments, setCommitments] = useState<{ advisory_only: boolean; total: number; delivered: number; commitments: { commitment_id: string; customer: string; summary: string; expected_at: string; status: string }[] } | null>(null);
  const [outcomes, setOutcomes] = useState<{ advisory_only: boolean; total: number; improved: number; outcomes: { outcome_id: string; customer: string; metric_kind: string; baseline: number | null; target: number | null; actual: number | null; unit: string | null; improved: boolean | null; recorded_at: string }[] } | null>(null);
  const [opportunities, setOpportunities] = useState<{ advisory_only: boolean; opportunities: { key: string; label?: string; signals: number; customers: number; addressed: boolean; strategic_relevance: boolean; decision_linkage: { requires_decision: boolean; note: string; recommendation?: string } }[] } | null>(null);
  const [knowledge, setKnowledge] = useState<{ knowledge_coverage_pct: number; themes: { key: string; knowledge_covered: boolean }[] } | null>(null);
  const [center, setCenter] = useState<CustomerIntelligenceCenterResponse | null>(null);
  const [centerCustomerId, setCenterCustomerId] = useState<string | null>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actingId, setActingId] = useState<string | null>(null);

  const refresh = useCallback(async (centerId?: string) => {
    setError(null);
    try {
      const [h, r, cv, g, t, s, cm, o, op, k] = await Promise.all([
        getCustomerIntelligenceHealth(),
        getCustomerIntelligenceRisk(),
        getCustomerIntelligenceCoverage(),
        getCustomerIntelligenceGaps(),
        getCustomerIntelligenceThemes(),
        getCustomerIntelligenceSignals(),
        getCustomerIntelligenceCommitments(),
        getCustomerIntelligenceOutcomes(),
        getCustomerIntelligenceOpportunities(),
        getCustomerIntelligenceKnowledge(),
      ]);
      setHealth(h);
      setRisk(r);
      setCoverage(cv);
      setGaps(g);
      setThemes(t);
      setSignals(s);
      setCommitments(cm);
      setOutcomes(o);
      setOpportunities(op);
      setKnowledge(k);
      if (centerId) setCenter(await getCustomerIntelligenceCenter(centerId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load customer intelligence");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function openCenter(customerId: string) {
    setCenterCustomerId(customerId);
    setError(null);
    try {
      setCenter(await getCustomerIntelligenceCenter(customerId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load the customer command center");
    }
  }

  async function resolve(signalId: string) {
    setActingId(signalId);
    setError(null);
    try {
      await resolveCustomerSignal(signalId);
      await processPendingEvents(500);
      await refresh(centerCustomerId ?? undefined);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to resolve the signal");
    } finally {
      setActingId(null);
    }
  }

  async function deliver(commitmentId: string) {
    setActingId(commitmentId);
    setError(null);
    try {
      await deliverCustomerCommitment(commitmentId);
      await processPendingEvents(500);
      await refresh(centerCustomerId ?? undefined);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to deliver the commitment");
    } finally {
      setActingId(null);
    }
  }

  if (error && !health && !loading) {
    return <ErrorState title="Could not load customer intelligence" message={error} />;
  }

  const openSignals = signals?.signals.filter((s) => !["resolved", "closed"].includes(s.status)).length ?? 0;

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <StatCard label="At-risk customers" value={loading ? "…" : risk?.at_risk_customers.length ?? 0} icon={ShieldAlert} />
        <StatCard label="Concerned" value={loading ? "…" : health?.concerned ?? 0} icon={AlertTriangle} />
        <StatCard label="Healthy" value={loading ? "…" : health?.healthy ?? 0} icon={HeartPulse} />
        <StatCard label="Open signals" value={loading ? "…" : openSignals} icon={Activity} />
        <StatCard label="Need coverage" value={loading ? "…" : `${coverage?.coverage_pct ?? 0}%`} icon={Target} />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card
            title={`Customer health · ${health?.total ?? 0} customers`}
            subtitle="The why, not a bare score: every health state lists the signal and commitment factors that produced it."
          >
            {loading ? (
              <div className="flex items-center gap-2 py-6 text-[12px] text-faint">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading customer health
              </div>
            ) : (health?.health ?? []).length === 0 ? (
              <EmptyState
                icon={Users}
                title="No customer health yet"
                description="Signal, commitment and outcome events from the real event stream build each customer's health ledger here."
              />
            ) : (
              <ul className="space-y-2">
                {(health?.health ?? []).map((row) => (
                  <li
                    key={row.customer_id}
                    className="flex flex-col gap-1 rounded-lg border border-border p-3"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <button
                        type="button"
                        onClick={() => openCenter(row.customer_id)}
                        className="text-[13px] font-medium text-white hover:underline"
                        title="Open the customer command center"
                      >
                        {row.customer}
                      </button>
                      <Badge tone={STATE_TONE[row.state] ?? "neutral"}>{row.state}</Badge>
                      <span className="text-[11px] text-faint">{row.score} / 100</span>
                      {row.reasons.slice(0, 3).map((reason) => (
                        <Badge key={reason} tone="warning">
                          {reason}
                        </Badge>
                      ))}
                      {row.positives.slice(0, 2).map((positive) => (
                        <Badge key={positive} tone="success">
                          {positive}
                        </Badge>
                      ))}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card
            title={`Risk propagation · ${risk?.at_risk_customers.length ?? 0} customers · ${risk?.commitments_at_risk.length ?? 0} commitments`}
            subtitle={
              risk?.propagation_note ??
              "A delayed project propagates to the customer commitments linked to it, then to the strategic goals above it."
            }
          >
            {loading ? (
              <div className="flex items-center gap-2 py-6 text-[12px] text-faint">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading risk views
              </div>
            ) : (risk?.at_risk_customers ?? []).length === 0 && (risk?.commitments_at_risk ?? []).length === 0 ? (
              <EmptyState
                icon={ShieldAlert}
                title="Nothing at risk"
                description="No at-risk customers or commitments. Risk only ever propagates from real signal and delivery evidence."
              />
            ) : (
              <ul className="space-y-3">
                {(risk?.at_risk_customers ?? []).map((row) => (
                  <li key={row.customer_id} className="rounded-lg border border-border p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-[13px] font-medium">{row.customer}</span>
                      <Badge tone={STATE_TONE[row.state] ?? "neutral"}>{row.state}</Badge>
                      <span className="text-[11px] text-faint">{row.score} / 100</span>
                      {row.reasons.map((reason) => (
                        <Badge key={reason} tone="danger">
                          {reason}
                        </Badge>
                      ))}
                    </div>
                  </li>
                ))}
                {(risk?.commitments_at_risk ?? []).map((row) => (
                  <li key={row.commitment_id} className="rounded-lg border border-border p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone={STATUS_TONE[row.status] ?? "neutral"}>{row.status}</Badge>
                      <span className="text-[13px] font-medium">{row.customer}</span>
                      <span className="text-[12px]">{row.summary}</span>
                      {row.project && <Badge tone="brand">{row.project}</Badge>}
                      {row.project_health && row.project_health !== "unknown" && (
                        <Badge tone="danger">{row.project_health} project</Badge>
                      )}
                    </div>
                    {(row.goals ?? []).length > 0 && (
                      <div className="mt-2 flex flex-wrap items-center gap-1 text-[11px] text-faint">
                        <TrendingUp className="h-3 w-3" />
                        {row.goals.map((g) => (
                          <span key={g.goal_id} className="rounded bg-surface px-1.5 py-0.5">
                            {g.goal}
                          </span>
                        ))}
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card
            title={`Themes · voice of the customer · ${themes?.themes.length ?? 0}`}
            subtitle="Signals on the same need aggregate into a theme with its evidence — occurrences, distinct customers, open count and high-severity cases."
          >
            {loading ? (
              <div className="flex items-center gap-2 py-6 text-[12px] text-faint">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading themes
              </div>
            ) : (themes?.themes ?? []).length === 0 ? (
              <EmptyState
                icon={Activity}
                title="No customer themes yet"
                description="Voice-of-customer signals (feedback, issues, requests, success, churn risk) aggregate here by need."
              />
            ) : (
              <ul className="space-y-3">
                {(themes?.themes ?? []).map((theme) => (
                  <li key={theme.key} className="rounded-lg border border-border p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone="brand">{theme.key}</Badge>
                      <span className="text-[11px] text-faint">
                        {theme.occurrences} signals · {theme.customers} customers
                      </span>
                      <Badge tone="warning">
                        {theme.open} open
                      </Badge>
                      {theme.high_severity > 0 && <Badge tone="danger">{theme.high_severity} high severity</Badge>}
                    </div>
                    {(theme.evidence ?? []).slice(0, 3).map((evidence, idx) => (
                      <p key={idx} className="mt-1.5 text-[12px] text-faint">
                        <span className="text-white">{evidence.customer}:</span> {evidence.summary}
                      </p>
                    ))}
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>

        <div className="space-y-6">
          <Card
            title={`Coverage vs gaps · ${coverage?.coverage_pct ?? 0}%`}
            subtitle="Which customer needs the execution plan already addresses — and which are open gaps."
          >
            {loading ? (
              <div className="flex items-center gap-2 py-6 text-[12px] text-faint">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading coverage
              </div>
            ) : (coverage?.themes ?? []).length === 0 ? (
              <EmptyState
                icon={MapPin}
                title="No coverage map yet"
                description="Every theme is matched against live projects linked through strategic goals and objectives."
              />
            ) : (
              <ul className="space-y-3">
                {(coverage?.themes ?? []).map((theme) => (
                  <li key={theme.key} className="rounded-lg border border-border p-3">
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge tone="brand">{theme.key}</Badge>
                        {theme.covered ? (
                          <Badge tone="success">covered · {theme.coverage_pct}%</Badge>
                        ) : (
                          <Badge tone="danger">gap</Badge>
                        )}
                      </div>
                      <span className="text-[11px] text-faint">{theme.occurrences} signals</span>
                    </div>
                    {(theme.addressing_projects ?? []).length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {(theme.addressing_projects ?? []).map((p) => (
                          <span key={p.id} className="rounded bg-surface px-1.5 py-0.5 text-[11px] text-faint">
                            {p.name}
                          </span>
                        ))}
                      </div>
                    )}
                  </li>
                ))}
                {(gaps?.gaps ?? []).slice(0, 4).map((gap) => (
                  <li key={gap.key} className="rounded-lg border border-danger/30 bg-danger/5 p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone={IMPACT_TONE[gap.impact] ?? "neutral"}>{gap.impact} impact</Badge>
                      <span className="text-[13px] font-medium">{gap.key}</span>
                    </div>
                    {(gap.evidence ?? []).slice(0, 2).map((evidence, idx) => (
                      <p key={idx} className="mt-1 text-[12px] text-faint">{evidence}</p>
                    ))}
                    {gap.recommendation && (
                      <p className="mt-1.5 text-[11px] text-warning">{gap.recommendation}</p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card
            title={`Opportunities · ${opportunities?.opportunities.length ?? 0}`}
            subtitle="Evidence-backed expansion signals — the engine recommends, a human decides."
          >
            {loading ? (
              <div className="flex items-center gap-2 py-6 text-[12px] text-faint">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading opportunities
              </div>
            ) : (opportunities?.opportunities ?? []).length === 0 ? (
              <EmptyState
                icon={ArrowUpRight}
                title="No opportunities"
                description="Expansion signals with real request evidence surface here — never auto-decided."
              />
            ) : (
              <ul className="space-y-3">
                {(opportunities?.opportunities ?? []).map((opportunity) => (
                  <li key={opportunity.key} className="rounded-lg border border-border p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone="brand">{opportunity.key}</Badge>
                      <span className="text-[11px] text-faint">
                        {opportunity.signals} signals · {opportunity.customers} customers
                      </span>
                      {opportunity.addressed ? (
                        <Badge tone="success">addressed</Badge>
                      ) : (
                        <Badge tone="warning">unaddressed</Badge>
                      )}
                    </div>
                    <div className="mt-2 flex items-start gap-1.5">
                      <Info className="mt-0.5 h-3 w-3 shrink-0 text-brand" />
                      <p className="text-[12px] text-faint">{opportunity.decision_linkage?.note}</p>
                    </div>
                    {opportunity.decision_linkage?.requires_decision && (
                      <Badge tone="neutral">requires a human decision</Badge>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card
            title={`Commitments · ${commitments?.total ?? 0} · ${commitments?.delivered ?? 0} delivered`}
            subtitle="What we promised customers, with dates. Delivery is a governed write."
          >
            {loading ? (
              <div className="flex items-center gap-2 py-6 text-[12px] text-faint">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading commitments
              </div>
            ) : (commitments?.commitments ?? []).length === 0 ? (
              <EmptyState
                icon={Clock}
                title="No commitments"
                description="Deliverable commitments with their dates live here."
              />
            ) : (
              <ul className="space-y-2">
                {(commitments?.commitments ?? []).slice(0, 6).map((row) => (
                  <li key={row.commitment_id} className="rounded-lg border border-border p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone={STATUS_TONE[row.status] ?? "neutral"}>{row.status}</Badge>
                      <span className="text-[13px] font-medium">{row.customer}</span>
                      <span className="text-[12px]">{row.summary}</span>
                    </div>
                    <div className="mt-1.5 flex items-center justify-between gap-2">
                      <span className="text-[11px] text-faint">due {row.expected_at}</span>
                      {canManage && row.status !== "delivered" && (
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => deliver(row.commitment_id)}
                          disabled={actingId === row.commitment_id}
                          aria-label={`Deliver ${row.summary}`}
                        >
                          {actingId === row.commitment_id ? (
                            <Loader2 className="h-3 w-3 animate-spin" />
                          ) : (
                            <CheckCircle2 className="h-3 w-3" />
                          )}
                          Deliver
                        </Button>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card
            title={`Outcomes · ${outcomes?.total ?? 0} · ${outcomes?.improved ?? 0} improved`}
            subtitle="Baseline → target → actual per metric, with the improvement direction."
          >
            {loading ? (
              <div className="flex items-center gap-2 py-6 text-[12px] text-faint">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading outcomes
              </div>
            ) : (outcomes?.outcomes ?? []).length === 0 ? (
              <EmptyState
                icon={TrendingUp}
                title="No outcome evidence"
                description="Recorded metric outcomes land on the customer ledger."
              />
            ) : (
              <ul className="space-y-2">
                {(outcomes?.outcomes ?? []).slice(0, 6).map((row) => (
                  <li key={row.outcome_id} className="rounded-lg border border-border p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-[13px] font-medium">{row.customer}</span>
                      <Badge tone="brand">{row.metric_kind}</Badge>
                      {row.improved && <Badge tone="success">improved</Badge>}
                    </div>
                    <p className="mt-1 text-[11px] text-faint">
                      baseline {row.baseline ?? "—"} → actual {row.actual ?? "—"}
                      {row.target != null && <> · target {row.target}</>}
                      {row.unit ? ` ${row.unit}` : ""}
                      {" · "}
                      {timeAgo(row.recorded_at)}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card
            title={`Knowledge linkage · ${knowledge?.knowledge_coverage_pct ?? 0}%`}
            subtitle="Are customer themes backed by documented organizational knowledge?"
          >
            {(knowledge?.themes ?? []).length === 0 ? (
              <p className="py-4 text-[12px] text-faint">No themes to link yet.</p>
            ) : (
              <ul className="space-y-2">
                {(knowledge?.themes ?? []).map((theme) => (
                  <li key={theme.key} className="flex items-center justify-between gap-2">
                    <Badge tone="brand">{theme.key}</Badge>
                    {theme.knowledge_covered ? (
                      <Badge tone="success">knowledge covered</Badge>
                    ) : (
                      <Badge tone="neutral">no knowledge yet</Badge>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>

      {center && (
        <Card
          title={`Command center · ${center.customer?.company_name ?? ""}`}
          subtitle="One customer's health trail, signal timeline, commitments and outcome evidence."
        >
          <div className="grid gap-6 md:grid-cols-2">
            <div>
              <p className="mb-2 text-[12px] font-medium text-faint">Health trail</p>
              <ul className="space-y-1.5">
                {center.health?.history?.slice(0, 5).map((h, idx) => (
                  <li key={idx} className="flex flex-wrap items-center gap-2 rounded-lg border border-border p-2">
                    <Badge tone={STATE_TONE[h.state] ?? "neutral"}>{h.state}</Badge>
                    <span className="text-[11px] text-faint">{h.score} / 100</span>
                    {(h.reasons ?? []).slice(0, 2).map((reason) => (
                      <Badge key={reason} tone="warning">
                        {reason}
                      </Badge>
                    ))}
                  </li>
                ))}
                {(center.health?.reasons ?? []).length > 0 && (
                  <li className="flex flex-wrap items-center gap-2">
                    {(center.health?.reasons ?? []).slice(0, 3).map((reason) => (
                      <Badge key={reason} tone="danger">
                        {reason}
                      </Badge>
                    ))}
                  </li>
                )}
              </ul>
            </div>
            <div>
              <p className="mb-2 text-[12px] font-medium text-faint">Signal timeline</p>
              <ul className="space-y-1.5">
                {(center.signals ?? []).slice(0, 6).map((s) => (
                  <li key={s.signal_id} className="flex flex-wrap items-center gap-2 rounded-lg border border-border p-2">
                    <Badge tone={SEVERITY_TONE[s.severity] ?? "neutral"}>{s.severity}</Badge>
                    <Badge tone="brand">{s.need}</Badge>
                    <span className="text-[12px]">{s.summary}</span>
                    {["resolved", "closed"].includes(s.status) ? (
                      <Badge tone="success">resolved</Badge>
                    ) : (
                      <Badge tone="warning">open</Badge>
                    )}
                    {canManage && !["resolved", "closed"].includes(s.status) && (
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => resolve(s.signal_id)}
                        disabled={actingId === s.signal_id}
                        aria-label={`Resolve ${s.summary}`}
                      >
                        {actingId === s.signal_id ? (
                          <Loader2 className="h-3 w-3 animate-spin" />
                        ) : (
                          <CircleDashed className="h-3 w-3" />
                        )}
                        Resolve
                      </Button>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          </div>
          {error && (
            <p className="mt-3 rounded-lg border border-danger/30 bg-danger/10 p-2 text-[11px] text-danger">{error}</p>
          )}
        </Card>
      )}
    </div>
  );
}