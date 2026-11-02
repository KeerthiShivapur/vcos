"use client";

import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BarChart3,
  CircleDashed,
  HeartPulse,
  Link2,
  Loader2,
  Target,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { StatCard } from "@/components/ui/PageHeader";
import {
  getBusinessBehindTarget,
  getBusinessDrivers,
  getBusinessForecasts,
  getBusinessMetrics,
  getBusinessPerformance,
  getBusinessRecommendations,
  getBusinessTargets,
  type BusinessBehindTargetResponse,
  type BusinessDriverRow,
  type BusinessForecastRow,
  type BusinessMetricsResponse,
  type BusinessPerformanceResponse,
  type BusinessRecommendationsResponse,
  type BusinessTargetRow,
} from "@/lib/api";
import { timeAgo } from "@/lib/utils";

const STATE_TONE: Record<
  string,
  "success" | "warning" | "danger" | "neutral" | "brand"
> = {
  healthy: "success",
  concerned: "warning",
  at_risk: "danger",
} as const;

const TREND_TONE: Record<string, "success" | "danger" | "neutral"> = {
  improving: "success",
  worsening: "danger",
  stable: "neutral",
} as const;

const STATUS_TONE: Record<
  string,
  "success" | "warning" | "danger" | "neutral" | "brand"
> = {
  on_track: "success",
  at_risk: "warning",
  slipped: "danger",
  achieved: "success",
  delivered: "success",
  missed: "danger",
  cancelled: "neutral",
} as const;

