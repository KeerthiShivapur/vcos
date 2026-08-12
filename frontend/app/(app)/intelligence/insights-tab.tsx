"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Clock,
  Gauge,
  Link2,
  RefreshCw,
  Scale,
} from "lucide-react";

import {
  brainInsightEvidence,
  brainInsightGet,
  brainInsightHistory,
  brainInsightRelated,
  brainInsightsList,
} from "@/lib/api";
import type {
  BrainInsight,
  BrainInsightEvidenceItem,
  BrainInsightHistoryResponse,
} from "@/types";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";

const INSIGHT_TYPES = [
  { id: "", label: "All types" },
  { id: "execution_bottleneck", label: "Execution" },
  { id: "decision_bottleneck", label: "Decision" },
  { id: "governance_bottleneck", label: "Governance" },
  { id: "ownership_ambiguity", label: "Ownership" },
  { id: "knowledge_gap", label: "Knowledge" },
  { id: "communication_breakdown", label: "Communication" },
  { id: "organizational_bottleneck", label: "Organization" },
  { id: "repeated_organizational_issue", label: "Repeated issue" },
  { id: "cross_domain_risk", label: "Cross-domain" },
] as const;

const SEVERITY_TONE: Record<string, "brand" | "success" | "warning" | "danger" | "neutral"> = {
  info: "neutral",
  warning: "warning",
  critical: "danger",
};

const STATUS_TONE: Record<string, "brand" | "success" | "warning" | "danger" | "neutral"> = {
  active: "warning",
  faded: "neutral",
  resolved: "success",
};

function confidenceTone(confidence: number): "brand" | "success" | "neutral" {
  if (confidence >= 0.6) return "success";
  if (confidence >= 0.4) return "brand";
  return "neutral";
}

function componentLabel(key: string): string {
  return key.replace(/_/g, " ");
}

type RelatedInsight = BrainInsight & { relation: string };

