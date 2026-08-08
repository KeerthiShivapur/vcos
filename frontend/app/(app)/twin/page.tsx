"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  CheckSquare2,
  Clock,
  HeartPulse,
  Lightbulb,
  Network,
  Newspaper,
  Play,
  RefreshCw,
  Send,
  Sparkles,
  TrendingUp,
  Users,
  Workflow,
  Zap,
} from "lucide-react";
import { useSearchParams } from "next/navigation";

import { Badge, statusTone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader, StatCard } from "@/components/ui/PageHeader";
import { Tabs } from "@/components/ui/Tabs";
import { useAuth } from "@/hooks/useAuth";
import { useFetch } from "@/hooks/useFetch";
import { api } from "@/lib/api";
import { PERMISSIONS, roleCan } from "@/lib/permissions";
import {
  askTwin,
  generateTwinForecasts,
  generateOptimizations,
  generatePredictions,
  generateRecommendations,
  getTwin,
  getTwinHealth,
  getTwinHealthHistory,
  getTwinHistory,
  listPredictions,
  listTwinSimulations,
  runTwinSimulation,
  setTwinRecommendationStatus,
  type TwinHealth,
  type TwinPrediction,
  type TwinRecommendation,
  type TwinSimulation,
  type TwinSnapshot,
  type TwinState,
} from "@/lib/api";
import { classNames } from "@/lib/utils";

type TabId = "overview" | "health" | "predictions" | "simulations" | "recommendations" | "decisions" | "brief";

const TABS: { id: TabId; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
  { id: "overview", label: "Overview", icon: Activity },
  { id: "health", label: "Company Health", icon: HeartPulse },
  { id: "predictions", label: "Predictions", icon: TrendingUp },
  { id: "simulations", label: "Simulations", icon: Play },
  { id: "recommendations", label: "Recommendations", icon: CheckSquare2 },
  { id: "decisions", label: "Decisions", icon: Network },
  { id: "brief", label: "Morning Brief", icon: Newspaper },
];

function healthTone(score?: number | null): "success" | "warning" | "danger" | "neutral" {
  if (score === null || score === undefined) return "neutral";
  if (score >= 75) return "success";
  if (score >= 50) return "warning";
  return "danger";
}

function levelTone(level?: string): "success" | "warning" | "danger" | "neutral" {
  switch (level) {
    case "critical":
    case "high":
      return "danger";
    case "medium":
    case "watch":
      return "warning";
    case "low":
    case "positive":
      return "success";
    default:
      return "neutral";
  }
}

export default function TwinPage() {
  return (
    <Suspense fallback={null}>
      <TwinContent />
    </Suspense>
  );
}

