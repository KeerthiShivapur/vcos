"use client";

import {
  AlertTriangle,
  ArrowRight,
  GitBranch,
  Handshake,
  Loader2,
  Repeat2,
  Route,
  Scale,
  Siren,
  UserCheck,
  Users,
  XCircle,
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
  getCoordinationCenter,
  getCoordinationProject,
  resolveCoordinationIncident,
  type CoordinationAlternative,
  type CoordinationCenterResponse,
  type CoordinationIncidentRow,
  type CoordinationProjectDetail,
  type CoordinationRecommendation,
  type CoordinationWhatIfOption,
} from "@/lib/api";
import { PERMISSIONS } from "@/lib/permissions";
import { timeAgo } from "@/lib/utils";

const SEVERITY_TONE: Record<string, "success" | "warning" | "danger" | "neutral" | "brand"> = {
  critical: "danger",
  high: "warning",
  medium: "warning",
  low: "neutral",
} as const;

const KIND_TONE: Record<string, "danger" | "warning" | "brand" | "neutral" | "success"> = {
  critical_conflict: "danger",
  propagation_risk: "danger",
  shared_capacity: "warning",
  handoff_risk: "warning",
  recurring_handoff: "warning",
  coordination_gap: "brand",
} as const;

const KIND_ICON: Record<string, typeof Scale> = {
  critical_conflict: Siren,
  propagation_risk: GitBranch,
  shared_capacity: Scale,
  handoff_risk: Handshake,
  recurring_handoff: Repeat2,
  coordination_gap: Users,
};

function kindTone(kind: string) {
  return KIND_TONE[kind] ?? "neutral";
}

function propagationLabel(p: unknown): string {
  if (typeof p === "string") return p;
  if (p && typeof p === "object") {
    const o = p as Record<string, unknown>;
    const from = String(o.from ?? "");
    const via = String(o.via ?? "");
    const to = String(o.to ?? "");
    if (from && to) return via ? `${from} ${via} → ${to}` : `${from} → ${to}`;
    const label = o.title ?? o.event_name ?? o.kind;
    if (label) return String(label);
  }
  return JSON.stringify(p);
}

function IncidentCard({
  incident,
  canManage,
  resolving,
  onResolve,
}: {
  incident: CoordinationIncidentRow;
  canManage: boolean;
  resolving: boolean;
  onResolve: (incidentId: string, note: string) => void;
}) {
  const [note, setNote] = useState("");
  const Icon = KIND_ICON[incident.kind] ?? AlertTriangle;
  return (
    <li className="rounded-xl border border-line/70 bg-elevated p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge tone={kindTone(incident.kind)}>{incident.kind}</Badge>
            <Badge tone={SEVERITY_TONE[incident.severity] ?? "neutral"}>{incident.severity}</Badge>
            <span className="text-[11px] text-faint">
              {Math.round(incident.confidence * 100)}% confident
            </span>
            {incident.project_name && (
              <span className="text-[11px] text-faint">· {incident.project_name}</span>
            )}
          </div>
          <p className="mt-1 text-[13px] font-medium text-ink">
            <Icon className="mr-1 inline h-3.5 w-3.5 text-faint" />
            {incident.title}
          </p>
          {incident.summary && (
            <p className="mt-0.5 text-[11px] leading-relaxed text-muted">{incident.summary}</p>
          )}
        </div>
        {canManage && (
          <div className="flex shrink-0 flex-col items-end gap-1.5">
            <input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="resolve note"
              className="w-44 rounded-lg border border-line bg-surface px-2 py-1 text-[11px] text-ink outline-none focus:border-brand"
            />
            <Button
              size="sm"
              variant="secondary"
              onClick={() => onResolve(incident.incident_id, note.trim())}
              disabled={resolving || !note.trim()}
            >
              {resolving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <UserCheck className="h-3.5 w-3.5" />}
              Resolve
            </Button>
          </div>
        )}
      </div>
      {incident.evidence.length > 0 && (
        <ul className="mt-2 flex flex-wrap gap-1.5">
          {incident.evidence.slice(0, 4).map((e, i) => (
            <li key={i} className="rounded-md border border-line/70 bg-surface px-2 py-1 text-[10px] text-faint">
              {e}
            </li>
          ))}
        </ul>
      )}
      {incident.propagation.length > 0 && (
        <p className="mt-1.5 text-[10px] text-faint">
          propagates: {incident.propagation.slice(0, 3).map(propagationLabel).join(" · ")}
        </p>
      )}
      <p className="mt-1.5 text-[10px] text-faint">
        first seen {timeAgo(incident.first_seen_at)} · last seen {timeAgo(incident.last_seen_at)}
      </p>
    </li>
  );
}

