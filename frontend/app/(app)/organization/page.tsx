"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  Building2,
  ChevronDown,
  ChevronRight,
  Network,
  TrendingUp,
  Users,
} from "lucide-react";

import { getOrgChart, getOrgIntelligence } from "@/lib/api";
import type { OrgChartNode, OrgChartResponse, OrgIntelligence } from "@/types";
import { PageHeader, StatCard } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { Avatar } from "@/components/ui/Avatar";
import { formatDate } from "@/lib/utils";

export default function OrganizationPage() {
  return (
    <Suspense fallback={null}>
      <OrgContent />
    </Suspense>
  );
}

function OrgContent() {
  const [chart, setChart] = useState<OrgChartResponse | null>(null);
  const [intelligence, setIntelligence] = useState<OrgIntelligence | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState("");
  const [expandedAll, setExpandedAll] = useState(false);

  useEffect(() => {
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const [chartData, intel] = await Promise.all([getOrgChart(), getOrgIntelligence()]);
        setChart(chartData);
        setIntelligence(intel);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load organization");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const roots = useMemo(() => {
    if (!chart) return [];
    return chart.roots.length ? chart.roots : chart.root ? [chart.root] : [];
  }, [chart]);

  function toggleNode(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function expandAll() {
    if (!chart) return;
    const ids = new Set<string>();
    const walk = (node: OrgChartNode) => {
      if (node.children.length) ids.add(node.id);
      node.children.forEach(walk);
    };
    roots.forEach(walk);
    setExpanded(expandedAll ? new Set() : ids);
    setExpandedAll(!expandedAll);
  }

  function matches(node: OrgChartNode): boolean {
    if (!query.trim()) return true;
    const q = query.trim().toLowerCase();
    return (
      node.name.toLowerCase().includes(q) ||
      (node.designation ?? "").toLowerCase().includes(q) ||
      (node.department ?? "").toLowerCase().includes(q) ||
      (node.team ?? "").toLowerCase().includes(q)
    );
  }

  function hasVisibleChild(node: OrgChartNode): boolean {
    if (matches(node)) return true;
    return node.children.some(hasVisibleChild);
  }

  function renderNode(node: OrgChartNode, depth: number): React.ReactNode {
    const visible = matches(node) || node.children.some(hasVisibleChild);
    if (!visible) return null;
    const isExpanded = expanded.has(node.id);
    const hasChildren = node.children.length > 0;

    return (
      <div key={node.id} className={depth > 0 ? "ml-7" : undefined}>
        <div className="relative flex items-center gap-2.5 rounded-xl border border-line bg-elevated px-3 py-2.5 transition-colors hover:border-brand/40">
          {hasChildren ? (
            <button
              onClick={() => toggleNode(node.id)}
              className="flex h-5 w-5 shrink-0 items-center justify-center rounded-md text-faint hover:bg-canvas hover:text-ink"
              aria-label={isExpanded ? "Collapse" : "Expand"}
            >
              {isExpanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
            </button>
          ) : (
            <span className="h-5 w-5 shrink-0" />
          )}
          <Link href={`/people/${node.id}`} className="flex min-w-0 flex-1 items-center gap-2.5">
            <Avatar name={node.name} src={node.avatar_url} size="sm" />
            <span className="min-w-0">
              <span className="flex items-center gap-2">
                <span className="truncate text-[13px] font-semibold text-ink">{node.name}</span>
                {node.is_online && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-500" />}
              </span>
              <span className="block truncate text-[11px] text-faint">
                {node.designation || "Employee"}
                {node.department ? ` · ${node.department}` : ""}
              </span>
            </span>
          </Link>
          {node.children.length > 0 && (
            <Badge tone="neutral">{node.children.length}</Badge>
          )}
        </div>
        {hasChildren && isExpanded && (
          <div className="mt-1.5 space-y-1.5 border-l border-line pl-4">
            {node.children.map((child) => renderNode(child, depth + 1))}
          </div>
        )}
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <PageHeader title="Organization" breadcrumb="People" />
        <ErrorState title="Could not load organization" message={error} />
      </div>
    );
  }

  if (loading || !intelligence) {
    return (
      <div className="space-y-6">
        <PageHeader title="Organization" breadcrumb="People" />
        <div className="flex justify-center py-24"><Spinner label="Loading organization" /></div>
      </div>
    );
  }

  const dist = (items: { name: string; count: number }[]): { name: string; count: number; pct: number }[] => {
    const total = items.reduce((sum, item) => sum + item.count, 0) || 1;
    return items.map((item) => ({ ...item, pct: Math.round((item.count / total) * 100) }));
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Organization"
        description="The living structure of the company — every relationship, connected."
        actions={
          chart && (chart.root || chart.roots.length) ? (
            <button className="text-[13px] font-medium text-brand hover:underline" onClick={expandAll}>
              {expandedAll ? "Collapse all" : "Expand all"}
            </button>
          ) : undefined
        }
      />

      <div className="grid gap-4 sm:grid-cols-3 lg:grid-cols-6">
        <StatCard label="Employees" value={intelligence.total_employees} icon={Users} hint={`${intelligence.active_employees} active`} />
        <StatCard label="Departments" value={intelligence.departments} icon={Building2} hint={`${intelligence.teams} teams`} />
        <StatCard label="Locations" value={intelligence.locations} icon={Network} hint={`${intelligence.business_units} business units`} />
        <StatCard label="Online now" value={intelligence.online_now} hint={`${intelligence.on_leave} on leave`} />
        <StatCard label="Growth 30d" value={`+${intelligence.growth_30d}`} icon={TrendingUp} hint={`90d: +${intelligence.growth_90d}`} />
        <StatCard label="Org health" value={`${intelligence.org_health}/100`} hint={`Depth ${intelligence.reporting_depth} · Span ${intelligence.management_span}`} />
      </div>

      <div className="grid gap-6 lg:grid-cols-5">
        <Card className="lg:col-span-3" title="Organization chart" subtitle="Reporting hierarchy — expand, collapse, and search.">
          <div className="relative mb-4">
            <Input placeholder="Search by name, role, or team..." value={query} onChange={(e) => setQuery(e.target.value)} />
          </div>
          {roots.length === 0 ? (
            <EmptyState
              icon={Network}
              title="No reporting hierarchy yet"
              description="Assign managers to employees and the chart will take shape automatically."
            />
          ) : (
            <div className="space-y-1.5">
              {roots.map((root) => renderNode(root, 0))}
              <p className="pt-2 text-[11px] text-faint">
                {chart?.total ?? 0} people in the hierarchy · max depth {chart?.max_depth ?? 0}
              </p>
            </div>
          )}
        </Card>

        <div className="space-y-6 lg:col-span-2">
          <Card title="Department distribution">
            {intelligence.department_distribution.length === 0 ? (
              <p className="text-[13px] text-faint">No departments yet.</p>
            ) : (
              <div className="space-y-3">
                {dist(intelligence.department_distribution).map((item) => (
                  <DistributionRow key={item.name} label={item.name} count={item.count} pct={item.pct} />
                ))}
              </div>
            )}
          </Card>

          <Card title="Skill distribution">
            {intelligence.skill_distribution.length === 0 ? (
              <p className="text-[13px] text-faint">No skills tracked yet.</p>
            ) : (
              <div className="space-y-3">
                {dist(intelligence.skill_distribution).map((item) => (
                  <DistributionRow key={item.name} label={item.name} count={item.count} pct={item.pct} />
                ))}
              </div>
            )}
          </Card>

          <Card title="Recent joins">
            {intelligence.recent_joins.length === 0 ? (
              <p className="text-[13px] text-faint">No recent joins.</p>
            ) : (
              <ul className="space-y-2.5">
                {intelligence.recent_joins.map((join) => (
                  <li key={join.employee_id}>
                    <Link href={`/people/${join.employee_id}`} className="flex items-center justify-between rounded-lg p-1.5 transition-colors hover:bg-canvas">
                      <div>
                        <p className="text-[13px] font-medium text-ink">{join.name}</p>
                        <p className="text-[11px] text-faint">{join.designation || "Employee"}</p>
                      </div>
                      <span className="text-[11px] text-faint">{formatDate(join.joining_date)}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}

function DistributionRow({ label, count, pct }: { label: string; count: number; pct: number }) {
  return (
    <div>
      <div className="flex items-center justify-between text-[13px]">
        <span className="truncate font-medium text-ink">{label}</span>
        <span className="text-muted">{count}</span>
      </div>
      <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-canvas">
        <div className="h-full rounded-full bg-brand" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
