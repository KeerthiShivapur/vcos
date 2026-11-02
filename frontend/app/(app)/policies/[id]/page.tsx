"use client";

import { Suspense, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import {
  AlertTriangle,
  CheckCircle2,
  Gavel,
  Send,
  XCircle,
} from "lucide-react";

import {
  approvePolicy,
  deletePolicy,
  getPolicy,
  rejectPolicy,
  submitPolicy,
  touchPresence,
} from "@/lib/api";
import { roleCan, PERMISSIONS } from "@/lib/permissions";
import type { Policy } from "@/types";
import { useAuth } from "@/hooks/useAuth";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Input } from "@/components/ui/Input";
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

export default function PolicyDetailPage() {
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

  const [policy, setPolicy] = useState<Policy | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showReject, setShowReject] = useState(false);
  const [rejectNote, setRejectNote] = useState("");

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setPolicy(await getPolicy(id));
      try {
        await touchPresence("policy", id);
      } catch {
        /* ignore */
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load policy");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function run(action: "submit" | "approve" | "reject") {
    setBusy(true);
    try {
      if (action === "submit") setPolicy(await submitPolicy(id));
      if (action === "approve") setPolicy(await approvePolicy(id));
      if (action === "reject") {
        setPolicy(await rejectPolicy(id, rejectNote || undefined));
        setShowReject(false);
        setRejectNote("");
      }
      toastSuccess("Policy updated");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    try {
      await deletePolicy(id);
      toastSuccess("Policy deleted");
      window.location.href = "/policies";
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return (
      <div className="flex justify-center py-24">
        <Spinner label="Loading policy" />
      </div>
    );
  }

  if (error || !policy) {
    return (
      <ErrorState
        title="Policy not found"
        message={error ?? "It may have been deleted."}
      />
    );
  }

  const inReview = policy.status === "in_review";

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <PageHeader
        breadcrumb="Policies"
        title={policy.title}
        description={policy.description ?? undefined}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <KnowledgeBadge status={policy.status} kind="policy" />
            {policy.review_overdue && (
              <Badge tone="warning">
                <AlertTriangle className="mr-1 inline h-3 w-3" /> review overdue
              </Badge>
            )}
            {canManage && (
              <>
                {policy.status === "draft" && (
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => run("submit")}
                    loading={busy}
                  >
                    <Send className="h-4 w-4" /> Submit for review
                  </Button>
                )}
              </>
            )}
            {canApprove && inReview && (
              <>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setShowReject(true)}
                >
                  <XCircle className="h-4 w-4" /> Reject
                </Button>
                <Button size="sm" onClick={() => run("approve")} loading={busy}>
                  <CheckCircle2 className="h-4 w-4" /> Approve
                </Button>
              </>
            )}
            {canManage && (
              <Button size="sm" variant="ghost" onClick={remove} loading={busy}>
                Delete
              </Button>
            )}
          </div>
        }
      />

      <WatchBar kind="policy" entityId={policy.id} />

      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 rounded-lg border border-line bg-surface px-4 py-3 text-[12px] text-muted">
        {policy.owner_name && (
          <span className="flex items-center gap-1.5">
            <Avatar name={policy.owner_name} size="xs" /> {policy.owner_name}
          </span>
        )}
        {policy.approver_name && <span>Approver: {policy.approver_name}</span>}
        <span>v{policy.version}</span>
        <span>{policy.view_count} views</span>
        <Badge tone="neutral">{policy.category}</Badge>
        {policy.effective_date && (
          <span>Effective {formatDate(policy.effective_date)}</span>
        )}
        {policy.review_date && (
          <span
            className={
              policy.review_overdue ? "font-semibold text-warning" : ""
            }
          >
            Review by {formatDate(policy.review_date)}
          </span>
        )}
        <span className="ml-auto text-faint">
          Updated {formatDate(policy.updated_at)}
        </span>
      </div>

      {policy.approval_note && (
        <div className="rounded-lg border border-line bg-surface px-4 py-3 text-[13px] text-muted">
          <span className="font-semibold text-ink">Last decision note:</span> “
          {policy.approval_note}”
        </div>
      )}

      {policy.ai_summary && (
        <div className="rounded-lg border border-brand/20 bg-brand-soft/40 p-4">
          <p className="text-[12px] font-semibold uppercase tracking-wide text-brand">
            AI summary
          </p>
          <p className="mt-1 text-[13px] leading-relaxed text-muted">
            {policy.ai_summary}
          </p>
        </div>
      )}

      <div className="card p-6">
        {policy.content ? (
          <div className="whitespace-pre-wrap text-[14px] leading-relaxed text-muted">
            {policy.content}
          </div>
        ) : (
          <EmptyState
            icon={Gavel}
            title="Empty policy"
            description="This policy has no content yet."
          />
        )}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <CommentsPanel kind="policy" entityId={policy.id} />
        <VersionHistory kind="policy" entityId={policy.id} />
      </div>

      <Modal
        open={showReject}
        onClose={() => setShowReject(false)}
        title="Reject policy"
        description="Send it back to the author with feedback."
      >
        <div className="space-y-4">
          <Input
            label="Note (required)"
            placeholder="e.g. Needs finance input before approval"
            value={rejectNote}
            onChange={(e) => setRejectNote(e.target.value)}
          />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setShowReject(false)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              onClick={() => run("reject")}
              loading={busy}
              disabled={!rejectNote.trim()}
            >
              Reject policy
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
