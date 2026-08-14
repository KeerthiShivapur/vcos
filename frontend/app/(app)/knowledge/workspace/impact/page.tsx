"use client";

import { useCallback, useState } from "react";
import {
  GitBranch,
  MapPin,
  Network,
  RefreshCw,
  Search,
  UserCircle2,
} from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { KnowledgeWorkspaceNav } from "@/components/knowledge/WorkspaceNav";
import {
  brainKnowledgeDiscover,
  brainKnowledgeTopicEvolution,
  brainKnowledgeTopicImpact,
  brainKnowledgeTopicOwnership,
  brainKnowledgeTopicPropagation,
} from "@/lib/api";
import {
  authorityLabel,
  confidenceTone,
} from "@/lib/knowledge-utils";
import type {
  KnowledgeDiscoveryAnswer,
  KnowledgeEvolutionResponse,
  KnowledgeImpactResponse,
  KnowledgeOwnershipResponse,
  KnowledgePropagationResponse,
} from "@/types";

interface TopicExplorer {
  topic: string;
  ownership: KnowledgeOwnershipResponse | null;
  propagation: KnowledgePropagationResponse | null;
  impact: KnowledgeImpactResponse | null;
  evolution: KnowledgeEvolutionResponse | null;
  busy: boolean;
  error: string | null;
}

