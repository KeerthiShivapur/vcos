"use client";

import { AlertTriangle, CircleGauge, Loader2, RefreshCw, SearchCheck } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { PageHeader, StatCard } from "@/components/ui/PageHeader";
import { useAuth } from "@/hooks/useAuth";
import {
  brainOwnershipDryRun,
  getOwnershipSignals,
  getOwnershipSummary,
  resolveOwnershipSignal,
  runOwnershipAnalysis,
  type OwnershipSignalRow,
  type OwnershipSummary,
} from "@/lib/api";
import { PERMISSIONS } from "@/lib/permissions";
import { timeAgo } from "@/lib/utils";

const SIGNAL_KIND_TONE: Record<string, "neutral" | "warning" | "brand" | "success" | "danger"> = {
  gap: "danger",
  mismatch: "warning",
  single_point: "warning",
} as const;

function signalKindLabel(kind: string) {
  switch (kind) {
    case "gap":
      return "Uncovered gap";
    case "mismatch":
      return "Declared vs observed";
    case "single_point":
      return "Single point";
    default:
      return kind;
  }
}

export default function OwnershipPage() {
  const { can } = useAuth();
  const canManage = can(PERMISSIONS.EMPLOYEES_MANAGE);

  const [summary, setSummary] = useState<OwnershipSummary | null>(null);
  const [signals, setSignals] = useState<OwnershipSignalRow[]>([]);
  const [signalsTotal, setSignalsTotal] = useState(0);
  const [dryRun, setDryRun] = useState<{ would_scan: number; note: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async (signal: { silent?: boolean } = {}) => {
    if (!signal.silent) setLoading(true);
    setError(null);
    try {
      const [sum, sig] = await Promise.all([
        getOwnershipSummary(),
        getOwnershipSignals(undefined, "open", 100),
      ]);
      setSummary(sum);
      setSignals(sig.signals);
      setSignalsTotal(sig.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load ownership posture");
    } finally {
      if (!signal.silent) setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function previewDryRun() {
    setError(null);
    try {
      const res = await brainOwnershipDryRun();
      setDryRun({ would_scan: res.would_scan, note: res.note });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to preview analysis");
    }
  }

  async function runAnalysis() {
    setRunning(true);
    setError(null);
    try {
      const res = await runOwnershipAnalysis();
      setDryRun({ would_scan: 0, note: `Batch written: ${res.signals_written} advisory signal(s) — responsibilities never changed.` });
      await refresh({ silent: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to run analysis");
    } finally {
      setRunning(false);
    }
  }

  async function resolve(signalId: string) {
    try {
      await resolveOwnershipSignal(signalId);
      setSignals((prev) => prev.filter((s) => s.id !== signalId));
      setSignalsTotal((t) => Math.max(0, t - 1));
      await refresh({ silent: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to resolve signal");
    }
  }

  if (error && !summary && signals.length === 0 && !loading) {
    return (
      <div className="space-y-6">
        <PageHeader title="Ownership & responsibility" breadcrumb="Brain" description="Who is responsible for what — declared, temporal, evidence-backed. Analysis is advisory only and never changes a responsibility." />
        <ErrorState title="Could not load ownership posture" message={error} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Ownership & responsibility"
        breadcrumb="Brain"
        description="Who is responsible for what — declared, temporal, evidence-backed. Analysis is advisory only and never changes a responsibility."
        actions={
          <Button variant="ghost" size="sm" onClick={previewDryRun}>
            <SearchCheck className="h-4 w-4" /> Preview advisory analysis
          </Button>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Active responsibilities" value={summary?.active_relationships ?? (loading ? "…" : 0)} icon={CircleGauge} />
        <StatCard label="Open signals" value={loading ? "…" : signalsTotal} icon={AlertTriangle} />
        <StatCard label="Gaps" value={summary?.open_signals?.gap ?? 0} icon={AlertTriangle} />
        <StatCard label="Mismatches" value={summary?.open_signals?.mismatch ?? 0} icon={AlertTriangle} />
      </div>

      <Card
        title="Advisory analysis"
        subtitle="Surfaces gaps, single-person dependencies and declared-vs-observed mismatches. Nothing is auto-assigned or changed."
        actions={
          canManage ? (
            <Button size="sm" onClick={runAnalysis} disabled={running}>
              {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
              Run bounded batch
            </Button>
          ) : undefined
        }
      >
        {dryRun ? (
          <p className="text-[12px] text-muted">
            {dryRun.would_scan > 0 ? (
              <>
                Next bounded batch would scan{" "}
                <span className="font-semibold text-ink">{dryRun.would_scan}</span> active
                responsibility window(s). {dryRun.note}
              </>
            ) : (
              dryRun.note
            )}
          </p>
        ) : (
          <p className="text-[12px] text-faint">
            No analysis run in this session. Preview what the next bounded batch would surface, or run it to write
            advisory signals.
          </p>
        )}
      </Card>

      <Card title="Open signals" subtitle={`${signalsTotal} advisory signal(s) awaiting acknowledgement.`}>
        {loading ? (
          <div className="flex items-center gap-2 py-6 text-[12px] text-faint">
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading signals
          </div>
        ) : signals.length === 0 ? (
          <EmptyState
            icon={AlertTriangle}
            title="No open signals"
            description="The ownership posture looks healthy. Signals appear when a gap, single-point dependency or declared-vs-observed mismatch is found."
          />
        ) : (
          <ul className="space-y-2">
            {signals.map((signal) => (
              <li key={signal.id} className="flex items-start justify-between gap-3 rounded-xl border border-line/70 bg-elevated p-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Badge tone={SIGNAL_KIND_TONE[signal.kind] ?? "neutral"}>
                      {signalKindLabel(signal.kind)}
                    </Badge>
                    <Badge tone="neutral">{signal.severity}</Badge>
                    <span className="text-[12px] font-medium text-ink">
                      {signal.object_name} <span className="font-normal text-faint">({signal.object_type})</span>
                    </span>
                  </div>
                  <p className="mt-1 text-[12px] leading-relaxed text-muted">{signal.detail}</p>
                  <p className="mt-1 text-[11px] text-faint">raised {timeAgo(signal.created_at)}</p>
                </div>
                {canManage && (
                  <Button variant="ghost" size="sm" onClick={() => resolve(signal.id)}>
                    Acknowledge
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}