function WhatIfOptions({ whatIf }: { whatIf: CoordinationProjectDetail["what_if"] }) {
  if (!whatIf.options.length) {
    return <p className="text-[12px] text-faint">No bounded options for this project right now.</p>;
  }
  return (
    <div className="space-y-2">
      {whatIf.options.map((option) => (
        <OptionCard key={option.kind} option={option} />
      ))}
      <p className="rounded-lg border border-brand/30 bg-brand/5 px-3 py-2 text-[11px] leading-relaxed text-muted">
        {whatIf.boundary}
      </p>
    </div>
  );
}

function OptionCard({ option }: { option: CoordinationWhatIfOption }) {
  return (
    <div className="rounded-lg border border-line/70 bg-surface p-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-[12px] font-semibold text-ink">{option.title}</p>
        <Badge tone={kindTone(option.kind)}>{option.kind}</Badge>
      </div>
      {option.kind === "delay" && option.effects && option.effects.length > 0 && (
        <ul className="mt-1.5 space-y-1">
          {option.effects.map((effect, i) => (
            <li key={i} className="text-[11px] text-muted">
              {effect.surface}: {effect.before} → {effect.after}
            </li>
          ))}
        </ul>
      )}
      {option.kind === "reassign" && option.options && option.options.length > 0 && (
        <ul className="mt-1.5 space-y-1.5">
          {option.options.map((alt: CoordinationAlternative) => (
            <li key={alt.person_id} className="rounded-md border border-line/70 bg-elevated px-2 py-1.5 text-[11px]">
              <span className="font-medium text-ink">{alt.person_label}</span>
              <span className="text-faint">
                {" "}
                · {alt.skill} · expertise {alt.expertise_score} · {alt.availability}
              </span>
              <p className="text-[10px] leading-relaxed text-muted">{alt.reason}</p>
              <p className="text-[10px] text-faint">{alt.boundary}</p>
            </li>
          ))}
        </ul>
      )}
      {option.kind === "knowledge" && option.topics && option.topics.length > 0 && (
        <ul className="mt-1.5 flex flex-wrap gap-1.5">
          {option.topics.map((topic, i) => (
            <li key={i} className="rounded-md border border-line/70 bg-elevated px-2 py-1 text-[10px] text-faint">
              {topic.topic}
            </li>
          ))}
        </ul>
      )}
      {option.triggered_by.length > 0 && (
        <p className="mt-1.5 text-[10px] text-faint">triggered by: {option.triggered_by.join(" · ")}</p>
      )}
      <p className="mt-1.5 text-[10px] leading-relaxed text-muted">{option.boundary}</p>
    </div>
  );
}

function RecommendationRow({ rec }: { rec: CoordinationRecommendation }) {
  return (
    <li className="rounded-lg border border-line/70 bg-surface px-3 py-2">
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge tone={kindTone(rec.kind)}>{rec.kind}</Badge>
        <span className="text-[11px] text-faint">
          priority {Math.round(rec.confidence * 100)}% confidence
        </span>
      </div>
      <p className="mt-1 text-[12px] font-medium text-ink">{rec.summary}</p>
      {rec.why.length > 0 && (
        <p className="mt-0.5 text-[11px] text-faint">{rec.why.join(" · ")}</p>
      )}
    </li>
  );
}

