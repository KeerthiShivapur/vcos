"use client";

import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  CircleDashed,
  Flag,
  Gauge,
  GitBranch,
  HeartPulse,
  ListChecks,
  Loader2,
  Milestone,
  Route,
  Send,
  ShieldAlert,
  Siren,
  TrendingDown,
  UserX,
  XCircle,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { PageHeader, StatCard } from "@/components/ui/PageHeader";
import { Tabs } from "@/components/ui/Tabs";
import { useAuth } from "@/hooks/useAuth";
import {
  askExecution,
  getExecutionCommand,
  getExecutionNext,
  getExecutionProjectDetail,
  recordExecutionOutcome,
  type ExecutionBlockerRow,
  type ExecutionCommandResponse,
  type ExecutionCommandRow,
  type ExecutionCriticalPath,
  type ExecutionNextItem,
  type ExecutionProjectDetail,
  type ExecutionQueryResponse,
} from "@/lib/api";
import { PERMISSIONS } from "@/lib/permissions";
import { timeAgo } from "@/lib/utils";

import { CoordinationTab } from "./coordination-tab";

const HEALTH_TONE: Record<string, "success" | "warning" | "danger" | "neutral" | "brand"> = {
  healthy: "success",
  watch: "warning",
  at_risk: "danger",
  critical: "danger",
} as const;

const CAUSE_ICON: Record<string, typeof AlertTriangle> = {
  "Timeline pressure": TrendingDown,
  "Dependency blockage": GitBranch,
  "Capacity constraints": Activity,
  "Pending decisions": ListChecks,
  "No owner": UserX,
};

const KIND_TONE: Record<string, "brand" | "danger" | "warning" | "neutral" | "success"> = {
  decision: "brand",
  critical: "danger",
  blocked: "warning",
  milestone: "warning",
  ready: "success",
} as const;

function healthPercent(score: number) {
  return Math.max(0, Math.min(100, score));
}

