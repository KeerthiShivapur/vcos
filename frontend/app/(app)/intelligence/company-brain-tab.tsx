"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  BookOpen,
  Brain,
  ChevronRight,
  ExternalLink,
  History,
  Layers,
  Network,
  RefreshCw,
  Repeat2,
  Send,
  Sparkles,
} from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import {
  brainAnswer,
  brainConversationCreate,
  brainConversationGet,
  brainConversationList,
  brainEvidence,
  brainGraphRelationshipSync,
  brainOverview,
  brainTimelineUnified,
  brainWhatChanged,
} from "@/lib/api";
import { roleCan, PERMISSIONS } from "@/lib/permissions";
import { useAuth } from "@/hooks/useAuth";
import type {
  BrainAnswer,
  BrainAttentionItem,
  BrainConversation,
  BrainEvidenceResponse,
  BrainRelatedProjection,
  BrainTimelineEntry,
  BrainTimelineResponse,
  BrainUnifiedOverview,
  BrainWhatChanged,
} from "@/types";

function confidenceTone(
  confidence: number,
): "brand" | "success" | "neutral" | "warning" {
  if (confidence >= 0.7) return "success";
  if (confidence >= 0.4) return "brand";
  return "warning";
}

function sectionLabel(key: string): string {
  return key === "patterns"
    ? "Patterns"
    : key === "insights"
      ? "Insights"
      : key === "memories"
        ? "Memory"
        : "Knowledge";
}

