"use client";

import {
  AlertTriangle,
  ArrowUpRight,
  CircleGauge,
  Loader2,
  Network,
  RefreshCw,
  SearchCheck,
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
  getCollaborationChanges,
  getCollaborationOverview,
  getCollaborationProject,
  getCollaborationSignals,
  listProjects,
  resolveCollaborationSignal,
  runCollaborationGapAnalysis,
  type CollaborationChangesResponse,
  type CollaborationOverview,
  type CollaborationRelationshipRow,
  type CollaborationSignalRow,
} from "@/lib/api";
import { roleCan, PERMISSIONS } from "@/lib/permissions";
import { timeAgo } from "@/lib/utils";

const HEALTH_TONE: Record<
  string,
  "success" | "brand" | "warning" | "neutral" | "danger"
> = {
  strong: "success",
  healthy: "brand",
  strengthening: "brand",
  emerging: "neutral",
  weakening: "warning",
  dormant: "danger",
} as const;

const CHANGE_TONE: Record<
  string,
  "neutral" | "brand" | "warning" | "danger" | "success"
> = {
  emerging: "neutral",
  strengthening: "success",
  weakening: "warning",
  dormant: "danger",
} as const;

const SIGNAL_KIND_TONE: Record<string, "neutral" | "warning" | "danger"> = {
  gap: "warning",
  slowdown: "danger",
  concentration: "warning",
} as const;

function pairLabel(row: CollaborationRelationshipRow): string {
  return `${row.person_a_label ?? row.person_a_id} ↔ ${row.person_b_label ?? row.person_b_id}`;
}

