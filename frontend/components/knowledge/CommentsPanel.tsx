"use client";

import { useEffect, useState } from "react";
import { MessageSquare, Send } from "lucide-react";

import {
  addKnowledgeComment,
  deleteKnowledgeComment,
  listKnowledgeComments,
} from "@/lib/api";
import type { KnowledgeComment } from "@/types";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Spinner } from "@/components/ui/Spinner";
import { Avatar } from "@/components/ui/Avatar";
import { formatDateTime } from "@/lib/utils";
import { toastSuccess } from "@/components/ui/Toaster";

export function CommentsPanel({ kind, entityId }: { kind: string; entityId: string }) {
  const [comments, setComments] = useState<KnowledgeComment[]>([]);
  const [loading, setLoading] = useState(true);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);

  async function load() {
    setLoading(true);
    try {
      setComments(await listKnowledgeComments(kind, entityId));
    } catch {
      setComments([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kind, entityId]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const content = draft.trim();
    if (!content || sending) return;
    setSending(true);
    try {
      const created = await addKnowledgeComment(kind, entityId, content);
      setComments((prev) => [...prev, created]);
      setDraft("");
      toastSuccess("Comment added");
    } catch {
      /* keep draft on failure */
    } finally {
      setSending(false);
    }
  }

  async function remove(commentId: string) {
    try {
      await deleteKnowledgeComment(kind, entityId, commentId);
      setComments((prev) => prev.filter((c) => c.id !== commentId));
    } catch {
      /* ignore */
    }
  }

  return (
    <Card title="Comments" subtitle="Discuss and annotate this item" className="mt-6">
      <form onSubmit={submit} className="flex items-start gap-2">
        <input
          className="input flex-1 py-2.5 text-sm"
          placeholder="Add a comment — use @Name to notify someone"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
        />
        <Button type="submit" size="sm" loading={sending} disabled={!draft.trim()}>
          <Send className="h-4 w-4" />
        </Button>
      </form>

      <div className="mt-4 space-y-3">
        {loading ? (
          <div className="flex justify-center py-6"><Spinner label="Loading comments" /></div>
        ) : comments.length === 0 ? (
          <EmptyState icon={MessageSquare} title="No comments yet" description="Start the conversation." />
        ) : (
          comments.map((comment) => (
            <div key={comment.id} className="flex gap-3">
              <Avatar name={comment.author_name ?? "?"} size="md" />
              <div className="min-w-0 flex-1 rounded-lg border border-line bg-canvas px-3 py-2">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-[13px] font-semibold text-ink">{comment.author_name ?? "Unknown"}</p>
                  <div className="flex items-center gap-3">
                    <span className="text-[11px] text-faint">{formatDateTime(comment.created_at)}</span>
                    <button
                      type="button"
                      onClick={() => remove(comment.id)}
                      className="text-[11px] text-faint hover:text-danger"
                    >
                      Delete
                    </button>
                  </div>
                </div>
                <p className="mt-1 whitespace-pre-wrap text-[13px] leading-relaxed text-muted">{comment.content}</p>
              </div>
            </div>
          ))
        )}
      </div>
    </Card>
  );
}
