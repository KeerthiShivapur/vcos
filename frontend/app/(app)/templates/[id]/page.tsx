"use client";

import { Suspense, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { CheckCircle2, Copy, Stamp, Trash2 } from "lucide-react";

import {
  deleteTemplate,
  getTemplate,
  publishTemplate,
  touchPresence,
  useTemplate as recordTemplateUse,
} from "@/lib/api";
import { roleCan, PERMISSIONS } from "@/lib/permissions";
import type { Template } from "@/types";
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

export default function TemplateDetailPage() {
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

  const [template, setTemplate] = useState<Template | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const [showDelete, setShowDelete] = useState(false);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setTemplate(await getTemplate(id));
      try {
        await touchPresence("template", id);
      } catch {
        /* ignore */
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load template");
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
      setTemplate(await publishTemplate(id));
      toastSuccess("Template published");
    } finally {
      setBusy(false);
    }
  }

  async function recordUse() {
    setBusy(true);
    try {
      setTemplate(await recordTemplateUse(id));
      toastSuccess("Usage recorded");
    } finally {
      setBusy(false);
    }
  }

  async function copyContent() {
    if (!template?.content) return;
    try {
      await navigator.clipboard.writeText(template.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable */
    }
  }

  async function remove() {
    setBusy(true);
    try {
      await deleteTemplate(id);
      toastSuccess("Template deleted");
      window.location.href = "/templates";
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return (
      <div className="flex justify-center py-24">
        <Spinner label="Loading template" />
      </div>
    );
  }

  if (error || !template) {
    return (
      <ErrorState
        title="Template not found"
        message={error ?? "It may have been deleted."}
      />
    );
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <PageHeader
        breadcrumb="Templates"
        title={template.title}
        description={template.description ?? undefined}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <KnowledgeBadge status={template.status} kind="template" />
            <Button
              size="sm"
              variant="secondary"
              onClick={recordUse}
              loading={busy}
            >
              <Copy className="h-4 w-4" /> Use template
            </Button>
            {canManage && (
              <>
                {template.status !== "published" && (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={publish}
                    loading={busy}
                  >
                    <CheckCircle2 className="h-4 w-4" /> Publish
                  </Button>
                )}
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setShowDelete(true)}
                >
                  <Trash2 className="h-4 w-4 text-danger" />
                </Button>
              </>
            )}
          </div>
        }
      />

      <WatchBar kind="template" entityId={template.id} />

      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 rounded-lg border border-line bg-surface px-4 py-3 text-[12px] text-muted">
        {template.owner_name && (
          <span className="flex items-center gap-1.5">
            <Avatar name={template.owner_name} size="xs" />{" "}
            {template.owner_name}
          </span>
        )}
        <span>v{template.version}</span>
        <span>{template.view_count} views</span>
        <span className="flex items-center gap-1 font-semibold text-brand">
          <Stamp className="h-3.5 w-3.5" /> {template.usage_count} uses
        </span>
        <Badge tone="neutral">{template.kind_name}</Badge>
        {template.category && <Badge tone="neutral">{template.category}</Badge>}
        <span className="ml-auto text-faint">
          Updated {formatDate(template.updated_at)}
        </span>
      </div>

      <div className="card p-6">
        <div className="mb-3 flex items-center justify-between">
          <p className="text-[13px] font-semibold text-ink">Template content</p>
          {template.content && (
            <Button size="sm" variant="ghost" onClick={copyContent}>
              {copied ? "Copied!" : "Copy content"}
            </Button>
          )}
        </div>
        {template.content ? (
          <div className="whitespace-pre-wrap font-mono text-[13px] leading-relaxed text-muted">
            {template.content}
          </div>
        ) : (
          <EmptyState
            icon={Stamp}
            title="Empty template"
            description="This template has no content yet."
          />
        )}
      </div>

      <CommentsPanel kind="template" entityId={template.id} />
      <VersionHistory kind="template" entityId={template.id} />

      <Modal
        open={showDelete}
        onClose={() => setShowDelete(false)}
        title="Delete template?"
        description="This cannot be undone."
      >
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setShowDelete(false)}>
            Cancel
          </Button>
          <Button variant="danger" onClick={remove} loading={busy}>
            Delete
          </Button>
        </div>
      </Modal>
    </div>
  );
}
