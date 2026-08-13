"use client";

import { useEffect, useMemo, useState } from "react";
import { Brain, ExternalLink, Layers, Network, RefreshCw, Send } from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import {
  brainAnswer,
  brainEvidence,
  brainGraphRelationshipSync,
  brainOverview,
} from "@/lib/api";
import { roleCan, PERMISSIONS } from "@/lib/permissions";
import { useAuth } from "@/hooks/useAuth";
import type {
  BrainAnswer,
  BrainAttentionItem,
  BrainEvidenceResponse,
  BrainUnifiedOverview,
} from "@/types";

function confidenceTone(confidence: number): "brand" | "success" | "neutral" | "warning" {
  if (confidence >= 0.7) return "success";
  if (confidence >= 0.4) return "brand";
  return "warning";
}

function sectionLabel(key: string): string {
  return key === "patterns" ? "Patterns" : key === "insights" ? "Insights" : key === "memories" ? "Memory" : "Knowledge";
}

export function CompanyBrainTab() {
  const { user } = useAuth();
  const canManage = roleCan(user?.role, PERMISSIONS.INTELLIGENCE_MANAGE);

  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<BrainAnswer | null>(null);
  const [overview, setOverview] = useState<BrainUnifiedOverview | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [drawer, setDrawer] = useState<BrainEvidenceResponse | null>(null);
  const [drawerError, setDrawerError] = useState<string | null>(null);

  const loadOverview = async () => {
    try {
      setOverview(await brainOverview());
    } catch {
      setOverview(null);
    }
  };

  useEffect(() => {
    void loadOverview();
  }, []);

  const ask = async () => {
    if (!question.trim() || busy) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    setDrawer(null);
    try {
      setAnswer(await brainAnswer({ question: question.trim() }));
      void loadOverview();
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

  const openDrawer = async (sourceType: string, sourceId: string) => {
    setDrawer(null);
    setDrawerError(null);
    try {
      setDrawer(await brainEvidence(sourceType, sourceId, { link_limit: 5 }));
    } catch (err) {
      setDrawerError(err instanceof Error ? err.message : "Evidence drawer unavailable");
    }
  };

  const sections = useMemo(
    () =>
      answer
        ? ([
            { key: "patterns", items: answer.patterns },
            { key: "insights", items: answer.insights },
            { key: "memories", items: answer.memories },
            { key: "knowledge", items: answer.knowledge },
          ] as const)
        : [],
    [answer]
  );

  return (
    <div className="space-y-4">
      <Card
        title="Canonical company brain"
        subtitle="One governed answer composed from every intelligence source — context, knowledge, memory, patterns, insights"
      >
        <div className="space-y-3">
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void ask();
            }}
            placeholder="Ask the company brain, e.g. Why is the Cloud Migration project behind on the approval policy review?"
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
              Governance first, then retrieval · claims are evidence-cited
            </span>
          </div>
          {notice && <p className="text-[13px] text-success">{notice}</p>}
          {error && <p className="text-[13px] text-danger">{error}</p>}
        </div>
      </Card>

      {overview && (
        <Card title="What needs attention" subtitle="Bounded, visibility-filtered intelligence" bodyClassName="p-0">
          {overview.attention.length === 0 ? (
            <EmptyState
              icon={Brain}
              title="Nothing demanding attention"
              description="No insights, patterns or memories require your attention right now."
            />
          ) : (
            <div className="divide-y divide-line">
              {overview.attention.map((item: BrainAttentionItem) => (
                <div key={`${item.source}-${item.id}`} className="flex items-start justify-between gap-3 px-5 py-3">
                  <div>
                    <a href={item.url} className="text-sm font-semibold text-ink hover:text-brand">
                      {item.title}
                    </a>
                    {item.detail && <p className="mt-0.5 text-xs text-muted">{item.detail}</p>}
                  </div>
                  <div className="flex shrink-0 items-center gap-1.5">
                    <Badge tone="neutral">{item.source}</Badge>
                    <Badge tone={confidenceTone(item.confidence)}>{(item.confidence * 100).toFixed(0)}%</Badge>
                  </div>
                </div>
              ))}
            </div>
          )}
          <div className="border-t border-line px-5 py-2.5 text-xs text-faint">
            <span className="font-medium text-muted">Recent intelligence:</span>{" "}
            {overview.recent_intelligence.insights.count} insights ·{" "}
            {overview.recent_intelligence.patterns.count} patterns ·{" "}
            {overview.recent_intelligence.memories.count} memories ·{" "}
            {overview.scope.org_wide ? "org-wide view" : "scoped view"}
          </div>
        </Card>
      )}

      {answer && (
        <>
          <Card
            title="Answer"
            subtitle={
              answer.sources_consulted.length
                ? `Composed from ${answer.sources_consulted.length} sources: ${answer.sources_consulted.join(", ")}`
                : `${answer.claims.length} claim${answer.claims.length === 1 ? "" : "s"}`
            }
            bodyClassName="p-0"
          >
            <div className="border-b border-line px-5 py-4">
              <div className="flex items-start justify-between gap-3">
                <p className="text-[15px] font-semibold leading-snug text-ink">{answer.summary}</p>
                <Badge tone={confidenceTone(answer.confidence)}>
                  {(answer.confidence * 100).toFixed(0)}% confidence
                </Badge>
              </div>
              {answer.related_entities.length > 0 && (
                <div className="mt-3 flex flex-wrap items-center gap-1.5">
                  <span className="text-[11px] uppercase tracking-wide text-faint">Related entities</span>
                  {answer.related_entities.map((entity) => (
                    <button
                      key={`${entity.type}-${entity.id}`}
                      onClick={() => void openDrawer(entity.type, entity.id)}
                      className="inline-flex cursor-pointer items-center gap-1 rounded-full border border-line bg-surface px-2.5 py-0.5 text-[11px] text-muted transition hover:border-brand hover:text-ink"
                    >
                      <span className="font-medium text-brand">{entity.type}</span>
                      {entity.title}
                    </button>
                  ))}
                </div>
              )}
            </div>

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
                      <Badge tone="neutral">{(claim.confidence * 100).toFixed(0)}% confidence</Badge>
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
                    <p className="mt-1.5 text-[11px] text-faint">{new Date(claim.timestamp).toLocaleString()}</p>
                  </div>
                ))
              )}
            </div>

            {sections.some((section) => section.items.length > 0) && (
              <div className="grid gap-px border-t border-line bg-line sm:grid-cols-2">
                {sections.map(
                  (section) =>
                    section.items.length > 0 && (
                      <div key={section.key} className="bg-surface px-5 py-4">
                        <p className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-faint">
                          <Layers className="h-3 w-3" /> {sectionLabel(section.key)}
                        </p>
                        <ul className="space-y-1.5">
                          {section.items.slice(0, 3).map((item) => (
                            <li key={item.id}>
                              <a
                                href={item.url}
                                className="text-[13px] font-medium text-ink hover:text-brand"
                              >
                                {item.title}
                              </a>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )
                )}
              </div>
            )}
          </Card>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card title="Evidence drawer" subtitle="Open a related entity to see why sources are connected" bodyClassName="p-0">
              <div className="divide-y divide-line">
                {!drawer && !drawerError && (
                  <p className="px-5 py-3 text-xs text-faint">
                    Click a related entity chip above, or an evidence link on any claim, to open its cross-source evidence drawer.
                  </p>
                )}
                {drawerError && <p className="px-5 py-3 text-[13px] text-danger">{drawerError}</p>}
                {drawer && (
                  <>
                    <div className="flex items-center justify-between gap-3 px-5 py-3">
                      <div className="flex items-center gap-2">
                        <Badge tone="neutral">{drawer.source.type}</Badge>
                        <span className="text-sm font-semibold text-ink">{drawer.source.title}</span>
                      </div>
                      <a
                        href={drawer.source.url}
                        className="inline-flex items-center gap-1 text-[11px] text-brand hover:underline"
                      >
                        Open source <ExternalLink className="h-3 w-3" />
                      </a>
                    </div>
                    {drawer.evidence.length === 0 ? (
                      <p className="px-5 py-3 text-xs text-faint">No linked intelligence yet — sources connect as signals form.</p>
                    ) : (
                      drawer.evidence.map((item) => (
                        <div key={`${item.type}-${item.id}`} className="flex items-start justify-between gap-3 px-5 py-3">
                          <div>
                            <a href={item.url} className="text-[13px] font-semibold text-ink hover:text-brand">
                              {item.title}
                            </a>
                            <p className="mt-0.5 text-[11px] text-muted">{item.relationship}</p>
                          </div>
                          <Badge tone="neutral">{item.type}</Badge>
                        </div>
                      ))
                    )}
                    {drawer.related_entities.length > 0 && (
                      <div className="border-t border-line px-5 py-2.5">
                        <p className="text-[11px] uppercase tracking-wide text-faint">Graph neighbors</p>
                        <div className="mt-1.5 flex flex-wrap gap-1.5">
                          {drawer.related_entities.map((entity) => (
                            <button
                              key={`${entity.type}-${entity.id}`}
                              onClick={() => void openDrawer(entity.type, entity.id)}
                              className="inline-flex cursor-pointer items-center gap-1 rounded-full border border-line bg-surface px-2.5 py-0.5 text-[11px] text-muted transition hover:border-brand hover:text-ink"
                            >
                              <span className="font-medium text-brand">{entity.type}</span>
                              {entity.title}
                              <span className="text-faint">{entity.relation}</span>
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                  </>
                )}
              </div>
            </Card>

            <Card title="Why this answer reached you" subtitle="Sources are consulted only when relevant — everything governed" bodyClassName="p-0">
              <div className="divide-y divide-line">
                <div className="flex flex-wrap gap-1.5 px-5 py-3">
                  {answer.sources_consulted.map((source) => (
                    <Badge key={source} tone="neutral">
                      {source}
                    </Badge>
                  ))}
                  <span className="ml-auto flex items-center gap-1 text-[11px] text-faint">
                    <Network className="h-3 w-3" />
                    {answer.metrics?.evidence_count ?? 0} evidence refs ·{" "}
                    {answer.metrics?.answer_claim_count ?? answer.claims.length} claims
                  </span>
                </div>
                <p className="px-5 py-3 text-xs leading-relaxed text-muted">
                  {answer.scope.org_wide
                    ? "Your governance access is org-wide, so this answer reflects the whole company's intelligence."
                    : "Your governance access is scoped — evidence beyond your scope never reaches this answer."}
                  {" "}Confidence is the mean of claim confidences; each claim carries its own evidence trail.{" "}
                  {overview?.scope && "The overview and answer above always observe the same governed intelligence."}
                </p>
                <p className="px-5 py-3 text-[11px] text-faint">
                  Answered {new Date(answer.answered_at).toLocaleString()} ·{" "}
                  {answer.metrics?.brain_query_duration_ms ?? 0}ms composed ·{" "}
                  {answer.metrics?.governance_filtered_count ?? 0} sources trimmed by access
                </p>
              </div>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}