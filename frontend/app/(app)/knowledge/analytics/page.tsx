"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle, BarChart3, Eye, FileText, GitMerge, Sparkles, Trophy, Users } from "lucide-react";

import { getKnowledgeAnalytics } from "@/lib/api";
import type { KnowledgeAnalytics } from "@/types";
import { useAuth } from "@/hooks/useAuth";
import { PageHeader, StatCard } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { KIND_LABELS, kindLabel } from "@/components/knowledge/KnowledgeBadge";
import { formatDate } from "@/lib/utils";

const TOTAL_COLORS = ["#6366f1", "#0ea5e9", "#f59e0b", "#10b981", "#8b5cf6", "#ef4444"];

export default function KnowledgeAnalyticsPage() {
  const { organization } = useAuth();
  const [data, setData] = useState<KnowledgeAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      setLoading(true);
      setError(null);
      try {
        setData(await getKnowledgeAnalytics());
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load analytics");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) {
    return (
      <div className="space-y-6">
        <PageHeader title="Knowledge Analytics" description="Quality, coverage and health of the org's memory." />
        <div className="flex justify-center py-24"><Spinner label="Loading analytics" /></div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="space-y-6">
        <PageHeader title="Knowledge Analytics" description="Quality, coverage and health of the org's memory." />
        <ErrorState title="Could not load analytics" message={error ?? "No data"} />
      </div>
    );
  }

  const kinds = Object.keys(data.totals);
  const totalItems = Math.max(1, data.total_items);
  const maxGrowth = Math.max(1, ...data.growth_series.map((g) => g.count));

  return (
    <div className="space-y-6">
      <PageHeader
        title="Knowledge Analytics"
        description={`How healthy is ${organization?.name ?? "the organization"}'s collective memory.`}
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Total items" value={data.total_items} icon={FileText} />
        <StatCard label="Relations" value={data.total_relations} icon={GitMerge} />
        <StatCard label="Avg quality score" value={data.avg_quality_score} icon={Trophy} />
        <StatCard label="Projects covered" value={data.coverage?.projects_with_knowledge ?? 0} icon={Users} />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Knowledge by type" subtitle="Item counts across kinds">
          <div className="space-y-2.5">
            {kinds.map((kind, i) => (
              <div key={kind} className="flex items-center gap-3">
                <span className="w-24 shrink-0 text-[13px] text-muted">{kindLabel(kind)}</span>
                <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-canvas">
                  <div
                    className="h-full rounded-full"
                    style={{ width: `${(data.totals[kind] / totalItems) * 100}%`, backgroundColor: TOTAL_COLORS[i % TOTAL_COLORS.length] }}
                  />
                </div>
                <span className="w-10 shrink-0 text-right text-[13px] font-semibold text-ink">{data.totals[kind]}</span>
              </div>
            ))}
          </div>
        </Card>

        <Card title="30-day growth" subtitle="Items created per day">
          {data.growth_series.length === 0 ? (
            <EmptyState icon={BarChart3} title="No growth data yet" />
          ) : (
            <div className="flex h-40 items-end gap-1">
              {data.growth_series.map((point) => (
                <div key={point.date} className="group relative flex-1">
                  <div
                    className="w-full rounded-t bg-brand/70 transition-colors group-hover:bg-brand"
                    style={{ height: `${Math.max(4, (point.count / maxGrowth) * 100)}%` }}
                  />
                  <div className="pointer-events-none absolute -top-9 left-1/2 hidden -translate-x-1/2 whitespace-nowrap rounded-md bg-ink px-2 py-1 text-[11px] text-white group-hover:block">
                    {point.date}: {point.count}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card title="Top contributors" subtitle="Who writes the org's memory">
          {data.top_contributors.length === 0 ? (
            <EmptyState icon={Users} title="No contributors yet" />
          ) : (
            <div className="space-y-2">
              {data.top_contributors.map((contributor) => (
                <div key={contributor.employee_id} className="flex items-center justify-between rounded-lg border border-line px-3 py-2">
                  <p className="text-[13px] font-medium text-ink">{contributor.name}</p>
                  <Badge tone="brand">{contributor.count} items</Badge>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card title="Most viewed" subtitle="The most popular knowledge">
          {data.top_viewed.length === 0 ? (
            <EmptyState icon={Eye} title="No views yet" />
          ) : (
            <div className="space-y-2">
              {data.top_viewed.map((item) => (
                <Link key={item.id} href={item.url} className="flex items-center justify-between gap-3 rounded-lg border border-line px-3 py-2 transition-colors hover:bg-surface">
                  <span className="flex min-w-0 items-center gap-2">
                    <Eye className="h-3.5 w-3.5 shrink-0 text-faint" />
                    <span className="truncate text-[13px] font-medium text-ink">{item.title}</span>
                  </span>
                  <span className="flex shrink-0 items-center gap-2">
                    <Badge tone="neutral">{kindLabel(item.kind)}</Badge>
                    <span className="text-[12px] text-faint">{item.views}</span>
                  </span>
                </Link>
              ))}
            </div>
          )}
        </Card>

        <Card title="Needs attention" subtitle="Outdated items and review backlog">
          <div className="space-y-2">
            {data.review_backlog.length === 0 && data.outdated.length === 0 ? (
              <EmptyState icon={Sparkles} title="All caught up" description="Nothing is overdue right now." />
            ) : (
              <>
                {data.review_backlog.map((item) => (
                  <Link key={`backlog-${item.id}`} href={item.url} className="flex items-center justify-between gap-2 rounded-lg border border-danger/20 bg-danger/5 px-3 py-2 transition-colors hover:bg-danger/10">
                    <span className="truncate text-[13px] font-medium text-ink">{item.title}</span>
                    <Badge tone="danger">review overdue</Badge>
                  </Link>
                ))}
                {data.outdated.map((item) => (
                  <Link key={`outdated-${item.id}`} href={item.url} className="flex items-center justify-between gap-2 rounded-lg border border-line px-3 py-2 transition-colors hover:bg-surface">
                    <span className="truncate text-[13px] font-medium text-ink">{item.title}</span>
                    <span className="shrink-0 text-[12px] text-faint">{formatDate(item.updated_at)}</span>
                  </Link>
                ))}
              </>
            )}
          </div>
        </Card>

        <Card title="Quality & duplicates" subtitle="AI-scored content quality">
          {data.quality_lowest.length === 0 && data.duplicates.length === 0 ? (
            <EmptyState icon={AlertTriangle} title="No quality issues" description="Run the quality worker to scan items." />
          ) : (
            <div className="space-y-2">
              {data.quality_lowest.map((q) => (
                <div key={q.id} className="flex items-center justify-between rounded-lg border border-line px-3 py-2">
                  <div className="min-w-0">
                    <p className="truncate text-[13px] font-medium text-ink">{q.entity_id}</p>
                    <p className="text-[11px] text-faint">{q.entity_type} · {q.issues.join(", ") || "low score"}</p>
                  </div>
                  <Badge tone={q.score < 40 ? "danger" : "warning"}>{q.score}</Badge>
                </div>
              ))}
              {data.duplicates.map((dup) => (
                <div key={`dup-${dup.entity_id}`} className="flex items-center justify-between rounded-lg border border-warning/20 bg-warning/5 px-3 py-2">
                  <p className="truncate text-[13px] text-ink">{dup.entity_id}</p>
                  <Badge tone="warning">duplicate of {dup.duplicate_of}</Badge>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