function TwinContent() {
  const { user } = useAuth();
  const searchParams = useSearchParams();
  const canManage = user ? roleCan(user.role, PERMISSIONS.DIGITAL_TWIN_MANAGE) : false;
  const initial = (searchParams.get("tab") as TabId) || "overview";
  const [active, setActive] = useState<TabId>(
    TABS.some((t) => t.id === initial) ? initial : "overview"
  );

  const [twinData, setTwinData] = useState<TwinState | null>(null);
  const [healthData, setHealthData] = useState<TwinHealth | null>(null);
  const [healthHistory, setHealthHistory] = useState<TwinHealth[]>([]);
  const [twinHistory, setTwinHistory] = useState<TwinSnapshot[]>([]);
  const [predictions, setPredictions] = useState<TwinPrediction[]>([]);
  const [recommendations, setRecommendations] = useState<TwinRecommendation[]>([]);
  const [simulations, setSimulations] = useState<TwinSimulation[]>([]);
  const [running, setRunning] = useState(false);
  const [busy, setBusy] = useState(false);
  const [scenario, setScenario] = useState("growth");
  const [simResult, setSimResult] = useState<TwinSimulation | null>(null);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<{ answer: string; data: Record<string, unknown> } | null>(null);

  const briefFetch = useFetch<Record<string, unknown>>("/twin/brief");  const refresh = useCallback(async () => {
    setBusy(true);
    try {
      const [twin, health, history, healthHistoryRows, preds, recs, sims] = await Promise.all([
        getTwin(true),
        getTwinHealth(),
        getTwinHistory(30),
        getTwinHealthHistory(30),
        listPredictions(),
        api<{ total: number; recommendations: TwinRecommendation[] }>("/twin/recommendations"),
        listTwinSimulations(),
      ]);
      setTwinData(twin);
      setHealthData(health);
      setTwinHistory(history.history);
      setHealthHistory(healthHistoryRows.history);
      setPredictions(preds.predictions);
      setRecommendations(recs.recommendations);
      setSimulations(sims.simulations);
    } catch (error) {
      console.error("twin refresh failed", error);
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void (async () => {
      const [twin, health, history, healthHistoryRows, preds, recs, sims] = await Promise.all([
        getTwin(),
        getTwinHealth(),
        getTwinHistory(30),
        getTwinHealthHistory(30),
        listPredictions(),
        generateRecommendations().catch(() => ({ total: 0, recommendations: [] as TwinRecommendation[] })),
        listTwinSimulations(),
      ]);
      setTwinData(twin);
      setHealthData(health);
      setTwinHistory(history.history);
      setHealthHistory(healthHistoryRows.history);
      setPredictions(preds.predictions);
      setRecommendations(recs.recommendations);
      setSimulations(sims.simulations);
    })();
  }, []);

  const runGenerate = async (kind: "predictions" | "recommendations" | "optimizations" | "forecasts") => {
    setBusy(true);
    try {
      if (kind === "predictions") {
        const res = await generatePredictions();
        setPredictions(res.predictions);
      } else if (kind === "recommendations") {
        const res = await generateRecommendations();
        setRecommendations(res.recommendations);
      } else if (kind === "optimizations") {
        await generateOptimizations();
      } else {
        await generateTwinForecasts();
      }
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  const runScenario = async () => {
    setRunning(true);
    setSimResult(null);
    try {
      const result = await runTwinSimulation(scenario);
      setSimResult(result);
      setSimulations((prev) => [result, ...prev].slice(0, 20));
    } finally {
      setRunning(false);
    }
  };

  const decideRecommendation = async (id: string, status: "accepted" | "dismissed") => {
    await setTwinRecommendationStatus(id, status);
    setRecommendations((prev) => prev.map((r) => (r.id === id ? { ...r, status } : r)));
  };

  const ask = async () => {
    if (!question.trim()) return;
    const res = await askTwin(question);
    setAnswer({ answer: res.answer, data: (res.context ?? {}) as Record<string, unknown> });
  };

  const counts = twinData?.entity_counts ?? {};
  const state = twinData?.state ?? {};
  const healthScore = healthData?.score ?? twinData?.health_score ?? null;
  const predictionsList = useMemo(() => predictions, [predictions]);

  const decideHistory = twinData?.state_history ?? [];
  const latestSnapshot = decideHistory[decideHistory.length - 1];

  return (
    <div>
      <PageHeader
        breadcrumb="Phase 18 · Autonomous Enterprise"
        title="Digital Twin"
        description="A living model of your organization — health, predictions, simulations, recommendations and decisions."
        actions={
          canManage ? (
            <Button onClick={() => refresh()} disabled={busy} variant="primary">
              <RefreshCw className="h-4 w-4" /> Refresh twin
            </Button>
          ) : undefined
        }
      />

      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label="Company health" value={healthScore !== null ? `${Math.round(healthScore)}/100` : "—"} hint={healthData?.status ?? twinData?.health_status ?? "pending"} icon={HeartPulse} />
        <StatCard label="Employees" value={counts.employees ?? 0} hint={`${counts.active_employees ?? 0} active`} icon={Users} />
        <StatCard label="Active projects" value={counts.active_projects ?? 0} hint={`${counts.open_tasks ?? 0} open tasks`} icon={Workflow} />
        <StatCard label="Knowledge items" value={counts.documents ?? 0} hint={`${counts.wiki_pages ?? 0} wiki pages`} icon={Lightbulb} />
      </div>

      <Tabs tabs={TABS} active={active} onChange={(id) => setActive(id as TabId)} />

      <div className="mt-6">
        {active === "overview" && (
          <div className="space-y-6">
            <div className="grid gap-3 lg:grid-cols-3">
              <Card className="lg:col-span-2">
                <div className="mb-3 flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-ink">Organizational state</h3>
                  <Badge tone={healthTone(healthScore)}>{healthData?.status ?? twinData?.health_status ?? "pending"}</Badge>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  {[
                    ["Workload / employee", state.workload_per_employee ?? 0],
                    ["Meetings", state.meetings ?? 0],
                    ["Customers", state.customers ?? 0],
                    ["Collaboration activity", state.collaboration_activity ?? 0],
                    ["Knowledge growth", state.knowledge_growth ?? 0],
                    ["Workflow executions", state.workflow_executions ?? 0],
                  ].map(([label, value]) => (
                    <div key={String(label)} className="rounded-lg border border-line bg-surface p-3">
                      <p className="text-xs text-faint">{String(label)}</p>
                      <p className="mt-1 text-lg font-semibold text-ink">{String(value)}</p>
                    </div>
                  ))}
                </div>
              </Card>
              <Card>
                <h3 className="mb-3 text-sm font-semibold text-ink">Entity counts</h3>
                <div className="space-y-2">
                  {Object.entries(counts)
                    .slice(0, 12)
                    .map(([key, value]) => (
                      <div key={key} className="flex items-center justify-between text-sm">
                        <span className="text-muted">{key.replace(/_/g, " ")}</span>
                        <span className="font-medium text-ink">{value}</span>
                      </div>
                    ))}
                </div>
              </Card>
            </div>

            <Card>
              <div className="mb-3 flex items-center justify-between">
                <h3 className="text-sm font-semibold text-ink">Twin intelligence</h3>
                {canManage && (
                  <div className="flex gap-2">
                    <Button size="sm" onClick={() => runGenerate("predictions")} disabled={busy}><Sparkles className="h-4 w-4" /> Predict</Button>
                    <Button size="sm" onClick={() => runGenerate("recommendations")} disabled={busy}><Zap className="h-4 w-4" /> Recommend</Button>
                    <Button size="sm" onClick={() => runGenerate("optimizations")} disabled={busy}><TrendingUp className="h-4 w-4" /> Optimize</Button>
                  </div>
                )}
              </div>
                  {latestSnapshot ? (
                <div className="space-y-2 text-sm text-muted">
                  <p>Snapshot from {latestSnapshot.captured_at ? new Date(latestSnapshot.captured_at).toLocaleString() : "—"}</p>
                  {Object.entries(latestSnapshot.state ?? {}).slice(0, 8).map(([key, value]) => (
                    <div key={key} className="flex justify-between border-b border-line py-1 last:border-0">
                      <span>{key.replace(/_/g, " ")}</span>
                      <span className="font-medium text-ink">{String(value)}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyState title="No twin data yet" description="Refresh the twin to build your organization model." />
              )}
            </Card>
          </div>
        )}

        {active === "health" && (
          <div className="space-y-6">
            <div className="flex items-center gap-4">
              <div
                className={classNames(
                  "flex h-28 w-28 items-center justify-center rounded-full border-4 text-center",
                  healthTone(healthScore) === "success" && "border-success/60",
                  healthTone(healthScore) === "warning" && "border-warning/60",
                  healthTone(healthScore) === "danger" && "border-danger/60"
                )}
              >
                <div>
                  <p className="text-3xl font-bold text-ink">{healthScore !== null ? Math.round(healthScore) : "—"}</p>
                  <p className="text-xs text-faint">/100</p>
                </div>
              </div>
              <div className="text-sm text-muted">
                <p className="font-medium text-ink">Overall health</p>
                <p>Updated {healthData?.generated_at ? new Date(healthData.generated_at).toLocaleString() : "—"}</p>
                {canManage && (
                  <Button className="mt-2" size="sm" onClick={() => refresh()} disabled={busy}><RefreshCw className="h-4 w-4" /> Recompute</Button>
                )}
              </div>
            </div>
            {healthData?.breakdown && (
              <Card>
                <h3 className="mb-3 text-sm font-semibold text-ink">Dimension scores</h3>
                <div className="space-y-3">
                  {Object.entries(healthData.breakdown).map(([key, dim]) => (
                    <div key={key}>
                      <div className="mb-1 flex items-center justify-between text-sm">
                        <span className="capitalize text-muted">{key.replace(/_/g, " ")}</span>
                        <span className="flex items-center gap-2">
                          <Badge tone={levelTone(dim?.status)}>{dim?.status ?? "—"}</Badge>
                          <span className="font-medium text-ink">{dim?.score !== undefined ? Math.round(dim.score) : "—"}</span>
                        </span>
                      </div>
                      <div className="h-2 overflow-hidden rounded-full bg-surface">
                        <div
                          className="h-full rounded-full bg-brand"
                          style={{ width: `${Math.min(100, Math.max(0, dim?.score ?? 0))}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </Card>
            )}
            <Card>
              <h3 className="mb-3 text-sm font-semibold text-ink">Health history</h3>
              <div className="space-y-2">
                {healthHistory.map((row) => (
                  <div key={row.id} className="flex items-center justify-between text-sm">
                    <span className="text-muted">{row.generated_at ? new Date(row.generated_at).toLocaleString() : "—"}</span>
                    <span className="flex items-center gap-2">
                      <Badge tone={levelTone(row.status)}>{row.status}</Badge>
                      <span className="font-medium text-ink">{row.score !== undefined ? Math.round(row.score) : "—"}</span>
                    </span>
                  </div>
                ))}
                {healthHistory.length === 0 && (
                  <EmptyState title="No health history" description="Health records appear after the first computation." />
                )}
              </div>
            </Card>
          </div>
        )}

        {active === "predictions" && (
          <div className="space-y-4">
                  {canManage && (
                    <Button onClick={() => runGenerate("predictions")} disabled={busy}>
                      <Sparkles className="h-4 w-4" /> Generate predictions
                    </Button>
                  )}
            <Card>
              <div className="space-y-3">
                {predictionsList.length === 0 && (
                  <EmptyState title="No predictions yet" description="Generate predictions to surface opportunities and risks." />
                )}
                {predictionsList.map((p) => (
                  <div key={p.id} className="flex items-start justify-between gap-3 rounded-lg border border-line p-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <Badge tone={levelTone(p.level)}>{p.level}</Badge>
                        <Badge tone="neutral">{p.kind}</Badge>
                        <span className="text-xs text-faint">{p.horizon_days ? `${p.horizon_days}d horizon` : ""}</span>
                      </div>
                      <p className="mt-1 text-sm font-medium text-ink">{p.title}</p>
                      {p.description && <p className="mt-1 text-xs text-muted">{p.description}</p>}
                      {p.probability !== undefined && p.probability !== null && (
                        <p className="mt-1 text-xs text-muted">Probability {Math.round(p.probability * 100)}% · impact {p.impact ?? "—"}</p>
                      )}
                    </div>
                    {p.status === "pending" && canManage && (
                      <div className="flex shrink-0 gap-2">
                        <Button size="sm" onClick={() => acknowledgePrediction(p.id)}>Acknowledge</Button>
                        <Button size="sm" variant="secondary" onClick={() => dismissPrediction(p.id)}>Dismiss</Button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </Card>
          </div>
        )}

        {active === "simulations" && (
          <div className="space-y-4">
            <Card>
              <h3 className="mb-2 text-sm font-semibold text-ink">Run a what-if simulation</h3>
              {canManage ? (
                <>
                  <div className="flex flex-wrap gap-2">
                    {["growth", "cost_cut", "reorg", "expansion", "attrition", "automation", "acquisition"].map((s) => (
                      <button
                        key={s}
                        onClick={() => setScenario(s)}
                        className={classNames(
                          "rounded-full border px-3 py-1 text-xs font-medium transition-colors",
                          scenario === s ? "border-brand bg-brand-soft text-brand" : "border-line text-muted hover:text-ink"
                        )}
                      >
                        {s.replace(/_/g, " ")}
                      </button>
                    ))}
                  </div>
                  <Button className="mt-3" onClick={runScenario} disabled={running}>
                    <Play className="h-4 w-4" /> {running ? "Simulating…" : "Run simulation"}
                  </Button>
                </>
              ) : (
                <p className="text-sm text-muted">You need the digital_twin:manage permission to run simulations.</p>
              )}
            </Card>

            {simResult && (
              <Card>
                <div className="mb-2 flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-ink">Latest simulation</h3>
                  <Badge tone={levelTone(String(simResult.results?.risk))}>Risk {simResult.results?.risk ?? "—"}/100</Badge>
                </div>
                <div className="grid grid-cols-3 gap-3">
                  <StatCard label="Risk" value={simResult.results?.risk ?? "—"} icon={AlertTriangle} />
                  <StatCard label="Cost" value={String(simResult.results?.cost ?? "—")} icon={BarChart3} />
                  <StatCard label="Timeline" value={String(simResult.results?.timeline ?? "—")} icon={Clock} />
                </div>
                <p className="mt-3 text-sm text-muted">{String(simResult.results?.summary ?? "")}</p>
              </Card>
            )}

            <Card>
              <h3 className="mb-3 text-sm font-semibold text-ink">Simulation history</h3>
              <div className="space-y-2">
                {simulations.length === 0 && <EmptyState title="No simulations yet" />}
                {simulations.map((s) => (
                  <div key={s.id} className="flex items-center justify-between rounded-lg border border-line p-3 text-sm">
                    <div>
                      <p className="font-medium text-ink">{s.scenario.replace(/_/g, " ")}</p>
                      <p className="text-xs text-faint">{s.created_at ? new Date(s.created_at).toLocaleString() : ""}</p>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-muted">risk {s.results?.risk ?? "—"}</span>
                      <span className="text-muted">{String(s.results?.cost ?? "—")}</span>
                      <Badge tone={statusTone(s.status ?? "pending")}>{s.status ?? "pending"}</Badge>
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          </div>
        )}

        {active === "recommendations" && (
          <div className="space-y-4">
            {canManage && (
              <Button onClick={() => runGenerate("recommendations")} disabled={busy}>
                <Zap className="h-4 w-4" /> Generate recommendations
              </Button>
            )}
            <Card>
              <div className="space-y-3">
                {recommendations.length === 0 && (
                  <EmptyState title="No recommendations yet" description="Generate recommendations to surface executive actions." />
                )}
                {recommendations.map((r) => (
                  <div key={r.id} className="flex items-start justify-between gap-3 rounded-lg border border-line p-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <Badge tone={levelTone(r.impact ?? r.kind)}>{r.impact ?? r.kind}</Badge>
                        <Badge tone="neutral">{r.kind}</Badge>
                      </div>
                      <p className="mt-1 text-sm font-medium text-ink">{r.title}</p>
                      {r.rationale && <p className="mt-1 text-xs text-muted">{r.rationale}</p>}
                    </div>
                    {r.status === "pending" && canManage ? (
                      <div className="flex shrink-0 gap-2">
                        <Button size="sm" onClick={() => decideRecommendation(r.id, "accepted")}>Accept</Button>
                        <Button size="sm" variant="secondary" onClick={() => decideRecommendation(r.id, "dismissed")}>Dismiss</Button>
                      </div>
                    ) : (
                      <Badge tone={statusTone(r.status)}>{r.status}</Badge>
                    )}
                  </div>
                ))}
              </div>
            </Card>
          </div>
        )}

        {active === "decisions" && (
          <div className="space-y-4">
            <Card>
              <h3 className="mb-2 text-sm font-semibold text-ink">Decision history</h3>
              <div className="space-y-2">
                {twinHistory.length === 0 && <EmptyState title="No snapshots yet" description="Refresh the twin to start recording state history." />}
                {twinHistory.map((row) => {
                  const snap = row.state ?? {};
                  return (
                    <div key={row.id} className="flex items-center justify-between rounded-lg border border-line p-3 text-sm">
                      <div className="flex items-center gap-3">
                        <span className="text-muted">{row.captured_at ? new Date(row.captured_at).toLocaleString() : "—"}</span>
                        <span className="text-ink">{String(snap.employees ?? 0)} employees</span>
                        <span className="text-ink">{String(snap.active_projects ?? 0)} projects</span>
                      </div>
                      <span className="text-xs text-faint">{String(snap.open_tasks ?? 0)} open tasks</span>
                    </div>
                  );
                })}
              </div>
            </Card>
          </div>
        )}

        {active === "brief" && (
          <div className="space-y-4">
            <Card>
              <div className="mb-3 flex items-center gap-2">
                <Newspaper className="h-4 w-4 text-brand" />
                <h3 className="text-sm font-semibold text-ink">Executive intelligence brief</h3>
              </div>
              {briefFetch.data ? (
                <pre className="whitespace-pre-wrap rounded-lg bg-surface p-3 text-sm text-muted">
                  {JSON.stringify(briefFetch.data, null, 2)}
                </pre>
              ) : briefFetch.loading ? (
                <p className="text-sm text-muted">Compiling your brief…</p>
              ) : (
                <EmptyState title="Brief unavailable" />
              )}
            </Card>

            <Card>
              <h3 className="mb-3 text-sm font-semibold text-ink">Ask the twin</h3>
              <div className="flex gap-2">
                <input
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && ask()}
                  placeholder="e.g. What is our biggest risk right now?"
                  className="flex-1 rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink outline-none focus:border-brand"
                />
                <Button onClick={ask} disabled={!question.trim()}><Send className="h-4 w-4" /> Ask</Button>
              </div>
              {answer && (
                <div className="mt-4 space-y-3">
                  <p className="text-sm text-muted">{answer.answer}</p>
                  {answer.data && Object.keys(answer.data).length > 0 && (
                    <pre className="whitespace-pre-wrap rounded-lg bg-surface p-3 text-xs text-faint">
                      {JSON.stringify(answer.data, null, 2)}
                    </pre>
                  )}
                </div>
              )}
            </Card>
          </div>
        )}
      </div>
    </div>
  );
}

async function acknowledgePrediction(id: string) {
  await api<{ status: string }>(`/twin/predictions/${id}/acknowledge`, { method: "POST" });
}

async function dismissPrediction(id: string) {
  await api<{ status: string }>(`/twin/predictions/${id}/dismiss`, { method: "POST" });
}
