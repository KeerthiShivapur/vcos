"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  BellRing,
  BookOpen,
  Brain,
  CircleDot,
  Copy,
  FileSearch,
  GitBranch,
  HeartPulse,
  ListChecks,
  Network,
  Play,
  Radar,
  RefreshCw,
  Repeat2,
  ScanSearch,
  Sparkles,
  Zap,
} from "lucide-react";

import {
  deactivateGraphEdge,
  generateAutonomousNotifications,
  generateBriefs,
  getAutonomousNotifications,
  getCollaborationMetrics,
  getEmployeeBrief,
  getEventCatalog,
  getExecutiveBrief,
  getExpertiseHistory,
  getExpertiseLeaderboard,
  getGraphBottlenecks,
  getGraphStats,
  getInsightRisks,
  getIntelligenceEventStats,
  getIntelligenceOverview,
  getLearningSummary,
  getMyRecommendations,
  getSearchStats,
  listBurnoutSignals,
  listDailyBriefs,
  listDuplicates,
  listGraphEdges,
  listIntelligenceEvents,
  listIntelligenceJobs,
  listKnowledgeInsights,
  listLearningLessons,
  listPatterns,
  listWorkers,
  listWorkflowInsights,
  processPendingEvents,
  refreshMyRecommendations,
  runWorkerOnDemand,
  scanInsightRisks,
  setBurnoutSignalStatus,
  setDuplicateStatus,
  setKnowledgeInsightStatus,
  setPatternStatus,
  setRecommendationStatus,
  setWorkflowInsightStatus,
} from "@/lib/api";
import type {
  AutonomousNotification,
  BurnoutSignal,
  CollaborationMetrics,
  DailyBrief,
  DuplicateDetection,
  ExpertiseHistoryEntry,
  ExpertiseLeaderEntry,
  GraphEdge,
  GraphPathStep,
  InsightRisk,
  IntelligenceEvent,
  IntelligenceJobs,
  IntelligenceOverview,
  KnowledgeInsight,
  LearningLesson,
  PatternDetection,
  RecommendationItem,
  WorkflowInsight,
} from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { roleCan, PERMISSIONS } from "@/lib/permissions";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { Tabs } from "@/components/ui/Tabs";
import { CompanyBrainTab } from "./company-brain-tab";
import { SemanticKnowledgeTab } from "./semantic-knowledge-tab";
import { MemoryTab } from "./memory-tab";
import { PatternTab } from "./pattern-tab";
import { UniversalInsightsTab } from "./insights-tab";

export default function IntelligencePage() {
  return (
    <Suspense fallback={null}>
      <IntelligenceContent />
    </Suspense>
  );
}

function levelTone(
  level: string,
): "neutral" | "brand" | "success" | "warning" | "danger" {
  if (level === "high" || level === "critical") return "danger";
  if (level === "elevated" || level === "moderate" || level === "warning")
    return "warning";
  if (level === "low" || level === "info" || level === "neutral")
    return "neutral";
  return "brand";
}

