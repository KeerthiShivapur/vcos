"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowBigUp, MessageSquare, Plus } from "lucide-react";

import {
  createForumThread,
  listForumCategories,
  listForumThreads,
} from "@/lib/api";
import { roleCan, PERMISSIONS } from "@/lib/permissions";
import type { ForumThread } from "@/types";
import { useAuth } from "@/hooks/useAuth";
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
import { timeAgo } from "@/lib/utils";

export default function ForumsPage() {
  return (
    <Suspense fallback={null}>
      <ForumsContent />
    </Suspense>
  );
}

function ForumsContent() {
  const { user } = useAuth();
  const [threads, setThreads] = useState<ForumThread[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [category, setCategory] = useState("");
  const [search, setSearch] = useState("");
  const [createOpen, setCreateOpen] = useState(false);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [list, cats] = await Promise.all([
        listForumThreads({
          category: category || undefined,
          search: search || undefined,
          limit: 200,
        }),
        listForumCategories(),
      ]);
      setThreads(list);
      setCategories(cats.map((c) => c.category));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load forums");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [category]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Forums"
        description="Ask questions, share knowledge, and discuss ideas."
        actions={
          <Button size="sm" onClick={() => setCreateOpen(true)}>
            <Plus className="h-4 w-4" /> New thread
          </Button>
        }
      />

      <div className="flex flex-wrap gap-2">
        <div className="w-56">
          <Input
            placeholder="Search threads…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && load()}
          />
        </div>
        <Select
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          placeholder="All categories"
          options={categories.map((c) => ({
            value: c,
            label: c.replace("_", " "),
          }))}
          className="w-44"
        />
        <Button variant="secondary" size="sm" onClick={load}>
          Search
        </Button>
      </div>

      {error ? (
        <ErrorState
          title="Could not load forums"
          message={error}
          onRetry={load}
        />
      ) : loading ? (
        <div className="flex justify-center py-24">
          <Spinner label="Loading forums" />
        </div>
      ) : threads.length === 0 ? (
        <EmptyState
          icon={MessageSquare}
          title="No threads yet"
          description="Start a discussion to get the conversation going."
          action={
            <Button size="sm" onClick={() => setCreateOpen(true)}>
              <Plus className="h-4 w-4" /> New thread
            </Button>
          }
        />
      ) : (
        <div className="space-y-2">
          {threads.map((thread) => (
            <Link
              key={thread.id}
              href={`/forums/${thread.id}`}
              className="block rounded-lg border border-line bg-surface p-4 transition hover:border-brand/40 hover:bg-surface-muted"
            >
              <div className="flex items-start gap-4">
                <div className="flex w-12 shrink-0 flex-col items-center rounded-md bg-brand-soft/50 py-2">
                  <ArrowBigUp className="h-4 w-4 text-brand" />
                  <span className="text-sm font-bold text-brand">
                    {thread.vote_count}
                  </span>
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="truncate text-[15px] font-semibold text-ink">
                      {thread.title}
                    </p>
                    <Badge tone="neutral">
                      {thread.category.replace("_", " ")}
                    </Badge>
                    {thread.is_pinned && <Badge tone="brand">Pinned</Badge>}
                    {thread.is_resolved && (
                      <Badge tone="success">Resolved</Badge>
                    )}
                  </div>
                  {thread.content && (
                    <p className="mt-1 line-clamp-2 text-[13px] text-muted">
                      {thread.content}
                    </p>
                  )}
                  <div className="mt-2 flex flex-wrap items-center gap-3 text-[12px] text-faint">
                    <span>{thread.author_name}</span>
                    <span>· {timeAgo(thread.created_at)}</span>
                    <span className="flex items-center gap-1">
                      <MessageSquare className="h-3.5 w-3.5" />{" "}
                      {thread.reply_count}
                    </span>
                    <span>{thread.view_count} views</span>
                    {thread.tags.length > 0 && (
                      <span className="flex gap-1">
                        {thread.tags.slice(0, 3).map((tag) => (
                          <span
                            key={tag}
                            className="rounded bg-surface-muted px-1.5 py-0.5 text-[11px]"
                          >
                            #{tag}
                          </span>
                        ))}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}

      <CreateThreadModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        categories={categories}
        onCreated={async (payload) => {
          await createForumThread(payload);
          setCreateOpen(false);
          load();
        }}
      />
    </div>
  );
}

function CreateThreadModal({
  open,
  onClose,
  categories,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  categories: string[];
  onCreated: (payload: {
    category: string;
    title: string;
    content?: string;
    tags?: string[];
  }) => Promise<void>;
}) {
  const [category, setCategory] = useState("");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [tags, setTags] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (!category) {
      setError("Pick a category");
      return;
    }
    if (!title.trim()) {
      setError("Title is required");
      return;
    }
    setError(null);
    try {
      await onCreated({
        category,
        title: title.trim(),
        content: content.trim() || undefined,
        tags: tags
          .split(",")
          .map((t) => t.trim().toLowerCase())
          .filter(Boolean),
      });
      setCategory("");
      setTitle("");
      setContent("");
      setTags("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create thread");
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="New thread"
      description="Start a discussion in the forums."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={submit}>Create thread</Button>
        </>
      }
    >
      <div className="space-y-4">
        <Select
          label="Category"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          placeholder="Pick a category"
          options={categories.map((c) => ({
            value: c,
            label: c.replace("_", " "),
          }))}
        />
        <Input
          label="Title"
          placeholder="What's your question or topic?"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
        <Textarea
          label="Content"
          placeholder="Provide more detail…"
          value={content}
          onChange={(e) => setContent(e.target.value)}
          rows={5}
        />
        <Input
          label="Tags (comma-separated)"
          placeholder="react, performance, hiring"
          value={tags}
          onChange={(e) => setTags(e.target.value)}
        />
        {error && <p className="text-[13px] text-danger">{error}</p>}
      </div>
    </Modal>
  );
}
