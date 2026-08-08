"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle, BarChart3, CalendarClock, CheckCircle2, FolderKanban, Target } from "lucide-react";

import { getExecutiveDashboard } from "@/lib/api";
import type { ExecutiveDashboard } from "@/types";
import { PageHeader, StatCard } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Badge, statusTone } from "@/components/ui/Badge";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";

export default function AnalyticsPage() {
  return (
    <Suspense fallback={null}>
      <AnalyticsContent />
    </Suspense>
  );
}

function AnalyticsContent() {
  const [data, setData] = useState<ExecutiveDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setData(await getExecutiveDashboard());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load executive analytics");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  if (error) return <ErrorState title="Could not load analytics" message={error} />;
  if (loading || !data) return <div className="flex justify-center py-24"><Spinner label="Loading analytics" /></div>;

  const healthTone = data.project_status === "good" ? "success" : data.project_status === "watch" ? "warning" : "danger";

  return (
    <div className="space-y-6">
      <PageHeader
        title="Executive Analytics"
        description="A pulse on the organization's work execution."
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Active projects" value={data.projects_active} hint={`${data.projects_completed} completed of ${data.projects_total}`} icon={FolderKanban} />
        <StatCard label="Tasks completed" value={`${data.tasks_completion_rate}%`} hint={`${data.tasks_completed} of ${data.tasks_total} · ${data.tasks_blocked} blocked`} icon={CheckCircle2} />
        <StatCard label="Goals complete" value={`${data.goals_completion_rate}%`} hint={`${data.goals_completed} of ${data.goals_total}`} icon={Target} />
        <StatCard label="Meetings (7d)" value={data.meetings_last_7d} hint="Across the organization" icon={CalendarClock} />
      </div>

      <div className={`card p-5 ${healthTone === "danger" ? "border-danger/40" : healthTone === "warning" ? "border-warning/40" : ""}`}>
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-ink">Average project health</p>
            <p className="text-[12px] text-faint">
              {data.avg_project_health}/100 across {data.projects_active} active projects · avg progress {data.avg_progress}%
            </p>
          </div>
          <Badge tone={healthTone}>{data.project_status}</Badge>
        </div>
        <div className="mt-3 h-2.5 overflow-hidden rounded-full bg-canvas">
          <div className={`h-full rounded-full ${healthTone === "danger" ? "bg-danger" : healthTone === "warning" ? "bg-warning" : "bg-success"}`}
            style={{ width: `${Math.max(2, data.avg_project_health)}%` }} />
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="Delivery" subtitle="Task flow health">
          <ul className="space-y-3">
            <MetricRow label="Completion rate" value={`${data.tasks_completion_rate}%`} />
            <MetricRow label="Open tasks" value={data.tasks_total} />
            <MetricRow label="Blocked tasks" value={data.tasks_blocked} />
            <MetricRow label="Avg project progress" value={`${data.avg_progress}%`} />
          </ul>
        </Card>

        <Card title="Risk & capacity" subtitle="What needs attention">
          <ul className="space-y-3">
            <MetricRow label="Open risks" value={data.risks_open} />
            <MetricRow label="High/critical risks" value={data.high_risks} tone={data.high_risks > 0 ? "danger" : "success"} />
            <MetricRow label="Overloaded employees" value={data.overloaded_employees} tone={data.overloaded_employees > 0 ? "warning" : "success"} />
          </ul>
          {(data.high_risks > 0 || data.overloaded_employees > 0) && (
            <div className="mt-4 flex items-start gap-2 rounded-lg border border-warning/30 bg-warning/10 px-3 py-2.5 text-[13px] text-warning">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>Review risks and redistribute work before it compounds.</span>
            </div>
          )}
        </Card>

        <Card title="Quick links" subtitle="Drill into the details">
          <ul className="space-y-2">
            <QuickLink href="/projects" label="All projects" />
            <QuickLink href="/tasks" label="Task engine" />
            <QuickLink href="/goals" label="Goals & key results" />
            <QuickLink href="/calendar" label="Calendar" />
            <QuickLink href="/my-work" label="My work" />
          </ul>
        </Card>
      </div>
    </div>
  );
}

function MetricRow({ label, value, tone }: { label: string; value: string | number; tone?: "success" | "danger" | "warning" }) {
  return (
    <li className="flex items-center justify-between gap-3">
      <span className="text-[13px] text-muted">{label}</span>
      <Badge tone={tone ?? "neutral"}>{value}</Badge>
    </li>
  );
}

function QuickLink({ href, label }: { href: string; label: string }) {
  return (
    <li>
      <Link href={href} className="flex items-center gap-2 rounded-lg border border-line px-3 py-2.5 text-[13px] font-medium text-ink transition-colors hover:border-brand hover:text-brand">
        <BarChart3 className="h-4 w-4 text-faint" />
        {label}
      </Link>
    </li>
  );
}
