"use client";

import { useCallback, useEffect, useState } from "react";
import { Activity, AlertTriangle, Clock, Link2, RefreshCw, Repeat2, ShieldCheck } from "lucide-react";

import {
  brainPatternEvidence,
  brainPatternGet,
  brainPatternHistory,
  brainPatternRelated,
  brainPatternSetStatus,
  brainPatternsList,
} from "@/lib/api";
import { roleCan, PERMISSIONS } from "@/lib/permissions";
import { useAuth } from "@/hooks/useAuth";
import type {
  BrainPattern,
  BrainPatternEvidenceItem,
  BrainPatternHistoryResponse,
  PatternLifecycle,
} from "@/types";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";

const FAMILIES = [
  { id: "", label: "All families" },
  { id: "execution", label: "Execution" },
  { id: "decision", label: "Decision" },
  { id: "governance", label: "Governance" },
  { id: "communication", label: "Communication" },
  { id: "knowledge", label: "Knowledge" },
  { id: "organization", label: "Organization" },
] as const;

const LIFECYCLE_TONE: Record<string, "brand" | "success" | "warning" | "danger" | "neutral"> = {
  candidate: "neutral",
  emerging: "brand",
  confirmed: "warning",
  persistent: "danger",
  fading: "neutral",
  resolved: "success",
  acknowledged: "success",
  dismissed: "neutral",
};

function familyBadge(family: string): "brand" | "success" | "warning" | "danger" | "neutral" {
  if (family === "execution") return "danger";
  if (family === "decision") return "warning";
  if (family === "governance") return "brand";
  if (family === "communication") return "success";
  return "neutral";
}

function confidenceTone(confidence: number): "brand" | "success" | "neutral" {
  if (confidence >= 0.6) return "success";
  if (confidence >= 0.4) return "brand";
  return "neutral";
}

type RelatedPattern = BrainPattern & { relation: string };

