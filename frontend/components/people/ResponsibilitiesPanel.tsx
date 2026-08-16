"use client";

import { ChevronDown, ChevronUp, ClipboardCheck, Loader2, ShieldAlert } from "lucide-react";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { getPersonResponsibilities, type OwnershipRelationshipRow, type PersonResponsibilitiesResponse } from "@/lib/api";
import { formatDate } from "@/lib/utils";

const RESPONSIBILITY_TONES: Record<string, "neutral" | "warning" | "brand" | "success" | "danger"> = {
  primary: "brand",
  operational: "neutral",
  technical: "neutral",
  business: "warning",
  knowledge: "neutral",
  decision: "success",
  customer: "neutral",
  backup: "neutral",
  delegated: "warning",
} as const;

function responsibilityTone(type: string) {
  return RESPONSIBILITY_TONES[type] ?? "neutral";
}

export function ResponsibilitiesCard({
  personId,
  personName,
}: {
  personId: string;
  personName?: string;
}) {
  const [data, setData] = useState<PersonResponsibilitiesResponse | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    getPersonResponsibilities(personId)
      .then((res) => {
        if (active) setData(res);
      })
      .catch((err) => {
        if (active) setError(err instanceof Error ? err.message : "Unable to load responsibilities");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [personId]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-4 text-[12px] text-faint">
        <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading responsibilities
      </div>
    );
  }

  if (error) {
    return <p className="py-2 text-[12px] text-red-600">{error}</p>;
  }

  if (!data) return null;

  return (
    <div className="space-y-3">
      {data.active.length === 0 ? (
        <p className="text-[12px] text-faint">
          Nothing is declared for {personName ?? "this person"} yet. Responsibilities are never assumed —
          the engine only surfaces what was explicitly declared or observed.
        </p>
      ) : (
        <ul className="space-y-2">
          {data.active.map((row) => (
            <li key={row.id} className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <ClipboardCheck className="h-3.5 w-3.5 shrink-0 text-brand" />
                  <p className="truncate text-[13px] font-medium text-ink">{row.object_name}</p>
                </div>
                <p className="mt-0.5 text-[11px] text-faint">
                  {row.object_type} · since {formatDate(row.declared_start)}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-1.5">
                <Badge tone={responsibilityTone(row.responsibility_type)}>{row.responsibility_type}</Badge>
                {row.backup_owner_id && (
                  <Badge tone="neutral">{row.backup_owner_label ?? "backed up"}</Badge>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      {data.backup_roles > 0 && (
        <p className="flex items-center gap-1.5 text-[12px] text-muted">
          <ShieldAlert className="h-3.5 w-3.5 text-amber-500" />
          Backup owner for {data.backup_roles} active responsibility
          {data.backup_roles === 1 ? "" : "ies"}.
        </p>
      )}

      {data.history.length > 0 && (
        <div className="border-t border-line/70 pt-2">
          <button
            type="button"
            onClick={() => setShowHistory((v) => !v)}
            className="flex items-center gap-1.5 text-[12px] font-medium text-brand transition-colors hover:text-brand-strong"
          >
            {showHistory ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
            Past responsibilities ({data.history.length})
          </button>
          {showHistory && (
            <ul className="mt-2 space-y-1.5">
              {data.history.map((row: OwnershipRelationshipRow) => (
                <li key={row.id} className="flex items-center justify-between gap-3 text-[12px]">
                  <span className="truncate text-muted">
                    {row.object_name}
                    <span className="text-faint"> · {row.object_type}</span>
                  </span>
                  <span className="shrink-0 text-[11px] text-faint">
                    {formatDate(row.declared_start)} →{" "}
                    {row.declared_end ? formatDate(row.declared_end) : "now"}
                    {row.closed_reason ? ` (${row.closed_reason})` : ""}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}