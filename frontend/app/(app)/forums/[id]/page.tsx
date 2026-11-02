"use client";

import { Suspense, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowBigDown, ArrowBigUp, ArrowLeft, Check, Send } from "lucide-react";

import {
  acceptThreadReply,
  addForumReply,
  deleteForumReply,
  getForumThread,
  getMyEmployee,
  listForumReplies,
  recordThreadView,
  voteForumReply,
  voteThread,
} from "@/lib/api";
import type { ForumReply, ForumThread } from "@/types";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { Textarea } from "@/components/ui/Textarea";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { Badge } from "@/components/ui/Badge";
import { Avatar } from "@/components/ui/Avatar";
import { timeAgo } from "@/lib/utils";

export default function ForumThreadPage() {
  return (
    <Suspense fallback={null}>
      <ForumThreadContent />
    </Suspense>
  );
}

function ForumThreadContent() {
  const params = useParams<{ id: string }>();
  const router = useRouter();

  const [thread, setThread] = useState<ForumThread | null>(null);
  const [replies, setReplies] = useState<ForumReply[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [replyText, setReplyText] = useState("");
  const [sending, setSending] = useState(false);
  const [myEmployeeId, setMyEmployeeId] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [threadData, repliesData, me] = await Promise.all([
        getForumThread(params.id),
        listForumReplies(params.id),
        getMyEmployee().catch(() => null),
      ]);
      setThread(threadData);
      setReplies(repliesData);
      setMyEmployeeId(me?.id ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load thread");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    recordThreadView(params.id).catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.id]);

  async function submitReply() {
    if (!replyText.trim()) return;
    setSending(true);
    try {
      await addForumReply(params.id, replyText.trim());
      setReplyText("");
      await load();
    } catch {
      /* ignore */
    } finally {
      setSending(false);
    }
  }

  async function vote(onThread: ForumThread | null, value: number) {
    if (onThread) {
      try {
        const result = await voteThread(onThread.id, value);
        setThread((prev) =>
          prev
            ? { ...prev, my_vote: result.voted, vote_count: result.vote_count }
            : prev,
        );
      } catch {
        /* ignore */
      }
    }
  }

  async function voteReply(reply: ForumReply, value: number) {
    try {
      const result = await voteForumReply(reply.thread_id, reply.id, value);
      setReplies((prev) =>
        prev.map((r) =>
          r.id === reply.id
            ? { ...r, my_vote: result.voted, vote_count: result.vote_count }
            : r,
        ),
      );
    } catch {
      /* ignore */
    }
  }

  async function accept(reply?: ForumReply) {
    try {
      const result = await acceptThreadReply(params.id, reply?.id);
      setThread((prev) =>
        prev
          ? {
              ...prev,
              accepted_reply_id: result.accepted_reply_id,
              is_resolved: result.is_resolved,
            }
          : prev,
      );
      await load();
    } catch {
      /* ignore */
    }
  }

  async function removeReply(reply: ForumReply) {
    try {
      await deleteForumReply(reply.thread_id, reply.id);
      await load();
    } catch {
      /* ignore */
    }
  }

  if (loading) {
    return (
      <div className="flex justify-center py-24">
        <Spinner label="Loading thread" />
      </div>
    );
  }

  if (error || !thread) {
    return (
      <ErrorState
        title="Could not load thread"
        message={error ?? "Not found"}
        onRetry={load}
      />
    );
  }

  const iAmAuthor = thread.author_id === myEmployeeId;
  const acceptedReply = thread.accepted_reply_id
    ? replies.find((r) => r.id === thread.accepted_reply_id)
    : null;

  return (
    <div className="space-y-6">
      <Button variant="ghost" size="sm" onClick={() => router.push("/forums")}>
        <ArrowLeft className="h-4 w-4" /> All forums
      </Button>

      <PageHeader
        title={thread.title}
        description={thread.content ?? undefined}
        breadcrumb={thread.category.replace("_", " ")}
      />

      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="neutral">{thread.category.replace("_", " ")}</Badge>
        {thread.is_pinned && <Badge tone="brand">Pinned</Badge>}
        <Badge
          tone={
            thread.status === "open"
              ? "success"
              : thread.status === "resolved"
                ? "brand"
                : "neutral"
          }
        >
          {thread.status}
        </Badge>
        {thread.tags.map((tag) => (
          <span
            key={tag}
            className="rounded bg-surface-muted px-1.5 py-0.5 text-[11px] text-muted"
          >
            #{tag}
          </span>
        ))}
      </div>

      <div className="rounded-lg border border-line bg-surface p-5">
        <div className="flex items-start gap-4">
          <div className="flex flex-col items-center gap-0.5">
            <Button variant="ghost" size="sm" onClick={() => vote(thread, 1)}>
              <ArrowBigUp
                className={`h-5 w-5 ${thread.my_vote === 1 ? "fill-brand text-brand" : ""}`}
              />
            </Button>
            <span className="text-sm font-bold text-ink">
              {thread.vote_count}
            </span>
            <Button variant="ghost" size="sm" onClick={() => vote(thread, -1)}>
              <ArrowBigDown
                className={`h-5 w-5 ${thread.my_vote === -1 ? "fill-brand text-brand" : ""}`}
              />
            </Button>
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <Avatar name={thread.author_name} size="sm" />
              <span className="text-[13px] font-semibold text-ink">
                {thread.author_name}
              </span>
              <span className="text-[12px] text-faint">
                {timeAgo(thread.created_at)}
              </span>
              <span className="text-[12px] text-faint">
                · {thread.view_count} views
              </span>
            </div>
            <p className="mt-3 whitespace-pre-wrap text-[14px] leading-relaxed text-muted">
              {thread.content}
            </p>
          </div>
        </div>
      </div>

      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-ink">
          Replies ({replies.length})
        </h3>
        {replies.length === 0 ? (
          <div className="rounded-lg border border-dashed border-line p-8 text-center text-[13px] text-faint">
            No replies yet — be the first to respond.
          </div>
        ) : (
          replies.map((reply) => (
            <div
              key={reply.id}
              className={`rounded-lg border bg-surface p-4 ${
                reply.id === thread.accepted_reply_id
                  ? "border-success/50 bg-success/5"
                  : "border-line"
              }`}
            >
              <div className="flex items-start gap-4">
                <div className="flex flex-col items-center gap-0.5">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => voteReply(reply, 1)}
                  >
                    <ArrowBigUp
                      className={`h-4 w-4 ${reply.my_vote === 1 ? "fill-brand text-brand" : ""}`}
                    />
                  </Button>
                  <span className="text-[13px] font-bold text-ink">
                    {reply.vote_count}
                  </span>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => voteReply(reply, -1)}
                  >
                    <ArrowBigDown
                      className={`h-4 w-4 ${reply.my_vote === -1 ? "fill-brand text-brand" : ""}`}
                    />
                  </Button>
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <Avatar name={reply.author_name} size="sm" />
                    <span className="text-[13px] font-semibold text-ink">
                      {reply.author_name}
                    </span>
                    <span className="text-[12px] text-faint">
                      {timeAgo(reply.created_at)}
                    </span>
                    {reply.is_accepted && (
                      <Badge tone="success">
                        <Check className="h-3 w-3" /> Accepted
                      </Badge>
                    )}
                    <div className="ml-auto flex gap-2">
                      {iAmAuthor && !reply.is_accepted && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => accept(reply)}
                        >
                          Accept
                        </Button>
                      )}
                      {reply.author_id === myEmployeeId && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => removeReply(reply)}
                        >
                          Delete
                        </Button>
                      )}
                    </div>
                  </div>
                  <p className="mt-2 whitespace-pre-wrap text-[13px] leading-relaxed text-muted">
                    {reply.content}
                  </p>
                </div>
              </div>
            </div>
          ))
        )}

        {acceptedReply && iAmAuthor && (
          <Button variant="ghost" size="sm" onClick={() => accept()}>
            Un-accept answer
          </Button>
        )}
      </div>

      <div className="rounded-lg border border-line bg-surface p-4">
        <Textarea
          placeholder="Write a reply…"
          value={replyText}
          onChange={(e) => setReplyText(e.target.value)}
          rows={3}
        />
        <div className="mt-2 flex justify-end">
          <Button size="sm" onClick={submitReply} loading={sending}>
            <Send className="h-4 w-4" /> Reply
          </Button>
        </div>
      </div>
    </div>
  );
}