export default function KnowledgeWorkspaceImpactPage() {
  const [query, setQuery] = useState("");
  const [matches, setMatches] = useState<KnowledgeDiscoveryAnswer[] | null>(null);
  const [searchBusy, setSearchBusy] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [explorer, setExplorer] = useState<TopicExplorer | null>(null);

  const searchTopics = useCallback(async () => {
    const text = query.trim();
    if (!text || searchBusy) return;
    setSearchBusy(true);
    setSearchError(null);
    try {
      const result = await brainKnowledgeDiscover({ query: text, limit: 8 });
      setMatches((result.answers ?? []) as KnowledgeDiscoveryAnswer[]);
    } catch (err) {
      setSearchError(err instanceof Error ? err.message : "Discovery failed");
      setMatches(null);
    } finally {
      setSearchBusy(false);
    }
  }, [query, searchBusy]);

  const openTopic = useCallback(
    async (topicName: string) => {
      setExplorer((current) => (current ? { ...current, topic: topicName } : { topic: topicName, ownership: null, propagation: null, impact: null, evolution: null, busy: true, error: null }));
      setMatches(null);
      setQuery(topicName);
      try {
        const [ownership, propagation, impact, evolution] = await Promise.all([
          brainKnowledgeTopicOwnership(topicName).catch(() => null),
          brainKnowledgeTopicPropagation(topicName, 3).catch(() => null),
          brainKnowledgeTopicImpact(topicName).catch(() => null),
          brainKnowledgeTopicEvolution(topicName).catch(() => null),
        ]);
        setExplorer({
          topic: topicName,
          ownership,
          propagation,
          impact,
          evolution,
          busy: false,
          error: null,
        });
      } catch (err) {
        setExplorer((current) =>
          current
            ? { ...current, busy: false, error: err instanceof Error ? err.message : "Topic analysis failed" }
            : null
        );
      }
    },
    []
  );

  return (
    <div className="space-y-4">
      <KnowledgeWorkspaceNav />

      <Card
        title="Impact analysis"
        subtitle="Pick a knowledge topic — see who owns it, what a change would reach, and how the understanding evolved"
      >
        <div className="flex flex-wrap items-center gap-2">
          <input
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setMatches(null);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") void searchTopics();
            }}
            placeholder="Search the company's knowledge topics, e.g. pricing"
            className="w-full max-w-md rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink outline-none focus:border-brand"
          />
          <Button onClick={() => void searchTopics()} disabled={searchBusy || !query.trim()}>
            {searchBusy ? (
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-line border-t-brand" />
            ) : (
              <Search className="h-4 w-4" />
            )}{" "}
            Find topic
          </Button>
          {explorer && (
            <Button
              variant="secondary"
              onClick={() => void openTopic(explorer.topic)}
              disabled={explorer.busy}
            >
              <RefreshCw className={`h-3.5 w-3.5 ${explorer.busy ? "animate-spin" : ""}`} /> Re-analyze
            </Button>
          )}
        </div>
        {searchError && <p className="mt-2 text-[13px] text-danger">{searchError}</p>}
        {matches && (
          <div className="mt-3">
            {matches.length === 0 ? (
              <p className="text-[13px] text-faint">No knowledge topics match this search.</p>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {matches.map((match) => (
                  <button
                    key={match.topic.id}
                    onClick={() => void openTopic(match.topic.name)}
                    className="inline-flex cursor-pointer items-center gap-1 rounded-full border border-line bg-surface px-3 py-1 text-[12px] text-muted transition hover:border-brand hover:text-ink"
                  >
                    <MapPin className="h-3 w-3 text-brand" />
                    {match.topic.name}
                    {match.confidence !== null && match.confidence !== undefined && (
                      <Badge tone={confidenceTone(match.confidence)}>
                        {(match.confidence * 100).toFixed(0)}%
                      </Badge>
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </Card>

      {!explorer && (
        <EmptyState
          icon={Network}
          title="No topic selected"
          description="Search for a topic above — for example “pricing” or “migration” — and open it to trace its impact."
        />
      )}

      {explorer && explorer.busy && (
        <Card>
          <div className="flex items-center justify-center py-10 text-sm text-faint">
            Tracing “{explorer.topic}” through the knowledge graph…
          </div>
        </Card>
      )}

      {explorer && !explorer.busy && (
        <div className="grid gap-4 lg:grid-cols-2">
          {(() => {
            const ownership = explorer.ownership;
            const propagation = explorer.propagation;
            const impact = explorer.impact;
            const evolution = explorer.evolution;
            return (
              <>
          {ownership && (
            <Card title="Ownership" subtitle="Who stands behind this knowledge" bodyClassName="p-0">
              <div className="space-y-3 px-5 py-4">
                <div className="flex items-center gap-2">
                  <UserCircle2 className="h-5 w-5 text-brand" />
                  <span className="text-sm font-semibold text-ink">
                    {ownership.owner.resolved
                      ? `Employee ${ownership.owner.employee_id}`
                      : "No accountable author on record"}
                  </span>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  <Badge tone="brand">{ownership.authority.label}</Badge>
                  <Badge tone={ownership.freshness_label === "stale" ? "danger" : "success"}>
                    {ownership.freshness_label}
                  </Badge>
                  <Badge tone="neutral">{ownership.evidence} claims</Badge>
                </div>
                <p className="text-xs text-muted">
                  Backed by “{ownership.source.title}” ({ownership.source.type})
                  {ownership.last_verified_at
                    ? ` · last verified ${new Date(ownership.last_verified_at).toLocaleDateString()}`
                    : " · never verified"}
                </p>
              </div>
            </Card>
          )}

          {propagation && (
            <Card
              title="What a change reaches"
              subtitle={`${propagation.total} entities across ${Object.keys(propagation.by_family).length} families · depth ${propagation.depth}`}
              bodyClassName="p-0"
            >
              <div className="flex flex-wrap gap-1.5 border-b border-line px-5 py-3">
                {Object.entries(propagation.by_family).map(([family, count]) => (
                  <Badge key={family} tone="neutral">
                    {family} × {count}
                  </Badge>
                ))}
              </div>
              {propagation.hops.length === 0 ? (
                <p className="px-5 py-4 text-xs text-faint">
                  No reachable entities yet — the graph sweep will link this topic as signals form.
                </p>
              ) : (
                <div className="divide-y divide-line">
                  {propagation.hops.slice(0, 40).map((hop, index) => (
                    <div key={`${hop.entity_type}-${hop.entity_id}-${index}`} className="flex items-start gap-3 px-5 py-2.5">
                      <Badge tone="neutral">depth {hop.depth}</Badge>
                      <div className="min-w-0 flex-1">
                        <p className="text-[13px] font-medium text-ink">{hop.title}</p>
                        <p className="text-[11px] text-faint">
                          {hop.entity_type} · {hop.relation} · via “{hop.via}”
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          )}

          {impact && (
            <Card
              title="Directly affected"
              subtitle={`${impact.affected.total} entities · ${impact.evidence.total} evidence rows`}
              bodyClassName="p-0"
            >
              {Object.keys(impact.affected.by_family).length === 0 ? (
                <p className="px-5 py-4 text-xs text-faint">No direct relationships anchor this topic yet.</p>
              ) : (
                <div className="divide-y divide-line">
                  {Object.entries(impact.affected.by_family).map(([family, bucket]) => (
                    <div key={family} className="px-5 py-3">
                      <div className="flex items-center justify-between">
                        <Badge tone="brand">{family}</Badge>
                        <Badge tone="neutral">{bucket.count}</Badge>
                      </div>
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {bucket.entities.slice(0, 8).map((entity) => (
                          <Badge key={entity.id} tone="neutral">
                            {entity.id}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {impact.evidence.sources.length > 0 && (
                <div className="border-t border-line px-5 py-3">
                  <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-faint">
                    Grounding evidence
                  </p>
                  <ul className="space-y-1">
                    {impact.evidence.sources.slice(0, 4).map((source, index) => (
                      <li key={index} className="text-xs text-muted">
                        <span className="font-medium text-ink">{source.title ?? source.id}</span> —{" "}
                        {source.excerpt}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </Card>
          )}

          {evolution && (
            <Card
              title="How the understanding evolved"
              subtitle={`${evolution.total} versions retained — nothing erased`}
              bodyClassName="p-0"
            >
              {evolution.steps.length === 0 ? (
                <p className="px-5 py-4 text-xs text-faint">No evolution recorded yet.</p>
              ) : (
                <ol className="divide-y divide-line">
                  {evolution.steps.map((step, index) => (
                    <li key={step.claim_id} className="flex items-start gap-3 px-5 py-3">
                      <div className="mt-1 flex h-2 w-2 shrink-0 rounded-full bg-brand" />
                      <div className="min-w-0 flex-1">
                        <p className="text-[13px] text-ink">{step.statement}</p>
                        <p className="mt-0.5 text-[11px] text-faint">
                          {new Date(step.at).toLocaleString()} · step {index + 1} of{" "}
                          {evolution.total}
                          {step.supersedes ? " · supersedes an earlier version" : " · first recorded"}
                        </p>
                      </div>
                      {typeof step.confidence === "number" && (
                        <Badge tone={confidenceTone(step.confidence)}>
                          {(step.confidence * 100).toFixed(0)}%
                        </Badge>
                      )}
                    </li>
                  ))}
                </ol>
              )}
            </Card>
          )}

          {explorer.error && (
            <Card>
              <p className="text-[13px] text-danger">{explorer.error}</p>
            </Card>
          )}

          {!ownership && !propagation && !impact && !evolution && !explorer.error && (
            <Card>
              <EmptyState
                icon={GitBranch}
                title="No intelligence for this topic yet"
                description="Ownership, propagation, impact and evolution appear once evidence anchors the topic."
              />
            </Card>
          )}
              </>
            );
          })()}
        </div>
      )}
    </div>
  );
}