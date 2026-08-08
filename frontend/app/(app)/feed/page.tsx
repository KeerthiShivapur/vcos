"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  Bookmark,
  MessageCircle,
  Newspaper,
  Pin,
  Plus,
  Send,
  Smile,
} from "lucide-react";

import {
  addPostComment,
  createPost,
  deletePost,
  getMyEmployee,
  listCommunities,
  listFeed,
  listPostComments,
  reactToComment,
  reactToPost,
  togglePostBookmark,
  togglePostPin,
} from "@/lib/api";
import { roleCan, PERMISSIONS } from "@/lib/permissions";
import type { Community, Post, PostComment } from "@/types";
import { POST_REACTIONS } from "@/types";
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

export default function FeedPage() {
  return (
    <Suspense fallback={null}>
      <FeedContent />
    </Suspense>
  );
}

function FeedContent() {
  const searchParams = useSearchParams();
  const [communities, setCommunities] = useState<Community[]>([]);
  const [communityId, setCommunityId] = useState(searchParams.get("community_id") ?? "");
  const [posts, setPosts] = useState<Post[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [myEmployeeId, setMyEmployeeId] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [feed, all, me] = await Promise.all([
        listFeed({ community_id: communityId || undefined, limit: 100 }),
        listCommunities({ limit: 500 }),
        getMyEmployee().catch(() => null),
      ]);
      setPosts(feed);
      setCommunities(all);
      setMyEmployeeId(me?.id ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load feed");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [communityId]);

  async function handleReaction(post: Post, emoji: string) {
    try {
      const result = await reactToPost(post.id, emoji);
      await load();
      if (!result.reacted) return;
    } catch {
      /* ignore */
    }
  }

  async function handleBookmark(post: Post) {
    try {
      await togglePostBookmark(post.id);
      await load();
    } catch {
      /* ignore */
    }
  }

  async function handlePin(post: Post) {
    try {
      await togglePostPin(post.id, !post.pinned);
      await load();
    } catch {
      /* ignore */
    }
  }

  async function handleDelete(post: Post) {
    try {
      await deletePost(post.id);
      setPosts((prev) => prev.filter((p) => p.id !== post.id));
    } catch {
      /* ignore */
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Feed"
        description="What your teams are sharing."
        actions={
          <Button size="sm" onClick={() => setCreateOpen(true)}>
            <Plus className="h-4 w-4" /> New post
          </Button>
        }
      />

      <div className="flex flex-wrap items-center gap-2">
        <div className="w-64">
          <Select
            value={communityId}
            onChange={(e) => setCommunityId(e.target.value)}
            placeholder="All communities"
            options={communities.map((c) => ({ value: c.id, label: c.name }))}
          />
        </div>
      </div>

      {error ? (
        <ErrorState title="Could not load feed" message={error} onRetry={load} />
      ) : loading ? (
        <div className="flex justify-center py-24"><Spinner label="Loading feed" /></div>
      ) : posts.length === 0 ? (
        <EmptyState
          icon={Newspaper}
          title="No posts yet"
          description="Share an update, question, or idea with your communities."
          action={<Button size="sm" onClick={() => setCreateOpen(true)}><Plus className="h-4 w-4" /> New post</Button>}
        />
      ) : (
        <div className="mx-auto max-w-2xl space-y-4">
          {posts.map((post) => (
            <PostCard
              key={post.id}
              post={post}
              isMine={post.author_id === myEmployeeId}
              onReact={handleReaction}
              onBookmark={handleBookmark}
              onPin={handlePin}
              onDelete={handleDelete}
            />
          ))}
        </div>
      )}

      <CreatePostModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        communities={communities}
        defaultCommunityId={communityId}
        onCreated={async (payload) => {
          await createPost(payload.community_id, {
            title: payload.title || undefined,
            content: payload.content || undefined,
            visibility: payload.visibility || undefined,
          });
          setCreateOpen(false);
          load();
        }}
      />
    </div>
  );
}

function PostCard({
  post,
  isMine,
  onReact,
  onBookmark,
  onPin,
  onDelete,
}: {
  post: Post;
  isMine: boolean;
  onReact: (post: Post, emoji: string) => void;
  onBookmark: (post: Post) => void;
  onPin: (post: Post) => void;
  onDelete: (post: Post) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [comments, setComments] = useState<PostComment[]>([]);
  const [commentText, setCommentText] = useState("");

  async function loadComments() {
    try {
      setComments(await listPostComments(post.id));
    } catch {
      /* ignore */
    }
  }

  async function submitComment() {
    if (!commentText.trim()) return;
    try {
      await addPostComment(post.id, commentText.trim());
      setCommentText("");
      await loadComments();
    } catch {
      /* ignore */
    }
  }

  async function reactComment(comment: PostComment, emoji: string) {
    try {
      await reactToComment(post.id, comment.id, emoji);
      await loadComments();
    } catch {
      /* ignore */
    }
  }

  return (
    <article className="rounded-lg border border-line bg-surface p-5">
      <div className="flex items-start gap-3">
        <Avatar name={post.author_name} size="md" />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-[13px] font-semibold text-ink">{post.author_name}</p>
            <Badge tone="neutral">{post.community_name}</Badge>
            {post.pinned && <Badge tone="brand">Pinned</Badge>}
          </div>
          <p className="text-[12px] text-faint">{timeAgo(post.created_at)}</p>
        </div>
        <div className="flex items-center gap-1">
          {isMine && (
            <>
              <Button variant="ghost" size="sm" onClick={() => onPin(post)}>
                <Pin className={`h-4 w-4 ${post.pinned ? "fill-brand text-brand" : ""}`} />
              </Button>
              <Button variant="ghost" size="sm" onClick={() => onDelete(post)}>Delete</Button>
            </>
          )}
        </div>
      </div>

      {post.title && <h3 className="mt-3 text-[15px] font-semibold text-ink">{post.title}</h3>}
      {post.content && <p className="mt-1.5 whitespace-pre-wrap text-[13px] leading-relaxed text-muted">{post.content}</p>}

      <div className="mt-3 flex flex-wrap items-center gap-3 border-t border-line pt-3 text-[12px] text-faint">
        <ReactPicker
          emoji={post.my_reaction}
          onPick={(emoji) => onReact(post, emoji)}
          count={post.reaction_count}
        />
        <button className="flex items-center gap-1 hover:text-ink" onClick={() => { setExpanded(!expanded); if (!expanded) loadComments(); }}>
          <MessageCircle className="h-4 w-4" /> {post.comment_count}
        </button>
        <button className="flex items-center gap-1 hover:text-ink" onClick={() => onBookmark(post)}>
          <Bookmark className={`h-4 w-4 ${post.is_bookmarked ? "fill-brand text-brand" : ""}`} /> {post.bookmark_count}
        </button>
      </div>

      {expanded && (
        <div className="mt-3 space-y-3">
          <div className="flex gap-2">
            <Input
              placeholder="Write a comment…"
              value={commentText}
              onChange={(e) => setCommentText(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && submitComment()}
            />
            <Button variant="secondary" size="sm" onClick={submitComment}><Send className="h-4 w-4" /></Button>
          </div>
          {comments.map((comment) => (
            <div key={comment.id} className="rounded-md bg-surface-muted p-3">
              <div className="flex items-center justify-between gap-2">
                <p className="text-[12px] font-semibold text-ink">{comment.author_name}</p>
                <div className="flex items-center gap-2">
                  {comment.is_resolution && <Badge tone="success">Resolution</Badge>}
                  <ReactPicker
                    emoji={comment.my_reaction}
                    onPick={(emoji) => reactComment(comment, emoji)}
                    count={comment.reaction_count}
                  />
                </div>
              </div>
              <p className="mt-1 whitespace-pre-wrap text-[13px] text-muted">{comment.content}</p>
            </div>
          ))}
        </div>
      )}
    </article>
  );
}

function ReactPicker({
  emoji,
  onPick,
  count,
}: {
  emoji: string | null;
  onPick: (emoji: string) => void;
  count: number;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative">
      <button
        className="flex items-center gap-1 hover:text-ink"
        onClick={() => setOpen(!open)}
        title={emoji ? `Reacted: ${emoji}` : "Add reaction"}
      >
        <Smile className={`h-4 w-4 ${emoji ? "text-brand" : ""}`} />
        <span>{count > 0 ? count : ""}</span>
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute bottom-full left-0 z-20 mb-2 flex gap-1 rounded-lg border border-line bg-elevated p-1.5 shadow-popover">
            {POST_REACTIONS.map((reaction) => (
              <button
                key={reaction}
                className={`rounded-md px-2 py-1 text-[11px] font-medium capitalize hover:bg-brand-soft ${emoji === reaction ? "bg-brand-soft text-brand" : "text-muted"}`}
                onClick={() => { onPick(reaction); setOpen(false); }}
              >
                {reaction.replace("_", " ")}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function CreatePostModal({
  open,
  onClose,
  communities,
  defaultCommunityId,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  communities: Community[];
  defaultCommunityId: string;
  onCreated: (payload: { community_id: string; title?: string; content?: string; visibility?: string }) => Promise<void>;
}) {
  const [communityId, setCommunityId] = useState(defaultCommunityId);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [visibility, setVisibility] = useState("members");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (defaultCommunityId && !communityId) setCommunityId(defaultCommunityId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [defaultCommunityId]);

  async function submit() {
    if (!communityId) {
      setError("Pick a community");
      return;
    }
    if (!title.trim() && !content.trim()) {
      setError("Add a title or some content");
      return;
    }
    setError(null);
    try {
      await onCreated({
        community_id: communityId,
        title: title.trim() || undefined,
        content: content.trim() || undefined,
        visibility,
      });
      setTitle("");
      setContent("");
      setVisibility("members");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create post");
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="New post"
      description="Share an update with your community."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={submit}>Post</Button>
        </>
      }
    >
      <div className="space-y-4">
        <Select
          label="Community"
          value={communityId}
          onChange={(e) => setCommunityId(e.target.value)}
          placeholder="Select a community"
          options={communities.map((c) => ({ value: c.id, label: c.name }))}
        />
        <Input label="Title (optional)" placeholder="A short headline" value={title} onChange={(e) => setTitle(e.target.value)} />
        <Textarea label="Content" placeholder="What do you want to share?" value={content} onChange={(e) => setContent(e.target.value)} rows={5} />
        <Select
          label="Visibility"
          value={visibility}
          onChange={(e) => setVisibility(e.target.value)}
          options={[
            { value: "members", label: "Community members" },
            { value: "organization", label: "Entire organization" },
          ]}
        />
        {error && <p className="text-[13px] text-danger">{error}</p>}
      </div>
    </Modal>
  );
}
