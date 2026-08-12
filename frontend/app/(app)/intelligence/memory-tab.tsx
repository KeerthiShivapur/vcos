"use client";

import { useCallback, useEffect, useState } from "react";
import {
  BookOpenCheck,
  History,
  Link2,
  RefreshCw,
  Scale,
  Search,
  Send,
  ShieldCheck,
  Target,
} from "lucide-react";

import {
  brainMemoryEvidence,
  brainMemoryFeed,
  brainMemoryRecordOutcome,
  brainMemoryRelated,
  brainMemorySearch,
  brainMemoryTimeline,
} from "@/lib/api";
import { roleCan, PERMISSIONS } from "@/lib/permissions";
import { useAuth } from "@/hooks/useAuth";
import type {
  BrainMemory,
  BrainMemoryEvidenceItem,
} from "@/types";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Spinner } from "@/components/ui/Spinner";

const CATEGORIES = [
  { id: "experience", label: "Experience", icon: Target },
  { id: "lesson", label: "Lesson", icon: BookOpenCheck },
  { id: "outcome", label: "Outcome", icon: Scale },
] as const;

function categoryBadge(category: string): "brand" | "success" | "warning" {
  if (category === "lesson") return "success";
  if (category === "outcome") return "warning";
  return "brand";
}

function confidenceTone(confidence: number): "brand" | "success" | "neutral" {
  if (confidence >= 0.7) return "success";
  if (confidence >= 0.4) return "brand";
  return "neutral";
}