export function BusinessPerformanceTab() {
  const [performance, setPerformance] =
    useState<BusinessPerformanceResponse | null>(null);
  const [metrics, setMetrics] = useState<BusinessMetricsResponse | null>(null);
  const [targets, setTargets] = useState<BusinessTargetRow[]>([]);
  const [forecasts, setForecasts] = useState<BusinessForecastRow[]>([]);
  const [drivers, setDrivers] = useState<BusinessDriverRow[]>([]);
  const [behind, setBehind] = useState<BusinessBehindTargetResponse | null>(
    null,
  );
  const [recommendations, setRecommendations] =
    useState<BusinessRecommendationsResponse | null>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const [p, m, t, f, d, b, r] = await Promise.all([
        getBusinessPerformance(),
        getBusinessMetrics(),
        getBusinessTargets(),
        getBusinessForecasts(),
        getBusinessDrivers(),
        getBusinessBehindTarget(),
        getBusinessRecommendations(),
      ]);
      setPerformance(p);
      setMetrics(m);
      setTargets(t.targets);
      setForecasts(f.forecasts);
      setDrivers(d.drivers);
      setBehind(b);
      setRecommendations(r);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to load business performance",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  if (error && !performance && !loading) {
    return (
      <ErrorState title="Could not load business performance" message={error} />
    );
  }

  const atRiskTargets = targets.filter((t) =>
    ["at_risk", "slipped", "missed"].includes(t.status),
  ).length;
  const concerningDims = (performance?.health.dimensions ?? []).filter((d) =>
    ["concerned", "at_risk"].includes(d.state),
  ).length;

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <StatCard
          label="Health score"
          value={loading ? "…" : (performance?.health.score ?? "—")}
          icon={HeartPulse}
        />
        <StatCard
          label="Metrics tracked"
          value={loading ? "…" : (metrics?.total ?? 0)}
          icon={Activity}
        />
        <StatCard
          label="Targets at risk"
          value={loading ? "…" : atRiskTargets}
          icon={AlertTriangle}
        />
        <StatCard
          label="Dimensions concerned"
          value={loading ? "…" : concerningDims}
          icon={Target}
        />
        <StatCard
          label="Active drivers"
          value={loading ? "…" : drivers.length}
          icon={Link2}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card
            title={`Performance health · ${performance?.scope ?? "org_wide"} · ${performance?.health.score ?? 0}/100`}
            subtitle="One explainable state per dimension — every score carries the evidence that produced it."
          >
            {loading ? (
              <div className="flex items-center gap-2 py-6 text-[12px] text-faint">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading
                performance health
              </div>
            ) : (performance?.health.dimensions ?? []).length === 0 ? (
              <EmptyState
                icon={BarChart3}
                title="No performance evidence yet"
                description="Define business metrics and record outcomes — the health assessment builds itself from the real event stream."
              />
            ) : (
              <ul className="space-y-3">
                {(performance?.health.dimensions ?? []).map((dim) => (
                  <li
                    key={dim.key}
                    className="rounded-lg border border-line/70 bg-elevated p-3"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone="brand">{dim.label}</Badge>
                      <Badge tone={STATE_TONE[dim.state] ?? "neutral"}>
                        {dim.state}
                      </Badge>
                      <span className="text-[12px] font-semibold text-ink">
                        {dim.score}/100
                      </span>
                      <span className="ml-auto text-[11px] text-faint">
                        {dim.metrics_count} metric(s) · {dim.evidence_count}{" "}
                        evidence
                        {dim.updated_at ? ` · ${timeAgo(dim.updated_at)}` : ""}
                      </span>
                    </div>
                    {dim.reasons.length > 0 && (
                      <p className="mt-2 flex flex-wrap items-center gap-1.5">
                        {dim.reasons.map((reason) => (
                          <Badge key={reason} tone="warning">
                            {reason}
                          </Badge>
                        ))}
                      </p>
                    )}
                    {dim.positives.length > 0 && (
                      <p className="mt-1.5 flex flex-wrap items-center gap-1.5">
                        {dim.positives.map((positive) => (
                          <Badge key={positive} tone="success">
                            {positive}
                          </Badge>
                        ))}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card
            title={`Metric trajectories · ${performance?.metrics.total ?? 0}`}
            subtitle="Direction-aware: each metric's current vs previous value and its trend toward the committed target."
          >
            {loading ? (
              <div className="flex items-center gap-2 py-6 text-[12px] text-faint">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading
                trajectories
              </div>
            ) : (performance?.metrics.trajectories ?? []).length === 0 ? (
              <EmptyState
                icon={TrendingUp}
                title="No metric trajectories"
                description="Recorded outcomes produce the trajectory ledger here."
              />
            ) : (
              <ul className="space-y-2">
                {(performance?.metrics.trajectories ?? []).map((row) => (
                  <li
                    key={row.metric_id}
                    className="rounded-lg border border-line/70 bg-elevated p-3"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-[13px] font-medium text-ink">
                        {row.label}
                      </p>
                      <Badge tone="neutral">{row.kind}</Badge>
                      <Badge tone={TREND_TONE[row.trend] ?? "neutral"}>
                        {row.trend}
                      </Badge>
                      <span className="ml-auto text-[12px] font-semibold text-ink">
                        {row.current ?? "—"}
                        {row.unit ? ` ${row.unit}` : ""}
                      </span>
                    </div>
                    <p className="mt-1 text-[11px] text-faint">
                      previous {row.previous ?? "—"}
                      {row.delta != null && (
                        <>
                          {" "}
                          · delta {row.delta > 0 ? "+" : ""}
                          {row.delta}
                          {row.pct_change != null && (
                            <>
                              {" "}
                              ({row.pct_change > 0 ? "+" : ""}
                              {row.pct_change}%)
                            </>
                          )}
                        </>
                      )}
                      {row.observed_count > 0 &&
                        ` · ${row.observed_count} observation(s)`}
                      {row.last_observed_at &&
                        ` · ${timeAgo(row.last_observed_at)}`}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card
            title={
              behind
                ? `Why are we behind target · ${behind.target?.metric_label ?? ""}`
                : "Why are we behind target"
            }
            subtitle="The flagship chain: target → gap → drivers → strategy → projects → capacity → decisions → what to do."
          >
            {loading ? (
              <div className="flex items-center gap-2 py-6 text-[12px] text-faint">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Walking the
                chain
              </div>
            ) : !behind ? (
              <EmptyState
                icon={Target}
                title="No committed target yet"
                description="Commit a business target with a deadline — the engine walks the chain from the gap."
              />
            ) : (
              <div className="space-y-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge
                    tone={STATUS_TONE[behind.target?.status ?? ""] ?? "neutral"}
                  >
                    {behind.target?.status ?? "—"}
                  </Badge>
                  <span className="text-[12px] text-muted">
                    target {behind.target?.target_value ?? "—"}
                    {behind.target?.unit ? ` ${behind.target.unit}` : ""} ·
                    current {behind.target?.current ?? "—"}
                    {behind.target?.gap != null && (
                      <span className="text-danger">
                        {" "}
                        · gap {behind.target.gap}
                      </span>
                    )}
                  </span>
                  <span className="ml-auto text-[11px] text-faint">
                    due {behind.target?.end_at ?? "—"}
                  </span>
                </div>
                {(behind.drivers ?? []).length > 0 && (
                  <div className="flex flex-wrap items-center gap-1.5">
                    {(behind.drivers ?? []).map((driver) => (
                      <Badge key={driver.driver_key} tone="brand">
                        {driver.title} · {driver.kind.replace(/_/g, " ")}
                      </Badge>
                    ))}
                  </div>
                )}
                {(behind.what_to_do ?? []).length > 0 && (
                  <div className="space-y-1.5">
                    <p className="text-[12px] font-semibold text-ink">
                      What to do
                    </p>
                    <ul className="space-y-1.5">
                      {(behind.what_to_do ?? []).map((item, idx) => (
                        <li
                          key={idx}
                          className="rounded-lg border border-line/70 bg-surface px-3 py-2"
                        >
                          <div className="flex flex-wrap items-center gap-1.5">
                            <Badge tone="neutral">{item.kind}</Badge>
                            <p className="text-[12px] font-medium text-ink">
                              {item.action}
                            </p>
                          </div>
                          {item.rationale && (
                            <p className="mt-0.5 text-[11px] text-faint">
                              {item.rationale}
                            </p>
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </Card>
        </div>

        <div className="space-y-6">
          <Card
            title={`Recommendations · ${recommendations?.total ?? 0}`}
            subtitle="What leadership should do next — advisory only, every item carries its evidence."
          >
            {loading ? (
              <div className="flex items-center gap-2 py-6 text-[12px] text-faint">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Deriving
                recommendations
              </div>
            ) : (recommendations?.recommendations ?? []).length === 0 ? (
              <EmptyState
                icon={CircleDashed}
                title="Nothing to recommend"
                description="Recommendations derive deterministically from at-risk or concerned dimensions and targets."
              />
            ) : (
              <ul className="space-y-2">
                {(recommendations?.recommendations ?? []).map((row, idx) => (
                  <li
                    key={idx}
                    className="rounded-lg border border-line/70 bg-elevated p-3"
                  >
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Badge tone="brand">{row.kind}</Badge>
                      <p className="text-[12px] font-medium text-ink">
                        {row.title}
                      </p>
                    </div>
                    {row.why && (
                      <p className="mt-0.5 text-[11px] text-faint">{row.why}</p>
                    )}
                    {row.evidence_count > 0 && (
                      <p className="mt-0.5 text-[11px] text-muted">
                        {row.evidence_count} evidence item(s)
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card
            title={`Targets · ${targets.length}`}
            subtitle="Committed targets with deterministic status and the gap to attainment."
          >
            {loading ? (
              <div className="flex items-center gap-2 py-6 text-[12px] text-faint">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading targets
              </div>
            ) : targets.length === 0 ? (
              <EmptyState
                icon={Target}
                title="No committed targets"
                description="Commit a target against a metric — status derives from real observations."
              />
            ) : (
              <ul className="space-y-2">
                {targets.map((row) => (
                  <li
                    key={row.target_id}
                    className="rounded-lg border border-line/70 bg-elevated p-3"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone={STATUS_TONE[row.status] ?? "neutral"}>
                        {row.status}
                      </Badge>
                      <p className="text-[12px] font-medium text-ink">
                        {row.metric_label}
                      </p>
                    </div>
                    <p className="mt-1 text-[11px] text-faint">
                      {row.period_label || "current period"} · target{" "}
                      {row.target_value}
                      {row.unit ? ` ${row.unit}` : ""} · current{" "}
                      {row.current ?? "—"}
                      {row.gap != null && (
                        <span
                          className={
                            row.gap > 0 ? "text-danger" : "text-success"
                          }
                        >
                          {" "}
                          · gap {row.gap}
                        </span>
                      )}
                      {" · "}
                      {timeAgo(row.end_at)}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card
            title={`Forecasts · ${forecasts.length}`}
            subtitle="Projected arcs only — labeled as projected, never observed fact."
          >
            {loading ? (
              <div className="flex items-center gap-2 py-6 text-[12px] text-faint">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading
                forecasts
              </div>
            ) : forecasts.length === 0 ? (
              <EmptyState
                icon={TrendingDown}
                title="No forecasts yet"
                description="Committed forecast arcs appear here, always labeled as projected."
              />
            ) : (
              <ul className="space-y-2">
                {forecasts.map((row) => (
                  <li
                    key={row.forecast_id}
                    className="rounded-lg border border-line/70 bg-elevated p-3"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone="brand">{row.forecast_type}</Badge>
                      <p className="text-[12px] font-medium text-ink">
                        {row.metric_label}
                      </p>
                      <Badge tone="neutral">projected</Badge>
                    </div>
                    <p className="mt-1 text-[11px] text-faint">
                      {row.low ?? "—"} → {row.midpoint ?? "—"} →{" "}
                      {row.high ?? "—"}
                      {row.confidence != null &&
                        ` · ${Math.round(row.confidence * 100)}% confidence`}
                      {row.horizon_label ? ` · ${row.horizon_label}` : ""}
                    </p>
                    {row.basis && (
                      <p className="mt-0.5 text-[11px] text-muted">
                        {row.basis}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card
            title={`Drivers · ${drivers.length}`}
            subtitle="What moves performance — with the deterministic link language to the metrics they drive."
          >
            {loading ? (
              <div className="flex items-center gap-2 py-6 text-[12px] text-faint">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading drivers
              </div>
            ) : drivers.length === 0 ? (
              <EmptyState
                icon={Link2}
                title="No drivers detected"
                description="Drivers link conservative cross-slice evidence to the metrics they move."
              />
            ) : (
              <ul className="space-y-2">
                {drivers.map((row) => (
                  <li
                    key={row.driver_key}
                    className="rounded-lg border border-line/70 bg-elevated p-3"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-[12px] font-medium text-ink">
                        {row.title}
                      </p>
                      <Badge tone={STATE_TONE[row.strength] ?? "neutral"}>
                        {row.strength}
                      </Badge>
                    </div>
                    <p className="mt-1 flex flex-wrap items-center gap-1 text-[11px] text-faint">
                      {row.metric_keys.map((key) => (
                        <span
                          key={key}
                          className="rounded bg-surface px-1.5 py-0.5"
                        >
                          {key}
                        </span>
                      ))}
                      <span className="text-muted">{row.kind_label}</span>
                    </p>
                    {row.relation_summary && (
                      <p className="mt-0.5 text-[11px] text-muted">
                        {row.relation_summary}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card
            title="Advisory only"
            subtitle="The assessment never rewrites the business."
          >
            <div className="flex items-center gap-2 text-[12px] text-muted">
              <CircleDashed className="h-3.5 w-3.5 shrink-0 text-faint" />
              Every score explains itself; people own targets, forecasts and
              decisions.
            </div>
          </Card>
        </div>
      </div>

      {error && (
        <p className="rounded-lg border border-danger/30 bg-danger/10 p-2 text-[11px] text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
