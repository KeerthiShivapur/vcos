"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { Gavel, Plus } from "lucide-react";

import { listDecisions } from "@/lib/api";
import { roleCan, PERMISSIONS } from "@/lib/permissions";
import type { Decision } from "@/types";
import { useAuth } from "@/hooks/useAuth";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { KnowledgeBadge } from "@/components/knowledge/KnowledgeBadge";
import { formatDate } from "@/lib/utils";

const STATUSES = ["proposed", "made", "implemented", "reviewed"];

export default function DecisionsPage() {
  return (
    <Suspense fallback={null}>
      <DecisionsContent />
    </Suspense>
  );
}

function DecisionsContent() {
  const { user } = useAuth();
  const canManage = roleCan(user?.role, PERMISSIONS.KNOWLEDGE_MANAGE);
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setDecisions(
        await listDecisions({
          status: status || undefined,
          search: search || undefined,
          limit: 200,
        })
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load decisions");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Decisions"
        description="A record of how and why decisions were made."
        actions={canManage ? (
          <Link href="/decisions/new"><Button size="sm"><Plus className="h-4 w-4" /> New decision</Button></Link>
        ) : undefined}
      />

      <div className="flex flex-wrap gap-2">
        <div className="w-56">
          <Input
            placeholder="Search decisions…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && load()}
          />
        </div>
        <Select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          placeholder="All statuses"
          options={STATUSES.map((s) => ({ value: s, label: s }))}
          className="w-44"
        />
      </div>

      {error ? (
        <ErrorState title="Could not load decisions" message={error} />
      ) : loading ? (
        <div className="flex justify-center py-24"><Spinner label="Loading decisions" /></div>
      ) : decisions.length === 0 ? (
        <EmptyState
          icon={Gavel}
          title="No decisions yet"
          description="Capture decisions so the reasoning is never lost."
          action={canManage ? <Link href="/decisions/new"><Button size="sm"><Plus className="h-4 w-4" /> New decision</Button></Link> : undefined}
        />
      ) : (
        <div className="space-y-2">
          {decisions.map((decision) => {
            const chosen = decision.options?.find((option) => option.chosen);
            return (
              <Link
                key={decision.id}
                href={`/decisions/${decision.id}`}
                className="block rounded-lg border border-line bg-surface p-4 transition hover:border-brand/40 hover:bg-surface-muted"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="truncate text-[15px] font-semibold text-ink">{decision.title}</p>
                      <KnowledgeBadge status={decision.status} kind="decision" />
                    </div>
                    {decision.description && <p className="mt-1 line-clamp-2 text-[13px] text-muted">{decision.description}</p>}
                    {chosen && (
                      <p className="mt-2 rounded-md bg-brand-soft/40 px-2 py-1 text-[12px] text-brand">
                        Chosen: <span className="font-semibold">{chosen.title}</span>
                      </p>
                    )}
                  </div>
                  <div className="shrink-0 text-right text-[12px] text-faint">
                    <p>{formatDate(decision.updated_at)}</p>
                    {decision.decision_maker_name && <p className="mt-1">{decision.decision_maker_name}</p>}
                  </div>
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