export default function CollaborationPage() {
  const { user } = useAuth();
  const canManage = roleCan(user?.role || "", PERMISSIONS.EMPLOYEES_MANAGE);

  const [overview, setOverview] = useState<CollaborationOverview | null>(null);
  const [changes, setChanges] = useState<CollaborationChangesResponse | null>(
    null,
  );
  const [signals, setSignals] = useState<CollaborationSignalRow[]>([]);
  const [signalsTotal, setSignalsTotal] = useState(0);
  const [projectId, setProjectId] = useState<string>("");
  const [projects, setProjects] = useState<{ id: string; name: string }[]>([]);
  const [projectView, setProjectView] = useState<{
    project_name: string;
    total_evidence: number;
    people: {
      person_id: string;
      evidence_count: number;
      share_of_project_evidence: number;
    }[];
    top_pairs: {
      person_a_label: string | null;
      person_b_label: string | null;
      evidence_count: number;
      successes: number;
      failures: number;
    }[];
    dependency_concentration: {
      person_a_label: string | null;
      person_b_label: string | null;
      share_of_project_evidence: number;
      advisory: string;
    } | null;
  } | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async (opts: { silent?: boolean } = {}) => {
    if (!opts.silent) setLoading(true);
    setError(null);
    try {
      const [ov, ch, sig] = await Promise.all([
        getCollaborationOverview(),
        getCollaborationChanges(30, 20),
        getCollaborationSignals(undefined, "open", 100),
      ]);
      setOverview(ov);
      setChanges(ch);
      setSignals(sig.signals);
      setSignalsTotal(sig.total);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to load collaboration graph",
      );
    } finally {
      if (!opts.silent) setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    (async () => {
      try {
        const rows = await listProjects();
        setProjects(rows.map((p) => ({ id: p.id, name: p.name })));
      } catch {
        setProjects([]);
      }
    })();
  }, []);

  async function loadProjectView() {
    if (!projectId) return;
    setError(null);
    try {
      const view = await getCollaborationProject(projectId);
      setProjectView(view);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to load project collaboration",
      );
    }
  }

  useEffect(() => {
    if (projectId) loadProjectView();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  async function runAnalysis() {
    setRunning(true);
    setError(null);
    try {
      const res = await runCollaborationGapAnalysis();
      await refresh({ silent: true });
      setError(null);
      return res;
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to run gap analysis",
      );
      return null;
    } finally {
      setRunning(false);
    }
  }

  async function resolve(signalId: string) {
    try {
      await resolveCollaborationSignal(signalId);
      setSignals((prev) => prev.filter((s) => s.id !== signalId));
      setSignalsTotal((t) => Math.max(0, t - 1));
      await refresh({ silent: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to resolve signal");
    }
  }

  if (error && !overview && !loading) {
    return (
      <div className="space-y-6">
        <PageHeader
          title="Work Collaboration"
          breadcrumb="Brain"
          description="Who works with whom — evidence-backed pairs, health and advisory signals. Analysis is advisory only and never changes people, teams or projects."
        />
        <ErrorState
          title="Could not load the collaboration graph"
          message={error}
        />
      </div>
    );
  }

  const healthEntries = Object.entries(overview?.health ?? {}).sort(
    (a, b) => b[1] - a[1],
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title="Work Collaboration"
        breadcrumb="Brain"
        description="Who works with whom — evidence-backed pairs, health and advisory signals. Analysis is advisory only and never changes people, teams or projects."
        actions={
          canManage ? (
            <Button size="sm" onClick={runAnalysis} disabled={running}>
              {running ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <SearchCheck className="h-4 w-4" />
              )}
              Run gap analysis
            </Button>
          ) : undefined
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Relationships"
          value={overview?.total_relationships ?? (loading ? "…" : 0)}
          icon={Network}
        />
        <StatCard
          label="Cross-functional"
          value={
            overview?.cross_functional_relationships ?? (loading ? "…" : 0)
          }
          icon={ArrowUpRight}
        />
        <StatCard
          label="Open signals"
          value={loading ? "…" : signalsTotal}
          icon={AlertTriangle}
        />
        <StatCard
          label="Org strength"
          value={
            overview?.org_rollup
              ? overview.org_rollup.total_strength.toFixed(2)
              : loading
                ? "…"
                : "0.00"
          }
          icon={CircleGauge}
        />
      </div>

      {healthEntries.length > 0 && (
        <Card
          title="Relationship health"
          subtitle="Distribution of the collaboration graph by health state."
        >
          <div className="flex flex-wrap gap-2">
            {healthEntries.map(([state, count]) => (
              <Badge key={state} tone={HEALTH_TONE[state] ?? "neutral"}>
                {state} · {count}
              </Badge>
            ))}
          </div>
        </Card>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card
          title="Strongest pairs"
          subtitle="Top relationships by collaboration strength (advisory)."
        >
          {loading ? (
            <div className="flex items-center gap-2 py-6 text-[12px] text-faint">
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading pairs
            </div>
          ) : (overview?.strongest ?? []).length === 0 ? (
            <EmptyState
              icon={Network}
              title="No strong pairs yet"
              description="Pairs appear as shared work, meetings and decisions accumulate evidence."
            />
          ) : (
            <ul className="space-y-2">
              {(overview?.strongest ?? []).map((row) => (
                <li
                  key={row.id}
                  className="flex items-center justify-between gap-3 rounded-xl border border-line/70 bg-elevated p-3"
                >
                  <div className="min-w-0">
                    <p className="truncate text-[13px] font-medium text-ink">
                      {pairLabel(row)}
                    </p>
                    <p className="text-[11px] text-faint">
                      {row.evidence_count} evidence item(s) ·{" "}
                      {row.successful_interactions} ok /{" "}
                      {row.failed_interactions} fail
                    </p>
                  </div>
                  <div className="text-right">
                    <Badge tone={HEALTH_TONE[row.health_state] ?? "neutral"}>
                      {row.health_state}
                    </Badge>
                    <p className="mt-1 text-[12px] font-semibold text-ink">
                      {row.strength.toFixed(2)}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card
          title="Weakening pairs"
          subtitle="Relationships whose recent evidence trend is downward (advisory)."
        >
          {loading ? (
            <div className="flex items-center gap-2 py-6 text-[12px] text-faint">
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading pairs
            </div>
          ) : (overview?.weakening ?? []).length === 0 ? (
            <EmptyState
              icon={TrendingDown}
              title="Nothing weakening"
              description="No relationships are trending toward disconnection."
            />
          ) : (
            <ul className="space-y-2">
              {(overview?.weakening ?? []).map((row) => (
                <li
                  key={row.id}
                  className="flex items-center justify-between gap-3 rounded-xl border border-line/70 bg-elevated p-3"
                >
                  <div className="min-w-0">
                    <p className="truncate text-[13px] font-medium text-ink">
                      {pairLabel(row)}
                    </p>
                    <p className="text-[11px] text-faint">
                      {row.points_prev_month} → {row.points_cur_month} points
                      this month
                    </p>
                  </div>
                  <div className="text-right">
                    <Badge tone={HEALTH_TONE[row.health_state] ?? "neutral"}>
                      {row.health_state}
                    </Badge>
                    <p className="mt-1 text-[12px] font-semibold text-ink">
                      {row.strength.toFixed(2)}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <Card
        title="Recent changes"
        subtitle={`How the collaboration graph has shifted in the last ${changes?.days ?? 30} days.`}
      >
        {loading ? (
          <div className="flex items-center gap-2 py-6 text-[12px] text-faint">
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading changes
          </div>
        ) : (changes?.changes ?? []).length === 0 ? (
          <EmptyState
            icon={RefreshCw}
            title="Nothing changed recently"
            description="Emerging, strengthening, weakening and dormant relationships appear here."
          />
        ) : (
          <ul className="space-y-2">
            {(changes?.changes ?? []).map((row) => (
              <li
                key={row.id}
                className="flex items-start justify-between gap-3 rounded-xl border border-line/70 bg-elevated p-3"
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Badge tone={CHANGE_TONE[row.change] ?? "neutral"}>
                      {row.change}
                    </Badge>
                    <span className="truncate text-[12px] font-medium text-ink">
                      {pairLabel(row)}
                    </span>
                  </div>
                  <p className="mt-1 text-[11px] text-faint">
                    {row.successful_interactions} ok / {row.failed_interactions}{" "}
                    fail · {row.shared_tasks} shared task(s) · last seen{" "}
                    {timeAgo(row.last_activity_at)}
                  </p>
                </div>
                <p className="shrink-0 text-[12px] font-semibold text-ink">
                  {row.strength.toFixed(2)}
                </p>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card
        title="Open signals"
        subtitle={`${signalsTotal} advisory signal(s) awaiting acknowledgement. Advisory only — resolving changes nothing in the graph.`}
      >
        {loading ? (
          <div className="flex items-center gap-2 py-6 text-[12px] text-faint">
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading signals
          </div>
        ) : signals.length === 0 ? (
          <EmptyState
            icon={AlertTriangle}
            title="No open signals"
            description="The collaboration graph looks healthy. Signals appear for potential concentration risk, slowdowns and required-but-low-evidence pairs."
          />
        ) : (
          <ul className="space-y-2">
            {signals.map((signal) => (
              <li
                key={signal.id}
                className="flex items-start justify-between gap-3 rounded-xl border border-line/70 bg-elevated p-3"
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Badge tone={SIGNAL_KIND_TONE[signal.kind] ?? "neutral"}>
                      {signal.kind}
                    </Badge>
                    <Badge tone="neutral">{signal.severity}</Badge>
                    <span className="text-[12px] font-medium text-ink">
                      {signal.subject_label}
                    </span>
                  </div>
                  <p className="mt-1 text-[12px] leading-relaxed text-muted">
                    {signal.detail}
                  </p>
                  <p className="mt-1 text-[11px] text-faint">
                    raised {timeAgo(signal.created_at)}
                  </p>
                </div>
                {canManage && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => resolve(signal.id)}
                  >
                    Acknowledge
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card
        title="Project collaboration"
        subtitle="Evidence share and top pairs per project, with potential dependency concentration (advisory)."
        actions={
          <select
            value={projectId}
            onChange={(e) => setProjectId(e.target.value)}
            className="rounded-lg border border-line bg-surface px-2.5 py-1.5 text-[12px] font-medium text-ink outline-none focus:border-brand"
          >
            <option value="">Select a project…</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        }
      >
        {!projectView ? (
          <p className="text-[12px] text-faint">
            Choose a project to see its collaboration evidence: per-person share
            and the top pairs.
          </p>
        ) : (
          <div className="space-y-4">
            {projectView.dependency_concentration && (
              <div className="rounded-xl border border-warning/40 bg-warning/5 p-3">
                <p className="flex items-center gap-1.5 text-[12px] font-semibold text-warning">
                  <TrendingUp className="h-3.5 w-3.5" /> Potential dependency
                  concentration
                </p>
                <p className="mt-1 text-[12px] leading-relaxed text-muted">
                  {projectView.dependency_concentration.person_a_label} ↔{" "}
                  {projectView.dependency_concentration.person_b_label} carry{" "}
                  {(
                    projectView.dependency_concentration
                      .share_of_project_evidence * 100
                  ).toFixed(0)}
                  % of the project&apos;s evidence.{" "}
                  {projectView.dependency_concentration.advisory}
                </p>
              </div>
            )}
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <p className="mb-1.5 text-[12px] font-semibold text-ink">
                  People · {projectView.total_evidence} evidence item(s)
                </p>
                <ul className="space-y-1.5">
                  {projectView.people.map((p) => (
                    <li
                      key={p.person_id}
                      className="flex items-center justify-between gap-3 rounded-lg border border-line/70 bg-elevated px-3 py-2"
                    >
                      <span className="truncate text-[12px] font-medium text-ink">
                        {p.person_id.slice(0, 8)}
                      </span>
                      <span className="text-[12px] text-faint">
                        {(p.share_of_project_evidence * 100).toFixed(0)}%
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <p className="mb-1.5 text-[12px] font-semibold text-ink">
                  Top pairs
                </p>
                <ul className="space-y-1.5">
                  {projectView.top_pairs.map((p, i) => (
                    <li
                      key={i}
                      className="flex items-center justify-between gap-3 rounded-lg border border-line/70 bg-elevated px-3 py-2"
                    >
                      <span className="truncate text-[12px] font-medium text-ink">
                        {p.person_a_label} ↔ {p.person_b_label}
                      </span>
                      <span className="text-[12px] text-faint">
                        {p.evidence_count} · {p.successes} ok / {p.failures}{" "}
                        fail
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
