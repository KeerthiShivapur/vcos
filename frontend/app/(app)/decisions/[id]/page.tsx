"use client";

import { Suspense, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { Check, Gavel, ThumbsUp, Trash2 } from "lucide-react";

import {
  chooseDecisionOption,
  deleteDecision,
  executeDecisionAction,
  getDecision,
  transitionDecision,
  updateDecision,
  touchPresence,
} from "@/lib/api";
import { roleCan, PERMISSIONS } from "@/lib/permissions";
import type { Decision, FollowUpAction } from "@/types";
import { useAuth } from "@/hooks/useAuth";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Badge } from "@/components/ui/Badge";
import { Avatar } from "@/components/ui/Avatar";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { KnowledgeBadge } from "@/components/knowledge/KnowledgeBadge";
import { WatchBar } from "@/components/knowledge/WatchBar";
import { CommentsPanel } from "@/components/knowledge/CommentsPanel";
import { VersionHistory } from "@/components/knowledge/VersionHistory";
import { formatDate } from "@/lib/utils";
import { toastSuccess } from "@/components/ui/Toaster";

const STATUS_FLOW: Record<string, string> = {
  proposed: "made",
  made: "implemented",
  implemented: "reviewed",
};

const ACTION_TONES: Record<string, "neutral" | "brand" | "success" | "danger"> = {
  pending: "neutral",
  in_progress: "brand",
  completed: "success",
  skipped: "danger",
};