const TIMELINE_KIND_LABEL: Record<string, string> = {
  memory: "Memory",
  pattern: "Pattern",
  insight: "Insight",
  project_timeline: "Project event",
};

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

  // Slice 4D.7 — conversational surface
  const [conversation, setConversation] = useState<BrainConversation | null>(
    null,
  );
  const [conversations, setConversations] = useState<BrainConversation[]>([]);
  const [timeline, setTimeline] = useState<BrainTimelineResponse | null>(null);
  const [timelineBusy, setTimelineBusy] = useState(false);
  const [whatChanged, setWhatChanged] = useState<BrainWhatChanged | null>(null);
  const [whatChangedBusy, setWhatChangedBusy] = useState(false);
  const [activeSection, setActiveSection] = useState<
    "chat" | "timeline" | "changes"
  >("chat");

  const loadOverview = useCallback(async () => {
    try {
      setOverview(await brainOverview());
    } catch {
      setOverview(null);
    }
  }, []);

  const loadConversations = useCallback(async () => {
    try {
      const result = await brainConversationList({ limit: 20 });
      setConversations(result.conversations);
      setConversation((current) => current ?? result.conversations[0] ?? null);
    } catch {
      // conversation list is best-effort; the answer still works without it
    }
  }, []);

  useEffect(() => {
    void loadOverview();
    void loadConversations();
  }, [loadConversations, loadOverview]);

  const ensureConversation = useCallback(async () => {
    if (conversation) return conversation;
    const created = await brainConversationCreate();
    setConversation(created);
    setConversations((current) => [created, ...current]);
    return created;
  }, [conversation]);

  const ask = useCallback(
    async (text?: string) => {
      const query = (text ?? question).trim();
      if (!query || busy) return;
      setBusy(true);
      setError(null);
      setNotice(null);
      setDrawer(null);
      setActiveSection("chat");
      try {
        const active = await ensureConversation();
        const result = await brainAnswer({
          question: query,
          conversation_id: active.id,
        });
        setAnswer(result);
        setConversation({
          ...active,
          turn_count: result.conversation?.turn ?? active.turn_count,
        });
        void loadOverview();
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "The brain could not answer",
        );
      } finally {
        setBusy(false);
      }
    },
    [busy, conversation, ensureConversation, loadOverview, question],
  );

  const switchConversation = useCallback(
    async (conversationId: string) => {
      setBusy(true);
      setError(null);
      setAnswer(null);
      try {
        const detail = await brainConversationGet(conversationId);
        setConversation(detail);
        setQuestion(detail.turns && detail.turns.length > 0 ? "" : question);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Could not open conversation",
        );
      } finally {
        setBusy(false);
      }
    },
    [question],
  );

  const loadTimeline = useCallback(
    async (entityType?: string | null, entityId?: string | null) => {
      setTimelineBusy(true);
      try {
        setTimeline(
          await brainTimelineUnified({
            ...(entityType && entityId
              ? { entity_type: entityType, entity_id: entityId }
              : {}),
            limit: 50,
          }),
        );
      } catch {
        setTimeline(null);
      } finally {
        setTimelineBusy(false);
      }
    },
    [],
  );

  const loadWhatChanged = useCallback(async () => {
    setWhatChangedBusy(true);
    try {
      setWhatChanged(await brainWhatChanged({ days: 7 }));
    } catch {
      setWhatChanged(null);
    } finally {
      setWhatChangedBusy(false);
    }
  }, []);

  const sync = useCallback(async () => {
    if (busy) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await brainGraphRelationshipSync({});
      setNotice(
        `Relationship sync: ${result.synced} edges refreshed (${result.mode})`,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Relationship sync failed");
    } finally {
      setBusy(false);
    }
  }, [busy]);

  const openDrawer = useCallback(
    async (sourceType: string, sourceId: string) => {
      setDrawer(null);
      setDrawerError(null);
      try {
        setDrawer(await brainEvidence(sourceType, sourceId, { link_limit: 5 }));
      } catch (err) {
        setDrawerError(
          err instanceof Error ? err.message : "Evidence drawer unavailable",
        );
      }
    },
    [],
  );

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
    [answer],
  );

  const relatedProjections = useMemo(
    () =>
      answer
        ? ([
            {
              key: "patterns",
              label: "Related patterns",
              items: answer.related_patterns ?? [],
            },
            {
              key: "memories",
              label: "Related memories",
              items: answer.related_memories ?? [],
            },
            {
              key: "insights",
              label: "Related insights",
              items: answer.related_insights ?? [],
            },
          ] as const)
        : [],
    [answer],
  );

  const anchorForTimeline = useMemo(() => {
    if (answer && answer.related_entities.length > 0) {
      const project = answer.related_entities.find(
        (entity) => entity.type === "project",
      );
      if (project) return { entity_type: project.type, entity_id: project.id };
    }
    return null;
  }, [answer]);

  const timelineEntries: BrainTimelineEntry[] = useMemo(() => {
    if (activeSection !== "timeline" || !timeline) return [];
    return timeline.timeline;
  }, [activeSection, timeline]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-1 border-b border-line">
          {[
            { id: "chat", label: "Q&A" },
            { id: "timeline", label: "Company timeline" },
            { id: "changes", label: "What changed" },
          ].map((section) => (
            <button
              key={section.id}
              onClick={() =>
                setActiveSection(section.id as typeof activeSection)
              }
              className={`border-b-2 px-3.5 py-2 text-[13px] font-medium ${
                activeSection === section.id
                  ? "border-brand text-ink"
                  : "border-transparent text-faint"
              }`}
            >
              {section.label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          {canManage && (
            <Button variant="secondary" onClick={sync} disabled={busy}>
              <RefreshCw className="h-4 w-4" /> Sync relationships
            </Button>
          )}
          <span className="text-[11px] text-faint">
            {conversation
              ? `Conversation · ${conversation.turn_count} turn${conversation.turn_count === 1 ? "" : "s"}`
              : "Start a conversation to enable follow-ups"}
          </span>
        </div>
      </div>

      {activeSection === "chat" && (
        <>
          <Card
            title="Unified company brain"
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
                <Button
                  onClick={() => void ask()}
                  disabled={busy || !question.trim()}
                >
                  {busy ? (
                    <span className="h-4 w-4 animate-spin rounded-full border-2 border-line border-t-brand" />
                  ) : (
                    <Send className="h-4 w-4" />
                  )}{" "}
                  Ask the brain
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => void ask("What changed this week?")}
                  disabled={busy}
                >
                  <Sparkles className="h-4 w-4" /> What changed this week?
                </Button>
                <span className="ml-auto text-xs text-faint">
                  Governance first, then retrieval · claims are evidence-cited
                </span>
              </div>
              {conversations.length > 1 && (
                <div className="flex flex-wrap items-center gap-1.5 pt-1">
                  <span className="text-[11px] uppercase tracking-wide text-faint">
                    Conversations
                  </span>
                  {conversations.slice(0, 6).map((item) => (
                    <button
                      key={item.id}
                      onClick={() => void switchConversation(item.id)}
                      className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[11px] transition ${
                        conversation?.id === item.id
                          ? "border-brand bg-brand-soft text-ink"
                          : "border-line bg-surface text-muted hover:border-brand hover:text-ink"
                      }`}
                    >
                      <History className="h-3 w-3" />
                      {item.turn_count} turn{item.turn_count === 1 ? "" : "s"}
                      {item.last_anchor_title
                        ? ` · ${item.last_anchor_title}`
                        : ""}
                    </button>
                  ))}
                </div>
              )}
              {notice && <p className="text-[13px] text-success">{notice}</p>}
              {error && <p className="text-[13px] text-danger">{error}</p>}
            </div>
          </Card>

          {overview && (
            <Card
              title="What needs attention"
              subtitle="Bounded, visibility-filtered intelligence"
              bodyClassName="p-0"
            >
              {overview.attention.length === 0 ? (
                <EmptyState
                  icon={Brain}
                  title="Nothing demanding attention"
                  description="No insights, patterns or memories require your attention right now."
                />
              ) : (
                <div className="divide-y divide-line">
                  {overview.attention.map((item: BrainAttentionItem) => (
                    <div
                      key={`${item.source}-${item.id}`}
                      className="flex items-start justify-between gap-3 px-5 py-3"
                    >
                      <div>
                        <a
                          href={item.url}
                          className="text-sm font-semibold text-ink hover:text-brand"
                        >
                          {item.title}
                        </a>
                        {item.detail && (
                          <p className="mt-0.5 text-xs text-muted">
                            {item.detail}
                          </p>
                        )}
                      </div>
                      <div className="flex shrink-0 items-center gap-1.5">
                        <Badge tone="neutral">{item.source}</Badge>
                        <Badge tone={confidenceTone(item.confidence)}>
                          {(item.confidence * 100).toFixed(0)}%
                        </Badge>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              <div className="border-t border-line px-5 py-2.5 text-xs text-faint">
                <span className="font-medium text-muted">
                  Recent intelligence:
                </span>{" "}
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
                    <p className="text-[15px] font-semibold leading-snug text-ink">
                      {answer.summary}
                    </p>
                    <Badge tone={confidenceTone(answer.confidence)}>
                      {(answer.confidence * 100).toFixed(0)}% confidence
                    </Badge>
                  </div>
                  {answer.related_entities.length > 0 && (
                    <div className="mt-3 flex flex-wrap items-center gap-1.5">
                      <span className="text-[11px] uppercase tracking-wide text-faint">
                        Related entities
                      </span>
                      {answer.related_entities.map((entity) => (
                        <button
                          key={`${entity.type}-${entity.id}`}
                          onClick={() =>
                            void openDrawer(entity.type, entity.id)
                          }
                          className="inline-flex cursor-pointer items-center gap-1 rounded-full border border-line bg-surface px-2.5 py-0.5 text-[11px] text-muted transition hover:border-brand hover:text-ink"
                        >
                          <span className="font-medium text-brand">
                            {entity.type}
                          </span>
                          {entity.title}
                        </button>
                      ))}
                    </div>
                  )}

                  {answer.timeline && answer.timeline.length > 0 && (
                    <div className="mt-4">
                      <p className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-faint">
                        <History className="h-3 w-3" /> What has happened
                      </p>
                      <ol className="space-y-1.5 border-l border-line pl-3">
                        {answer.timeline.map((entry) => (
                          <li
                            key={`${entry.kind}-${entry.id}`}
                            className="flex items-center gap-2 text-[13px]"
                          >
                            <ChevronRight className="h-3 w-3 shrink-0 text-faint" />
                            <a
                              href={entry.url}
                              className="font-medium text-ink hover:text-brand"
                            >
                              {entry.title}
                            </a>
                            <Badge tone="neutral">
                              {TIMELINE_KIND_LABEL[entry.kind] ?? entry.kind}
                            </Badge>
                            {entry.occurred_at && (
                              <span className="ml-auto shrink-0 text-[11px] text-faint">
                                {new Date(
                                  entry.occurred_at,
                                ).toLocaleDateString()}
                              </span>
                            )}
                          </li>
                        ))}
                      </ol>
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
                      <div
                        key={`${claim.timestamp}-${index}`}
                        className="px-5 py-4"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <p className="text-sm font-semibold text-ink">
                            {claim.claim}
                          </p>
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
                              <span className="font-medium text-brand">
                                {evidence.type}
                              </span>
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

                {answer.reasoning_chain &&
                  answer.reasoning_chain.length > 0 && (
                    <div className="border-y border-line px-5 py-4">
                      <p className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-faint">
                        <Network className="h-3 w-3" /> Why the brain thinks so
                        — reasoning chain
                      </p>
                      <ol className="space-y-2">
                        {answer.reasoning_chain.map((step) => (
                          <li
                            key={step.step}
                            className="flex items-start gap-2.5"
                          >
                            <Badge tone="brand">step {step.step}</Badge>
                            <div className="min-w-0">
                              <p className="text-[13px] leading-snug text-ink">
                                <span className="font-semibold">
                                  {step.label}:
                                </span>{" "}
                                {step.claim}
                              </p>
                              <div className="mt-1 flex flex-wrap gap-1.5">
                                {step.evidence.slice(0, 3).map((evidence) => (
                                  <a
                                    key={`${evidence.type}-${evidence.id}`}
                                    href={evidence.url}
                                    className="inline-flex items-center gap-1 rounded-full border border-line bg-surface px-2 py-0.5 text-[11px] text-muted hover:text-ink"
                                  >
                                    <span className="font-medium text-brand">
                                      {evidence.type}
                                    </span>
                                    {evidence.title}
                                  </a>
                                ))}
                              </div>
                            </div>
                            <Badge tone="neutral" className="ml-auto shrink-0">
                              {(step.confidence * 100).toFixed(0)}%
                            </Badge>
                          </li>
                        ))}
                      </ol>
                    </div>
                  )}

                {sections.some((section) => section.items.length > 0) && (
                  <div className="grid gap-px border-b border-line bg-line sm:grid-cols-2">
                    {sections.map(
                      (section) =>
                        section.items.length > 0 && (
                          <div
                            key={section.key}
                            className="bg-surface px-5 py-4"
                          >
                            <p className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-faint">
                              <Layers className="h-3 w-3" />{" "}
                              {sectionLabel(section.key)}
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
                        ),
                    )}
                  </div>
                )}

                {relatedProjections.some(
                  (section) => section.items.length > 0,
                ) && (
                  <div className="px-5 py-4">
                    <p className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-faint">
                      <Repeat2 className="h-3 w-3" /> Anchored to this entity
                    </p>
                    <div className="grid gap-3 sm:grid-cols-3">
                      {relatedProjections.map(
                        (section) =>
                          section.items.length > 0 && (
                            <div key={section.key}>
                              <p className="mb-1.5 text-xs text-muted">
                                {section.label}
                              </p>
                              <ul className="space-y-1">
                                {section.items.map(
                                  (item: BrainRelatedProjection) => (
                                    <li key={item.id}>
                                      <a
                                        href={item.url}
                                        className="text-[13px] font-medium text-ink hover:text-brand"
                                      >
                                        {item.title}
                                      </a>
                                    </li>
                                  ),
                                )}
                              </ul>
                            </div>
                          ),
                      )}
                    </div>
                  </div>
                )}

                {answer.recommended_next_questions &&
                  answer.recommended_next_questions.length > 0 && (
                    <div className="border-t border-line px-5 py-4">
                      <p className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-faint">
                        <Sparkles className="h-3 w-3" /> Keep asking
                      </p>
                      <div className="flex flex-wrap gap-1.5">
                        {answer.recommended_next_questions.map(
                          (nextQuestion) => (
                            <button
                              key={nextQuestion}
                              onClick={() => {
                                setQuestion(nextQuestion);
                                void ask(nextQuestion);
                              }}
                              disabled={busy}
                              className="inline-flex cursor-pointer items-center gap-1 rounded-full border border-brand/30 bg-brand-soft px-3 py-1 text-[12px] font-medium text-ink transition hover:border-brand"
                            >
                              {nextQuestion}
                              <ArrowRight className="h-3 w-3" />
                            </button>
                          ),
                        )}
                      </div>
                    </div>
                  )}
              </Card>

              <div className="grid gap-4 lg:grid-cols-2">
                <Card
                  title="Evidence drawer"
                  subtitle="Open a related entity to see why sources are connected"
                  bodyClassName="p-0"
                >
                  <div className="divide-y divide-line">
                    {!drawer && !drawerError && (
                      <p className="px-5 py-3 text-xs text-faint">
                        Click a related entity chip above, or an evidence link
                        on any claim, to open its cross-source evidence drawer.
                      </p>
                    )}
                    {drawerError && (
                      <p className="px-5 py-3 text-[13px] text-danger">
                        {drawerError}
                      </p>
                    )}
                    {drawer && (
                      <>
                        <div className="flex items-center justify-between gap-3 px-5 py-3">
                          <div className="flex items-center gap-2">
                            <Badge tone="neutral">{drawer.source.type}</Badge>
                            <span className="text-sm font-semibold text-ink">
                              {drawer.source.title}
                            </span>
                          </div>
                          <a
                            href={drawer.source.url}
                            className="inline-flex items-center gap-1 text-[11px] text-brand hover:underline"
                          >
                            Open source <ExternalLink className="h-3 w-3" />
                          </a>
                        </div>
                        {drawer.evidence.length === 0 ? (
                          <p className="px-5 py-3 text-xs text-faint">
                            No linked intelligence yet — sources connect as
                            signals form.
                          </p>
                        ) : (
                          drawer.evidence.map((item) => (
                            <div
                              key={`${item.type}-${item.id}`}
                              className="flex items-start justify-between gap-3 px-5 py-3"
                            >
                              <div>
                                <a
                                  href={item.url}
                                  className="text-[13px] font-semibold text-ink hover:text-brand"
                                >
                                  {item.title}
                                </a>
                                <p className="mt-0.5 text-[11px] text-muted">
                                  {item.relationship}
                                </p>
                              </div>
                              <Badge tone="neutral">{item.type}</Badge>
                            </div>
                          ))
                        )}
                        {(drawer.related_entities.length > 0 ||
                          drawer.evidence.length > 0) && (
                          <div className="border-t border-line px-5 py-2.5">
                            <p className="text-[11px] uppercase tracking-wide text-faint">
                              Graph neighbors
                            </p>
                            {drawer.related_entities.length > 0 ? (
                              <div className="mt-1.5 flex flex-wrap gap-1.5">
                                {drawer.related_entities.map((entity) => (
                                  <button
                                    key={`${entity.type}-${entity.id}`}
                                    onClick={() =>
                                      void openDrawer(entity.type, entity.id)
                                    }
                                    className="inline-flex cursor-pointer items-center gap-1 rounded-full border border-line bg-surface px-2.5 py-0.5 text-[11px] text-muted transition hover:border-brand hover:text-ink"
                                  >
                                    <span className="font-medium text-brand">
                                      {entity.type}
                                    </span>
                                    {entity.title}
                                    <span className="text-faint">
                                      {entity.relation}
                                    </span>
                                  </button>
                                ))}
                              </div>
                            ) : (
                              <p className="mt-1 text-[11px] text-faint">
                                No connected entities yet — neighbors surface
                                once the graph sweep links this entity.
                              </p>
                            )}
                          </div>
                        )}
                      </>
                    )}
                  </div>
                </Card>

                <Card
                  title="Why this answer reached you"
                  subtitle="Sources are consulted only when relevant — everything governed"
                  bodyClassName="p-0"
                >
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
                        {answer.metrics?.answer_claim_count ??
                          answer.claims.length}{" "}
                        claims · {answer.metrics?.timeline_entries ?? 0}{" "}
                        timeline · {answer.metrics?.reasoning_chain_steps ?? 0}{" "}
                        chain steps
                      </span>
                    </div>
                    <p className="px-5 py-3 text-xs leading-relaxed text-muted">
                      {answer.scope.org_wide
                        ? "Your governance access is org-wide, so this answer reflects the whole company's intelligence."
                        : "Your governance access is scoped — evidence beyond your scope never reaches this answer."}{" "}
                      Confidence is the mean of claim confidences; each claim
                      carries its own evidence trail.{" "}
                      {overview?.scope &&
                        "The overview and answer above always observe the same governed intelligence."}
                    </p>
                    <p className="px-5 py-3 text-[11px] text-faint">
                      Answered {new Date(answer.answered_at).toLocaleString()} ·{" "}
                      {answer.metrics?.brain_query_duration_ms ?? 0}ms composed
                      · {answer.metrics?.governance_filtered_count ?? 0} sources
                      trimmed by access
                      {answer.persona && (
                        <>
                          {" "}
                          · view{" "}
                          {answer.persona.org_wide ? "org-wide" : "scoped"} (
                          {answer.persona.visible_project_count} projects ·{" "}
                          {answer.persona.visible_scope_count} scopes visible)
                        </>
                      )}
                    </p>
                  </div>
                </Card>
              </div>
            </>
          )}
        </>
      )}

      {activeSection === "timeline" && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-muted">
              The unified company timeline — memories, patterns, insights and
              project events, every entry linked to a real row you can access.
            </p>
            <div className="flex items-center gap-2">
              {anchorForTimeline && (
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() =>
                    void loadTimeline(
                      anchorForTimeline.entity_type,
                      anchorForTimeline.entity_id,
                    )
                  }
                  disabled={timelineBusy}
                >
                  <BookOpen className="h-3.5 w-3.5" /> Open{" "}
                  {anchorForTimeline.entity_type} timeline
                </Button>
              )}
              <Button
                size="sm"
                onClick={() => void loadTimeline()}
                disabled={timelineBusy}
              >
                <RefreshCw
                  className={`h-3.5 w-3.5 ${timelineBusy ? "animate-spin" : ""}`}
                />{" "}
                Refresh
              </Button>
            </div>
          </div>
          {timelineBusy && !timeline ? (
            <Card>
              <div className="flex items-center justify-center py-10 text-sm text-faint">
                Loading the unified timeline…
              </div>
            </Card>
          ) : (
            <Card
              title={
                timeline?.entity
                  ? `Timeline — ${timeline.entity.title ?? timeline.entity.id}`
                  : "Unified company timeline"
              }
              subtitle={
                timeline
                  ? `${timeline.count} entries · ${timeline.scope.org_wide ? "org-wide view" : "scoped view"}`
                  : "Evidence-backed company history under governance"
              }
              bodyClassName="p-0"
            >
              {!timeline || timeline.timeline.length === 0 ? (
                <EmptyState
                  icon={History}
                  title="No timeline entries yet"
                  description="Memories, patterns, insights and project events will appear here as the organization works."
                  action={
                    <Button
                      size="sm"
                      onClick={() => void loadTimeline()}
                      disabled={timelineBusy}
                    >
                      <RefreshCw
                        className={`h-3.5 w-3.5 ${timelineBusy ? "animate-spin" : ""}`}
                      />{" "}
                      Load timeline
                    </Button>
                  }
                />
              ) : (
                <ol className="divide-y divide-line">
                  {timeline.timeline.map((entry) => (
                    <li
                      key={`${entry.kind}-${entry.id}`}
                      className="flex items-start gap-3 px-5 py-3"
                    >
                      <div className="mt-1 flex h-2 w-2 shrink-0 rounded-full bg-brand" />
                      <div className="min-w-0 flex-1">
                        <a
                          href={entry.url}
                          className="text-[13px] font-semibold text-ink hover:text-brand"
                        >
                          {entry.title}
                        </a>
                        <p className="mt-0.5 text-[11px] text-faint">
                          {TIMELINE_KIND_LABEL[entry.kind] ?? entry.kind} ·{" "}
                          {entry.occurred_at
                            ? new Date(entry.occurred_at).toLocaleString()
                            : "no timestamp"}
                        </p>
                      </div>
                      {typeof entry.confidence === "number" && (
                        <Badge tone="neutral" className="shrink-0">
                          {(entry.confidence * 100).toFixed(0)}%
                        </Badge>
                      )}
                    </li>
                  ))}
                </ol>
              )}
            </Card>
          )}
        </div>
      )}

      {activeSection === "changes" && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-muted">
              What changed across the company recently — bounded, persona-aware.
              Scoped callers see only their scope&apos;s activity.
            </p>
            <Button
              size="sm"
              onClick={() => void loadWhatChanged()}
              disabled={whatChangedBusy}
            >
              <RefreshCw
                className={`h-3.5 w-3.5 ${whatChangedBusy ? "animate-spin" : ""}`}
              />{" "}
              Refresh
            </Button>
          </div>
          {whatChangedBusy && !whatChanged ? (
            <Card>
              <div className="flex items-center justify-center py-10 text-sm text-faint">
                Digesting recent activity…
              </div>
            </Card>
          ) : (
            <Card
              title={`What changed${whatChanged ? ` · last ${whatChanged.days} days` : ""}`}
              subtitle={
                whatChanged
                  ? whatChanged.org_wide
                    ? "Org-wide digest"
                    : "Your scope's digest"
                  : "Recent company activity under governance"
              }
              bodyClassName="p-0"
            >
              {!whatChanged || whatChanged.categories.length === 0 ? (
                <EmptyState
                  icon={Sparkles}
                  title="Nothing changed recently"
                  description="Recent tasks, decisions, memories, meetings and messages will appear here."
                  action={
                    <Button
                      size="sm"
                      onClick={() => void loadWhatChanged()}
                      disabled={whatChangedBusy}
                    >
                      <RefreshCw
                        className={`h-3.5 w-3.5 ${whatChangedBusy ? "animate-spin" : ""}`}
                      />{" "}
                      Load digest
                    </Button>
                  }
                />
              ) : (
                <div className="divide-y divide-line">
                  {whatChanged.categories.map((category) => (
                    <div key={category.category} className="px-5 py-3.5">
                      <div className="flex items-center justify-between gap-3">
                        <p className="text-[13px] font-semibold text-ink">
                          {category.category.replace(/_/g, " ")}
                        </p>
                        <Badge tone="neutral">
                          {category.count}{" "}
                          {category.count === 1 ? "change" : "changes"}
                        </Badge>
                      </div>
                      {category.items && category.items.length > 0 && (
                        <ul className="mt-2 space-y-1">
                          {category.items.slice(0, 6).map((item) => (
                            <li
                              key={`${item.type}-${item.id}`}
                              className="flex items-center gap-2 text-[13px]"
                            >
                              <ChevronRight className="h-3 w-3 shrink-0 text-faint" />
                              <a
                                href={item.url}
                                className="font-medium text-ink hover:text-brand"
                              >
                                {item.title}
                              </a>
                              <Badge tone="neutral">{item.type}</Badge>
                              {item.timestamp && (
                                <span className="ml-auto shrink-0 text-[11px] text-faint">
                                  {new Date(item.timestamp).toLocaleString()}
                                </span>
                              )}
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
