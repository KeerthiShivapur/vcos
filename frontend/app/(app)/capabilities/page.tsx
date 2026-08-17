"use client";

import {
  AlertTriangle,
  ArrowUpRight,
  Boxes,
  CheckCircle2,
  CircleGauge,
  Loader2,
  SearchCheck,
  Sparkles,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { PageHeader, StatCard } from "@/components/ui/PageHeader";
import { useAuth } from "@/hooks/useAuth";
import {
  acknowledgeCapabilitySignal,
  analyzeCapabilityInitiative,
  getCapabilityDetail,
  getCapabilityOverview,
  getCapabilitySignals,
  type CapabilityBrief,
  type CapabilityDetail as CapabilityDetailRow,
  type CapabilityInitiativeAnswer,
  type CapabilitySignalRow,
  type CapabilityOverview,
} from "@/lib/api";
import { PERMISSIONS } from "@/lib/permissions";
import { timeAgo } from "@/lib/utils";

const LIFECYCLE_TONE: Record<string, "success" | "brand" | "warning" | "neutral" | "danger"> = {
  strategic: "success",
  strong: "success",
  established: "brand",
  emerging: "neutral",
  declining: "warning",
  dormant: "danger",
} as const;

const CAPACITY_TONE: Record<string, "success" | "brand" | "warning" | "danger" | "neutral"> = {
  available: "success",
  tight: "warning",
  constrained: "danger",
  stretched: "warning",
  unknown: "neutral",
} as const;

const DEMAND_TONE: Record<string, "brand" | "neutral" | "danger"> = {
  active: "brand",
  none: "neutral",
  constrained: "danger",
} as const;

const SIGNAL_KIND_TONE: Record<string, "warning" | "danger" | "brand" | "neutral"> = {
  concentration: "warning",
  single_point_dependency: "danger",
  capacity_constraint: "danger",
  capability_gap: "warning",
  emerging_without_capacity: "neutral",
  capacity_without_expertise: "brand",
} as const;

const READINESS_TONE: Record<string, "success" | "warning" | "danger"> = {
  ready: "success",
  partial: "warning",
  gap: "danger",
} as const;

export default function CapabilitiesPage() {
  const { can } = useAuth();
  const canManage = can(PERMISSIONS.EMPLOYEES_MANAGE);

  const [overview, setOverview] = useState<CapabilityOverview | null>(null);
  const [signals, setSignals] = useState<CapabilitySignalRow[]>([]);
  const [signalsTotal, setSignalsTotal] = useState(0);
  const [detail, setDetail] = useState<CapabilityDetailRow | null>(null);
  const [question, setQuestion] = useState("");
  const [initiative, setInitiative] = useState<{
    answer: string;
    answers: CapabilityInitiativeAnswer[];
  } | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async (opts: { silent?: boolean } = {}) => {
    if (!opts.silent) setLoading(true);
    setError(null);
    try {
      const [ov, sig] = await Promise.all([getCapabilityOverview(), getCapabilitySignals()]);
      setOverview(ov);
      setSignals(sig.signals);
      setSignalsTotal(sig.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load capability intelligence");
    } finally {
      if (!opts.silent) setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function openDetail(skillId: string) {
    setError(null);
    setDetail(null);
    try {
      setDetail(await getCapabilityDetail(skillId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load capability detail");
    }
  }

  async function acknowledge(signalId: string) {
    try {
      await acknowledgeCapabilitySignal(signalId);
      setSignals((prev) => prev.filter((s) => s.signal_id !== signalId));
      setSignalsTotal((t) => Math.max(0, t - 1));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to acknowledge signal");
    }
  }

  async function runInitiative() {
    const q = question.trim();
    if (!q) return;
    setRunning(true);
    setError(null);
    try {
      const res = await analyzeCapabilityInitiative(q);
      setInitiative({ answer: res.answer, answers: res.answers });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to analyze initiative");
    } finally {
      setRunning(false);
    }
  }

  if (error && !overview && !loading) {
    return (
      <div className="space-y-6">
        <PageHeader
          title="Capability Center"
          breadcrumb="Brain"
          description="What the organization can actually deliver — lifecycle, capacity, demand, concentration and gaps, all evidence-backed and explainable."
        />
        <ErrorState title="Could not load capability intelligence" message={error} />
      </div>
    );
  }

  const strongCount = (overview?.by_state?.strategic ?? 0) + (overview?.by_state?.strong ?? 0);
  const inDemand = (overview?.capabilities ?? []).filter((c) => c.demand_count > 0).length;
  const stateEntries = Object.entries(overview?.by_state ?? {}).sort((a, b) => b[1] - a[1]);

  function CapRows({ rows, emptyTitle, emptyText }: { rows: CapabilityBrief[]; emptyTitle: string; emptyText: string }) {
    if (rows.length === 0) return <EmptyState icon={Boxes} title={emptyTitle} description={emptyText} />;
    return (
      <ul className="space-y-2">
        {rows.map((c) => (
          <li key={c.skill_id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-line/70 bg-elevated p-3">
            <button
              type="button"
              onClick={() => openDetail(c.skill_id)}
              className="min-w-0 text-left"
              title={c.explain}
            >
              <p className="text-[13px] font-medium text-ink hover:text-brand">{c.name}</p>
              <p className="text-[11px] text-faint">
                {c.expert_count} expert(s) · {c.evidence_count} evidence · {c.confidence.toFixed(2)} confidence
                {c.demand_count > 0 ? ` · ${c.demand_count} project(s) in demand` : ""}
              </p>
            </button>
            <div className="flex shrink-0 items-center gap-1.5">
              <Badge tone={LIFECYCLE_TONE[c.lifecycle] ?? "neutral"}>{c.lifecycle}</Badge>
              <Badge tone={CAPACITY_TONE[c.capacity_state] ?? "neutral"}>{c.capacity_state}</Badge>
              <span className="text-[12px] font-semibold text-ink">{c.capacity_available} free</span>
            </div>
          </li>
        ))}
      </ul>
    );
  }

  const countBy = (list: CapabilityBrief[]) => list.length;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Capability Center"
        breadcrumb="Brain"
        description="What the organization can actually deliver — lifecycle, capacity = potential − committed − reserved, demand, concentration and gaps. Every row is evidence-backed; advisory signals never change the organization."
      />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Capabilities" value={overview?.total ?? (loading ? "…" : 0)} icon={Boxes} />
        <StatCard label="Strong / strategic" value={loading ? "…" : strongCount} icon={TrendingUp} />
        <StatCard label="In demand" value={loading ? "…" : inDemand} icon={SearchCheck} />
        <StatCard label="Open signals" value={loading ? "…" : signalsTotal} icon={AlertTriangle} />
      </div>

      {stateEntries.length > 0 && (
        <Card title="Lifecycle distribution" subtitle="Where the organization's capabilities stand, by evidence band.">
          <div className="flex flex-wrap gap-2">
            {stateEntries.map(([state, count]) => (
              <Badge key={state} tone={LIFECYCLE_TONE[state] ?? "neutral"}>
                {state} · {count}
              </Badge>
            ))}
          </div>
        </Card>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Strong capabilities" subtitle="Proven delivery capacity — strong and strategic, top of the list.">
          {loading ? (
            <div className="flex items-center gap-2 py-6 text-[12px] text-faint">
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading capabilities
            </div>
          ) : (
            <CapRows
              rows={overview?.strong ?? []}
              emptyTitle="No strong capabilities yet"
              emptyText="Capabilities reach strong once multiple experts carry consistent, corroborated evidence."
            />
          )}
        </Card>

        <Card title="Emerging" subtitle="Early evidence — worth attention before capability gaps form.">
          <CapRows
            rows={overview?.emerging ?? []}
            emptyTitle="Nothing emerging"
            emptyText="New expertise evidence will surface emerging capabilities here."
          />
        </Card>

        <Card title="Constrained" subtitle="Demand is at or beyond what the freed evidence can carry.">
          <CapRows
            rows={overview?.constrained ?? []}
            emptyTitle="No constraints"
            emptyText="No capability is stretched or constrained right now."
          />
        </Card>

        <Card title="Concentration risks" subtitle="A small number of experts carry a large share of the evidence.">
          <CapRows
            rows={overview?.concentration_risks ?? []}
            emptyTitle="No concentration risk"
            emptyText="No capability is concentrated in two or fewer experts beyond the advisory threshold."
          />
        </Card>

        <Card title="Capability gaps" subtitle="In-demand capabilities with no free experts to staff them.">
          <CapRows
            rows={overview?.gaps ?? []}
            emptyTitle="No gaps"
            emptyText="Every in-demand capability still has available experts."
          />
        </Card>

        <Card
          title="CEO readiness"
          subtitle='"Can we take this on?" — deterministic, evidence-backed. Never a forecast and never a guarantee.'
        >
          <div className="flex gap-2">
            <input
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && runInitiative()}
              placeholder='e.g. "We are being asked to build a platform for Kubernetes delivery"'
              className="flex-1 rounded-lg border border-line bg-surface px-3 py-2 text-[13px] text-ink outline-none focus:border-brand"
            />
            <Button size="sm" onClick={runInitiative} disabled={running || !question.trim()}>
              {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
              Analyze
            </Button>
          </div>
          {initiative && (
            <div className="mt-3 space-y-3">
              <p className="rounded-xl border border-brand/30 bg-brand/5 p-3 text-[12px] leading-relaxed text-ink">
                {initiative.answer}
              </p>
              {initiative.answers.length > 0 && (
                <ul className="space-y-1.5">
                  {initiative.answers.map((a) => (
                    <li key={a.skill_id} className="flex items-center justify-between gap-3 rounded-lg border border-line/70 bg-elevated px-3 py-2">
                      <div className="min-w-0">
                        <p className="text-[12px] font-medium text-ink">{a.skill_name}</p>
                        <p className="truncate text-[11px] text-faint">{a.reason}</p>
                      </div>
                      <Badge tone={READINESS_TONE[a.readiness] ?? "neutral"}>{a.readiness}</Badge>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </Card>
      </div>

      <Card title="Open signals" subtitle={`${signalsTotal} advisory signal(s) awaiting acknowledgement. Advisory only — acknowledging changes nothing in the organization.`}>
        {loading ? (
          <div className="flex items-center gap-2 py-6 text-[12px] text-faint">
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading signals
          </div>
        ) : signals.length === 0 ? (
          <EmptyState icon={AlertTriangle} title="No open signals" description="Concentration, single-point dependency, constraint and gap signals appear here as evidence accumulates." />
        ) : (
          <ul className="space-y-2">
            {signals.map((signal) => (
              <li key={signal.signal_id} className="flex items-start justify-between gap-3 rounded-xl border border-line/70 bg-elevated p-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Badge tone={SIGNAL_KIND_TONE[signal.kind] ?? "neutral"}>{signal.kind}</Badge>
                    <Badge tone="neutral">{signal.severity}</Badge>
                    <span className="text-[12px] font-medium text-ink">{signal.skill_name}</span>
                  </div>
                  <p className="mt-1 text-[12px] leading-relaxed text-muted">{signal.detail}</p>
                  <p className="mt-1 text-[11px] text-faint">raised {timeAgo(signal.created_at)}</p>
                </div>
                {canManage && (
                  <Button variant="ghost" size="sm" onClick={() => acknowledge(signal.signal_id)}>
                    <CheckCircle2 className="h-4 w-4" /> Acknowledge
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card
        title={`All capabilities · ${overview?.total ?? 0}`}
        subtitle="Evidence-backed capabilities in the canonical taxonomy. Click a row for full detail: experts, capacity model, demand, owners, teams, projects, history and adjacencies."
      >
        {loading ? (
          <div className="flex items-center gap-2 py-6 text-[12px] text-faint">
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading capabilities
          </div>
        ) : !overview || overview.capabilities.length === 0 ? (
          <EmptyState icon={Boxes} title="No capabilities yet" description="Capabilities are discovered as task completions, projects and decisions produce expertise evidence — never by scanning." />
        ) : (
          <div className="space-y-4">
            <ul className="space-y-2">
              {overview.capabilities.map((c) => (
                <li key={c.skill_id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-line/70 bg-elevated p-3">
                  <button type="button" onClick={() => openDetail(c.skill_id)} className="min-w-0 text-left" title={c.explain}>
                    <p className="text-[13px] font-medium text-ink hover:text-brand">{c.name}</p>
                    <p className="text-[11px] text-faint">
                      {c.category ?? "uncategorized"} · {c.expert_count} expert(s) · {c.evidence_count} evidence
                    </p>
                  </button>
                  <div className="flex shrink-0 items-center gap-1.5">
                    <Badge tone={LIFECYCLE_TONE[c.lifecycle] ?? "neutral"}>{c.lifecycle}</Badge>
                    <Badge tone={DEMAND_TONE[c.demand_state] ?? "neutral"}>
                      {c.demand_count > 0 ? `demand ${c.demand_count}` : "no demand"}
                    </Badge>
                    <Badge tone={CAPACITY_TONE[c.capacity_state] ?? "neutral"}>{c.capacity_state}</Badge>
                  </div>
                </li>
              ))}
            </ul>

            {detail && (
              <div className="rounded-2xl border border-brand/40 bg-elevated p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <CircleGauge className="h-4 w-4 text-brand" />
                    <p className="text-[14px] font-semibold text-ink">{detail.name}</p>
                    <Badge tone={LIFECYCLE_TONE[detail.lifecycle] ?? "neutral"}>{detail.lifecycle}</Badge>
                    <Badge tone={CAPACITY_TONE[detail.capacity.state] ?? "neutral"}>{detail.capacity.state}</Badge>
                  </div>
                  <p className="text-[11px] text-faint">
                    {detail.expert_count} expert(s) · {detail.strong_expert_count} strong · {detail.evidence_count} evidence · confidence {(detail.confidence * 100).toFixed(0)}%
                  </p>
                </div>
                <p className="mt-2 text-[12px] leading-relaxed text-muted">{detail.explain}</p>

                <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  <div className="rounded-xl border border-line/70 bg-surface p-3">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-faint">Capacity model</p>
                    <p className="mt-1 text-[12px] text-muted">
                      potential <span className="font-semibold text-ink">{detail.capacity.potential}</span> · committed{" "}
                      <span className="font-semibold text-ink">{detail.capacity.committed}</span> · reserved{" "}
                      <span className="font-semibold text-ink">{detail.capacity.reserved}</span>
                    </p>
                    <p className="mt-1 text-[13px] font-semibold text-ink">{detail.capacity.available} free expert(s)</p>
                  </div>
                  <div className="rounded-xl border border-line/70 bg-surface p-3">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-faint">Demand</p>
                    <p className="mt-1 text-[13px] font-semibold text-ink">{detail.demand.count} active project(s)</p>
                    <p className="text-[11px] text-faint">{detail.demand.state}</p>
                  </div>
                  <div className="rounded-xl border border-line/70 bg-surface p-3">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-faint">Concentration</p>
                    <p className="mt-1 text-[13px] font-semibold text-ink">{(detail.concentration.share * 100).toFixed(0)}%</p>
                    <p className="text-[11px] text-faint">
                      top expert share · second {(detail.concentration.second_share * 100).toFixed(0)}%
                    </p>
                  </div>
                  <div className="rounded-xl border border-line/70 bg-surface p-3">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-faint">Counts</p>
                    <p className="mt-1 text-[12px] text-muted">
                      {detail.counts.owners} owner(s) · {detail.counts.teams} team(s) · {detail.counts.knowledge} topic(s)
                    </p>
                    <p className="mt-1 text-[11px] text-faint">
                      outcome ratio {(detail.outcome_ratio * 100).toFixed(0)}% · {detail.corroborated_kinds.length} corroborated kind(s)
                    </p>
                  </div>
                </div>

                <div className="mt-3 grid gap-3 lg:grid-cols-2">
                  <div>
                    <p className="mb-1.5 text-[12px] font-semibold text-ink">Experts</p>
                    {detail.experts.length === 0 ? (
                      <p className="text-[11px] text-faint">No experts yet.</p>
                    ) : (
                      <ul className="space-y-1.5">
                        {detail.experts.map((e) => (
                          <li key={e.person_id} className="flex items-center justify-between gap-3 rounded-lg border border-line/70 bg-surface px-3 py-2">
                            <div>
                              <p className="text-[12px] font-medium text-ink">{e.name}</p>
                              <p className="text-[11px] text-faint">
                                {e.lifecycle} · {e.evidence_count} evidence · {(e.confidence * 100).toFixed(0)}% confidence
                              </p>
                            </div>
                            <span className="shrink-0 text-[12px] font-semibold text-ink">{e.score.toFixed(2)}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                    {detail.teams.length > 0 && (
                      <>
                        <p className="mb-1.5 mt-3 text-[12px] font-semibold text-ink">Teams</p>
                        <ul className="space-y-1.5">
                          {detail.teams.map((t) => (
                            <li key={t.team_id} className="rounded-lg border border-line/70 bg-surface px-3 py-2 text-[12px] text-muted">
                              {t.name} · {t.experts} expert(s)
                            </li>
                          ))}
                        </ul>
                      </>
                    )}
                  </div>
                  <div>
                    <p className="mb-1.5 text-[12px] font-semibold text-ink">Adjacent capabilities</p>
                    {detail.adjacent.length === 0 ? (
                      <p className="text-[11px] text-faint">No adjacencies in the taxonomy neighborhood yet.</p>
                    ) : (
                      <ul className="space-y-1.5">
                        {detail.adjacent.slice(0, 10).map((a) => (
                          <li key={a.skill_id}>
                            <button
                              type="button"
                              onClick={() => openDetail(a.skill_id)}
                              className="flex w-full items-center justify-between gap-3 rounded-lg border border-line/70 bg-surface px-3 py-2 text-left hover:border-brand/50"
                            >
                              <span className="text-[12px] font-medium text-ink hover:text-brand">{a.name}</span>
                              <span className="shrink-0 text-[11px] text-faint">{a.shared_experts} shared expert(s)</span>
                            </button>
                          </li>
                        ))}
                      </ul>
                    )}
                    {(detail.projects.length > 0 || detail.history.length > 0 || detail.signals.length > 0) && (
                      <>
                        {detail.projects.length > 0 && (
                          <>
                            <p className="mb-1.5 mt-3 text-[12px] font-semibold text-ink">Projects · {detail.projects.length}</p>
                            <ul className="space-y-1.5">
                              {detail.projects.slice(0, 5).map((p) => (
                                <li key={p.project_id} className="flex items-center justify-between gap-3 rounded-lg border border-line/70 bg-surface px-3 py-2">
                                  <span className="truncate text-[12px] font-medium text-ink">{p.project_name}</span>
                                  <Badge tone="neutral">{p.status}</Badge>
                                </li>
                              ))}
                            </ul>
                          </>
                        )}
                        {detail.signals.length > 0 && (
                          <>
                            <p className="mb-1.5 mt-3 text-[12px] font-semibold text-ink">Signals</p>
                            <ul className="space-y-1.5">
                              {detail.signals.map((s) => (
                                <li key={s.signal_id} className="flex items-center gap-2 rounded-lg border border-line/70 bg-surface px-3 py-2">
                                  <Badge tone={SIGNAL_KIND_TONE[s.kind] ?? "neutral"}>{s.kind}</Badge>
                                  <span className="truncate text-[11px] text-muted">{s.detail}</span>
                                </li>
                              ))}
                            </ul>
                          </>
                        )}
                      </>
                    )}
                  </div>
                </div>

                {detail.factors && Object.keys(detail.factors).length > 0 && (
                  <p className="mt-3 rounded-xl border border-line/70 bg-surface p-3 text-[11px] leading-relaxed text-faint">
                    <span className="font-semibold text-ink">Why we believe this</span> · {Object.entries(detail.factors).map(([k, v]) => `${k}: ${v}`).join(" · ")}
                  </p>
                )}
              </div>
            )}
          </div>
        )}
      </Card>
    </div>
  );
}