export default function DecisionDetailPage() {
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

  const [decision, setDecision] = useState<Decision | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showDelete, setShowDelete] = useState(false);
  const [chooseModal, setChooseModal] = useState<{ optionId: string; reason: string } | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setDecision(await getDecision(id));
      try {
        await touchPresence("decision", id);
      } catch {
        /* ignore */
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load decision");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function chooseOption() {
    if (!chooseModal) return;
    setBusy(true);
    try {
      setDecision(await chooseDecisionOption(id, chooseModal.optionId, chooseModal.reason || undefined));
      setChooseModal(null);
      toastSuccess("Decision recorded");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to record choice");
    } finally {
      setBusy(false);
    }
  }

  async function advance() {
    if (!decision) return;
    const next = STATUS_FLOW[decision.status];
    if (!next) return;
    setBusy(true);
    try {
      setDecision(await transitionDecision(id, next));
      toastSuccess(`Status: ${next}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to update status");
    } finally {
      setBusy(false);
    }
  }

  async function convertAction(index: number) {
    setBusy(true);
    try {
      const result = await executeDecisionAction(id, index);
      setDecision(result.decision);
      toastSuccess("Action converted to a task and assigned to its owner");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to convert action");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    try {
      await deleteDecision(id);
      toastSuccess("Decision deleted");
      window.location.href = "/decisions";
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return <div className="flex justify-center py-24"><Spinner label="Loading decision" /></div>;
  }

  if (error || !decision) {
    return <ErrorState title="Decision not found" message={error ?? "It may have been deleted."} />;
  }

  const chosen = decision.options?.find((option) => option.chosen);
  const nextStatus = STATUS_FLOW[decision.status];

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <PageHeader
        breadcrumb="Decisions"
        title={decision.title}
        description={decision.description ?? undefined}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <KnowledgeBadge status={decision.status} kind="decision" />
            {canManage && (
              <>
                {nextStatus && (
                  <Button size="sm" variant="secondary" onClick={advance} loading={busy}>
                    <ThumbsUp className="h-4 w-4" /> Mark {nextStatus}
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

      <WatchBar kind="decision" entityId={decision.id} />

      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 rounded-lg border border-line bg-surface px-4 py-3 text-[12px] text-muted">
        {decision.decision_maker_name && <span className="flex items-center gap-1.5"><Avatar name={decision.decision_maker_name} size="xs" /> {decision.decision_maker_name}</span>}
        <span>v{decision.version}</span>
        <span>{decision.view_count} views</span>
        {decision.project_name && <Link href={`/projects/${decision.project_id}`} className="text-brand hover:underline">{decision.project_name}</Link>}
        {decision.decision_date && <span>Decided {formatDate(decision.decision_date)}</span>}
        <span className="ml-auto text-faint">Updated {formatDate(decision.updated_at)}</span>
      </div>

      {chosen && (
        <div className="rounded-lg border border-brand/30 bg-brand-soft/40 p-4">
          <p className="text-[13px] font-semibold text-brand">Chosen option</p>
          <p className="mt-1 text-[15px] font-semibold text-ink">{chosen.title}</p>
          {chosen.chosen_reason && <p className="mt-1 text-[13px] text-muted">{chosen.chosen_reason}</p>}
        </div>
      )}

      {decision.context && (
        <div className="card p-6">
          <p className="mb-2 text-[13px] font-semibold text-ink">Context</p>
          <div className="whitespace-pre-wrap text-[14px] leading-relaxed text-muted">{decision.context}</div>
        </div>
      )}

      {decision.impact && (
        <div className="card p-6">
          <p className="mb-2 text-[13px] font-semibold text-ink">Expected impact</p>
          <div className="whitespace-pre-wrap text-[14px] leading-relaxed text-muted">{decision.impact}</div>
        </div>
      )}

      <div className="card p-6">
        <div className="mb-4 flex items-center gap-2">
          <Gavel className="h-4 w-4 text-brand" />
          <p className="text-[13px] font-semibold text-ink">Options considered</p>
        </div>
        <div className="space-y-3">
          {decision.options?.map((option) => (
            <div key={option.id} className={`rounded-lg border p-4 ${option.chosen ? "border-brand/50 bg-brand-soft/30" : "border-line"}`}>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="flex items-center gap-2 text-[14px] font-semibold text-ink">
                    {option.chosen && <Check className="h-4 w-4 text-brand" />}
                    {option.title}
                  </p>
                  {option.description && <p className="mt-0.5 text-[13px] text-muted">{option.description}</p>}
                </div>
                {canManage && !option.chosen && !chosen && (
                  <Button size="sm" variant="secondary" onClick={() => setChooseModal({ optionId: option.id, reason: "" })}>
                    <Check className="h-4 w-4" /> Choose
                  </Button>
                )}
              </div>
              {(option.pros || option.cons) && (
                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  {option.pros && (
                    <div className="rounded-md bg-emerald-50 px-3 py-2">
                      <p className="text-[11px] font-bold uppercase tracking-wide text-emerald-600">Pros</p>
                      <p className="mt-0.5 whitespace-pre-wrap text-[13px] text-muted">{option.pros}</p>
                    </div>
                  )}
                  {option.cons && (
                    <div className="rounded-md bg-rose-50 px-3 py-2">
                      <p className="text-[11px] font-bold uppercase tracking-wide text-rose-600">Cons</p>
                      <p className="mt-0.5 whitespace-pre-wrap text-[13px] text-muted">{option.cons}</p>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {decision.follow_up_actions && decision.follow_up_actions.length > 0 && (
        <div className="card p-6">
          <div className="mb-4 flex items-center gap-2">
            <Check className="h-4 w-4 text-brand" />
            <p className="text-[13px] font-semibold text-ink">Follow-up actions</p>
            <span className="ml-auto text-[12px] text-faint">
              {decision.follow_up_actions.filter((a) => a.status !== "completed").length} open
            </span>
          </div>
          <div className="space-y-3">
            {decision.follow_up_actions.map((action, index) => (
              <FollowUpRow
                key={index}
                action={action}
                index={index}
                decision={decision}
                canManage={canManage}
                busy={busy}
                onConvert={convertAction}
              />
            ))}
          </div>
          <p className="mt-4 text-[12px] text-faint">
            When every converted task is completed, the decision is automatically marked implemented.
          </p>
        </div>
      )}

      {decision.participants && decision.participants.length > 0 && (
        <div className="card p-6">
          <p className="mb-3 text-[13px] font-semibold text-ink">Participants</p>
          <div className="flex flex-wrap gap-2">
            {decision.participants.map((participant) => (
              <div key={participant.id} className="flex items-center gap-2 rounded-md border border-line bg-canvas px-2.5 py-1.5">
                <Avatar name={participant.employee_name ?? participant.employee_id} size="xs" />
                <span className="text-[13px] font-medium text-ink">{participant.employee_name ?? participant.employee_id}</span>
                <Badge tone="neutral">{participant.role}</Badge>
              </div>
            ))}
          </div>
        </div>
      )}

      {decision.future_review_date && (
        <div className="rounded-lg border border-line bg-surface px-4 py-3 text-[12px] text-muted">
          Review scheduled: {formatDate(decision.future_review_date)}
        </div>
      )}

      <CommentsPanel kind="decision" entityId={decision.id} />
      <VersionHistory kind="decision" entityId={decision.id} />

      <Modal
        open={chooseModal !== null}
        onClose={() => setChooseModal(null)}
        title="Record this choice?"
        description="This will mark the option as chosen and log the reasoning."
      >
        <textarea
          className="w-full rounded-lg border border-line bg-canvas px-3 py-2 text-sm text-ink outline-none focus:border-brand"
          rows={3}
          placeholder="Why this option? (optional)"
          value={chooseModal?.reason ?? ""}
          onChange={(e) => setChooseModal((prev) => (prev ? { ...prev, reason: e.target.value } : prev))}
        />
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setChooseModal(null)}>Cancel</Button>
          <Button variant="secondary" onClick={chooseOption} loading={busy}>Record choice</Button>
        </div>
      </Modal>

      <Modal open={showDelete} onClose={() => setShowDelete(false)} title="Delete decision?" description="This cannot be undone.">
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setShowDelete(false)}>Cancel</Button>
          <Button variant="danger" onClick={remove} loading={busy}>Delete</Button>
        </div>
      </Modal>
    </div>
  );
}

function FollowUpRow({
  action,
  index,
  decision,
  canManage,
  busy,
  onConvert,
}: {
  action: FollowUpAction;
  index: number;
  decision: Decision;
  canManage: boolean;
  busy: boolean;
  onConvert: (index: number) => void;
}) {
  const task = action.task_id ? decision.tasks?.find((t) => t.id === action.task_id) ?? null : null;
  return (
    <div className="rounded-lg border border-line p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[14px] font-semibold text-ink">{action.text}</p>
          <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-muted">
            <span className="flex items-center gap-1.5">
              <Avatar name={action.owner_name ?? action.owner_id ?? "?"} size="xs" />
              {action.owner_name ?? "Unassigned"}
            </span>
            {task && (
              <Link href={`/tasks/${task.id}`} className="text-brand hover:underline">
                {task.title} · {task.status.replace(/_/g, " ")}
              </Link>
            )}
            {action.project_id && decision.tasks?.length === 0 && <span>Project linked</span>}
            {action.goal_id && <span>Goal linked</span>}
            {action.due_date && <span>Due {formatDate(action.due_date)}</span>}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Badge tone={ACTION_TONES[action.status] ?? "neutral"}>{action.status.replace(/_/g, " ")}</Badge>
          {canManage && !task && action.status === "pending" && (
            <Button size="sm" variant="secondary" loading={busy} onClick={() => onConvert(index)}>
              <Check className="h-4 w-4" /> Convert to task
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
