"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  ArrowRight,
  Brain,
  GitBranch,
  HeartPulse,
  MapPin,
  Newspaper,
  RefreshCw,
  Send,
  Sparkles,
  Target,
  TrendingUp,
} from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { KnowledgeWorkspaceNav } from "@/components/knowledge/WorkspaceNav";
import {
  brainKnowledgeBrief,
  brainKnowledgeHealthCenter,
  brainKnowledgeQuery,
} from "@/lib/api";
import {
  authorityLabel,
  confidenceTone,
  kindLabel,
  severityTone,
} from "@/lib/knowledge-utils";
import type {
  KnowledgeBriefResponse,
  KnowledgeDiscoveryAnswer,
  KnowledgeHealthCenterResponse,
  KnowledgeIntelInsight,
  KnowledgeQueryResponse,
} from "@/types";

const EXAMPLE_QUESTIONS = [
  "What do we know about our pricing?",
  "Should we worry about our Cloud Migration?",
  "What changed in the company this week?",
  "What was our pricing in January?",
  "What decisions are waiting on us?",
  "What knowledge is least certain?",
];

const INTENT_HEADINGS: Record<string, string> = {
  discovery: "What the company knows",
  temporal: "What was true then",
  affected: "What a change to this knowledge would reach",
  stakeholders: "Who owns this knowledge",
  worry: "What deserves worry",
  decide: "Decisions waiting on us",
  missing: "What we don't know",
  next: "Recommended actions",
  confident: "Least certain knowledge",
  changes: "Recent changes",
  gaps: "Knowledge gaps",
  health: "Knowledge health",
  recommendations: "Recommendations",
  contradictions: "Unresolved contradictions",
  provenance: "How this is grounded",
  impact: "What depends on this knowledge",
  ownership: "Who owns this knowledge",
  actions: "The Company Action Center",
  attention: "What needs attention",
  blocked: "Blocked actions",
  overdue: "Overdue actions",
  escalation: "Escalated actions",
};

function CountStat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-line bg-surface px-4 py-3">
      <p className="text-xl font-bold text-ink">{value}</p>
      <p className="mt-0.5 text-[11px] font-medium uppercase tracking-wide text-faint">{label}</p>
    </div>
  );
}

const ACTION_STATE_TONE: Record<string, "neutral" | "brand" | "success" | "warning" | "danger"> = {
  proposed: "neutral",
  validating: "brand",
  awaiting_approval: "warning",
  approved: "brand",
  ready: "brand",
  in_progress: "brand",
  blocked: "danger",
  completed: "success",
  verified: "success",
  rejected: "neutral",
  cancelled: "neutral",
  expired: "neutral",
  failed: "danger",
  superseded: "neutral",
};

function stateTone(state: string) {
  return ACTION_STATE_TONE[state] ?? "neutral";
}

function stateLabel(state: string) {
  const map: Record<string, string> = {
    proposed: "Proposed",
    validating: "Validating",
    awaiting_approval: "Awaiting approval",
    approved: "Approved",
    ready: "Ready",
    in_progress: "In progress",
    blocked: "Blocked",
    completed: "Completed",
    verified: "Verified",
    rejected: "Rejected",
    cancelled: "Cancelled",
    expired: "Expired",
    failed: "Failed",
    superseded: "Superseded",
  };
  return map[state] ?? state.replaceAll("_", " ");
}

