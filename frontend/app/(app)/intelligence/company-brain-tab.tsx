"use client";

import { useState } from "react";
import { Brain, RefreshCw, Send } from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { brainAnswer, brainGraphRelationshipSync } from "@/lib/api";
import { roleCan, PERMISSIONS } from "@/lib/permissions";
import { useAuth } from "@/hooks/useAuth";
import type { BrainAnswer } from "@/types";

export function CompanyBrainTab() {
  const { user } = useAuth();
  const canManage = roleCan(user?.role, PERMISSIONS.INTELLIGENCE_MANAGE);

  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<BrainAnswer | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const ask = async () => {
    if (!question.trim() || busy) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      setAnswer(await brainAnswer({ question: question.trim() }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "The brain could not answer");
    } finally {
      setBusy(false);
    }
  };

  const sync = async () => {
    if (busy) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await brainGraphRelationshipSync({});
      setNotice(`Relationship sync: ${result.synced} edges refreshed (${result.mode})`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Relationship sync failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <Card title="Canonical company brain" subtitle="Evidence-backed answers gated by your governance access">
        <div className="space-y-3">
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void ask();
            }}
            placeholder="Ask the company brain, e.g. What is the status of the Cloud Migration project and its tasks?"
            rows={3}
            className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink outline-none focus:border-brand"
          />
          <div className="flex items-center gap-2">
            <Button onClick={ask} disabled={busy || !question.trim()}>
              {busy ? (
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-line border-t-brand" />
              ) : (
                <Send className="h-4 w-4" />
              )}{" "}
              Ask the brain
            </Button>
            {canManage && (
              <Button variant="secondary" onClick={sync} disabled={busy}>
                <RefreshCw className="h-4 w-4" /> Sync relationships
              </Button>
            )}
            <span className="ml-auto text-xs text-faint">
              Claims are evidence-cited and scoped to your access
            </span>
          </div>
          {notice && <p className="text-[13px] text-success">{notice}</p>}
          {error && <p className="text-[13px] text-danger">{error}</p>}
        </div>
      </Card>

      {answer && (
        <Card title="Answer" subtitle={`${answer.claims.length} claim${answer.claims.length === 1 ? "" : "s"} · ${answer.scope_ids.length} governance scope${answer.scope_ids.length === 1 ? "" : "s"}`} bodyClassName="p-0">
          <div className="divide-y divide-line">
            {answer.claims.length === 0 ? (
              <EmptyState
                icon={Brain}
                title="No evidence within your access"
                description="The brain only answers from company records you are authorized to see."
              />
            ) : (
              answer.claims.map((claim, index) => (
                <div key={`${claim.timestamp}-${index}`} className="px-5 py-4">
                  <div className="flex items-start justify-between gap-3">
                    <p className="text-sm font-semibold text-ink">{claim.claim}</p>
                    <Badge tone="neutral">
                      {(claim.confidence * 100).toFixed(0)}% confidence
                    </Badge>
                  </div>
                  <div className="mt-2 flex flex-wrap items-center gap-1.5">
                    {claim.evidence.map((evidence) => (
                      <a
                        key={`${evidence.type}-${evidence.id}`}
                        href={evidence.url}
                        className="inline-flex items-center gap-1 rounded-full border border-line bg-surface px-2.5 py-0.5 text-[11px] text-muted transition hover:border-brand hover:text-ink"
                      >
                        <span className="font-medium text-brand">{evidence.type}</span>
                        {evidence.title}
                      </a>
                    ))}
                  </div>
                  <p className="mt-1.5 text-[11px] text-faint">
                    {new Date(claim.timestamp).toLocaleString()}
                  </p>
                </div>
              ))
            )}
          </div>
        </Card>
      )}
    </div>
  );
}