function IntelligenceContent() {
  const { user } = useAuth();
  const canManage = roleCan(user?.role, PERMISSIONS.INTELLIGENCE_MANAGE);

  const [tab, setTab] = useState("overview");
  const [overview, setOverview] = useState<IntelligenceOverview | null>(null);
  const [events, setEvents] = useState<IntelligenceEvent[]>([]);
  const [eventStats, setEventStats] = useState<IntelligenceJobs | null>(null);
  const [workers, setWorkers] = useState<
    { name: string; interval_seconds?: number; run_on_demand: boolean }[]
  >([]);
  const [jobs, setJobs] = useState<unknown[]>([]);
  const [leaderboard, setLeaderboard] = useState<ExpertiseLeaderEntry[]>([]);
  const [history, setHistory] = useState<ExpertiseHistoryEntry[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const [graphStats, setGraphStats] = useState<{ [k: string]: unknown } | null>(
    null,
  );
  const [bottlenecks, setBottlenecks] = useState<GraphPathStep[]>([]);
  const [knowledge, setKnowledge] = useState<KnowledgeInsight[]>([]);
  const [burnout, setBurnout] = useState<BurnoutSignal[]>([]);
  const [duplicates, setDuplicates] = useState<DuplicateDetection[]>([]);
  const [patterns, setPatterns] = useState<PatternDetection[]>([]);
  const [workflow, setWorkflow] = useState<WorkflowInsight[]>([]);
  const [lessons, setLessons] = useState<LearningLesson[]>([]);
  const [learningSummary, setLearningSummary] = useState<{
    total: number;
    by_type: Record<string, number>;
  } | null>(null);
  const [collab, setCollab] = useState<CollaborationMetrics | null>(null);
  const [execBrief, setExecBrief] = useState<DailyBrief | null>(null);
  const [employeeBrief, setEmployeeBrief] = useState<DailyBrief | null>(null);
  const [briefs, setBriefs] = useState<DailyBrief[]>([]);
  const [feed, setFeed] = useState<RecommendationItem[]>([]);
  const [risks, setRisks] = useState<InsightRisk[]>([]);
  const [alerts, setAlerts] = useState<AutonomousNotification[]>([]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [
        ov,
        ev,
        es,
        wk,
        lb,
        gs,
        eg,
        bot,
        kn,
        bu,
        du,
        pa,
        wf,
        ls,
        ls2,
        co,
        fe,
        rk,
        al,
      ] = await Promise.all([
        getIntelligenceOverview(),
        listIntelligenceEvents(100),
        getIntelligenceEventStats(),
        listWorkers(),
        getExpertiseLeaderboard(),
        getGraphStats(),
        listGraphEdges({ limit: 100 }),
        getGraphBottlenecks(),
        listKnowledgeInsights({ limit: 100 }),
        listBurnoutSignals("moderate", undefined, 100),
        listDuplicates(undefined, "open", 100),
        listPatterns(undefined, "open", 100),
        listWorkflowInsights("open", 100),
        listLearningLessons(undefined, 100),
        getLearningSummary(),
        getCollaborationMetrics(),
        getMyRecommendations(25),
        getInsightRisks({ limit: 50 }),
        getAutonomousNotifications(undefined, 50),
      ]);
      setOverview(ov);
      setEvents(ev);
      setEventStats(es);
      setWorkers(wk);
      setLeaderboard(lb);
      setGraphStats(gs);
      setEdges(eg);
      setBottlenecks(bot);
      setKnowledge(kn);
      setBurnout(bu);
      setDuplicates(du);
      setPatterns(pa);
      setWorkflow(wf);
      setLessons(ls);
      setLearningSummary(ls2);
      setCollab(co);
      setFeed(fe);
      setRisks(rk.risks);
      setAlerts(al);
      setLoading(false);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load intelligence",
      );
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const flash = (message: string) => {
    setNotice(message);
    window.setTimeout(() => setNotice(null), 2500);
  };

  const handleProcessEvents = async () => {
    setBusy(true);
    try {
      const result = await processPendingEvents(100);
      flash(`Dispatched ${result.processed} events`);
      await loadAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Dispatch failed");
    } finally {
      setBusy(false);
    }
  };

  const handleRunWorker = async (name: string) => {
    if (!canManage) return;
    setBusy(true);
    try {
      const result = await runWorkerOnDemand(name);
      flash(`Worker ${name} finished: ${result.processed} processed`);
      await loadAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : `Worker ${name} failed`);
    } finally {
      setBusy(false);
    }
  };

  const handleBriefs = async () => {
    setBusy(true);
    try {
      await generateBriefs();
      const [eb, emb, bl] = await Promise.all([
        getExecutiveBrief(),
        getEmployeeBrief(),
        listDailyBriefs(20),
      ]);
      setExecBrief(eb);
      setEmployeeBrief(emb);
      setBriefs(bl);
      flash("Briefs regenerated");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Brief generation failed");
    } finally {
      setBusy(false);
    }
  };

  const handleRefreshFeed = async () => {
    setBusy(true);
    try {
      await refreshMyRecommendations();
      setFeed(await getMyRecommendations(25));
      flash("Recommendation feed refreshed");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Feed refresh failed");
    } finally {
      setBusy(false);
    }
  };

  const handleScanRisks = async () => {
    if (!canManage) return;
    setBusy(true);
    try {
      const result = await scanInsightRisks();
      flash(
        result.scanned
          ? `Risk scan complete: ${result.new_risks} new`
          : "No new risks detected",
      );
      await loadAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Risk scan failed");
    } finally {
      setBusy(false);
    }
  };

  const handleGenerateAlerts = async () => {
    if (!canManage) return;
    setBusy(true);
    try {
      const result = await generateAutonomousNotifications();
      flash(`Generated ${result.generated} autonomous notifications`);
      await loadAll();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Notification generation failed",
      );
    } finally {
      setBusy(false);
    }
  };

  const handleSetStatus = async (kind: string, id: string, status: string) => {
    try {
      if (kind === "knowledge") await setKnowledgeInsightStatus(id, status);
      if (kind === "burnout") await setBurnoutSignalStatus(id, status);
      if (kind === "duplicate") await setDuplicateStatus(id, status);
      if (kind === "pattern") await setPatternStatus(id, status);
      if (kind === "workflow") await setWorkflowInsightStatus(id, status);
      if (kind === "recommendation") await setRecommendationStatus(id, status);
      await loadAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed");
    }
  };

  const handleDeactivateEdge = async (edgeId: string) => {
    try {
      await deactivateGraphEdge(edgeId);
      flash("Edge deactivated");
      await loadAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Edge update failed");
    }
  };

  const tabs = useMemo(
    () => [
      { id: "overview", label: "Overview", icon: Brain },
      { id: "brain", label: "Company Brain", icon: Sparkles },
      { id: "semantic", label: "Semantic Knowledge", icon: ScanSearch },
      { id: "memory", label: "Company Memory", icon: BookOpen },
      {
        id: "patterns",
        label: "Pattern Intelligence",
        icon: Repeat2,
        count: patterns.filter((p) =>
          [
            "candidate",
            "emerging",
            "confirmed",
            "persistent",
            "fading",
          ].includes(p.status),
        ).length,
      },
      { id: "company-insights", label: "Company Insights", icon: Radar },
      {
        id: "events",
        label: "Event Bus",
        icon: Activity,
        count: overview?.jobs.done ?? 0,
      },
      { id: "workers", label: "Workers", icon: Play },
      { id: "expertise", label: "Expertise", icon: BarChart3 },
      {
        id: "graph",
        label: "Org Graph",
        icon: Network,
        count: overview?.graph.edges ?? 0,
      },
      { id: "insights", label: "Insights", icon: FileSearch },
      {
        id: "learning",
        label: "Learning",
        icon: BookOpen,
        count: learningSummary?.total ?? 0,
      },
      { id: "collab", label: "Collaboration", icon: GitBranch },
      { id: "briefs", label: "Daily Briefs", icon: Sparkles },
      { id: "feed", label: "My Recommendations", icon: Zap },
      {
        id: "risks",
        label: "Risks & Alerts",
        icon: AlertTriangle,
        count: overview?.risks?.count ?? 0,
      },
    ],
    [overview, learningSummary],
  );

  if (error) {
    return (
      <div className="p-6">
        <PageHeader
          title="Background Intelligence"
          description="The autonomous organization at work"
        />
        <ErrorState message={error} onRetry={loadAll} />
      </div>
    );
  }

  if (loading || !overview) {
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner label="Loading intelligence…" />
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Background Intelligence"
        description="Autonomous monitoring, learning and recommendations"
        actions={
          <>
            {canManage && (
              <>
                <Button
                  variant="secondary"
                  onClick={handleProcessEvents}
                  disabled={busy}
                >
                  <Play className="h-4 w-4" /> Dispatch events
                </Button>
                <Button
                  variant="secondary"
                  onClick={handleBriefs}
                  disabled={busy}
                >
                  <Sparkles className="h-4 w-4" /> Generate briefs
                </Button>
              </>
            )}
            <Button onClick={loadAll} disabled={busy}>
              <RefreshCw className={`h-4 w-4 ${busy ? "animate-spin" : ""}`} />{" "}
              Refresh
            </Button>
          </>
        }
      />

      {notice && (
        <div className="mx-6 mb-3 rounded-lg bg-success/10 px-3 py-2 text-[13px] text-success">
          {notice}
        </div>
      )}

      <div className="flex-1 overflow-y-auto p-6 pt-2">
        <Tabs tabs={tabs} active={tab} onChange={setTab} />

        <div className="mt-5">
          {tab === "overview" && <OverviewTab overview={overview} />}
          {tab === "brain" && <CompanyBrainTab />}
          {tab === "semantic" && <SemanticKnowledgeTab />}
          {tab === "memory" && <MemoryTab />}
          {tab === "patterns" && <PatternTab />}
          {tab === "company-insights" && <UniversalInsightsTab />}
          {tab === "events" && (
            <EventsTab
              events={events}
              stats={eventStats}
              jobs={jobs}
              canManage={canManage}
              onProcess={handleProcessEvents}
              busy={busy}
            />
          )}
          {tab === "workers" && (
            <WorkersTab
              workers={workers}
              canManage={canManage}
              onRun={handleRunWorker}
              busy={busy}
            />
          )}
          {tab === "expertise" && (
            <ExpertiseTab
              leaderboard={leaderboard}
              history={history}
              onSelect={setHistory}
            />
          )}
          {tab === "graph" && (
            <GraphTab
              stats={graphStats}
              edges={edges}
              bottlenecks={bottlenecks}
              canManage={canManage}
              onDeactivate={handleDeactivateEdge}
            />
          )}
          {tab === "insights" && (
            <InsightsTab
              knowledge={knowledge}
              burnout={burnout}
              duplicates={duplicates}
              patterns={patterns}
              workflow={workflow}
              onStatus={handleSetStatus}
              canManage={canManage}
            />
          )}
          {tab === "learning" && (
            <LearningTab lessons={lessons} summary={learningSummary} />
          )}
          {tab === "collab" && (
            <CollabTab metrics={collab} onRefresh={loadAll} busy={busy} />
          )}
          {tab === "briefs" && (
            <BriefsTab
              execBrief={execBrief}
              employeeBrief={employeeBrief}
              briefs={briefs}
              onLoad={async () => {
                const [eb, emb, bl] = await Promise.all([
                  getExecutiveBrief(),
                  getEmployeeBrief(),
                  listDailyBriefs(20),
                ]);
                setExecBrief(eb);
                setEmployeeBrief(emb);
                setBriefs(bl);
              }}
            />
          )}
          {tab === "feed" && (
            <FeedTab
              feed={feed}
              onRefresh={handleRefreshFeed}
              onStatus={handleSetStatus}
              busy={busy}
            />
          )}
          {tab === "risks" && (
            <RisksTab
              risks={risks}
              alerts={alerts}
              canManage={canManage}
              onScan={handleScanRisks}
              onGenerate={handleGenerateAlerts}
              busy={busy}
            />
          )}
        </div>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ overview

function StatCard({
  label,
  value,
  icon,
  tone,
}: {
  label: string;
  value: number | string;
  icon: React.ReactNode;
  tone?: string;
}) {
  return (
    <Card className="p-5">
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-soft text-brand">
          {icon}
        </div>
        <div>
          <p className="text-xl font-bold text-ink">{value}</p>
          <p className="text-xs text-faint">{label}</p>
        </div>
      </div>
    </Card>
  );
}

function OverviewTab({ overview }: { overview: IntelligenceOverview }) {
  const jobs = overview.jobs;
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard
          label="Events dispatched"
          value={jobs.done ?? 0}
          icon={<Activity className="h-4 w-4" />}
        />
        <StatCard
          label="Graph edges"
          value={overview.graph.edges ?? 0}
          icon={<Network className="h-4 w-4" />}
        />
        <StatCard
          label="Searches"
          value={overview.search.total_searches ?? 0}
          icon={<FileSearch className="h-4 w-4" />}
        />
        <StatCard
          label="Lessons learned"
          value={overview.learning.total ?? 0}
          icon={<BookOpen className="h-4 w-4" />}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Worker health" subtitle="Event dispatch job status">
          <div className="flex flex-wrap gap-2">
            <Badge tone="neutral">queued {jobs.queued ?? 0}</Badge>
            <Badge tone="brand">running {jobs.running ?? 0}</Badge>
            <Badge tone="success">done {jobs.done ?? 0}</Badge>
            <Badge tone="warning">retry {jobs.retry ?? 0}</Badge>
            <Badge tone="danger">failed {jobs.failed ?? 0}</Badge>
          </div>
        </Card>

        <Card
          title="Signals needing attention"
          subtitle="Elevated burnout + open insights"
        >
          <div className="space-y-2 text-[13px]">
            <p>
              <Badge
                tone={overview.burnout.latest.length ? "warning" : "success"}
              >
                {overview.burnout.count} burnout signals
              </Badge>{" "}
              <span className="text-muted">
                {overview.burnout.latest.length
                  ? "— elevated workload patterns detected"
                  : "— no elevated workload patterns"}
              </span>
            </p>
            <p>
              <Badge tone="neutral">
                {overview.knowledge.count} knowledge insights
              </Badge>{" "}
              <span className="text-muted">
                outdated, duplicate or missing content
              </span>
            </p>
            <p>
              <Badge tone="neutral">
                {overview.duplicates.count} duplicate detections
              </Badge>
            </p>
            <p>
              <Badge tone="warning">{overview.patterns.count} patterns</Badge>{" "}
              <span className="text-muted">
                repeated delays, bottlenecks, gaps
              </span>
            </p>
            <p>
              <Badge tone="neutral">
                {overview.workflow.count} workflow insights
              </Badge>{" "}
              <span className="text-muted">
                slow approvals and automation chances
              </span>
            </p>
            <p>
              <Badge
                tone={
                  overview.risks && overview.risks.count > 0
                    ? "danger"
                    : "success"
                }
              >
                {overview.risks?.count ?? 0} strategic risks
              </Badge>{" "}
              <span className="text-muted">
                {overview.risks && overview.risks.count > 0
                  ? "— from background intelligence scans"
                  : "— no open strategic risks"}
              </span>
            </p>
            <p>
              <Badge
                tone={
                  overview.autonomous_notifications &&
                  overview.autonomous_notifications.count > 0
                    ? "warning"
                    : "neutral"
                }
              >
                {overview.autonomous_notifications?.count ?? 0} autonomous
                notifications
              </Badge>
            </p>
          </div>
        </Card>
      </div>

      {overview.burnout.latest.length > 0 && (
        <Card title="Latest burnout signals">
          <div className="space-y-2">
            {overview.burnout.latest.map((signal) => (
              <div
                key={signal.id}
                className="flex items-center justify-between rounded-lg border border-line px-3 py-2"
              >
                <div>
                  <p className="text-[13px] font-medium text-ink">
                    {signal.employee_name ?? signal.employee_id}
                  </p>
                  <p className="text-xs text-faint">
                    Workload pattern · score {signal.score}
                  </p>
                </div>
                <Badge tone={levelTone(signal.level)}>{signal.level}</Badge>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ events

function EventsTab({
  events,
  stats,
  jobs,
  canManage,
  onProcess,
  busy,
}: {
  events: IntelligenceEvent[];
  stats: IntelligenceJobs | null;
  jobs: unknown[];
  canManage: boolean;
  onProcess: () => void;
  busy: boolean;
}) {
  const processed = events.filter((e) => e.processed_at).length;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        {stats && (
          <>
            <Badge tone="neutral">
              total jobs{" "}
              {stats.queued +
                stats.done +
                stats.running +
                stats.retry +
                stats.failed}
            </Badge>
            <Badge tone="success">done {stats.done ?? 0}</Badge>
            <Badge tone="warning">retry {stats.retry ?? 0}</Badge>
            <Badge tone="danger">failed {stats.failed ?? 0}</Badge>
          </>
        )}
        <span className="text-xs text-faint">
          {processed}/{events.length} events processed
        </span>
        {canManage && (
          <Button
            size="sm"
            variant="secondary"
            onClick={onProcess}
            disabled={busy}
          >
            <Play className="h-3.5 w-3.5" /> Dispatch pending
          </Button>
        )}
      </div>

      {events.length === 0 ? (
        <EmptyState
          icon={Activity}
          title="No events yet"
          description="Activity will appear here as the organization works."
        />
      ) : (
        <Card bodyClassName="p-0">
          <div className="divide-y divide-line">
            {events.slice(0, 60).map((event) => (
              <div
                key={event.id}
                className="flex items-center justify-between gap-3 px-5 py-2.5"
              >
                <div className="min-w-0">
                  <p className="truncate text-[13px] font-medium text-ink">
                    {event.name}
                  </p>
                  <p className="truncate text-xs text-faint">
                    {event.occurred_at
                      ? new Date(event.occurred_at).toLocaleString()
                      : "—"}
                  </p>
                </div>
                <Badge tone={event.processed_at ? "success" : "warning"}>
                  {event.processed_at ? "processed" : "pending"}
                </Badge>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ workers

function WorkersTab({
  workers,
  canManage,
  onRun,
  busy,
}: {
  workers: {
    name: string;
    interval_seconds?: number;
    run_on_demand: boolean;
  }[];
  canManage: boolean;
  onRun: (name: string) => void;
  busy: boolean;
}) {
  return (
    <Card
      title="Background workers"
      subtitle="Scheduled autonomous passes — run any of them on demand"
      bodyClassName="p-0"
    >
      <div className="divide-y divide-line">
        {workers.map((worker) => (
          <div
            key={worker.name}
            className="flex items-center justify-between gap-3 px-5 py-3"
          >
            <div>
              <p className="font-mono text-[13px] font-medium text-ink">
                {worker.name}
              </p>
              <p className="text-xs text-faint">
                every {Math.round((worker.interval_seconds ?? 0) / 60)} min
              </p>
            </div>
            {canManage && worker.run_on_demand && (
              <Button
                size="sm"
                variant="secondary"
                onClick={() => onRun(worker.name)}
                disabled={busy}
              >
                <Play className="h-3.5 w-3.5" /> Run now
              </Button>
            )}
          </div>
        ))}
      </div>
    </Card>
  );
}

// ------------------------------------------------------------------ expertise

function ExpertiseTab({
  leaderboard,
  history,
  onSelect,
}: {
  leaderboard: ExpertiseLeaderEntry[];
  history: ExpertiseHistoryEntry[];
  onSelect: (history: ExpertiseHistoryEntry[]) => void;
}) {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card
        title="Expertise leaderboard"
        subtitle="Evolved continuously from organizational activity"
      >
        {leaderboard.length === 0 ? (
          <EmptyState
            icon={BarChart3}
            title="No expertise yet"
            description="Complete tasks, milestones and meetings to grow expertise."
          />
        ) : (
          <div className="space-y-2">
            {leaderboard.map((entry, index) => (
              <button
                key={entry.employee_id}
                onClick={async () =>
                  onSelect(await getExpertiseHistory(entry.employee_id, 25))
                }
                className="flex w-full items-center justify-between gap-3 rounded-lg border border-line px-3 py-2 text-left hover:bg-surface"
              >
                <div className="flex items-center gap-3">
                  <span className="w-5 text-center text-xs font-semibold text-faint">
                    {index + 1}
                  </span>
                  <div>
                    <p className="text-[13px] font-medium text-ink">
                      {entry.name}
                    </p>
                    <p className="text-xs text-faint">
                      {entry.designation ?? "Employee"}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {entry.top_skills?.slice(0, 2).map((skill) => (
                    <Badge key={skill.skill_id}>{skill.skill_name}</Badge>
                  ))}
                  <span className="text-sm font-bold text-brand">
                    {entry.expertise_score?.toFixed(0) ?? "0"}
                  </span>
                </div>
              </button>
            ))}
          </div>
        )}
      </Card>

      <Card
        title="Expertise evolution"
        subtitle="Activity deltas behind the scores"
      >
        {history.length === 0 ? (
          <EmptyState
            icon={Activity}
            title="Select an employee"
            description="Click a leader to see their expertise history."
          />
        ) : (
          <div className="divide-y divide-line">
            {history.map((entry) => (
              <div
                key={entry.id}
                className="flex items-center justify-between gap-3 py-2"
              >
                <div className="min-w-0">
                  <p className="truncate text-[13px] text-ink">
                    {entry.skill_name}
                  </p>
                  <p className="truncate text-xs text-faint">
                    {entry.reason ?? entry.source_event}
                  </p>
                </div>
                <Badge tone={entry.delta > 0 ? "success" : "neutral"}>
                  {entry.before} → {entry.after} (+{entry.delta})
                </Badge>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

// ------------------------------------------------------------------ graph

function GraphTab({
  stats,
  edges,
  bottlenecks,
  canManage,
  onDeactivate,
}: {
  stats: { [k: string]: unknown } | null;
  edges: GraphEdge[];
  bottlenecks: GraphPathStep[];
  canManage: boolean;
  onDeactivate: (edgeId: string) => void;
}) {
  const edgesByRelation = useMemo(() => {
    const map: Record<string, number> = {};
    for (const edge of edges)
      map[edge.relation] = (map[edge.relation] ?? 0) + 1;
    return map;
  }, [edges]);

  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Graph stats">
          <div className="flex flex-wrap gap-2">
            {Object.entries(stats ?? {}).map(([key, value]) => (
              <Badge key={key}>
                {key} {String(value)}
              </Badge>
            ))}
          </div>
        </Card>
        <Card title="Edges by relation">
          <div className="flex flex-wrap gap-2">
            {Object.entries(edgesByRelation).map(([relation, count]) => (
              <Badge key={relation} tone="brand">
                {relation} × {count}
              </Badge>
            ))}
          </div>
        </Card>
      </div>

      {bottlenecks.length > 0 && (
        <Card
          title="Collaboration bottlenecks"
          subtitle="Highly connected employees — risk concentration"
        >
          <div className="space-y-2">
            {bottlenecks.map((edge) => (
              <div
                key={String(edge.employee_id)}
                className="flex items-center justify-between rounded-lg border border-line px-3 py-2"
              >
                <div>
                  <p className="text-[13px] font-medium text-ink">
                    {String(edge.name ?? edge.employee_id)}
                  </p>
                  <p className="text-xs text-faint">
                    {String(edge.designation ?? "Employee")}
                  </p>
                </div>
                <Badge tone="warning">degree {Number(edge.degree ?? 0)}</Badge>
              </div>
            ))}
          </div>
        </Card>
      )}

      <Card
        title={`Org graph edges (${edges.length})`}
        subtitle="Structural + activity relationships"
        bodyClassName="p-0"
      >
        <div className="divide-y divide-line">
          {edges.slice(0, 80).map((edge) => (
            <div
              key={edge.id}
              className="flex items-center justify-between gap-3 px-5 py-2.5"
            >
              <div className="min-w-0">
                <p className="truncate text-[13px] text-ink">
                  {edge.source_name ?? edge.source_id}{" "}
                  <span className="text-faint">—{edge.relation}→</span>{" "}
                  {edge.target_name ?? edge.target_id}
                </p>
                <p className="truncate text-xs text-faint">{edge.evidence}</p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <Badge tone={edge.active ? "success" : "neutral"}>
                  {edge.active ? "active" : "inactive"}
                </Badge>
                {canManage && (
                  <button
                    onClick={() => onDeactivate(edge.id)}
                    className="rounded p-1 text-faint hover:text-danger"
                    title="Deactivate edge"
                  >
                    <CircleDot className="h-4 w-4" />
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

// ------------------------------------------------------------------ insights

function InsightRow({
  title,
  detail,
  status,
  tone,
  onAction,
}: {
  title: string;
  detail?: string;
  status: string;
  tone: string;
  onAction?: (status: string) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-3 px-5 py-3">
      <div className="min-w-0">
        <p className="truncate text-[13px] font-medium text-ink">{title}</p>
        {detail && <p className="truncate text-xs text-faint">{detail}</p>}
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <Badge tone={tone as never}>{status}</Badge>
        {onAction && status === "open" && (
          <Button
            size="sm"
            variant="secondary"
            onClick={() => onAction("accepted")}
          >
            Accept
          </Button>
        )}
        {onAction && status === "open" && (
          <Button
            size="sm"
            variant="ghost"
            onClick={() => onAction("dismissed")}
          >
            Dismiss
          </Button>
        )}
      </div>
    </div>
  );
}

function InsightsTab({
  knowledge,
  burnout,
  duplicates,
  patterns,
  workflow,
  onStatus,
  canManage,
}: {
  knowledge: KnowledgeInsight[];
  burnout: BurnoutSignal[];
  duplicates: DuplicateDetection[];
  patterns: PatternDetection[];
  workflow: WorkflowInsight[];
  onStatus: (kind: string, id: string, status: string) => void;
  canManage: boolean;
}) {
  const [section, setSection] = useState("knowledge");
  const sections = [
    { id: "knowledge", label: "Knowledge", count: knowledge.length },
    { id: "burnout", label: "Burnout", count: burnout.length },
    { id: "duplicates", label: "Duplicates", count: duplicates.length },
    { id: "patterns", label: "Patterns", count: patterns.length },
    { id: "workflow", label: "Workflow", count: workflow.length },
  ];
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-1 border-b border-line">
        {sections.map((s) => (
          <button
            key={s.id}
            onClick={() => setSection(s.id)}
            className={`border-b-2 px-3.5 py-2 text-[13px] font-medium ${
              section === s.id
                ? "border-brand text-ink"
                : "border-transparent text-faint"
            }`}
          >
            {s.label} ({s.count})
          </button>
        ))}
      </div>

      {section === "knowledge" && (
        <Card
          title="Knowledge insights"
          subtitle="Outdated, duplicate, unused and missing knowledge"
        >
          {knowledge.length === 0 ? (
            <EmptyState
              icon={FileSearch}
              title="No knowledge insights"
              description="The knowledge worker will surface issues here."
            />
          ) : (
            <div className="divide-y divide-line">
              {knowledge.map((insight) => (
                <InsightRow
                  key={insight.id}
                  title={insight.title}
                  detail={`${insight.kind} · ${Math.round(insight.confidence * 100)}% confident`}
                  status={insight.status}
                  tone={insight.kind === "outdated" ? "warning" : "neutral"}
                  onAction={
                    canManage
                      ? (status) => onStatus("knowledge", insight.id, status)
                      : undefined
                  }
                />
              ))}
            </div>
          )}
        </Card>
      )}

      {section === "burnout" && (
        <Card
          title="Burnout signals"
          subtitle="Workload patterns — task load, overdue pressure, meetings"
        >
          {burnout.length === 0 ? (
            <EmptyState
              icon={HeartPulse}
              title="No signals"
              description="No elevated workload patterns right now."
            />
          ) : (
            <div className="divide-y divide-line">
              {burnout.map((signal) => (
                <div
                  key={signal.id}
                  className="flex items-center justify-between gap-3 px-5 py-3"
                >
                  <div className="min-w-0">
                    <p className="truncate text-[13px] font-medium text-ink">
                      {signal.employee_name ?? signal.employee_id}
                    </p>
                    <p className="truncate text-xs text-faint">
                      {signal.signals_json
                        ? Object.entries(
                            signal.signals_json as Record<string, unknown>,
                          )
                            .map(([k, v]) => `${k} ${v as number}`)
                            .join(" · ")
                        : `score ${signal.score}`}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <Badge tone={levelTone(signal.level)}>
                      {signal.level} · {signal.score}
                    </Badge>
                    {canManage && signal.status === "open" && (
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() =>
                          onStatus("burnout", signal.id, "acknowledged")
                        }
                      >
                        Acknowledge
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      )}

      {section === "duplicates" && (
        <Card
          title="Duplicate detections"
          subtitle="Similar projects, tasks, meetings, policies and ideas"
        >
          {duplicates.length === 0 ? (
            <EmptyState
              icon={Copy}
              title="No duplicates"
              description="Nothing similar found in the current scan."
            />
          ) : (
            <div className="divide-y divide-line">
              {duplicates.map((duplicate) => (
                <InsightRow
                  key={duplicate.id}
                  title={duplicate.title_a ?? duplicate.id}
                  detail={`vs ${duplicate.title_b ?? "…"} · ${Math.round(duplicate.similarity * 100)}% similar`}
                  status={duplicate.status}
                  tone="warning"
                  onAction={
                    canManage
                      ? (status) =>
                          onStatus(
                            "duplicate",
                            duplicate.id,
                            status === "accepted" ? "confirmed" : "dismissed",
                          )
                      : undefined
                  }
                />
              ))}
            </div>
          )}
        </Card>
      )}

      {section === "patterns" && (
        <Card
          title="Repeated patterns"
          subtitle="Delays, bottlenecks and knowledge gaps that recur"
        >
          {patterns.length === 0 ? (
            <EmptyState
              icon={AlertTriangle}
              title="No patterns"
              description="No repeated organizational patterns detected."
            />
          ) : (
            <div className="divide-y divide-line">
              {patterns.map((pattern) => (
                <InsightRow
                  key={pattern.id}
                  title={pattern.title}
                  detail={`${pattern.detail ?? ""} · seen ${pattern.count}×`}
                  status={pattern.status}
                  tone="warning"
                  onAction={
                    canManage
                      ? (status) =>
                          onStatus(
                            "pattern",
                            pattern.id,
                            status === "accepted"
                              ? "acknowledged"
                              : "dismissed",
                          )
                      : undefined
                  }
                />
              ))}
            </div>
          )}
        </Card>
      )}

      {section === "workflow" && (
        <Card
          title="Workflow insights"
          subtitle="Slow approvals and automation opportunities"
        >
          {workflow.length === 0 ? (
            <EmptyState
              icon={ListChecks}
              title="No workflow insights"
              description="Approval flows look healthy."
            />
          ) : (
            <div className="divide-y divide-line">
              {workflow.map((insight) => (
                <InsightRow
                  key={insight.id}
                  title={insight.title}
                  detail={insight.detail}
                  status={insight.status}
                  tone={insight.severity === "critical" ? "danger" : "warning"}
                  onAction={
                    canManage
                      ? (status) => onStatus("workflow", insight.id, status)
                      : undefined
                  }
                />
              ))}
            </div>
          )}
        </Card>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ learning

function LearningTab({
  lessons,
  summary,
}: {
  lessons: LearningLesson[];
  summary: { total: number; by_type: Record<string, number> } | null;
}) {
  return (
    <div className="space-y-4">
      <Card title="Learning summary">
        <div className="flex flex-wrap gap-2">
          <Badge tone="brand">{summary?.total ?? 0} lessons</Badge>
          {Object.entries(summary?.by_type ?? {}).map(([type, count]) => (
            <Badge key={type}>
              {type} × {count}
            </Badge>
          ))}
        </div>
      </Card>
      <Card
        title="Lessons learned"
        subtitle="What the organization has learned — also stored in AI memory"
        bodyClassName="p-0"
      >
        {lessons.length === 0 ? (
          <EmptyState
            icon={BookOpen}
            title="No lessons yet"
            description="Lessons are captured as work completes."
          />
        ) : (
          <div className="divide-y divide-line">
            {lessons.map((lesson) => (
              <div key={lesson.id} className="px-5 py-3">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-[13px] font-medium text-ink">
                    {lesson.title}
                  </p>
                  <Badge>{lesson.event_type}</Badge>
                </div>
                {lesson.lesson && (
                  <p className="mt-1 text-xs text-muted">{lesson.lesson}</p>
                )}
                <p className="mt-0.5 text-xs text-faint">
                  {lesson.created_at
                    ? new Date(lesson.created_at).toLocaleDateString()
                    : ""}
                  {lesson.tags?.length ? ` · ${lesson.tags.join(", ")}` : ""}
                </p>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

// ------------------------------------------------------------------ collaboration

function CollabTab({
  metrics,
  onRefresh,
  busy,
}: {
  metrics: CollaborationMetrics | null;
  onRefresh: () => void;
  busy: boolean;
}) {
  if (!metrics || !Object.keys(metrics).length) {
    return (
      <EmptyState
        icon={GitBranch}
        title="No collaboration metrics yet"
        description="Run the collaboration worker to compute department interactions and silos."
        action={
          <Button
            size="sm"
            variant="secondary"
            onClick={onRefresh}
            disabled={busy}
          >
            <RefreshCw className="h-3.5 w-3.5" /> Refresh
          </Button>
        }
      />
    );
  }
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card
        title="Department pair interactions"
        subtitle="Cross-department collaboration strength"
      >
        {Array.isArray(metrics.department_pairs) &&
        metrics.department_pairs.length ? (
          <div className="space-y-2">
            {metrics.department_pairs.map((pair, index) => (
              <div
                key={index}
                className="flex items-center justify-between rounded-lg border border-line px-3 py-2"
              >
                <p className="text-[13px] text-ink">
                  {pair.a} ↔ {pair.b}
                </p>
                <Badge tone="brand">{pair.interactions} interactions</Badge>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-faint">
            No cross-department interactions yet.
          </p>
        )}
      </Card>
      <Card title="Department activity" subtitle="Interactions per department">
        <div className="space-y-2">
          {Object.entries(metrics.department_activity ?? {}).map(
            ([department, count]) => (
              <div
                key={department}
                className="flex items-center justify-between rounded-lg border border-line px-3 py-2"
              >
                <p className="text-[13px] text-ink">{department}</p>
                <Badge>{count as number} interactions</Badge>
              </div>
            ),
          )}
        </div>
        {Array.isArray(metrics.silos) && metrics.silos.length > 0 && (
          <div className="mt-4">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-faint">
              Potential silos
            </p>
            <div className="space-y-2">
              {metrics.silos.map((silo) => (
                <div
                  key={silo.employee_id}
                  className="rounded-lg border border-line px-3 py-2"
                >
                  <p className="text-[13px] text-ink">
                    {silo.name ?? silo.employee_id}
                  </p>
                  {silo.department_id && (
                    <p className="text-xs text-faint">{silo.department_id}</p>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}

// ------------------------------------------------------------------ briefs

function BriefCard({ brief }: { brief: DailyBrief | null }) {
  if (!brief) return null;
  return (
    <Card
      title={
        brief.brief_type === "executive"
          ? "Executive brief"
          : `Employee brief · ${brief.recipient_name ?? ""}`
      }
      subtitle={brief.brief_date}
    >
      <div className="space-y-3">
        {brief.sections.map((section, index) => (
          <div
            key={index}
            className="rounded-lg border border-line px-3 py-2.5"
          >
            <div className="flex items-center justify-between">
              <p className="text-[13px] font-semibold text-ink">
                {section.title}
              </p>
              <Badge tone={levelTone(section.severity)}>
                {section.severity}
              </Badge>
            </div>
            <ul className="mt-1.5 space-y-1">
              {section.items.map((item, itemIndex) => (
                <li key={itemIndex} className="text-xs text-muted">
                  • {item}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </Card>
  );
}

function BriefsTab({
  execBrief,
  employeeBrief,
  briefs,
  onLoad,
}: {
  execBrief: DailyBrief | null;
  employeeBrief: DailyBrief | null;
  briefs: DailyBrief[];
  onLoad: () => void;
}) {
  useEffect(() => {
    onLoad();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-2">
        <BriefCard brief={execBrief} />
        <BriefCard brief={employeeBrief} />
      </div>
      <Card
        title="Recent briefs"
        subtitle="Autonomously generated daily"
        bodyClassName="p-0"
      >
        {briefs.length === 0 ? (
          <EmptyState
            icon={Sparkles}
            title="No briefs yet"
            description="Generate the daily briefs to see the autonomous summaries."
          />
        ) : (
          <div className="divide-y divide-line">
            {briefs.map((brief) => (
              <div
                key={brief.id}
                className="flex items-center justify-between px-5 py-3"
              >
                <p className="text-[13px] font-medium text-ink">
                  {brief.brief_type === "executive"
                    ? "Executive brief"
                    : "Employee brief"}
                  {brief.recipient_name ? ` · ${brief.recipient_name}` : ""}
                </p>
                <Badge
                  tone={brief.brief_type === "executive" ? "brand" : "neutral"}
                >
                  {brief.brief_date}
                </Badge>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

// ------------------------------------------------------------------ feed

function FeedTab({
  feed,
  onRefresh,
  onStatus,
  busy,
}: {
  feed: RecommendationItem[];
  onRefresh: () => void;
  onStatus: (kind: string, id: string, status: string) => void;
  busy: boolean;
}) {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted">
          Personalized recommendations — experts to learn from, docs to read,
          communities to join.
        </p>
        <Button
          size="sm"
          variant="secondary"
          onClick={onRefresh}
          disabled={busy}
        >
          <RefreshCw className="h-3.5 w-3.5" /> Regenerate
        </Button>
      </div>
      {feed.length === 0 ? (
        <EmptyState
          icon={Zap}
          title="No recommendations yet"
          description="Regenerate your feed once there is more activity."
        />
      ) : (
        <div className="space-y-3">
          {feed.map((item) => (
            <Card key={item.id} className="p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <Badge tone="brand">{item.kind}</Badge>
                    <span className="text-xs text-faint">
                      score {Math.round(item.score * 10) / 10}
                    </span>
                  </div>
                  <p className="mt-1.5 text-[13px] font-semibold text-ink">
                    {item.title}
                  </p>
                  {item.body && (
                    <p className="mt-0.5 text-xs text-muted">{item.body}</p>
                  )}
                  {item.reasons?.length > 0 && (
                    <p className="mt-1 text-xs text-faint">
                      {item.reasons.join(" · ")}
                    </p>
                  )}
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <Badge>{item.status}</Badge>
                  {item.status === "active" && (
                    <>
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() =>
                          onStatus("recommendation", item.id, "accepted")
                        }
                      >
                        Accept
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() =>
                          onStatus("recommendation", item.id, "dismissed")
                        }
                      >
                        Dismiss
                      </Button>
                    </>
                  )}
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ risks & alerts

function RisksTab({
  risks,
  alerts,
  canManage,
  onScan,
  onGenerate,
  busy,
}: {
  risks: InsightRisk[];
  alerts: AutonomousNotification[];
  canManage: boolean;
  onScan: () => void;
  onGenerate: () => void;
  busy: boolean;
}) {
  const riskCounts = risks.reduce<Record<string, number>>((acc, risk) => {
    acc[risk.level] = (acc[risk.level] ?? 0) + 1;
    return acc;
  }, {});
  const alertTone = (priority: string) =>
    priority === "urgent"
      ? "danger"
      : priority === "high"
        ? "warning"
        : "neutral";

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Badge tone={risks.length > 0 ? "danger" : "success"}>
          {risks.length} open risks
        </Badge>
        <Badge tone="neutral">{alerts.length} autonomous notifications</Badge>
        {Object.entries(riskCounts).map(([level, count]) => (
          <Badge key={level} tone={levelTone(level)}>
            {level} {count}
          </Badge>
        ))}
        {canManage && (
          <span className="ml-auto flex gap-2">
            <Button
              size="sm"
              variant="secondary"
              onClick={onScan}
              disabled={busy}
            >
              <ScanSearch className="h-3.5 w-3.5" /> Scan for risks
            </Button>
            <Button
              size="sm"
              variant="secondary"
              onClick={onGenerate}
              disabled={busy}
            >
              <BellRing className="h-3.5 w-3.5" /> Generate alerts
            </Button>
          </span>
        )}
      </div>

      <Card
        title="Strategic risk register"
        subtitle="Background engine over intelligence signals"
        bodyClassName="p-0"
      >
        {risks.length === 0 ? (
          <EmptyState
            icon={AlertTriangle}
            title="No open risks"
            description="Run a risk scan or wait for the background worker to surface findings."
          />
        ) : (
          <div className="divide-y divide-line">
            {risks.map((risk) => (
              <div
                key={risk.id}
                className="flex items-start justify-between gap-3 px-5 py-3"
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <Badge tone={levelTone(risk.level)}>{risk.level}</Badge>
                    <Badge tone="neutral">{risk.kind}</Badge>
                    <span className="text-xs text-faint">
                      score {Math.round(risk.score * 100) / 100} ·{" "}
                      {Math.round(risk.probability * 100)}% ×{" "}
                      {Math.round(risk.impact * 100)}%
                    </span>
                  </div>
                  <p className="mt-1.5 text-[13px] font-semibold text-ink">
                    {risk.title}
                  </p>
                  {risk.description && (
                    <p className="mt-0.5 text-xs text-muted">
                      {risk.description}
                    </p>
                  )}
                  {risk.subject_name && (
                    <p className="mt-0.5 text-xs text-faint">
                      Subject: {risk.subject_name}
                      {risk.created_at
                        ? ` · ${new Date(risk.created_at).toLocaleString()}`
                        : ""}
                    </p>
                  )}
                </div>
                <Badge>{risk.status}</Badge>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card
        title="Autonomous notifications"
        subtitle="Risk alerts, burnout warnings and pattern flags"
        bodyClassName="p-0"
      >
        {alerts.length === 0 ? (
          <EmptyState
            icon={BellRing}
            title="No autonomous notifications"
            description="Generate alerts from open risks, burnout signals and repeated patterns."
          />
        ) : (
          <div className="divide-y divide-line">
            {alerts.map((alert) => (
              <div
                key={alert.id}
                className="flex items-start justify-between gap-3 px-5 py-3"
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <Badge tone={alertTone(alert.priority)}>
                      {alert.priority}
                    </Badge>
                    <Badge tone="neutral">{alert.type}</Badge>
                  </div>
                  <p className="mt-1.5 text-[13px] font-semibold text-ink">
                    {alert.title}
                  </p>
                  {alert.body && (
                    <p className="mt-0.5 text-xs text-muted">{alert.body}</p>
                  )}
                  {alert.created_at && (
                    <p className="mt-0.5 text-xs text-faint">
                      {new Date(alert.created_at).toLocaleString()}
                    </p>
                  )}
                </div>
                <Badge>{alert.entity_type ?? "—"}</Badge>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
