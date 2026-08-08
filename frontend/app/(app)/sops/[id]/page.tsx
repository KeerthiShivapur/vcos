"use client";

import { Suspense, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { CheckCircle2, CheckSquare, ListChecks, Trash2 } from "lucide-react";

import {
  deleteSop,
  getSop,
  publishSop,
  touchPresence,
} from "@/lib/api";
import { roleCan, PERMISSIONS } from "@/lib/permissions";
import type { SOP } from "@/types";
import { useAuth } from "@/hooks/useAuth";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
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

export default function SopDetailPage() {
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

  const [sop, setSop] = useState<SOP | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showDelete, setShowDelete] = useState(false);
  const [checked, setChecked] = useState<Record<string, boolean>>({});

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setSop(await getSop(id));
      try {
        await touchPresence("sop", id);
      } catch {
        /* ignore */
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load SOP");
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
      setSop(await publishSop(id));
      toastSuccess("SOP published");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    try {
      await deleteSop(id);
      toastSuccess("SOP deleted");
      window.location.href = "/sops";
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return <div className="flex justify-center py-24"><Spinner label="Loading SOP" /></div>;
  }

  if (error || !sop) {
    return <ErrorState title="SOP not found" message={error ?? "It may have been deleted."} />;
  }

  const steps = sop.steps ?? [];
  const doneCount = steps.filter((step) => checked[step.id]).length;

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <PageHeader
        breadcrumb="SOPs"
        title={sop.title}
        description={sop.description ?? undefined}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <KnowledgeBadge status={sop.status} kind="sop" />
            {canManage && (
              <>
                {sop.status !== "published" && (
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

      <WatchBar kind="sop" entityId={sop.id} />

      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 rounded-lg border border-line bg-surface px-4 py-3 text-[12px] text-muted">
        {sop.owner_name && <span className="flex items-center gap-1.5"><Avatar name={sop.owner_name} size="xs" /> {sop.owner_name}</span>}
        <span>v{sop.version}</span>
        <span>{sop.view_count} views</span>
        <span>{steps.length} step{steps.length === 1 ? "" : "s"}</span>
        {sop.category && <Badge tone="neutral">{sop.category}</Badge>}
        <span className="ml-auto text-faint">Updated {formatDate(sop.updated_at)}</span>
      </div>

      <div className="card p-6">
        <div className="mb-4 flex items-center justify-between">
          <p className="flex items-center gap-2 text-[13px] font-semibold text-ink">
            <ListChecks className="h-4 w-4 text-brand" /> Procedure
          </p>
          {steps.length > 0 && (
            <span className="text-[12px] text-faint">
              {doneCount} / {steps.length} done
            </span>
          )}
        </div>

        {steps.length === 0 ? (
          <EmptyState icon={ListChecks} title="No steps yet" description="This SOP has no procedure steps." />
        ) : (
          <div className="space-y-2">
            {steps.map((step) => (
              <div key={step.id} className="flex items-start gap-3 rounded-lg border border-line px-4 py-3">
                <button
                  type="button"
                  onClick={() => setChecked((prev) => ({ ...prev, [step.id]: !prev[step.id] }))}
                  className="mt-0.5 shrink-0"
                  aria-label="Toggle step"
                >
                  <CheckSquare
                    className={`h-5 w-5 ${checked[step.id] ? "text-brand" : "text-faint"}`}
                    fill={checked[step.id] ? "currentColor" : "none"}
                  />
                </button>
                <div className="min-w-0 flex-1">
                  <p className={`text-[14px] font-medium ${checked[step.id] ? "text-faint line-through" : "text-ink"}`}>
                    {step.sort_order + 1}. {step.title}
                  </p>
                  {step.instruction && <p className="mt-0.5 text-[13px] text-muted">{step.instruction}</p>}
                </div>
                {step.is_checklist && <Badge tone="neutral">checklist</Badge>}
              </div>
            ))}
          </div>
        )}
      </div>

      {sop.content && (
        <div className="card p-6">
          <p className="mb-2 text-[13px] font-semibold text-ink">Overview</p>
          <div className="whitespace-pre-wrap text-[14px] leading-relaxed text-muted">{sop.content}</div>
        </div>
      )}

      <CommentsPanel kind="sop" entityId={sop.id} />
      <VersionHistory kind="sop" entityId={sop.id} />

      <Modal open={showDelete} onClose={() => setShowDelete(false)} title="Delete SOP?" description="This cannot be undone.">
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setShowDelete(false)}>Cancel</Button>
          <Button variant="danger" onClick={remove} loading={busy}>Delete</Button>
        </div>
      </Modal>
    </div>
  );
}
