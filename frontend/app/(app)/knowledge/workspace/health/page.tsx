"use client";

import { useCallback, useEffect, useState } from "react";
import { HeartPulse, RefreshCw } from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { KnowledgeWorkspaceNav } from "@/components/knowledge/WorkspaceNav";
import { brainKnowledgeCoverage, brainKnowledgeHealthCenter } from "@/lib/api";
import type {
  KnowledgeCoverageResponse,
  KnowledgeHealthCenterResponse,
} from "@/types";

function barTone(label: string): "success" | "warning" | "danger" {
  return label === "healthy" ? "success" : label === "attention" ? "warning" : "danger";
}

export default function KnowledgeWorkspaceHealthPage() {
  const [health, setHealth] = useState<KnowledgeHealthCenterResponse | null>(null);
  const [coverage, setCoverage] = useState<KnowledgeCoverageResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const [healthResult, coverageResult] = await Promise.all([
        brainKnowledgeHealthCenter(),
        brainKnowledgeCoverage(),
      ]);
      setHealth(healthResult);
      setCoverage(coverageResult);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Health center unavailable");
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const drill = health?.drill_down;

  return (
    <div className="space-y-4">
      <KnowledgeWorkspaceNav />

      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-muted">
          Company knowledge health — a 0-100 score from seven explainable bars, with drill-down
          counts and per-area coverage.
        </p>
        <Button size="sm" onClick={() => void load()} disabled={busy}>
          <RefreshCw className={`h-3.5 w-3.5 ${busy ? "animate-spin" : ""}`} /> Refresh
        </Button>
      </div>

      {error && (
        <Card>
          <p className="text-[13px] text-danger">{error}</p>
        </Card>
      )}

      {busy && !health && (
        <Card>
          <div className="flex items-center justify-center py-10 text-sm text-faint">
            Measuring knowledge health…
          </div>
        </Card>
      )}

      {health && (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,300px)_1fr]">
          <Card title="Health score" bodyClassName="p-0">
            <div className="flex flex-col items-center gap-2 px-5 py-8">
              <div className="flex h-24 w-24 items-center justify-center rounded-full border-4 border-brand text-3xl font-bold text-brand">
                {health.score}
              </div>
              <p className="text-[11px] font-medium uppercase tracking-wide text-faint">/ 100</p>
              <p className="text-center text-xs text-muted">
                Mean of the seven bars below · {health.scope === "org" ? "org-wide" : "scoped"} view
              </p>
              {drill && (
                <div className="mt-3 grid w-full grid-cols-2 gap-2">
                  <Stat label="Contradictions" value={drill.contradictions} />
                  <Stat label="Critical gaps" value={drill.critical_gaps} />
                  <Stat label="Unverified" value={drill.unverified_claims} />
                  <Stat label="Stale" value={drill.stale_knowledge} />
                  <Stat label="Orphan topics" value={drill.orphan_topics} />
                  <Stat label="Total topics" value={drill.total_topics} />
                </div>
              )}
            </div>
          </Card>

          <div className="space-y-4">
            <Card title="The seven bars" subtitle="Every bar explainable — hover any bar for its detail" bodyClassName="p-0">
              {health.bars.length === 0 ? (
                <EmptyState
                  icon={HeartPulse}
                  title="No knowledge yet"
                  description="Bars appear once the company has synthesized knowledge topics."
                />
              ) : (
                <div className="divide-y divide-line">
                  {health.bars.map((bar) => (
                    <div key={bar.name} className="px-5 py-3.5">
                      <div className="flex items-center justify-between gap-3">
                        <p className="text-[13px] font-semibold text-ink">
                          {bar.name.replace(/_/g, " ")}
                        </p>
                        <Badge tone={barTone(bar.label)}>{bar.label}</Badge>
                      </div>
                      <div className="mt-2 h-2 overflow-hidden rounded-full bg-line">
                        <div
                          className="h-full rounded-full bg-brand"
                          style={{ width: `${Math.max(0, Math.min(100, bar.value))}%` }}
                        />
                      </div>
                      <p className="mt-1.5 text-[11px] text-faint">{bar.detail}</p>
                    </div>
                  ))}
                </div>
              )}
            </Card>

            {health.why_weak.length > 0 && (
              <Card title="Why the score is what it is" bodyClassName="p-0">
                <div className="divide-y divide-line">
                  {health.why_weak.map((weak) => (
                    <div key={weak.reason} className="px-5 py-3.5">
                      <p className="text-[13px] font-semibold text-ink">{weak.reason}</p>
                      {weak.details.length > 0 && (
                        <div className="mt-1.5 flex flex-wrap gap-1.5">
                          {weak.details.map((detail, index) => (
                            <Badge key={index} tone="neutral">
                              {JSON.stringify(detail)}
                            </Badge>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </Card>
            )}
          </div>
        </div>
      )}

      {coverage && (
        <Card
          title="Coverage by business area"
          subtitle={`${coverage.total} areas · how much of each area's knowledge is authoritative and fresh`}
          bodyClassName="p-0"
        >
          <div className="grid gap-px border-b border-line bg-line sm:grid-cols-2 lg:grid-cols-3">
            {coverage.areas.map((area) => (
              <div key={area.area} className="bg-surface px-5 py-4">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-[13px] font-semibold capitalize text-ink">{area.area}</p>
                  <Badge tone={area.coverage >= 60 ? "success" : "warning"}>
                    {area.coverage}% covered
                  </Badge>
                </div>
                <div className="mt-2 h-2 overflow-hidden rounded-full bg-line">
                  <div
                    className={`h-full rounded-full ${area.coverage >= 60 ? "bg-success" : "bg-warning"}`}
                    style={{ width: `${Math.max(0, Math.min(100, area.coverage))}%` }}
                  />
                </div>
                <p className="mt-1.5 text-[11px] text-faint">
                  {area.authoritative} authoritative of {area.total_topics} topics
                  {area.stale > 0 ? ` · ${area.stale} stale` : ""}
                </p>
                {area.weak_reasons.length > 0 && (
                  <ul className="mt-2 space-y-0.5">
                    {area.weak_reasons.map((reason) => (
                      <li key={reason} className="text-[11px] text-muted">
                        {reason}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-line bg-surface px-3 py-2">
      <p className="text-lg font-bold text-ink">{value}</p>
      <p className="text-[10px] font-medium uppercase tracking-wide text-faint">{label}</p>
    </div>
  );
}