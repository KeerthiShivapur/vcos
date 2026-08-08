"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  Archive,
  CheckCircle2,
  Edit3,
  FileText,
  Pencil,
  Send,
  Trash2,
} from "lucide-react";

import {
  approveDocument,
  archiveDocument,
  deleteDocument,
  getDocument,
  publishDocument,
  submitDocument,
  touchPresence,
  updateDocument,
} from "@/lib/api";
import { roleCan, PERMISSIONS } from "@/lib/permissions";
import type { Document } from "@/types";
import { useAuth } from "@/hooks/useAuth";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { Badge } from "@/components/ui/Badge";
import { Avatar } from "@/components/ui/Avatar";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { KnowledgeBadge } from "@/components/knowledge/KnowledgeBadge";
import { WatchBar } from "@/components/knowledge/WatchBar";
import { CommentsPanel } from "@/components/knowledge/CommentsPanel";
import { VersionHistory } from "@/components/knowledge/VersionHistory";
import { formatDate, formatDateTime } from "@/lib/utils";
import { toastSuccess } from "@/components/ui/Toaster";

export default function DocumentDetailPage() {
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
  const canApprove = roleCan(user?.role, PERMISSIONS.KNOWLEDGE_APPROVE);

  const [doc, setDoc] = useState<Document | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [showEdit, setShowEdit] = useState(false);
  const [showDelete, setShowDelete] = useState(false);
  const [editContent, setEditContent] = useState("");
  const [editNote, setEditNote] = useState("");

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setDoc(await getDocument(id));
      try {
        await touchPresence("document", id);
      } catch {
        /* ignore */
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load document");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function run(action: "publish" | "archive" | "submit" | "approve") {
    setBusy(true);
    try {
      if (action === "publish") setDoc(await publishDocument(id));
      if (action === "archive") setDoc(await archiveDocument(id));
      if (action === "submit") setDoc(await submitDocument(id));
      if (action === "approve") setDoc(await approveDocument(id));
      toastSuccess("Document updated");
    } finally {
      setBusy(false);
    }
  }

  async function saveEdit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      setDoc(
        await updateDocument(id, {
          content: editContent,
          change_note: editNote || undefined,
        })
      );
      toastSuccess("Document updated");
      setShowEdit(false);
      setEditNote("");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    try {
      await deleteDocument(id);
      toastSuccess("Document deleted");
      window.location.href = "/documents";
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return <div className="flex justify-center py-24"><Spinner label="Loading document" /></div>;
  }

  if (error || !doc) {
    return <ErrorState title="Document not found" message={error ?? "It may have been deleted."} />;
  }

  const inReview = doc.status === "in_review";

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <PageHeader
        breadcrumb="Documents"
        title={doc.title}
        description={doc.description ?? undefined}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <KnowledgeBadge status={doc.status} kind="document" />
            {canManage && (
              <>
                <Button size="sm" variant="ghost" onClick={() => { setEditContent(doc.content ?? ""); setShowEdit(true); }}>
                  <Pencil className="h-4 w-4" /> Edit
                </Button>
                {doc.status === "draft" && (
                  <Button size="sm" variant="secondary" onClick={() => run("submit")} loading={busy}>
                    <Send className="h-4 w-4" /> Submit for review
                  </Button>
                )}
                {(doc.status === "draft" || inReview) && (
                  <Button size="sm" variant="secondary" onClick={() => run("publish")} loading={busy}>
                    <CheckCircle2 className="h-4 w-4" /> Publish
                  </Button>
                )}
                {doc.status !== "archived" && (
                  <Button size="sm" variant="ghost" onClick={() => run("archive")} loading={busy}>
                    <Archive className="h-4 w-4" />
                  </Button>
                )}
                <Button size="sm" variant="ghost" onClick={() => setShowDelete(true)}>
                  <Trash2 className="h-4 w-4 text-danger" />
                </Button>
              </>
            )}
            {canApprove && inReview && (
              <Button size="sm" onClick={() => run("approve")} loading={busy}>
                <CheckCircle2 className="h-4 w-4" /> Approve
              </Button>
            )}
          </div>
        }
      />

      <WatchBar kind="document" entityId={doc.id} />

      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 rounded-lg border border-line bg-surface px-4 py-3 text-[12px] text-muted">
        {doc.author_name && (
          <span className="flex items-center gap-1.5"><Avatar name={doc.author_name} size="xs" /> {doc.author_name}</span>
        )}
        <span>v{doc.version}</span>
        <span>{doc.view_count} views</span>
        {doc.category && <Badge tone="neutral">{doc.category}</Badge>}
        {doc.project_name && <Link href={`/projects/${doc.project_id}`} className="font-medium text-brand hover:underline">{doc.project_name}</Link>}
        <span className="ml-auto text-faint">Updated {formatDate(doc.updated_at)}</span>
      </div>

      {doc.tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {doc.tags.map((tag) => (
            <span key={tag} className="rounded-md bg-canvas px-2 py-0.5 text-[11px] text-muted">#{tag}</span>
          ))}
        </div>
      )}

      {doc.ai_summary && (
        <div className="rounded-lg border border-brand/20 bg-brand-soft/40 p-4">
          <p className="text-[12px] font-semibold uppercase tracking-wide text-brand">AI summary</p>
          <p className="mt-1 text-[13px] leading-relaxed text-muted">{doc.ai_summary}</p>
        </div>
      )}

      <div className="card p-6">
        {doc.content ? (
          <div className="whitespace-pre-wrap text-[14px] leading-relaxed text-muted">{doc.content}</div>
        ) : (
          <EmptyState icon={FileText} title="Empty document" description="This document has no content yet." />
        )}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <div>
          <CommentsPanel kind="document" entityId={doc.id} />
        </div>
        <div>
          <VersionHistory kind="document" entityId={doc.id} />
        </div>
      </div>

      <Modal open={showEdit} onClose={() => setShowEdit(false)} title={`Edit — v${doc.version}`} description="A new version will be saved." size="lg">
        <form onSubmit={saveEdit} className="space-y-4">
          <Input label="Change note" name="change_note" placeholder="What changed?" value={editNote} onChange={(e) => setEditNote(e.target.value)} />
          <div>
            <label className="label">Content</label>
            <Textarea rows={14} value={editContent} onChange={(e) => setEditContent(e.target.value)} />
          </div>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => setShowEdit(false)}>Cancel</Button>
            <Button type="submit" loading={busy}>Save version</Button>
          </div>
        </form>
      </Modal>

      <Modal open={showDelete} onClose={() => setShowDelete(false)} title="Delete document?" description="This cannot be undone.">
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setShowDelete(false)}>Cancel</Button>
          <Button variant="danger" onClick={remove} loading={busy}>Delete</Button>
        </div>
      </Modal>
    </div>
  );
}