export function PatternTab() {
  const { user } = useAuth();
  const canManage = roleCan(user?.role, PERMISSIONS.BRAIN_MANAGE);

  const [patterns, setPatterns] = useState<BrainPattern[]>([]);
  const [family, setFamily] = useState("");
  const [selected, setSelected] = useState<BrainPattern | null>(null);
  const [evidence, setEvidence] = useState<BrainPatternEvidenceItem[] | null>(null);
  const [supporting, setSupporting] = useState<BrainPatternEvidenceItem[] | null>(null);
  const [history, setHistory] = useState<BrainPatternHistoryResponse | null>(null);
  const [related, setRelated] = useState<RelatedPattern[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const flash = (message: string) => {
    setNotice(message);
    window.setTimeout(() => setNotice(null), 2500);
  };

  const load = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await brainPatternsList({
        pattern_type: family || undefined,
        status: undefined,
        limit: 100,
      });
      setPatterns(result.patterns);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load patterns");
    } finally {
      setBusy(false);
    }
  }, [family]);

  useEffect(() => {
    void load();
  }, [load]);

  const openPattern = async (pattern: BrainPattern) => {
    setSelected(pattern);
    setEvidence(null);
    setSupporting(null);
    setHistory(null);
    setRelated([]);
    try {
      const [detail, ev, historyRes, rel] = await Promise.all([
        brainPatternGet(pattern.id),
        brainPatternEvidence(pattern.id),
        brainPatternHistory(pattern.id, { limit: 40 }),
        brainPatternRelated(pattern.id, { limit: 10 }),
      ]);
      setSelected(detail);
      setEvidence(ev.evidence);
      setSupporting(
        (ev.supporting_memories ?? []).map((memory) => ({
          type: "memory",
          id: memory.id,
          title: memory.title,
          relationship: `${memory.memory_category ?? "memory"} · ${memory.fact_kind ?? "fact"}`,
        }))
      );
      setHistory(historyRes);
      setRelated(rel.related);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load pattern detail");
    }
  };

  const setStatus = async (pattern: BrainPattern, status: string) => {
    if (!canManage) return;
    setBusy(true);
    setError(null);
    try {
      await brainPatternSetStatus(pattern.id, status);
      flash(`Pattern marked ${status}`);
      await load();
      if (selected && selected.id === pattern.id) {
        setSelected({ ...selected, status: status as PatternLifecycle });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Status update failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        {FAMILIES.map((option) => (
          <button
            key={option.id}
            onClick={() => setFamily(option.id)}
            className={`rounded-full border px-3 py-1 text-xs font-medium ${
              family === option.id
                ? "border-brand bg-brand-soft text-brand"
                : "border-line text-faint hover:bg-surface"
            }`}
          >
            {option.label}
          </button>
        ))}
        <span className="ml-auto flex items-center gap-2">
          <Badge tone="brand">{patterns.length} observable patterns</Badge>
          <Button size="sm" variant="secondary" onClick={load} disabled={busy}>
            <RefreshCw className={`h-3.5 w-3.5 ${busy ? "animate-spin" : ""}`} /> Refresh
          </Button>
        </span>
      </div>

      {notice && <p className="text-[13px] text-success">{notice}</p>}
      {error && <p className="text-[13px] text-danger">{error}</p>}

      <Card
        title="Universal organizational patterns"
        subtitle="Change-driven detection — recurring delays, bottlenecks and gaps, always with evidence. One occurrence is never a pattern."
      >
        {patterns.length === 0 ? (
          <EmptyState
            icon={ShieldCheck}
            title="No patterns yet"
            description="Patterns form automatically as work repeats — block tasks three times in a project and a repeated-delay pattern appears here."
          />
        ) : (
          <div className="divide-y divide-line">
            {patterns.map((pattern) => (
              <button
                key={pattern.id}
                onClick={() => void openPattern(pattern)}
                className="flex w-full items-start justify-between gap-3 px-5 py-3 text-left hover:bg-surface"
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={familyBadge(pattern.family)}>{pattern.family}</Badge>
                    <span className="truncate text-[13px] font-medium text-ink">{pattern.title}</span>
                  </div>
                  {pattern.description && (
                    <p className="mt-1 line-clamp-2 text-xs text-muted">{pattern.description}</p>
                  )}
                  <p className="mt-1 text-[11px] text-faint">
                    {pattern.pattern_type}
                    {pattern.scope_type === "project" ? ` · project-scoped` : " · org-wide"}
                    {pattern.last_seen ? ` · last seen ${new Date(pattern.last_seen).toLocaleString()}` : ""}
                  </p>
                </div>
                <div className="flex shrink-0 flex-col items-end gap-1">
                  <Badge tone={confidenceTone(pattern.confidence)}>
                    {Math.round(pattern.confidence * 100)}% · {pattern.confidence_label}
                  </Badge>
                  <Badge tone={LIFECYCLE_TONE[pattern.status] ?? "neutral"}>
                    {pattern.status} · ×{pattern.occurrence_count}
                  </Badge>
                </div>
              </button>
            ))}
          </div>
        )}
      </Card>

      {selected && (
        <Card
          title={selected.title}
          subtitle={`${selected.pattern_type} · ${selected.family} · lifecycle ${selected.status}`}
        >
          <div className="space-y-4">
            <div className="flex flex-wrap gap-2">
              <Badge tone={LIFECYCLE_TONE[selected.status] ?? "neutral"}>status {selected.status}</Badge>
              <Badge tone="brand">×{selected.occurrence_count} occurrences</Badge>
              <Badge tone={confidenceTone(selected.confidence)}>
                {Math.round(selected.confidence * 100)}% confidence
              </Badge>
              <Badge tone="neutral">trend {selected.trend}</Badge>
              <Badge tone="neutral">window {selected.time_window_days} days</Badge>
              {selected.avg_interval_days !== null && (
                <Badge tone="neutral">every ~{selected.avg_interval_days?.toFixed(1)} days</Badge>
              )}
              {selected.scope_type === "project" && (
                <Badge tone="warning">project-scoped</Badge>
              )}
            </div>

            {selected.description && (
              <p className="text-[13px] leading-relaxed text-muted">{selected.description}</p>
            )}
            {selected.detail && (
              <p className="text-[13px] leading-relaxed text-muted">
                <span className="font-medium text-ink">Detail:</span> {selected.detail}
              </p>
            )}

            <div className="grid gap-4 lg:grid-cols-2">
              <div>
                <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-faint">
                  Why VCOS believes this ({(evidence ?? []).length + (supporting ?? []).length} refs)
                </p>
                {evidence === null ? (
                  <p className="text-xs text-faint">Resolving evidence…</p>
                ) : (evidence?.length ?? 0) === 0 && (supporting?.length ?? 0) === 0 ? (
                  <p className="text-xs text-faint">No resolvable evidence refs.</p>
                ) : (
                  <div className="space-y-1.5">
                    {supporting?.map((item) => (
                      <div key={`m-${item.id}`} className="flex items-center justify-between gap-2 rounded-lg border border-line px-3 py-1.5">
                        <div className="min-w-0">
                          <p className="truncate text-[13px] text-ink">
                            <Badge tone="brand">{item.relationship}</Badge>{" "}
                            {item.title || item.id}
                          </p>
                        </div>
                        <Badge tone="success">memory</Badge>
                      </div>
                    ))}
                    {evidence?.map((item, index) => (
                      <div key={`e-${index}`} className="flex items-center justify-between gap-2 rounded-lg border border-line px-3 py-1.5">
                        <div className="min-w-0">
                          <p className="truncate text-[13px] text-ink">
                            <Badge tone="neutral">{item.relationship}</Badge>{" "}
                            {item.title || `${item.type} ${item.id}`}
                          </p>
                          {item.occurred_at && (
                            <p className="text-[11px] text-faint">
                              event at {new Date(item.occurred_at).toLocaleString()}
                            </p>
                          )}
                        </div>
                        <Badge tone="neutral">{item.type}</Badge>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div>
                <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-faint">
                  Occurrence history ({history?.history.length ?? 0})
                </p>
                {history === null ? (
                  <p className="text-xs text-faint">Loading history…</p>
                ) : (history.history?.length ?? 0) === 0 ? (
                  <p className="text-xs text-faint">No resolvable occurrence events.</p>
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
            </div>

            {related.length > 0 && (
              <div>
                <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-faint">
                  Related patterns ({related.length})
                </p>
                <div className="space-y-1.5">
                  {related.map((pattern) => (
                    <button
                      key={pattern.id}
                      onClick={() => void openPattern(pattern)}
                      className="flex w-full items-center justify-between gap-2 rounded-lg border border-line px-3 py-1.5 text-left hover:bg-surface"
                    >
                      <p className="truncate text-[13px] text-ink">
                        <Link2 className="mr-1 inline h-3 w-3 text-faint" />
                        {pattern.title}
                      </p>
                      <Badge tone="neutral">{pattern.relation}</Badge>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {canManage && (
              <div className="flex flex-wrap items-center gap-2 rounded-lg border border-line p-3">
                <Repeat2 className="h-4 w-4 text-faint" />
                <span className="text-xs font-semibold uppercase tracking-wider text-faint">
                  Manage pattern (brain:manage)
                </span>
                <span className="ml-auto flex gap-2">
                  <Button size="sm" variant="secondary" onClick={() => void setStatus(selected, "acknowledged")} disabled={busy}>
                    Acknowledge
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => void setStatus(selected, "dismissed")} disabled={busy}>
                    Dismiss
                  </Button>
                  {selected.status !== "resolved" && (
                    <Button size="sm" variant="ghost" onClick={() => void setStatus(selected, "resolved")} disabled={busy}>
                      Resolve
                    </Button>
                  )}
                </span>
              </div>
            )}
          </div>
        </Card>
      )}

      <div className="flex items-center gap-2 text-xs text-faint">
        <AlertTriangle className="h-3.5 w-3.5" />
        <span>
          Patterns are evidence-backed and governance-scoped: scoped callers see exactly their scope subtree,
          and hidden patterns are indistinguishable from missing ones.
        </span>
      </div>
      <div className="flex items-center gap-2 text-xs text-faint">
        <Activity className="h-3.5 w-3.5" />
        <span>
          Detection is change-driven — significant events enqueue pattern.evaluate jobs, and the pattern worker
          consolidates occurrences into lifecycle states (candidate → emerging → confirmed → persistent).
        </span>
      </div>
    </div>
  );
}
