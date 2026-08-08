"use client";

import { Suspense, useEffect, useState } from "react";
import { BarChart3, Plus, Vote } from "lucide-react";

import {
  createPoll,
  getMyEmployee,
  getPollResults,
  listCommunities,
  listPolls,
  votePoll,
} from "@/lib/api";
import type { Community, Poll, PollResult } from "@/types";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { Select } from "@/components/ui/Select";
import { Modal } from "@/components/ui/Modal";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { Badge } from "@/components/ui/Badge";
import { Avatar } from "@/components/ui/Avatar";
import { timeAgo } from "@/lib/utils";

export default function PollsPage() {
  return (
    <Suspense fallback={null}>
      <PollsContent />
    </Suspense>
  );
}

function PollsContent() {
  const [polls, setPolls] = useState<Poll[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [myEmployeeId, setMyEmployeeId] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [list, me] = await Promise.all([
        listPolls({ limit: 200 }),
        getMyEmployee().catch(() => null),
      ]);
      setPolls(list);
      setMyEmployeeId(me?.id ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load polls");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Polls"
        description="Quick decisions, crowdsourced."
        actions={
          <Button size="sm" onClick={() => setCreateOpen(true)}>
            <Plus className="h-4 w-4" /> New poll
          </Button>
        }
      />

      {error ? (
        <ErrorState title="Could not load polls" message={error} onRetry={load} />
      ) : loading ? (
        <div className="flex justify-center py-24"><Spinner label="Loading polls" /></div>
      ) : polls.length === 0 ? (
        <EmptyState
          icon={Vote}
          title="No polls yet"
          description="Ask your team a question and get answers fast."
          action={<Button size="sm" onClick={() => setCreateOpen(true)}><Plus className="h-4 w-4" /> New poll</Button>}
        />
      ) : (
        <div className="mx-auto max-w-2xl space-y-4">
          {polls.map((poll) => (
            <PollCard
              key={poll.id}
              poll={poll}
              isMine={poll.created_by === myEmployeeId}
              onVote={async (optionIds) => {
                await votePoll(poll.id, optionIds);
                load();
              }}
            />
          ))}
        </div>
      )}

      <CreatePollModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={async (payload) => {
          await createPoll(payload);
          setCreateOpen(false);
          load();
        }}
      />
    </div>
  );
}

function PollCard({
  poll,
  isMine,
  onVote,
}: {
  poll: Poll;
  isMine: boolean;
  onVote: (optionIds: string[]) => Promise<void>;
}) {
  const [results, setResults] = useState<PollResult | null>(null);
  const [choices, setChoices] = useState<string[]>([]);
  const [voting, setVoting] = useState(false);

  async function toggleChoice(optionId: string) {
    setChoices((prev) =>
      poll.multiple_choice
        ? prev.includes(optionId)
          ? prev.filter((c) => c !== optionId)
          : [...prev, optionId]
        : [optionId]
    );
  }

  async function submit() {
    if (choices.length === 0) return;
    setVoting(true);
    try {
      await onVote(choices);
      setChoices([]);
    } finally {
      setVoting(false);
    }
  }

  async function showResults() {
    try {
      setResults(await getPollResults(poll.id));
    } catch {
      /* ignore */
    }
  }

  const showBars = poll.voted || isMine || results !== null;

  return (
    <div className="rounded-lg border border-line bg-surface p-5">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-[15px] font-semibold text-ink">{poll.title}</h3>
        <Badge tone={poll.status === "open" ? "success" : "neutral"}>{poll.status}</Badge>
        {poll.multiple_choice && <Badge tone="brand">Multiple</Badge>}
        {poll.anonymous && <Badge tone="neutral">Anonymous</Badge>}
      </div>
      {poll.question && <p className="mt-1 text-[13px] text-muted">{poll.question}</p>}
      <div className="mt-2 flex items-center gap-3 text-[12px] text-faint">
        <span className="flex items-center gap-1.5"><Avatar name={poll.creator_name} size="xs" /> {poll.creator_name}</span>
        <span>· {timeAgo(poll.created_at)}</span>
        {poll.community_name && <Badge tone="neutral">{poll.community_name}</Badge>}
        <span>· {poll.participant_count} participants</span>
      </div>

      <div className="mt-4 space-y-2">
        {poll.options.map((option) => {
          const percent = showBars
            ? poll.vote_count > 0
              ? Math.round((option.vote_count / poll.vote_count) * 100)
              : 0
            : 0;
          const selected = choices.includes(option.id);
          return (
            <button
              key={option.id}
              disabled={poll.status !== "open" || poll.voted}
              onClick={() => toggleChoice(option.id)}
              className={`relative w-full overflow-hidden rounded-md border px-3 py-2 text-left text-[13px] transition ${
                selected ? "border-brand bg-brand-soft text-brand" : "border-line bg-surface-muted text-ink hover:border-brand/40"
              }`}
            >
              {showBars && (
                <span
                  className="absolute inset-y-0 left-0 bg-brand/10 transition-all"
                  style={{ width: `${percent}%` }}
                />
              )}
              <span className="relative flex items-center justify-between">
                <span className="font-medium">{option.text}</span>
                {showBars && (
                  <span className="text-[12px] text-faint">
                    {option.vote_count} · {percent}%
                  </span>
                )}
              </span>
            </button>
          );
        })}
      </div>

      <div className="mt-3 flex items-center gap-2">
        {poll.status === "open" && !poll.voted && !isMine ? (
          <Button size="sm" onClick={submit} loading={voting} disabled={choices.length === 0}>
            Vote
          </Button>
        ) : null}
        {showBars ? (
          <Button variant="ghost" size="sm" onClick={() => setResults(null)}>Refresh results</Button>
        ) : (
          <Button variant="ghost" size="sm" onClick={showResults}>
            <BarChart3 className="h-4 w-4" /> Results
          </Button>
        )}
      </div>
    </div>
  );
}

function CreatePollModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (payload: {
    title: string;
    question?: string;
    options: { text: string; sort_order?: number }[];
    multiple_choice?: boolean;
    anonymous?: boolean;
    community_id?: string;
  }) => Promise<void>;
}) {
  const [communities, setCommunities] = useState<Community[]>([]);
  const [title, setTitle] = useState("");
  const [question, setQuestion] = useState("");
  const [optionTexts, setOptionTexts] = useState(["", ""]);
  const [multiple, setMultiple] = useState(false);
  const [anonymous, setAnonymous] = useState(false);
  const [communityId, setCommunityId] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    listCommunities({ limit: 500 })
      .then(setCommunities)
      .catch(() => undefined);
  }, [open]);

  async function submit() {
    if (!title.trim()) {
      setError("Title is required");
      return;
    }
    const options = optionTexts.map((text) => text.trim()).filter(Boolean);
    if (options.length < 2) {
      setError("Add at least two options");
      return;
    }
    setError(null);
    try {
      await onCreated({
        title: title.trim(),
        question: question.trim() || undefined,
        options: options.map((text, index) => ({ text, sort_order: index })),
        multiple_choice: multiple,
        anonymous,
        community_id: communityId || undefined,
      });
      setTitle("");
      setQuestion("");
      setOptionTexts(["", ""]);
      setMultiple(false);
      setAnonymous(false);
      setCommunityId("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create poll");
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="New poll"
      description="Ask your team a question."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={submit}>Create poll</Button>
        </>
      }
    >
      <div className="space-y-4">
        <Input label="Title" placeholder="e.g. Where should the offsite be?" value={title} onChange={(e) => setTitle(e.target.value)} />
        <Input label="Question (optional)" placeholder="More detail" value={question} onChange={(e) => setQuestion(e.target.value)} />
        <div className="space-y-2">
          <p className="label">Options</p>
          {optionTexts.map((text, index) => (
            <div key={index} className="flex gap-2">
              <Input
                placeholder={`Option ${index + 1}`}
                value={text}
                onChange={(e) => setOptionTexts((prev) => prev.map((t, i) => (i === index ? e.target.value : t)))}
              />
              {optionTexts.length > 2 && (
                <Button variant="ghost" size="sm" onClick={() => setOptionTexts((prev) => prev.filter((_, i) => i !== index))}>
                  Remove
                </Button>
              )}
            </div>
          ))}
          <Button variant="secondary" size="sm" onClick={() => setOptionTexts((prev) => [...prev, ""])}>
            Add option
          </Button>
        </div>
        {communities.length > 0 && (
          <Select
            label="Community (optional)"
            value={communityId}
            onChange={(e) => setCommunityId(e.target.value)}
            placeholder="Whole organization"
            options={communities.map((c) => ({ value: c.id, label: c.name }))}
          />
        )}
        <label className="flex items-center gap-2 text-[13px] text-muted">
          <input type="checkbox" checked={multiple} onChange={(e) => setMultiple(e.target.checked)} />
          Allow multiple choices
        </label>
        <label className="flex items-center gap-2 text-[13px] text-muted">
          <input type="checkbox" checked={anonymous} onChange={(e) => setAnonymous(e.target.checked)} />
          Anonymous responses
        </label>
        {error && <p className="text-[13px] text-danger">{error}</p>}
      </div>
    </Modal>
  );
}
