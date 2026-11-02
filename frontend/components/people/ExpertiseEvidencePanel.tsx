"use client";

import {
  ChevronDown,
  ChevronUp,
  FileSearch,
  Loader2,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import { useState } from "react";

import {
  getEvidenceItem,
  getPersonEvidence,
  getPersonTrust,
  type EvidenceLine,
  type TrustProfile,
} from "@/lib/api";
import type { ExpertiseScore } from "@/types";
import { Badge } from "@/components/ui/Badge";
import { formatDate } from "@/lib/utils";

const LIFECYCLE_TONE: Record<
  string,
  "neutral" | "warning" | "brand" | "success" | "danger"
> = {
  none: "neutral",
  emerging: "warning",
  observed: "neutral",
  established: "brand",
  strong: "success",
  authoritative: "neutral",
} as const;

function lifecycleTone(lifecycle: string) {
  return LIFECYCLE_TONE[lifecycle] ?? "neutral";
}

export default function ExpertiseEvidencePanel({
  personId,
  skill,
}: {
  personId: string;
  skill: ExpertiseScore;
}) {
  const [open, setOpen] = useState(false);
  const [trust, setTrust] = useState<TrustProfile | null>(null);
  const [evidence, setEvidence] = useState<EvidenceLine[] | null>(null);
  const [detail, setDetail] = useState<EvidenceLine | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function toggle() {
    if (open) {
      setOpen(false);
      return;
    }
    setOpen(true);
    setLoading(true);
    setError(null);
    try {
      const [t, ev] = await Promise.all([
        getPersonTrust(personId, skill.skill_id),
        getPersonEvidence(personId, skill.skill_id),
      ]);
      setTrust(t);
      setEvidence(ev.evidence);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to load trust evidence",
      );
    } finally {
      setLoading(false);
    }
  }

  async function openDetail(item: EvidenceLine) {
    try {
      setDetail(await getEvidenceItem(item.evidence_id));
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to open evidence detail",
      );
    }
  }

  const failed = (trust?.failed_count ?? 0) + (trust?.expired_count ?? 0);

  return (
    <div className="mt-2">
      <button
        type="button"
        onClick={toggle}
        className="flex items-center gap-1.5 text-[12px] font-medium text-brand transition-colors hover:text-brand-strong"
      >
        <ShieldCheck className="h-3.5 w-3.5" />
        Why we trust it
        {open ? (
          <ChevronUp className="h-3.5 w-3.5" />
        ) : (
          <ChevronDown className="h-3.5 w-3.5" />
        )}
      </button>

      {open &&
        (loading ? (
          <div className="mt-2 flex items-center gap-2 text-[12px] text-faint">
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading trust
            profile
          </div>
        ) : error ? (
          <p className="mt-2 text-[12px] text-red-600">{error}</p>
        ) : trust ? (
          <div className="mt-2 space-y-2.5 rounded-xl border border-line bg-canvas/50 p-3">
            <div className="flex flex-wrap items-center gap-1.5">
              <Badge tone={lifecycleTone(trust.lifecycle)}>
                {trust.lifecycle}
              </Badge>
              <Badge tone="neutral">
                {Math.round(trust.confidence * 100)}% confidence
              </Badge>
              <Badge tone="neutral">{trust.freshness}</Badge>
              <Badge tone="neutral">{trust.score}/100</Badge>
            </div>

            <p className="text-[12px] leading-relaxed text-muted">
              {trust.successful_count} successful / {trust.failed_count} failed
              outcome(s) across {trust.distinct_lineages} independent lineage(s)
              from {trust.corroborated_kinds} evidence kind(s) —{" "}
              {trust.evidence_total} evidence item(s),{" "}
              {trust.deduplicated_count} deduplicated.
            </p>

            {failed > 0 && (
              <p className="flex items-center gap-1.5 text-[12px] font-medium text-red-600">
                <XCircle className="h-3.5 w-3.5" />
                {failed} failed or expired item(s) remain visible and count
                against this claim.
              </p>
            )}

            <div className="space-y-1">
              {(evidence ?? []).map((item) => (
                <button
                  key={item.evidence_id}
                  type="button"
                  onClick={() => openDetail(item)}
                  className="flex w-full items-center justify-between gap-2 rounded-lg border border-line/70 bg-elevated px-2.5 py-1.5 text-left transition-colors hover:bg-canvas"
                >
                  <span className="flex min-w-0 items-center gap-2 text-[12px]">
                    <FileSearch className="h-3.5 w-3.5 shrink-0 text-brand" />
                    <span className="truncate text-ink">
                      {item.source_type}:{item.source_id}
                    </span>
                    {item.source_title && (
                      <span className="hidden truncate text-faint sm:inline">
                        {item.source_title}
                      </span>
                    )}
                  </span>
                  <span className="flex shrink-0 items-center gap-1.5">
                    <Badge
                      tone={
                        item.outcome === "failed"
                          ? "danger"
                          : item.outcome === "successful"
                            ? "success"
                            : "neutral"
                      }
                    >
                      {item.outcome}
                    </Badge>
                    <Badge tone="neutral">{item.evidence_kind}</Badge>
                    {item.valid_to && new Date(item.valid_to) < new Date() && (
                      <Badge tone="warning">expired</Badge>
                    )}
                  </span>
                </button>
              ))}
              {(evidence ?? []).length === 0 && (
                <p className="text-[12px] text-faint">
                  No current evidence row remains (expired).
                </p>
              )}
            </div>

            {detail && (
              <div className="rounded-lg border border-line bg-elevated p-2.5 text-[12px] leading-relaxed text-muted">
                <p className="font-semibold text-ink">Evidence detail</p>
                <p className="text-[11px] text-faint">
                  <span className="font-medium text-muted">Detail:</span>{" "}
                  {detail.detail || detail.evidence_type} ·{" "}
                  <span className="font-medium text-muted">lineage:</span>{" "}
                  {detail.lineage_key} ·{" "}
                  <span className="font-medium text-muted">origin:</span>{" "}
                  {detail.origin_event_id || "n/a"} ·{" "}
                  <span className="font-medium text-muted">occurred:</span>{" "}
                  {formatDate(detail.occurred_at)}
                </p>
              </div>
            )}
          </div>
        ) : (
          <p className="mt-2 text-[12px] text-faint">
            Nothing to trust yet — no evidence-derived expertise is visible.
          </p>
        ))}
    </div>
  );
}
