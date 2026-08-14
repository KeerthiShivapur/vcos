"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  Eye,
  History,
  Layers,
  RefreshCw,
} from "lucide-react";

import { Badge, statusTone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { KnowledgeWorkspaceNav } from "@/components/knowledge/WorkspaceNav";
import {
  brainKnowledgeChanges,
  brainKnowledgeGaps,
  brainKnowledgeInsightAcknowledge,
  brainKnowledgeInsightGet,
  brainKnowledgeInsights,
  brainKnowledgeInsightResolve,
} from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { roleCan, PERMISSIONS } from "@/lib/permissions";
import {
  authorityLabel,
  confidenceTone,
  kindLabel,
  severityTone,
} from "@/lib/knowledge-utils";
import type {
  KnowledgeChangesResponse,
  KnowledgeGap,
  KnowledgeGapsResponse,
  KnowledgeInsightDetailResponse,
  KnowledgeIntelInsight,
  KnowledgeIntelInsightsResponse,
} from "@/types";

type Section = "changes" | "insights" | "gaps";

export default function KnowledgeWorkspaceChangesPage() {
  const { user } = useAuth();
  const canManage = roleCan(user?.role, PERMISSIONS.BRAIN_MANAGE);

  const [section, setSection] = useState<Section>("changes");

  const [changes, setChanges] = useState<KnowledgeChangesResponse | null>(null);
  const [changesBusy, setChangesBusy] = useState(false);

  const [insights, setInsights] = useState<KnowledgeIntelInsightsResponse | null>(null);
  const [insightsBusy, setInsightsBusy] = useState(false);
  const [kindFilter, setKindFilter] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("");

  const [gaps, setGaps] = useState<KnowledgeGapsResponse | null>(null);
  const [gapsBusy, setGapsBusy] = useState(false);

  const [detail, setDetail] = useState<KnowledgeInsightDetailResponse | null>(null);
  const [detailBusy, setDetailBusy] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [actionBusy, setActionBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const loadChanges = useCallback(async () => {
    setChangesBusy(true);
    try {
      setChanges(await brainKnowledgeChanges({ days: 7 }));
    } catch {
      setChanges(null);
    } finally {
      setChangesBusy(false);
    }
  }, []);

  const loadInsights = useCallback(
    async (kind?: string, status?: string) => {
      setInsightsBusy(true);
      try {
        setInsights(
          await brainKnowledgeInsights({
            ...(kind ? { kind } : {}),
            ...(status ? { status } : {}),
            limit: 60,
          })
        );
      } catch {
        setInsights(null);
      } finally {
        setInsightsBusy(false);
      }
    },
    []
  );

  const loadGaps = useCallback(async () => {
    setGapsBusy(true);
    try {
      setGaps(await brainKnowledgeGaps({ limit: 50 }));
    } catch {
      setGaps(null);
    } finally {
      setGapsBusy(false);
    }
  }, []);

  useEffect(() => {
    if (section === "changes") void loadChanges();
    if (section === "insights") void loadInsights(kindFilter, statusFilter);
    if (section === "gaps") void loadGaps();
  }, [section, kindFilter, statusFilter, loadChanges, loadGaps, loadInsights]);

  const openDetail = useCallback(
    async (insightId: string) => {
      setDetail(null);
      setDetailError(null);
      setDetailBusy(true);
      try {
        setDetail(await brainKnowledgeInsightGet(insightId));
      } catch (err) {
        setDetailError(err instanceof Error ? err.message : "Insight unavailable");
      } finally {
        setDetailBusy(false);
      }
    },
    []
  );

  const act = useCallback(
    async (insightId: string, action: "acknowledge" | "resolve") => {
      if (!canManage || actionBusy) return;
      setActionBusy(insightId);
      setActionError(null);
      try {
        if (action === "acknowledge") {
          await brainKnowledgeInsightAcknowledge(insightId);
        } else {
          await brainKnowledgeInsightResolve(insightId);
        }
        setDetail((current) => (current?.id === insightId ? null : current));
        await loadInsights(kindFilter, statusFilter);
      } catch (err) {
        setActionError(err instanceof Error ? err.message : "Action failed");
      } finally {
        setActionBusy(null);
      }
    },
    [actionBusy, canManage, kindFilter, loadInsights, statusFilter]
  );

  const grouped = useMemo(() => {
    if (!changes) return [];
    return changes.topic_changes.map((topicChange) => {
      const understanding = topicChange.events.filter((e) => e.kind === "understanding");
      const evidence = topicChange.events.filter((e) => e.kind === "new_evidence");
      return { topic: topicChange.topic, families: topicChange.families, understanding, evidence };
    });
  }, [changes]);

  const insightCounts = insights?.by_kind ?? {};

  return (
    <div className="space-y-4">
      <KnowledgeWorkspaceNav />

      <div className="flex flex-wrap gap-1 border-b border-line">
        {([
          { id: "changes", label: "What changed" },
          { id: "insights", label: "Insights" },
          { id: "gaps", label: "Gaps" },
        ] as const).map((tab) => (
          <button
            key={tab.id}
            onClick={() => setSection(tab.id)}
            className={`border-b-2 px-3.5 py-2 text-[13px] font-medium ${
              section === tab.id ? "border-brand text-ink" : "border-transparent text-faint"
            }`}
          >
            {tab.label}
          </button>
        ))}
        <div className="ml-auto flex items-center gap-2 pb-1">
          <Button
            size="sm"
            onClick={() =>
              section === "changes"
                ? void loadChanges()
                : section === "insights"
                  ? void loadInsights(kindFilter, statusFilter)
                  : void loadGaps()
            }
            disabled={changesBusy || insightsBusy || gapsBusy}
          >
            <RefreshCw className="h-3.5 w-3.5" /> Refresh
          </Button>
        </div>
      </div>

      {section === "changes" && (
        <Card
          title={`What changed · last ${changes?.window_days ?? 7} days`}
          subtitle={
            changes
              ? `${changes.total} topic${changes.total === 1 ? "" : "s"} moved · ${changes.scope === "org" ? "org-wide view" : "scoped view"}`
              : "Old understanding -> new understanding, at what time, from which source families"
          }
          bodyClassName="p-0"
        >
          {changesBusy && !changes ? (
            <div className="flex items-center justify-center py-10 text-sm text-faint">
              Digesting recent understanding…
            </div>
          ) : !changes || changes.topic_changes.length === 0 ? (
            <EmptyState
              icon={History}
              title="No changes in this window"
              description="New evidence and superseded understandings will appear here."
            />
          ) : (
            <div className="divide-y divide-line">
              {grouped.map((group) => (
                <div key={group.topic.id} className="px-5 py-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-semibold text-ink">{group.topic.name}</span>
                    <Badge tone="neutral">
                      {group.understanding.length + group.evidence.length} event
                      {group.understanding.length + group.evidence.length === 1 ? "" : "s"}
                    </Badge>
                    {group.families.length > 0 && (
                      <span className="text-[11px] text-faint">
                        families: {group.families.join(", ")}
                      </span>
                    )}
                  </div>
                  {group.understanding.map((event) => (
                    <div key={event.claim_id} className="mt-3 space-y-1.5 border-l border-line pl-3">
                      <p className="text-[11px] text-faint">
                        {new Date(event.at).toLocaleString()} · understanding superseded
                      </p>
                      {event.from && (
                        <p className="text-[13px] text-muted line-through decoration-danger/40">
                          {event.from}
                        </p>
                      )}
                      {event.to && (
                        <p className="flex items-start gap-1.5 text-[13px] text-ink">
                          <ChevronRight className="mt-0.5 h-3 w-3 shrink-0 text-brand" />
                          {event.to}
                        </p>
                      )}
                    </div>
                  ))}
                  {group.evidence.slice(0, 3).map((event) => (
                    <div key={event.claim_id} className="mt-2 flex items-start gap-2 text-[13px] text-muted">
                      <Activity className="mt-0.5 h-3 w-3 shrink-0 text-brand" />
                      <span>
                        New {event.family} evidence: {event.statement}
                        {event.source_title ? ` (${event.source_title})` : ""} —{" "}
                        {new Date(event.at).toLocaleString()}
                      </span>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          )}
        </Card>
      )}

      {section === "insights" && (
        <Card
          title="Universal knowledge insights"
          subtitle="What the company knows means — twelve kinds, exact-once, evidence-lineaged"
          bodyClassName="p-0"
        >
          <div className="flex flex-wrap items-center gap-1.5 border-b border-line px-5 py-2.5">
            <button
              onClick={() => setKindFilter("")}
              className={`inline-flex cursor-pointer items-center gap-1 rounded-full border px-2.5 py-0.5 text-[11px] transition ${
                kindFilter === "" ? "border-brand bg-brand-soft text-ink" : "border-line bg-surface text-muted"
              }`}
            >
              All
            </button>
            {(insights?.kinds ?? []).map((kind) => (
              <button
                key={kind}
                onClick={() => setKindFilter(kindFilter === kind ? "" : kind)}
                className={`inline-flex cursor-pointer items-center gap-1 rounded-full border px-2.5 py-0.5 text-[11px] transition ${
                  kindFilter === kind ? "border-brand bg-brand-soft text-ink" : "border-line bg-surface text-muted"
                }`}
              >
                {kindLabel(kind)} <span className="text-faint">{insightCounts[kind] ?? 0}</span>
              </button>
            ))}
            <div className="ml-auto flex items-center gap-1.5">
              {(["active", "acknowledged", "resolved"] as const).map((status) => (
                <button
                  key={status}
                  onClick={() => setStatusFilter(statusFilter === status ? "" : status)}
                  className={`inline-flex cursor-pointer items-center gap-1 rounded-full border px-2.5 py-0.5 text-[11px] capitalize transition ${
                    statusFilter === status ? "border-brand bg-brand-soft text-ink" : "border-line bg-surface text-muted"
                  }`}
                >
                  {status}
                </button>
              ))}
            </div>
          </div>

          {insightsBusy && !insights ? (
            <div className="flex items-center justify-center py-10 text-sm text-faint">
              Materializing insights…
            </div>
          ) : !insights || insights.insights.length === 0 ? (
            <EmptyState
              icon={Layers}
              title="No insights in this view"
              description="Insights form from contradictions, risks, gaps, impacts and decisions as the company works."
            />
          ) : (
            <div className="divide-y divide-line">
              {insights.insights.map((insight) => (
                <InsightRow
                  key={insight.id}
                  insight={insight}
                  onOpen={openDetail}
                  detailBusy={detailBusy}
                  detailOpen={detail?.id === insight.id}
                />
              ))}
            </div>
          )}
        </Card>
      )}

      {section === "gaps" && (
        <Card
          title={`Knowledge gaps · ${gaps?.total ?? 0}`}
          subtitle="What the company doesn't know it doesn't know — stale, conflicted, undocumented, thin"
          bodyClassName="p-0"
        >
          {gapsBusy && !gaps ? (
            <div className="flex items-center justify-center py-10 text-sm text-faint">
              Scanning for gaps…
            </div>
          ) : !gaps || gaps.gaps.length === 0 ? (
            <EmptyState
              icon={AlertTriangle}
              title="No knowledge gaps"
              description="Every active topic is authoritative, fresh, documented and cross-validated."
            />
          ) : (
            <div className="divide-y divide-line">
              {gaps.gaps.map((gap) => (
                <GapRow key={`${gap.kind}-${gap.topic.id}`} gap={gap} />
              ))}
            </div>
          )}
        </Card>
      )}

      {detail && (
        <Card
          title={detail.title}
          subtitle={`${kindLabel(detail.kind)} · created ${new Date(detail.created_at).toLocaleString()}`}
          actions={
            canManage ? (
              <>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => void act(detail.id, "acknowledge")}
                  disabled={actionBusy === detail.id || detail.status !== "active"}
                >
                  <Eye className="h-3.5 w-3.5" /> Acknowledge
                </Button>
                <Button
                  size="sm"
                  onClick={() => void act(detail.id, "resolve")}
                  disabled={actionBusy === detail.id || detail.status !== "active"}
                >
                  <CheckCircle2 className="h-3.5 w-3.5" /> Resolve
                </Button>
              </>
            ) : undefined
          }
          bodyClassName="p-0"
        >
          {actionError && <p className="px-5 py-2 text-[13px] text-danger">{actionError}</p>}
          <div className="px-5 py-4">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={severityTone(detail.severity)}>{kindLabel(detail.kind)}</Badge>
              <Badge tone={statusTone(detail.status)}>{detail.status}</Badge>
              <Badge tone={confidenceTone(detail.confidence)}>
                {(detail.confidence * 100).toFixed(0)}% confidence
              </Badge>
              {detail.topic_name && <Badge tone="neutral">{detail.topic_name}</Badge>}
              {detail.urgency && <Badge tone="warning">urgency: {detail.urgency}</Badge>}
            </div>
            <p className="mt-3 text-sm leading-relaxed text-ink">{detail.summary}</p>
            {detail.impact && <p className="mt-2 text-[13px] text-muted">{detail.impact}</p>}
          </div>
          {detail.lineage.claims.length > 0 && (
            <div className="border-t border-line px-5 py-4">
              <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-faint">
                Evidence lineage · {detail.lineage.claims.length} claims
              </p>
              <ul className="space-y-2">
                {detail.lineage.claims.map((claim) => (
                  <li key={claim.id} className="text-[13px] text-muted">
                    <span className="font-medium text-ink">{claim.statement}</span>
                    <span className="ml-2 text-[11px] text-faint">
                      {claim.source_type} · {authorityLabel(claim.authority_level)} ·{" "}
                      {new Date(claim.valid_from).toLocaleDateString()}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {detail.audit.length > 0 && (
            <div className="border-t border-line px-5 py-4">
              <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-faint">
                Audit trail · {detail.audit.length} events
              </p>
              <ol className="space-y-1.5">
                {detail.audit.map((event, index) => (
                  <li key={index} className="flex items-start gap-2 text-[12px] text-muted">
                    <Badge tone="neutral" className="shrink-0">
                      {event.action}
                    </Badge>
                    <span className="text-faint">
                      {new Date(event.at).toLocaleString()}
                      {event.note ? ` · “${event.note}”` : ""}
                    </span>
                  </li>
                ))}
              </ol>
            </div>
          )}
        </Card>
      )}

      {detailError && (
        <Card>
          <p className="text-[13px] text-danger">{detailError}</p>
        </Card>
      )}
    </div>
  );
}

function InsightRow({
  insight,
  onOpen,
  detailBusy,
  detailOpen,
}: {
  insight: KnowledgeIntelInsight;
  onOpen: (id: string) => void;
  detailBusy: boolean;
  detailOpen: boolean;
}) {
  return (
    <button
      onClick={() => void onOpen(insight.id)}
      disabled={detailBusy}
      className="flex w-full cursor-pointer items-start justify-between gap-3 px-5 py-3 text-left transition hover:bg-surface"
    >
      <div className="min-w-0">
        <p className="text-[13px] font-semibold text-ink">{insight.title}</p>
        <p className="mt-0.5 text-xs text-muted">{insight.summary}</p>
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
          <Badge tone={severityTone(insight.severity)}>{kindLabel(insight.kind)}</Badge>
          <Badge tone={statusTone(insight.status)}>{insight.status}</Badge>
          {insight.topic_name && <Badge tone="neutral">{insight.topic_name}</Badge>}
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <Badge tone={confidenceTone(insight.confidence)}>
          {(insight.confidence * 100).toFixed(0)}%
        </Badge>
        {insight.evidence_count > 0 && (
          <span className="text-[11px] text-faint">{insight.evidence_count} ev</span>
        )}
        {detailOpen && <ChevronRight className="h-4 w-4 text-brand" />}
      </div>
    </button>
  );
}

function GapRow({ gap }: { gap: KnowledgeGap }) {
  return (
    <div className="px-5 py-3.5">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={severityTone(gap.severity)}>{gap.kind.replace(/_/g, " ")}</Badge>
        <span className="text-[13px] font-semibold text-ink">{gap.topic.name}</span>
        <Badge tone="neutral">{gap.evidence} claims</Badge>
      </div>
      <p className="mt-1.5 text-[13px] leading-relaxed text-muted">{gap.reason}</p>
    </div>
  );
}