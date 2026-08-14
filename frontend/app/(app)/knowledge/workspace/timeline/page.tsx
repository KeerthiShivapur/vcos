"use client";

import { useCallback, useState } from "react";
import { GitBranch, History, Search } from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { KnowledgeWorkspaceNav } from "@/components/knowledge/WorkspaceNav";
import {
  brainKnowledgeDiscover,
  brainKnowledgeTopicEvolution,
  brainKnowledgeTopicStateAt,
} from "@/lib/api";
import { confidenceTone } from "@/lib/knowledge-utils";
import type {
  KnowledgeDiscoveryAnswer,
  KnowledgeEvolutionResponse,
  KnowledgeStateAtResponse,
} from "@/types";

const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

export default function KnowledgeWorkspaceTimelinePage() {
  const [query, setQuery] = useState("");
  const [matches, setMatches] = useState<KnowledgeDiscoveryAnswer[] | null>(null);
  const [searchBusy, setSearchBusy] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  const [topic, setTopic] = useState<string | null>(null);
  const [evolution, setEvolution] = useState<KnowledgeEvolutionResponse | null>(null);
  const [evolutionBusy, setEvolutionBusy] = useState(false);
  const [evolutionError, setEvolutionError] = useState<string | null>(null);

  const [month, setMonth] = useState<number>(new Date().getMonth());
  const [stateAt, setStateAt] = useState<KnowledgeStateAtResponse | null>(null);
  const [stateBusy, setStateBusy] = useState(false);
  const [stateError, setStateError] = useState<string | null>(null);

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
      setTopic(topicName);
      setMatches(null);
      setQuery(topicName);
      setEvolution(null);
      setStateAt(null);
      setEvolutionBusy(true);
      setEvolutionError(null);
      setStateError(null);
      try {
        setEvolution(await brainKnowledgeTopicEvolution(topicName));
      } catch (err) {
        setEvolutionError(err instanceof Error ? err.message : "Evolution unavailable");
      } finally {
        setEvolutionBusy(false);
      }
    },
    []
  );

  const loadStateAt = useCallback(async () => {
    if (!topic || stateBusy) return;
    setStateBusy(true);
    setStateError(null);
    setStateAt(null);
    const year = new Date().getFullYear();
    const asOf = new Date(Date.UTC(year, month, 1)).toISOString();
    try {
      setStateAt(await brainKnowledgeTopicStateAt(topic, { as_of: asOf }));
    } catch (err) {
      setStateError(err instanceof Error ? err.message : "No recorded state at that time");
    } finally {
      setStateBusy(false);
    }
  }, [month, stateBusy, topic]);

  return (
    <div className="space-y-4">
      <KnowledgeWorkspaceNav />

      <Card
        title="Evolution timeline"
        subtitle="Pick a topic to walk the supersession chain — what was true, when it changed, what replaced it"
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
            placeholder="Search topics, e.g. pricing"
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
                    <GitBranch className="h-3 w-3 text-brand" />
                    {match.topic.name}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </Card>

      {!topic && (
        <EmptyState
          icon={History}
          title="No topic selected"
          description="Search for a topic above to see how the company's understanding of it evolved."
        />
      )}

      {topic && evolutionBusy && (
        <Card>
          <div className="flex items-center justify-center py-10 text-sm text-faint">
            Rebuilding the supersession chain for “{topic}”…
          </div>
        </Card>
      )}

      {topic && !evolutionBusy && evolution && (
        <Card
          title={`“${evolution.topic.name}” · ${evolution.total} version${evolution.total === 1 ? "" : "s"}`}
          subtitle="Old versions are retained, never erased — each step shows what superseded what"
          bodyClassName="p-0"
        >
          {evolution.steps.length === 0 ? (
            <p className="px-5 py-4 text-xs text-faint">No evolution recorded for this topic yet.</p>
          ) : (
            <ol className="divide-y divide-line">
              {evolution.steps.map((step, index) => (
                <li key={step.claim_id} className="flex items-start gap-3 px-5 py-3.5">
                  <div className="mt-1.5 flex flex-col items-center">
                    <div className="h-2.5 w-2.5 rounded-full border-2 border-brand" />
                    {index < evolution.steps.length - 1 && <div className="h-full w-px bg-line" />}
                  </div>
                  <div className="min-w-0 flex-1 pb-2">
                    <p className="text-[13px] leading-relaxed text-ink">{step.statement}</p>
                    <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                      <Badge tone="neutral">{new Date(step.at).toLocaleString()}</Badge>
                      <Badge tone={step.status === "superseded" ? "neutral" : "success"}>
                        {step.status}
                      </Badge>
                      {typeof step.confidence === "number" && (
                        <Badge tone={confidenceTone(step.confidence)}>
                          {(step.confidence * 100).toFixed(0)}%
                        </Badge>
                      )}
                      {step.supersedes && (
                        <span className="text-[11px] text-faint">supersedes {step.supersedes}</span>
                      )}
                      {step.replaced_by && (
                        <span className="text-[11px] text-faint">
                          later replaced by {step.replaced_by}
                        </span>
                      )}
                    </div>
                  </div>
                </li>
              ))}
            </ol>
          )}
        </Card>
      )}

      {topic && evolutionError && (
        <Card>
          <p className="text-[13px] text-danger">{evolutionError}</p>
        </Card>
      )}

      {topic && (
        <Card
          title="What was true then"
          subtitle="Temporal state — the understanding valid in a chosen month"
          actions={
            <div className="flex items-center gap-2">
              <select
                value={month}
                onChange={(e) => setMonth(Number(e.target.value))}
                className="rounded-lg border border-line bg-surface px-2 py-1.5 text-sm text-ink outline-none focus:border-brand"
              >
                {MONTHS.map((name, index) => (
                  <option key={name} value={index}>
                    {name}
                  </option>
                ))}
              </select>
              <Button size="sm" onClick={() => void loadStateAt()} disabled={stateBusy}>
                {stateBusy ? (
                  <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-line border-t-brand" />
                ) : (
                  <History className="h-3.5 w-3.5" />
                )}{" "}
                Show state
              </Button>
            </div>
          }
          bodyClassName="p-0"
        >
          {stateError && <p className="px-5 py-3 text-[13px] text-danger">{stateError}</p>}
          {stateAt && (
            <div className="divide-y divide-line">
              <div className="px-5 py-4">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone="brand">
                    {new Date(stateAt.as_of).toLocaleDateString("en-US", {
                      month: "long",
                      year: "numeric",
                    })}
                  </Badge>
                  {typeof stateAt.state.confidence === "number" && (
                    <Badge tone={confidenceTone(stateAt.state.confidence)}>
                      {(stateAt.state.confidence * 100).toFixed(0)}% confidence
                    </Badge>
                  )}
                </div>
                <p className="mt-2 text-[14px] leading-relaxed text-ink">{stateAt.state.statement}</p>
                <p className="mt-1 text-[11px] text-faint">
                  valid from {new Date(stateAt.state.valid_from).toLocaleDateString()}
                  {stateAt.state.valid_to
                    ? ` to ${new Date(stateAt.state.valid_to).toLocaleDateString()}`
                    : " — still the current understanding"}
                </p>
              </div>
              {stateAt.replaced_by && (
                <div className="px-5 py-4">
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-faint">
                    Replaced on {new Date(stateAt.replaced_by.at).toLocaleDateString()}
                  </p>
                  <p className="mt-1 text-[13px] leading-relaxed text-muted">
                    {stateAt.replaced_by.statement}
                  </p>
                </div>
              )}
            </div>
          )}
        </Card>
      )}
    </div>
  );
}