function DiscoveryAnswerCard({ answer }: { answer: KnowledgeDiscoveryAnswer }) {
  return (
    <div className="px-5 py-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold text-ink">{answer.topic.name}</span>
        <Badge tone="neutral">{(answer.score * 100).toFixed(0)}% match</Badge>
        {answer.confidence !== null && answer.confidence !== undefined && (
          <Badge tone={confidenceTone(answer.confidence)}>
            {(answer.confidence * 100).toFixed(0)}% confidence
          </Badge>
        )}
        <Badge tone="brand">{authorityLabel(answer.authority)}</Badge>
        {answer.families.length > 0 && (
          <span className="text-[11px] text-faint">evidenced by {answer.families.join(", ")}</span>
        )}
      </div>
      {answer.statement && (
        <p className="mt-2 text-[13px] leading-relaxed text-ink">{answer.statement}</p>
      )}
      {answer.evidence.length > 0 && (
        <ul className="mt-2 space-y-1">
          {answer.evidence.slice(0, 3).map((evidence) => (
            <li key={evidence.claim_id} className="flex items-start gap-2 text-xs text-muted">
              <ArrowRight className="mt-0.5 h-3 w-3 shrink-0 text-faint" />
              <span>
                {evidence.excerpt}
                {evidence.source_title ? ` — ${evidence.source_title}` : ""}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function KnowledgeWorkspacePage() {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<KnowledgeQueryResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [brief, setBrief] = useState<KnowledgeBriefResponse | null>(null);
  const [health, setHealth] = useState<KnowledgeHealthCenterResponse | null>(null);
  const [loadingSummary, setLoadingSummary] = useState(true);

  const loadSummary = useCallback(async () => {
    setLoadingSummary(true);
    try {
      const [briefResult, healthResult] = await Promise.all([
        brainKnowledgeBrief(24),
        brainKnowledgeHealthCenter(),
      ]);
      setBrief(briefResult);
      setHealth(healthResult);
    } catch {
      // best-effort summary
    } finally {
      setLoadingSummary(false);
    }
  }, []);

  useEffect(() => {
    void loadSummary();
  }, [loadSummary]);

  const ask = useCallback(
    async (text?: string) => {
      const query = (text ?? question).trim();
      if (!query || busy) return;
      setBusy(true);
      setError(null);
      try {
        setResult(await brainKnowledgeQuery(query));
      } catch (err) {
        setError(err instanceof Error ? err.message : "The knowledge layer could not answer");
      } finally {
        setBusy(false);
      }
    },
    [busy, question]
  );

  const answerList = useMemo(() => {
    if (!result) return null;
    if (result.intent === "discovery") {
      const answers = (result.answers ?? []) as KnowledgeDiscoveryAnswer[];
      if (answers.length === 0) return null;
      return { type: "discovery" as const, items: answers };
    }
    const insights = (result.answers ?? []).filter(
      (a): a is KnowledgeIntelInsight => typeof (a as KnowledgeIntelInsight).kind === "string"
    );
    if (insights.length === 0) return null;
    return { type: "insights" as const, items: insights };
  }, [result]);

  const heading = result ? INTENT_HEADINGS[result.intent] ?? "Answer" : "";

  return (
    <div className="space-y-4">
      <KnowledgeWorkspaceNav />

      <Card
        title="Ask the company what you know"
        subtitle="One governed surface — every answer is grounded in evidence you can actually see"
      >
        <div className="space-y-3">
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void ask();
            }}
            placeholder="Ask anything about the company's knowledge, e.g. Should we worry about our pricing?"
            rows={3}
            className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink outline-none focus:border-brand"
          />
          <div className="flex flex-wrap items-center gap-2">
            <Button onClick={() => void ask()} disabled={busy || !question.trim()}>
              {busy ? (
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-line border-t-brand" />
              ) : (
                <Send className="h-4 w-4" />
              )}{" "}
              Ask
            </Button>
            {EXAMPLE_QUESTIONS.map((example) => (
              <button
                key={example}
                onClick={() => void ask(example)}
                disabled={busy}
                className="inline-flex cursor-pointer items-center gap-1 rounded-full border border-line bg-surface px-3 py-1 text-[12px] text-muted transition hover:border-brand hover:text-ink"
              >
                <Sparkles className="h-3 w-3 text-brand" />
                {example}
              </button>
            ))}
          </div>
          {error && <p className="text-[13px] text-danger">{error}</p>}
        </div>
      </Card>

      {result && (
        <Card
          title={heading}
          subtitle={
            result.total === 0
              ? undefined
              : `${result.total} result${result.total === 1 ? "" : "s"} · ${result.scope === "org" ? "org-wide view" : "scoped view"}`
          }
          bodyClassName="p-0"
        >
          {result.intent === "temporal" && (
            <div className="divide-y divide-line">
              {result.answer && !result.state && (
                <p className="px-5 py-4 text-sm text-muted">{result.answer}</p>
              )}
              {result.state && (
                <>
                  <div className="px-5 py-4">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone="brand">
                        As of {result.as_of ? new Date(result.as_of).toLocaleDateString() : ""}
                      </Badge>
                      {typeof result.state.confidence === "number" && (
                        <Badge tone={confidenceTone(result.state.confidence)}>
                          {(result.state.confidence * 100).toFixed(0)}% confidence
                        </Badge>
                      )}
                    </div>
                    <p className="mt-2 text-[14px] leading-relaxed text-ink">
                      {result.state.statement}
                    </p>
                  </div>
                  {result.replaced_by && (
                    <div className="px-5 py-4">
                      <p className="text-[11px] font-semibold uppercase tracking-wide text-faint">
                        Replaced on {new Date(result.replaced_by.at).toLocaleDateString()}
                      </p>
                      <p className="mt-1 text-[13px] leading-relaxed text-muted">
                        {result.replaced_by.statement}
                      </p>
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          {result.intent === "affected" && (
            <div className="divide-y divide-line">
              {typeof result.topic === "object" && result.topic && (
                <p className="px-5 py-3 text-[13px] text-muted">
                  <span className="font-semibold text-ink">{result.topic.name}</span> —{" "}
                  {result.total} entities reached across{" "}
                  {Object.keys((result.by_family ?? {}) as Record<string, number>).length} families
                </p>
              )}
              {Array.isArray(result.hops) && result.hops.length === 0 && (
                <EmptyState
                  icon={MapPin}
                  title="No reachable impact"
                  description="A change to this knowledge currently reaches no other entity."
                />
              )}
              {Array.isArray(result.hops) &&
                (result.hops as Array<Record<string, unknown>>).slice(0, 40).map((hop, index) => (
                  <div key={index} className="flex items-start gap-3 px-5 py-3">
                    <Badge tone="neutral">depth {hop.depth as number}</Badge>
                    <div className="min-w-0 flex-1">
                      <p className="text-[13px] font-semibold text-ink">{hop.title as string}</p>
                      <p className="mt-0.5 text-[11px] text-faint">
                        {hop.entity_type as string} · via “{hop.via as string}” (
                        {hop.relation as string})
                      </p>
                    </div>
                  </div>
                ))}
            </div>
          )}

          {result.intent === "stakeholders" && (
            <div className="px-5 py-4">
              <p className="text-[13px] text-muted">
                Owner:{" "}
                <span className="font-semibold text-ink">
                  {(result.owner as Record<string, unknown> | null)?.resolved
                    ? "resolved"
                    : "no accountable author on record"}
                </span>
              </p>
              {Array.isArray(result.stakeholders) && (result.stakeholders as string[]).length > 0 && (
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {(result.stakeholders as string[]).slice(0, 12).map((name) => (
                    <Badge key={name} tone="neutral">
                      {name}
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          )}

          {(result.intent === "changes" ||
            result.intent === "gaps" ||
            result.intent === "health" ||
            result.intent === "recommendations" ||
            result.intent === "contradictions") && (
            <div className="flex items-center gap-3 px-5 py-4 text-sm text-muted">
              <Activity className="h-4 w-4 text-brand" />
              <span>
                This question routes to the{" "}
                <a href={WORKSPACE_LINKS[result.intent] ?? "/knowledge/workspace"} className="font-semibold text-brand hover:underline">
                  {heading}
                </a>{" "}
                section of this workspace — open it for the full view.
              </span>
            </div>
          )}

          {(result.intent === "actions" ||
            result.intent === "attention" ||
            result.intent === "blocked" ||
            result.intent === "overdue" ||
            result.intent === "escalation") && (
            <div className="divide-y divide-line">
              {Array.isArray(result.items) &&
                (result.items as Array<Record<string, unknown>>).length === 0 && (
                  <EmptyState
                    icon={Target}
                    title="No actions here"
                    description="The governed action center has nothing matching this view right now."
                  />
                )}
              {Array.isArray(result.items) &&
                (result.items as Array<Record<string, unknown>>).slice(0, 40).map((item) => (
                  <div key={item.id as string} className="px-5 py-4">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone={stateTone(String(item.state))}>
                        {stateLabel(String(item.state))}
                      </Badge>
                      <Badge tone="neutral">{item.action_type as string}</Badge>
                      <Badge
                        tone={
                          item.risk === "high"
                            ? "danger"
                            : item.risk === "medium"
                              ? "warning"
                              : "success"
                        }
                      >
                        {item.risk as string} risk
                      </Badge>
                      {Array.isArray(item.attention_reasons) &&
                        (item.attention_reasons as string[]).map((reason) => (
                          <Badge key={reason} tone="warning">
                            {reason}
                          </Badge>
                        ))}
                    </div>
                    <p className="mt-2 text-sm font-semibold text-ink">{item.title as string}</p>
                    {item.why ? (
                      <p className="mt-0.5 text-[12px] leading-relaxed text-muted">
                        {item.why as string}
                      </p>
                    ) : null}
                    <p className="mt-1 text-[11px] text-faint">
                      {item.due_at
                        ? `due ${new Date(item.due_at as string).toLocaleString()} · `
                        : ""}
                      escalated {String(item.escalation_level)} · updated{" "}
                      {new Date(item.updated_at as string).toLocaleString()}
                    </p>
                  </div>
                ))}
              {result.total > 0 && (
                <p className="px-5 py-3 text-[11px] text-faint">
                  {result.total} action{result.total === 1 ? "" : "s"} in this view — open the{" "}
                  <a
                    href="/knowledge/workspace/actions"
                    className="font-semibold text-brand hover:underline"
                  >
                    Action Center
                  </a>{" "}
                  to operate on them.
                </p>
              )}
            </div>
          )}

          {answerList === null && result.intent !== "temporal" && result.intent !== "affected" && (
            <EmptyState
              icon={Brain}
              title="No grounded answer"
              description="Nothing in the company's evidence directly answers this question yet."
            />
          )}

          {answerList?.type === "discovery" &&
            answerList.items.map((answer) => (
              <DiscoveryAnswerCard key={answer.topic.id} answer={answer} />
            ))}

          {answerList?.type === "insights" &&
            (answerList.items as KnowledgeIntelInsight[]).map((insight) => (
              <div key={insight.id} className="px-5 py-4">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={severityTone(insight.severity)}>{kindLabel(insight.kind)}</Badge>
                  <Badge tone={confidenceTone(insight.confidence)}>
                    {(insight.confidence * 100).toFixed(0)}% confidence
                  </Badge>
                  {insight.topic_name && <Badge tone="neutral">{insight.topic_name}</Badge>}
                </div>
                <p className="mt-2 text-sm font-semibold text-ink">{insight.title}</p>
                <p className="mt-1 text-[13px] text-muted">{insight.summary}</p>
              </div>
            ))}
        </Card>
      )}

      {loadingSummary ? (
        <Card>
          <div className="flex items-center justify-center py-8 text-sm text-faint">
            Composing the knowledge brief…
          </div>
        </Card>
      ) : (
        <>
          {brief && (
            <Card
              title="Executive knowledge brief"
              subtitle={
                brief.generated_at
                  ? `Generated ${new Date(brief.generated_at).toLocaleString()} · last ${brief.since_hours} hours`
                  : "What changed, emerged, and needs a decision"
              }
              actions={
                <Button size="sm" variant="secondary" onClick={() => void loadSummary()}>
                  <RefreshCw className="h-3.5 w-3.5" /> Refresh
                </Button>
              }
              bodyClassName="p-0"
            >
              <div className="grid gap-px border-b border-line bg-line sm:grid-cols-2 lg:grid-cols-4">
                <div className="bg-surface px-5 py-4">
                  <p className="text-xl font-bold text-ink">{brief.counts.significant_changes}</p>
                  <p className="mt-0.5 text-[11px] font-medium uppercase tracking-wide text-faint">
                    Significant changes
                  </p>
                </div>
                <div className="bg-surface px-5 py-4">
                  <p className="text-xl font-bold text-ink">{brief.counts.emerging_risks}</p>
                  <p className="mt-0.5 text-[11px] font-medium uppercase tracking-wide text-faint">
                    Emerging risks
                  </p>
                </div>
                <div className="bg-surface px-5 py-4">
                  <p className="text-xl font-bold text-ink">{brief.counts.major_knowledge_gaps}</p>
                  <p className="mt-0.5 text-[11px] font-medium uppercase tracking-wide text-faint">
                    Major gaps
                  </p>
                </div>
                <div className="bg-surface px-5 py-4">
                  <p className="text-xl font-bold text-ink">
                    {brief.counts.decisions_potentially_affected}
                  </p>
                  <p className="mt-0.5 text-[11px] font-medium uppercase tracking-wide text-faint">
                    Decisions affected
                  </p>
                </div>
              </div>
              {brief.attention.length === 0 ? (
                <EmptyState
                  icon={Newspaper}
                  title="Nothing needs attention"
                  description="No active knowledge signals demand attention right now."
                />
              ) : (
                <div className="divide-y divide-line">
                  {brief.attention.map((item) => (
                    <div key={item.id} className="flex items-start justify-between gap-3 px-5 py-3">
                      <div>
                        <p className="text-[13px] font-semibold text-ink">{item.title}</p>
                        <p className="mt-0.5 text-xs text-muted">{item.summary}</p>
                      </div>
                      <div className="flex shrink-0 items-center gap-1.5">
                        <Badge tone={severityTone(item.severity)}>{kindLabel(item.kind)}</Badge>
                        <Badge tone={confidenceTone(item.priority_score / 100)}>
                          {(item.priority_score * 100).toFixed(0)}
                        </Badge>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          )}

          {health && (
            <div className="grid gap-4 lg:grid-cols-[minmax(0,260px)_1fr]">
              <Card title="Knowledge health" bodyClassName="p-0">
                <div className="flex flex-col items-center gap-2 px-5 py-6">
                  <div className="flex h-20 w-20 items-center justify-center rounded-full border-4 border-brand text-2xl font-bold text-brand">
                    {health.score}
                  </div>
                  <p className="text-[11px] font-medium uppercase tracking-wide text-faint">
                    Health score · 0-100
                  </p>
                  <p className="text-center text-xs text-muted">
                    Seven explainable bars, {health.drill_down.total_topics} topics
                  </p>
                  <div className="mt-2 flex flex-wrap justify-center gap-1.5">
                    <Badge tone={health.drill_down.contradictions > 0 ? "danger" : "success"}>
                      {health.drill_down.contradictions} contradictions
                    </Badge>
                    <Badge tone={health.drill_down.critical_gaps > 0 ? "warning" : "success"}>
                      {health.drill_down.critical_gaps} critical gaps
                    </Badge>
                    <Badge tone={health.drill_down.unverified_claims > 0 ? "warning" : "success"}>
                      {health.drill_down.unverified_claims} unverified
                    </Badge>
                  </div>
                </div>
              </Card>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                <a
                  href="/knowledge/workspace/changes"
                  className="rounded-xl border border-line bg-surface p-5 transition hover:border-brand"
                >
                  <Activity className="h-5 w-5 text-brand" />
                  <p className="mt-2 text-sm font-semibold text-ink">Changes, insights & gaps</p>
                  <p className="mt-1 text-xs text-muted">
                    What moved, what it means, and what we don't know.
                  </p>
                </a>
                <a
                  href="/knowledge/workspace/impact"
                  className="rounded-xl border border-line bg-surface p-5 transition hover:border-brand"
                >
                  <MapPin className="h-5 w-5 text-brand" />
                  <p className="mt-2 text-sm font-semibold text-ink">Impact analysis</p>
                  <p className="mt-1 text-xs text-muted">
                    What a knowledge change reaches through the graph.
                  </p>
                </a>
                <a
                  href="/knowledge/workspace/recommendations"
                  className="rounded-xl border border-line bg-surface p-5 transition hover:border-brand"
                >
                  <TrendingUp className="h-5 w-5 text-brand" />
                  <p className="mt-2 text-sm font-semibold text-ink">Command center</p>
                  <p className="mt-1 text-xs text-muted">
                    Review, accept and execute recommendations.
                  </p>
                </a>
                <a
                  href="/knowledge/workspace/timeline"
                  className="rounded-xl border border-line bg-surface p-5 transition hover:border-brand"
                >
                  <GitBranch className="h-5 w-5 text-brand" />
                  <p className="mt-2 text-sm font-semibold text-ink">Evolution timeline</p>
                  <p className="mt-1 text-xs text-muted">
                    What was true, when it changed, what replaced it.
                  </p>
                </a>
                <a
                  href="/knowledge/workspace/health"
                  className="rounded-xl border border-line bg-surface p-5 transition hover:border-brand"
                >
                  <HeartPulse className="h-5 w-5 text-brand" />
                  <p className="mt-2 text-sm font-semibold text-ink">Health center</p>
                  <p className="mt-1 text-xs text-muted">
                    Coverage by business area and the seven bars.
                  </p>
                </a>
                <div className="rounded-xl border border-dashed border-line bg-surface p-5">
                  <p className="text-sm font-semibold text-ink">Quick look</p>
                  <div className="mt-2 grid grid-cols-2 gap-2">
                    <CountStat label="Changes" value={brief?.counts.significant_changes ?? 0} />
                    <CountStat label="Attention" value={brief?.attention.length ?? 0} />
                    <CountStat label="Active insights" value={health?.drill_down.contradictions ?? 0} />
                    <CountStat label="Topics" value={health?.drill_down.total_topics ?? 0} />
                  </div>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

const WORKSPACE_LINKS: Record<string, string> = {
  changes: "/knowledge/workspace/changes",
  gaps: "/knowledge/workspace/changes",
  health: "/knowledge/workspace/health",
  recommendations: "/knowledge/workspace/recommendations",
  contradictions: "/knowledge/workspace/changes",
};