export function MemoryTab() {
  const { user } = useAuth();
  const canManage = roleCan(user?.role, PERMISSIONS.BRAIN_MANAGE);

  const [section, setSection] = useState("feed");
  const [memories, setMemories] = useState<BrainMemory[]>([]);
  const [episodes, setEpisodes] = useState<BrainMemory[]>([]);
  const [question, setQuestion] = useState("");
  const [matched, setMatched] = useState<BrainMemory[] | null>(null);
  const [selected, setSelected] = useState<BrainMemory | null>(null);
  const [evidence, setEvidence] = useState<BrainMemoryEvidenceItem[] | null>(null);
  const [related, setRelated] = useState<BrainMemory[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const flash = (message: string) => {
    setNotice(message);
    window.setTimeout(() => setNotice(null), 2500);
  };

  const loadFeed = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const feed = await brainMemoryFeed({ limit: 100 });
      setMemories(feed.memories);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load memory feed");
    } finally {
      setBusy(false);
    }
  }, []);

  const loadTimeline = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const timeline = await brainMemoryTimeline({ limit: 100 });
      setEpisodes(timeline.episodes);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load timeline");
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    loadFeed();
    loadTimeline();
  }, [loadFeed, loadTimeline]);

  const openMemory = async (memory: BrainMemory) => {
    setSelected(memory);
    setEvidence(null);
    setRelated(null);
    const [ev, rel] = await Promise.all([
      brainMemoryEvidence(memory.id),
      brainMemoryRelated(memory.id),
    ]);
    setEvidence(ev.evidence);
    setRelated(rel.related);
  };

  const search = async () => {
    if (!question.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const result = await brainMemorySearch({ question: question.trim(), limit: 15 });
      setMatched(result.memories);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Memory search failed");
    } finally {
      setBusy(false);
    }
  };

  const recordOutcome = async (outcomeType: string, outcome: string) => {
    if (!selected || !canManage) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await brainMemoryRecordOutcome(selected.id, {
        outcome_type: outcomeType as "positive" | "negative" | "partial" | "unresolved",
        outcome: outcome || null,
      });
      setSelected({ ...selected, ...updated });
      flash("Outcome recorded — history is preserved in memory_outcomes");
      await loadFeed();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not record outcome");
    } finally {
      setBusy(false);
    }
  };

  const sections = [
    { id: "feed", label: "Feed", count: memories.length },
    { id: "search", label: "Historical search", count: matched?.length ?? null },
    { id: "timeline", label: "Timeline", count: episodes.length },
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-1 border-b border-line">
        {sections.map((s) => (
          <button
            key={s.id}
            onClick={() => setSection(s.id)}
            className={`border-b-2 px-3.5 py-2 text-[13px] font-medium ${
              section === s.id ? "border-brand text-ink" : "border-transparent text-faint"
            }`}
          >
            {s.label}
            {s.count !== null && ` (${s.count})`}
          </button>
        ))}
      </div>

      {notice && <p className="text-[13px] text-success">{notice}</p>}
      {error && <p className="text-[13px] text-danger">{error}</p>}

      {section === "search" && (
        <Card
          title="Historical search"
          subtitle='Ask "have we seen this before?" — semantic retrieval over experiences, lessons and outcomes, bounded by your governance access'
        >
          <div className="flex items-start gap-2">
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void search();
              }}
              placeholder="e.g. task was blocked during execution like this before"
              rows={2}
              className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink outline-none focus:border-brand"
            />
            <Button onClick={search} disabled={busy || !question.trim()}>
              {busy ? (
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-line border-t-brand" />
              ) : (
                <Search className="h-4 w-4" />
              )}{" "}
              Search
            </Button>
          </div>
          {matched === null ? (
            <p className="mt-2 text-xs text-faint">Similarity floor 0.25 — weak matches are excluded.</p>
          ) : matched.length === 0 ? (
            <div className="mt-3">
              <EmptyState
                icon={Search}
                title="Nothing historically similar"
                description="No memories matched within your access at the similarity floor."
              />
            </div>
          ) : (
            <div className="mt-3 divide-y divide-line">
              {matched.map((memory) => (
                <MemoryRow key={memory.id} memory={memory} onOpen={() => void openMemory(memory)} />
              ))}
            </div>
          )}
        </Card>
      )}

      {section === "feed" && (
        <Card
          title="Memory feed"
          subtitle="Evidence-backed organizational memory — experiences, lessons and outcomes"
          actions={
            <Button size="sm" variant="secondary" onClick={loadFeed} disabled={busy}>
              <RefreshCw className={`h-3.5 w-3.5 ${busy ? "animate-spin" : ""}`} /> Refresh
            </Button>
          }
        >
          {memories.length === 0 ? (
            <EmptyState
              icon={ShieldCheck}
              title="No memories yet"
              description="Memories form automatically as work happens — blocked tasks, decisions and completions are captured here."
            />
          ) : (
            <div className="divide-y divide-line">
              {memories.map((memory) => (
                <MemoryRow key={memory.id} memory={memory} onOpen={() => void openMemory(memory)} />
              ))}
            </div>
          )}
        </Card>
      )}

      {section === "timeline" && (
        <Card
          title="Company history"
          subtitle="Episode-style timeline — memories with the events that formed them"
          bodyClassName="p-0"
        >
          {episodes.length === 0 ? (
            <EmptyState
              icon={History}
              title="No history yet"
              description="Timeline episodes appear once the memory worker forms memories from activity."
            />
          ) : (
            <div className="divide-y divide-line">
              {episodes.map((memory) => (
                <MemoryRow key={memory.id} memory={memory} onOpen={() => void openMemory(memory)} />
              ))}
            </div>
          )}
        </Card>
      )}

      {selected && (
        <Card
          title="Memory detail"
          subtitle={`${selected.memory_category} · ${selected.source_event ?? "recorded"} · confidence ${Math.round(selected.confidence * 100)}%`}
        >
          <div className="space-y-4">
            <p className="text-sm font-semibold text-ink">{selected.title}</p>
            {selected.summary && <p className="text-[13px] leading-relaxed text-muted">{selected.summary}</p>}
            {selected.outcome && (
              <p className="text-[13px] leading-relaxed text-muted">
                <span className="font-medium text-ink">Outcome:</span> {selected.outcome}
              </p>
            )}
            {selected.lesson && (
              <p className="text-[13px] leading-relaxed text-muted">
                <span className="font-medium text-ink">Lesson:</span> {selected.lesson}
              </p>
            )}

            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-faint">
                Why VCOS believes this ({evidence?.length ?? 0} evidence refs)
              </p>
              {evidence === null ? (
                <p className="text-xs text-faint">Resolving evidence…</p>
              ) : evidence.length === 0 ? (
                <p className="text-xs text-faint">No resolvable evidence refs.</p>
              ) : (
                <div className="space-y-1.5">
                  {evidence.map((item, index) => (
                    <div key={index} className="flex items-center justify-between gap-2 rounded-lg border border-line px-3 py-1.5">
                      <div className="min-w-0">
                        <p className="truncate text-[13px] text-ink">
                          <Badge tone="neutral">{item.relationship}</Badge>{" "}
                          {item.title || `${item.type} ${item.id}`}
                        </p>
                        {item.occurred_at && (
                          <p className="text-[11px] text-faint">
                            event at {new Date(item.occurred_at).toLocaleString()}
                          </p>
                        )}
                      </div>
                      <Badge tone={item.resolved ? "success" : "warning"}>
                        {item.resolved ? "resolved" : "unresolved"}
                      </Badge>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {related !== null && related.length > 0 && (
              <div>
                <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-faint">
                  Related memories ({related.length})
                </p>
                <div className="space-y-1.5">
                  {related.map((memory) => (
                    <button
                      key={memory.id}
                      onClick={() => void openMemory(memory)}
                      className="flex w-full items-center justify-between gap-2 rounded-lg border border-line px-3 py-1.5 text-left hover:bg-surface"
                    >
                      <p className="truncate text-[13px] text-ink">
                        <Link2 className="mr-1 inline h-3 w-3 text-faint" />
                        {memory.title}
                      </p>
                      <Badge tone={categoryBadge(memory.memory_category)}>{memory.memory_category}</Badge>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {canManage && (
              <OutcomeForm busy={busy} onRecord={recordOutcome} />
            )}
          </div>
        </Card>
      )}
    </div>
  );
}

function MemoryRow({ memory, onOpen }: { memory: BrainMemory; onOpen: () => void }) {
  return (
    <button onClick={onOpen} className="flex w-full items-start justify-between gap-3 px-5 py-3 text-left hover:bg-surface">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={categoryBadge(memory.memory_category)}>{memory.memory_category}</Badge>
          <span className="truncate text-[13px] font-medium text-ink">{memory.title}</span>
        </div>
        {(memory.summary || memory.lesson || memory.outcome) && (
          <p className="mt-1 truncate text-xs text-muted">{memory.summary || memory.lesson || memory.outcome}</p>
        )}
        <p className="mt-1 text-[11px] text-faint">
          {memory.source_event ?? "recorded"}
          {memory.entity_type ? ` · ${memory.entity_type} ${memory.entity_id?.slice(0, 8) ?? ""}` : ""}
          {memory.occurred_at ? ` · ${new Date(memory.occurred_at).toLocaleString()}` : ""}
        </p>
      </div>
      <div className="flex shrink-0 flex-col items-end gap-1">
        <Badge tone={confidenceTone(memory.confidence)}>{Math.round(memory.confidence * 100)}%</Badge>
        <Badge tone={memory.auth_scope === "org" ? "success" : "warning"}>
          {memory.auth_scope === "org" ? "org-wide" : "project-scoped"}
        </Badge>
      </div>
    </button>
  );
}

function OutcomeForm({
  busy,
  onRecord,
}: {
  busy: boolean;
  onRecord: (outcomeType: string, outcome: string) => void;
}) {
  const [outcomeType, setOutcomeType] = useState("positive");
  const [outcome, setOutcome] = useState("");
  return (
    <div className="rounded-lg border border-line p-3">
      <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-faint">
        Record an observed outcome (brain:manage)
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <select
          value={outcomeType}
          onChange={(e) => setOutcomeType(e.target.value)}
          className="rounded-lg border border-line bg-surface px-2 py-1.5 text-sm text-ink outline-none focus:border-brand"
        >
          <option value="positive">positive</option>
          <option value="partial">partial</option>
          <option value="negative">negative</option>
          <option value="unresolved">unresolved</option>
        </select>
        <input
          value={outcome}
          onChange={(e) => setOutcome(e.target.value)}
          placeholder="What happened? (monotonic — upgrades only)"
          className="min-w-0 flex-1 rounded-lg border border-line bg-surface px-3 py-1.5 text-sm text-ink outline-none focus:border-brand"
        />
        <Button size="sm" variant="secondary" onClick={() => onRecord(outcomeType, outcome)} disabled={busy}>
          <Send className="h-3.5 w-3.5" /> Record
        </Button>
      </div>
    </div>
  );
}