export function UniversalInsightsTab() {
  const [insights, setInsights] = useState<BrainInsight[]>([]);
  const [typeFilter, setTypeFilter] = useState("");
  const [selected, setSelected] = useState<BrainInsight | null>(null);
  const [evidence, setEvidence] = useState<BrainInsightEvidenceItem[] | null>(null);
  const [history, setHistory] = useState<BrainInsightHistoryResponse | null>(null);
  const [related, setRelated] = useState<RelatedInsight[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await brainInsightsList({
        insight_type: typeFilter || undefined,
        limit: 100,
      });
      setInsights(result.insights);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load insights");
    } finally {
      setBusy(false);
    }
  }, [typeFilter]);

  useEffect(() => {
    void load();
  }, [load]);

  const openInsight = async (insight: BrainInsight) => {
    setSelected(insight);
    setEvidence(null);
    setHistory(null);
    setRelated([]);
    try {
      const [detail, ev, historyRes, rel] = await Promise.all([
        brainInsightGet(insight.id),
        brainInsightEvidence(insight.id),
        brainInsightHistory(insight.id, { limit: 40 }),
        brainInsightRelated(insight.id, { limit: 10 }),
      ]);
      setSelected(detail);
      setEvidence(ev.evidence);
      setHistory(historyRes);
      setRelated(rel.related);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load insight detail");
    }
  };

  const critical = insights.filter((i) => i.severity === "critical").length;
  const warnings = insights.filter((i) => i.severity === "warning").length;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        {INSIGHT_TYPES.map((option) => (
          <button
            key={option.id}
            onClick={() => setTypeFilter(option.id)}
            className={`rounded-full border px-3 py-1 text-xs font-medium ${
              typeFilter === option.id
                ? "border-brand bg-brand-soft text-brand"
                : "border-line text-faint hover:bg-surface"
            }`}
          >
            {option.label}
          </button>
        ))}
        <span className="ml-auto flex items-center gap-2">
          <Badge tone={critical > 0 ? "danger" : "neutral"}>{critical} critical</Badge>
          <Badge tone={warnings > 0 ? "warning" : "neutral"}>{warnings} warnings</Badge>
          <Badge tone="brand">{insights.length} insights</Badge>
          <Button size="sm" variant="secondary" onClick={load} disabled={busy}>
            <RefreshCw className={`h-3.5 w-3.5 ${busy ? "animate-spin" : ""}`} /> Refresh
          </Button>
        </span>
      </div>

      {error && <p className="text-[13px] text-danger">{error}</p>}

      <Card
        title="Universal company insights"
        subtitle="Composition over patterns, memories, decisions, approvals and dependencies — evidence-backed, governance-scoped, observation only."
      >
        {insights.length === 0 ? (
          <EmptyState
            icon={Gauge}
            title="No insights yet"
            description="Insights form automatically as the organization works — repeated delays, pending decisions, slow approvals and knowledge gaps compose into company-level observations."
          />
        ) : (
          <div className="divide-y divide-line">
            {insights.map((insight) => (
              <button
                key={insight.id}
                onClick={() => void openInsight(insight)}
                className="flex w-full items-start justify-between gap-3 px-5 py-3 text-left hover:bg-surface"
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={SEVERITY_TONE[insight.severity] ?? "neutral"}>{insight.severity}</Badge>
                    <span className="truncate text-[13px] font-medium text-ink">{insight.title}</span>
                  </div>
                  {insight.claim && (
                    <p className="mt-1 line-clamp-2 text-xs text-muted">{insight.claim}</p>
                  )}
                  <p className="mt-1 text-[11px] text-faint">
                    {insight.insight_type}
                    {insight.scope_type === "project" ? " · project-scoped" : " · org-wide"}
                    {insight.last_observed_at
                      ? ` · observed ${new Date(insight.last_observed_at).toLocaleString()}`
                      : ""}
                  </p>
                </div>
                <div className="flex shrink-0 flex-col items-end gap-1">
                  <Badge tone={confidenceTone(insight.confidence)}>
                    {Math.round(insight.confidence * 100)}% confidence
                  </Badge>
                  <Badge tone={STATUS_TONE[insight.status] ?? "neutral"}>{insight.status}</Badge>
                </div>
              </button>
            ))}
          </div>
        )}
      </Card>

      {selected && (
        <Card title={selected.title} subtitle={`${selected.insight_type} · ${selected.domain} · ${selected.status}`}>
          <div className="space-y-4">
            <div className="flex flex-wrap gap-2">
              <Badge tone={SEVERITY_TONE[selected.severity] ?? "neutral"}>{selected.severity}</Badge>
              <Badge tone={confidenceTone(selected.confidence)}>
                {Math.round(selected.confidence * 100)}% confidence
              </Badge>
              <Badge tone="neutral">{selected.status}</Badge>
              {selected.scope_type === "project" && <Badge tone="warning">project-scoped</Badge>}
              {selected.first_observed_at && (
                <Badge tone="neutral">
                  since {new Date(selected.first_observed_at).toLocaleDateString()}
                </Badge>
              )}
            </div>

            {selected.claim && (
              <p className="text-[13px] leading-relaxed text-muted">
                <span className="font-medium text-ink">Claim:</span> {selected.claim}
              </p>
            )}
            {selected.summary && (
              <p className="text-[13px] leading-relaxed text-muted">
                <span className="font-medium text-ink">Summary:</span> {selected.summary}
              </p>
            )}

            <div className="grid gap-4 lg:grid-cols-2">
              <div>
                <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-faint">
                  Confidence — why this score
                </p>
                <div className="space-y-1.5">
                  {Object.entries(selected.confidence_components ?? {})
                    .filter(([key]) => key !== "weights")
                    .map(([key, value]) => (
                      <div key={key} className="flex items-center justify-between gap-2 rounded-lg border border-line px-3 py-1.5">
                        <span className="text-[13px] text-ink">{componentLabel(key)}</span>
                        <Badge tone="brand">{Math.round(Number(value) * 100)}%</Badge>
                      </div>
                    ))}
                </div>
              </div>

              <div>
                <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-faint">
                  Why VCOS believes this ({(evidence ?? []).length} refs)
                </p>
                {evidence === null ? (
                  <p className="text-xs text-faint">Resolving evidence…</p>
                ) : (evidence?.length ?? 0) === 0 ? (
                  <p className="text-xs text-faint">No resolvable evidence refs.</p>
                ) : (
                  <div className="space-y-1.5">
                    {evidence?.map((item, index) => (
                      <div key={`e-${index}`} className="flex items-center justify-between gap-2 rounded-lg border border-line px-3 py-1.5">
                        <div className="min-w-0">
                          <p className="truncate text-[13px] text-ink">
                            <Badge tone="neutral">{item.relationship}</Badge>{" "}
                            {item.title || `${item.type} ${item.id}`}
                          </p>
                          {item.occurred_at && (
                            <p className="text-[11px] text-faint">
                              at {new Date(item.occurred_at).toLocaleString()}
                            </p>
                          )}
                        </div>
                        <Badge tone="neutral">{item.type}</Badge>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              <div>
                <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-faint">
                  Recompose history ({history?.history.length ?? 0})
                </p>
                {history === null ? (
                  <p className="text-xs text-faint">Loading history…</p>
                ) : (history.history?.length ?? 0) === 0 ? (
                  <p className="text-xs text-faint">No feeding events recorded.</p>
                ) : (
                  <div className="space-y-1.5">
                    {history.history.map((item) => (
                      <div key={item.event_id} className="flex items-center justify-between gap-2 rounded-lg border border-line px-3 py-1.5">
                        <p className="truncate text-[13px] text-ink">
                          <Clock className="mr-1 inline h-3 w-3 text-faint" />
                          {item.event_name}
                        </p>
                        <span className="text-[11px] text-faint">
                          {item.occurred_at ? new Date(item.occurred_at).toLocaleString() : "—"}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div>
                <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-faint">
                  Affected entities ({selected.affected_entities?.length ?? 0})
                </p>
                {(selected.affected_entities?.length ?? 0) === 0 ? (
                  <p className="text-xs text-faint">None resolved.</p>
                ) : (
                  <div className="space-y-1.5">
                    {selected.affected_entities?.map((entity) => (
                      <div key={`${entity.type}-${entity.id}`} className="flex items-center justify-between gap-2 rounded-lg border border-line px-3 py-1.5">
                        <p className="truncate text-[13px] text-ink">{entity.title || entity.id}</p>
                        <Badge tone="neutral">{entity.type}</Badge>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {related.length > 0 && (
              <div>
                <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-faint">
                  Related insights ({related.length})
                </p>
                <div className="space-y-1.5">
                  {related.map((insight) => (
                    <button
                      key={insight.id}
                      onClick={() => void openInsight(insight)}
                      className="flex w-full items-center justify-between gap-2 rounded-lg border border-line px-3 py-1.5 text-left hover:bg-surface"
                    >
                      <p className="truncate text-[13px] text-ink">
                        <Link2 className="mr-1 inline h-3 w-3 text-faint" />
                        {insight.title}
                      </p>
                      <Badge tone="neutral">{insight.relation}</Badge>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </Card>
      )}

      <div className="flex items-center gap-2 text-xs text-faint">
        <Scale className="h-3.5 w-3.5" />
        <span>
          Insights are observations, never prescriptions — VCOS states what is happening and why it believes it,
          and never recommends actions or mutates work.
        </span>
      </div>
      <div className="flex items-center gap-2 text-xs text-faint">
        <Activity className="h-3.5 w-3.5" />
        <span>
          Composition is change-driven: pattern, memory, decision and approval events enqueue insight.evaluate
          jobs that recompose bounded neighborhoods into canonical, deduplicated insight rows.
        </span>
      </div>
      <div className="flex items-center gap-2 text-xs text-faint">
        <AlertTriangle className="h-3.5 w-3.5" />
        <span>
          Governance-scoped like patterns: scoped callers see exactly their scope subtree, and hidden insights
          are indistinguishable from missing ones.
        </span>
      </div>
    </div>
  );
}