export function CoordinationTab({ onOpenCount }: { onOpenCount?: (open: number) => void }) {
  const { can } = useAuth();
  const canManage = can(PERMISSIONS.PROJECTS_MANAGE);

  const [center, setCenter] = useState<CoordinationCenterResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [detail, setDetail] = useState<CoordinationProjectDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [resolvingId, setResolvingId] = useState<string | null>(null);

  const loadCenter = useCallback(async () => {
    const res = await getCoordinationCenter();
    setCenter(res);
    onOpenCount?.(res.total_incidents);
    return res;
  }, [onOpenCount]);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      await loadCenter();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load the coordination center");
    } finally {
      setLoading(false);
    }
  }, [loadCenter]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function openProject(projectId: string) {
    setDetailLoading(true);
    setError(null);
    try {
      setDetail(await getCoordinationProject(projectId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load the coordination record");
    } finally {
      setDetailLoading(false);
    }
  }

  async function resolve(incidentId: string, note: string) {
    setResolvingId(incidentId);
    setError(null);
    try {
      await resolveCoordinationIncident(incidentId, note);
      const [c, d] = await Promise.all([
        loadCenter(),
        detail ? getCoordinationProject(detail.project_id) : Promise.resolve(null),
      ]);
      setCenter(c);
      if (d) setDetail(d);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to resolve the finding");
    } finally {
      setResolvingId(null);
    }
  }

  if (error && !center && !loading) {
    return <ErrorState title="Could not load the coordination center" message={error} />;
  }

  const counts = center?.counts ?? {
    open: 0, critical: 0, high: 0, medium: 0, low: 0,
  } as CoordinationCenterResponse["counts"];

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <StatCard label="Open findings" value={loading ? "…" : center?.total_incidents ?? 0} icon={AlertTriangle} />
        <StatCard label="Critical" value={loading ? "…" : counts.critical} icon={Siren} />
        <StatCard label="High severity" value={loading ? "…" : counts.high} icon={GitBranch} />
        <StatCard label="Medium + low" value={loading ? "…" : (counts.medium ?? 0) + (counts.low ?? 0)} icon={Scale} />
        <StatCard label="Slow handoffs 30d" value={loading ? "…" : center?.handoffs.slow_30d ?? 0} icon={Repeat2} />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card
            title={`Open coordination findings · ${center?.total_incidents ?? 0}`}
            subtitle="Deterministic dependency intelligence: shared capacity, blocked critical paths, handoffs and gaps — each with evidence and confidence."
          >
            {loading ? (
              <div className="flex items-center gap-2 py-6 text-[12px] text-faint">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading coordination findings
              </div>
            ) : (center?.incidents ?? []).length === 0 ? (
              <EmptyState
                icon={Handshake}
                title="Nothing to coordinate"
                description="No open coordination findings — shared capacity, blocked paths, handoffs and gaps surface here from the real event stream."
              />
            ) : (
              <ul className="space-y-2">
                {(center?.incidents ?? []).map((incident) => (
                  <IncidentCard
                    key={incident.incident_id}
                    incident={incident}
                    canManage={canManage}
                    resolving={resolvingId === incident.incident_id}
                    onResolve={resolve}
                  />
                ))}
              </ul>
            )}
            {error && (
              <p className="mt-2 rounded-lg border border-danger/30 bg-danger/10 p-2 text-[11px] text-danger">{error}</p>
            )}
          </Card>

          <Card
            title={`Recommended focus · ${center?.recommendations.length ?? 0}`}
            subtitle="Deterministic priorities: critical conflicts first, then shared capacity, propagation, handoffs, gaps."
          >
            {loading ? (
              <div className="flex items-center gap-2 py-6 text-[12px] text-faint">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Ranking
              </div>
            ) : (center?.recommendations ?? []).length === 0 ? (
              <EmptyState icon={Route} title="No recommendations" description="Nothing pressing to coordinate right now." />
            ) : (
              <ol className="space-y-1.5">
                {(center?.recommendations ?? []).map((rec) => (
                  <RecommendationRow key={rec.incident_id} rec={rec} />
                ))}
              </ol>
            )}
          </Card>
        </div>

        <div className="space-y-6">
          <Card title="Handoff ledger" subtitle="Ownership transitions, measured, never guessed.">
            {loading ? (
              <div className="flex items-center gap-2 py-6 text-[12px] text-faint">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading
              </div>
            ) : (
              <div className="space-y-1.5 text-[12px]">
                <p className="flex items-center justify-between">
                  <span className="text-muted">Pending handoffs</span>
                  <Badge tone={center?.handoffs.pending ? "warning" : "neutral"}>
                    {center?.handoffs.pending ?? 0}
                  </Badge>
                </p>
                <p className="flex items-center justify-between">
                  <span className="text-muted">Completed</span>
                  <Badge tone="neutral">{center?.handoffs.completed ?? 0}</Badge>
                </p>
                <p className="flex items-center justify-between">
                  <span className="text-muted">Avg duration</span>
                  <Badge tone="neutral">
                    {center?.handoffs.avg_duration_hours == null
                      ? "—"
                      : `${center.handoffs.avg_duration_hours}h`}
                  </Badge>
                </p>
                <p className="flex items-center justify-between">
                  <span className="text-muted">Slow in 30d (72h+)</span>
                  <Badge tone={(center?.handoffs.slow_30d ?? 0) > 0 ? "warning" : "neutral"}>
                    {center?.handoffs.slow_30d ?? 0}
                  </Badge>
                </p>
              </div>
            )}
          </Card>

          <Card
            title="Entangled projects"
            subtitle="Projects with open coordination findings."
          >
            {loading ? (
              <div className="flex items-center gap-2 py-6 text-[12px] text-faint">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading
              </div>
            ) : (center?.projects_affected ?? []).length === 0 ? (
              <p className="text-[12px] text-faint">No entangled projects.</p>
            ) : (
              <ul className="space-y-1.5">
                {(center?.projects_affected ?? []).map((p) => (
                  <li key={p.project_id}>
                    <button
                      type="button"
                      onClick={() => openProject(p.project_id)}
                      className="flex w-full items-center justify-between gap-2 rounded-lg border border-line/70 bg-surface px-3 py-2 text-left hover:border-brand/40"
                    >
                      <span className="min-w-0 truncate text-[12px] font-medium text-ink">{p.name}</span>
                      <span className="flex shrink-0 items-center gap-1.5">
                        <Badge tone="warning">{p.incident_count} finding(s)</Badge>
                        <ArrowRight className="h-3.5 w-3.5 text-faint" />
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="Advisory only" subtitle="Nothing here moves people or work.">
            <div className="flex items-center gap-2 text-[12px] text-muted">
              <UserCheck className="h-3.5 w-3.5 shrink-0 text-faint" />
              Findings, handoffs and what-if options are evidence for humans — the system never reassigns or reschedules anything.
            </div>
          </Card>
        </div>
      </div>

      {detail && (
        <Card
          title={`${detail.name} · coordination record`}
          subtitle={`${detail.code} · ${detail.status}`}
          actions={
            <Button variant="ghost" size="sm" onClick={() => setDetail(null)} aria-label="Close coordination record">
              <XCircle className="h-4 w-4" />
            </Button>
          }
        >
          {detailLoading ? (
            <div className="flex items-center gap-2 py-6 text-[12px] text-faint">
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading the coordination record
            </div>
          ) : (
            <div className="grid gap-6 lg:grid-cols-2">
              <div className="space-y-4">
                <div>
                  <p className="mb-1.5 text-[12px] font-semibold text-ink">
                    <Handshake className="mr-1 inline h-3.5 w-3.5 text-faint" /> Findings · {detail.incidents.length}
                  </p>
                  {detail.incidents.length === 0 ? (
                    <p className="text-[12px] text-faint">No open findings for this project.</p>
                  ) : (
                    <ul className="space-y-2">
                      {detail.incidents.map((incident) => (
                        <IncidentCard
                          key={incident.incident_id}
                          incident={incident}
                          canManage={canManage}
                          resolving={resolvingId === incident.incident_id}
                          onResolve={resolve}
                        />
                      ))}
                    </ul>
                  )}
                </div>

                <div>
                  <p className="mb-1.5 text-[12px] font-semibold text-ink">
                    <Repeat2 className="mr-1 inline h-3.5 w-3.5 text-faint" /> Handoff ledger
                  </p>
                  {detail.handoffs.pending.length === 0 && detail.handoffs.recent_completed.length === 0 ? (
                    <p className="text-[12px] text-faint">No handoffs recorded yet.</p>
                  ) : (
                    <div className="space-y-3">
                      {detail.handoffs.pending.length > 0 && (
                        <div>
                          <p className="mb-1 text-[11px] font-medium text-warning">pending</p>
                          <ul className="space-y-1.5">
                            {detail.handoffs.pending.map((h) => (
                              <li key={h.task_id} className="rounded-lg border border-line/70 bg-surface px-3 py-2">
                                <p className="text-[12px] font-medium text-ink">{h.task_title}</p>
                                <p className="text-[11px] text-faint">
                                  {h.from_owner} → {h.to_owner} · pending {h.pending_hours}h
                                </p>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {detail.handoffs.recent_completed.length > 0 && (
                        <div>
                          <p className="mb-1 text-[11px] font-medium text-faint">recent completed</p>
                          <ul className="space-y-1.5">
                            {detail.handoffs.recent_completed.map((h) => (
                              <li key={h.task_id} className="rounded-lg border border-line/70 bg-surface px-3 py-2">
                                <p className="text-[12px] font-medium text-ink">{h.task_title}</p>
                                <p className="text-[11px] text-faint">
                                  {h.from_owner} → {h.to_owner} · {h.duration_hours}h · {timeAgo(h.completed_at)}
                                </p>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {detail.propagation.length > 0 && (
                  <div>
                    <p className="mb-1.5 text-[12px] font-semibold text-ink">
                      <GitBranch className="mr-1 inline h-3.5 w-3.5 text-faint" /> Propagation history
                    </p>
                    <ul className="space-y-1">
                      {detail.propagation.slice(0, 8).map((h, i) => (
                        <li key={i} className="flex items-center gap-2 text-[11px] text-faint">
                          <Badge tone={SEVERITY_TONE[h.severity] ?? "neutral"}>{h.kind}</Badge>
                          <span className="font-medium text-ink">{h.title}</span>
                          <span className="ml-auto">{timeAgo(h.occurred_at)}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>

              <div className="space-y-4">
                <div>
                  <p className="mb-1.5 text-[12px] font-semibold text-ink">
                    <Scale className="mr-1 inline h-3.5 w-3.5 text-faint" /> What if we change course?
                  </p>
                  <WhatIfOptions whatIf={detail.what_if} />
                </div>
                {detail.alternatives.length > 0 && (
                  <div>
                    <p className="mb-1.5 text-[12px] font-semibold text-ink">
                      <UserCheck className="mr-1 inline h-3.5 w-3.5 text-faint" /> Alternative owners
                    </p>
                    <ul className="space-y-1.5">
                      {detail.alternatives.map((alt) => (
                        <li key={alt.person_id} className="rounded-lg border border-line/70 bg-surface px-3 py-2">
                          <p className="text-[12px] font-medium text-ink">{alt.person_label}</p>
                          <p className="text-[11px] text-faint">
                            {alt.skill} · expertise {alt.expertise_score} · {alt.availability}
                          </p>
                          <p className="mt-0.5 text-[10px] leading-relaxed text-muted">{alt.boundary}</p>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {detail.recommendations.length > 0 && (
                  <div>
                    <p className="mb-1.5 text-[12px] font-semibold text-ink">
                      <Route className="mr-1 inline h-3.5 w-3.5 text-faint" /> Recommended focus
                    </p>
                    <ol className="space-y-1.5">
                      {detail.recommendations.map((rec) => (
                        <RecommendationRow key={rec.incident_id} rec={rec} />
                      ))}
                    </ol>
                  </div>
                )}
              </div>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
