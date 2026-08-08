"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  CalendarClock,
  CheckCircle2,
  HeartPulse,
  Lightbulb,
  Network,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  Target,
  TrendingUp,
} from "lucide-react";

import {
  askStrategy,
  createStrategicGoal,
  getExecutiveIntelligence,
  getExecutiveTrends,
  getOrganizationTimeline,
  getStrategyPlan,
  listStrategicGoals,
  runSimulation,
  updateRecommendationStatus,
  updateStrategicGoal,
  updateStrategicRiskStatus,
} from "@/lib/api";
import type {
  ExecutiveIntelligenceDashboard,
  StrategicGoal,
  StrategyPlan,
  ExecutiveTimelineEntry,
  TrendSeries,
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
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";

const BREAKDOWN_LABELS: Record<string, string> = {
  project_execution: "Project execution",
  task_completion: "Task completion",
  meeting_effectiveness: "Meeting effectiveness",
  knowledge_growth: "Knowledge growth",
  employee_workload: "Employee workload",
  community_engagement: "Community engagement",
  learning_progress: "Learning progress",
  innovation: "Innovation",
  policy_compliance: "Policy compliance",
  risk_management: "Risk management",
  goals: "Goals",
};

const SCENARIOS: Record<string, string> = {
  hire_engineers: "Hire engineers",
  delay_release: "Delay release",
  lose_specialist: "Lose a specialist",
  sales_increase: "Sales increase",
  merge_teams: "Merge teams",
  expand: "Expand to new region",
  reduce_meetings: "Reduce meetings",
};

export default function ExecutivePage() {
  return (
    <Suspense fallback={null}>
      <ExecutiveContent />
    </Suspense>
  );
}

function healthTone(status: string): "success" | "warning" | "danger" {
  if (status === "excellent" || status === "good") return "success";
  if (status === "watch") return "warning";
  return "danger";
}

function ExecutiveContent() {
  const { user } = useAuth();
  const canManage = roleCan(user?.role, PERMISSIONS.EXECUTIVE_MANAGE);

  const [data, setData] = useState<ExecutiveIntelligenceDashboard | null>(null);
  const [trends, setTrends] = useState<TrendSeries[]>([]);
  const [timeline, setTimeline] = useState<ExecutiveTimelineEntry[]>([]);
  const [goals, setGoals] = useState<StrategicGoal[]>([]);
  const [plan, setPlan] = useState<StrategyPlan | null>(null);

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [askInput, setAskInput] = useState("");
  const [askResult, setAskResult] = useState<string | null>(null);
  const [askBusy, setAskBusy] = useState(false);

  const [goalName, setGoalName] = useState("");
  const [goalFocus, setGoalFocus] = useState("growth");
  const [goalBusy, setGoalBusy] = useState(false);

  const [planBusy, setPlanBusy] = useState(false);

  const [simScenario, setSimScenario] = useState("hire_engineers");
  const [simCount, setSimCount] = useState("3");
  const [simBusy, setSimBusy] = useState(false);
  const [simResult, setSimResult] = useState<string | null>(null);

  async function load(force = false) {
    if (force) setRefreshing(true);
    setError(null);
    try {
      const [dash, trendData, timelineData, goalsData] = await Promise.all([
        getExecutiveIntelligence(force),
        getExecutiveTrends("weekly"),
        getOrganizationTimeline(15),
        listStrategicGoals(),
      ]);
      setData(dash);
      setTrends(trendData.trends);
      setTimeline(timelineData.entries);
      setGoals(goalsData.goals);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load executive intelligence");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const topTrends = useMemo(
    () => [...trends].sort((a, b) => b.last - a.last).slice(0, 6),
    [trends]
  );

  async function acceptRecommendation(id: string) {
    await updateRecommendationStatus(id, "accepted");
    await load(false);
  }

  async function acceptRisk(id: string) {
    await updateStrategicRiskStatus(id, "accepted");
    await load(false);
  }

  async function createGoal() {
    if (!goalName.trim()) return;
    setGoalBusy(true);
    try {
      await createStrategicGoal({ name: goalName.trim(), focus: goalFocus, timeframe: "quarter" });
      setGoalName("");
      setGoals((await listStrategicGoals()).goals);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create goal");
    } finally {
      setGoalBusy(false);
    }
  }

  async function advanceGoal(goal: StrategicGoal) {
    const next = goal.status === "planned" ? "active" : goal.status === "active" ? "completed" : "active";
    await updateStrategicGoal(goal.id, { status: next });
    setGoals((await listStrategicGoals()).goals);
  }

  async function generatePlan() {
    setPlanBusy(true);
    try {
      setPlan(await getStrategyPlan("quarter"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not generate plan");
    } finally {
      setPlanBusy(false);
    }
  }

  async function ask() {
    if (!askInput.trim()) return;
    setAskBusy(true);
    setAskResult(null);
    try {
      setAskResult((await askStrategy(askInput.trim())).answer);
    } catch (err) {
      setAskResult(err instanceof Error ? err.message : "Could not answer");
    } finally {
      setAskBusy(false);
    }
  }

  async function runSim() {
    setSimBusy(true);
    setSimResult(null);
    try {
      const result = await runSimulation(simScenario, { count: Number(simCount) || 3 });
      const relief = result.results.workload_relief_percent;
      setSimResult(
        `"${result.title}" — baseline ${JSON.stringify(result.baseline)}. ` +
          `Assumptions: ${result.assumptions.join("; ")}.` +
          (relief !== undefined ? ` Workload relief: ${relief}%.` : "") +
          (result.risks.length ? ` Risks: ${result.risks.join("; ")}.` : "") +
          (result.opportunities.length ? ` Opportunities: ${result.opportunities.join("; ")}.` : "")
      );
    } catch (err) {
      setSimResult(err instanceof Error ? err.message : "Could not run simulation");
    } finally {
      setSimBusy(false);
    }
  }

  if (error) return <ErrorState title="Could not load executive intelligence" message={error} />;
  if (loading || !data) {
    return <div className="flex justify-center py-24"><Spinner label="Loading executive intelligence" /></div>;
  }

  const health = data.health;
  const tone = healthTone(health.status);
  const att = data.attention;

  return (
    <div className="space-y-6">
      <PageHeader
        breadcrumb="Executive Intelligence"
        title={`${data.organization.name} — Company Digital Twin`}
        description={data.summary}
        actions={
          <Button variant="secondary" size="sm" loading={refreshing} onClick={() => load(true)}>
            <RefreshCw className="h-3.5 w-3.5" /> Recompute intelligence
          </Button>
        }
      />

      <div className={`card p-6 ${tone === "danger" ? "border-danger/40" : tone === "warning" ? "border-warning/40" : "border-success/30"}`}>
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className={`flex h-14 w-14 items-center justify-center rounded-2xl ${tone === "success" ? "bg-success/10 text-success" : tone === "warning" ? "bg-warning/10 text-warning" : "bg-danger/10 text-danger"}`}>
              <HeartPulse className="h-6 w-6" />
            </div>
            <div>
              <p className="text-sm font-semibold text-ink">Company health</p>
              <div className="flex items-center gap-2">
                <span className="text-3xl font-bold tracking-tight text-ink">{Math.round(health.score)}</span>
                <span className="text-sm text-faint">/ 100</span>
                <Badge tone={tone}>{health.status}</Badge>
              </div>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-x-8 gap-y-1 text-[13px] sm:grid-cols-4">
            <div><p className="text-faint">Active projects</p><p className="font-semibold text-ink">{health.counts.active_projects}</p></div>
            <div><p className="text-faint">Open tasks</p><p className="font-semibold text-ink">{health.counts.tasks_total}</p></div>
            <div><p className="text-faint">Overdue</p><p className="font-semibold text-danger">{health.counts.tasks_overdue}</p></div>
            <div><p className="text-faint">Employees</p><p className="font-semibold text-ink">{health.counts.employees_active}</p></div>
          </div>
        </div>
        <div className="mt-5 h-2.5 overflow-hidden rounded-full bg-canvas">
          <div
            className={`h-full rounded-full ${tone === "success" ? "bg-success" : tone === "warning" ? "bg-warning" : "bg-danger"}`}
            style={{ width: `${Math.max(2, health.score)}%` }}
          />
        </div>
        <div className="mt-5 grid gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
          {Object.entries(health.breakdown).map(([key, value]) => (
            <div key={key}>
              <div className="flex items-center justify-between text-[12px]">
                <span className="text-muted">{BREAKDOWN_LABELS[key] ?? key}</span>
                <span className="font-semibold text-ink">{Math.round(Number(value))}%</span>
              </div>
              <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-canvas">
                <div
                  className={`h-full rounded-full ${Number(value) >= 75 ? "bg-success" : Number(value) >= 55 ? "bg-warning" : "bg-danger"}`}
                  style={{ width: `${Math.max(2, Number(value))}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <AttentionCard label="Critical risks" value={att.critical_risks} tone={att.critical_risks > 0 ? "danger" : "success"} icon={ShieldAlert} />
        <AttentionCard label="Active recommendations" value={att.active_recommendations} tone={att.active_recommendations > 0 ? "brand" : "success"} icon={Lightbulb} />
        <AttentionCard label="Overdue tasks" value={att.overdue_tasks} tone={att.overdue_tasks > 0 ? "warning" : "success"} icon={AlertTriangle} />
        <AttentionCard label="Overloaded employees" value={att.overloaded_employees} tone={att.overloaded_employees > 0 ? "warning" : "success"} icon={Activity} />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Strategic risks" subtitle="AI-detected with probability × impact" actions={
          data.risks.length > 0 && canManage ? (
            <Button variant="ghost" size="sm" onClick={() => acceptRisk(data.risks[0].id)}>Accept top risk</Button>
          ) : undefined
        }>
          {data.risks.length === 0 ? (
            <EmptyState icon={CheckCircle2} title="No open strategic risks" description="The risk engine watches deadlines, dependencies, workloads and knowledge gaps." />
          ) : (
            <ul className="space-y-3">
              {data.risks.slice(0, 6).map((r) => (
                <li key={r.id} className="rounded-xl border border-line p-3.5">
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-[13px] font-semibold text-ink">{r.title}</p>
                    <Badge tone={r.level === "critical" ? "danger" : r.level === "high" ? "warning" : "neutral"}>{r.level}</Badge>
                  </div>
                  <p className="mt-1 text-[12px] text-muted">{r.description}</p>
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-faint">
                    <span>Probability {Math.round(r.probability * 100)}%</span>
                    <span>×</span>
                    <span>Impact {Math.round(r.impact * 100)}%</span>
                    <span>=</span>
                    <span className="font-semibold text-ink">score {r.score.toFixed(2)}</span>
                  </div>
                  {r.recommended_actions.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {r.recommended_actions.slice(0, 3).map((a) => (
                        <span key={a} className="rounded-full bg-canvas px-2 py-0.5 text-[11px] text-muted">{a}</span>
                      ))}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Recommendations" subtitle="AI-suggested actions with confidence and expected outcome" actions={
          data.recommendations.length > 0 && canManage ? (
            <Button variant="ghost" size="sm" onClick={() => acceptRecommendation(data.recommendations[0].id)}>Accept top recommendation</Button>
          ) : undefined
        }>
          {data.recommendations.length === 0 ? (
            <EmptyState icon={Lightbulb} title="No active recommendations" description="Recommendations appear when the engines find actions worth taking." />
          ) : (
            <ul className="space-y-3">
              {data.recommendations.slice(0, 6).map((r) => (
                <li key={r.id} className="rounded-xl border border-line p-3.5">
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-[13px] font-semibold text-ink">{r.title}</p>
                    <Badge tone={r.impact === "high" ? "warning" : "neutral"}>{Math.round(r.confidence * 100)}%</Badge>
                  </div>
                  <p className="mt-1 text-[12px] text-muted">{r.rationale}</p>
                  <p className="mt-1.5 text-[12px] text-faint">Expected outcome: {r.expected_outcome}</p>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="Digital twin" subtitle="A live model of the company">
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2.5 text-[13px]">
            {Object.entries(data.digital_twin)
              .filter(([, v]) => typeof v === "number")
              .slice(0, 12)
              .map(([k, v]) => (
                <div key={k} className="flex items-center justify-between gap-2">
                  <dt className="truncate text-muted">{k.replace(/_/g, " ")}</dt>
                  <dd className="font-semibold text-ink">{v}</dd>
                </div>
              ))}
          </dl>
          <div className="mt-4 flex items-center gap-2 rounded-lg bg-canvas px-3 py-2 text-[12px] text-faint">
            <Network className="h-3.5 w-3.5" />
            {data.digital_twin.employees_active ?? 0} employees · {data.digital_twin.projects_active ?? 0} active projects · graph nodes
          </div>
        </Card>

        <Card title="Trends" subtitle="Weekly metric trajectory">
          {topTrends.length === 0 ? (
            <EmptyState icon={TrendingUp} title="No trends yet" description="Trends accumulate as work happens across the company." />
          ) : (
            <ul className="space-y-2.5">
              {topTrends.map((t) => (
                <li key={t.metric} className="flex items-center justify-between gap-3">
                  <span className="truncate text-[13px] text-muted">{t.metric.replace(/_/g, " ")}</span>
                  <span className="flex shrink-0 items-center gap-1.5 text-[13px]">
                    <span className="font-semibold text-ink">{t.last}</span>
                    <Badge tone={t.direction === "growing" ? "success" : t.direction === "declining" ? "danger" : "neutral"}>
                      {t.direction === "growing" ? "+" : ""}{t.change_percent}%
                    </Badge>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Upcoming meetings" subtitle="Executive calendar">
          {data.executive_calendar.length === 0 ? (
            <EmptyState icon={CalendarClock} title="Nothing scheduled" description="Upcoming meetings will appear here." />
          ) : (
            <ul className="space-y-2.5">
              {data.executive_calendar.slice(0, 8).map((m) => (
                <li key={m.id} className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-[13px] font-medium text-ink">{m.title}</p>
                    <p className="text-[11px] text-faint">
                      {m.start_at ? new Date(m.start_at).toLocaleString() : "not scheduled"} · {m.meeting_type}
                    </p>
                  </div>
                  <Badge tone="neutral">{m.status}</Badge>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Recent decisions" subtitle="Decision registry">
          {data.recent_decisions.length === 0 ? (
            <EmptyState icon={BarChart3} title="No decisions yet" />
          ) : (
            <ul className="space-y-2.5">
              {data.recent_decisions.map((d) => (
                <li key={d.id} className="flex items-center justify-between gap-3">
                  <span className="truncate text-[13px] text-ink">{d.title}</span>
                  <Badge tone="neutral">{d.status}</Badge>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Activity" subtitle="Company timeline">
          {timeline.length === 0 ? (
            <EmptyState icon={Activity} title="No activity yet" />
          ) : (
            <ul className="space-y-2.5">
              {timeline.slice(0, 10).map((e, i) => (
                <li key={i} className="flex items-start justify-between gap-3">
                  <span className="text-[13px] text-muted">{e.title}</span>
                  <span className="shrink-0 text-[11px] text-faint">
                    {e.occurred_at ? new Date(e.occurred_at).toLocaleString() : ""}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      {/* Strategy panel */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Strategy" subtitle="Goals, plan and AI assistant" actions={
          canManage ? <Button size="sm" loading={planBusy} onClick={generatePlan}><Target className="h-3.5 w-3.5" /> Draft plan</Button> : undefined
        }>
          {plan && (
            <div className="mb-4 rounded-xl border border-brand/30 bg-brand-soft/60 p-4">
              <p className="text-[13px] font-semibold text-ink">Quarterly plan — health {plan.company_health}/100 ({plan.status})</p>
              <ul className="mt-2 space-y-1.5">
                {plan.initiatives.map((i) => (
                  <li key={i.title} className="text-[12px] text-muted">
                    <span className="font-semibold text-ink">{i.title}</span> — {i.why}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {goals.length > 0 && (
            <ul className="mb-4 space-y-2.5">
              {goals.map((g) => (
                <li key={g.id} className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-[13px] font-medium text-ink">{g.name}</p>
                    <p className="text-[11px] text-faint">{g.focus} · {g.timeframe} · {g.progress}%</p>
                  </div>
                  <Badge tone={g.status === "completed" ? "success" : g.status === "active" ? "brand" : "neutral"}>{g.status}</Badge>
                </li>
              ))}
            </ul>
          )}
          {canManage && (
            <div className="flex gap-2">
              <div className="min-w-0 flex-1">
                <Input
                  placeholder="New strategic goal…"
                  value={goalName}
                  onChange={(e) => setGoalName(e.target.value)}
                />
              </div>
              <Select
                className="w-32"
                value={goalFocus}
                onChange={(e) => setGoalFocus(e.target.value)}
                options={[
                  { value: "growth", label: "Growth" },
                  { value: "retention", label: "Retention" },
                  { value: "innovation", label: "Innovation" },
                  { value: "efficiency", label: "Efficiency" },
                  { value: "expansion", label: "Expansion" },
                  { value: "learning", label: "Learning" },
                ]}
              />
              <Button size="sm" loading={goalBusy} onClick={createGoal}>Add</Button>
            </div>
          )}
        </Card>

        <div className="space-y-6">
          <Card title="Ask the Executive AI" subtitle="Strategy, health, risks, contributors, meetings">
            <div className="flex gap-2">
              <div className="min-w-0 flex-1">
                <Input
                  placeholder='e.g. "What are the biggest risks right now?"'
                  value={askInput}
                  onChange={(e) => setAskInput(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") ask(); }}
                />
              </div>
              <Button size="sm" loading={askBusy} onClick={ask}><Sparkles className="h-3.5 w-3.5" /> Ask</Button>
            </div>
            {askResult && (
              <div className="mt-3 rounded-xl border border-line bg-canvas/60 p-3.5 text-[13px] text-ink">
                {askResult}
              </div>
            )}
          </Card>

          <Card title="Simulations" subtitle="What-if analysis on live company data">
            <div className="flex flex-wrap gap-2">
              <div className="min-w-[180px] flex-1">
                <Select
                  value={simScenario}
                  onChange={(e) => setSimScenario(e.target.value)}
                  options={Object.entries(SCENARIOS).map(([value, label]) => ({ value, label }))}
                />
              </div>
              <div className="w-20">
                <Input
                  type="number"
                  min={1}
                  value={simCount}
                  onChange={(e) => setSimCount(e.target.value)}
                />
              </div>
              <Button size="sm" variant="secondary" loading={simBusy} onClick={runSim} disabled={!canManage}>
                Run
              </Button>
            </div>
            {simResult && (
              <div className="mt-3 rounded-xl border border-line bg-canvas/60 p-3.5 text-[13px] text-ink">
                {simResult}
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}

function AttentionCard({
  label,
  value,
  tone,
  icon: Icon,
}: {
  label: string;
  value: number;
  tone: "success" | "warning" | "danger" | "brand";
  icon: React.ComponentType<{ className?: string }>;
}) {
  const toneClasses: Record<string, string> = {
    success: "bg-success/10 text-success",
    warning: "bg-warning/10 text-warning",
    danger: "bg-danger/10 text-danger",
    brand: "bg-brand-soft text-brand",
  };
  return (
    <div className="card flex items-start justify-between p-4">
      <div>
        <p className="text-xs font-medium text-faint">{label}</p>
        <p className="mt-1 text-2xl font-semibold tracking-tight text-ink">{value}</p>
      </div>
      <div className={`flex h-9 w-9 items-center justify-center rounded-lg ${toneClasses[tone]}`}>
        <Icon className="h-4 w-4" />
      </div>
    </div>
  );
}
