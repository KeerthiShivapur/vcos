"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { BookOpen, CheckCircle2, ChevronRight, Move, Pencil, Trash2 } from "lucide-react";

import {
  deleteWikiPage,
  getWikiChildren,
  getWikiPage,
  getWikiTree,
  moveWikiPage,
  publishWikiPage,
  touchPresence,
  updateWikiPage,
} from "@/lib/api";
import { roleCan, PERMISSIONS } from "@/lib/permissions";
import type { WikiPage, WikiTreeNode } from "@/types";
import { useAuth } from "@/hooks/useAuth";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { Select } from "@/components/ui/Select";
import { Badge } from "@/components/ui/Badge";
import { Avatar } from "@/components/ui/Avatar";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { KnowledgeBadge } from "@/components/knowledge/KnowledgeBadge";
import { WatchBar } from "@/components/knowledge/WatchBar";
import { CommentsPanel } from "@/components/knowledge/CommentsPanel";
import { VersionHistory } from "@/components/knowledge/VersionHistory";
import { formatDate } from "@/lib/utils";
import { toastSuccess } from "@/components/ui/Toaster";

export default function WikiDetailPage() {
  return (
    <Suspense fallback={null}>
      <DetailContent />
    </Suspense>
  );
}

function DetailContent() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const { user } = useAuth();
  const canManage = roleCan(user?.role, PERMISSIONS.KNOWLEDGE_MANAGE);

  const [page, setPage] = useState<WikiPage | null>(null);
  const [children, setChildren] = useState<WikiPage[]>([]);
  const [tree, setTree] = useState<WikiTreeNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [showMove, setShowMove] = useState(false);
  const [moveTarget, setMoveTarget] = useState("");
  const [showEdit, setShowEdit] = useState(false);
  const [editTitle, setEditTitle] = useState("");
  const [editContent, setEditContent] = useState("");
  const [showDelete, setShowDelete] = useState(false);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [pageData, childList, treeData] = await Promise.all([
        getWikiPage(id),
        getWikiChildren(id).catch(() => [] as WikiPage[]),
        getWikiTree().catch(() => [] as WikiTreeNode[]),
      ]);
      setPage(pageData);
      setChildren(childList);
      setTree(treeData);
      try {
        await touchPresence("wiki", id);
      } catch {
        /* ignore */
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load page");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function publish() {
    setBusy(true);
    try {
      setPage(await publishWikiPage(id));
      toastSuccess("Page published");
    } finally {
      setBusy(false);
    }
  }

  async function move() {
    setBusy(true);
    try {
      setPage(await moveWikiPage(id, moveTarget || null));
      toastSuccess("Page moved");
      setShowMove(false);
      await load();
    } finally {
      setBusy(false);
    }
  }

  async function saveEdit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      setPage(
        await updateWikiPage(id, {
          title: editTitle,
          content: editContent,
        })
      );
      toastSuccess("Page updated");
      setShowEdit(false);
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    try {
      await deleteWikiPage(id);
      toastSuccess("Page deleted");
      window.location.href = "/wiki";
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return <div className="flex justify-center py-24"><Spinner label="Loading page" /></div>;
  }

  if (error || !page) {
    return <ErrorState title="Wiki page not found" message={error ?? "It may have been deleted."} />;
  }

  const siblings = flatten(tree).filter((n) => n.value !== id);

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <PageHeader
        breadcrumb={`Wiki${page.parent_id ? "" : " · root"}`}
        title={page.title}
        description={page.description ?? undefined}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <KnowledgeBadge status={page.status} kind="wiki" />
            {canManage && (
              <>
                <Button size="sm" variant="ghost" onClick={() => setShowMove(true)}>
                  <Move className="h-4 w-4" /> Move
                </Button>
                <Button size="sm" variant="ghost" onClick={() => { setEditTitle(page.title); setEditContent(page.content ?? ""); setShowEdit(true); }}>
                  <Pencil className="h-4 w-4" /> Edit
                </Button>
                {page.status !== "published" && (
                  <Button size="sm" variant="secondary" onClick={publish} loading={busy}>
                    <CheckCircle2 className="h-4 w-4" /> Publish
                  </Button>
                )}
                <Button size="sm" variant="ghost" onClick={() => setShowDelete(true)}>
                  <Trash2 className="h-4 w-4 text-danger" />
                </Button>
              </>
            )}
          </div>
        }
      />

      <WatchBar kind="wiki" entityId={page.id} />

      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 rounded-lg border border-line bg-surface px-4 py-3 text-[12px] text-muted">
        {page.author_name && <span className="flex items-center gap-1.5"><Avatar name={page.author_name} size="xs" /> {page.author_name}</span>}
        <span>v{page.version}</span>
        <span>{page.view_count} views</span>
        <Badge tone="neutral">{page.space}</Badge>
        {page.parent_id && (
          <Link href={`/wiki/${page.parent_id}`} className="flex items-center gap-0.5 font-medium text-brand hover:underline">
            <ChevronRight className="h-3.5 w-3.5" /> parent
          </Link>
        )}
        <span className="ml-auto text-faint">Updated {formatDate(page.updated_at)}</span>
      </div>

      {page.ai_summary && (
        <div className="rounded-lg border border-brand/20 bg-brand-soft/40 p-4">
          <p className="text-[12px] font-semibold uppercase tracking-wide text-brand">AI summary</p>
          <p className="mt-1 text-[13px] leading-relaxed text-muted">{page.ai_summary}</p>
        </div>
      )}

      <div className="card p-6">
        {page.content ? (
          <div className="whitespace-pre-wrap text-[14px] leading-relaxed text-muted">{page.content}</div>
        ) : (
          <EmptyState icon={BookOpen} title="Empty page" description="This page has no content yet." />
        )}
      </div>

      {children.length > 0 && (
        <div className="card p-5">
          <p className="mb-3 text-[12px] font-semibold uppercase tracking-wide text-faint">
            Sub-pages ({children.length})
          </p>
          <div className="space-y-1.5">
            {children.map((child) => (
              <Link key={child.id} href={`/wiki/${child.id}`} className="flex items-center justify-between rounded-md px-2 py-1.5 text-[13px] text-ink transition-colors hover:bg-surface">
                <span className="truncate font-medium">{child.title}</span>
                <Badge tone="neutral">{child.status}</Badge>
              </Link>
            ))}
          </div>
        </div>
      )}

      <CommentsPanel kind="wiki" entityId={page.id} />
      <VersionHistory kind="wiki" entityId={page.id} />

      <Modal open={showMove} onClose={() => setShowMove(false)} title="Move page" description="Choose a new parent — leaving it empty moves it to the root.">
        <div className="space-y-4">
          <Select
            value={moveTarget}
            onChange={(e) => setMoveTarget(e.target.value)}
            placeholder="Root level"
            options={siblings}
          />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setShowMove(false)}>Cancel</Button>
            <Button onClick={move} loading={busy}>Move page</Button>
          </div>
        </div>
      </Modal>

      <Modal open={showEdit} onClose={() => setShowEdit(false)} title={`Edit — v${page.version}`}>
        <form onSubmit={saveEdit} className="space-y-4">
          <Input label="Title" value={editTitle} onChange={(e) => setEditTitle(e.target.value)} />
          <div>
            <label className="label">Content</label>
            <Textarea rows={12} value={editContent} onChange={(e) => setEditContent(e.target.value)} />
          </div>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => setShowEdit(false)}>Cancel</Button>
            <Button type="submit" loading={busy}>Save</Button>
          </div>
        </form>
      </Modal>

      <Modal open={showDelete} onClose={() => setShowDelete(false)} title="Delete page?" description="This cannot be undone.">
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setShowDelete(false)}>Cancel</Button>
          <Button variant="danger" onClick={remove} loading={busy}>Delete</Button>
        </div>
      </Modal>
    </div>
  );
}

function flatten(nodes: WikiTreeNode[]): { value: string; label: string }[] {
  return nodes.flatMap((node) => [
    { value: node.id, label: node.title },
    ...flatten(node.children ?? []),
  ]);
}