export default function ExecutionPage() {
  const { can } = useAuth();
  const canManage = can(PERMISSIONS.PROJECTS_MANAGE);

  const [center, setCenter] = useState<ExecutionCommandResponse | null>(null);
  const [next, setNext] = useState<ExecutionNextItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [detail, setDetail] = useState<ExecutionProjectDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [expandedPath, setExpandedPath] = useState(false);

  const [question, setQuestion] = useState("");
  const [brain, setBrain] = useState<ExecutionQueryResponse | null>(null);
  const [asking, setAsking] = useState(false);

  const [outcomeForm, setOutcomeForm] = useState({ status: "partial", planned: "", actual: "", assessment: "" });
  const [recording, setRecording] = useState(false);
  const [tab, setTab] = useState("command");
  const [coordOpen, setCoordOpen] = useState(0);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const [c, n] = await Promise.all([getExecutionCommand(), getExecutionNext()]);
      setCenter(c);
      setNext(n.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load the execution command center");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function openProject(projectId: string) {
    setDetailLoading(true);
    setError(null);
    try {
      setDetail(await getExecutionProjectDetail(projectId));
      setExpandedPath(false);
      setOutcomeForm({ status: "partial", planned: "", actual: "", assessment: "" });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load the execution record");
    } finally {
      setDetailLoading(false);
    }
  }

  async function recordOutcome() {
    if (!detail) return;
    setRecording(true);
    setError(null);
    try {
      await recordExecutionOutcome(detail.project_id, {
        status: outcomeForm.status as "successful" | "partial" | "unsuccessful",
        planned_outcome: outcomeForm.planned.trim() || undefined,
        actual_outcome: outcomeForm.actual.trim() || undefined,
        assessment: outcomeForm.assessment.trim() || undefined,
      });
      setDetail(await getExecutionProjectDetail(detail.project_id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to record the outcome");
    } finally {
      setRecording(false);
    }
  }

  async function ask() {
    const q = question.trim();
    if (!q) return;
    setAsking(true);
    setError(null);
    try {
      setBrain(await askExecution(q));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to answer the question");
    } finally {
      setAsking(false);
    }
  }

  if (error && !center && !loading) {
    return (
      <div className="space-y-6">
        <PageHeader
          title="Execution Command Center"
          breadcrumb="Brain"
          description="Every active project's execution record in one place: deterministic health with one human explain, the real critical path, blocker root-cause chains and what should happen next."
        />
        <ErrorState title="Could not load the execution command center" message={error} />
      </div>
    );
  }

  const c = center?.counts ?? { active_projects: 0, at_risk: 0, blocked_projects: 0, pending_decisions: 0, capacity_constraints: 0 };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Execution Command Center"
        breadcrumb="Brain"
        description="Goal → project → milestone → task: one canonical execution record per project, fed from the same durable events the platform already emits. Deterministic health and explanation — never a score without a reason, never an automatic decision."
      />

      <Tabs
        tabs={[
          { id: "command", label: "Command Center" },
          { id: "coordination", label: "Coordination", count: coordOpen },
        ]}
        active={tab}
        onChange={setTab}
      />

      {tab === "coordination" && <CoordinationTab onOpenCount={setCoordOpen} />}

      {tab === "command" && (
      <>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <StatCard label="Active projects" value={loading ? "…" : c.active_projects} icon={Gauge} />
        <StatCard label="At risk or critical" value={loading ? "…" : c.at_risk} icon={Siren} />
        <StatCard label="With blocked work" value={loading ? "…" : c.blocked_projects} icon={AlertTriangle} />
        <StatCard label="Pending decisions" value={loading ? "…" : c.pending_decisions} icon={ListChecks} />
        <StatCard label="Constrained capacities" value={loading ? "…" : c.capacity_constraints} icon={Activity} />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card
            title={`Execution status · ${center?.total_projects ?? 0}`}
            subtitle="Every active project's health, primary cause and the event that last changed it."
          >
            {loading ? (
              <div className="flex items-center gap-2 py-6 text-[12px] text-faint">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading execution records
              </div>
            ) : (center?.projects ?? []).length === 0 ? (
              <EmptyState
                icon={Gauge}
                title="No execution records yet"
                description="Create and start a project with tasks — the execution record builds itself from the real event stream."
              />
            ) : (
              <ul className="space-y-2">
                {(center?.projects ?? []).map((row) => (
                  <li key={row.project_id} className="rounded-xl border border-line/70 bg-elevated p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <button type="button" onClick={() => openProject(row.project_id)} className="min-w-0 text-left">
                        <p className="text-[13px] font-medium text-ink hover:text-brand">
                          {row.name}
                          <span className="ml-1.5 text-[11px] font-normal text-faint">[{row.code}]</span>
                        </p>
                        <p className="truncate text-[11px] text-faint">
                          {row.status} · {row.primary_cause ?? "moving as expected"}
                          {row.owner_label ? ` · ${row.owner_label}` : ""}
                        </p>
                      </button>
                      <div className="flex shrink-0 items-center gap-1.5">
                        <Badge tone={HEALTH_TONE[row.health_status] ?? "neutral"}>{row.health_status}</Badge>
                        <span className="text-[12px] font-semibold text-ink">{row.health_score}</span>
                        <Button variant="ghost" size="sm" onClick={() => openProject(row.project_id)}>
                          <ArrowRight className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </div>
                    <p className="mt-1.5 text-[11px] leading-relaxed text-muted">{row.explain}</p>
                    <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[11px] text-faint">
                      <Badge tone="neutral">{row.counts.overdue_tasks} overdue</Badge>
                      <Badge tone="neutral">{row.counts.blocked_tasks} blocked</Badge>
                      {row.counts.critical_overdue_tasks > 0 && (
                        <Badge tone="danger">{row.counts.critical_overdue_tasks} critical past due</Badge>
                      )}
                      {row.counts.no_owner_tasks > 0 && (
                        <Badge tone="warning">{row.counts.no_owner_tasks} unowned</Badge>
                      )}
                      <span className="ml-auto">
                        {row.last_change ? `changed: ${row.last_change}` : "no change yet"}
                        {row.last_event_at ? ` · ${timeAgo(row.last_event_at)}` : ""}
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            )}
            {error && <p className="mt-2 rounded-lg border border-danger/30 bg-danger/10 p-2 text-[11px] text-danger">{error}</p>}
          </Card>

          <Card
            title={`What should happen next · ${next.length}`}
            subtitle="Deterministic prioritization: decisions first, then critical-path pressure, blocked path work, overdue milestones, ready high-priority work."
          >
            {loading ? (
              <div className="flex items-center gap-2 py-6 text-[12px] text-faint">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Prioritizing
              </div>
            ) : next.length === 0 ? (
              <EmptyState
                icon={ListChecks}
                title="Nothing pressing"
                description="No pending decisions, critical-path pressure, blocked path work, overdue milestones or ready high-priority work."
              />
            ) : (
              <ol className="space-y-1.5">
                {next.map((item, i) => (
                  <li key={i} className="flex items-start gap-2 rounded-lg border border-line/70 bg-surface px-3 py-2">
                    <span className="mt-0.5 w-5 shrink-0 text-center text-[11px] font-semibold text-faint">{item.priority}</span>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <Badge tone={KIND_TONE[item.kind] ?? "neutral"}>{item.kind}</Badge>
                        <p className="text-[13px] font-medium text-ink">{item.title}</p>
                      </div>
                      <p className="mt-0.5 text-[11px] leading-relaxed text-faint">{item.reason}</p>
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </Card>
        </div>

        <div className="space-y-6">
          <Card
            title="Ask the brain"
            subtitle='"Is the launch on track?", "why is the project at risk?", "what should we do next?"'
          >
            <div className="flex gap-2">
              <input
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && ask()}
                placeholder='e.g. "is the Atlas launch on track?"'
                className="flex-1 rounded-lg border border-line bg-surface px-3 py-2 text-[13px] text-ink outline-none focus:border-brand"
              />
              <Button size="sm" onClick={ask} disabled={asking || !question.trim()}>
                {asking ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                Ask
              </Button>
            </div>
            {brain && (
              <div className="mt-3 space-y-3">
                <div className="flex flex-wrap items-center gap-1.5">
                  <Badge tone="brand">{brain.intent}</Badge>
                  <Badge tone="neutral">scope: {brain.scope}</Badge>
                </div>
                {brain.project ? (
                  <ProjectDetailBody
                    detail={brain.project}
                    expandedPath={expandedPath}
                    setExpandedPath={setExpandedPath}
                  />
                ) : brain.answers && brain.answers.length > 0 ? (
                  <ul className="space-y-1.5">
                    {brain.answers.map((row: ExecutionCommandRow) => (
                      <li key={row.project_id} className="rounded-lg border border-line/70 bg-surface px-3 py-2">
                        <p className="text-[12px] font-medium text-ink">{row.name}</p>
                        <p className="text-[11px] text-faint">
                          {row.health_status} · {row.primary_cause ?? "moving as expected"}
                        </p>
                      </li>
                    ))}
                  </ul>
                ) : brain.execution_next?.items ? (
                  <NextList items={brain.execution_next.items} />
                ) : (
                  <p className="rounded-xl border border-line/70 bg-surface p-3 text-[12px] leading-relaxed text-ink">
                    {brain.answer ?? `No execution record answers "${brain.question}".`}
                  </p>
                )}
              </div>
            )}
          </Card>

          <Card
            title="Why projects change"
            subtitle="Every snapshot is keyed to the durable event that caused it; replays converge and history answers what changed over time."
          >
            <div className="space-y-1.5">
              {(["Timeline pressure", "Dependency blockage", "Capacity constraints", "Pending decisions", "No owner"] as const).map(
                (cause) => {
                  const Icon = CAUSE_ICON[cause] ?? AlertTriangle;
                  return (
                    <p key={cause} className="flex items-center gap-2 text-[12px] text-muted">
                      <Icon className="h-3.5 w-3.5 text-faint" /> {cause}
                    </p>
                  );
                }
              )}
            </div>
          </Card>
        </div>
      </div>

      {detail && (
        <ProjectDetailPanel
          detail={detail}
          loading={detailLoading}
          canManage={canManage}
          expandedPath={expandedPath}
          setExpandedPath={setExpandedPath}
          outcomeForm={outcomeForm}
          setOutcomeForm={setOutcomeForm}
          recording={recording}
          onRecord={recordOutcome}
          onClose={() => setDetail(null)}
        />
      )}
      </>
      )}
    </div>
  );
}

function HealthBar({ detail }: { detail: ExecutionProjectDetail }) {
  const pct = healthPercent(detail.health_score);
  const tone =
    detail.health_status === "healthy"
      ? "bg-emerald-500"
      : detail.health_status === "watch"
        ? "bg-amber-400"
        : detail.health_status === "at_risk"
          ? "bg-orange-500"
          : "bg-red-500";
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-line/60">
      <div className={`h-full rounded-full ${tone}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

function CriticalPathView({ path }: { path: ExecutionCriticalPath }) {
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2 text-[12px]">
        <Badge tone="neutral">{path.total_hours} estimated hours</Badge>
        <Badge tone="neutral">finish ≈ {path.projected_finish_hours}h</Badge>
        <Badge tone={path.min_slack === 0 ? "danger" : "warning"}>
          min slack {path.min_slack === null ? "—" : `${path.min_slack}h`}
        </Badge>
        <Badge tone="danger">{path.overdue_critical_ids} critical past due</Badge>
      </div>
      <div className="flex flex-wrap items-center gap-1">
        {path.tasks.map((t, i) => (
          <span key={t.task_id} className="flex items-center gap-1">
            {i > 0 && <ArrowRight className="h-3 w-3 text-faint" />}
            <span
              className={`rounded-md border px-2 py-1 text-[11px] ${
                t.critical ? "border-brand/40 bg-brand/10 text-ink" : "border-line/70 bg-surface text-faint"
              }`}
              title={`${t.title} · slack ${t.slack_hours}h`}
            >
              {t.title}
              {t.critical ? <span className="ml-1 text-brand">●</span> : null}
            </span>
          </span>
        ))}
      </div>
    </div>
  );
}

function BlockerView({ blockers }: { blockers: ExecutionBlockerRow[] }) {
  if (!blockers.length) return <p className="text-[12px] text-faint">No blocked work.</p>;
  return (
    <ul className="space-y-1.5">
      {blockers.map((b) => (
        <li key={b.task_id} className="rounded-lg border border-line/70 bg-surface px-3 py-2">
          <div className="flex items-center justify-between gap-2">
            <p className="text-[12px] font-medium text-ink">{b.title}</p>
            <Badge tone="warning">depth {b.chain_depth}</Badge>
          </div>
          {b.chain.length > 0 && (
            <p className="mt-1 flex flex-wrap items-center gap-1 text-[11px] text-faint">
              {b.chain.map((c, i) => (
                <span key={c.task_id} className="flex items-center gap-1">
                  {i > 0 && <ArrowRight className="h-3 w-3" />}
                  {c.title}
                </span>
              ))}
            </p>
          )}
        </li>
      ))}
    </ul>
  );
}

function ProjectDetailBody({
  detail,
  expandedPath,
  setExpandedPath,
}: {
  detail: ExecutionProjectDetail;
  expandedPath: boolean;
  setExpandedPath: (v: boolean) => void;
}) {
  const icon = detail.health_status === "healthy" ? CheckCircle2 : detail.health_status === "watch" ? HeartPulse : ShieldAlert;
  const StatusIcon = icon;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge tone={HEALTH_TONE[detail.health_status] ?? "neutral"}>{detail.health_status}</Badge>
        <span className="text-[13px] font-semibold text-ink">{detail.health_score}/100</span>
        {detail.primary_cause && <Badge tone="warning">{detail.primary_cause}</Badge>}
        <span className="ml-auto text-[11px] text-faint">{detail.status}</span>
      </div>
      <HealthBar detail={detail} />
      <p className="rounded-xl border border-brand/30 bg-brand/5 p-3 text-[12px] leading-relaxed text-ink">
        <StatusIcon className="mr-1.5 inline h-3.5 w-3.5 text-brand" />
        {detail.explain}
      </p>

      {detail.goal_chain.length > 0 && (
        <>
          <p className="text-[12px] font-semibold text-ink">
            <Milestone className="mr-1 inline h-3.5 w-3.5 text-faint" /> Goal chain
          </p>
          <p className="flex flex-wrap items-center gap-1 text-[11px] text-faint">
            {detail.goal_chain.map((g, i) => (
              <span key={`${g.type}-${g.id}`} className="flex items-center gap-1">
                {i > 0 && <ArrowRight className="h-3 w-3" />}
                <Badge tone="neutral">{g.type}</Badge>
                {g.title}
              </span>
            ))}
          </p>
        </>
      )}

      {detail.critical_path.tasks.length > 0 && (
        <>
          <p className="text-[12px] font-semibold text-ink">
            <Route className="mr-1 inline h-3.5 w-3.5 text-faint" /> Critical path
          </p>
          <CriticalPathView path={detail.critical_path} />
        </>
      )}

      {detail.blockers.length > 0 && (
        <>
          <p className="text-[12px] font-semibold text-ink">
            <GitBranch className="mr-1 inline h-3.5 w-3.5 text-faint" /> Blocker root causes
          </p>
          <BlockerView blockers={detail.blockers} />
        </>
      )}

      {detail.systemic_blockers.length > 0 && (
        <>
          <p className="text-[12px] font-semibold text-ink">
            <AlertTriangle className="mr-1 inline h-3.5 w-3.5 text-faint" /> Systemic blockers
          </p>
          <ul className="space-y-1.5">
            {detail.systemic_blockers.map((s) => (
              <li key={s.subject_id} className="rounded-lg border border-danger/30 bg-danger/5 px-3 py-2">
                <p className="text-[12px] font-medium text-ink">
                  {s.subject_label} · {s.affected_count} affected
                </p>
                <p className="mt-0.5 text-[11px] leading-relaxed text-muted">{s.explain}</p>
              </li>
            ))}
          </ul>
        </>
      )}

      {detail.capacity_constraints.length > 0 && (
        <>
          <p className="text-[12px] font-semibold text-ink">
            <Activity className="mr-1 inline h-3.5 w-3.5 text-faint" /> Capacity constraints
          </p>
          <div className="flex flex-wrap gap-1.5">
            {detail.capacity_constraints.map((cap) => (
              <Badge key={`${cap.skill_name}-${cap.capacity_state}`} tone="warning">
                {cap.skill_name} · {cap.capacity_state}
              </Badge>
            ))}
          </div>
        </>
      )}

      {detail.pending_decisions.length > 0 && (
        <>
          <p className="text-[12px] font-semibold text-ink">
            <ListChecks className="mr-1 inline h-3.5 w-3.5 text-faint" /> Pending decisions
          </p>
          <ul className="space-y-1">
            {detail.pending_decisions.map((d) => (
              <li key={d.id} className="rounded-lg border border-line/70 bg-surface px-3 py-2 text-[11px] text-muted">
                {d.title} · {d.open_actions} open action(s)
              </li>
            ))}
          </ul>
        </>
      )}

      {detail.history.length > 0 && (
        <>
          <button
            type="button"
            onClick={() => setExpandedPath(!expandedPath)}
            className="flex items-center gap-1 text-[12px] font-semibold text-ink"
          >
            {expandedPath ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
            What changed over time · {detail.history.length}
          </button>
          {expandedPath && (
            <ol className="space-y-1">
              {detail.history.map((h) => (
                <li key={h.id} className="flex items-center gap-2 text-[11px] text-faint">
                  <Badge tone={HEALTH_TONE[h.health_status] ?? "neutral"}>{h.health_status}</Badge>
                  <span className="font-medium text-ink">{h.event_name}</span>
                  <span>{h.health_score}</span>
                  <span className="ml-auto">{timeAgo(h.occurred_at)}</span>
                </li>
              ))}
            </ol>
          )}
        </>
      )}

      {detail.outcome && (
        <div className="rounded-lg border border-line/70 bg-surface p-3">
          <p className="text-[12px] font-semibold text-ink">
            <Flag className="mr-1 inline h-3.5 w-3.5 text-faint" /> Outcome · {detail.outcome.status}
          </p>
          {detail.outcome.planned_outcome && (
            <p className="mt-1 text-[11px] text-faint">planned: {detail.outcome.planned_outcome}</p>
          )}
          {detail.outcome.actual_outcome && (
            <p className="text-[11px] text-faint">actual: {detail.outcome.actual_outcome}</p>
          )}
          {detail.outcome.assessment && (
            <p className="text-[11px] leading-relaxed text-muted">{detail.outcome.assessment}</p>
          )}
        </div>
      )}
    </div>
  );
}

function NextList({ items }: { items: ExecutionNextItem[] }) {
  if (!items.length) return <p className="text-[12px] text-faint">Nothing pressing.</p>;
  return (
    <ol className="space-y-1.5">
      {items.map((item, i) => (
        <li key={i} className="rounded-lg border border-line/70 bg-surface px-3 py-2">
          <div className="flex items-center gap-1.5">
            <Badge tone={KIND_TONE[item.kind] ?? "neutral"}>{item.kind}</Badge>
            <p className="text-[12px] font-medium text-ink">{item.title}</p>
          </div>
          <p className="mt-0.5 text-[11px] text-faint">{item.reason}</p>
        </li>
      ))}
    </ol>
  );
}

function ProjectDetailPanel({
  detail,
  loading,
  canManage,
  expandedPath,
  setExpandedPath,
  outcomeForm,
  setOutcomeForm,
  recording,
  onRecord,
  onClose,
}: {
  detail: ExecutionProjectDetail;
  loading: boolean;
  canManage: boolean;
  expandedPath: boolean;
  setExpandedPath: (v: boolean) => void;
  outcomeForm: { status: string; planned: string; actual: string; assessment: string };
  setOutcomeForm: (v: { status: string; planned: string; actual: string; assessment: string }) => void;
  recording: boolean;
  onRecord: () => void;
  onClose: () => void;
}) {
  return (
    <Card
      title={`${detail.name} · execution record`}
      subtitle={`${detail.code} · ${detail.status}${detail.description ? ` · ${detail.description}` : ""}`}
      actions={
        <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close execution record">
          <XCircle className="h-4 w-4" />
        </Button>
      }
    >
      {loading ? (
        <div className="flex items-center gap-2 py-6 text-[12px] text-faint">
          <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading the execution record
        </div>
      ) : (
        <div className="grid gap-6 lg:grid-cols-3">
          <div className="space-y-4 lg:col-span-2">
            <ProjectDetailBody detail={detail} expandedPath={expandedPath} setExpandedPath={setExpandedPath} />
          </div>
          <div className="space-y-4">
            <Card title="Record the outcome" subtitle="The mandatory outcome record — written by a human, never by the system.">
              {detail.outcome ? (
                <div className="space-y-1.5 text-[12px]">
                  <Badge tone="neutral">outcome: {detail.outcome.status}</Badge>
                  {detail.outcome.actual_outcome && <p className="text-muted">{detail.outcome.actual_outcome}</p>}
                  {detail.outcome.assessment && <p className="text-faint">{detail.outcome.assessment}</p>}
                  <p className="text-[11px] text-faint">recorded {timeAgo(detail.outcome.recorded_at)}</p>
                </div>
              ) : canManage ? (
                <div className="space-y-2">
                  <select
                    value={outcomeForm.status}
                    onChange={(e) => setOutcomeForm({ ...outcomeForm, status: e.target.value })}
                    className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-[13px] text-ink outline-none focus:border-brand"
                  >
                    <option value="successful">successful</option>
                    <option value="partial">partial</option>
                    <option value="unsuccessful">unsuccessful</option>
                  </select>
                  <input
                    value={outcomeForm.planned}
                    onChange={(e) => setOutcomeForm({ ...outcomeForm, planned: e.target.value })}
                    placeholder="Planned outcome"
                    className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-[13px] text-ink outline-none focus:border-brand"
                  />
                  <input
                    value={outcomeForm.actual}
                    onChange={(e) => setOutcomeForm({ ...outcomeForm, actual: e.target.value })}
                    placeholder="Actual outcome"
                    className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-[13px] text-ink outline-none focus:border-brand"
                  />
                  <textarea
                    value={outcomeForm.assessment}
                    onChange={(e) => setOutcomeForm({ ...outcomeForm, assessment: e.target.value })}
                    placeholder="Assessment"
                    rows={2}
                    className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-[13px] text-ink outline-none focus:border-brand"
                  />
                  <Button size="sm" onClick={onRecord} disabled={recording || !outcomeForm.status}>
                    {recording ? <Loader2 className="h-4 w-4 animate-spin" /> : <Flag className="h-4 w-4" />}
                    Record outcome
                  </Button>
                </div>
              ) : (
                <p className="text-[11px] text-faint">Recording outcomes requires project management access.</p>
              )}
            </Card>
            <Card title="Advisory only" subtitle="The record never rewrites the project.">
              <div className="flex items-center gap-2 text-[12px] text-muted">
                <CircleDashed className="h-3.5 w-3.5 shrink-0 text-faint" />
                The execution record explains what is and what to do about it — people own the projects.
              </div>
            </Card>
          </div>
        </div>
      )}
    </Card>
  );
}
